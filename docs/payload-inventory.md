# Payload inventory

This is the recovered installer manifest, grouped to keep the handoff readable. The extracted files were deleted after analysis; this document is the retained inventory.

## Executable and root data

```text
app/Gaming Mouse 3.0.exe                 approximately 2.92 MiB
app/constMacro.dat                       approximately 43.7 KiB
```

## Main skin assets

The following files are JPEG or PNG UI assets beneath `app/skins/`:

```text
advanced_down.jpg
advanced_normal.jpg
advanced_over.jpg
color_down.jpg
color_mask.jpg
color_normal.jpg
color_over.jpg
combinationKey_down.jpg
combinationKey_normal.jpg
combinationKey_over.jpg
gun_down.jpg
gun_mask.jpg
gun_normal.jpg
gun_over.jpg
keyset_down.jpg
keyset_mask.jpg
keyset_normal.jpg
keyset_over.jpg
led-menu.jpg
led_down.jpg
led_menu_down.jpg
led_menu_mask.jpg
led_menu_normal.jpg
led_menu_over.jpg
led_normal.jpg
led_null.jpg
led_over.jpg
Macro_menu_down.jpg
Macro_menu_mask.jpg
Macro_menu_normal.jpg
Macro_menu_over.jpg
mac_down.jpg
mac_normal.jpg
mac_over.jpg
main_down.jpg
main_mask.jpg
main_normal.jpg
main_over.jpg
menu1_down.jpg
menu1_mask.jpg
menu1_normal.jpg
menu1_over.jpg
menu2_down.jpg
menu2_mask.jpg
menu2_normal.jpg
menu2_over.jpg
menu_down.jpg
menu_mask.jpg
menu_normal.jpg
menu_over.jpg
more_down.jpg
more_mask.jpg
more_normal.jpg
more_over.jpg
moveRect.png
Profile_down.jpg
Profile_mask.jpg
Profile_normal.jpg
Profile_over.jpg
sound_down.jpg
sound_mask.jpg
sound_normal.jpg
sound_null.jpg
sound_over.jpg
warning_down.jpg
warning_mask.jpg
warning_normal.jpg
warning_over.jpg
```

These assets reveal the Windows UI organization: main button assignments, advanced settings, lighting, colour selection, macro editing, sound, warning dialogs, profile selection, and a gun/PUBG feature.

## English skin/configuration directory

Files under `app/skins/1_INI_EN/`:

```text
LanguageText.ini
LBWarning.ini
PUBG.dat
skin_advance.ini
skin_color.ini
skin_gun.ini
skin_keyset.ini
skin_mac.ini
skin_main.ini
skin_selcolor.ini
skin_shortcut.ini
skin_sound.ini
ver_normal.jpg
ver_over.jpg
zhi.png
macro/.dat
macro/macroGrp.ini
macroReset/macroGrp.ini
```

Only the English directory was included in this installer despite the binary containing path strings for many other locale directories.

## Product configuration directory

Files under `app/skins/config/`:

```text
config.ini
configReset.ini
constMacro.dat
PUBG_CN.dat
PUBG_EN.dat
font/Cairo-Regular.ttf
font/Manrope-Regular.ttf
font/Roboto-Regular-14.ttf
font/Roboto-Regular.ttf
```

Approximate font sizes reported by the extractor were 135 KiB, 90.2 KiB, 154 KiB, and 154 KiB respectively.

## Gun/PUBG artwork

`app/skins/Gun/` contains `1.jpg` through `11.jpg`. Together with `PUBG.dat`, `PUBG_CN.dat`, `PUBG_EN.dat`, and macro-related strings, this suggests a dedicated game/recoil configuration feature. Its exact relationship to onboard memory remains unknown.

## Macro menu artwork

Files under `app/skins/MacMenu/`:

```text
Insert2th_down.jpg
Insert2th_mask.jpg
Insert2th_normal.jpg
Insert2th_over.jpg
Insert3th_down.jpg
Insert3th_mask.jpg
Insert3th_normal.jpg
Insert3th_over.jpg
Insert_down.jpg
Insert_mask.jpg
Insert_normal.jpg
Insert_over.jpg
MacG_down.jpg
MacG_mask.jpg
MacG_normal.jpg
MacG_over.jpg
MacR_down.jpg
MacR_down2.jpg
MacR_mask.jpg
MacR_mask2.jpg
MacR_normal.jpg
MacR_normal2.jpg
MacR_over.jpg
MacR_over2.jpg
```

## Packaging implications

The installer payload is self-contained and asset-heavy. A Linux port does not need to reproduce the Windows skin system. The valuable artifacts are the protocol behavior, data-field names, feature labels, and default values. Reusing original artwork or fonts in a distributed port may raise licensing questions and should not be assumed permissible.

