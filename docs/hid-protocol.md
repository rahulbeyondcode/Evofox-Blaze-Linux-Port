# Recovered HID protocol

This document records the strongest technical evidence from static disassembly. Addresses are preferred virtual addresses in `Gaming Mouse 3.0.exe` unless explicitly called file offsets. They are useful for relocating the same code in Ghidra or another disassembler.

## Device identity

The application's initialized `.data` begins at virtual address `0x66b000`, corresponding to file offset `0x269800` in the extracted executable. Its first 12 bytes were:

```text
fa 30 00 00 40 14 00 00 01 1e 00 00
```

The enumeration function reads `HIDD_ATTRIBUTES.VendorID` and `ProductID` as 16-bit values, then compares them with those initialized 32-bit globals. Therefore:

```text
Vendor ID:       0x30fa
Product ID #1:   0x1440
Product ID #2:   0x1e01
```

This is confirmed by code at approximately `0x41a081` through `0x41a0d8`:

- Vendor ID at stack offset `[ebp-0x7c]` is compared with `[0x66b000]`.
- Product ID at `[ebp-0x7a]` is compared with `[0x66b004]` and `[0x66b008]`.
- A global flag records which accepted PID matched.

The physical mouse must still confirm which PID it currently exposes. The second PID may represent another revision or operating mode.

## Enumeration algorithm

Confirmed behavior in the function beginning near `0x419df0`:

1. Call `HidD_GetHidGuid`.
2. Obtain the present HID device-interface set with SetupAPI.
3. Enumerate up to 100 HID interfaces.
4. Resolve each device path.
5. Open the path and populate a 12-byte `HIDD_ATTRIBUTES` structure.
6. Read the HID product string into a 100-byte buffer.
7. Require VID `30fa` and PID `1440` or `1e01`.
8. Obtain `HIDP_CAPS` through `HidD_GetPreparsedData` and `HidP_GetCaps`.
9. Select interfaces based on Usage and Usage Page.
10. Keep separate handles for two vendor-defined interfaces.

The application imports `RegisterDeviceNotificationW`, so it also responds to device arrival/removal.

## HID interface selection

The application requires Usage `0x0001` and recognizes two vendor usage pages:

| Usage Page | Usage | Open mode observed | Role |
|---|---:|---|---|
| `0xff00` | `0x0001` | `GENERIC_READ` | Secondary/read interface; exact role unknown |
| `0xff01` | `0x0001` | `GENERIC_WRITE` | Configuration interface used for HID feature commands |

Relevant code is approximately `0x41a113` through `0x41a1f2`.

The `HIDP_CAPS` for `ff00` is copied to a global block beginning `0x671050`. The caps for `ff01` are copied to a block beginning `0x671090`.

`HIDP_CAPS.FeatureReportByteLength` is at offset eight in that structure, so the feature-report length later read from `0x671098` belongs to the `ff01` interface. The program does not hard-code this length; it asks the physical device.

## Handles and global buffers

Observed global state:

| Address | Meaning |
|---|---|
| `0x671010` | Temporary `HIDP_CAPS` output |
| `0x671050` | Copied caps for Usage Page `ff00` |
| `0x671090` | Copied caps for Usage Page `ff01` |
| `0x671098` | `ff01` feature-report byte length |
| `0x6710d8` | Shared feature-report buffer, guarded as a maximum 256-byte array |
| `0x67141c` | Configuration handle associated with Usage Page `ff01` |
| `0x671420` | Secondary handle associated with Usage Page `ff00` |

The buffer code repeatedly checks computed indexes against `0x100`, establishing a 256-byte allocation. This allocation size is not the same as the actual feature-report length.

## HID API calls and thunks

The PE import thunks relevant to configuration were:

| Function | Thunk address |
|---|---:|
| `HidP_GetCaps` | `0x5d179f` |
| `HidD_GetAttributes` | `0x5d17a5` |
| `HidD_GetHidGuid` | `0x5d17ab` |
| `HidD_GetPreparsedData` | `0x5d17b1` |
| `HidD_FreePreparsedData` | `0x5d17b7` |
| `HidD_GetFeature` | `0x5d17bd` |
| `HidD_SetFeature` | `0x5d17c3` |
| `HidD_GetProductString` | `0x5d17c9` |

The static scan found approximately five calls to `HidD_GetFeature` and 24 calls to `HidD_SetFeature`. This is enough surface area to reconstruct the command families from the executable if device observation alone is insufficient.

## Report mechanics

Confirmed recurring behavior:

- The shared report buffer starts with byte `0x07`, establishing report ID 7.
- The program passes the descriptor-derived feature-report length to both `HidD_GetFeature` and `HidD_SetFeature`.
- Several command builders populate only byte indexes 0 through 7.
- Some operations sleep for 2 ms or 10 ms between feature transactions.
- A status query sets only report ID `07`, calls `GetFeature`, and examines response byte 6.

An eight-byte feature report is therefore a strong inference, but it must be confirmed from the Linux report descriptor or `HIDP_CAPS` equivalent before implementation.

## Recovered command `0x18`

The function at `0x413910` is a generic feature-report writer. It constructs:

```text
byte 0: 0x07
byte 1: 0x18
byte 2: packed flags/address component
byte 3: argument 8, low byte
byte 4: argument 7, low byte
byte 5: argument 7, high byte
byte 6: argument 10, low byte
byte 7: argument 9, low byte
```

With the function's ten stack arguments numbered from one, byte 2 is built as:

```text
(arg1 << 5) + (arg2 << 4) + (arg3 * 4) +
(arg4 * 8) + (arg5 * 2) + arg6
```

Only the low byte is stored. Argument 7 is stored little-endian in bytes 4 and 5. The function then calls `HidD_SetFeature(handle, buffer, FeatureReportByteLength)`.

A nearby routine repeatedly invokes this writer, waits 2 ms, invokes `HidD_GetFeature`, and copies response byte 1 to an output buffer. The official A825 reference driver now makes indexed configuration-memory access a strong family-level interpretation, but it remains **inferred** for the physical Blaze.

## Independent protocol-family corroboration

A public [libratbag support request for the Ant Esports GM320](https://github.com/libratbag/libratbag/issues/1795) reports the same USB ID `30fa:1440`, report ID `07`, HID `SET_REPORT` writes, and a packet prefix `07 18`. Its author describes the following three bytes as a possible memory address and identifies an Instant Microelectronics A825 controller after opening that different mouse.

This is unusually close independent corroboration of the static findings, but it is not Blaze-specific proof. The issue concerns another retail product, its reported 65-KiB capture is not attached, and no libratbag implementation accompanies it. Do not import an address map or assume an A825 controller until the physical Blaze descriptor and behavior agree. See [Related hardware research](related-hardware-research.md) for the complete comparison and source limitations.

The controller vendor's official generic A825 driver is stronger evidence than the retail-device report. Its statically recovered write helper sends fixed eight-byte frames in these phases:

```text
07 18 03 <index> <address-low> <address-high> <data> <length-minus-one>
07 18 09 00      <address-low> <address-high> 00     <length-minus-one>
07 18 00 00      <address-low> <address-high> 00     00
```

This aligns with the EvoFox builder byte-for-byte and suggests the following semantics:

| Byte | Family-level interpretation |
|---:|---|
| 0 | Report ID `07` |
| 1 | Command family `18` |
| 2 | Operation or transaction phase |
| 3 | Byte/chunk index or subcommand value |
| 4–5 | Little-endian configuration address |
| 6 | Data or operation-specific value |
| 7 | Length-minus-one or operation-specific control |

The generic driver waits about 4 ms before its byte-2 `09` frame and about 12 ms before its final byte-2 `00` frame. These timings and operation labels must be verified on the Blaze before writes are enabled.

## Other observed command bytes

Several report writers use byte 1 value `0x16`, including code around `0x430098` and `0x43023e`. The surrounding code supplies additional bytes from configuration globals. Its exact feature meaning has not been assigned.

Do not label command `0x16` as DPI, RGB, macro, or profile control until a differential device test or deeper data-flow analysis proves it.

## Encryption and checksums

The recovered `0x18` command is assembled directly from arguments and sent without a visible encryption or checksum step. Other simple report builders behave similarly. The application does contain strings related to encrypted **macro-file export**, which is a separate desktop-file feature and is not evidence of encrypted USB traffic.

Current conclusion:

- No protocol-wide encryption layer was evident.
- No protocol-wide checksum has yet been identified.
- Only fully decoded command paths may be assumed to lack a checksum.

## Linux transport implication

The expected Linux transport is HIDAPI or direct `hidraw` feature-report ioctls:

- `hid_get_feature_report` / `HIDIOCGFEATURE` for reads.
- `hid_send_feature_report` / `HIDIOCSFEATURE` for writes.

The initial probe must enumerate by VID/PID and then verify usage page, usage, interface number, report ID, and report length. It must not choose an interface solely by `/dev/hidrawN` ordering.
