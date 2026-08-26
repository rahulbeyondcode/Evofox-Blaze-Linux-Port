# AI/developer handoff

Use this file to start a new AI session on the Linux machine. The detailed evidence is linked below and should be read before making protocol claims.

## Copyable context

```text
We are building a native Linux configuration utility for the EvoFox Blaze
programmable gaming mouse. Development starts on Linux with the physical mouse;
the vendor binaries are static protocol references only. Firmware, bootloader,
erase, and raw-flash operations are out of scope.

The official installer in the repository is evofox-blaze.exe, size 5,243,024
bytes, SHA-256:
c45662764d9847e3b14c34d19a745e6b6b34a7e966889be18814cd5513c47468
It exactly matched both official Amkette download links on 2026-08-26.

Static extraction found app/Gaming Mouse 3.0.exe, a native PE32 x86 MFC-style
application, SHA-256:
9eec736ee629ff9d0684f787a270afe86d064fdcf23e7eb11f921dc7844eee55
No custom .sys driver or standalone firmware was bundled.

Confirmed HID facts from disassembly:
- VID 0x30fa
- accepted PIDs 0x1440 and 0x1e01
- Usage 0x0001 on Usage Pages 0xff00 and 0xff01
- ff01 is the configuration collection used for feature reports
- report ID 0x07
- report length is read from HIDP_CAPS.FeatureReportByteLength
- command builders usually fill bytes 0..7, so length 8 is likely but unproven
- at least one command is [07 18 ...] with a directly recovered packet builder
- Windows calls HidD_GetFeature/HidD_SetFeature directly; no kernel driver layer

Strong controller-family evidence found on 2026-08-26:
- Wuxi Yingsite/Instant Microelectronics, the EvoFox installer signer, officially
  publishes an A825 mouse-controller datasheet and generic reference driver
- generic A825 config accepts 30fa:1e01 and 30fa:1441; EvoFox accepts 30fa:1e01
  and 30fa:1440; the datasheet says VID/PID are OEM-customizable
- another reported A825 mouse uses 30fa:1440 and the same 07 18 packets
- official generic A825 code hard-codes 8-byte feature reports and constructs:
  07 18 03 <index> <addr-lo> <addr-hi> <data> <length-minus-one>
  07 18 09 00      <addr-lo> <addr-hi> 00     <length-minus-one>
  07 18 00 00      <addr-lo> <addr-hi> 00     00
- treat those phases as family evidence, not safe Blaze write commands yet
- A825 family candidates: four onboard groups, six DPI stages selected from a
  23-value 200..12800 CPI table, and 125/250/500/1000 Hz report rates
- no matching libratbag device definition or implementation was found

The first Linux task is strictly read-only: run lsusb, map all hidraw nodes,
save USB and HID report descriptors, and confirm PID/interface/usage/report
length. Put sanitized captures under docs/device-captures/. Do not call
hid_send_feature_report or HIDIOCSFEATURE yet.

Read docs/README.md, docs/hid-protocol.md,
docs/related-hardware-research.md, docs/linux-bringup.md, and
docs/open-questions.md before acting. Preserve the confirmed/inferred/unknown
distinction. Update the docs whenever an unknown is resolved and save evidence
or a reproducible command with it.
```

## Immediate next task on Linux

1. Confirm the physical device with `lsusb`.
2. Capture `lsusb -v` for the observed VID/PID.
3. Map every corresponding `/dev/hidrawN` node.
4. Save each raw HID report descriptor.
5. Confirm the `ff00` and `ff01` collections and feature-report length.
6. Write a read-only enumeration/probe program.

The read-only CLI is an engineering tool, not the final product. The target deliverable is a native Linux GUI configuration utility with the Windows application's user-facing capabilities, built on the tested transport, codec, and model layers.

Do not begin by re-extracting or re-analyzing the installer. The key static facts and offsets are already in [Recovered HID protocol](hid-protocol.md). Return to the executable only when a specific unresolved packet question requires it.

## Working expectations for a future AI

- Treat the physical device as the source of truth for descriptors and revision differences.
- Keep raw transport separate from semantic command encoding.
- Add mock-transport tests before enabling writes.
- Show exact packets and require confirmation for early write experiments.
- Never infer onboard persistence merely because the Windows UI has profiles.
- Never infer literal polling rates or DPI from index fields without evidence.
- Do not copy vendor artwork into a distributable UI without resolving licensing.
- Keep a raw backup path available before button, profile, or macro writes.

## Detailed references

- [Provenance and hashes](software-provenance.md)
- [Application architecture](payload-and-application.md)
- [Recovered HID protocol](hid-protocol.md)
- [A825 and related-hardware evidence](related-hardware-research.md)
- [Feature model](feature-model.md)
- [Safe Linux procedure](linux-bringup.md)
- [Implementation milestones](implementation-roadmap.md)
- [Pending research](open-questions.md)
