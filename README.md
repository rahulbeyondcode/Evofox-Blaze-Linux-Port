# EvoFox Blaze Linux

A native Linux configuration utility for the EvoFox Blaze gaming mouse.
The goal is a GUI for DPI, lighting, polling rate, buttons, profiles, and macros.
**Working slice:** experimental state reads, polling-setting changes, durable
eight-byte backups, readback, scoped restore, native built-in button assignments,
and experimental on-device keyboard chords.
Polling change/restore was exercised; native side-button Back/Forward was written,
read back, and user-tested after physical replug. **The full app is not finished:**
custom sequences/macros, the physical rapid-fire button's assignment,
lighting, physical CPI values and profiles are still missing.

See the [feature-by-feature offline audit](docs/feature-audit.md) for tested
workflows, reproduced UI fixes, and remaining nonfunctional/reference controls.
Passing tests do **not** mean every visible feature is implemented or hardware-validated.

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
settings remain disabled except for explicitly requested no-op assignment-menu
placeholders. Button assignments recover the **latest verified saved journal**
on startup, marked **saved, not live**. Click **Read mouse assignments…** on the
Button page to explicitly read the current native actions and supported keyboard
shortcuts. Without saved evidence, values remain unknown rather than invented.
Other unimplemented settings still show reference examples, **not live mouse
state**. Press **F1** for the optional device controls. The right-click
context menu has been removed.
The original controls can also be opened directly with `--diagnostics`.
Reference artwork is staged locally in `.work/ui-skin`, not redistributed as
MIT-licensed assets. See [UI setup, controls, and preview exports](docs/ui-development.md)
for preparing it on another checkout. The supplied `MouseImage.png` illustration
is now the default; `python3 -m evofox_blaze.gui --reference-mouse` uses the
preserved original mouse artwork instead. Neither original image is overwritten.
Drag the top header or center logo to move the window; drag any edge or corner
to resize. Routine assignment edits keep a generic footer; operation progress and
errors still appear there.
Mouse operations now show a dark, Blaze-styled loading overlay. It blocks the
underlying controls, keyboard shortcuts and normal window closure until the
operation and saved-result checks finish, then disappears automatically. Recorder
Save is draft-only and does not show this loading screen. Routine hover tooltips
are removed; unavailable items simply say **Not implemented**.
One line beneath the spinner now shows the actual phase—reading, backing up,
writing, verifying or sending activation—with cycling `.`, `..`, `...` dots.
The mouse may respond before full readback finishes; the overlay waits for all
verification rather than claiming completion early.

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
custom sequences and macros cannot yet be written to the mouse. Keyboard chords
use the separate experimental backend described below. Core CLI tools do not
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

The state/polling backend still accesses only `0x0018`. A separate native-button
backend accesses only `0x0008`. The CLI also implements already-enabled
DPI-stage **index** changes, tested offline but not yet exercised as a hardware
setting change. It does not set physical CPI values. No arbitrary addresses,
lighting writes, firmware operations, or full-image replay are available.

### Native button remapping — 2026-10-27

1. Launch `python3 -m evofox_blaze.gui`.
2. Click an assignment directly on **Button**. No F1, prerequisite read,
   assignment dialog or **Keep draft** button is needed.
3. Choose a built-in action from the dropdown or its right-hand **Extend** menu.
   Selection changes only the in-app assignment. An asterisk marks pending edits;
   **Cancel** discards them. Returning to the starting option removes that row's
   change; Apply disables when no changed rows remain, even after trying several
   other options, once a real read or verified Apply establishes a baseline.
   At startup, no board read is performed: the latest verified saved assignments
   are recovered from the app's evidence directory. A later failed/incomplete
   operation prevents stale fallback. Without history, choosing Left/Right then
   Apply still works even if they match the old artwork defaults.
   **Read mouse assignments…** on the Button page explicitly reads the native
   table and supported shortcut records, so chord names appear instead of just
   Stored shortcut. This separately confirmed staged read makes no settings commit;
   unknown allocation layouts are refused. Button 8's native assignment remains
   outside the supported scope and is not guessed from its descriptor.
4. Click **Apply** to authorize the selected programming operation directly,
   without another confirmation dialog. It validates the device, reads the real
   table, backs it up, writes only the selections and checks complete readback.
   Progress/errors stay in the main window. Apply disables after verified success;
   failure retains the selection without retrying automatically.
5. After completion, physically unplug for about ten seconds and reconnect.
   The user confirmed Back/Forward working after this step; immediate activation
   is not established. No automatic reset/finalize command is sent.

All eight rows open the same dropdown. Seven vendor-UI assignment rows support
programming through native slots `1..6,8`. The eighth row (physical rapid-fire,
slot `9`) is menu preview only: it lies outside this backed-up block. Actions
implemented in the menu are Left/Middle/Right, Back/Forward,
Double Click, Rapid Fire, DPI Loop/+/− and LED Loop. **Only the side-button
Back/Forward change has behavioral validation**; other targets are source-derived.
At least one standard button must remain Left Click.

Button 8 is restricted by current backend coverage, not proven hard-wired to
Rapid Fire. Its initial label is a reference example. Static analysis identifies
a candidate in the next mixed-settings block, but that region still needs its
own explicitly authorized read/backup/write/restore work before remapping is safe.

**Extend**, **Media**, **Macro**, and **Profile Selection** have native cascading
submenus, opened by hover/click or keyboard navigation. Show desktop, every Media
action, the hardcoded Office/Game 1/Game 2/Media profile entries, and
**No macros found** are currently clickable placeholders: they only close the
menu and never produce an assignment or device write. Opening the app or menu
performs **no device access**; the original table is read only when Apply is
clicked (or through the optional diagnostic read).

**Shortcut** now opens a Blaze-styled recorder rather than a placeholder:

1. Start with three visible key boxes. Use **+ Add box** for up to six, or **×**
   to delete unused boxes (at least one remains).
2. Click **Record** or a particular box. **Press and release one key at a time.**
   Each release fills the box and activates the next empty box.
3. **Save** stages it on the selected button in the app, marked with `*`.
   Cancel/close discards the editor's unsaved recording. Reopening Shortcut shows
   that button's existing draft. The main **Cancel** discards all button drafts.

For **Ctrl+Alt+Down**: tap Ctrl and release it; tap Alt and release it; then tap
Down and release it. **Do not hold them together during entry**. The preview shows
the combined shortcut the mouse will send. Every box must be filled and the chord
must contain distinct modifiers and exactly one regular key before Save enables.
There is no accordion, all-keys dropdown or modifier-checkbox panel. Click a filled
box to replace its key; Re-record clears the editor boxes, not the existing button
assignment. Focus loss/Stop/timeout stops capture and keeps completed boxes; click
a box or Record to resume. No global grab or desktop-shortcut changes are used.

If Pop!_OS opens its launcher when you tap the Windows key, click the recorder's
**Windows / Super** button instead. It explicitly inserts **left Windows/Super**
into the armed box or first empty box without pressing a desktop shortcut. To
replace a filled box, click that box first. After focus loss/Stop, this insertion
does not restart recording; click the next box or Record to continue.

Recording is opt-in, only inside the focused editor, with no global hooks or
disk logging. Focus loss, Stop, close and a 20-second timeout stop recording.
It supports one standard key with optional Ctrl/Shift/Alt/Super modifiers, not
multi-step macros. System-reserved shortcuts may be intercepted by the desktop.

4. Close the recorder with **Save**, then click the main **Apply**. Save never
   contacts the mouse; Apply explicitly authorizes a fresh-read/backup/write/full
   readback transaction. Mixed native/shortcut drafts use one combined transaction,
   never just the native subset. After verified success Apply disables. Returning
   to the verified starting chord also removes a pending change.
5. Wait for completion, then unplug for about ten seconds and reconnect. Test the
   physical mouse button in the application where you want the combination to work.

**Experimental:** only the inspected allocation layout and seven supported rows
are accepted. Unknown/shared records are refused, not relocated. Original records,
auxiliary data and allocation metadata remain untouched; new chords use distinct
backed-up tail slots. F13 was written/read back, and the user reported the test
opening desktop Settings, consistent with the desktop's Tools binding. This is
not a raw input capture or validation of every chord, modifier release or persistence.
On 2026-11-02 the user reported **Ctrl+Alt+Down working** in the prompted mouse-button
workspace-switching test. This is a behavior report, not a raw event capture;
replug persistence and modifier release were not explicitly confirmed separately.
Desktop-reserved keys may open another app or switch workspace. Drafts do not
survive app exit.

This is on-device programming, not an evdev/uinput service. It does **not** yet
program custom sequences or macros. Existing original shortcut
records remain untouched. Native-only changes replace just their button-table link
with a built-in assignment. The original `2e` links are retained in the exact-block
backup. **F1 → Restore button backup…** is a separate confirmed operation that
refuses intervening edits. Native-button restore has offline coverage, not a
live restore test. **F1 → Restore shortcut backup…** separately confirms restoration
from a `shortcut-backup.json`, refusing intervening edits. Shortcut restore has
offline coverage only; no live restore has been authorized or executed. Backups
are partial, not a complete backup of existing macros.

Saved evidence can be inspected without contacting the mouse:

```sh
python3 -m evofox_blaze.button_capture --capture docs/device-captures/30fa-1440-0100-button-read-01/button-read.jsonl
python3 -m evofox_blaze.button_config_capture --capture docs/device-captures/30fa-1440-0100-button-remap-01/button-configuration.jsonl
python3 -m evofox_blaze.button_write --help
```

The [button checkpoint](docs/reverse-engineering.md#native-button-checkpoint--2026-10-27)
records the precise scope, current stored table and remaining shortcut work.
Current validation: **459 tests passed** on a private authenticated Xvfb display, including native cascading-menu and
direct-Apply checks, GTK rendering, fault injection, exact backup/restore
simulation, combined shortcut Apply, net-change baselines and immutable evidence
checks. No live mouse operation was performed for the latest GUI integration.
Native Back/Forward has the separate user-reported after-replug validation above.

Run the full suite without desktop popups using
`python3 -m tools.run_virtual_tests --xvfb /path/to/trusted/Xvfb`.
See [headless testing](docs/ui-development.md#tests-and-visual-review) for the local
executable path and a no-display fallback that skips GUI coverage.

### Experimental immediate activation

To try the built-in reload candidate after a new Apply:

```sh
python3 -m evofox_blaze.gui --experimental-activation
```

**Off by default; broader firmware effects remain experimental.** The user reports
the prompted Ctrl+A assignment working immediately without unplug/replug after
opt-in GUI Apply. This is a user behavior report, not raw input or whole-device
validation. Startup, menus, recording and Save
stay offline. The Button page shows an armed warning. Apply authorizes the selected
native/shortcut change **plus** the fixed two-report activation candidate after
durable backup and matching readback, using the same locked handle. Performance's
polling confirmation also explains the extra scope. This may activate **all stored
settings**, not only the edited button; there is no whole-device backup.

On success the UI says **activation sequence sent**, not behavior verified. Test
the changed assignment before reconnecting. Any failure stops without retry,
cleanup or automatic rollback; drafts and backup remain available for review.
No-change results send no activation. Reads, restores, DPI-stage CLI operations
and the old F13 field-test scope never acquire activation implicitly.

The vendor sequence is independently corroborated by a related-product capture,
and now has the user-reported no-replug result above. No agent-side live activation
test or independent inspection of that GUI transaction was performed.
Normal startup without the flag keeps the previous Apply behavior and reconnect
guidance. `python3 -m evofox_blaze.activation --preview` remains a safe offline
preview. See the [integrated activation checkpoint](docs/reverse-engineering.md#opt-in-immediate-activation-integration--2026-11-02).

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
from that preview has been exercised on this Blaze; its other regions remain
offline. The separate native-button backend has also exercised fixed `0x0008`.

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
- **159 tests passed at the 2026-10-25 checkpoint on Python 3.10.12**, including all four native GTK
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
7. **Native button milestone:** fixed-table built-in assignments and GUI drafts
    implemented; side Back/Forward confirmed after replug. Experimental chord
     backup/encoding/Apply/restore is implemented; Ctrl+Alt+Down now has a successful
     user behavior report. **Current priority:** validate immediate activation
     without replug before connecting the separate candidate sequence to Apply.
     Confirm modifier-release details and investigate physical rapid-fire slot coverage next, then
   broader profiles/macros. A full-device backup is still missing.

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
