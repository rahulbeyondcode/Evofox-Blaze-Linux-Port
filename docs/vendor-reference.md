# Vendor reference material

The vendor executables are static interoperability references, never executed.
This project's MIT license does not grant redistribution rights to vendor code,
artwork, or fonts. Extracted files and third-party tools stay outside Git.

## EvoFox artifact identity

Official support page: <https://support.amkette.com/software/evofox-blaze-software/>

The original 2026-08-26 research recorded both official downloads as identical:

- <https://amkette-media.blr1.digitaloceanspaces.com/nexus-amkette/software/1753439033308.exe>
- <https://amkette-media.blr1.digitaloceanspaces.com/nexus-amkette/software/1753098734587.exe>

| Artifact | SHA-256 |
|---|---|
| Repository `evofox-blaze.exe` (5,243,024 bytes) | `c45662764d9847e3b14c34d19a745e6b6b34a7e966889be18814cd5513c47468` |
| Extracted `app/Gaming Mouse 3.0.exe` | `9eec736ee629ff9d0684f787a270afe86d064fdcf23e7eb11f921dc7844eee55` |

The installer and freshly extracted application hashes were rechecked during
this implementation session and match the recorded identities. The download links
above are historical provenance, not a claim that they were revalidated today.

Inno Setup 5.5.7 Unicode; extracted application is native PE32 x86, not .NET.
Extraction produced 132 files; no `.sys` file or separate firmware image was
identified in the manifest. Certificate strings name Wuxi Yingsite Microelectronics;
this is signer metadata, not cryptographic signature verification.

Use `innoextract` for static extraction. Analyze the inner application, not
the installer's setup loader. Relevant application sections:

| Section | Preferred VA | File offset |
|---|---|---|
| `.text` | `0x401000` | `0x400` |
| `.rdata` | `0x602000` | `0x200e00` |
| `.data` | `0x66b000` | `0x269800` |
| `.rsrc` | `0x6e7000` | `0x26f600` |

## Configuration search seeds

Extract these alongside the executable when resolving setting encodings:

| File / fields | What the original static research establishes |
|---|---|
| `app/skins/config/config.ini`, `configReset.ini` | Product model and defaults |
| `ConfigNum=4`, `Config0`…`Config4` | Four UI profiles; extra section's purpose unknown |
| `KeyNum=8`, `K1_MAP`…`K9_MAP`, `K0`…`K11` | Eight declared keys with extra mapping slots; not nine proven buttons |
| `DPI_LEVEL`, `DPI_SET0`…`5`, `DPI_SET_EN0`…`5`, `DPI*_R/G/B` | Six DPI-stage UI controls; values may be encoded indexes |
| `LED_TYPE`, `LED_BRIGHT`, `LED_CYC_TIME`, `LED_CYCTIME`, `LED_USER_COLER_EN` | Lighting fields; preserve vendor spellings |
| `LED_FEATURE_SCOLOR`, `LED_FEATURE_DIREC`, `LED_FEATURE_SYMMETRY` | Candidate lighting options |
| `USB_SPEED`, `DPI_SPEED`, `WHEEL_SPEED`, `FIRE_TIME` | Polling, pointer/wheel speed, rapid-fire timing; hardware vs OS effects unresolved |
| `app/skins/1_INI_EN/LanguageText.ini` and `skin_*.ini` | UI labels, not wire encodings |
| `constMacro.dat`, `macroGrp.ini`, `MacMd5`, `DAT_VER`, `SOFT_HARD_MAC` | Macro-format search seeds; no decoded format yet |

An earlier default/shared block has `DPI_SET0..5 = 2,5,10,13,16,22`,
`USB_SPEED=2`, and `FIRE_TIME=50`. These are file values, not measured hardware
state. The UI's sixteen lighting labels do not establish sixteen implemented
device modes. Profile labels and key defaults contain template inconsistencies.
Preserve original configuration bytes before deciding their text encoding.

## Independent capture and implementation review

The original [OpenRGB ANKO request #3551](https://gitlab.com/CalcProgrammer1/OpenRGB/-/issues/3551)
publishes a [USB capture](https://gitlab.com/CalcProgrammer1/OpenRGB/uploads/a3d265c6bea632625982e96b6227c5d6/USB_GAMING_MOUSE_KM43243952.pcapng)
for a **different physical product**, ANKO KM43243952. Reviewed during this
bring-up, the 284,884-byte file has SHA-256
`db3a3ba224069226ce75d9ded8a37d9363e71deb15737d749a2f951ad637c9c8`.
Its USB device/configuration descriptors match the captured Blaze envelope;
no HID report descriptor was observed. Packets 1943–1995 corroborate the
source-derived eight-byte read and contain no commit in that read. The returned
bytes match the preceding committed block, not the staged zeros.

The focused [fixture](../tests/fixtures/anko-read-corroboration.json) preserves
packet numbers and technical facts; the full third-party capture stays outside
Git. Recheck it without hardware or executing downloaded code:

```sh
python3 -m tools.audit_public_capture --capture <downloaded.pcapng>
```

An existing [Phantom Air implementation](https://github.com/Navadeep-Reddy/evofox-phantom-air-linux)
was reviewed at commit `8fe57c3121c4882899adbb88a3aa4e4c7067354a`, pinned by
file hashes in the fixture. It includes the same ANKO capture, verified against
the original OpenRGB upload; it is not independent proof for the attached Blaze.
Importantly, its `protocol.py` appends phase `09` to reads while both our exact
Blaze reader and the captured read do **not**. That behavior was not imported.
No external application, hardware test, install script, or reference driver
was executed. Polling labels are additionally informed by its code; real
event frequency and runtime/persistent-state equivalence remain unmeasured.

## A825 comparison

Official controller site: <https://www.instant-sys.com/>

The following identities were recorded on 2026-08-26; not re-downloaded in the
descriptor capture session:

| Artifact | URL | SHA-256 |
|---|---|---|
| A825 V1.01 summary datasheet | [PDF](https://www.instant-sys.com/storage/file/20260313/8c5e1a37bbdfe6bdf35620d9a2975a89.pdf) | `76f8b7ca950aa686b254adcef9b10ec4ad1f03fedbe3377ea989623e91c48d56` |
| Reference installer | [EXE](https://www.instant-sys.com/storage/file/20260313/c41912deb8fb976f9f04ccb504e99607.exe) | `07d068f98e8cc67b4364cd9cb0e83b8bffab023011c9b1b9d5056d178e5373a2` |
| Extracted `DevDock.exe` | From that installer | `27fb599a729ad72e7cb48b4e7925a1761d24f438149f80d0045e02bd9c05a6a8` |

Its configuration accepts `30fa:1e01` and `30fa:1441`; the EvoFox application
accepts `30fa:1e01` and `30fa:1440`. Both use direct HID feature reports.
The A825 family advertises four groups, six DPI stages, and 125/250/500/1000 Hz.
Candidate CPI table:

```text
200 400 600 800 1000 1200 1400 1600 1800 2000 2400 3200
4000 4800 5600 6400 7200 8000 8800 9600 10400 11200 12800
```

These are family candidates, not Blaze limits or confirmed index encodings.
Do not infer capacity from ambiguous `32kb`, `EEP_CAP=4`, a 16-bit address,
or a third party's capture-size estimate.

The [libratbag GM320 request 1795](https://github.com/libratbag/libratbag/issues/1795)
was also rechecked: it is open, has no comments, and reports the same VID/PID
and an A825 chip photo. Its capture-size/address guesses are not a protocol
specification. There is now a concrete related implementation above; the old
broad “no implementation found” claim must not be reused.
