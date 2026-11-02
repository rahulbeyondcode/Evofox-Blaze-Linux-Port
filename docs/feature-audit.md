# Offline feature audit — 2026-11-02

The user requested an independent test-based check while unavailable, including
the Windows/Super problem and discrepancies across the full interface.
**This is a software audit, not a claim that the whole application works on
hardware.** No real mouse reads, writes, restores, event monitoring, USB resets,
permission changes or Windows executable execution were performed.

## Reproduce without desktop windows

**Original audit result: 413 tests passed, with no skips, on authenticated private Xvfb.**
This includes 13 added audit/regression cases beyond the 400-test recorder
checkpoint. No active-desktop test windows were opened.

Subsequent immediate-activation implementation passed **434 tests, no skips**.
The matrix's activation row reflects that newer explicit opt-in path; its hardware
effect remains unvalidated. See the [integration checkpoint](reverse-engineering.md#opt-in-immediate-activation-integration--2026-11-02).

Subsequent saving-overlay/minimal-tooltip work passed **442 tests, no skips**.
The user has since reported no-replug behavior working after their own opt-in
Apply; that report is separate from the simulated test results.

```sh
python3 -m tools.run_virtual_tests --xvfb /path/to/trusted/Xvfb
```

The local executable and no-display fallback are documented in
[headless testing](ui-development.md#tests-and-visual-review). Tests use saved
captures, synthetic events delivered only to GTK widgets on the private display,
and fake mouse memory/feature ioctls. Fake transactions run the real scoped
writer, backup and strict saved-journal validator; they do not emulate firmware
behavior or the Pop!_OS compositor.

## What was checked

| Area | Software coverage / present status | Hardware limit |
|---|---|---|
| Four-page shell | Navigation, resizing, dragging, scaled hit targets, rendering, actual mapped-window footer, busy and modal guards | Reference visual baseline preserved; not an exhaustive pixel comparison on every display |
| Native assignments | All 11 built-in menu actions route to each of the seven supported vendor rows; eighth row remains preview-only. Draft, Cancel, net-change, retained Left Click and exact backup/readback/restore tests | Historical side Back/Forward user report after replug; not behavioral proof of every built-in |
| Keyboard shortcuts | Separate taps, modifier sides, six-box limit, invalid/duplicate chords, focus loss, timeout, stale state, Save-only staging, mixed Apply, failures and strict verification | Ctrl+Alt+Down has a successful user report; arbitrary chords, persistence and modifier release are not generally proven |
| Windows/Super fallback | Explicit Windows button → Ctrl+Super+Left → Save → GUI Apply → real scoped writer on fake memory → strict journal → offline restart recovery. Exact stored HID usage `e3` checked; original records preserved | Does not suppress Pop!_OS's launcher or prove that a physical Super tap reaches the application |
| Saved-state recovery | Latest verified journal only; later incomplete/failed operations block stale fallback. Startup and inspection stay offline | Saved state is not a fresh device reading |
| Read assignments | Explicit confirmation, native/shortcut decoding, unknown-layout refusal, exact operation bounds and failure retention | New full-assignment reader has offline coverage, not a newly recorded agent hardware test |
| Polling | Main Performance Apply → confirmation → real fake-device transaction → backup/readback → updated displayed baseline. All four supported codes and exact scoped restore tested | Historical stored-byte change/restore, not measured USB frequency or instant activation |
| DPI | Existing enabled-stage-index CLI planner has offline tests; physical value controls and stage enabling stay disabled | No physical CPI-value programming/readback or new stage-change hardware test |
| Macros | Page renders; Record, Insert and repeat controls are intentionally inactive and cannot launch workers or change drafts | Macro programming/custom sequences are not implemented |
| Lighting | Page renders; effect/color/brightness/speed/direction controls remain inactive. Static brightness codec/arithmetic have offline tests | No original-value device readback/restore or lighting writes |
| Host sensitivity/scroll/double-click speed | Reference values; controls remain disabled and cannot silently change host settings | Not implemented |
| Profiles/import/export/reset | Disabled main-page controls; assignment-menu profiles are explicit no-ops, preserving drafts | Hardware profiles, full-profile import/export and reset are not implemented |
| Media/Show desktop/menu macros | Clickable placeholders close menus without staging assignments or writing anything | Not implemented; these are not working device settings |
| Physical Button 8 / native slot 9 | Preview menu only; existing backend refuses programming and preserves its independent records | Needs its own bounded backup/read/write/restore work |
| Failure details | Partial/failed journals never become verified state; commit warnings and original backup guidance are shown offline | A failure does not prove the device stayed unchanged |
| Immediate activation | Newer opt-in integration adds the fixed candidate after verified new Apply with `--experimental-activation`; ordinary Apply stays unchanged. Consent, same-handle lock, readback ordering, strict journals and failures have fake-device coverage | Subsequent user report confirms the prompted workflow works without replug; not a raw event capture or validation of all firmware effects |
| Live button tester/full-device backup | Not advertised as implemented by these tests | Both remain unavailable; block/transaction backups are partial |

Disabled controls on **every page** were invoked both through their GTK signals
and the normal dispatcher, checking that they preserve polling/button drafts
and start no worker. Native menu routing includes all eight visible rows,
including refusal to stage unsupported row 8. Placeholder behavior is intentional,
not a passing implementation test for the missing feature.

## Reproduced defects fixed

1. **Error details was disconnected:** its hit target was always enabled but
   had no action, and the renderer was not passed its error flag. It is now
   painted/enabled only for a real error and opens the existing diagnostics
   window's details tab without starting a device operation. The footer reserves
   space so the details button does not cover the failure text.
2. **Failure details were blank/lost:** the diagnostics view cleared the text
   area on failure even when detailed journal diagnostics existed. Details now
   propagate from failed reads, Apply verification and startup recovery; plain
   worker errors have a plain-text fallback. Successful loading/verification
   clears stale errors. Incomplete Apply retains its drafts and commit warning.
3. **Polling commit warnings were omitted:** the failure-summary parser missed
   the `config_write_intent` event name. It now recognizes commit requests from
   all three write backends, including torn journals, without accepting partial
   data as verified state.
4. **Saved-capture chooser missed a busy guard:** direct signal/handler invocation
   could open it while another operation was running. It now refuses that path,
   consistent with other guarded controls.

New tests first reproduced the error-details, commit-warning and busy-guard
failures, then passed after the fixes. The full test suite is rerun after them.
The final complete run passed all 413 cases.
Recorder/failure screenshots were also inspected on an authenticated private
display; these are disposable local artifacts, not redistributable skin assets
or evidence of device behavior.

## What still needs a person and explicit hardware consent

- Compare a changed assignment immediately after Apply, before unplugging. The
  earlier replug instruction was conservative, not proof that replug is required.
- If necessary, explicitly approve a single bounded activation-candidate test.
  It may activate all stored settings, not just one selected row; no such test
  was approved/run by the agent. The user subsequently reported no-replug success
  after their own GUI Apply. The GUI opt-in remains experimental;
  do not enable activation in ordinary Apply by default based on offline tests alone.
- Confirm real key release, reconnect/power-cycle persistence and device-specific
  physical-button behavior separately. Fake memory cannot establish these.
- User-specific visual/input discrepancies may still require screenshots or
  reproduction details later. Passing tests cannot establish every desktop or
  keyboard-layout behavior.

See the [activation checkpoint](reverse-engineering.md#immediate-activation-investigation--2026-11-02)
and [Windows/Super checkpoint](ui-development.md#windows-super-launcher-interception--2026-11-02)
for the existing evidence and authorization boundaries.
