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
provide a hotplug lock or exclusive access against other programs.

Before committing additional evidence, remove usernames, hostnames, serial
numbers, unrelated devices, and permanent claims about hidraw numbering.
Keep VID/PID, revision, interface numbers, usage values, descriptor bytes,
tool versions, exact commands, and errors/coverage limits.

Connection topology, physical label, initial settings, power-cycle history,
and persistence were not established by this first capture. Existing access
permissions do not prove that every Linux host will work without a udev rule.
