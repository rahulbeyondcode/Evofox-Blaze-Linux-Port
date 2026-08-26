# EvoFox Blaze Linux port research

This directory is the handoff package for building a native Linux configuration utility for the EvoFox Blaze programmable gaming mouse. It records the static analysis completed on 2026-08-26, the evidence behind the feasibility assessment, and the work that remains when the physical mouse is available on Linux.

## Current conclusion

A Linux port is highly feasible, but it has not yet been tested against the physical mouse. The end product is intended to be a graphical configuration utility comparable to the Windows application; a CLI is only the diagnostic and protocol-validation foundation.

The official Windows application uses normal user-space HID APIs. It does not ship a custom kernel driver. It finds USB vendor `30fa`, accepts product `1440` or `1e01`, selects vendor-defined HID interfaces, and exchanges feature reports whose first byte is report ID `07`. At least one core command path constructs a straightforward eight-byte frame beginning `07 18`.

This is protocol reconstruction, not a source-code port. The Windows program was never executed during analysis.

## Evidence vocabulary

Every document uses these meanings:

- **Confirmed:** directly observed in the official installer, extracted payload, PE metadata, strings, or disassembly.
- **Inferred:** strongly suggested by confirmed evidence but requires a physical-device test.
- **Unknown:** must not be treated as an implementation fact yet.

## Read these files in order

1. [AI handoff](ai-handoff.md) — compact context for another AI or developer.
2. [Software provenance](software-provenance.md) — official URLs, hashes, and installer identity.
3. [Payload and application](payload-and-application.md) — extracted program architecture and dependencies.
4. [Payload inventory](payload-inventory.md) — files contained in the installer and what they imply.
5. [Recovered HID protocol](hid-protocol.md) — the most important reverse-engineering evidence.
6. [Feature and data model](feature-model.md) — profiles, buttons, DPI, lighting, macros, and configuration fields.
7. [Related hardware research](related-hardware-research.md) — the strongest public protocol-family lead and its limits.
8. [Linux bring-up](linux-bringup.md) — safe procedure for the first session with the mouse.
9. [Implementation roadmap](implementation-roadmap.md) — staged plan from probe to GUI.
10. [Open questions](open-questions.md) — explicit unknowns and how to resolve them.
11. [Static research record](analysis-log.md) — reproducible commands and important disassembly locations.
12. [Device captures](device-captures/README.md) — where to store Linux USB/HID observations.

## Quick facts

| Item | Value | Status |
|---|---|---|
| Product | EvoFox Blaze Gaming Mouse | Confirmed |
| Official platform | Windows 10/11 | Confirmed |
| Installer | `evofox-blaze.exe` | Confirmed |
| Installer SHA-256 | `c45662764d9847e3b14c34d19a745e6b6b34a7e966889be18814cd5513c47468` | Confirmed |
| Installer technology | Inno Setup 5.5.7 Unicode | Confirmed |
| Actual application | `Gaming Mouse 3.0.exe` | Confirmed |
| Application SHA-256 | `9eec736ee629ff9d0684f787a270afe86d064fdcf23e7eb11f921dc7844eee55` | Confirmed from the extracted payload |
| Application architecture | Native PE32 x86, no CLR | Confirmed |
| Kernel driver required | No bundled custom driver | Confirmed for the official package |
| USB VID | `30fa` | Confirmed from disassembly |
| Accepted PIDs | `1440`, `1e01` | Confirmed from disassembly |
| Configuration HID usage | Usage Page `ff01`, Usage `0001` | Confirmed from disassembly |
| Secondary HID usage | Usage Page `ff00`, Usage `0001` | Confirmed from disassembly |
| Configuration report ID | `07` | Confirmed from multiple command builders |
| Feature-report length | Read dynamically from the HID descriptor | Confirmed |
| Likely report length | Eight bytes | Inferred from command construction; must be measured |
| Onboard persistence | Likely | Inferred; must be tested across power cycles |
| Controller-family lead | Instant Microelectronics A825 or a close relative | Strongly inferred from official signer, ID, and packet overlap; physical confirmation pending |
| Existing Linux implementation | None found in current libratbag definitions | Confirmed only for the bounded 2026-08-26 search |
