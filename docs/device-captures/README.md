# Device evidence

- [2026-10-23, 30fa:1440 / revision 0100](2026-10-23-30fa-1440-0100/probe.json):
  USB/HID descriptor bytes, hashes, decoded collections/report lengths,
  access checks, and kernel/Python/tool versions. Sysfs-only capture; no
  device node opened. `capture_node` is a snapshot-local index, not a device ID.
  [lsusb.txt](2026-10-23-30fa-1440-0100/lsusb.txt) separately records
  `lsusb -d 30fa:1440 -v`, including its tool version and exit status. Its HID
  report descriptor display is unavailable; the sysfs bytes above fill that gap.
- [Standalone GET_FEATURE 07](30fa-1440-0100-get-feature-01/feature-read.jsonl):
  `30fa:1440` / revision `0100` / interface 1, eight-byte reply
  `07 00 58 09 1f 00 23 7b`. One request, no SET_REPORT or retries. The journal
  preserves baseline hash, descriptor, handle validation, exact ioctl/buffer,
  raw return count, timestamps, and completion; no response fields are decoded.
  `python3 -m evofox_blaze.status --capture <feature-read.jsonl>` separately
  inspects the saved record offline and labels static profile candidates; the
  original capture is never rewritten with those interpretations.
- [First fixed state read](30fa-1440-0100-state-read-01/state-read.jsonl):
  separately approved staged read at `0x0018`; 18 SET / 8 GET, no commit/retry.
  Collected `19 3f 32 00 f3 ff 01 00`. This is an eight-byte state record, not
  a full mouse backup. `python3 -m evofox_blaze.state_capture --capture <journal>`
  validates and interprets it offline.
- [Polling test](30fa-1440-0100-polling-test-01/configuration.jsonl) and
  [restore](30fa-1440-0100-polling-restore-01/configuration.jsonl): separately
  approved temporary polling code `01 → 00`, complete readback, and explicit
  restoration/readback of the original eight bytes. Each journal has one
  settings commit, 46 SET / 16 GET, and no retry. Each directory contains a
  private `original-state.json` partial backup. Physical polling frequency and
  power-cycle persistence were not measured. Neither settings test changed
  lighting, CPI tables, button bindings, macros, or firmware.

## Session bring-up checkpoint — 2026-10-25

The initial state read plus the polling change/restore used **five fixed state
reads and two settings commits** in total: 110 SET_FEATUREs and 40 GET_FEATUREs.
These totals exclude the earlier standalone GET and descriptor/metadata reads.
The final restore readback matched the complete original block
`19 3f 32 00 f3 ff 01 00`; no later device-state claim is implied.

Each hardware test had explicit user approval. No automatic retry, reset,
firmware command, driver detach, permission change or input-event read was
performed. The backups cover only eight bytes at `0x0018`, not the full mouse.
Physical polling frequency and power-cycle persistence remain untested; click
monitoring and physical-button identification remain unimplemented. UI progress
is recorded separately in [ui-development.md](../ui-development.md).

## Native button checkpoint — 2026-10-27

- [Initial button table](30fa-1440-0100-button-read-01/button-read.jsonl): one
  explicitly approved new-region `0x0008`/8-byte read, 18 SET / 8 GET, no commit.
  Original bytes: `21 22 23 2e 2e 35 00 26`. The user identified their existing
  side assignments as Ctrl+Windows+Left/Right; no input event was recorded.
- [Side remap](30fa-1440-0100-button-remap-01/button-configuration.jsonl): after
  the user's fresh permission to change the side assignments, native slot 4
  became Back and slot 5 Forward. A fresh read, durable
  [backup](30fa-1440-0100-button-remap-01/button-backup.json), one commit, and full
  readback produced `21 22 23 24 25 35 00 26`. Other six bytes and all shortcut
  extension records were preserved. 46 SET / 16 GET; no retry or restore.
- [Behavior report](30fa-1440-0100-button-remap-01/behavior-validation.json): the
  user selected **Works after replug** for Back/Forward. This is a user report,
  not an event capture; immediate activation, every physical button, arbitrary
  shortcuts and long-term retention are not thereby validated. The raw write
  journal intentionally continues to say `behavior_verified: false` because
  readback alone cannot establish behavior. The later report is a separate file.

This milestone totals **three button-block reads and one commit: 64 SET / 24 GET**.
Together with the earlier polling milestone: eight fixed-block reads, three
settings commits, 174 SET / 64 GET, excluding the standalone GET and metadata.
No setting was automatically restored: the Back/Forward mappings were left in
place after the user's successful test. All these approvals are consumed.

## Shortcut backend inspections — 2026-10-27

Two fresh, separately approved inspections were completed with **no settings
commit**. Both approvals are consumed; neither included writes, restores or input
monitoring.

- [Metadata journal](30fa-1440-0100-shortcut-headers-01/shortcut-headers.jsonl):
  74 fixed blocks, **1332 SET / 592 GET**. Three nonzero descriptors reference
  `0400`, `0408` and `0410`; macro endpoint `0418`, auxiliary pointers
  `0420/0428/0430`, stored endpoint `0438`. Fresh button bytes were
  **`21 22 23 24 23 35 00 26`**, different from the historical side-button test.
  Do not replace this newer slot-5 Right Click observation with old Forward bytes.
- [Payload journal](30fa-1440-0100-shortcut-payload-01/shortcut-payload.jsonl):
  exactly `0400..045f`, **216 SET / 96 GET**, associated with the saved metadata.
  The three original records decode as Ctrl+Super+Left, Ctrl+Super+Right and
  Super+Tab. Each has a repeat prefix of one and press-only keyboard events with
  four ticks per event, corroborating the source-derived codec. The last record
  is linked by native slot 9's descriptor; this does not prove physical button
  behavior or authorize slot-9 writes. The candidate tail contains nonzero bytes;
  it must never be assumed blank or backed up from defaults.

These snapshots are partial, not complete-device backups. The journals are
private and immutable. `authorization.json` records each separate scope. Total
new inspection traffic: **1548 SET / 688 GET**. No shortcut write or restore has
yet been exercised. The experimental tail-pointer policy still needs explicit
write approval and behavioral testing; it is not enabled as a working UI action.

### Subsequent F13 write/readback — user report below

The user separately chose **Approve F13 test**. That approval was consumed by
the [guarded transaction](30fa-1440-0100-shortcut-f13-test-01/shortcut-configuration.jsonl):
**3126 SET / 1376 GET, three settings commits**, strict scoped backup and full
readback succeeded. Exactly three eight-byte blocks changed: `0438` (F13 record),
`00c8` (native slot-5 descriptor) and `0008` (selected button link). All original
payload/auxiliary bytes and allocation metadata matched their fresh originals.
The [backup](30fa-1440-0100-shortcut-f13-test-01/shortcut-backup.json) contains both
scoped states and is private; it is not a full-device backup.

Last recorded native table is **`21 22 23 24 2e 35 00 26`**: UI button 4/native
slot 5 is stored as F13, with the new record pointer `0438`. **No restore was
executed or authorized.** No automatic retry, activation/reset or input monitor
was used. Readback is not physical behavior evidence; the user still needs to
replug and test whether the key is emitted. Do not repeat this write on resume.

Subsequent [user report with screenshots](30fa-1440-0100-shortcut-f13-test-01/behavior-validation.json):
the test opened desktop Settings and the recorder stopped on focus loss. This is
consistent with desktop interception of Tools/F13 and supports test-key emission;
no raw input events were captured. Replug, modifier release, Ctrl+Shift+Down and
general persistence are not confirmed by the report. It authorizes no additional
operation. The newest GUI integration enables experimental chord Apply with
fresh scoped backup/readback and separate F1 restore controls; it added no live
device operation, and no restore has been executed.

### Ordinary shortcut user report — 2026-11-02

The user replied **"It is working"** after being prompted to assign Ctrl+Alt+Down
through GUI Save/Apply and test workspace switching with the mouse button. This
is a successful user behavior report, not a new versioned hardware journal or raw
input capture. Reconnect/persistence and modifier release were not separately
confirmed in the reply; the exact selected button and current bytes were not
inspected. No original capture was altered, no new agent-side mouse operation
was performed, and no read/write/restore/monitoring approval is implied.

Offline `button_capture` and `button_config_capture` validate the exact fixed
sequences, not arbitrary reports. Native restore must be separately authorized;
it has offline tests, not a recorded live test. The `2e` links are backed up, but
their untouched shortcut data is **not** included in this eight-byte backup.

### Immediate activation user report — 2026-11-02

After launching `gui --experimental-activation`, the user was prompted to assign
Ctrl+A to Button 4, Save, Apply, wait for "activation sequence sent", and test
selection in a text editor **without disconnecting the mouse**. They replied:
"Perfect it works without unplougging and replugging the mouse."

This supports immediate behavior for the tested GUI workflow. The exact selected
assignment/current board bytes and transaction journal were not independently
inspected, and no input events were captured. It does not establish every action,
polling frequency, modifier-release behavior, power-cycle retention, or the
candidate command's complete firmware meaning. Original journal flags/captures
are unchanged. No new agent-side live command was authorized or performed; do
not repeat this test or restore its setting automatically on resume.

Reproduce with `python3 -m evofox_blaze.probe --capture <new-directory>` from
the repository root. The destination must not exist. The probe does not need
root or hidraw-node access when sysfs descriptors are readable.

Reproduce a feature read with `python3 -m evofox_blaze.feature_read
--read-feature --baseline <probe.json> --capture <new-directory>` (Linux
x86-64). It requires ordinary read access to the matching hidraw node and
refuses existing destinations. The JSONL intent is flushed before the only
GET_FEATURE; errors, short replies, and unexpected report IDs fail without retry.
An intent without a response/completion records an uncertain or interrupted
attempt, not proof that no request reached the device. Revalidation does not
provide a hotplug lock or exclusive access against non-cooperating programs.
Current tools take a nonblocking advisory hidraw lock before metadata/feature
I/O; the earlier recorded captures predate that software lock.

`state_read` requires **both** `--read-state` and
`--accept-staged-read-risk`; `config_write` requires `--accept-write-risk`.
Read their `--help` and protocol limits first. They accept only the exact
captured revision/descriptor and fixed block `0x0018`, refuse existing capture
destinations, and journal each feature request before I/O. A settings failure
does not trigger automatic rollback; the retained backup must be reviewed and
restored through a separately authorized operation. GUI-created evidence goes
to the user's XDG state directory, not this versioned evidence directory.

Before committing additional evidence, remove usernames, hostnames, serial
numbers, unrelated devices, and permanent claims about hidraw numbering.
Keep VID/PID, revision, interface numbers, usage values, descriptor bytes,
tool versions, exact commands, and errors/coverage limits.

Connection topology, physical label, initial settings, power-cycle history,
and persistence were not established by this first capture. Existing access
permissions do not prove that every Linux host will work without a udev rule.
