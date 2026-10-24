# Protocol evidence

## Observed hardware: 30fa:1440, revision 0100

Source: [descriptor capture](device-captures/2026-10-23-30fa-1440-0100/probe.json).
Raw USB/HID descriptor bytes and HID report descriptor SHA-256 hashes are retained there.
No feature request or mouse-setting write was made during this capture.

| USB interface | Top-level usage page/usage | Report type / ID / length |
|---|---|---|
| 0 | `0001/0002` mouse | Input `01`, 7 bytes |
| 1 | `0001/0006` keyboard | Input `03`, 8 bytes |
| 1 | `000c/0001` consumer control | Input `02`, 3 bytes |
| 1 | `ff00/0001` vendor | Input `06`, 3 bytes |
| 1 | `ff01/0001` configuration | Feature `07`, 8 bytes |
| 1 | `0001/0080` system control | Input `08`, 2 bytes |

Lengths include the report ID. Feature `07` has seven eight-bit payload fields:
**seven payload bytes plus one ID byte**, not eight payload bytes.

Linux exposes one hidraw node per USB HID interface here. Both vendor
collections belong to interface 1, alongside ordinary input collections.
Windows collection handles must not be translated into separate Linux nodes.
Find configuration support by scanning collections and their owned feature
reports, not by accepting only a node's first top-level usage.

The USB manufacturer is `INSTANT`, product `USB GAMING MOUSE`, speed 12 Mbit/s.
This does not identify the controller silicon or prove the retail label.

## Observed standalone GET_FEATURE

Source: [one-shot read journal](device-captures/30fa-1440-0100-get-feature-01/feature-read.jsonl),
on `30fa:1440`, revision `0100`, interface 1. The open handle's USB IDs and
report descriptor matched the saved baseline before the only feature request.

```text
HIDIOCGFEATURE(8):  0xc0084807
Syscall buffer:   07 00 00 00 00 00 00 00
Returned bytes:   07 00 58 09 1f 00 23 7b
Returned length:  8
```

No SET_REPORT preceded this request in our work. This confirms that a standalone
feature read is accepted on this revision, not that the bytes form a complete
configuration or a current/stable status schema. Do not apply the base-`0018`
block decoder to this report. No polling, repetition, or persistence test was done.

The logged buffer is an ioctl argument, **not** a USB payload capture. The
ioctl's READ|WRITE direction bits describe the in/out userspace buffer, not a
SET_REPORT. Metadata ioctls preceded the read; none were feature requests.
The transport currently accepts Linux x86-64's verified UAPI layout only.

### Static interpretation, not yet validated through a device change

The [consumer fixture](../tests/fixtures/status-consumer-observations.json)
records the exact executable hash, REA Evidence IDs, and masks used by the
offline `evofox_blaze.status` decoder:

| Bytes / bits | Observed Windows behavior | Saved reply |
|---|---|---|
| `(byte[6] >> 2) & 3` | Stored at `0x6d6bdc`, written to `[Init] CurConfig` | Profile index candidate `0` |
| `byte[6] & 2` | Initializer assigns local `0x0ff8` if set, `0x07f8` otherwise | Set; local constant `0x0ff8` |
| `byte[6] & 0xf3`; bytes 1–5 and 7 | Firmware meanings unassigned | Preserved verbatim |

The profile consumers follow GetFeature calls at `0x44f55e` and `0x44fc3e` in
`0x44f2b0`; the INI writes are at `0x44f5e1` and `0x44fcc1`. The initializer
reads are at `0x41a4e3` and `0x422143`. No subsequent use of their selected
local was found in recovered pseudocode: **do not treat it as a memory address
or storage capacity**. Bit 1's firmware meaning therefore remains unknown.

These cover four of the five observed direct GetFeature thunk references;
the fifth is the command-18 bulk reader. Indirect coverage remains unknown.
The reply does not establish a DPI stage, CPI value, polling rate, lighting
mode, or checksum. An offline decoder accepts only a complete standalone-read
journal, not an arbitrary report-07 packet or a failed/partial read.

## Static EvoFox application evidence

These offsets refer to the application hash in
[vendor-reference.md](vendor-reference.md), preferred image
base `0x00400000`; they are virtual addresses, not installer file offsets.
The command-18 routines were rechecked in this session; the remaining addresses
are retained research seeds until rechecked.

| Address | Research seed |
|---|---|
| `0x413910` | Generic `07 18` feature-report builder |
| `0x413a10` | Staged write helper; **not** the reader (corrected below) |
| `0x413ac0` | Request / wait / GetFeature / copy-response-byte loop |
| `0x413b90` | Preparation helper called by `0x413ac0` |
| `0x419df0` | Enumeration; accepts `30fa:1440` and `30fa:1e01` |
| `0x41a340` | HID capabilities acquisition |
| `0x430098`, `0x43023e` | Command `16` builders; meaning unresolved |
| `0x5d17bd`, `0x5d17c3` | GetFeature and SetFeature import thunks |
| `0x671098` | Configuration feature-report length |
| `0x6710d8` | Shared report buffer (256-byte allocation, not report length) |

The application selects usage `0001` on pages `ff00` and `ff01`, keeps
collection handles separately on Windows, and passes the descriptor-derived
feature length to HidD_GetFeature / HidD_SetFeature. The new Ghidra inventory
finds five direct references to the GetFeature thunk and **23**, not the old
approximate 24, to SetFeature. This does not establish indirect-call coverage.

REA evidence IDs (raw bundles are retained in `.work/analysis/`):

| Observation | Evidence ID |
|---|---|
| Builder `0x413910` | `ev_5a044464d9fa2bccd73483febee0dd426e9f2a6aaa58121de1c31a39a40c9787` |
| Writer `0x413a10` | `ev_416dbeed5df074bf93e5abe8016ab7d8f6d46293bf796ac7cec46756283a7901` |
| Reader `0x413ac0` | `ev_deb30d296f27936b059a53842f666bc0548880b1ea56cdabd29a17da02972f26` |
| Preparation `0x413b90` | `ev_2b07d0d512b35abb5c028b03876e73587b2c60b45ae2feca69e8ed2288f9caab` |
| GetFeature thunk references | `ev_d1089537cc6a1c39e45fee5e4edd34bf5899102ff765dad00c52b11075b6a0b2` |
| SetFeature thunk references | `ev_c3709f3f85719d823ccbabc8ab7ad912a6d07677cd3f5d87c2c62604efa0ddf3` |

At `0x413910`, ten stack arguments construct:

```text
07 18 flags arg8 arg7-lo arg7-hi arg10 arg9
flags = low_byte((arg1 << 5) + (arg2 << 4) + (arg3 * 4)
                 + (arg4 * 8) + (arg5 * 2) + arg6)
```

No protocol-wide encryption/checksum has been established; absence in one
builder is not proof for other commands.

## Corrected EvoFox read/write routines

Rechecking the exact executable exposed an incorrect offset in the original
notes: `0x413a10` is a **write helper**, not a read loop. GNU objdump shows
it builds phase `03` data frames, waits 4 ms, sends phase `09`, waits 2 ms,
then sends phase `00`. This is Blaze-application evidence, not a timing copied
from the generic driver. Execution and hardware effects remain untested.

The read loop starts at `0x413ac0`. Its static sequence is:

1. Call `0x413b90(base, length)`. That helper sends phase `03` frames with
   zero data and increasing index, sleeping 2 ms after each; waits another
   2 ms and sends phase `00` with the base retained.
2. For each index, send `07 18 05 ii aa AA 00 nn`, wait 2 ms, call GetFeature,
   and copy response byte 1 into the caller's output buffer.
3. Wait 2 ms, then send `07 18 00 00 00 00 00 00`.

Here `aa AA` is the supplied base, `ii` the index, and `nn` length minus one.
This **uses SET_REPORT**, including zero-data preparation, so it must not be
exposed as a harmless read or run before those phases' side effects are known.
The original code stores API return values without checking them before copying
the response; a Linux implementation must not copy that error-handling behavior.

The three reader callers supply the following fixed arguments:

| Caller / call site | Base / collected length | Use in the host application |
|---|---|---|
| `0x44c880` / `0x44ca69` | `0x0fa0`, `0x0fa8`, `0x0fb0`, `0x0fb8`; 8 bytes each | Compare the resulting 32 bytes with an encoded input string |
| `0x44cc10` / `0x44cc46` | `0x0018`; 8 bytes | Mask byte 0 with `07`, then call `0x4325f0` |
| `0x44e560` / `0x44e606` | `0x0018`; 8 bytes | Mask byte 0 with `07`, store at `0x670fac`, update a UI path |

The `0x0018` selector follows the DPI-stage state, not a proven profile index:
the cached value at `0x670fac` is initialized from `0x671d8c`, which is loaded
from the `DPI_LEVEL` INI field (`0x42ae3f` through `0x42ae6e`, string
`0x604fac`). This is a static application mapping; no CPI value or physical
stage range has been measured. Preserve selector values 6/7 as unassigned.

The [static fixture](../tests/fixtures/vendor-read-observations.json) preserves
caller Evidence IDs and exact arguments. No incoming xrefs were found for
`0x44c880` or `0x44cc10`; they may be unused/template code or reached indirectly.
`0x44e560` has one static caller at `0x43aff7` and opens an audio-related UI
path (`0x44e4e0` checks the Windows mixer). None was observed executing.

Do not invoke the whole `0x44cc10` path as a read: `0x4325f0` emits a separate
command `07 14 ...` through SetFeature immediately afterward. The offline
preview models only `0x413ac0` and its preparation helper, not that caller.

For each observed eight-byte block, the helper emits **18 SET_FEATUREs,
8 GET_FEATUREs, and 36 ms of explicit sleeps** (USB time is additional).
No phase `09` occurs in this helper; the actual writer uses it. This supports
an uncommitted-buffer interpretation of preparation, but firmware side effects
cannot be proved from host code. Zero-data phase `03` is still a write-shaped
transaction and remains unavailable to hardware.

These callers do not establish a full settings read/backup map. Neither the
comparison blocks' purpose nor arbitrary addresses are safe to infer or sweep.

The REA dossiers corroborate this sequence. To reproduce the instruction check
without executing the application:

```sh
objdump -d -Mintel --start-address=0x413910 --stop-address=0x413c0e 'Gaming Mouse 3.0.exe'
```

## A825 comparison — hypothesis for Blaze, not hardware commands

The [official A825 reference application](vendor-reference.md#a825-comparison)
has a helper at `0x455a40` that builds:

```text
07 18 03 ii aa AA dd nn   # one frame per data byte
07 18 09 00 aa AA 00 nn   # after about 4 ms
07 18 00 00 aa AA 00 00   # after about 12 ms
```

`ii` is the byte index, `aa AA` a little-endian base value, `dd` the data byte,
and `nn` total length minus one. Interpreting these as staging/commit/finalize
and the base as configuration memory is inferred. Another routine near
`0x486160` uses phases `03` / `05` / `00` and GetFeature.

Matching USB IDs, signer metadata, report ID, and frame layout make A825 a
useful lead. They do **not** validate addresses, storage capacity, timing,
safe ranges, or persistence on the Blaze. Do not replay these frames.

## Unresolved, in implementation order

1. Validate the static profile candidate against a controlled device observation;
   assign the remaining response bits only with evidence, not plausibility.
2. Establish the recovered reader's firmware-side preparation effects before
   allowing its SET_REPORT transactions; fixed source ranges are now recorded.
3. Which addresses/fields control lighting, and how are original values restored?
4. What are command `16`, commit/status semantics, error responses, and delays?
5. Map DPI indexes, polling indexes, profiles, and buttons using application
   data flow plus device readback. Establish persistence by power-cycle testing.
6. Decode macro records only after ordinary settings can be backed up/restored.
