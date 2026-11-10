"""Keyboard shortcuts and media keys: HID usage codes, catalog, flash macro format.

Flash format (reverse engineered from the vendor software, verified against a live Win+L macro):
  Key byte      0x2d (= 0x20 | 0x0d "macro / shortcut"),  0x2f (= 0x20 | 0x0f "media key")
  Descriptor    at 0xa0 + 10 * (profile * 14 + slot), 10 bytes:
                [0] delay unit - 1 (0 -> 1 ms)   [1] event count (low 7 bits)   [2] 0xff
                [3..4] consumer usage (media)    [5..6] body address (14 bits)
                [7] 0   [8] 1   [9] 0
  Body          [repeat lo, repeat hi] + events; event = [delay (7 bits) | 0x80 = press][HID usage]
                Delays above 127 ms are continued by extra "7f 00" entries after the event.
"""
import smx_i18n as i18n

# ---------------------------------------------------------------- HID keyboard usages
MODS = [('Ctrl', 0xe0), ('Shift', 0xe1), ('Alt', 0xe2), ('Win', 0xe3)]
MOD_NAME = {0xe0: 'Ctrl', 0xe1: 'Shift', 0xe2: 'Alt', 0xe3: 'Win',
            0xe4: 'RCtrl', 0xe5: 'RShift', 0xe6: 'AltGr', 0xe7: 'RWin'}

KEYS = [(chr(ord('A') + i), 0x04 + i) for i in range(26)]
KEYS += [(str(i), 0x1e + i - 1) for i in range(1, 10)] + [('0', 0x27)]
KEYS += [(f'F{i}', 0x3a + i - 1) for i in range(1, 13)]
KEYS += [('Enter', 0x28), ('Esc', 0x29), ('Backspace', 0x2a), ('Tab', 0x2b), ('Space', 0x2c),
         ('-', 0x2d), ('=', 0x2e), ('[', 0x2f), (']', 0x30), (';', 0x33), ("'", 0x34), (',', 0x36),
         ('.', 0x37), ('/', 0x38), ('Print', 0x46), ('Pause', 0x48), ('Insert', 0x49), ('Home', 0x4a),
         ('PgUp', 0x4b), ('Delete', 0x4c), ('End', 0x4d), ('PgDn', 0x4e), ('→', 0x4f), ('←', 0x50),
         ('↓', 0x51), ('↑', 0x52), ('Menu', 0x65), ('Mute', 0x7f), ('Vol+', 0x80), ('Vol−', 0x81)]
KEY_NAME = dict((v, k) for k, v in KEYS)
KEY_NAME.update(MOD_NAME)

# Consumer-page usages used by the vendor software (media keys)
CONSUMER_NAME = {0x223: 'Browser', 0x183: 'Media player', 0x18a: 'Mail', 0xe9: 'Vol+', 0xea: 'Vol−',
                 0xb6: '⏮', 0xb5: '⏭', 0xe2: 'Mute', 0xcd: '⏯', 0x192: 'Calc', 0xb7: '⏹'}


class Shortcut:
    """keys: HID usages in press order; or consumer: a consumer-page usage (media key)."""

    def __init__(self, keys=(), consumer=None):
        self.keys, self.consumer = tuple(keys), consumer

    def __eq__(self, o):
        return isinstance(o, Shortcut) and (self.keys, self.consumer) == (o.keys, o.consumer)

    def __hash__(self):
        return hash((self.keys, self.consumer))

    def combo(self):
        if self.consumer is not None:
            return CONSUMER_NAME.get(self.consumer, f'0x{self.consumer:03x}')
        return '+'.join(KEY_NAME.get(k, f'0x{k:02x}') for k in self.keys)

    def label(self):
        entry = CATALOG_BY_SC.get(self)
        if entry:
            return f'{entry_name(entry)} ({self.combo()})'
        return f'{i18n.T("custom_sc")}: {self.combo()}'


def keys(*names):
    table = dict(KEYS)
    table.update({n: v for n, v in MODS})
    return Shortcut([table[n] for n in names])


# ---------------------------------------------------------------- catalog (KDE Plasma defaults)
# (id, group, Turkish name, English name, shortcut)
CATALOG = [
    ('lock', 'sys', 'Kilitle', 'Lock screen', keys('Win', 'L')),
    ('overview', 'sys', 'Pencere görünümü', 'Window overview', keys('Win', 'W')),
    ('launcher', 'sys', 'Uygulama menüsü', 'App launcher', keys('Win')),
    ('krunner', 'sys', 'Arama (KRunner)', 'Search (KRunner)', keys('Alt', 'Space')),
    ('files', 'sys', 'Dosya yöneticisi', 'File manager', keys('Win', 'E')),
    ('alttab', 'sys', 'Pencere değiştir', 'Switch window', keys('Alt', 'Tab')),
    ('close', 'sys', 'Pencereyi kapat', 'Close window', keys('Alt', 'F4')),
    ('shot', 'sys', 'Ekran görüntüsü', 'Screenshot', keys('Print')),
    ('region', 'sys', 'Bölge görüntüsü', 'Region screenshot', keys('Win', 'Shift', 'S')),
    ('clip', 'sys', 'Pano geçmişi', 'Clipboard history', keys('Win', 'V')),
    ('deskl', 'sys', 'Önceki sanal masaüstü', 'Previous desktop', keys('Ctrl', 'Win', '←')),
    ('deskr', 'sys', 'Sonraki sanal masaüstü', 'Next desktop', keys('Ctrl', 'Win', '→')),
    ('copy', 'edit', 'Kopyala', 'Copy', keys('Ctrl', 'C')),
    ('cut', 'edit', 'Kes', 'Cut', keys('Ctrl', 'X')),
    ('paste', 'edit', 'Yapıştır', 'Paste', keys('Ctrl', 'V')),
    ('undo', 'edit', 'Geri al', 'Undo', keys('Ctrl', 'Z')),
    ('redo', 'edit', 'Yinele', 'Redo', keys('Ctrl', 'Shift', 'Z')),
    ('all', 'edit', 'Tümünü seç', 'Select all', keys('Ctrl', 'A')),
    ('save', 'edit', 'Kaydet', 'Save', keys('Ctrl', 'S')),
    ('find', 'edit', 'Bul', 'Find', keys('Ctrl', 'F')),
    ('enter', 'edit', 'Enter', 'Enter', keys('Enter')),
    ('esc', 'edit', 'Esc', 'Esc', keys('Esc')),
    ('del', 'edit', 'Sil', 'Delete', keys('Delete')),
    ('bback', 'web', 'Sayfa geri', 'Page back', keys('Alt', '←')),
    ('bfwd', 'web', 'Sayfa ileri', 'Page forward', keys('Alt', '→')),
    ('reload', 'web', 'Yenile', 'Reload', keys('F5')),
    ('newtab', 'web', 'Yeni sekme', 'New tab', keys('Ctrl', 'T')),
    ('closetab', 'web', 'Sekmeyi kapat', 'Close tab', keys('Ctrl', 'W')),
    ('reopen', 'web', 'Kapanan sekmeyi aç', 'Reopen closed tab', keys('Ctrl', 'Shift', 'T')),
    ('nexttab', 'web', 'Sonraki sekme', 'Next tab', keys('Ctrl', 'Tab')),
    ('prevtab', 'web', 'Önceki sekme', 'Previous tab', keys('Ctrl', 'Shift', 'Tab')),
    ('zin', 'web', 'Yakınlaştır', 'Zoom in', keys('Ctrl', '=')),
    ('zout', 'web', 'Uzaklaştır', 'Zoom out', keys('Ctrl', '-')),
    ('z0', 'web', 'Yakınlaştırmayı sıfırla', 'Reset zoom', keys('Ctrl', '0')),
    ('full', 'web', 'Tam ekran', 'Full screen', keys('F11')),
    ('volup', 'media', 'Sesi aç', 'Volume up', keys('Vol+')),
    ('voldn', 'media', 'Sesi kıs', 'Volume down', keys('Vol−')),
    ('mute', 'media', 'Sessiz', 'Mute', keys('Mute')),
    ('play', 'media', 'Oynat / duraklat ⚗', 'Play / pause ⚗', Shortcut(consumer=0xcd)),
    ('next', 'media', 'Sonraki parça ⚗', 'Next track ⚗', Shortcut(consumer=0xb5)),
    ('prev', 'media', 'Önceki parça ⚗', 'Previous track ⚗', Shortcut(consumer=0xb6)),
    ('calc', 'media', 'Hesap makinesi ⚗', 'Calculator ⚗', Shortcut(consumer=0x192)),
]
GROUPS = ['sys', 'edit', 'web', 'media']
CATALOG_BY_SC = {e[4]: e for e in CATALOG}


def entry_name(e):
    return e[2] if i18n.LANG == 'tr' else e[3]


# ---------------------------------------------------------------- flash format
MACRO_CODE, MEDIA_CODE = 0x2d, 0x2f
MACRO_KINDS = (0x0d, 0x0e, 0x1e, 0x1f)
DESC_BASE, DESC_LEN = 0xa0, 10
SC_AREA, SC_SLOT = 0xe00, 0x20          # this tool's own macro area (32 bytes per slot)
PRESS_DELAY, RELEASE_DELAY = 20, 20     # ms; <= 127 so no extra delay entries are needed


def desc_addr(slot, profile=0):
    return DESC_BASE + DESC_LEN * (profile * 14 + slot)


def body_addr(slot):
    return SC_AREA + SC_SLOT * slot


def encode(sc, slot):
    """Returns (body bytes or None, 10-byte descriptor, key byte)."""
    if sc.consumer is not None:
        desc = bytes([0x00, 0x00, 0xff, sc.consumer & 0xff, sc.consumer >> 8, 0, 0, 0, 1, 0])
        return None, desc, MEDIA_CODE
    events = [(0x80 | PRESS_DELAY, k) for k in sc.keys] + [(RELEASE_DELAY, k) for k in reversed(sc.keys)]
    body = bytearray([0x01, 0x00])                     # repeat once
    for a, b in events:
        body += bytes([a, b])
    if len(body) > SC_SLOT:
        raise ValueError('shortcut too long')
    body += bytes(SC_SLOT - len(body))                  # zero the rest of the slot
    addr = body_addr(slot)
    desc = bytes([0x00, len(events) & 0x7f, 0xff, 0, 0, addr & 0xff, (addr >> 8) & 0x3f, 0, 1, 0])
    return bytes(body), desc, MACRO_CODE


def parse_desc(desc):
    return {'count': (desc[1] & 0x7f) | (desc[7] & 0x3f) << 7, 'consumer': desc[3] | desc[4] << 8,
            'addr': desc[5] | (desc[6] & 0x3f) << 8}


def decode_body(body, count):
    """Extract the pressed keys (in order) from a macro body, skipping pure delay entries."""
    pressed, i, n = [], 2, 0
    while n < count + 64 and i + 1 < len(body):
        a, k = body[i], body[i + 1]
        i += 2
        if k == 0:
            continue
        n += 1
        if a & 0x80 and k not in pressed:
            pressed.append(k)
        if n >= count:
            break
    return Shortcut(pressed)
