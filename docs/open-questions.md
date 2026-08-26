# Open questions and research ledger

This file is the authoritative pending-work list. Move an item to “Resolved facts” only when evidence is saved in the repository.

## Priority 0: required before sending any write

- [ ] Which PID does the physical EvoFox Blaze expose: `1440`, `1e01`, or both under different conditions?
- [ ] What is the device's `bcdDevice` revision?
- [ ] How many USB interfaces and hidraw nodes does it expose?
- [ ] Which Linux interface/node corresponds to Usage Page `ff00`, Usage `0001`?
- [ ] Which corresponds to Usage Page `ff01`, Usage `0001`?
- [ ] Is report ID `07` present in the physical HID report descriptor?
- [ ] What is the exact `FeatureReportByteLength` for `ff01`?
- [ ] Are feature GET reports accepted without first sending a command report?
- [ ] Can all current settings be read before changing anything?
- [ ] Does Linux need a `udev` rule only, or are there kernel/desktop permission conflicts?
- [ ] Does the physical descriptor and harmless read behavior match the A825-family evidence in [Related hardware research](related-hardware-research.md)?

How to resolve: follow [Linux bring-up](linux-bringup.md) and commit sanitized outputs under `device-captures/`.

## Priority 1: core protocol

- [ ] Confirm that normal configuration frames are eight bytes long.
- [ ] Determine the request/response role of command `0x18`.
- [ ] Assign semantics to all ten arguments of the `0x18` builder.
- [ ] Verify the family-derived byte layout: operation in byte 2, index in byte 3, little-endian address in bytes 4–5, data in byte 6, and count/control in byte 7.
- [ ] Verify whether byte-2 phases `03`, `09`, and `00` mean stage data, commit, and finalize on the Blaze.
- [ ] Determine the meaning of command `0x16`.
- [ ] Catalog all report command bytes used by the 24 SetFeature call sites.
- [ ] Catalog the five GetFeature call sites and expected response layouts.
- [ ] Determine whether any command family has a checksum, sequence number, unlock step, or commit command.
- [ ] Determine why the app requires both `ff00` and `ff01` interfaces.
- [ ] Determine the required delays between commands and whether 2 ms/10 ms are conservative or mandatory.
- [ ] Determine whether PID `1440` and PID `1e01` use identical packets.

How to resolve: combine differential feature-report observation on Linux with deeper static data-flow analysis. Start with readback and one reversible setting; preserve exact before/after packets and restore the original value immediately.

## Priority 1: settings semantics

- [ ] Map `DPI_SET0` through `DPI_SET5` indexes against the official A825 23-value table, then verify through Blaze readback.
- [ ] Determine supported DPI range and step size.
- [ ] Map the four `USB_SPEED` indexes to the A825 family rates 125/250/500/1000 Hz.
- [ ] Determine whether `DPI_SPEED` changes hardware sensitivity or Windows pointer settings.
- [ ] Determine whether `WHEEL_SPEED` changes hardware or operating-system state.
- [ ] Determine `FIRE_TIME` units and safe range.
- [ ] Map each of the 16 lighting labels to on-wire values.
- [ ] Map brightness, direction, symmetry, single-colour, cycle speed, and reactive-light fields.
- [ ] Explain `LED_CYC_TIME` versus `LED_CYCTIME`.
- [ ] Explain `MODE_LIGHT`, `BOOT_LED`, and `CFG_LED`.
- [ ] Identify valid button action codes.
- [ ] Explain why eight declared keys coexist with a `K9_MAP` entry.

## Priority 1: profiles and onboard memory

- [ ] Are all four profiles physically stored in the mouse?
- [ ] Is `Config4` a fifth profile, a shared block, or a template artifact?
- [ ] Why does the fourth profile read `Game III` in one config and `Media` in the UI skin?
- [ ] Which fields are global and which are per-profile?
- [ ] Is there an explicit save/commit operation?
- [ ] Do settings survive program exit, USB power loss, host reboot, and transfer to another computer?
- [ ] Can the complete onboard state be backed up and restored safely?
- [ ] Reconcile the datasheet's ambiguous `32kb` capacity, the generic driver's 16-bit address field, `EEP_CAP=4`, and the GM320 author's reported “65 KB” sweep.

## Priority 2: macro format

- [ ] Decode the large decimal strings in macro `.dat` files.
- [ ] Identify event record size and endianness.
- [ ] Map key press/release, mouse click, X/Y motion, delay, DPI, and LED events.
- [ ] Determine delay units and limits.
- [ ] Determine maximum macros, events, and storage bytes.
- [ ] Confirm the UI statement that 12 macro groups are supported.
- [ ] Determine the meaning and calculation of `MacMd5`.
- [ ] Determine the purpose and accepted values of `DAT_VER`.
- [ ] Determine `SOFT_HARD_MAC` semantics.
- [ ] Determine whether macros execute entirely onboard.
- [ ] Separate ordinary macros from PUBG/gun data.

## Priority 2: product/revision behavior

- [ ] Confirm whether the physical Blaze contains A825 silicon or a protocol-compatible relative. Protocol/descriptor agreement is sufficient for development; opening the mouse is optional and should occur only if the owner chooses.
- [ ] Determine Wuxi Yingsite/Instant Microelectronics' exact role for the Blaze: controller supplier, software vendor, ODM, or some combination.
- [ ] Explain the apparent A825-family PID pattern: EvoFox `1440`/`1e01`, generic reference `1e01`/`1441`, and GM320 `1440`.
- [ ] Recheck [libratbag issue 1795](https://github.com/libratbag/libratbag/issues/1795) for a published capture, implementation, or register map.
- [ ] Determine whether another open-source project has since implemented this protocol family. The bounded 2026-08-26 search found none.
- [ ] Decide whether contacting the GM320 issue author for the reported capture is worthwhile after the Blaze descriptor is known.

## Priority 3: application behavior

- [ ] Determine whether the original application modifies Windows registry pointer settings in addition to mouse hardware.
- [ ] Determine the purpose of audio/mixer imports and sound UI assets.
- [ ] Determine whether any configuration is stored only in local INI files.
- [ ] Determine whether encrypted macro export is proprietary file obfuscation or a standard cryptographic construction.
- [ ] Verify the Authenticode signature cryptographically if provenance auditing becomes necessary.

## Explicit non-goals until separately authorized

- Firmware flashing.
- Bootloader entry.
- EEPROM erase or raw memory writes.
- Redistributing vendor artwork, fonts, or executable code without confirming rights.

## Resolved facts that should not be rediscovered

- [x] The repository installer exactly matches the official downloads by SHA-256.
- [x] It is an Inno Setup 5.5.7 Unicode package.
- [x] The actual application is native 32-bit Windows code, not .NET/Electron/Qt.
- [x] The application directly imports Windows HID and SetupAPI functions.
- [x] The installer contains no custom `.sys` driver.
- [x] The accepted VID/PID pairs are `30fa:1440` and `30fa:1e01`.
- [x] The application selects Usage `0001` on vendor pages `ff00` and `ff01`.
- [x] The configuration path uses HID feature reports and report ID `07`.
- [x] Feature-report length is obtained from device capabilities, not hard-coded.
- [x] A command builder beginning `07 18` has been statically recovered.
- [x] Four profiles, eight programmable buttons, six DPI controls, lighting, polling, rapid fire, and macros are present in the Windows feature model.
- [x] Wuxi Yingsite/Instant Microelectronics publishes the A825 mouse-controller datasheet and an official generic reference driver.
- [x] The generic A825 configuration uses `30fa:1e01` and `30fa:1441`, overlapping the EvoFox application's accepted IDs.
- [x] The generic A825 driver uses direct HID feature reports, report ID `07`, command `18`, and fixed eight-byte frames; it bundles no custom kernel driver.
- [x] A public A825 mouse report independently matches `30fa:1440`, `07 18`, four profiles, and six DPI stages.
- [x] The A825 datasheet supplies family-level candidate limits: four stored groups, 23 DPI values up to 12,800 CPI, and 125/250/500/1000 Hz USB report rates.
- [x] No matching libratbag device definition or implementation was present in the 123 upstream definitions scanned on 2026-08-26.
