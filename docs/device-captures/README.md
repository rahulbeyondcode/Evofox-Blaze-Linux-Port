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
