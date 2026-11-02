# Static analysis with REA

## Scope

Recover and bound the EvoFox application's setting and readback behavior.
Standalone GET, fixed `0x0018` state and separate `0x0008` button transports are
implemented; polling write/readback/restore and native side Back/Forward programming
have been exercised. Generic memory access and lighting
writes remain unavailable. Start with the functions and unresolved questions in
[hid-protocol.md](hid-protocol.md), not a fresh whole-installer investigation.
REA orchestrates Ghidra; it does not itself validate hardware commands.

Use the **published package's** advertised schemas. Repository `main` can have
different requirements and capabilities even when its version string matches.
The installed 6.7.0 package accepts this host's Node 24.18.0; a Node upgrade
was not needed. Ghidra's scoped doctor check passed with the versions below.

## Local toolchain

Tools were acquired under `/tmp/opencode/evofox-re-tools/`, not installed
system-wide. No agent MCP registrations or skill files were changed.
This temporary directory is disposable; it is not a project dependency.

| Tool | Version / source |
|---|---|
| REA | `rea-agents@6.7.0` from the npm registry |
| Ghidra | [12.1.4 official release](https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.1.4_build) |
| JDK | [Temurin 21.0.13+9](https://github.com/adoptium/temurin21-binaries/releases/tag/jdk-21.0.13%2B9) |
| innoextract | [1.9 Linux release](https://github.com/dscharrer/innoextract/releases/tag/1.9), `bin/amd64/innoextract` |

Archive SHA-256 values:

```text
ghidra_12.1.4_PUBLIC_20260921.zip
ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db
OpenJDK21U-jdk_x64_linux_hotspot_21.0.13_9.tar.gz
d7f5d5cf865a2902b70ff549b97586a7d3f234e016f041ab447ea740c7d66d1c
innoextract-1.9-linux.tar.xz
008efe5011476ccc4aae17c3e22038b5a1bc5c7aad2b9d4d869537bf3874d21f
```

Ghidra and JDK archives matched their release metadata. The innoextract hash
records the downloaded artifact; its detached signature was not verified.
The REA npm installation retains `package-lock.json` outside the repository.

## Reproduce

After downloading/verifying and extracting the tools at the location above:

```sh
export RE_TOOLS=/tmp/opencode/evofox-re-tools
npm install --prefix "$RE_TOOLS/rea" --ignore-scripts --omit=optional --no-audit --no-fund rea-agents@6.7.0
export JAVA_HOME="$RE_TOOLS/jdk-21.0.13+9"
export GHIDRA_INSTALL_DIR="$RE_TOOLS/ghidra_12.1.4_PUBLIC"
export TMPDIR="$RE_TOOLS"
export REA_GHIDRA_STARTUP_TIMEOUT_MS=600000
"$RE_TOOLS/rea/node_modules/.bin/rea" doctor --provider ghidra --json
"$RE_TOOLS/innoextract-1.9-linux/bin/amd64/innoextract" --output-dir "$RE_TOOLS/payload" evofox-blaze.exe
node tools/analyze_vendor.mjs "$RE_TOOLS/rea" "$RE_TOOLS/payload/app/Gaming Mouse 3.0.exe" .work/analysis/readback-01
```

The analysis script verifies the application SHA-256, discovers the installed
tool schemas, and uses one private stdio MCP session for four function dossiers
and four targeted xref queries. It exports Evidence and a query snapshot before
closing. It refuses an existing output directory and rechecks the source hash.
Snapshots cache exact observations; they are not saved Ghidra databases. An
optional fourth argument imports an earlier compatible `snapshot.json`; new
queries still require a fresh Ghidra import after the previous session closes.
A fifth argument selects a bounded JSON plan containing `procedures` and
`xrefs` address arrays, with optional `pseudocode` and `instructions` arrays
for focused queries without oversized function dossiers. Each array is limited
to 32 unique lowercase hexadecimal addresses; `-` skips the optional snapshot.
The checked-in caller plan avoids reissuing the initial builder queries:

```sh
node tools/analyze_vendor.mjs "$RE_TOOLS/rea" "$RE_TOOLS/payload/app/Gaming Mouse 3.0.exe" .work/analysis/read-callers-01 .work/analysis/readback-02/snapshot.json tools/analysis-plans/read-callers.json
```

The brightness follow-up uses the same driver and toolchain:

```sh
node tools/analyze_vendor.mjs "$RE_TOOLS/rea" "$RE_TOOLS/payload/app/Gaming Mouse 3.0.exe" .work/analysis/lighting-brightness-01 .work/analysis/status-consumers-01/snapshot.json tools/analysis-plans/lighting-brightness.json
```

To check the outbound storage arithmetic and file-profile context:

```sh
node tools/analyze_vendor.mjs "$RE_TOOLS/rea" "$RE_TOOLS/payload/app/Gaming Mouse 3.0.exe" .work/analysis/lighting-storage-01 .work/analysis/lighting-brightness-01/snapshot.json tools/analysis-plans/lighting-storage.json
```

All raw results stay in ignored `.work/analysis/`. Commit only focused findings,
evidence IDs, source addresses, and sanitized fixtures—not vendor resources,
tool installations, host configuration diagnostics, or unreviewed decompiler output.

## Result ledger

The initial builder/readback runs completed; Evidence and snapshots were exported
and both sessions closed. The second imported the first snapshot and added the
correct reader and preparation dossiers. The cold imports took about 229 and
244 seconds; cached dossiers returned without repeating their analysis.

Results:

- `0x413a10` writes; the old reader label was wrong.
- `0x413ac0` reads through `0x413b90` preparation and SET_REPORT requests.
- Five GetFeature / 23 SetFeature thunk references were observed.
- The caller plan completed: six new dossiers and four xref queries, exported
  with the inherited Evidence and snapshot, then closed normally. The bundle
  in `.work/analysis/read-callers-01/` retains 21 observations.
- Reads are fixed to `0x0018` (8 bytes) and `0x0fa0` through `0x0fb8`
  (four 8-byte chunks), not a complete configuration-backup path.
- `0x44cc10` also performs a command `14` write. Two helpers have no observed
  incoming xrefs; existence is not proof of runtime reachability.

The [static fixture](../tests/fixtures/vendor-read-observations.json) retains
the caller Evidence IDs and tested read arguments. The DPI_LEVEL-to-selector
path, preparation limits, and caller writes are in [hid-protocol.md](hid-protocol.md).

The `tools/analysis-plans/status-consumers.json` plan completed in
`.work/analysis/status-consumers-01/`: three pseudocode queries, three xrefs,
and 22 instruction inspections, with Evidence/snapshot exported and the session
closed. Its bundle retains 48 observations including inherited records. This
establishes the byte-6-to-`CurConfig` mapping and finds no later use of the
initializers' `0x07f8`/`0x0ff8` locals in recovered pseudocode. The
[consumer fixture](../tests/fixtures/status-consumer-observations.json) preserves
the new Evidence IDs. No new device request accompanied this analysis.

The `lighting-brightness.json` plan completed in
`.work/analysis/lighting-brightness-01/`: three xrefs, three pseudocode queries,
and 18 instruction inspections, with 71 total Evidence records including
inherited observations. Evidence/snapshot exports succeeded and the session
closed. The cold import took about 230 seconds. Key results:

- Command builder `0x432030` writes `LED_BRIGHT & 7` to command `13`, byte 5.
- Its four direct call sites are `0x44cd2e`, `0x44f90c`, `0x44f990`, and
  `0x44f9f2`. No new incoming bulk-reader references were found.
- `0x44cc10` uses its read only for the DPI selector, then sends command `14`
  **and command `13`**; brightness comes from cached state, not that read.
- `0x43d970` updates the brightness global from a UI-control result; this does
  not establish physical brightness units or readback semantics.

The [brightness fixture](../tests/fixtures/lighting-brightness-observations.json)
retains focused Evidence IDs, verified instruction bytes, and synthetic frame
examples. The app hash, INI key strings, and focused bytes also matched an
independent objdump check. No vendor binary execution or device request occurred.

The `lighting-storage.json` plan completed in
`.work/analysis/lighting-storage-01/`: three xrefs, three pseudocode queries,
and 27 instruction inspections. Its exported bundle contains 98 records
including inherited evidence; snapshot export and session close succeeded.
The cold import took about 201 seconds. Two serializer layouts independently
produce the same logical writer byte, `0x003f`: base `0x20` plus index 31,
or base `0x38` plus index 7. Both add the cached `LED_USER6_B` companion to
the shifted brightness value, with no nibble mask on that companion. The file
loader constructs `Config` sections from its profile argument; this does not
establish firmware profile banks. The
[storage fixture](../tests/fixtures/lighting-storage-observations.json) retains
Evidence IDs, base arithmetic, exact companion/guard semantics, and synthetic
examples. No read region was expanded and no device interaction occurred.

Evidence IDs and packet details are in [hid-protocol.md](hid-protocol.md).
The initial raw results are in `.work/analysis/readback-01/` and `readback-02/`; the second
bundle retains 11 observations. These local files are deliberately not committed.
Static packet reconstruction does not authorize sending the reconstructed bytes.

## Protocol/backend checkpoint — 2026-10-25

This checkpoint covers this session's protocol/backend work only. The separate
[UI-development record](ui-development.md) owns the visual/UI milestone; its
changes are not part of this checkpoint.

| Capability | Implementation and evidence status |
|---|---|
| Identify the mouse | Request-time USB identity, revision, interface and descriptor matching; not automatic discovery at GUI startup |
| Standalone GET | One completed capture; profile interpretation remains a static candidate |
| Fixed state read | Exact `0x0018`/8-byte sequence exercised; no arbitrary-address read API |
| Polling change / backup / restore | Temporary code `01 → 00`, complete readback, then exact eight-byte restore/readback succeeded |
| DPI-stage index change | Constrained CLI implementation and offline tests; no hardware stage-change test yet; physical CPI values remain unread |
| Lighting | Static brightness mapping and arithmetic models only; no original-value hardware readback or lighting write |
| Click/button identification | Not implemented; no input-event listener or device-specific live button attribution |
| Full-device backup, button remapping, hardware profiles, macros | Not implemented |

The last verified end state of this session was the restored block
`19 3f 32 00 f3 ff 01 00`. It is a recorded observation, not a guarantee of
the mouse's current state after later sessions. Actual polling frequency,
runtime activation and power-cycle persistence were not measured. The app is
not feature-complete.

All six static-analysis sessions finished and closed normally. Their essential
findings and Evidence IDs are retained in the protocol document and five static
field/consumer fixtures; the full local bundles are intentionally excluded from Git. Offline
tests now cover descriptor decoding, selection, packet sequencing, GET-only
validation/logging, saved-evidence handling, status masks, and offline brightness
field replacement and storage arithmetic. With transaction, backup, journal,
subprocess-boundary and GUI tests, **147 tests passed at this session's backend
checkpoint**. This is a historical validation result, not the current total
after the separate UI session. Optional native GTK smoke tests skip without GTK
or a display. No GUI test performs device enumeration or a feature request.

Brightness now has a concrete host mapping: `LED_BRIGHT` at `0x671d78` is
masked with `07` into command `13`, byte 5. The offline field codec and tests
exercise only synthetic outbound frames; no context or original device value
is derived from shipped defaults. The completed bounded query plan is checked in
as `tools/analysis-plans/lighting-brightness.json`.

The storage follow-up identifies a candidate logical byte, not a readback API.
The arithmetic model preserves native low-byte addition and tests carries,
signed companion values, and the disabled host guard. It intentionally does not
decode arbitrary bytes as brightness or expose a new command-18 read range.

The fixed-state readback gate has now been exercised: independent USB evidence
was audited, the user approved one fixed read, and then separately approved a
temporary polling-code change and exact restore. The five fixed reads and two
settings commits are preserved in versioned captures. No phase `09` is added
to a read, no generic address is exposed, and no unknown activation/reset
command was tried. `state_read`, `config_write`, and strict offline inspectors
implement that narrow path. Original-block backups are durable before setting
data is sent; restore refuses intervening edits and failures never cause blind
retry or rollback. Details and counts are in [hid-protocol.md](hid-protocol.md).

Continue with separately approved DPI-stage testing, CPI-value recovery and
lighting readback. Brightness still has no proven original-value readback path.
Profile index `0` remains a static candidate, not a controlled hardware
confirmation. Do not treat unused initializer locals as device addresses.

A device-specific, opt-in **read-only button tester** is also pending. It must
first establish which physical controls produce distinct Linux/HID events;
DPI, lighting and rapid-fire buttons cannot be assumed to do so. UI button
labels/highlights are not evidence of physical-button monitoring. Do not add
input grabs, event injection or permission changes implicitly.

The approvals used for the recorded read and polling roundtrip were consumed
by those exact operations. Future live reads, setting changes, restores or
input monitoring require their own explicit authorization. No device operation
is needed to reproduce offline journal inspection or tests.

The desktop entry point is `python3 -m evofox_blaze.gui`. Startup and saved-file
inspection perform no device access. Separately confirmed state reads, polling
changes and scoped restore run in a worker/subprocess boundary with exclusive
new evidence directories. The display validates all three journal types and
does not equate readback with physical behavior. GTK/PyGObject remain optional
for CLI use; missing settings are not presented as working controls. No input
service, evdev/uinput permissions, driver changes or Windows execution were added.

The independently reviewed ANKO capture and pinned related project are described
in [vendor-reference.md](vendor-reference.md#independent-capture-and-implementation-review).
`python3 -m tools.audit_public_capture --capture <file>` checks the exact source
hash, USB descriptor envelope, 26-operation read excerpt, and preceding committed
bytes without running any downloaded code or touching hardware. The related
project's extra read-commit frame was explicitly rejected, not adopted.

## Resuming without this conversation

Start with [AGENTS.md](../AGENTS.md), then the checkpoint above. The source,
test fixtures and sanitized captures—not chat history—are the continuation
record. Pending backend work is explicitly distinguished from the separately
approved UI milestone and from hardware-tested behavior.

The initial implementation commit `c93d7ad` alone does **not** contain the later
polling/backend, accepted-UI and handoff work. Use a revision containing this
complete checkpoint, including source, docs, fixtures, sanitized captures and
reference inputs. Check `git status` for subsequent uncommitted or untracked
work before transferring a checkout, and retain or back it up explicitly. Do
not overwrite another session's changes while assembling that handoff.

Temporary tool installations and ignored analysis/UI staging files are not a
portable backup. Their reconstruction instructions are documented; essential
protocol findings and evidence identifiers have been extracted into repository
documents and fixtures. No hardware operation is needed to restore this context.

Handoff verification: **159 offline tests passed**, including the other session's
UI tests, with no new device operations. The earlier 147-test backend checkpoint
is intentionally retained as historical progress. Handoff links, backend entry
points and recorded hardware evidence were checked for presence.

## Native button checkpoint — 2026-10-27

**Newer than the protocol/backend checkpoint above.** User selected on-device
mapping, not a Linux input service. Implemented fixed `0x0008`/8-byte reads,
native built-in assignment plans, scoped durable backup/write/readback and
separately confirmed exact restore. No arbitrary-address API, extension-table
writer, runtime activation/reset, automatic retry, rollback or input monitor.

The separately approved first button read returned `21 22 23 2e 2e 35 00 26`.
The user described the old side bindings as Ctrl+Windows+Left/Right and explicitly
authorized changing them. One subsequent commit changed native slot 4 to Back
and slot 5 to Forward: `21 22 23 24 25 35 00 26`. Fresh read, original-table
backup and full readback succeeded. The user then selected **Works after replug**
when testing the side buttons. Original captures and the later separate report
are in [device evidence](device-captures/README.md#native-button-checkpoint--2026-10-27).
The mappings were intentionally left in place; **no native restore was executed**.

This milestone used **three button reads and one commit: 64 SET / 24 GET**.
No captured input events or automatic reconnect/reset occurred. These approvals
are consumed, including the first read; do not repeat the write because the chat
was interrupted. Last recorded button block is the changed table above, not a
guarantee about later state. The earlier restored `0x0018` block is separate.

### Static scope and reconstruction

- `buttons.json` completed in `.work/analysis/buttons-02/`: five xrefs, four
  pseudocode queries, seven instruction inspections, Evidence/snapshot exported,
  session closed. The first attempt failed before import because Python's ZIP
  extraction omitted executable bits; restoring the archive-declared bits in
  the temporary Ghidra extraction fixed it. No vendor application was executed.
- Serializer `0x422070`, writer call `0x423626`, advances base zero by eight,
  then sends eight button bytes. It indexes native slots through `K*_MAP` at
  `0x671b50`. The exact shipped configuration maps UI 1–8 to native
  `1,3,2,5,4,8,6,9`. The eighth physical-row assignment therefore is **not** in
  the supported first block. Slot 7 is spare/unmapped and must be preserved.
- `FUN_STRING` labels plus serializer branches map the listed built-ins to
  codes. Plain captured assignments have flag `20`; unknown/Fn/repeat states
  are refused. Only the observed extension-link `2e` may be replaced by a built-in;
  no shortcut record is synthesized, freed or changed. Exact original links can
  be restored from a validated scoped backup while those records remain untouched.
- The independently pinned ANKO capture contains eight-byte button commits at
  packets 53 and 2137 (`21 22 23 24 25 26 00 29`), but **only base `0018` reads**.
  `audit_public_capture` now checks this explicitly. That third-party block is
  never used as this Blaze's defaults/backup or replayed.
- `button-records.json` completed in `.work/analysis/button-records-01/`: four
  xrefs and five pseudocode queries, exported/closed normally. `0x414420`
  converts a keyboard index through Windows VK to HID usage; it is **not a
  checksum**. `0x42f450` maps consumer-control usages. `0x435540` locates cached
  macro records; `0x448580` expands repetitions. `0x413d60` emits phase `10`,
  sleeps 5 ms, then phase `00`; this is static knowledge, not permission or
  evidence to append it to our scoped operation. It was not sent.

Focused hashes, instruction bytes, code table and Evidence IDs are retained in
[vendor-button-observations.json](../tests/fixtures/vendor-button-observations.json).
Recreate the temporary toolchain as above and run:

```sh
node tools/analyze_vendor.mjs "$RE_TOOLS/rea" "$RE_TOOLS/payload/app/Gaming Mouse 3.0.exe" .work/analysis/buttons-new .work/analysis/lighting-storage-01/snapshot.json tools/analysis-plans/buttons.json
node tools/analyze_vendor.mjs "$RE_TOOLS/rea" "$RE_TOOLS/payload/app/Gaming Mouse 3.0.exe" .work/analysis/button-records-new .work/analysis/buttons-new/snapshot.json tools/analysis-plans/button-records.json
```

Snapshots are optional caches; use `-` if missing. The old snapshots are not
portable dependencies. Temporary tools and full decompilations remain outside Git.

### What still blocks full programmable-button support

The GUI now offers **native built-in assignments**, not arbitrary keyboard
shortcuts/custom sequences. The serializer routes codes `0d/0e/0f/1e/1f` through
a separate descriptor table (candidate base `00a0`, ten-byte stride) and
variable records beginning at candidate `0400`. Counts, flags, pointer sharing,
deduplication and other cached data matter. Neither region has been read/backed
up on this Blaze and no hardware API for them exists. Do not guess a record,
overwrite shared records, expand allocation, or replay a generic profile image.

Next work for **custom programming**: reconstruct the exact descriptor/event
codec, independently corroborate it, establish bounded original-record backup
and sharing rules, then seek explicit new read/write/restore approvals. Also
recover the physical rapid-fire slot 9's independently scoped backup. Preserve
the approved UI; the native read/draft/Apply/restore workflow is documented in
[ui-development.md](ui-development.md#native-button-integration--2026-10-27).

Final offline verification for this milestone: **211 tests passed**. Checked
documentation links, JSON/JSONL syntax, exact journal counts and original capture
hashes, common-secret/home-path scan, public-capture audit and `git diff --check`.
No further hardware operation was performed during GUI integration or final
validation. New source, tests, sanitized evidence and docs are pending in the
working checkout; this feature task did not include a new commit or push request.

### Subsequent direct-menu workflow

The user tested the native app and requested direct dropdown/cascading assignment
menus, no prerequisite read/dialog and no Keep draft step. The Button page now
allows offline selection immediately. **Apply** is the explicit authorization for
the existing fresh-read/backup/write/readback transaction; it runs without another
modal or opening diagnostics. Only successful, request-matching saved verification
clears the selection and disables Apply. Failures retain the selection, clear stale
captured bytes and never trigger automatic retry/rollback. Opening the app or a
menu still performs no device operation. No additional hardware approval was
consumed by this UI-only change.

All requested unimplemented menu leaves are clickable no-ops, not new codecs:
media, macros, Shortcut, profile selection and Show desktop are not enabled as
device commands. Slot 9 remains preview-only. See the latest
[UI workflow](ui-development.md#direct-assignment-menus--2026-10-27) for details.

Direct-menu follow-up verification: **227 offline tests passed**, documentation
links/anchors and JSON validated, `git diff --check` clean. Main-page, root-menu
and Extend submenu images were reviewed outside Git. No new hardware operation,
reset, activation command or transport expansion accompanied this UI change.

### Subsequent UI polish

The user requested net-change comparison, removal of the right-click context
menu, and their supplied mouse illustration as the default. Apply now disables
when every selected assignment returns to its initial displayed value, including
before any device read and after trying multiple alternatives. UI baseline values
remain separate from raw captured bytes and are not used as device backup data.
Failure invalidates raw evidence but preserves the displayed comparison baseline;
reverting selections does not claim a hardware restore after an uncertain write.

There is no right-click/keyboard context menu or artwork toggle. Optional
diagnostics/explicit restore remain accessible through F1 and `--diagnostics`.
The original vendor mouse art is preserved and available via `--reference-mouse`;
the default uses `docs/Software_UI/MouseImage.png`. **238 offline tests passed**.
No hardware read/write, restore, input monitoring or transport expansion occurred
in this polish step.

### Button 8 investigation — 2026-10-27

The user observed that row 8 stays Rapid Fire. The immediate cause is software:
`UI_SLOTS[7] == 9`, while `ButtonDraft.editable()` and the planner permit only
slots `1..6,8` inside the backed-up `0008` block. Menu selection is deliberately
a no-op for row 8. Its initial Rapid Fire label is a reference example, not a
read of native slot 9; after loading button evidence it says **Not read (slot 9)**.
This does **not** establish a permanent hardware Rapid Fire restriction.

Re-inspection of the saved serializer pseudocode (entry `0x422070`, Evidence
`ev_4c1603b7dd3456d34089b5719646087cb11ac79250e64b2c0a5a9e385926795f`)
narrows the next static candidate without contacting the device:

- The mapping loop copies each action to `0x006d69b3 + native_slot`.
  Slot 9's cached action is therefore `DAT_006d69bc`.
- After the eight-byte `0008` block, the serializer advances its logical base
  another eight bytes. Byte 0 of the candidate `0010` block uses that action:
  either `DAT_006d69bc` or the low byte of
  `DAT_006d6bb4 * 0x40 + DAT_006d6c00 * 0x20 + DAT_006d69bc`.
- The other bytes contain DPI metadata; this is **not** another independent
  eight-button table. Do not extend the existing writer or synthesize its neighbors.

These source-derived findings are retained in `slot_9_followup` in the button
fixture. There is still no Blaze original-value read/backup for `0010`, no scoped
writer/restore for it, and no behavior validation. Recover/corroborate a bounded
read and preservation plan first, then obtain fresh explicit authorization for
any live read, and separately for writes/restores. Existing approvals remain
consumed. No transport scope was expanded during this investigation.

The accompanying generic-footer/marker/window-routing UI fixes passed **246
offline tests**; see [UI development](ui-development.md#footer-marker-and-window-interaction-polish--2026-10-27).

### Shortcut recorder and remaining write gate — 2026-10-27

The user requested a custom-styled keyboard-shortcut recorder: Record/Re-record,
Save to a button's local draft, then main Apply as the only mouse-write action.
The recorder and draft workflow are implemented in `shortcuts.py`,
`shortcut_editor.py`, `button_draft.py` and `desktop.py`. Recording is explicitly
armed and restricted to focused-editor GTK events, never global monitoring. Tests
use synthetic, process-local GTK events, not real keyboard input or injection.

This is **not yet end-to-end shortcut programming**. A saved symbolic combination
is not a device record. No keyboard HID usage, extension descriptor, allocation
pointer or `2e` link is synthesized. Any shortcut draft blocks Button-page Apply,
including mixed drafts, rather than partially applying native changes. The editor
and tooltips explicitly explain this restriction. Existing native Apply still
uses the approved fixed `0008` transaction when no shortcut draft exists.

Re-reading the saved `0x422070` serializer confirms that the record path is not
a second ordinary action code: it uses shared cached pointers/deduplication,
record lengths and counts, a repeat prefix and per-event serialization. The
record helper findings and Evidence IDs remain in the native-button checkpoint
and fixture above. No new protocol query or live operation was needed for the
recorder UI. None of those static observations supplies the missing original
extension-table/data backups or a safe scoped allocator/restore implementation.

Next device task: reconstruct/corroborate the exact shortcut descriptor/event
codec, bounds and sharing rules; design a narrow preservation/read/backup plan;
obtain fresh explicit authorization for the bounded device reads; only then
implement/validate scoped writes and restore with separate approvals. Do not
extend the native writer, replay vendor images or add an evdev/uinput workaround.

**275 offline tests passed**; no live reads/writes/restores, global input hooks,
permission changes or vendor execution occurred. See the
[recorder UI checkpoint](ui-development.md#custom-shortcut-recorder--2026-10-27).

### Shortcut backend research in progress — 2026-10-27

The user explicitly requested finishing the on-device feature, including research
and backend work. This authorizes implementation/static analysis, **not an
unrestricted live memory operation**. No new hardware approval has been consumed.

`shortcut-codec.json` completed in `.work/analysis/shortcut-codec-01/`, with a
fresh Ghidra import, evidence/snapshot export and normal close. Findings and
source identities are retained in
[`vendor-shortcut-observations.json`](../tests/fixtures/vendor-shortcut-observations.json):

- Both source serializers construct 56 ten-byte descriptors at `00a0..02cf`:
  four vendor table groups of 14 entries, **not proof of hardware profile banks**.
  Tick, event count, keyboard/consumer usage, record pointer and repeat-flag
  fields are individually identified. Raw opaque bytes remain preserved.
- `430490` dispatches keyboard VK conversion according to the cached layout.
  `414420` is an index-to-VK-to-usage path, not a checksum. Targeted follow-up
  `shortcut-usages.json` examines the US-layout converter without running the EXE.
- The pinned ANKO capture independently contains two complete 70-block writes
  at `00a0..02c8`. All descriptor bytes there are zero, so it corroborates address
  arithmetic/chunking **only**, not a nonzero shortcut record or Blaze read safety.
  The public-capture auditor now verifies this in addition to earlier findings.
- The macro-data endpoint is serialized at `006e..006f`; `0070..0075` contains
  ancillary endpoint pointers, and `0078` contains a stored-end prefix. These
  are candidates to inspect, not permission to move/overwrite auxiliary settings
  or infer firmware capacity. Existing shortcut records may be shared.

Implemented a **separate fixed metadata reader and strict offline inspector**:
`shortcut_read.py`, `shortcut_capture.py`, with fault/consent/scope tests. It reads
exactly 74 eight-byte blocks: `0008`, `0068`, `0070`, `0078`, then 70 blocks from
`00a0` through `02c8`. Total **1332 SET / 592 GET**, zero-data staging preparation,
**no phase-09 commit**, no payload-region access, no retry/reset/input monitor.
Identity, descriptor, open handle and sysfs are checked; the new private journal
and directory entries are persisted before feature I/O. It refuses arbitrary
addresses/lengths and existing destinations.

This reader is **implemented, not hardware-exercised**. Its staged reads in new
regions need a fresh explicit approval. The immediate next step is that one
metadata inspection, so payload backup boundaries/allocation rules can be based
on the mouse's actual descriptors rather than defaults. Payload reads, changes
and restore will require their own separately scoped approvals. UI Apply remains
safely gated while this work is incomplete.

Offline commands (the second one performs **no** device access):

```sh
python3 -m evofox_blaze.shortcut_read --help
python3 -m evofox_blaze.shortcut_capture --capture <saved-shortcut-headers.jsonl>
```

### Newer live inspection and implementation checkpoint

The two explicit approvals subsequently granted were consumed by their exact
operations: metadata (1332 SET/592 GET) and `0400..045f` payload (216 SET/96 GET),
no settings commit. Original journals/authorization scopes are retained under
`docs/device-captures/30fa-1440-0100-shortcut-{headers,payload}-01/`. Do not repeat
either operation automatically. The fresh native table is `21 22 23 24 23 35 00 26`;
preserve that observed slot-5 Right Click rather than the old Forward baseline.

Actual descriptors and keyboard payload corroborate the 10-byte descriptor,
two-byte repeat prefix and `[delay|press-bit, HID usage]` event codec. The three
records at `0400/0408/0410` are press-only Ctrl+Super+Left, Ctrl+Super+Right and
Super+Tab, with four ticks each. No original record or auxiliary byte was changed.
`shortcut-usages.json` completed normally with Evidence/snapshot export; the
`458640` US-layout VK converter confirms all UI keys including F13–F24 and the
eight modifier usages. Focused findings are in the shortcut fixture.

Implemented `shortcut_codec.py`, `shortcut_plan.py`, `shortcut_write.py`, and
`shortcut_config_capture.py` with offline transaction/fault/restore tests. The
**experimental, not yet hardware-proven** preservation policy:

- Accept only the inspected `0418/0438` metadata layout and known original or
  supported, unshared app-generated descriptors. Reject other layouts before
  setting data. Keep slot 9 and all original `0400..0437` payload/auxiliary bytes.
- At most seven distinct 40-byte tail slots at `0438 + index*40`, ending before
  `0550`, for the seven supported native rows. No unknown sharing, relocation,
  metadata-end changes, pool clearing or assumption that the tail is zero.
- Back up fresh complete header blocks, original payload/auxiliary guard blocks
  and all used/new record-slot blocks durably before any setting-data frame.
  Write only changed chord prefixes, owned descriptor bytes (neighbor bytes
  copied from fresh reads) and selected native-table bytes. Read back all guards.
- Generate the captured press-only/mouse-release-managed format (`2e` link),
  not an invented firmware macro or activation command. Restores are explicit,
  preserve exact old bytes and reject changes outside recorded whole/prefix
  transaction states. No retry, cleanup write or automatic rollback occurs.

The first prospective field test is one harmless F13 chord on UI button 4/native
slot 5, currently Right Click: eight new record bytes at `0438`, eight descriptor
bytes at `00c8`, and the eight-byte native table, preserving all other bytes.
It would use 86-block fresh read and readback: **3126 SET / 1376 GET, three
settings commits**, with no original-record/auxiliary/metadata-end writes.
Whether this firmware follows a record pointer after the existing stored-end
marker is **not proven**; it must be tested explicitly rather than claimed from
readback. No such write is authorized or performed yet. UI shortcut Apply stays
gated until that hardware path is resolved.

Shortcut configuration journals exceed the old single-block 1-MiB evidence cap.
A separate, fixed 8-MiB reader accepts only shortcut-configuration journals;
general evidence reads retain their original 1-MiB limit and regular-file/
no-symlink/no-device safeguards.

### F13 transaction completed — user behavior test pending

Newer than the prospective test above: the user explicitly approved that single
F13 test, and its permission is now consumed. The guarded CLI transaction wrote
and read back exactly the planned `0438/8`, `00c8/8`, `0008/8` blocks: **3126 SET /
1376 GET, three commits**. Strict offline journal and backup validation confirmed
that every original record/auxiliary byte and allocation-metadata byte was
unchanged. Current recorded table is **`21 22 23 24 2e 35 00 26`**; UI button 4 /
native slot 5 is stored as F13. Evidence, original-byte backup and authorization
are in `docs/device-captures/30fa-1440-0100-shortcut-f13-test-01/`.

**Do not repeat the write or restore without a new explicit approval.** No
restore is approved or executed, and the user still must replug/test F13. The
app's shortcut Apply remains gated pending that behavioral result and final
integration. Readback alone does not prove that the controller follows a record
pointer beyond its stored-end marker.

Validation before the field test: **324 offline tests passed** on a private
authenticated Xvfb display. Two existing cascade tests failed on the active host
display because their root popups were not mapped; they passed in isolation,
without modifying the menu implementation. The trusted Ubuntu Xvfb package was
downloaded/hash-checked/extracted only under `/tmp/opencode/evofox-xvfb`, not
installed on the host. Package SHA-256:
`f857020815dd091b4331cc45b37550a92480178c2931c76b486af2202e4271ec`.
Use `python3 -m tools.run_virtual_tests --xvfb <trusted-Xvfb>` to repeat the full
suite without interacting with the user's desktop. A subsequent extra unit test
checks the first-tail-test guard against an intervening button-state change.

### Shortcut GUI integration and user test report — 2026-10-28

Supersedes the preceding UI gate, not the consumed authorization boundaries.
The user reported that pressing the test button opened desktop Settings, with
screenshots showing Settings/Power and the recorder stopped on focus loss.
This is consistent with F13 being mapped to Tools and intercepted by the desktop,
supporting tail-record key emission. It is **not** an input-event capture or proof
of replug/persistence, ordinary modifier-chord behavior or correct key release.
The report is retained separately as `behavior-validation.json` beside the F13
journal; no original journal is changed. No restore or further write is authorized
by that report, and none was performed.

The user's requested normal workflow is now integrated: Record → Save stages
only RAM; main Apply runs the scoped chord transaction, including all mixed native
changes. Native-only Apply keeps its original fixed-block backend. Strict saved
verification must match every selected row/chord before drafts clear. Verified
chords form display-only net-change baselines, never synthetic backup bytes.
F1 has separately confirmed shortcut-backup restore controls. Startup, menus,
saved-file inspection and Save remain offline. Unknown/shared allocation layouts,
slot 9 and custom sequences/macros remain unsupported.

**341 offline tests passed** on private authenticated Xvfb, including combined
Record/Save/Apply, no-change, failure retention, first-test guards, request-matching
journals, exact scoped restore simulation, large evidence files and GTK focus
safeguards. No live hardware access was needed for integration. Next: restart the
app, record Ctrl+Shift+Down again, Save, explicitly Apply, then replug and test in
the intended application. Only that user Apply authorizes that transaction; do
not initiate another agent-side read/write/restore on resume.

### Newer startup-baseline and reserved-shortcut correction — 2026-10-28

The user reported having applied Left/Right swaps, then being unable to select the
old reference defaults after restart. Thus the F13 journal above is only a last
recorded agent transaction, **not a claim about the current board table**. No fresh
agent hardware operation was authorized or performed for this report.

Reference defaults must not masquerade as read board state or suppress explicit
assignment requests. Startup now shows **Not read**, with no assumed native
comparison baseline. Selecting Left/Right is applicable even before a read;
the existing backend obtains fresh backup bytes and enforces retained Left Click.
A real explicit read or verified Apply establishes the normal net-change baseline.
Startup still performs no automatic feature I/O. Optional F1 → Read button
assignments uses the existing separately confirmed fixed `0008` transport.

The intended workspace combination is **Ctrl+Alt+Down**, not Ctrl+Shift+Down.
The desktop intercepts Down while recording and switches workspace. The editor
now supports local modifier/key selection without pressing the chord or disabling
desktop shortcuts. Focus loss stops capture and clears timers/held state, but
retains received valid chords or a non-saveable partial preview. Intercepted keys
are never inferred; the user can choose Down explicitly to complete Ctrl+Alt+….
Save remains draft-only, Apply unchanged. No global grab, background input
capture, compositor changes, permission changes or new transport path was added.

**353 offline tests passed** on private Xvfb for the latest correction. Physical
Ctrl+Alt+Down behavior and key release still need the user's test after their
explicit Apply and replug; no additional agent-side operation is authorized.

### Newer six-box editor and assignment-read integration — 2026-10-28

The user rejected unread-only startup and the accordion/key-dropdown/checkbox
shortcut UX. Replaced the editor with 1–6 individual key boxes (three initially),
tap/release capture, automatic next-empty-box progression, add/delete and a full
preview. All boxes must be filled with distinct modifiers plus one regular key.
Ctrl+Alt+Down is entered as three separate taps, not a held desktop shortcut.
Focus loss stops capture but retains completed boxes. No global grab, desktop
shortcut inhibition or host remapping was introduced.

Startup now recovers only the latest strictly validated GUI assignment journal
offline, labeled saved/not live; it never falls back past an incomplete attempt.
The main Button page exposes **Read mouse assignments…**, with its own explicit
staging-risk confirmation. `assignment_read.py` reuses the existing bounded
snapshot reader with **no new allocation request**: 74 metadata blocks, seven
original record/auxiliary guard blocks and five blocks per recognized owned tail
slot. Total **81–116 blocks, 1458–2088 SET / 648–928 GET, zero settings commits**.
Unknown layouts/sharing are refused before payload expansion. The strict offline
inspector validates the exact snapshot and completion, including decoded active
keyboard chords. Native slot 9's action is not read or inferred from its known
descriptor. No arbitrary address/range CLI or write frame was added to this reader.

The new full-assignment read is **implemented with offline coverage only**; no
fresh agent hardware operation was authorized or performed. GUI confirmation is
the user's scope-specific read authorization when they choose to run it, not
standing approval for the agent. Startup, saved history, boxes and Save stay
offline; Apply/restore safeguards and consumed hardware approvals are unchanged.
Latest offline validation: **377 tests passed** on private authenticated Xvfb.

### Ordinary shortcut user report — 2026-11-02

After being prompted to assign Ctrl+Alt+Down through the GUI, wait for Apply,
reconnect and test workspace switching with the physical button, the user replied
**"It is working"**. This supersedes ordinary-chord behavior being wholly pending:
the intended Ctrl+Alt+Down workflow now has a successful user behavior report.
The reply did not separately confirm reconnect/persistence or absence of stuck
modifiers; do not elevate it to raw event evidence or validation of all chords.
The exact selected button, current bytes and GUI journal were not inspected.

The agent only launched the app offline and recorded the report; it performed no
new mouse read, write, restore or input monitoring. The report authorizes no such
operation. Original captures remain unchanged. No shortcut restore was performed.
Next: confirm the remaining behavioral details and investigate physical rapid-fire
slot 9 with its own bounded backend/backup; do not broaden `0x0008` writes.

The unchanged full suite passed **377 tests** on authenticated private Xvfb.
The active desktop lacked an `Alt_R` keymap entry, causing two test-helper failures
there; both passed on the isolated display. Future tests must run headlessly as
requested, without repeatedly opening windows on the user's desktop.

### Immediate activation investigation — 2026-11-02

The user selected removal of the replug workaround as the next priority.
Inspected the retained helper/serializer decompilations, then independently
rechecked six focused instruction byte sequences against a freshly statically
extracted, hash-matched application with objdump. No new REA session was needed;
the existing Evidence IDs remain attributed to their original observations.
Temporary analysis material is under `/tmp/opencode/evofox-activation-research`;
essential facts are preserved in
`tests/fixtures/vendor-activation-observations.json` and
`tools/analysis-plans/activation.json`, not dependent on that temporary directory.

Findings: serializer `0x422070` calls helper `0x413d60` at `0x42a161` after its
block writes. The helper sends `07 18 10 00 00 00 00 00`, sleeps 5 ms, then sends
`07 18 00 00 00 00 00 00`. The pinned ANKO capture independently contains three
such pairs, including two immediately following configuration-write passes.
`audit_public_capture` now verifies their packet numbers. The separate `07 20`
command later in that capture is excluded. End-of-settings/runtime reload is a
candidate interpretation only; firmware effects on this Blaze remain unknown.
See [protocol scope](hid-protocol.md#end-of-settings--immediate-activation-candidate--2026-11-02).

Implemented the fixed, separate `activation.py` transport/CLI and strict offline
`activation_capture.py` inspector. Preview/default is offline. Live mode requires
both `--activate` and `--accept-activation-risk`, the exact baseline and a new
private evidence directory. It sends **two SETs / zero GETs**, no setting-data
frames or phase-09 commit; validates identity/descriptor/handle, holds the device
lock, and durably logs intent. Any failure stops without retry/cleanup/rollback.
It does not back up settings or claim that sent reports prove activation, and
may activate all stored configuration, not just a selected row.

**No new live mouse operation was authorized or performed. Automatic activation
is not integrated into GUI Apply/restore/startup.** Next: ask the user to make one
intentional supported assignment change through Apply and test it **without
replugging**. If the old behavior remains, request explicit approval for this
single two-report candidate, with its all-stored-settings/unknown-effects limit,
before running it. No broad write, reset or monitoring is implied. If behavior
confirms it, integrate only after complete successful writes, preserving backups,
readback, strict journal validation, and no retries or success after failure.

Validation: **392 offline tests passed on private authenticated Xvfb**, including
15 new fixed-sequence, consent, identity/lock, durable-intent/result/delay-fault,
no-retry, exclusive-evidence and strict-inspection cases. The pinned public-capture
audit and all six application instruction-byte checks passed. No active-desktop
test windows or Windows executable execution were used.

Reproduce the safe preview and instruction checks:

```sh
python3 -m evofox_blaze.activation --preview
objdump -d -Mintel --start-address=0x413d60 --stop-address=0x413dab 'Gaming Mouse 3.0.exe'
objdump -d -Mintel --start-address=0x42a142 --stop-address=0x42a166 'Gaming Mouse 3.0.exe'
```

Re-run the focused REA plan with the documented toolchain if needed (the plan is
retained for reproduction, not claimed as a newly executed REA run):

```sh
node tools/analyze_vendor.mjs "$RE_TOOLS/rea" "$RE_TOOLS/payload/app/Gaming Mouse 3.0.exe" .work/analysis/activation-new - tools/analysis-plans/activation.json
```

### Windows/Super recorder correction — 2026-11-02

During the requested no-replug test setup, the user reported that the Windows
key opens the Pop!_OS launcher instead of recording. Added an explicit local
**Windows / Super** button as the safe fallback, not a global grab or inference
of an intercepted tap. See the [recorder checkpoint](ui-development.md#windows-super-launcher-interception--2026-11-02)
for armed-box/idle behavior and safeguards. **400 tests passed headlessly**.
This UI correction performed no device operation and does not validate or
authorize the activation candidate. Immediate behavior before replug remains
the next hardware question; no automatic activation was connected to Apply.

### Independent offline feature audit — 2026-11-02

The user became unavailable and explicitly requested independent test cases and
coverage of discrepancies across the full app. This did **not** authorize new
hardware reads/writes/activation/restore/monitoring. Expanded headless tests to
413 cases; **all 413 passed, no skips**. The added end-to-end Windows/Super flow
uses actual GUI routing and the scoped writer/backup/journal on fake mouse memory,
including exact `e3` usage, mixed native edits, restart recovery and uncertain
commit retention without retry. Polling similarly uses its actual writer on fake
memory. Native menu routing covers every built-in across all eight visible rows,
with the unsupported eighth row still refusing drafts.

Reproduced and fixed disconnected/blank Error details, lost failure diagnostics,
missing polling commit warnings, and a missing saved-capture busy guard. Preserved
the existing partial diagnostic work rather than removing it. See
[the feature audit](feature-audit.md) and
[UI checkpoint](ui-development.md#independent-offline-feature-audit--2026-11-02).
Disabled controls/placeholders were tested as inactive, **not** as completed
features. The app remains incomplete; original hardware captures are unchanged.
Immediate runtime activation, physical release and persistence questions still
require separately authorized hardware testing when the user is available.

### Opt-in immediate activation integration — 2026-11-02

The user selected **Immediate activation** when clarifying "Build that". Implemented
the application path, not a live test: `gui --experimental-activation` arms new
native-button, shortcut and polling Apply transactions. Ordinary Apply without
the flag remains unchanged; startup, menus, Save and saved-evidence loading stay
offline. No agent-side hardware read/write/activation/restore/monitoring was
authorized or performed.

Implementation:

- `activation.py` shares its exact two-report sender with the existing standalone
  tool. `activate_verified_change` logs an explicit after-readback boundary; the
  caller retains its already validated/locked handle. The same fixed 5-ms delay,
  strict completions and stop-without-cleanup semantics apply.
- `button_write.py`, `shortcut_write.py` and `config_write.py` require separate
  boolean `accept_activation_risk`, validate scope before device access, and send
  the candidate only after durable backup, successful complete writes, matching
  readback and another identity recheck. Polling/native transactions add two SETs
  (48 SET / 16 GET); shortcuts add two SETs without changing read/commit counts.
- No-change skips the candidate and creates no new backup. Restores, DPI-stage
  changes and the old first-F13 field-test scope cannot acquire activation. Reads
  and startup never activate, including recovery of a saved activation journal.
- `activation_capture.py` shares the strict ordered suffix validator with the
  three configuration inspectors. Session consent, exact frames/timing, ordering,
  typed completion fields and false behavior flags are required. Legacy journal
  shape and immutable capture hashes are preserved; unsolicited activation claims
  cannot be accepted as a verified result.
- `DeviceControl` propagates the opt-in only for eligible new changes. GUI Apply
  requires the saved verification to match both the selected assignments and the
  requested activation policy. Failed/partial activation retains drafts and the
  actual backup, reports failure and blocks stale startup history fallback.
- The Button page displays an armed warning and scope tooltip. Polling's existing
  confirmation includes the risk. Successful UI text says **sequence sent**, not
  runtime behavior verified; no-change explicitly says no activation was sent.

The candidate may reload **all** stored configuration. Stored-byte readback is
before the candidate, not proof of its later firmware effects. No real activation
test has been approved or executed; the source/related-capture evidence still
does not establish a no-replug guarantee. Do not silently make this the default
or perform a live test because the implementation exists. No command `20`, USB
reset, driver detach, permission change, global capture or blind rollback was added.

Safe reproduction remains headless tests or `activation --preview`. The GUI
flag arms future user Apply authorization; it is not standing approval for an
agent command. Original hardware captures and consumed F13/polling/button scopes
are unchanged.

Validation: **434 tests passed headlessly, no skips**, including 21 new integration
cases beyond the 413-test audit. Coverage includes all three eligible backends,
same-handle ordering and identity recheck, exact two-SET overhead, no-change/default
omission, failed backup/write/readback/activation/logging, strict journal tampering,
CLI scope rejection, GUI launch/routing/confirmation, retained drafts, incomplete
history fallback refusal and recovery without startup activation. Fake memory and
ioctls validate software sequencing only, not the firmware's runtime reload.

### No-replug user report and saving UX — 2026-11-02

The user returned, requested a fresh manual test, and the agent launched
`gui --experimental-activation` offline. The prompted workflow was Button 4 →
Ctrl+A (separate Ctrl/A taps) → Save → Apply → wait for activation-sent → test
text selection without unplugging. The user reported: **"Perfect it works without
unplougging and replugging the mouse."** This is successful user behavior evidence
for that workflow; no new agent-side hardware command, independent GUI-journal
inspection or raw input capture was performed. Do not infer the current board
table, validation of every setting, persistence, or new authorization from it.
Do not replay the assignment/activation or restore it automatically on resume.

The follow-up request was UI-only: a non-dismissible, Blaze-styled saving overlay
and minimal tooltips. Added a reusable app-local busy shield for main/diagnostic
windows, disabled underlying content, retained close/key/duplicate-operation
guards, and kept it visible through strict saved-result validation. It clears
on completion/failure; recorder Save stays draft-only. Removed verbose background
and supported-control/menu hovers, retaining only short unavailable/prerequisite,
clipped-label and Windows-key guidance. See the
[UI checkpoint](ui-development.md#saving-overlay-and-minimal-hover-help--2026-11-02).
No protocol/transport scope or activation default was changed for this UI work.

Final validation: **442 headless tests passed, no skips**. Eight new overlay/hover
cases and existing fake-device lifecycle checks verify that the shield blocks
normal close, keyboard/pointer actions and underlying controls until completion,
including saved-journal validation, and clears on every tested failure path.

### Live loading phases and post-write wait — 2026-11-02

The user reported the assigned shortcut working while the overlay was still
loading. Offline saved-GUI-journal inspection showed roughly 26 seconds for the
fresh snapshot and another 26 seconds for complete post-write readback (about
52 seconds total); strict saved-result decoding took about 0.11 seconds. The
overlay was waiting for real verification, not an artificial timer. This is saved
timing evidence, not a new live behavior/activation test or current-device read.

At the user's request, added a single actual-phase line with cycling activity dots
under the spinner. A private inherited phase pipe carries deduplicated hints from
the existing durable journal events plus explicit backup boundaries. Final JSON,
journal schema, flush/fsync intent ordering, identity checks, backup, full readback,
activation policy and failure/no-retry semantics remain unchanged. GUI updates
run on GTK's main loop with per-operation tokens; completion/destruction clears
the animation and stale updates cannot overwrite saved-result checks. See the
[UI checkpoint](ui-development.md#live-loading-phase-line--2026-11-02).
No mouse operation, input monitoring, new command, reduced verification or
automatic retry was authorized or performed for this change.

Validation: **459 headless tests passed, no skips**. New tests cover real pipe
delivery with a plain Python child and all writer phases on fake device memory;
strict journal validation still passes with identical evidence schemas. UI tests
cover dot timers, both shields, saved-result checks and stale callback cleanup.
