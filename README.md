# smx — SMX-R22 mouse control for Linux

A terminal application to configure the **SMX-R22** gaming mouse (USB ID `30fa:1040`,
reported as "INSTANT USB GAMING MOUSE") on Linux — no Windows software needed.
English and Turkish interface; the language is detected on first run.

[Türkçe README](README.tr.md)

## Features

| | |
|---|---|
| DPI | 6 levels (200–12800), turn levels on/off, active level, per-level colour of the bottom LED strip (the top DPI indicator colours are fixed by the mouse) |
| Buttons | 7 buttons: left/right/middle click, back/forward, DPI loop/±, double click, rapid fire, show desktop, LED loop, disabled |
| Shortcuts | 40+ ready-made shortcuts (lock screen, window overview, screenshot, copy/paste, tab handling, volume…) and a custom shortcut builder |
| Lighting | 14 LED effects, speed, brightness |
| Live | Changes are written to the mouse as you change them; the active DPI level follows the mouse; pressed buttons light up on the drawing |
| Safe | Automatic backup on start, read-back verification, the USB identity header is never written |

Not supported (yet): multi-step macros. Polling rate cannot be changed on this model (the
vendor software does not support it either). Media keys (play/pause, next/previous) are
marked experimental.

## Requirements

Python 3.8+ (standard library only), a terminal with 256 colours, and access to the mouse's
`/dev/hidraw*` nodes.

## Installation

```sh
git clone https://github.com/emreatmaca0/smx-r22-linux.git && cd smx-r22-linux
sudo cp 70-smx-r22.rules /etc/udev/rules.d/ && sudo udevadm control --reload
# re-plug the mouse
ln -sf "$PWD/smx" ~/.local/bin/smx
```

The udev rule gives the logged-in user access to the mouse's hidraw nodes, so no `sudo` is
needed afterwards.

## Usage

Run `smx`. Only four keys are used:

| Key | Action |
|---|---|
| `↑` `↓` | select a setting |
| `←` `→` | change the value — applied to the mouse immediately |
| `Enter` | colour picker / list |
| `q` | quit |

- A DPI level is turned off by moving its value below 200 (or above 12800).
- On a button row, `Enter` opens a grouped list: basic functions, system, editing, browser,
  media and "create custom shortcut".
- On a DPI level row, `Enter` opens the colour picker. If the colours on screen do not match
  the mouse, change *Other › LED colour mapping*.
- The mouse drawing appears when the terminal is at least 100 columns wide.

Command line:

```sh
smx status                 # print the current settings
smx backup                 # save a backup (~/.local/share/smx/backups/)
smx restore FILE           # restore a backup (the header is never written)
smx dpi 5 3200             # set level 5 to 3200 DPI
smx dump 0x00 0x40         # hex dump of the flash (read-only)
smx listen                 # print raw input reports (read-only)
smx tui --demo FILE        # try the interface without a mouse, using a backup file
smx --lang en              # switch the language
```

The shortcut catalog follows KDE Plasma's default key bindings; most entries (copy, paste,
browser shortcuts, Alt+Tab…) work on any desktop.

## Safety

- The flash header `0x00–0x07` (USB VID/PID) is never written — the code refuses it.
- Only decoded blocks are written: settings `0x08–0x3f`, shortcut descriptors `0xa0–0x12b`
  and the tool's own shortcut area `0xe00–0xeff`. Each block is re-read from the mouse right
  before writing, unknown bits are preserved, and every written block is read back.
- At least one button must stay "Left click" and at least one DPI level must stay on.
- Writes happen when you release the arrow key, not on every step, to limit flash wear.

## How it works

The configuration protocol (HID feature report 7, flash access command `0x18`) was reverse
engineered from the vendor's Windows software for interoperability. See
[PROTOCOL.md](PROTOCOL.md) for the full description. Other mice using the same "INSTANT"
controller (`30fa:xxxx`) may use the same protocol; contributions are welcome.

## Disclaimer

This project is not affiliated with the mouse manufacturer. It does not contain any vendor
software. You use it at your own risk; a backup is taken every time the interface starts.

## License

MIT — see [LICENSE](LICENSE).
