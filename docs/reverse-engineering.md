# Static analysis with REA

## Scope

Recover and bound the EvoFox application's setting and readback behavior.
Standalone GET and the fixed `0x0018` state transport are implemented; polling
write/readback/restore has been exercised. Generic memory access and lighting
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
