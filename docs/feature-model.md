# Feature and data model

This document separates feature evidence from protocol mapping. A feature appearing in the Windows UI does not yet mean its HID packet is known.

## Feature confidence table

| Feature | Evidence | Status |
|---|---|---|
| Button assignment | Official page, UI assets, INI fields | Confirmed application feature; packet mapping pending |
| DPI stages | Official page, INI fields, strings | Confirmed application feature; packet mapping pending |
| DPI-stage colours | `DPI*_R/G/B` fields | Confirmed application feature; persistence pending |
| Polling rate | `USB_SPEED` fields, four UI controls, A825 datasheet | A825 family values known; Blaze encoding pending |
| Lighting modes | Official page and 16 named modes | Confirmed application feature; packet mapping pending |
| Brightness and animation speed | INI fields and UI | Confirmed application feature; packet mapping pending |
| Four selectable profiles | `ConfigNum=4`, UI labels | Confirmed application feature; onboard persistence pending |
| Macros | Macro editor, data files, strings | Confirmed application feature; encoding/persistence pending |
| Rapid fire | Button function and `FIRE_TIME` | Confirmed application feature; packet mapping pending |
| Mouse sensitivity | `DPI_SPEED` and slider | Confirmed application feature; OS-vs-device behavior pending |
| Wheel speed | `WHEEL_SPEED` and slider | Confirmed application feature; OS-vs-device behavior pending |
| PUBG/gun profiles | Data files, UI assets, strings | Confirmed application feature; exact behavior pending |
| Firmware update | Only broad wording on support page | Unconfirmed; no firmware file in payload |

## Profile configuration

The product configuration begins with:

```ini
[Init]
VER_SEL=1
CurConfig=0
ConfigNum=4
ConfigName1_EN=Office
ConfigName2_EN=Game I
ConfigName3_EN=Game II
ConfigName4_EN=Game III
```

The English UI skin separately labels four profile controls as Office, Game I, Game II, and Media. The mismatch between `Game III` in the product config and `Media` in the skin must be preserved as an observed vendor inconsistency until device behavior identifies the intended fourth profile.

The INI contains sections `Config0` through `Config4` despite declaring four configurations. `Config4` may be a shared/default block, but that is not yet proven.

## Product and key count

```ini
[PRODUCTNAME]
PRODUCTNAME_CN=EvoFox Blaze Gaming Mouse
PRODUCTNAME_EN=EvoFox Blaze Gaming Mouse

[KEYNUM]
KeyNum=8
```

The hardware-position map in the vendor file is:

```ini
K1_MAP=1   # S0_R0
K2_MAP=3   # S0_R1
K3_MAP=2   # S0_R2
K4_MAP=5   # S1_R1
K5_MAP=4   # S1_R0
K6_MAP=8   # S2_R1
K7_MAP=6   # S1_R2
K8_MAP=9   # S2_R0
K9_MAP=9   # S2_R2
```

The file declares eight keys but contains a ninth mapping entry. This may be a shared template artifact or a hidden/duplicate position. Do not expose a ninth button without physical confirmation.

Vendor-provided initialization comments associate positions with:

```text
K1: Left click
K2: Middle click
K3: Right click
K4: Forward
K5: Back
K6: DPI+
K7: DPI-
K8: Fire
K9: LED switch
```

The literal initialization values next to those comments are:

```ini
K1_INIT_VAL=1
K2_INIT_VAL=1
K3_INIT_VAL=1
K4_INIT_VAL=1
K5_INIT_VAL=1
K6_INIT_VAL=16
K7_INIT_VAL=17
K8_INIT_VAL=14
K9_INIT_VAL=19
```

The first five values are duplicated even though their comments name different buttons, so the comments and numeric values must be treated as separate evidence.

The first profile block also contains these literal internal key values:

```ini
K0=1
K1=3
K2=2
K3=5
K4=4
K5=6
K6=15
K7=14
K8=14
K9=1
K10=1
K11=0
```

Their relationship to UI action IDs is not yet fully mapped.

## Button-function labels

Confirmed labels in the English UI include:

```text
DPI Loop
Profiles Selection
Rapid Fire
DPI +
DPI -
```

The macro editor additionally knows left, middle, and right click; X/Y movement; DPI changes; LED changes; delays; key press; and key release.

## DPI

The UI exposes six enabled/disabled DPI-stage controls and six colour indicators. The configuration uses:

```text
DPI_LEVEL
DPI_SET0 ... DPI_SET5
DPI_SET_EN0 ... DPI_SET_EN5
DPI0_R/G/B ... DPI5_R/G/B
```

The binary contains these display strings:

```text
200, 400, 600, 800, 1000, 1200,
1600, 1600, 2000, 2000, 2400, 2400,
3200, 4000, 4800, 800, Error
```

Duplicates likely arise from more than one internal mapping table. No direct index-to-DPI formula has been confirmed. Do not assume that `DPI_SETn` stores literal DPI.

The official A825 reference configuration contains a 23-entry table from 200 through 12,800 CPI and explicit encoded values. This likely explains the EvoFox indexes, but the two configuration formats are not identical. Use the table as a candidate decoder and confirm every value through Blaze readback before making it authoritative. See [Related hardware research](related-hardware-research.md).

An observed default/shared block contains:

```ini
DPI_LEVEL=1
DPI_SET0=2
DPI_SET1=5
DPI_SET2=10
DPI_SET3=13
DPI_SET4=16
DPI_SET5=22
```

All six stages are enabled in that block, with four-bit-looking colour channel values from 0 through 15.

## Lighting

Configuration field names include:

```text
LED_TYPE
LED_TYPE_SW_EN0 ... LED_TYPE_SW_EN9
LED_CYC_TIME
LED_CYCTIME
LED_USER_COLER_EN
LED_FEATURE_SCOLOR
LED_FEATURE_DIREC
LED_FEATURE_SYMMETRY
LED_BRIGHT
MODE_LIGHT
BOOT_LED
LED_REACT_EN0 ...
LED_REACT_TYPE0 ...
LED_USER0_R/G/B ...
```

`COLER` and the two cycle-time spellings are literal vendor spellings and should be preserved when parsing files.

The English language file names 16 modes:

1. DPI Breathing Effect
2. Cycle Breathing Effect
3. Light On
4. Flowing Water Effect
5. Mono Water Effect
6. Comet Streak
7. Neon
8. Ambilight
9. Flicker
10. Star Trek
11. Ripple
12. Enraptured
13. Button Response
14. LED Off
15. Single Breath
16. Cycle Color

The relationship between this one-based UI list and the on-wire lighting values is unknown.

The official generic A825 configuration enables fourteen entries numbered 0–13, and the `30fa:1440` GM320 report also says fourteen modes. Those numbers do not cleanly match the Blaze application's sixteen labels. The chip datasheet itself groups lighting into three families and says up to ten effects. Treat these as different layers—chip effects, OEM-enabled modes, and UI entries—not interchangeable counts. The source comparison is in [Related hardware research](related-hardware-research.md).

## Advanced settings

The advanced UI exposes:

- Mouse sensitivity through `DPI_SPEED`.
- Scroll speed through `WHEEL_SPEED`.
- Double-click/rapid-fire timing through `FIRE_TIME`, with UI text mentioning a maximum of 300 ms.
- Polling rate through `USB_SPEED`, with four choices.

A common default block contains:

```ini
DPI_SPEED=5
WHEEL_SPEED=2
USB_SPEED=2
FIRE_TIME=50
```

The official A825 datasheet identifies the four family-level rates as 125, 250, 500, and 1000 Hz. The Blaze application's index-to-rate mapping and on-wire encoding are still unproven. These four values may be offered only after the physical device confirms it belongs to this family and readback establishes the index order.

## Other observed configuration keys

The parser/binary also references:

```text
WHEEL_STATUS
LEFT_MAC...
MAC_COR...
CYC_7COL_EN
CFG_LED
LED_DATA
HIDE
DISPLAY
fontFlag
RT_FONT
```

`LEFT_MAC` and `MAC_COR` appear repeatedly with numeric suffixes across profile/button slots. They are likely macro-assignment and correction/coordinate fields, but their semantics have not been confirmed. `HIDE`, `DISPLAY`, and font fields appear to control application presentation rather than hardware.

## Macros

Macro-related evidence includes:

- `macroNum`, `Macros`, `MacrosSet`, `Macro`, `MacMd5`, and `DAT_VER` fields.
- `SOFT_HARD_MAC`, whose exact meaning is unknown.
- Large fixed-width decimal digit strings in `.dat` files.
- Macro group import, export, rename, reset, and encrypted export UI actions.
- Insert-before, insert-after, X/Y movement, DPI, LED, and delay operations.
- Press-down and release event types.
- A UI warning that only 12 macro groups can be saved.

The macro encoding has not been decoded. The presence of an MD5-named field does not establish how integrity is calculated or whether it is sent to the device.

## PUBG/gun data

The package includes English and Chinese PUBG data, a separate English `PUBG.dat`, 11 gun images, and a UI label for converting a key to a macro. This may implement recoil-control sequences. It should be treated as an optional late milestone after ordinary onboard button and profile support.
