# EvoFox Blaze Linux

A native Linux configuration utility for the EvoFox Blaze gaming mouse.
The goal is a GUI for DPI, lighting, polling rate, buttons, profiles, and macros.
The current implementation has descriptor and opt-in feature-read probes,
plus offline packet tools. It is not yet a configuration tool.

## Working now

Requires Linux and Python 3.10+, with no Python dependencies:

```sh
python3 -m evofox_blaze.probe
python3 -m unittest discover -s tests -v
```

Save a new sanitized snapshot (the destination must not exist):

```sh
python3 -m evofox_blaze.probe --capture .work/captures/initial
```

The sysfs probe never opens `/dev/hidraw*`, reads input events,
or sends feature reports. It selects USB IDs, examines **all** collections on
each node, and calculates report sizes from descriptors instead of guessing.
Local output includes session-specific device paths; saved captures omit them.

Perform **one GET_FEATURE 07** using a previously saved descriptor baseline
(currently Linux x86-64 only; destination must be new):

```sh
python3 -m evofox_blaze.feature_read --read-feature \
  --baseline docs/device-captures/2026-10-23-30fa-1440-0100/probe.json \
  --capture .work/captures/get-feature-01
```

This opens the selected node read-only, validates its kernel identity and report
descriptor against the baseline, then sends one GET_FEATURE. It logs intent
before the ioctl and records the raw result. There is no SET_REPORT, automatic
retry, input-event reading, or permission change. If multiple devices match,
select a session-specific path with `--device /dev/hidrawN`.

Inspect an existing read **offline**, without contacting the mouse:

```sh
python3 -m evofox_blaze.status --capture docs/device-captures/30fa-1440-0100-get-feature-01/feature-read.jsonl
```

The vendor-code profile mask gives candidate profile index `0` for this
capture. It is not hardware-validated. Unknown bits/bytes are preserved;
no DPI, polling rate, lighting, or storage capacity is guessed. Saved-evidence
inputs must be regular files, not device nodes, streams, or symlinks.

Preview the vendor's bulk-read sequence **offline**, without sending packets:

```sh
python3 -m evofox_blaze.read_preview dpi-state --report-length 8
```

This prints SET/GET operations and delays, not a hardware read. Only source-
observed regions can be selected; preparation effects remain unverified.

## Current evidence

The [2026-10-23 capture](docs/device-captures/2026-10-23-30fa-1440-0100/probe.json)
records a connected `30fa:1440`, revision `0100`, with two USB HID interfaces:

| Interface | Collections relevant to this port | Reports, including ID byte |
|---|---|---|
| 0 | Mouse (`0001/0002`) | Input `01`: 7 bytes |
| 1 | `ff00/0001` and `ff01/0001`, alongside keyboard/consumer/system collections | Input `06`: 3 bytes; feature `07`: **8 bytes** |

`ff00` and `ff01` share one Linux hidraw node. They are not separate Linux
interfaces. Existing node permissions allow access on this host; no permission
rules were installed. A [standalone GET_FEATURE](docs/device-captures/30fa-1440-0100-get-feature-01/feature-read.jsonl)
returned `07 00 58 09 1f 00 23 7b` without a preceding SET_REPORT in our work.
Only a statically derived profile candidate is interpreted; it is not a
configuration backup. No settings have been written by these tools.

## Initial implementation checkpoint

- Implemented the sysfs descriptor probe, opt-in GET-only transport, offline
  command-18 codec/read preview, and saved-status inspector. Runtime Python
  tools have no third-party dependencies; feature ioctls currently target Linux x86-64.
- Preserved sanitized hardware captures and static-analysis fixtures. REA/Ghidra
  investigations are reproducible through checked-in query plans; temporary
  tool installations, full analysis bundles, and extracted vendor files are not committed.
- **64 offline tests pass locally on Python 3.10.12.** Native Linux-header ioctl
  constants, fixture/Evidence identities, capture integrity, and documentation
  links were checked. CI is configured for Python 3.10 and 3.13; remote CI has
  not been run during this session.
- Hardware validation is limited to descriptor inspection and **one** successful
  standalone GET_FEATURE. There is no setting-write API, complete configuration
  backup/restore, persistence validation, macro implementation, or GUI yet.

## Direction and next tasks

1. **Done:** capture USB/HID descriptors; implement and test the sysfs probe.
2. **Done:** [REA + Ghidra](docs/reverse-engineering.md) recovered the builder,
   writer, bulk reader, and its preparation helper. Corrected the old reader
   offset and added offline packet-layout tests. The bulk reader uses SET_REPORT
   and has unverified side effects; it is not exposed as a hardware operation.
3. **Done:** trace the three reader callers and test their offline packet
   sequences. Source-observed reads are eight bytes at `0x0018` and four eight-byte
   comparison blocks starting at `0x0fa0`. This is not complete configuration
   backup support. Host-code intent does not establish preparation side effects.
4. **Done:** implement and exercise one opt-in GET_FEATURE with identity checks,
   descriptor-sized buffers, and durable request/response logs. Traced its static
   consumers and added an offline decoder with explicit unknown fields. Bulk read
   preparation remains disabled; no generic memory reads are available.
5. **Next:** recover one lighting field and its original-value readback;
   implement a tested codec, original-value backup, explicit write confirmation,
   readback, and restore before trying it on hardware.
6. Expand verified settings, backup/restore, then macros and the GUI. Keep
   transport, packet encoding, and the UI separate; test packets without hardware.

Do not execute the Windows software, replay generic A825 transactions, detach
the mouse driver, change system permissions, or issue firmware/bootloader/
erase/reset commands. Hardware writes are not implemented.

## References

- [Protocol evidence and unresolved mappings](docs/hid-protocol.md)
- [REA workflow and analysis results](docs/reverse-engineering.md)
- [Vendor artifacts and configuration search seeds](docs/vendor-reference.md)
- [Device captures and reproduction](docs/device-captures/README.md)

Observed descriptor facts, static application behavior, and family-derived
hypotheses are labeled separately. None alone establishes onboard persistence.
