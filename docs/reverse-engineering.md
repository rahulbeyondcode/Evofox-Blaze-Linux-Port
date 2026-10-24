# Static analysis with REA

## Scope

Recover and bound the EvoFox application's setting and readback behavior.
The standalone GET-only transport is implemented; bulk reads and setting writes
remain unavailable. Start with the functions and unresolved questions in
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

Evidence IDs and packet details are in [hid-protocol.md](hid-protocol.md).
Raw results are in `.work/analysis/readback-01/` and `readback-02/`; the second
bundle retains 11 observations. These local files are deliberately not committed.
Static packet reconstruction does not authorize sending the reconstructed bytes.

## Checkpoint and continuation

All four static-analysis sessions finished and closed normally. Their essential
findings and Evidence IDs are retained in the protocol document and two test
fixtures; the full local bundles are intentionally excluded from Git. Offline
tests now cover descriptor decoding, selection, packet sequencing, GET-only
validation/logging, saved-evidence handling, and status masks (64 passing locally).

Continue with one lighting field and a proven original-value readback/restore
path. Profile index `0` remains a static candidate derived from the single saved
reply, not a controlled hardware confirmation. Do not treat unused initializer
locals as addresses or enable the vendor's SET_REPORT-based read preparation.
