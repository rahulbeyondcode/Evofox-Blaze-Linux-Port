# Physical-device captures

This directory is reserved for sanitized, read-only observations from the physical EvoFox Blaze on Linux.

## Suggested files

Use the actual PID in filenames:

```text
lsusb-summary.txt
lsusb-30fa-1440-verbose.txt
lsusb-tree.txt
hidraw-map.md
hidraw-interface-N-udev.txt
hidraw-interface-N-report-descriptor.hex
hidraw-interface-N-report-descriptor-decoded.txt
environment.md
```

If the PID is `1e01`, use it instead of `1440`.

## Environment metadata

Record in `environment.md`:

- Linux distribution and version.
- Kernel version from `uname -a`.
- Desktop/session type if permission behavior matters.
- Mouse label/model markings.
- USB connection type: direct, hub, dock, or KVM.
- Whether the device was freshly power-cycled.
- Any existing onboard settings visible before testing.

## Sanitization

Before committing captures, remove or replace:

- Usernames and home-directory paths.
- Hostnames.
- Unrelated USB devices.
- Device serial numbers if they are unique and not needed for protocol work.
- `/dev` node numbers when quoting them as permanent identities; node numbers are session-specific.

Do not sanitize VID, PID, interface number, usage page, usage, report descriptor bytes, endpoint descriptors, or device revision. Those are the evidence this directory exists to preserve.

## Evidence update rule

Whenever a capture resolves an item in [Open questions](../open-questions.md):

1. Link the capture from the resolved statement.
2. Record the exact command or program version used.
3. Move the item to the resolved section or mark it complete.
4. Update [Recovered HID protocol](../hid-protocol.md) if it changes a protocol fact.
5. Keep revision-specific facts labeled with VID, PID, and `bcdDevice`.
