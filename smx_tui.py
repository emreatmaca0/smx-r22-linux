#!/usr/bin/env python3
"""SMX-R22 visual terminal interface — one list, arrow keys + Enter, changes apply instantly."""
import colorsys, curses, locale, math, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import smx
import smx_i18n as i18n
import smx_keys as K
from smx_i18n import T
from smx import (BUTTON_SLOTS, CODE_BY_DPI, DPI_VALUES, FACTORY_KEYS, FIRE_RANGE, FUNC_CODES,
                 LED_BRIGHTS, LED_COUNT, LED_OFF, LED_REACT, LED_SPEEDS, button_name, func_name,
                 led_mode_name)

DEBOUNCE = 0.3          # wait after the last change before writing to the mouse (s)
POLL_INTERVAL = 1.5     # re-read the active DPI level from flash this often (s)
MIN_W, MIN_H = 64, 20
PRESETS = [(255, 0, 0), (255, 143, 0), (255, 220, 0), (0, 255, 64), (0, 255, 255),
           (0, 16, 255), (160, 0, 255), (255, 0, 191), (255, 255, 255)]

# ---------------------------------------------------------------- mouse drawing (top view)
ART = [
    '    ╭──────┬──────╮',
    '   ╱       │       ╲',
    '  │    1   │   2    │',
    '  │        │        │',
    '  │      ╭─┴─╮      │',
    '  │      │ 3 │      │',
    '  │      ╰─┬─╯      │',
    '  │       [6]       │',
    '▐5│       (7)       │',
    '▐4│                 │',
    '  │   ▄▄▄▄▄▄▄▄▄▄▄   │',
    '  │                 │',
    '   ╲     S M X     ╱',
    '    ╲             ╱',
    '     ╰───────────╯',
]
ART_W = max(len(l) for l in ART)
# button number -> cells to paint (row, first column, last column)
REGIONS = {1: [(2, 3, 10), (3, 3, 10)], 2: [(2, 12, 19), (3, 12, 19)], 3: [(4, 9, 13), (5, 9, 13), (6, 9, 13)],
           6: [(7, 10, 12)], 7: [(8, 10, 12)], 5: [(8, 0, 1)], 4: [(9, 0, 1)]}
LED_ROW, LED_COLS = 10, range(6, 17)
SLOT_OF_BUTTON = {n: s for n, s in enumerate(BUTTON_SLOTS, 1)}     # drawing number -> flash slot
MOUSE_BIT = {0x21: 1, 0x23: 2, 0x22: 4, 0x24: 8, 0x25: 16}        # function -> report 1 button bit
DPI_FUNCS = (0x26, 0x2b, 0x2c)
LED_LOOP = 0x35


def clamp(v, rng):
    return max(rng[0], min(rng[-1], v))


def hsv(h, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, 1.0, v)
    return int(r * 255), int(g * 255), int(b * 255)


def scale(rgb, f):
    return tuple(int(c * max(0.0, min(1.0, f))) for c in rgb)


class Item:
    def __init__(self, label, value, left=None, right=None, enter=None, help='', swatch=None,
                 dim=False, button=None, warn=False, hint=''):
        self.label, self.value, self.left, self.right, self.enter = label, value, left, right, enter
        self.help, self.swatch, self.dim, self.button, self.warn, self.hint = help, swatch, dim, button, warn, hint


class UI:
    def __init__(self, scr, sess, first_run):
        self.s, self.sess, self.demo = scr, sess, sess.t.demo
        self.cache = sess.snapshot()                     # last known device state
        self.start = self.cache.copy()                   # state at startup (for undo)
        self.edit = self.cache.copy()                    # state shown on screen / requested
        self.sc = sess.read_shortcuts(self.cache)        # slot -> Shortcut
        self.start_sc = dict(self.sc)
        self.pending, self.last_change = set(), 0.0
        self.next_poll = time.time() + POLL_INTERVAL
        self.sel, self.top = 1, 0
        self.status, self.status_kind = T('st_live'), 'dim'
        self.event = ''
        self.mouse_btn, self.flash, self.wheel = 0, {}, (0, 0.0)
        self.backup_path = None
        if not self.demo:
            try:
                self.backup_path = sess.backup(snap=sess.snap)
                self.say(T('st_backup', f=os.path.basename(self.backup_path)), 'dim')
            except IOError as e:
                self.backup_path = False                 # never write without a backup
                self.say(str(e), 'err')
        else:
            self.say(T('st_demo'), 'warn')
        prof = (sess.snap[1] >> 5) & 3
        if prof:
            self.say(T('profile_warn', n=prof + 1), 'warn')
        if first_run:
            self.say(T('lang_detected', lang=i18n.LANGS[i18n.LANG]), 'accent')
        self._colors()

    # ------------------------------------------------------------ colours
    def _colors(self):
        curses.start_color()
        try:
            curses.use_default_colors(); self.bg = -1
        except curses.error:
            self.bg = curses.COLOR_BLACK
        defs = [('title', curses.COLOR_BLACK, curses.COLOR_CYAN), ('accent', curses.COLOR_CYAN, self.bg),
                ('ok', curses.COLOR_GREEN, self.bg), ('warn', curses.COLOR_YELLOW, self.bg),
                ('err', curses.COLOR_RED, self.bg), ('dim', 8 if curses.COLORS > 8 else curses.COLOR_WHITE, self.bg),
                ('sel', curses.COLOR_BLACK, curses.COLOR_CYAN), ('head', curses.COLOR_YELLOW, self.bg),
                ('press', curses.COLOR_BLACK, curses.COLOR_GREEN)]
        self.C = {}
        for i, (n, fg, b) in enumerate(defs, 1):
            curses.init_pair(i, fg, b)
            self.C[n] = curses.color_pair(i)
        self.npair, self.pairs, self.c256 = len(defs) + 1, {}, curses.COLORS >= 256

    def _idx(self, rgb):
        if self.c256:
            return 16 + 36 * round(rgb[0] / 51) + 6 * round(rgb[1] / 51) + round(rgb[2] / 51)
        return (rgb[0] > 127) | (rgb[1] > 127) << 1 | (rgb[2] > 127) << 2

    def _pair(self, fg, bg):
        key = (fg, bg)
        if key not in self.pairs and self.npair < curses.COLOR_PAIRS:
            curses.init_pair(self.npair, fg, bg)
            self.pairs[key] = curses.color_pair(self.npair)
            self.npair += 1
        return self.pairs.get(key, curses.A_REVERSE)

    def swatch_attr(self, rgb):
        return self._pair(curses.COLOR_BLACK, self._idx(rgb))

    def fg_attr(self, rgb):
        return self._pair(self._idx(rgb), self.bg)

    # ------------------------------------------------------------ helpers
    def put(self, y, x, text, attr=0):
        h, w = self.s.getmaxyx()
        if 0 <= y < h and 0 <= x < w - 1:
            try:
                self.s.addnstr(y, x, text, w - 1 - x, attr)
            except curses.error:
                pass

    def box(self, y, x, h, w, title='', clear=False):
        a = self.C['accent']
        self.put(y, x, '╭' + '─' * (w - 2) + '╮', a)
        for i in range(1, h - 1):
            self.put(y + i, x, '│', a)
            if clear:
                self.put(y + i, x + 1, ' ' * (w - 2))
            self.put(y + i, x + w - 1, '│', a)
        self.put(y + h - 1, x, '╰' + '─' * (w - 2) + '╯', a)
        if title:
            self.put(y, x + 2, f' {title} ', a | curses.A_BOLD)

    def say(self, text, kind='ok'):
        self.status, self.status_kind = text, kind

    def key_label(self, slot):
        sc = self.sc.get(slot)
        code = self.edit.get(f'key{slot}')
        if sc is not None and code & 0x1f in K.MACRO_KINDS + (0x0f,):
            return sc.label(), True
        return func_name(code), code in FUNC_CODES

    # ------------------------------------------------------------ live writes and sync
    def change(self, field, value):
        """Change a setting (rejected if invalid); written to the mouse after DEBOUNCE."""
        trial = self.edit.copy()
        trial.set(field, value)
        bad = trial.problems()
        if bad:
            self.say(bad[0], 'err')
            return False
        self.edit = trial
        self.pending.add(field)
        self.last_change = time.time()
        return True

    def tick(self):
        """Process input reports, write pending changes once the user pauses, and poll
        the active DPI level so changes made on the mouse itself always show up."""
        now = time.time()
        for ev in self.sess.t.events():
            self.on_input(ev, now)
        if self.pending and now - self.last_change >= DEBOUNCE:
            self.flush()
        elif not self.pending and now >= self.next_poll:
            self.poll_active()

    def set_active(self, lv):
        if lv == self.cache.get('dpi_active') and lv == self.edit.get('dpi_active'):
            return
        self.cache.set('dpi_active', lv)
        if 'dpi_active' not in self.pending:
            self.edit.set('dpi_active', lv)
        self.event = T('ev_dpi', n=lv + 1, dpi=self.cache.dpi(lv))

    def poll_active(self):
        self.next_poll = time.time() + POLL_INTERVAL
        try:
            self.set_active(self.sess.read_active())
        except OSError:
            pass

    def on_input(self, ev, now):
        if not ev:
            return
        rid = ev[0]
        if rid == 1 and len(ev) >= 2:                                   # pointer buttons / wheel
            newly = ev[1] & 0x1f & ~self.mouse_btn
            self.mouse_btn = ev[1] & 0x1f
            for s in BUTTON_SLOTS:
                if MOUSE_BIT.get(self.edit.get(f'key{s}'), 0) & newly:
                    self.flash[s] = now
            if len(ev) >= 7 and ev[6]:
                self.wheel = (1 if ev[6] < 0x80 else -1, now)
        elif rid == 6 and len(ev) >= 3 and ev[1] >= 0xf0:              # vendor event: 0xf0 + button
            slot = ev[1] - 0xf1                                         # 1-based hardware slot
            func = self.edit.get(f'key{slot}') if 0 <= slot < 9 else None
            if ev[2] & 0x80:
                if slot in BUTTON_SLOTS:
                    self.flash[slot] = now
                if func in DPI_FUNCS:
                    self.set_active(ev[2] & 7)
            self.next_poll = now + 0.15                                 # confirm from flash
        elif rid == 3 and len(ev) >= 3:                                 # keyboard report (shortcuts)
            held = {0xe0 + i for i in range(8) if ev[1] >> i & 1} | {k for k in ev[2:8] if k}
            if held:
                for s, sc in self.sc.items():
                    if sc.keys and set(sc.keys) <= held:
                        self.flash[s] = now
        elif rid == 2 and len(ev) >= 3:                                 # consumer report (media)
            usage = ev[1] | ev[2] << 8
            for s, sc in self.sc.items():
                if usage and sc.consumer == usage:
                    self.flash[s] = now

    def active(self, slot, now):
        code = self.edit.get(f'key{slot}')
        return bool(self.mouse_btn & MOUSE_BIT.get(code, 0)) or now - self.flash.get(slot, 0) < 0.35

    def flush(self):
        if not self.pending:
            return
        if self.backup_path is False:
            self.edit, self.pending = self.cache.copy(), set()
            return
        self.say(T('st_writing'), 'warn')
        self.draw()
        try:
            _, self.cache = self.sess.live_apply(self.cache, self.edit, self.pending)
            self.say(T('st_done'), 'ok')
        except Exception as e:
            self.say(f'{T("error")}: {e}', 'err')
            try:
                self.cache = self.sess.read_config()
            except Exception:
                pass
        self.edit, self.pending = self.cache.copy(), set()
        self.next_poll = time.time() + POLL_INTERVAL

    def write_shortcut(self, slot, sc):
        if self.backup_path is False:
            return
        self.flush()
        self.say(T('sc_writing'), 'warn')
        self.draw()
        try:
            self.cache = self.sess.set_shortcut(self.cache, slot, sc)
            self.edit = self.cache.copy()
            self.sc[slot] = sc
            self.say(T('sc_written', b=button_name(slot), s=sc.label()), 'ok')
        except Exception as e:
            self.say(f'{T("error")}: {e}', 'err')

    # ------------------------------------------------------------ rows
    def items(self):
        e = self.edit
        rows = [('head', T('sec_dpi'))]
        act, en = e.get('dpi_active'), e.get('dpi_en')
        on_levels = [i for i in range(6) if en >> i & 1]

        def step_active(d):
            j = on_levels.index(act) if act in on_levels else 0
            self.change('dpi_active', on_levels[(j + d) % len(on_levels)])
        rows.append(Item(T('active_level'), f'{act + 1}  ·  {e.dpi(act)} DPI',
                         lambda: step_active(-1), lambda: step_active(1), help=T('h_active')))
        for i in range(6):
            rows.append(self._level_item(i))

        rows.append(('head', T('sec_keys')))
        for n, slot in enumerate(BUTTON_SLOTS, 1):
            rows.append(self._key_item(n, slot))

        rows.append(('head', T('sec_led')))
        mode, speed = e.get('led')
        rows.append(Item(T('mode'), led_mode_name(mode),
                         lambda: self.change('led', ((mode - 1) % LED_COUNT, speed)),
                         lambda: self.change('led', ((mode + 1) % LED_COUNT, speed)),
                         lambda: self.pick(T('mode'), [((m,), led_mode_name(m)) for m in range(LED_COUNT)], (mode,),
                                           lambda v: self.change('led', (v[0], speed))),
                         help=T('h_mode')))
        off = mode == LED_OFF
        rows.append(Item(T('speed'), '—' if off else self.meter(speed, LED_SPEEDS),
                         None if off else lambda: self.change('led', (mode, clamp(speed - 1, LED_SPEEDS))),
                         None if off else lambda: self.change('led', (mode, clamp(speed + 1, LED_SPEEDS))),
                         help=T('h_speed'), dim=off))
        b = e.get('bright')
        rows.append(Item(T('brightness'), self.meter(b, LED_BRIGHTS),
                         lambda: self.change('bright', clamp(b - 1, LED_BRIGHTS)),
                         lambda: self.change('bright', clamp(b + 1, LED_BRIGHTS)), help=T('h_bright')))

        rows.append(('head', T('sec_other')))
        f = e.get('fire')
        rows.append(Item(T('fire'), f'{f} ms', lambda: self.change('fire', clamp(f - 8, FIRE_RANGE)),
                         lambda: self.change('fire', clamp(f + 8, FIRE_RANGE)), help=T('h_fire')))
        langs = list(i18n.LANGS)
        cycle_lang = lambda d: i18n.save(langs[(langs.index(i18n.LANG) + d) % len(langs)])
        rows.append(Item(T('language'), i18n.LANGS[i18n.LANG], lambda: cycle_lang(-1), lambda: cycle_lang(1),
                         help=T('h_lang')))
        maps = smx.COLOR_MAPPINGS
        cur_map = (smx.COLOR_ORDER, smx.COLOR_INVERT)
        cycle_map = lambda d: smx.set_color_mapping(*maps[(maps.index(cur_map) + d) % len(maps)])
        rows.append(Item(T('color_order'), smx.COLOR_ORDER + (f' · {T("inverted")}' if smx.COLOR_INVERT else ''),
                         lambda: cycle_map(-1), lambda: cycle_map(1), help=T('h_color_order')))
        rows.append(Item(T('factory_keys'), '↵', enter=self.factory_keys, help=T('h_factory')))
        rows.append(Item(T('undo_all'), '↵', enter=self.undo_all, help=T('h_undo')))
        return rows

    def _level_item(self, i):
        e = self.edit
        on = e.get('dpi_en') >> i & 1
        cur = e.dpi(i)

        def step(d):
            # Off -> back on at its stored value; below 200 / above 12800 -> Off
            if not on:
                self.change('dpi_en', e.get('dpi_en') | (1 << i))
                return
            j = (DPI_VALUES.index(cur) if cur in DPI_VALUES else 0) + d
            if 0 <= j < len(DPI_VALUES):
                self.change(f'dpi{i}', CODE_BY_DPI[DPI_VALUES[j]])
            else:
                self.change('dpi_en', e.get('dpi_en') & ~(1 << i))
        mark = '▶ ' if i == e.get('dpi_active') else '  '
        return Item(f'{mark}{T("level", n=i + 1)}', f'{cur} DPI' if on else T('off'),
                    lambda: step(-1), lambda: step(1), lambda: self.color_picker(i),
                    help=T('h_level'), swatch=e.get(f'color{i}'), dim=not on, hint=T('color_hint'))

    def _key_item(self, n, slot):
        code = self.edit.get(f'key{slot}')
        label, known = self.key_label(slot)

        def step(d):
            j = FUNC_CODES.index(code) + d if code in FUNC_CODES else 0
            self.assign(slot, ('fn', FUNC_CODES[j % len(FUNC_CODES)]))
        return Item(f'{n}  {button_name(slot)}', label, lambda: step(-1), lambda: step(1),
                    lambda: self.pick_function(slot), help=T('h_key'), button=n, warn=not known)

    @staticmethod
    def meter(v, rng):
        n = rng[-1] - rng[0] + 1
        k = v - rng[0] + 1
        return '■' * k + '□' * (n - k) + f'  {v}'

    # ------------------------------------------------------------ actions
    def assign(self, slot, choice):
        kind = choice[0]
        if kind == 'fn':
            if self.change(f'key{slot}', choice[1]):
                self.sc.pop(slot, None)
        elif kind == 'sc':
            self.write_shortcut(slot, choice[1])
        elif kind == 'custom':
            sc = self.shortcut_builder(slot)
            if sc is not None:
                self.write_shortcut(slot, sc)

    def pick_function(self, slot):
        code = self.edit.get(f'key{slot}')
        cur_sc = self.sc.get(slot) if code & 0x1f in K.MACRO_KINDS + (0x0f,) else None
        opts = [(None, T('grp_basic'))] + [(('fn', c), func_name(c)) for c in FUNC_CODES]
        for g in K.GROUPS:
            opts.append((None, T('grp_' + g)))
            opts += [(('sc', e[4]), f'{K.entry_name(e):<24} {e[4].combo()}') for e in K.CATALOG if e[1] == g]
        opts += [(None, T('grp_custom')), (('custom',), T('custom_new'))]
        current = ('sc', cur_sc) if cur_sc is not None else ('fn', code)
        self.pick(button_name(slot), opts, current, lambda v: self.assign(slot, v), width=46, foot=T('exp_note'))

    def factory_keys(self):
        for s in range(8):
            self.change(f'key{s}', FACTORY_KEYS[s])
        self.sc = {}
        self.flush()
        self.say(T('factory_done'), 'ok')

    def undo_all(self):
        self.edit = self.start.copy()
        self.pending |= {f for f in smx.Config.FIELDS if self.start.get(f) != self.cache.get(f)}
        self.pending.discard('dpi_active')            # the active level follows the mouse
        self.edit.set('dpi_active', self.cache.get('dpi_active'))
        self.flush()
        for slot, sc in self.start_sc.items():        # re-write shortcuts that were replaced
            if self.sc.get(slot) != sc or self.cache.get(f'key{slot}') != self.start.get(f'key{slot}'):
                self.write_shortcut(slot, sc)
        self.sc = dict(self.start_sc)
        self.say(T('undone'), 'ok')

    # ------------------------------------------------------------ LED preview
    def led_colors(self, n, now):
        """Approximate colours of the LED strip for the selected effect."""
        e = self.edit
        mode, speed = e.get('led')
        base = e.get(f'color{e.get("dpi_active")}')
        bright = (e.get('bright') + 1) / (LED_BRIGHTS[-1] + 1)
        period = max(0.25, (1200 - 200 * speed) / 1000) * 3
        ph = (now / period) % 1.0
        breath = 0.15 + 0.85 * (0.5 - 0.5 * math.cos(2 * math.pi * ph))
        if mode == LED_OFF:
            return [None] * n
        if mode == 0:
            cols = [scale(base, breath)] * n
        elif mode == 1:
            cols = [scale(hsv(math.floor(now / period) / 7), breath)] * n
        elif mode == 2:
            cols = [base] * n
        elif mode == 8:
            cols = [base if ph < 0.5 else None] * n
        elif mode == LED_REACT:
            hit = any(self.active(s, now) for s in BUTTON_SLOTS)
            cols = [base if hit else None] * n
        elif mode == 4:
            pos = int(ph * n)
            cols = [base if i == pos else scale(base, 0.15) for i in range(n)]
        elif mode == 5:                                         # comet: DPI-coloured head
            pos = ph * n
            cols = [scale(base, max(0.0, 1 - ((pos - i) % n) / 4)) for i in range(n)]
        else:                                                   # flowing rainbow effects
            cols = [hsv(ph + i / n) for i in range(n)]
        return [scale(c, bright) if c else None for c in cols]

    # ------------------------------------------------------------ drawing
    def draw(self):
        s = self.s
        s.erase()
        h, w = s.getmaxyx()
        if h < MIN_H or w < MIN_W:
            self.put(0, 0, T('err_small', w=w, h=h, mw=MIN_W, mh=MIN_H), self.C['warn'])
            s.refresh()
            return
        now = time.time()
        self.put(0, 0, ' ' * (w - 1), self.C['title'])
        self.put(0, 2, T('title'), self.C['title'] | curses.A_BOLD)
        dev = self.sess.t.path + ('  DEMO' if self.demo else '')
        self.put(0, w - len(dev) - 3, dev, self.C['title'])

        rows = self.items()
        self.rows = rows
        side = w >= 100
        lw = min(66, w - 36) if side else w - 4
        list_h = h - 6
        label_w = max(len(r.label) for r in rows if not isinstance(r, tuple) and (r.left or r.right))
        vx = min(3 + label_w + 4, 2 + lw - 30)
        if self.sel < self.top:
            self.top = self.sel
        if self.sel >= self.top + list_h:
            self.top = self.sel - list_h + 1
        if self.top > 0 and isinstance(rows[self.top - 1], tuple) and self.sel - self.top + 1 < list_h:
            self.top -= 1
        for k, row in enumerate(rows[self.top:self.top + list_h]):
            y, idx = 2 + k, self.top + k
            if isinstance(row, tuple):
                self.put(y, 2, row[1], self.C['head'] | curses.A_BOLD)
                self.put(y, 3 + len(row[1]), '─' * (lw - len(row[1]) - 2), self.C['dim'])
                continue
            selected = idx == self.sel
            base = self.C['sel'] | curses.A_BOLD if selected else (self.C['dim'] if row.dim else 0)
            if selected:
                self.put(y, 2, ' ' * lw, base)
            if not (row.left or row.right):                     # action row: label + ↵
                self.put(y, 3, f'{row.label}  {row.value}'[:lw - 2], base)
                continue
            lit = row.button and self.active(SLOT_OF_BUTTON[row.button], now)
            self.put(y, 3, row.label[:vx - 5], self.C['press'] | curses.A_BOLD if lit else base)
            if row.swatch:
                self.put(y, vx - 4, '  ', self.swatch_attr(row.swatch))
            val = f'◀ {row.value} ▶' if selected else f'  {row.value}'
            if selected and row.hint:
                val += f'   {row.hint}'
            vattr = base if selected else (self.C['warn'] if row.warn else (self.C['dim'] if row.dim else 0))
            self.put(y, vx, val[:2 + lw - vx], vattr)
        if self.top + list_h < len(rows):
            self.put(h - 4, lw - 1, '▼', self.C['dim'])
        if self.top > 0:
            self.put(2, lw - 1, '▲', self.C['dim'])

        cur = rows[self.sel]
        if side:
            self.draw_mouse(2, lw + 4, h, w, cur, now)

        self.put(h - 3, 2, cur.help[:w - 4], self.C['dim'])
        self.put(h - 2, 2, self.status[:w - 4], self.C.get(self.status_kind, 0) | curses.A_BOLD)
        bar = T('help_bar') + ('    d = DPI (demo)' if self.demo else '')
        self.put(h - 1, 0, ' ' * (w - 1), self.C['title'])
        self.put(h - 1, 2, bar, self.C['title'])
        s.refresh()

    def draw_mouse(self, y, x, h, w, cur, now):
        bw = w - x - 2
        bh = len(ART) + 4
        self.box(y, x, bh, bw, T('mouse'))
        ax = x + max(2, (bw - ART_W) // 2)
        ay = y + 2
        for r, line in enumerate(ART):
            self.put(ay + r, ax, line, self.C['accent'])
        # button regions: pressed = green, selected in the list = highlighted
        for n, cells in REGIONS.items():
            slot = SLOT_OF_BUTTON[n]
            pressed, chosen = self.active(slot, now), cur.button == n
            if not (pressed or chosen):
                continue
            attr = self.C['press'] | curses.A_BOLD if pressed else self.C['sel'] | curses.A_BOLD
            for r, c0, c1 in cells:
                self.put(ay + r, ax + c0, ART[r][c0:c1 + 1], attr)
        # LED strip
        for c, rgb in zip(LED_COLS, self.led_colors(len(LED_COLS), now)):
            if rgb is None:
                self.put(ay + LED_ROW, ax + c, '░', self.C['dim'])
            else:
                self.put(ay + LED_ROW, ax + c, '█', self.fg_attr(rgb))
        # wheel
        wd, wt = self.wheel
        if now - wt < 0.3:
            self.put(ay + 5, ax + ART_W + 1, '▲' if wd > 0 else '▼', self.C['ok'] | curses.A_BOLD)
        # below: pressed buttons, preview note, DPI colours
        yy = y + bh
        pressed = [button_name(s) for s in BUTTON_SLOTS if self.active(s, now)]
        if now - wt < 0.3:
            pressed.append(T('wheel_up') if wd > 0 else T('wheel_down'))
        self.put(yy, x + 1, f'{T("pressed")}: {", ".join(pressed) or "—"}'[:bw], self.C['ok'] if pressed else self.C['dim'])
        mode, _ = self.edit.get('led')
        self.put(yy + 1, x + 1, f'LED: {led_mode_name(mode)}  ·  {T("preview")}'[:bw], self.C['dim'])
        e = self.edit
        if yy + 4 < h - 3:
            for i in range(6):
                on = e.get('dpi_en') >> i & 1
                cx = x + 1 + i * 6
                self.put(yy + 3, cx, '▼' if i == e.get('dpi_active') else ' ', self.C['ok'] | curses.A_BOLD)
                self.put(yy + 4, cx, '    ', self.swatch_attr(e.get(f'color{i}')) if on else self.C['dim'])
                if yy + 5 < h - 3:
                    self.put(yy + 5, cx, f'{e.dpi(i) if on else "—"}', 0 if on else self.C['dim'])
        if self.event and yy + 6 < h - 3:
            self.put(yy + 6, x + 1, self.event[:bw], self.C['accent'])

    # ------------------------------------------------------------ dialogs
    def modal_loop(self, render, on_key):
        while True:
            self.tick()
            self.draw()
            render()
            self.s.refresh()
            k = self.s.getch()
            if k == -1:
                continue
            r = on_key(k)
            if r is not None:
                return r

    def pick(self, title, options, current, apply, width=38, foot=''):
        """options: [(value, label)]; value None = group heading (not selectable)."""
        sel = [i for i, (v, _) in enumerate(options) if v is not None]
        st = {'i': next((i for i in sel if options[i][0] == current), sel[0])}

        def render():
            h, w = self.s.getmaxyx()
            bw = min(width, w - 4)
            bh = min(len(options) + 4 + (1 if foot else 0), h - 2)
            by, bx = (h - bh) // 2, (w - bw) // 2
            self.box(by, bx, bh, bw, title, clear=True)
            vis = bh - 4 - (1 if foot else 0)
            top = max(0, min(st['i'] - vis // 2, len(options) - vis))
            for j, (v, label) in enumerate(options[top:top + vis]):
                n = top + j
                if v is None:
                    self.put(by + 2 + j, bx + 2, label, self.C['head'] | curses.A_BOLD)
                else:
                    attr = self.C['sel'] | curses.A_BOLD if n == st['i'] else 0
                    self.put(by + 2 + j, bx + 2, f'  {label:<{bw - 7}}', attr)
            if foot:
                self.put(by + bh - 2, bx + 3, foot[:bw - 6], self.C['dim'])
            self.put(by + bh - 1, bx + 2, f' {T("list_help")} ', self.C['dim'])

        def key(k):
            pos = sel.index(st['i'])
            if k == curses.KEY_UP:
                st['i'] = sel[(pos - 1) % len(sel)]
            elif k == curses.KEY_DOWN:
                st['i'] = sel[(pos + 1) % len(sel)]
            elif k == curses.KEY_PPAGE:
                st['i'] = sel[max(0, pos - 10)]
            elif k == curses.KEY_NPAGE:
                st['i'] = sel[min(len(sel) - 1, pos + 10)]
            elif k in (10, 13, curses.KEY_ENTER):
                apply(options[st['i']][0]); return True
            elif k in (27, ord('q')):
                return False
        self.modal_loop(render, key)

    def shortcut_builder(self, slot):
        sc = self.sc.get(slot)
        held = set(sc.keys) if sc and sc.keys else set()
        main = [k for k in (sc.keys if sc else ()) if k not in K.MOD_NAME]
        key_list = K.KEYS
        st = {'row': 4, 'mods': {m for _, m in K.MODS if m in held},
              'key': next((i for i, (_, v) in enumerate(key_list) if main and v == main[-1]), 0)}
        rows = [n for n, _ in K.MODS] + [T('key')]

        def current():
            mods = [m for _, m in K.MODS if m in st['mods']]
            return K.Shortcut(mods + [key_list[st['key']][1]])

        def render():
            h, w = self.s.getmaxyx()
            bw, bh = 46, 12
            by, bx = (h - bh) // 2, (w - bw) // 2
            self.box(by, bx, bh, bw, T('builder_title', b=button_name(slot)), clear=True)
            self.put(by + 2, bx + 3, current().combo(), self.C['ok'] | curses.A_BOLD)
            for r, name in enumerate(rows):
                yy = by + 4 + r
                attr = self.C['sel'] | curses.A_BOLD if r == st['row'] else 0
                self.put(yy, bx + 3, f' {name:<8}', attr)
                if r < 4:
                    on = K.MODS[r][1] in st['mods']
                    self.put(yy, bx + 14, '[✓]' if on else '[ ]', self.C['ok'] if on else self.C['dim'])
                else:
                    self.put(yy, bx + 14, f'◀ {key_list[st["key"]][0]:^9} ▶', attr)
            self.put(by + bh - 2, bx + 3, T('builder_help'), self.C['dim'])

        def key(k):
            if k == curses.KEY_UP:
                st['row'] = (st['row'] - 1) % len(rows)
            elif k == curses.KEY_DOWN:
                st['row'] = (st['row'] + 1) % len(rows)
            elif k in (curses.KEY_LEFT, curses.KEY_RIGHT, ord(' ')):
                if st['row'] < 4:
                    st['mods'] ^= {K.MODS[st['row']][1]}
                else:
                    st['key'] = (st['key'] + (1 if k != curses.KEY_LEFT else -1)) % len(key_list)
            elif k in (10, 13, curses.KEY_ENTER):
                return current()
            elif k == 27:
                return False
        r = self.modal_loop(render, key)
        return r if isinstance(r, K.Shortcut) else None

    def color_picker(self, level):
        orig = self.edit.get(f'color{level}')
        st = {'row': 0, 'rgb': list(orig), 'preset': 0}
        names = [T('palette'), T('red'), T('green'), T('blue')]
        self.say(T('led_dpi_hint'), 'accent')

        def render():
            h, w = self.s.getmaxyx()
            bw, bh = 52, 12
            by, bx = (h - bh) // 2, (w - bw) // 2
            self.box(by, bx, bh, bw, T('color_title', n=level + 1), clear=True)
            rgb = tuple(st['rgb'])
            self.put(by + 2, bx + 3, ' ' * 8, self.swatch_attr(rgb))
            self.put(by + 2, bx + 13, '#%02x%02x%02x' % rgb, curses.A_BOLD)
            for r in range(4):
                yy = by + 4 + r
                sel = r == st['row']
                self.put(yy, bx + 2, f' {names[r]:<8}', self.C['sel'] | curses.A_BOLD if sel else 0)
                if r == 0:
                    for p, c in enumerate(PRESETS):
                        self.put(yy, bx + 13 + p * 4, '   ', self.swatch_attr(c))
                        if sel and p == st['preset']:
                            self.put(yy, bx + 12 + p * 4, '[', curses.A_BOLD)
                            self.put(yy, bx + 16 + p * 4, ']', curses.A_BOLD)
                else:
                    v = st['rgb'][r - 1]
                    fill = round(v / 255 * 24)
                    self.put(yy, bx + 13, '█' * fill + '░' * (24 - fill), self.C['accent'])
                    self.put(yy, bx + 39, f'{v:>3}')
            self.put(by + bh - 2, bx + 3, T('color_help'), self.C['dim'])

        def key(k):
            if k == curses.KEY_UP:
                st['row'] = (st['row'] - 1) % 4
            elif k == curses.KEY_DOWN:
                st['row'] = (st['row'] + 1) % 4
            elif k in (curses.KEY_LEFT, curses.KEY_RIGHT):
                d = 1 if k == curses.KEY_RIGHT else -1
                if st['row'] == 0:
                    st['preset'] = (st['preset'] + d) % len(PRESETS)
                    st['rgb'] = list(PRESETS[st['preset']])
                else:
                    c = st['row'] - 1
                    st['rgb'][c] = max(0, min(255, st['rgb'][c] + 17 * d))
                self.change(f'color{level}', tuple(st['rgb']))       # live preview on the mouse
            elif k in (10, 13, curses.KEY_ENTER):
                return True
            elif k == 27:
                self.change(f'color{level}', orig)
                return False
        self.modal_loop(render, key)

    # ------------------------------------------------------------ main loop
    def move(self, d):
        n = len(self.rows)
        i = self.sel
        for _ in range(n):
            i = (i + d) % n
            if not isinstance(self.rows[i], tuple):
                self.sel = i
                return

    def loop(self):
        self.s.timeout(80)
        self.rows = self.items()
        while True:
            self.tick()
            self.draw()
            k = self.s.getch()
            if k in (-1, curses.KEY_RESIZE):
                continue
            row = self.rows[self.sel]
            if k in (ord('q'), 27):
                if self.pending:
                    self.say(T('quit_pending'), 'warn'); self.draw(); self.flush()
                return
            if k == curses.KEY_UP:
                self.move(-1)
            elif k == curses.KEY_DOWN:
                self.move(1)
            elif k == curses.KEY_LEFT and row.left:
                row.left()
            elif k == curses.KEY_RIGHT and row.right:
                row.right()
            elif k in (10, 13, curses.KEY_ENTER, ord(' ')) and row.enter:
                row.enter()
            elif self.demo and k == ord('d'):              # demo: DPI button with event
                self.sess.t.press_dpi()
            elif self.demo and k == ord('m'):              # demo: DPI button, event lost
                self.sess.t.press_dpi(report=False)
            elif self.demo and k == ord('b'):              # demo: left click
                self.sess.t.pending += [bytes([1, 1, 0, 0, 0, 0, 0]), bytes([1, 0, 0, 0, 0, 0, 0])]


def run(demo=None, first_run=None):
    locale.setlocale(locale.LC_ALL, '')
    os.environ.setdefault('ESCDELAY', '25')
    first = smx.load_settings() if first_run is None else first_run
    try:
        t = smx.FakeTransport(demo) if demo else smx.HidTransport()
    except smx.DeviceError as e:
        sys.exit(f'{T("error")}: {e}')
    sess = smx.Session(t)
    try:
        def main(scr):
            curses.curs_set(0)
            UI(scr, sess, first).loop()
        curses.wrapper(main)
    finally:
        sess.close()


if __name__ == '__main__':
    run(sys.argv[1] if len(sys.argv) > 1 else None)
