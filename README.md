# EvoFox Blaze Linux

A native Linux configuration utility for the EvoFox Blaze gaming mouse.
The goal is a GUI for DPI, lighting, polling rate, buttons, profiles, and macros.
**Working slice:** experimental state reads, polling-setting changes, durable
eight-byte backups, readback, and scoped restore. The polling change/restore
path has been exercised on the attached Blaze. **The full app is not finished:**
lighting, physical CPI values, buttons, profiles, and macros are still missing.

## Working now

Core CLI tools require Linux and Python 3.10+, with no third-party dependencies:

```sh
python3 -m evofox_blaze.probe
python3 -m unittest discover -s tests -v
```

### Desktop controls

```sh
python3 -m evofox_blaze.gui
```

The default window now recreates the original **Button, Macro, Performance, and
Backlight** screens with the reference skin and a resizable layout. Unsupported
settings are visible but disabled; initial values are reference examples, **not
live mouse state**. Press **F1** or right-click for the existing device controls.
The original controls can also be opened directly with `--diagnostics`.
Reference artwork is staged locally in `.work/ui-skin`, not redistributed as
MIT-licensed assets. See [UI setup, controls, and preview exports](docs/ui-development.md)
for preparing it on another checkout and using the supplied mouse illustration.

The native GTK 3 app needs GTK and Python GObject bindings (`gi`); both are
already available on this development host. No host packages were installed.
It starts without contacting the mouse. **Read mouse state…** asks permission
for the fixed staged read. Then select a polling target and use **Apply
polling…**; this requires separate confirmation and saves the original block
before writing. **Restore block backup…** restores a selected `original-state.json`
only if the mouse still matches the saved change. There is no automatic retry
or rollback. Captures/backups go under `$XDG_STATE_HOME/evofox-blaze` or
`~/.local/state/evofox-blaze`.

Each operation checks the exact identity/descriptor and holds a cooperative
device lock. The UI remains responsive and prevents normal window closure while
an operation is in progress. **Written/read back is not measured physical polling
frequency.** Backups cover block `0x0018`, not the whole mouse. Lighting, CPI,
buttons and macros are not exposed as working controls. Core CLI tools do not
require GTK. `--capture <saved-journal>` opens evidence without device access.

### CLI probes and offline inspection

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

Inspect the newly captured state **offline**:

```sh
python3 -m evofox_blaze.state_capture --capture docs/device-captures/30fa-1440-0100-state-read-01/state-read.jsonl
```

Experimental hardware commands require explicit risk opt-ins and new evidence
directories. `state_read` sends zero-data SET_REPORT preparation, not just GETs.
`config_write` can commit a setting. Read their help before using them:

```sh
python3 -m evofox_blaze.state_read --help
python3 -m evofox_blaze.config_write --help
```

Only fixed block `0x0018` is accessible. The CLI also implements already-enabled
DPI-stage **index** changes, tested offline but not yet exercised as a hardware
setting change. It does not set physical CPI values. No arbitrary addresses,
lighting writes, firmware operations, or full-image replay are available.

Preview the recovered brightness field **offline**, using synthetic command
bytes (not a mouse capture or a command approved for sending):

```sh
python3 -m evofox_blaze.lighting --command13 '07 13 81 92 a3 04 b5 c6' --brightness-code 2
```

Only byte 5 changes. Raw codes `0..7` come from the vendor's three-bit mask,
not verified brightness percentages. Original-device-value readback and restore
are still unavailable, so this is not exposed as a hardware setting.

Model the separate outbound storage arithmetic using explicit synthetic inputs:

```sh
python3 -m evofox_blaze.lighting --storage-companion 16 --storage-mode enabled --brightness-code 1
```

This shows why companion-value carries matter: the serialized byte is `20`,
not `10`. The candidate logical byte `0x003f` comes from writer arguments,
not a confirmed device read. No new read region or packet is generated.

Preview the vendor's bulk-read sequence **offline**, without sending packets:

```sh
python3 -m evofox_blaze.read_preview dpi-state --report-length 8
```

This prints SET/GET operations and delays, not a hardware read. Only source-
observed regions can be selected. Only the separate fixed `0x0018` transport
has been exercised on this Blaze; other regions remain offline.

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
That standalone reply is not a configuration backup. A separately approved
fixed read returned `19 3f 32 00 f3 ff 01 00`: stage index candidate `1`, enable
mask `3f`, polling code `1` (500-Hz setting candidate; frequency not measured).

The approved polling test changed only byte 6, `01 → 00`, read back the complete
block, then restored and read back **all original eight bytes**. The
[test](docs/device-captures/30fa-1440-0100-polling-test-01/configuration.jsonl),
[restore](docs/device-captures/30fa-1440-0100-polling-restore-01/configuration.jsonl),
and original-block backups are retained. This proves stored-byte change and
restore, not physical frequency, power-cycle persistence, or a full backup.

## Implementation checkpoint

- **UI milestone complete — user-approved on 2026-10-25:** the four reference-style
  GTK screens (Button, Macro, Performance, Backlight) are the accepted visual
  baseline. Unsupported hardware features remain disabled. See the
  [UI progress checkpoint](docs/ui-development.md#progress-checkpoint--2026-10-25).
- **Session continuity:** root [AGENTS.md](AGENTS.md) directs future sessions to
  the [next-session handoff](docs/ui-development.md#next-session-handoff), including
  the stopping point, code locations, recovery commands and hardware-consent limits.
- Implemented descriptor probing, standalone GET, fixed state reads, constrained
  DPI-stage/polling writes, durable scoped backup/restore, strict journal
  inspectors, and GTK polling controls. Core tools have no third-party Python
  dependencies; feature ioctls currently target Linux x86-64.
- Preserved sanitized hardware captures and static-analysis fixtures. REA/Ghidra
  investigations are reproducible through checked-in query plans; temporary
  tool installations, full analysis bundles, and extracted vendor files are not committed.
- **159 tests pass locally on Python 3.10.12**, including all four native GTK
  screens, scaled hit targets, window shrinking, offline exports, disabled controls,
  polling drafts and evidence refresh/error clearing with no device access. The optional window
  smoke test skips where GTK or a display is absent. Native Linux-header ioctl
  constants, fixture/Evidence identities, capture integrity, and documentation
  links were checked. CI is configured for Python 3.10 and 3.13; remote CI has
  not been run during this session.
- Hardware coverage: descriptor capture, one standalone GET, five fixed state
  reads, and two explicitly approved settings commits (polling change + exact
  restore). No unapproved scans, resets, driver detaches, permission changes,
  or input-event reads occurred.

## Direction and next tasks

1. **Done:** capture USB/HID descriptors; implement and test the sysfs probe.
2. **Done:** [REA + Ghidra](docs/reverse-engineering.md) recovered the builder,
   writer, bulk reader, and its preparation helper. Corrected the old reader
   offset and added offline packet-layout tests. The bulk reader uses SET_REPORT
   and is not a harmless GET. Only one source/capture-matched fixed block is
   exposed through a separate risk-acknowledged transport.
3. **Done:** trace the three reader callers and test their offline packet
   sequences. Source-observed reads are eight bytes at `0x0018` and four eight-byte
   comparison blocks starting at `0x0fa0`. This is not complete configuration
   backup support. Host-code intent does not establish preparation side effects.
4. **Done:** implement and exercise one opt-in GET_FEATURE with identity checks,
   descriptor-sized buffers, and durable request/response logs. Traced its static
   consumers and added an offline decoder with explicit unknown fields.
5. **Done for polling:** independently corroborate the read sequence, capture
   current bytes, back up the original block, change one field, read back, and
   explicitly restore/verify. Desktop polling controls now use that backend.
6. **Next:** exercise the DPI-stage index operation with separate consent;
   recover and validate physical CPI values and lighting readback before enabling
   those settings. Brightness's candidate byte `0x003f` remains inaccessible.
7. Expand owned-field backups, then buttons, profiles, and macros. A full-device
   backup and physical behavior/persistence tests are still missing.

Do not execute the Windows software, replay generic A825 transactions, detach
the mouse driver, change system permissions, or issue firmware/bootloader/
erase/reset commands. Do not treat a partial block backup as a full-device restore.

## References

- [Protocol evidence and unresolved mappings](docs/hid-protocol.md)
- [REA workflow and analysis results](docs/reverse-engineering.md)
- [Vendor artifacts and configuration search seeds](docs/vendor-reference.md)
- [Device captures and reproduction](docs/device-captures/README.md)

Observed descriptor facts, static application behavior, and family-derived
hypotheses are labeled separately. None alone establishes onboard persistence.
