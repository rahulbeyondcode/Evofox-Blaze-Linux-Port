# Installer payload and Windows application

## Extraction method

The Inno Setup package was listed and statically extracted with `innoextract` 1.9. Package-installation details are irrelevant to the Linux port; the durable results are the payload inventory, hashes, strings, PE metadata, and disassembly recorded in these documents.

The EvoFox installer and extracted Windows application were never executed.

## Main application

The payload's only executable application is:

```text
app/Gaming Mouse 3.0.exe
```

Confirmed metadata:

| Property | Value |
|---|---|
| Approximate size | 2.92 MiB as reported by `innoextract` |
| SHA-256 | `9eec736ee629ff9d0684f787a270afe86d064fdcf23e7eb11f921dc7844eee55` |
| Format | PE32 GUI executable, Intel 80386 |
| Runtime | Native Windows code; no CLR/.NET header |
| Linker version | 14.16 |
| PE timestamp | 2023-08-01 12:53:24 |
| Sections | `.text`, `.rdata`, `.data`, `.rsrc`, `.reloc` |
| Manifest privilege | `asInvoker` |
| UI access | `false` |
| DPI awareness | enabled |
| Internal application identity | `ACIST_GMouseApp`, `IST_GMouse` |
| Displayed name | `Gaming Mouse 3.0` |
| Internal version string | `IST_GMouse Version 1.0` |

The binary contains MFC class names and is consistent with a native Visual C++/MFC desktop application.

The PE timestamp is a build-header value and can be altered; it is useful for comparing binaries but is not independent proof of a release date.

## PE layout for future disassembly

The preferred image base is `0x00400000`. The section table recovered by GNU `objdump` was:

| Section | Size | Preferred VA | File offset |
|---|---:|---:|---:|
| `.text` | `0x002009a5` | `0x00401000` | `0x00000400` |
| `.rdata` | `0x000688c2` | `0x00602000` | `0x00200e00` |
| `.data` | `0x00005e00` raw data | `0x0066b000` | `0x00269800` |
| `.rsrc` | `0x0004acc0` | `0x006e7000` | `0x0026f600` |
| `.reloc` | `0x0002e200` | `0x00732000` | `0x002ba400` |

Other header values:

```text
AddressOfEntryPoint: 0x001cff8b
SizeOfImage:         0x00361000
Security directory: file offset 0x002e8600, size 0x00002a10
```

The `.data` section has substantial zero-initialized virtual storage beyond its raw bytes. This is where the HID caps, handles, report buffer, and application configuration globals observed in disassembly reside.

## Relevant imports

The application directly imports these HID functions from `HID.DLL`:

```text
HidP_GetCaps
HidD_GetAttributes
HidD_GetHidGuid
HidD_GetPreparsedData
HidD_FreePreparsedData
HidD_GetFeature
HidD_SetFeature
HidD_GetProductString
```

It imports these enumeration functions from `SETUPAPI.dll`:

```text
SetupDiDestroyDeviceInfoList
SetupDiEnumDeviceInterfaces
SetupDiGetDeviceInterfaceDetailW
SetupDiGetClassDevsW
```

Other imported DLLs are ordinary Windows UI/runtime components:

```text
KERNEL32.dll
USER32.dll
GDI32.dll
MSIMG32.dll
WINSPOOL.DRV
ADVAPI32.dll
SHELL32.dll
COMCTL32.dll
SHLWAPI.dll
UxTheme.dll
ole32.dll
OLEAUT32.dll
oledlg.dll
gdiplus.dll
OLEACC.dll
WINMM.dll
IMM32.dll
```

No WinInet, Winsock, or other obvious network library is in the static import table. That is not a full security audit, but no network subsystem is needed for the observed device configuration path.

## What is not in the payload

The extracted installer did not contain:

- A `.sys` kernel driver.
- A separate service executable.
- A device-specific DLL.
- A standalone firmware image.
- Source code.

This is important because the application's device protocol is implemented directly in the application and can be reconstructed from it. A Linux implementation should be able to use HIDAPI or Linux `hidraw`; a custom kernel module is not currently indicated.

The controller vendor's official A825 reference package independently uses the same direct HID architecture and also contains no custom driver files. That comparison is documented in [Related hardware research](related-hardware-research.md).

## Configuration and data files

The application ships its product configuration as editable-looking INI and DAT files rather than embedding all semantics in resources. Important files include:

```text
app/constMacro.dat
app/skins/config/config.ini
app/skins/config/configReset.ini
app/skins/config/constMacro.dat
app/skins/config/PUBG_CN.dat
app/skins/config/PUBG_EN.dat
app/skins/1_INI_EN/LanguageText.ini
app/skins/1_INI_EN/LBWarning.ini
app/skins/1_INI_EN/PUBG.dat
app/skins/1_INI_EN/macro/.dat
app/skins/1_INI_EN/macro/macroGrp.ini
app/skins/1_INI_EN/macroReset/macroGrp.ini
```

Several language/configuration files mix Chinese text with English and appear to use UTF-16LE or a legacy Chinese encoding. Future parsers must preserve the original bytes until the encoding is positively identified.

## Security and execution note

The executable was analyzed only with file identification, hashes, string extraction, PE inspection, and disassembly. Static analysis establishes program structure; it does not prove that the executable is safe to run. The exact hash matching the official download establishes provenance, not a blanket security guarantee.
