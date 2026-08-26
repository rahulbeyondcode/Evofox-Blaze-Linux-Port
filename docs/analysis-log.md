# Static research record

## Scope

Research date: 2026-08-26

All application findings in this repository came from hashes, archive listing/extraction, strings, configuration files, PE metadata, and static disassembly. No vendor executable was run and no USB device was accessed. Physical-device facts remain clearly marked as pending.

## EvoFox installer identification

Representative read-only commands:

```bash
file evofox-blaze.exe
sha256sum evofox-blaze.exe
stat evofox-blaze.exe
xxd -l 256 evofox-blaze.exe
strings -a -n 4 evofox-blaze.exe
strings -a -e l -n 3 evofox-blaze.exe
objdump -x evofox-blaze.exe
```

Results:

```text
size:    5,243,024 bytes
SHA-256: c45662764d9847e3b14c34d19a745e6b6b34a7e966889be18814cd5513c47468
format:  PE32 x86 Inno Setup 5.5.7 Unicode
```

Both links on the [official EvoFox Blaze support page](https://support.amkette.com/software/evofox-blaze-software/) produced the same SHA-256 as the repository installer.

## EvoFox payload inspection

The archive was listed and extracted statically with `innoextract` 1.9. The main payload was identified and inspected with:

```bash
file 'Gaming Mouse 3.0.exe'
sha256sum 'Gaming Mouse 3.0.exe'
objdump -h 'Gaming Mouse 3.0.exe'
objdump -p 'Gaming Mouse 3.0.exe'
objdump -d -Mintel 'Gaming Mouse 3.0.exe'
strings -a -n 4 'Gaming Mouse 3.0.exe'
strings -a -e l -n 3 'Gaming Mouse 3.0.exe'
```

The payload's hashes, manifest, configuration fields, UI strings, imports, and PE layout are retained in [Payload and application](payload-and-application.md) and [Payload inventory](payload-inventory.md).

## Key EvoFox disassembly locations

Preferred virtual addresses in `Gaming Mouse 3.0.exe`:

```text
0x413910  command 0x18 feature-report builder
0x413a10  repeated write/wait/get/read-byte pattern
0x419df0  HID enumeration and VID/PID/interface filtering
0x41a340  HIDP_CAPS acquisition
0x5d179f  HidP_GetCaps import thunk
0x5d17a5  HidD_GetAttributes import thunk
0x5d17ab  HidD_GetHidGuid import thunk
0x5d17b1  HidD_GetPreparsedData import thunk
0x5d17b7  HidD_FreePreparsedData import thunk
0x5d17bd  HidD_GetFeature import thunk
0x5d17c3  HidD_SetFeature import thunk
0x5d17c9  HidD_GetProductString import thunk
```

The initialized VID/PID globals are at extracted-file offset `0x269800`. The bytes decode to vendor `30fa` and products `1440`/`1e01` when read using the application's comparison logic.

## Official A825 research

The official [Instant Microelectronics site](https://www.instant-sys.com/) was searched through its public A825 result page. The site identifies Wuxi Yingsite Microelectronics, matching the English signer string in the EvoFox installer, and publishes both a summary datasheet and generic A825 reference driver.

Verified public artifacts:

```text
A825 English summary datasheet
URL:     https://www.instant-sys.com/storage/file/20260313/8c5e1a37bbdfe6bdf35620d9a2975a89.pdf
SHA-256: 76f8b7ca950aa686b254adcef9b10ec4ad1f03fedbe3377ea989623e91c48d56

A825 reference-driver installer
URL:     https://www.instant-sys.com/storage/file/20260313/c41912deb8fb976f9f04ccb504e99607.exe
size:    6,154,888 bytes
SHA-256: 07d068f98e8cc67b4364cd9cb0e83b8bffab023011c9b1b9d5056d178e5373a2
```

The reference package was listed and extracted statically with `innoextract` 1.9. It contains no `.sys`, `.cat`, or `.inf` driver file. Its main application is:

```text
DevDock.exe
size:    1,654,288 bytes
SHA-256: 27fb599a729ad72e7cb48b4e7925a1761d24f438149f80d0045e02bd9c05a6a8
format:  PE32 x86
PE time: 2024-09-20 13:26:58
```

The UTF-16LE `DeviceFeature.ini` was converted to text for inspection. It names `Instant A825 Gaming Mouse`, gives VID/PID pairs `30fa:1e01` and `30fa:1441`, declares 23 DPI choices, and enables fourteen lighting-list entries.

Relevant preferred virtual addresses in `DevDock.exe`:

```text
0x455a40  staged eight-byte 07 18 configuration write helper
0x455ba0  two-frame 07 18 sequence using byte-2 values 10 and 00
0x486160  07 18 sequence using byte-2 values 03, 05, and 00 plus GetFeature
0x4fc738  HidD_SetFeature import slot
0x4fc748  HidD_GetFeature import slot
```

The write helper at `0x455a40` was followed instruction by instruction to establish the index, low/high address, data, and length-minus-one byte assignments recorded in [Recovered HID protocol](hid-protocol.md). Names such as “commit” and “finalize” remain interpretations, not symbols from the binary.

## Public implementation search

The [libratbag support request for Ant Esports GM320](https://github.com/libratbag/libratbag/issues/1795) was inspected directly. Its body supplied the same `30fa:1440`, report ID `07`, and `07 18` prefix, but no capture or implementation was attached.

The current libratbag source archive was scanned across all 123 `data/devices/*.device` files for:

```text
30fa
1440
1e01
A825
Instant Micro
```

No match was present. Public GitHub issue search for exact `30fa:1e01` returned zero results. These are bounded, dated results rather than proof that no implementation exists anywhere.

## Confidence discipline

- Installer/application bytes and disassembly facts are **confirmed** for the exact hashes recorded here.
- Datasheet capabilities and generic-driver packets are **confirmed** for the A825 family, not automatically for every EvoFox revision.
- Matching signer, USB IDs, feature-report prefix, profile count, and DPI count make an A825-family Blaze **strongly inferred**.
- The physical mouse remains the source of truth for PID, revision, descriptor, report length, address map, safe ranges, and persistence.
