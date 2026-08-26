# Related hardware and controller-family research

Research date: 2026-08-26

This document records public evidence that may shorten the Linux protocol work. It deliberately separates official A825 material, a third-party report about another retail mouse, and facts proven specifically from the EvoFox application.

## Conclusion

The EvoFox Blaze is very likely in the Instant Microelectronics A825 protocol family, or a very closely related firmware family.

That conclusion is **strongly inferred**, not yet physically confirmed. The evidence is unusually specific:

- The EvoFox installer contains signing-certificate strings for `Wuxi Yingsite Microelectronics Co., Ltd.`
- The official controller site identifies itself as `无锡英斯特微电子有限公司`, the Chinese company name corresponding to Wuxi Yingsite Microelectronics, and uses the Instant brand.
- The site's official A825 reference driver is signed by the same English company name.
- The reference driver's configuration accepts `30fa:1e01`; the EvoFox application also accepts `30fa:1e01`.
- Another A825 mouse is reported at `30fa:1440`, the EvoFox application's other accepted ID.
- Both the EvoFox application and the A825 reference driver use report ID `07`, HID feature reports, command `0x18`, and eight-byte command builders.

The remaining proof is simple but important: identify the physical Blaze on Linux and compare its descriptor and harmless read behavior.

## Official Instant A825 sources

The official [Instant Microelectronics website](https://www.instant-sys.com/) describes the company as a designer of chips for PC peripherals, including mouse sensors and keyboard controllers. Its [public search result for A825](https://www.instant-sys.com/index/lists/search.html?title=A825) exposes:

- An A825 product result.
- An English A825 summary datasheet.
- A generic A825 Windows reference driver.
- Demonstration videos for performance, basic settings, macros, and lighting.

The old datasheet URL linked from GitHub currently redirects to the vendor site's error route. The current official English summary is:

- <https://www.instant-sys.com/storage/file/20260313/8c5e1a37bbdfe6bdf35620d9a2975a89.pdf>
- SHA-256 on 2026-08-26: `76f8b7ca950aa686b254adcef9b10ec4ad1f03fedbe3377ea989623e91c48d56`
- Document identity: `A825 DATASHEET`, Instant Microelectronics Co., Ltd., version V1.01.
- PDF metadata: four pages; created 2021-01-04 and modified 2026-02-26.

### Datasheet capabilities

The summary datasheet describes A825 as a full-speed USB optical-mouse SoC compliant with USB 2.0 and HID 1.1. It states:

- Up to six DPI/CPI stages.
- Twenty-three selectable values: 200, 400, 600, 800, 1000, 1200, 1400, 1600, 1800, 2000, 2400, 3200, 4000, 4800, 5600, 6400, 7200, 8000, 8800, 9600, 10400, 11200, and 12800 CPI.
- Selectable USB report rates of 125, 250, 500, and 1000 Hz.
- Four built-in configuration groups and a button action for selecting a group.
- Customizable K1 through K9 buttons plus the wheel.
- Three lighting families and up to ten lighting effects at the chip-capability level.
- User-customizable buttons, movement behavior, macros, DPI, VID/PID, colours, and lighting effects.
- Storage capacity described as `32kb`. The capitalization is ambiguous; do not silently reinterpret it as 32 KiB.
- Settings configured by the vendor program can operate when the mouse is later used with macOS or Android. This is direct evidence that the controller is designed for host-independent onboard configuration.

These are A825 capabilities, not guaranteed Blaze product limits. An OEM configuration may expose only a subset.

## Official A825 reference driver

Current public file:

- <https://www.instant-sys.com/storage/file/20260313/c41912deb8fb976f9f04ccb504e99607.exe>
- Size: `6,154,888` bytes.
- SHA-256: `07d068f98e8cc67b4364cd9cb0e83b8bffab023011c9b1b9d5056d178e5373a2`.
- Inno Setup 5.5.7 Unicode, the same installer generation as the EvoFox package.
- Signing-certificate strings name `Wuxi Yingsite Microelectronics Co., Ltd.`

The package was statically listed and extracted for comparison; no executable was run. It contains no `.sys`, `.cat`, or `.inf` driver. The main program is:

```text
DevDock.exe
size:    1,654,288 bytes
SHA-256: 27fb599a729ad72e7cb48b4e7925a1761d24f438149f80d0045e02bd9c05a6a8
format:  PE32 x86
PE time: 2024-09-20 13:26:58
```

`DevDock.exe` directly imports `HidD_GetFeature`, `HidD_SetFeature`, `HidD_GetAttributes`, `HidD_GetPreparsedData`, and `HidP_GetCaps`. This independently confirms that the controller vendor's own configuration architecture is ordinary user-space HID, not a custom kernel driver.

Its version metadata identifies `New825Tab` version `1.0.0`. The bundled `DeviceFeature.ini` identifies `Instant A825 Gaming Mouse` and contains:

```text
VID  = 12538 = 0x30fa
PID  =  7681 = 0x1e01
VID2 = 12538 = 0x30fa
PID2 =  5185 = 0x1441
```

This is a critical bridge. The EvoFox program accepts `30fa:1440` and `30fa:1e01`; the generic A825 program accepts `30fa:1e01` and `30fa:1441`. The shared `1e01` PID and adjacent `1440`/`1441` PIDs strongly suggest OEM or firmware variants. The A825 datasheet explicitly says VID and PID are customizable, so retail-model ID differences are expected.

Other generic configuration facts are:

```text
EEP_CAP=4
EEP_VER=1
KeyNum=9
DPI_GEAR_NUM=23
LED_MODE_SW_EN=16383  # 0x3fff, bits 0 through 13
```

`EEP_CAP` looks related to stored configuration capacity, but its unit and exact meaning are unknown. It must not be translated into bytes. The configuration lists fourteen lighting entries numbered 0 through 13, matching the `0x3fff` enable mask.

## A825 eight-byte transaction evidence

The generic reference program hard-codes eight-byte buffers at its A825 feature-report call sites. A function beginning near preferred VA `0x455a40` accepts a handle, a base value that is split into low/high address bytes, a data pointer, and a length. It sends this sequence:

```text
For each data byte i:
07 18 03 ii aa AA dd nn

Then:
07 18 09 00 aa AA 00 nn

Then:
07 18 00 00 aa AA 00 00
```

Where the disassembly establishes:

```text
ii = zero-based data-byte index
aa = base address low byte
AA = base address high byte
dd = data byte i
nn = total length minus one
```

The function waits about 4 ms before the `09` frame and about 12 ms before the final `00` frame. This looks like a staged memory/configuration write followed by commit/finalization, but those operation names remain inferred until readback or captures prove them.

Other A825 code around `0x486160` uses byte-2 values `03` and `05`, address bytes `80 0f`, `HidD_GetFeature`, and a final byte-2 value `00`. This supports a memory-addressed request/read transaction model. Do not send these example addresses to the Blaze merely because they occur in the generic driver.

This new evidence clarifies the EvoFox `0x18` builder described in [Recovered HID protocol](hid-protocol.md): its byte 2 is probably an operation/phase field, byte 3 an index, bytes 4–5 a little-endian address, byte 6 data or a subcommand value, and byte 7 a count/control value. That mapping is still family-derived until a Blaze capture confirms it.

## Third-party retail-device report

An open [libratbag issue for the Ant Esports GM320](https://github.com/libratbag/libratbag/issues/1795) was filed on 2026-01-03 and remained open without an implementation on 2026-08-26. Its author reports:

- USB ID `30fa:1440`.
- A825 silicon identified by opening that mouse.
- Eight buttons, four profiles, six DPI stages from 200 through 12,800, and fourteen lighting modes.
- Report ID `07`.
- Configuration through HID `SET_REPORT` request `0x09`.
- Packets beginning `07 18` followed by what the author suspected was address information.
- A roughly 65-KiB, 900-packet capture while investigating polling and lighting.

The capture is not attached to the issue, so none of its unshown memory map can be relied on. The issue is valuable as independent corroboration, not as a protocol specification.

The reported “65 KB” should not be equated with physical storage. The official transaction helper uses a 16-bit address, which can describe a 65,536-address span, while the datasheet separately says `32kb` storage capacity. The issue's packet estimate also does not establish bytes per transaction. It may describe an address-space sweep, sparse registers, or a loose size estimate.

## Correlation table

| Observation | EvoFox application | Official A825 material | GM320 report | Interpretation |
|---|---|---|---|---|
| Vendor ID | `30fa` | `30fa` in reference config | `30fa` | Exact family match |
| Product IDs | `1440`, `1e01` | `1e01`, `1441` | `1440` | Strong OEM/revision pattern |
| HID report ID | `07` | `07` | `07` | Exact protocol match |
| Main prefix | `07 18` | `07 18` | `07 18` | Exact protocol match |
| Report length | Likely 8 | Hard-coded 8 | Not explicitly stated | Eight is now a strong family inference |
| Configuration profiles | 4 | 4 groups | 4 | Exact model capability match |
| DPI stages | 6 | Up to 6 | 6 | Exact model capability match |
| Buttons | 8 declared, ninth map entry | Up to K1–K9 plus wheel | 8 | OEM configuration differs |
| Lighting list | 16 UI labels | 14 generic entries; chip says up to 10 effects | 14 | UI/mode bookkeeping is model-specific |
| Polling choices | Four, values previously unknown | 125/250/500/1000 Hz | Mapping reportedly under study | Likely values; encoding still unknown |
| Onboard settings | Inferred from profiles | Explicit controller storage/groups | Reported memory capture | Strong design evidence; Blaze persistence still needs a power-cycle test |

## Current open-source support status

As of 2026-08-26:

- The libratbag support request has no linked implementation.
- A scan of all 123 `.device` definitions in the current [libratbag device database](https://github.com/libratbag/libratbag/tree/master/data/devices) found no `30fa`, `1440`, `1e01`, `A825`, or `Instant Micro` entry.
- Public GitHub issue search returned no exact `30fa:1e01` result.
- No public repository containing the GM320 author's reported capture was found.

This is a bounded search result, not proof that no implementation exists anywhere. Recheck libratbag issue 1795 before starting major integration work.

## How this changes Linux bring-up

Do not begin by replaying the generic driver's writes. Instead:

1. Capture the physical Blaze VID, PID, `bcdDevice`, all HID collections, and report descriptors.
2. Verify `ff00/0001`, `ff01/0001`, report ID `07`, and an eight-byte feature report.
3. If PID is `1e01`, treat the official A825 reference driver as especially relevant; if it is `1440`, compare both the reference driver and GM320 report.
4. Attempt harmless state reads only after preserving the request and response bytes.
5. Use differential observations to assign byte-2 operations and addresses.
6. Treat the A825 polling-rate list and DPI table as candidate validation ranges, not Blaze facts, until readback agrees.
7. Test persistence by unplugging the mouse and using it on another host before claiming onboard-memory support.

If physical evidence matches, the fastest route is an A825-family protocol codec with per-device capability tables rather than a one-model-only packet implementation.
