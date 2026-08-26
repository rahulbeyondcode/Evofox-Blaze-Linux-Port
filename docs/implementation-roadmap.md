# Implementation roadmap

The implementation should be transport-first and UI-last. The final product is a graphical Linux configuration utility comparable to the vendor's Windows application. The protocol library and a small CLI are the testable foundation; the CLI is not a substitute for the GUI. Everything must remain testable without a physical mouse through a mock transport.

## Proposed architecture

```text
Linux HID transport
        |
Protocol codec and typed commands
        |
Device/profile model
        |
CLI and diagnostic tools
        |
Desktop GUI
```

Recommended boundaries:

- **Transport:** enumeration, interface selection, feature read/write, permissions, reconnect behavior.
- **Codec:** byte-exact encoding/decoding with no UI state.
- **Model:** profiles, DPI stages, button assignments, lighting, macros, and revision-specific capabilities.
- **CLI:** inspection, backups, controlled setting changes, raw packet logging.
- **GUI:** user-friendly editing only after the lower layers are reliable.

HIDAPI is the likely portable transport. Direct Linux `hidraw` ioctls are a reasonable fallback and may expose descriptor details more clearly. Avoid detaching the standard mouse kernel driver unless evidence shows it is necessary.

The A825-family evidence argues for a shared protocol codec plus a per-model capability table. Do not bake generic A825 limits into the Blaze model: the official generic configuration, the GM320 report, and the EvoFox UI disagree on button and lighting counts.

## Milestone 0: evidence capture

Deliverables:

- USB descriptor capture.
- All matching hidraw-node properties.
- Raw HID report descriptors.
- Confirmed PID, interface numbers, usage pages, usage, report IDs, and lengths.
- Notes saved under `docs/device-captures/`.

No writes in this milestone.

## Milestone 1: read-only device probe

Deliverables:

- Enumerate the Blaze without relying on hidraw numbering.
- Reject devices with the right VID/PID but wrong usage collection.
- Print device metadata and feature-report length.
- Optional explicit GET_FEATURE request for report ID `07`.
- Hex and structured logs suitable for committing as test fixtures after sensitive host paths are removed.

## Milestone 2: protocol test harness

Deliverables:

- Mock HID transport.
- Exact-size report buffers derived from descriptors.
- Encoder test for the known `07 18` builder.
- Fixture-only tests for the generic A825 `03` data, `09` transaction, and `00` final frames documented in [Related hardware research](related-hardware-research.md). These tests must not make those writes available to real hardware yet.
- Decoder tests for every observed response.
- Command logging with timestamps and redaction of host device paths.
- Explicit separation of reads and writes in the API.

No GUI in this milestone.

## Milestone 3: one reversible setting

Choose LED brightness or a DPI-stage colour after its packet is proven. Implement:

- Current-value read.
- Validated value range.
- One write.
- Immediate readback.
- Restore operation.
- Power-cycle persistence result.

This milestone proves end-to-end Linux control without risking the button map or macro memory.

## Milestone 4: ordinary configuration

Implement and test incrementally:

1. Lighting mode, colour, brightness, direction, and speed.
2. DPI stages, enable flags, stage colours, and current stage.
3. Polling rate after its numeric encoding is confirmed.
4. Mouse and wheel sensitivity if these are hardware settings.
5. Rapid-fire timing.
6. Profile selection and profile-specific settings.
7. Button assignments, with a rule that at least one physical button remains left click.

Every command needs a documented valid range and a golden packet test.

## Milestone 5: onboard backup and restore

Before macro writes or bulk profile updates, provide:

- A versioned, checksummed backup format owned by this project.
- Raw report/memory snapshots where the protocol permits reads.
- Device VID, PID, revision, descriptor hash, and timestamp in the backup.
- Dry-run restore validation.
- Refusal to restore a backup to a mismatched device revision without an expert override.

Do not copy the vendor's file encryption blindly. A transparent documented format is preferable for the Linux application.

## Milestone 6: macros

Macro support comes after ordinary profile backup/restore because it likely uses larger or indexed writes.

Required work:

- Decode event record width and ordering.
- Identify delays and units.
- Identify keyboard, mouse-button, movement, DPI, and LED event encodings.
- Establish maximum events, groups, and per-profile capacity.
- Determine the role of `MacMd5` and `DAT_VER`.
- Prove whether execution is onboard when connected to another host.

PUBG/gun automation is a separate optional sub-feature.

## Milestone 7: desktop UI

The GUI should consume the tested model API. It should include:

- Clear connected-device identity and revision.
- Read-only view when permissions are insufficient.
- Unsaved-change indication.
- Per-profile editing.
- Before/apply/verify feedback.
- Backup and restore.
- A raw diagnostic export for bug reports.

The original Windows artwork is not required and should not be copied without confirming reuse rights.

## Explicitly deferred

- Firmware update or bootloader access.
- Raw erase/flash operations.
- Background macro execution in software.
- Automatic installation of system-wide permission rules.
- macOS support, until the shared protocol core works on Linux.

## Definition of a successful initial Linux port

The first useful release should:

- Detect the mouse as an ordinary user through a narrowly scoped `udev` rule.
- Read and back up current device configuration.
- Configure DPI, lighting, polling rate, buttons, and profiles.
- Verify each write through readback where possible.
- Preserve ordinary mouse operation on failure.
- Never expose firmware operations.
- Include protocol fixtures and tests that run without hardware.
