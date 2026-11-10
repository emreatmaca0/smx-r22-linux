#!/usr/bin/env python3
"""smx — configuration tool for the SMX-R22 gaming mouse (USB 30fa:1040) on Linux.

The protocol was reverse engineered from the vendor's Windows software (build 2022-05-17)
for interoperability; see PROTOCOL.md.

  smx                             visual terminal interface
  smx tui [--demo SNAPSHOT]       --demo: simulate the mouse from a snapshot/backup file
  smx status | backup [-o F] | restore F
  smx dpi LEVEL DPI | dpi-enable 1,2,3 | dpi-active LEVEL
  smx dump START LENGTH           hex dump of flash (read-only)
  smx listen [SECONDS]            print raw input reports (read-only)
  smx --lang tr|en ...            change and save the interface language

Safety:
  * The flash header 0x00-0x07 (USB VID/PID) is never written.
  * Only whitelisted blocks are written; unknown bits inside them are preserved.
  * Every written block is read back and verified.
"""
import argparse, datetime, fcntl, glob, json, os, select, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import smx_i18n as i18n
import smx_keys as K
from smx_i18n import T

VID, PID = 0x30FA, 0x1040
RID, REPORT_LEN = 7, 8

HEADER = range(0x00, 0x08)
CFG_START, CFG_LEN = 0x08, 0x38                  # decoded settings region: 0x08..0x3f
WRITABLE = {0x08, 0x10, 0x18, 0x20, 0x28, 0x30, 0x38}
DESC_BLOCKS = set(range(K.DESC_BASE, K.desc_addr(13) + K.DESC_LEN, 8))   # profile 0 descriptors
SC_BLOCKS = set(range(K.SC_AREA, K.body_addr(8), 8))                    # own macro area 0xe00-0xeff
ALLOWED = WRITABLE | DESC_BLOCKS | SC_BLOCKS
RESTORABLE = range(0x08, 0x100, 8)
BACKUP_RANGES = [(0x0000, 0x100), (0x0fa0, 8)]

# ------------------------------------------------------------------ constant tables
# DPI code -> DPI (vendor software 0x411b2a). Code 11 is unused.
DPI_BY_CODE = {c: c * 200 for c in range(1, 11)}
DPI_BY_CODE.update({12: 2400, 13: 3200, 14: 4000, 15: 4800, 16: 5600, 17: 6400,
                    18: 7200, 19: 8000, 20: 8800, 21: 9600, 22: 10400, 23: 11200, 24: 12800})
CODE_BY_DPI = {v: k for k, v in DPI_BY_CODE.items()}
DPI_VALUES = sorted(CODE_BY_DPI)

# Button functions (key byte), in display order
FUNC_CODES = [0x21, 0x23, 0x22, 0x24, 0x25, 0x26, 0x2b, 0x2c, 0x28, 0x29, 0x27, 0x35, 0x00]
LEFT_CLICK = 0x21
# Physical buttons -> flash slot index (KeyNum=7; slots 0-5 and 7)
BUTTON_SLOTS = [0, 2, 1, 3, 4, 5, 7]
FACTORY_KEYS = bytes.fromhex('2122232425260035')

LED_OFF, LED_REACT, LED_COUNT = 13, 12, 14
LED_SPEEDS = range(0, 6)          # 0 slow … 5 fast (period = 1200 - 200 * speed ms)
LED_BRIGHTS = range(0, 5)
FIRE_RANGE = range(8, 304, 8)     # ms

# How DPI colours are stored in flash. Verified on hardware: the LED driver lights each channel
# at 255 - value (bytes 00 ff ff show red), in R, G, B order. Both can be changed by the user
# (settings "color_order" / "color_invert") in case another revision behaves differently.
COLOR_ORDERS = ['RGB', 'BGR', 'GRB', 'GBR', 'RBG', 'BRG']
COLOR_ORDER = 'RGB'
COLOR_INVERT = True


def func_name(code):
    names = i18n.FUNC_NAMES[i18n.LANG]
    if code in names:
        return names[code]
    kinds = i18n.FUNC_KINDS[i18n.LANG]
    return f'{kinds.get(code & 0x1f, kinds[None])} ({code:#04x})'


def button_name(slot):
    return i18n.BUTTON_NAMES[i18n.LANG][slot]


def led_mode_name(m):
    return i18n.LED_MODES[i18n.LANG][m]


def load_settings():
    """Load user settings (language, colour order). Returns True on first run."""
    global COLOR_ORDER, COLOR_INVERT
    first = i18n.load()
    if 'color_order' in i18n.SETTINGS and 'color_invert' not in i18n.SETTINGS:
        set_color_mapping('RGB', True)               # migrate from versions without inversion
    if i18n.SETTINGS.get('color_order') in COLOR_ORDERS:
        COLOR_ORDER = i18n.SETTINGS['color_order']
    if isinstance(i18n.SETTINGS.get('color_invert'), bool):
        COLOR_INVERT = i18n.SETTINGS['color_invert']
    return first


COLOR_MAPPINGS = [(o, inv) for inv in (True, False) for o in COLOR_ORDERS]


def set_color_mapping(order, invert):
    global COLOR_ORDER, COLOR_INVERT
    COLOR_ORDER, COLOR_INVERT = order, invert
    i18n.set_setting('color_order', order)
    i18n.set_setting('color_invert', invert)


# ------------------------------------------------------------------ HID transport
def _ioc(nr, n):
    return (3 << 30) | (n << 16) | (ord('H') << 8) | nr


class DeviceError(Exception):
    pass


def _hidraw_nodes():
    for dev in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
        try:
            if f'{VID:08X}:{PID:08X}' in open(f'{dev}/device/uevent').read():
                yield '/dev/' + os.path.basename(dev), open(f'{dev}/device/report_descriptor', 'rb').read()
        except OSError:
            continue


def find_dev():
    """The vendor interface: usage page 0xFF01 with feature report 7."""
    for path, desc in _hidraw_nodes():
        if b'\x06\x01\xff' in desc and b'\x85\x07' in desc:
            return path
    raise DeviceError(T('err_notfound'))


class HidTransport:
    demo = False

    def __init__(self, dry_run=False, verbose=False):
        self.path = find_dev()
        try:
            self.fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
        except PermissionError:
            raise DeviceError(T('err_perm', p=self.path))
        self.dry_run, self.verbose = dry_run, verbose
        self.mouse_fd = None          # pointer interface (report 1), read-only, for live preview
        for path, desc in _hidraw_nodes():
            if b'\x09\x02\xa1\x01\x85\x01' in desc:
                try:
                    self.mouse_fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                except OSError:
                    pass
                break

    def close(self):
        os.close(self.fd)
        if self.mouse_fd is not None:
            os.close(self.mouse_fd)

    def set(self, pkt, mutating=False):
        if self.verbose or (self.dry_run and mutating):
            print('   →', bytes(pkt).hex(' '), '(dry-run)' if self.dry_run and mutating else '')
        if self.dry_run and mutating:
            return
        fcntl.ioctl(self.fd, _ioc(0x06, REPORT_LEN), bytearray(pkt))

    def get(self):
        buf = bytearray([RID] + [0] * (REPORT_LEN - 1))
        fcntl.ioctl(self.fd, _ioc(0x07, REPORT_LEN), buf)
        return buf

    def events(self):
        """All pending input reports from both interfaces (non-blocking)."""
        out = []
        for fd in (self.fd, self.mouse_fd):
            if fd is None:
                continue
            for _ in range(4000):                       # drain 1000 Hz motion reports
                if not select.select([fd], [], [], 0)[0]:
                    break
                try:
                    out.append(os.read(fd, 64))
                except OSError:
                    break
        return out


class FakeTransport:
    """Simulated mouse backed by a snapshot/backup file (demo mode and tests)."""
    demo = True

    def __init__(self, snapshot_path):
        snap = json.load(open(snapshot_path))
        self.mem = bytearray(0x1000)
        for start, hexdata in snap['ranges'].items():
            b = bytes.fromhex(hexdata)
            self.mem[int(start, 16):int(start, 16) + len(b)] = b
        self.path = f'demo:{os.path.basename(snapshot_path)}'
        self.buf, self.out, self.log, self.pending, self.dry_run = bytearray(8), 0, [], [], False

    def close(self):
        pass

    def set(self, p, mutating=False):
        assert p[0] == RID and p[1] == 0x18
        self.log.append(bytes(p))
        sub, i, addr, data, last = p[2], p[3], p[4] | p[5] << 8, p[6], p[7]
        if sub == 0x03:
            self.buf[i] = data
        elif sub == 0x09:
            assert addr >= 8, 'header write!'
            self.mem[addr:addr + last + 1] = self.buf[:last + 1]
        elif sub == 0x05:
            self.out = self.mem[addr + i]

    def get(self):
        return bytearray([RID, self.out, 0, 0, 0, 0, 0, 0])

    def events(self):
        ev, self.pending = self.pending, []
        return ev

    def press_dpi(self, report=True):
        """Demo: the DPI button on the mouse. report=False simulates a missed event."""
        en, cur = self.mem[0x19] & 0x3f, self.mem[0x18] & 7
        nxt = next((cur + k) % 6 for k in range(1, 7) if en >> ((cur + k) % 6) & 1)
        self.mem[0x18] = (self.mem[0x18] & 0xf8) | nxt
        if report:
            self.pending += [bytes([6, 0xf6, 0x80 | nxt]), bytes([6, 0xf6, nxt])]


def ms(n):
    time.sleep(n / 1000)


class Mouse:
    """Flash access via command 0x18 (vendor software 0x40e620 / 0x40e760 / 0x40e860 / 0x40ead0)."""

    def __init__(self, t):
        self.t = t

    @staticmethod
    def _pkt(sub, i=0, addr=0, data=0, last=0):
        assert sub in (0x00, 0x03, 0x05, 0x09, 0x10)
        return [RID, 0x18, sub, i, addr & 0xff, (addr >> 8) & 0xff, data, last]

    def read_block(self, addr, n=8):
        for i in range(n):
            self.t.set(self._pkt(0x03, i, addr, 0, n - 1)); ms(2)
        ms(2)
        self.t.set(self._pkt(0x00, 0, addr))
        out = bytearray()
        for i in range(n):
            self.t.set(self._pkt(0x05, i, addr, 0, n - 1)); ms(2)
            out.append(self.t.get()[1])
        ms(2)
        self.t.set(self._pkt(0x00))
        return bytes(out)

    def read(self, start, length):
        data = bytearray()
        for a in range(start, start + length, 8):
            data += self.read_block(a, min(8, start + length - a))
        return bytes(data)

    def write_block(self, addr, data, allowed):
        n = len(data)
        if n != 8 or addr % 8:
            raise ValueError('only aligned 8-byte blocks can be written')
        if any(a in HEADER for a in range(addr, addr + n)):
            raise PermissionError('header block (VID/PID) must never be written')
        if addr not in allowed:
            raise PermissionError(f'block {addr:#06x} is not writable')
        for i, b in enumerate(data):
            self.t.set(self._pkt(0x03, i, addr, b, n - 1), mutating=True)
        ms(4)
        self.t.set(self._pkt(0x09, 0, addr, 0, n - 1), mutating=True); ms(2)
        self.t.set(self._pkt(0x00, 0, addr), mutating=True)

    def apply(self):
        self.t.set(self._pkt(0x10), mutating=True); ms(5)
        self.t.set(self._pkt(0x00), mutating=True)


# ------------------------------------------------------------------ settings model
class Config:
    """Field-level view of flash 0x08..0x3f; r[addr - 0x08]."""

    FIELDS = ([f'key{i}' for i in range(9)] + [f'dpi{i}' for i in range(6)] +
              ['dpi_en', 'dpi_active'] + [f'color{i}' for i in range(6)] +
              ['led', 'bright', 'fire'])

    def __init__(self, region):
        assert len(region) == CFG_LEN
        self.r = bytearray(region)
        self.touched = None

    def copy(self):
        return Config(bytes(self.r))

    def _b(self, addr):
        return self.r[addr - CFG_START]

    def _s(self, addr, v):
        if self.touched is not None:
            self.touched.add(addr)
        self.r[addr - CFG_START] = v & 0xff

    def get(self, name):
        if name.startswith('key'):
            i = int(name[3:])
            return self._b(0x08 + i) if i < 8 else self._b(0x10)
        if name.startswith('dpi') and name[3:].isdigit():
            i = int(name[3:])
            hi = (self._b(0x13) >> i) & 1
            pair = self._b(0x15 + i // 2)
            lo = pair >> 4 if i % 2 == 0 else pair & 15
            return lo | hi << 4
        if name == 'dpi_en':
            return self._b(0x19) & 0x3f
        if name == 'dpi_active':
            return self._b(0x18) & 7
        if name.startswith('color'):
            i = int(name[5:])
            raw = [self._b(0x20 + 3 * i + k) for k in range(3)]
            if COLOR_INVERT:
                raw = [255 - x for x in raw]
            return tuple(raw[COLOR_ORDER.index(c)] for c in 'RGB')
        if name == 'led':
            b4 = self._b(0x1c)
            speed = b4 & 7
            if speed == 7:
                return (LED_OFF, 2)
            if b4 & 0x08:
                return (LED_REACT, speed)
            return (((b4 >> 4) & 7) | (8 if self._b(0x33) & 0x80 else 0), speed)
        if name == 'bright':
            return (self._b(0x3f) >> 4) & 7
        if name == 'fire':
            return (self._b(0x1a) | self._b(0x1b) << 8) * 8
        raise KeyError(name)

    def set(self, name, v):
        if name.startswith('key'):
            i = int(name[3:])
            self._s(0x08 + i if i < 8 else 0x10, v)
        elif name.startswith('dpi') and name[3:].isdigit():
            i = int(name[3:])
            assert v in DPI_BY_CODE
            self._s(0x13, (self._b(0x13) & ~(1 << i)) | ((v >> 4) & 1) << i)
            a, pair = 0x15 + i // 2, self._b(0x15 + i // 2)
            self._s(a, (pair & 0x0f) | (v & 15) << 4 if i % 2 == 0 else (pair & 0xf0) | (v & 15))
        elif name == 'dpi_en':
            self._s(0x19, (self._b(0x19) & 0xc0) | (v & 0x3f))
        elif name == 'dpi_active':
            self._s(0x18, (self._b(0x18) & 0xf8) | (v & 7))
        elif name.startswith('color'):
            i = int(name[5:])
            rgb = dict(zip('RGB', v))
            for k, c in enumerate(COLOR_ORDER):
                self._s(0x20 + 3 * i + k, 255 - rgb[c] if COLOR_INVERT else rgb[c])
        elif name == 'led':
            mode, speed = v
            b4, b33 = self._b(0x1c), self._b(0x33)
            if mode == LED_OFF:
                self._s(0x1c, 0x80 | (b4 & 0x70) | 7)
            elif mode == LED_REACT:
                self._s(0x1c, 0x80 | 0x10 | 0x08 | (speed & 7))
                self._s(0x33, 0x40 | (b33 & 0x3f))
            else:
                self._s(0x1c, 0x80 | (mode & 7) << 4 | (speed & 7))
                self._s(0x33, (0xc0 if mode & 8 else 0x40) | (b33 & 0x3f))
        elif name == 'bright':
            self._s(0x3f, (self._b(0x3f) & 0x8f) | (v & 7) << 4)
        elif name == 'fire':
            n = v // 8
            self._s(0x1a, n & 0xff); self._s(0x1b, n >> 8)
        else:
            raise KeyError(name)

    def dpi(self, i):
        return DPI_BY_CODE.get(self.get(f'dpi{i}'))

    def blocks(self):
        return {CFG_START + o: bytes(self.r[o:o + 8]) for o in range(0, CFG_LEN, 8)}

    def blocks_of(self, fields):
        """The 8-byte blocks touched when writing these fields."""
        probe = self.copy()
        probe.touched = set()
        for f in fields:
            probe.set(f, self.get(f))
        return sorted({a & ~7 for a in probe.touched})

    def problems(self):
        out = []
        if LEFT_CLICK not in [self.get(f'key{s}') for s in BUTTON_SLOTS]:
            out.append(T('err_left'))
        en = self.get('dpi_en')
        if not en:
            out.append(T('err_one_level'))
        elif not (en >> self.get('dpi_active')) & 1:
            out.append(T('err_active_off'))
        return out


# ------------------------------------------------------------------ session
def backup_dir():
    return os.path.join(i18n.data_dir(), 'backups')


class Session:
    """Device access + backups + safe writes."""

    def __init__(self, transport):
        self.t, self.m = transport, Mouse(transport)
        self.snap = bytearray(0x100)

    def close(self):
        self.t.close()

    def read_config(self):
        return Config(self.m.read(CFG_START, CFG_LEN))

    def snapshot(self):
        """Single read of 0x000-0x0ff: header + settings + profile 0 shortcut descriptors."""
        self.snap = bytearray(self.m.read(0x000, 0x100))
        return Config(bytes(self.snap[CFG_START:CFG_START + CFG_LEN]))

    def read_active(self):
        """Currently active DPI level (0-based), straight from flash (one 8-byte block)."""
        return self.m.read_block(0x18)[0] & 7

    def backup(self, path=None, snap=None):
        if self.t.demo:
            return None
        try:
            data = {f'{s:#06x}': (bytes(snap) if snap is not None and (s, n) == (0, 0x100)
                                  else self.m.read(s, n)).hex() for s, n in BACKUP_RANGES}
            if path is None:
                d = backup_dir()
                os.makedirs(d, exist_ok=True)
                path = os.path.join(d, datetime.datetime.now().strftime('smx-%Y%m%d-%H%M%S-%f.json'))
            with open(path, 'w') as f:
                json.dump({'device': f'{VID:04x}:{PID:04x}', 'ranges': data}, f, indent=1)
            i18n._chown(path)
            i18n._chown(os.path.dirname(path))
        except OSError as e:
            raise IOError(T('err_backup', e=e.strerror, d=e.filename or backup_dir())) from None
        return path

    def _write(self, old_blocks, new_blocks, backup_path=None, allowed=WRITABLE):
        todo = [a for a in new_blocks if new_blocks[a] != old_blocks[a]]   # in the given order
        if any(a not in allowed for a in todo):
            raise PermissionError('unexpected block change')
        for a in todo:
            self.m.write_block(a, new_blocks[a], allowed)
        if todo:
            self.m.apply()
        if todo and not self.t.dry_run:
            ms(10)
            for a in todo:
                if self.m.read_block(a) != new_blocks[a]:
                    raise IOError(T('err_verify', a=f'{a:#04x}', b=backup_path or '-'))
        return todo

    def apply(self, edited, dirty, backup=True):
        """Full read + merge + backup + write (CLI). Returns (blocks, backup path, new Config)."""
        fresh = self.read_config()
        target = fresh.copy()
        for name in dirty:
            target.set(name, edited.get(name))
        bad = target.problems()
        if bad:
            raise ValueError(' '.join(bad))
        if fresh.blocks() == target.blocks():
            return [], None, fresh
        bpath = self.backup() if backup and not self.t.dry_run else None
        todo = self._write(fresh.blocks(), target.blocks(), bpath)
        return todo, bpath, target

    def live_apply(self, cache, edited, dirty):
        """Instant apply: refresh only the affected blocks from the mouse, merge the dirty
        fields, write, verify. `cache` is the last known device state.
        Returns (written blocks, new cache)."""
        blocks = cache.blocks_of(dirty)
        fresh = cache.copy()
        for a in blocks:
            o = a - CFG_START
            fresh.r[o:o + 8] = self.m.read_block(a)
        target = fresh.copy()
        for name in dirty:
            target.set(name, edited.get(name))
        bad = target.problems()
        if bad:
            raise ValueError(' '.join(bad))
        old = {a: fresh.blocks()[a] for a in blocks}
        new = {a: target.blocks()[a] for a in blocks}
        return self._write(old, new), target

    # ---------------------------------------------------- shortcuts
    def _read_range(self, addr, n):
        start, end = addr & ~7, (addr + n + 7) & ~7
        data = self.m.read(start, end - start)
        return data[addr - start:addr - start + n]

    def read_shortcuts(self, cfg):
        """{slot: Shortcut} for profile 0. Call after snapshot()."""
        out = {}
        for slot in BUTTON_SLOTS:
            code = cfg.get(f'key{slot}')
            a = K.desc_addr(slot)
            d = K.parse_desc(bytes(self.snap[a:a + K.DESC_LEN]))
            try:
                if code & 0x1f in K.MACRO_KINDS and 0 < d['count'] < 64 and 0x100 <= d['addr'] < 0xf20:
                    sc = K.decode_body(self._read_range(d['addr'], 2 + 2 * d['count'] + 16), d['count'])
                    if sc.keys:
                        out[slot] = sc
                elif code & 0x1f == 0x0f and d['consumer']:
                    out[slot] = K.Shortcut(consumer=d['consumer'])
            except Exception:
                pass
        return out

    def set_shortcut(self, cache, slot, sc):
        """Assign a shortcut: write body -> descriptor -> key byte, apply, verify.
        Returns the new cache (Config)."""
        body, desc, code = K.encode(sc, slot)
        trial = cache.copy()
        trial.set(f'key{slot}', code)
        bad = trial.problems()
        if bad:
            raise ValueError(' '.join(bad))
        plan, old = {}, {}                                   # ordered: block -> new content
        if body is not None:
            base = K.body_addr(slot)
            for o in range(0, len(body), 8):
                old[base + o] = self.m.read_block(base + o)
                plan[base + o] = body[o:o + 8]
        da = K.desc_addr(slot)
        for blk in range(da & ~7, da + K.DESC_LEN, 8):
            old[blk] = self.m.read_block(blk)
            cur = bytearray(old[blk])
            for i in range(8):
                if da <= blk + i < da + K.DESC_LEN:
                    cur[i] = desc[blk + i - da]
            plan[blk] = bytes(cur)
        key_blk = 0x08 if slot < 8 else 0x10
        old[key_blk] = self.m.read_block(key_blk)
        fresh = bytearray(old[key_blk])
        fresh[slot if slot < 8 else 0] = code
        plan[key_blk] = bytes(fresh)
        self._write(old, plan, allowed=ALLOWED)
        for blk in range(da & ~7, da + K.DESC_LEN, 8):        # keep the snapshot current
            self.snap[blk:blk + 8] = plan[blk]
        new = cache.copy()
        new.r[key_blk - CFG_START:key_blk - CFG_START + 8] = plan[key_blk]
        return new

    def restore(self, path):
        snap = json.load(open(path))
        region = bytes.fromhex(snap['ranges']['0x0000'])
        cur = self.m.read(0x00, 0x100)
        if region[:8] != cur[:8]:
            raise ValueError(f'header mismatch (backup {region[:8].hex(" ")} / mouse {cur[:8].hex(" ")})')
        todo = [a for a in RESTORABLE if region[a:a + 8] != cur[a:a + 8]]
        if not todo:
            return []
        if not self.t.dry_run:
            self.backup()
        for a in todo:
            self.m.write_block(a, region[a:a + 8], set(RESTORABLE))
        self.m.apply()
        if not self.t.dry_run:
            ms(20)
            bad = [a for a in todo if self.m.read_block(a) != region[a:a + 8]]
            if bad:
                raise IOError(f'unverified blocks: {[hex(x) for x in bad]}')
        return todo


# ------------------------------------------------------------------ CLI
def print_status(cfg, shortcuts=None):
    shortcuts = shortcuts or {}
    print(T('cli_levels'))
    en, act = cfg.get('dpi_en'), cfg.get('dpi_active')
    for i in range(6):
        r, g, b = cfg.get(f'color{i}')
        state = T('cli_on') if en >> i & 1 else T('cli_off')
        print(f'  {"▶" if i == act else " "} {i + 1}: {cfg.dpi(i) or "?":>6} DPI  [{state:^6}]  '
              f'{T("cli_color")} #{r:02x}{g:02x}{b:02x}')
    mode, speed = cfg.get('led')
    print(f'{T("cli_led")}: {led_mode_name(mode)}  {T("speed")}={speed}  {T("brightness")}={cfg.get("bright")}')
    print(f'{T("fire")}: {cfg.get("fire")} ms')
    print(T('cli_keys'))
    for slot in BUTTON_SLOTS:
        code = cfg.get(f'key{slot}')
        sc = shortcuts.get(slot) if code & 0x1f in K.MACRO_KINDS + (0x0f,) else None
        print(f'  {button_name(slot):20} {sc.label() if sc else func_name(code)}')


def cli_change(sess, args, field, value):
    cfg = sess.read_config()
    edited = cfg.copy()
    edited.set(field, value)
    try:
        todo, bpath, _ = sess.apply(edited, [field])
    except (ValueError, IOError) as e:
        sys.exit(f'{T("error")}: {e}')
    if not todo:
        print(T('cli_nochange'))
        return
    print(T('cli_written', b=', '.join(f'{a:#04x}' for a in todo)))
    if not args.dry_run:
        print(T('cli_backup', f=bpath))
        print(T('cli_verified'))


def parse_levels(s):
    lv = sorted({int(x) for x in s.split(',') if x.strip()})
    if not lv or any(not 1 <= x <= 6 for x in lv):
        raise argparse.ArgumentTypeError('1-6')
    return lv


def main(argv=None):
    first_run = load_settings()
    p = argparse.ArgumentParser(prog='smx', description=T('title'))
    p.add_argument('-v', '--verbose', action='store_true', help='print HID packets')
    p.add_argument('--lang', choices=sorted(i18n.LANGS))
    sub = p.add_subparsers(dest='cmd')
    s = sub.add_parser('tui', help='visual interface (default)'); s.add_argument('--demo', metavar='SNAPSHOT')
    sub.add_parser('status', help='show the current settings')
    s = sub.add_parser('backup', help='back up the settings region'); s.add_argument('-o', '--output')
    s = sub.add_parser('dpi', help='set the DPI of a level')
    s.add_argument('level', type=int, choices=range(1, 7), metavar='LEVEL'); s.add_argument('value', type=int, metavar='DPI')
    s = sub.add_parser('dpi-enable', help='levels the DPI button cycles through')
    s.add_argument('levels', type=parse_levels, metavar='1,2,...')
    s = sub.add_parser('dpi-active', help='select the active level')
    s.add_argument('level', type=int, choices=range(1, 7), metavar='LEVEL')
    s = sub.add_parser('restore', help='restore a backup (header excluded)'); s.add_argument('file')
    s = sub.add_parser('dump', help='hex dump of flash (read-only)')
    s.add_argument('start', type=lambda x: int(x, 0)); s.add_argument('length', type=lambda x: int(x, 0))
    s = sub.add_parser('listen', help='print raw input reports (read-only)')
    s.add_argument('seconds', type=float, nargs='?', default=15)
    for name in ('dpi', 'dpi-enable', 'dpi-active', 'restore'):
        sub.choices[name].add_argument('--dry-run', action='store_true', help='show packets, do not send')
    a = p.parse_args(argv)
    if a.lang:
        i18n.save(a.lang)

    if a.cmd in (None, 'tui'):
        import smx_tui
        return smx_tui.run(getattr(a, 'demo', None), first_run and not a.lang)

    try:
        sess = Session(HidTransport(dry_run=getattr(a, 'dry_run', False), verbose=a.verbose))
    except DeviceError as e:
        sys.exit(f'{T("error")}: {e}')
    try:
        if a.cmd == 'status':
            cfg = sess.snapshot()
            print_status(cfg, sess.read_shortcuts(cfg))
        elif a.cmd == 'backup':
            print(T('cli_backedup', f=sess.backup(a.output)))
        elif a.cmd == 'dpi':
            if a.value not in CODE_BY_DPI:
                sys.exit(T('cli_valid_dpi', v=', '.join(map(str, DPI_VALUES))))
            cli_change(sess, a, f'dpi{a.level - 1}', CODE_BY_DPI[a.value])
        elif a.cmd == 'dpi-enable':
            cli_change(sess, a, 'dpi_en', sum(1 << (x - 1) for x in a.levels))
        elif a.cmd == 'dpi-active':
            cli_change(sess, a, 'dpi_active', a.level - 1)
        elif a.cmd == 'restore':
            todo = sess.restore(a.file)
            print(T('cli_same') if not todo else T('cli_restored', b=', '.join(f'{x:#04x}' for x in todo)))
        elif a.cmd == 'dump':
            data = sess.m.read(a.start, a.length)
            for o in range(0, len(data), 16):
                print(f'{a.start + o:04x}: {data[o:o + 16].hex(" ")}')
        elif a.cmd == 'listen':
            print(T('cli_listen', s=a.seconds))
            end = time.time() + a.seconds
            while time.time() < end:
                for ev in sess.t.events():
                    if ev[:1] != b'\x01' or ev[1:2] != b'\x00':      # skip pure motion reports
                        print('  ', ev.hex(' '))
                time.sleep(0.01)
    finally:
        sess.close()


if __name__ == '__main__':
    main()
