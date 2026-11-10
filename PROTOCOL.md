# SMX-R22 (USB 30fa:1040) configuration protocol

Reverse engineered for interoperability from the vendor's Windows configuration software
(`SMX-R22.[20220517].exe`, an InstallShield package containing `smx_r22.exe`, MFC, 32-bit) and
verified against a real mouse. Addresses in brackets refer to that executable
(ImageBase 0x400000). A 2025 build of the same software exists but targets PIDs 0x1440/0x1e01,
not 0x1040.

## USB interfaces

| hidraw interface | Reports |
|---|---|
| 0 | Report 1, mouse: `01 buttons xlo xhi ylo yhi wheel` (bit0 left, 1 right, 2 middle, 3 back, 4 forward) |
| 1 | Report 3 keyboard `03 mods k1..k6` · Report 2 consumer `02 lo hi` · Report 8 system control · **Report 6 vendor input** (2 bytes) · **Feature report 7 vendor** (7 bytes, usage page 0xFF01) |

All configuration goes through feature report 7 (`HidD_SetFeature` / `HidD_GetFeature`),
8 bytes including the report ID:

```
07 <cmd> <p0> <p1> <p2> <p3> <p4> <p5>
```

## Vendor input report 6

`06 <0xf0 + button> <state>`; button is the 1-based hardware slot. For a DPI function the
state is `0x80 | level` on press and `level` on release (level 0-5). After an event the vendor
software issues a plain GetFeature and takes the active profile from `(buf[6] >> 2) & 3`.

## Command 0x18: flash access

`p0` is a bit field: `commit << 3 | read << 2 | write_buffer << 1 | enable`.
Addresses are byte addresses (`lo = addr & 0xff`, `hi = addr >> 8`), blocks are 8 bytes.

| p0 | Operation | Packet |
|---|---|---|
| 0x03 | write byte to buffer | `07 18 03 <i> <lo> <hi> <data> <n-1>` |
| 0x09 | commit buffer to flash | `07 18 09 00 <lo> <hi> 00 <n-1>` |
| 0x05 | read byte (result in GetFeature `buf[1]`) | `07 18 05 <i> <lo> <hi> 00 <n-1>` |
| 0x00 | end of transaction | `07 18 00 00 <lo> <hi> 00 00` |
| 0x10 | apply / reload settings | `07 18 10 00 00 00 00 00` |

**Read** (0x40e860 + 0x40e760): for each i `03 i … 00 n-1` (data 0), sleep 2 ms; sleep 2 ms;
`00 … lo hi`; for each i `05 i lo hi 00 n-1`, sleep 2 ms, GetFeature → byte; sleep 2 ms;
`00 00 00 00 00 00`.

**Write** (0x40e620): for each i `03 i lo hi data n-1`; sleep 4 ms; `09 00 lo hi 00 n-1`;
sleep 2 ms; `00 00 lo hi 00 00`. After a batch of writes **apply** (0x40ead0):
`10 …`, sleep 5 ms, `00 …`.

The flash is 4 KiB on this mouse (`GetFeature buf[6] & 2` selects 0xff8 vs 0x7f8).

Other commands seen in the software (not needed by smx): 0x09, 0x0a, 0x0b, 0x10, 0x11, 0x12,
0x13 (live LED), 0x14 (live DPI colour), 0x15, 0x16, 0x17, 0x20, 0x61.

## Flash map

| Address | Content |
|---|---|
| 0x00–0x07 | **Header**: `5a (profile<<5 \| 3) a5 PIDlo PIDhi VIDlo VIDhi flags` (`5a 03 a5 40 10 fa 30 10`). Defines the USB identity — never write it. The vendor software only updates byte 0x01 (active profile). |
| 0x08–0x0f | Button key bytes, profile 1, slots 0–7 |
| 0x10 | `[0]` slot 8 key · `[3]` bit i = bit 4 of DPI code i · `[4]` 0x08 · `[5..7]` low nibbles of DPI codes 0–5 (high nibble first) |
| 0x18 | `[0]` 0x18 \| active level · `[1]` enabled-level mask · `[2..3]` rapid-fire interval / 8 (LE) · `[4]` 0x80 \| (led_mode & 7) << 4 \| react << 3 \| speed · `[5]` LED cycle mask · `[6]` 0x07 · `[7]` ? |
| 0x20–0x31 | DPI colours, 6 levels × 3 bytes in R, G, B order, **inverted**: the LED lights 255 − value per channel (verified: `00 ff ff` shows red). Drives the **bottom LED strip** ("Light on", "DPI breathing", coloured part of other effects). The top DPI indicator LED uses colours fixed in the firmware and is not configurable. |
| 0x30[2..3] | Supported LED mode mask (0x3fff); `0x33` bit 7 = bit 3 of the LED mode, bit 6 = 1 |
| 0x38 | `[2]` LED symmetry/direction + ? · `[3..5]` keys of slots 10–12 · `[7]` high nibble = brightness |
| 0x40–0x6f | Button tables of profiles 2–4 (11 bytes each) |
| 0x6e–0x7f | Address table of extra structures stored after the macros (0x410–0x45f on the test mouse) |
| 0xa0–0x2cf | Macro / shortcut descriptors, 4 profiles × 14 slots × 10 bytes |
| 0x400–0xf1f | Macro bodies (vendor software writes them sequentially from 0x400) |
| 0xfa0 | Unknown table |

### DPI codes (0x411b2a)

| Code | 1–10 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DPI | code × 200 | 2400 | 3200 | 4000 | 4800 | 5600 | 6400 | 7200 | 8000 | 8800 | 9600 | 10400 | 11200 | 12800 |

### Button key byte

`(type << 5) | value`; type is 1 for normal functions, 0x00 means disabled.

| Value | Function | Value | Function |
|---|---|---|---|
| 0x01 | Left click | 0x0b | DPI + |
| 0x02 | Middle click | 0x0c | DPI − |
| 0x03 | Right click | 0x0d / 0x0e | Keyboard shortcut / macro |
| 0x04 | Back | 0x0f | Media key (consumer usage) |
| 0x05 | Forward | 0x14 | Fn |
| 0x06 | DPI loop | 0x15 | LED mode loop |
| 0x07 | Show desktop | 0x17–0x1a | Profile 1–4 |
| 0x08 | Double click | 0x1e / 0x1f | Macro (other repeat modes) |
| 0x09 | Rapid fire | | |

Physical buttons (KeyNum = 7): slots 0 left, 1 wheel, 2 right, 3 rear side, 4 front side,
5 top (DPI), 7 extra. Factory: `21 22 23 24 25 26 00 35`.

### LED modes

0 DPI breathing, 1 cycle breathing, 2 light on, 3 flowing water, 4 mono water, 5 comet streak,
6 neon, 7 ambilight, 8 flicker, 9 Star Trek, 10 ripple, 11 enraptured, 12 button response,
13 off.

- modes 0–11: `0x1c = 0x80 | (m & 7) << 4 | speed`, `0x33 bit 7 = m >> 3`
- mode 12: `0x1c = 0x80 | 1 << 4 | 0x08 | speed`
- mode 13: speed field = 7 (mode bits kept)

Speed 0–5 (period 1200 − 200 · speed ms in the software preview).

## Shortcuts, macros and media keys (0x414ee1–0x416941)

**Descriptor** at `0xa0 + 10 · (profile · 14 + slot)`:

```
[0] delay unit - 1 (0 = 1 ms)   [1] event count (low 7 bits)   [2] 0xff
[3..4] consumer usage           [5] body address lo             [6] body address hi & 0x3f (+ mode bits)
[7] count >> 7 (+ flag)         [8] 1                           [9] 0
```

**Body**: `[repeat lo][repeat hi]` followed by 2-byte events
`[delay (7 bits) | 0x80 if press][HID usage]`. Delays above 127 ms continue with extra
`7f 00` entries after the event. Example from the test mouse (Win+L at 0x400, descriptor
`00 04 ff 00 00 00 04 00 01 00`):

```
01 00  e9 e3  81 0f  7f 00  1d 0f  14 e3
       ▲Win↓  ▲L↓    delay  L↑     Win↑
```

Media keys use key byte `0x2f` and the consumer usage in descriptor `[3..4]`
(0x223 browser, 0x183 media player, 0x18a mail, 0xe9/0xea volume, 0xb6/0xb5 prev/next,
0xe2 mute, 0xcd play/pause, 0x192 calculator, 0xb7 stop); descriptor bytes 2 and 8 on this
path are assumed to match the macro path.

smx writes its own shortcut bodies at `0xe00 + 0x20 · slot` (an area the vendor software only
reaches with very large macro sets) in the order body → descriptor → key byte.

## Vendor software notes

- `DPI_SPEED` / `WHEEL_SPEED` are Windows pointer/wheel settings (`SystemParametersInfo`), not
  mouse settings.
- `USB_SPEED` (polling rate) is forced to 0 on load and never sent; the UI element is commented
  out in `skin_advance.ini`. Polling rate is not configurable on this model.
