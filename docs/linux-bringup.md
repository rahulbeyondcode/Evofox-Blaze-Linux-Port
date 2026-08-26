# Safe Linux bring-up

This procedure is for the first session on a native Linux machine with the physical EvoFox Blaze attached. The first session is evidence collection, not configuration writing.

## Safety rules

1. Do not run the Windows executable.
2. Do not send HID feature reports until the descriptor and current state have been captured.
3. Do not issue firmware, bootloader, reset, erase, or raw-flash commands.
4. Do not assume `/dev/hidrawN` numbering is stable.
5. Select devices by VID, PID, usage page, usage, interface, and report characteristics.
6. Save the device's initial observable state before the first write.
7. Make the first write small, reversible, and visually verifiable.
8. Power-cycle only after the applied setting and readback are understood.

## Phase 1: USB identity

Run:

```bash
lsusb
lsusb -t
```

Look specifically for either:

```text
30fa:1440
30fa:1e01
```

Then capture the matching descriptor. Use the PID actually observed:

```bash
lsusb -d 30fa:1440 -v
```

If the mouse reports `1e01`, substitute that PID. Save outputs under [device-captures](device-captures/README.md).

Record:

- Manufacturer and product strings.
- `bcdDevice` revision.
- Number of configurations and interfaces.
- Every interface number and alternate setting.
- HID descriptor lengths.
- Endpoint addresses, directions, transfer types, and packet sizes.

## Phase 2: map hidraw nodes

List properties without writing to any node:

```bash
rg -n . /sys/class/hidraw/hidraw*/device/uevent
```

For each candidate node:

```bash
udevadm info --query=property --name=/dev/hidrawN
udevadm info --attribute-walk --name=/dev/hidrawN
```

Replace `hidrawN` with the actual node. Record all nodes belonging to VID `30fa` and the observed PID; a composite mouse may expose several.

## Phase 3: capture HID report descriptors

For each matching hidraw node, resolve and copy its report descriptor in human-readable hexadecimal:

```bash
realpath /sys/class/hidraw/hidrawN/device/report_descriptor
xxd -g 1 /sys/class/hidraw/hidrawN/device/report_descriptor
```

If available, `hid-recorder`, `usbhid-dump`, or a small descriptor parser may provide a decoded view. Record the tool and version with the capture so later results are reproducible.

The critical facts to confirm are:

- A collection with Usage Page `ff01`, Usage `0001`.
- A collection with Usage Page `ff00`, Usage `0001`.
- Feature report ID `07`.
- Feature report byte length, likely but not yet proven to be eight.
- Interface number associated with each usage page.

The public GM320 report described in [Related hardware research](related-hardware-research.md) makes `30fa:1440`, report ID `07`, and prefix `07 18` useful expectations, not acceptance criteria. A Blaze that differs must be documented as a revision instead of being forced into the sibling device's model.

## Phase 4: permissions

Do not make a system-wide permission change until the IDs are confirmed. A likely `udev` rule is:

```udev
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="30fa", ATTRS{idProduct}=="1440", TAG+="uaccess"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="30fa", ATTRS{idProduct}=="1e01", TAG+="uaccess"
```

Only the rule matching real hardware is necessary. A production rule should be narrowed further if interface attributes make that possible.

## Phase 5: read-only probe

Build a small program that:

1. Enumerates HID devices by VID/PID.
2. Prints path, interface number, manufacturer, product, serial, usage page, usage, and report lengths.
3. Opens only the `ff01`/`0001` configuration collection.
4. Allocates the descriptor-derived feature-report length.
5. Optionally performs only known `GET_FEATURE` requests beginning with report ID `07`.
6. Hex-dumps responses without interpreting unknown bytes.

Even a feature-report read is an interaction with the device. Keep it behind an explicit `--read-feature` flag and show the exact request before sending it.

The read-only probe must not call:

```text
hid_send_feature_report
HIDIOCSFEATURE
libusb_control_transfer with SET_REPORT
```

## Phase 6: first controlled write

Only after descriptors and readback are understood:

1. Save all available current feature reports.
2. Choose a reversible setting such as LED brightness or a single DPI colour.
3. Display the exact before/after packet.
4. Require interactive confirmation.
5. Send one report.
6. Read back immediately.
7. Verify ordinary mouse input still works.
8. Restore the original setting.
9. Unplug/replug and determine whether the change persisted.

Do not start with button mappings, macros, profile-memory bulk writes, polling rate, or anything resembling firmware control.

## Persistence test matrix

For each implemented setting, distinguish:

| Event | Question |
|---|---|
| Close configuration program | Does the setting remain? |
| Reopen device node | Does the setting remain? |
| USB unplug/replug | Does the setting remain? |
| Host reboot | Does the setting remain? |
| Mouse connected to another host | Does the setting remain? |
| Hardware profile switch | Is the value profile-specific? |

Only settings surviving disconnection qualify as onboard-memory programming.
