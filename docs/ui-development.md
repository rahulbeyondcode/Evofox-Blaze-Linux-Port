# Blaze desktop UI milestone

## Progress checkpoint — 2026-10-25

**Visual UI milestone complete and approved by the user after reviewing the app.**

- Delivered the four reference-style GTK screens: Button, Macro, Performance,
  and Backlight, with the original artwork, navigation and resizable layout.
- Included the supplied generated mouse illustration as an optional alternative.
- Retained existing device controls through F1/right-click; unsupported settings
  remain visible but disabled.
- Validation at delivery: **159 tests passed locally**, including native screen,
  resizing, disabled-control and offline-rendering checks. No hardware operations
  were performed during this UI milestone.

Treat this design as the accepted visual baseline for subsequent work. User
approval records visual acceptance, not a measured pixel-perfect comparison or
completion of all hardware features. Remaining work is backend integration and
validation for unsupported settings, while preserving the approved appearance.

## Next-session handoff

**Historical stopping point:** the user-approved visual UI milestone. The newer
[native-button integration](#native-button-integration--2026-10-27) below records
the subsequent selected feature and its bounded hardware validation.

1. Read the root `AGENTS.md`, this checkpoint, and the implementation/next-task
   sections in `README.md`. Check `git status` before editing existing work.
2. Keep the approved appearance. The next work should build on this UI, not
   recreate or redesign it. Ask the user which remaining feature to prioritize.
3. Existing state reads, polling changes and scoped restore already have backend
   support. Native built-in button assignments now have the separate bounded
   support below. Physical DPI values, lighting readback, profiles, custom
   device-side keyboard shortcuts and macros remain incomplete; do not enable
    their writes implicitly. The newest experimental Shortcut Apply checkpoint
    below supersedes the recorder's original draft-only gate.
4. The README identifies a consent-gated DPI-stage index exercise as the next
   protocol task. It is not permission to perform it automatically. Prior UI or
   polling-test approval does not authorize new hardware operations.
5. Use the launch, test and artwork-preparation commands below to recover the
   development environment. The visual-baseline run passed 159 tests; rerun after
   changes. UI source is in `evofox_blaze/desktop.py`, `ui_skin.py`, `ui_layout.py`
   and `gui.py`, with UI coverage in `tests/test_desktop.py` and `tests/test_gui.py`.

These files survive the loss of a chat session in the same working directory.
For a fresh clone or another machine, source, documentation and reference inputs
must first be committed or otherwise backed up. Ignored `.work` artwork and
previews are local-only; re-stage artwork using the instructions below. A new
session should use this written handoff rather than assume it has the old chat.

## Implementation

The default GTK 3 application now has the original **Button, Macro, Performance,
and Backlight** screens. It renders the original 1024 × 737 skin atlases with
separate text, selection and focus layers. Actual GTK buttons provide scaled hit
targets, keyboard navigation, accessible names and tooltips. It is not a video
screenshot with a single click handler.

## Launch on the development host

The reference artwork has been staged in the ignored `.work/ui-skin` directory:

```sh
python3 -m evofox_blaze.gui
```

- Click the four tabs, or use **Ctrl+1–4**.
- **F1** opens optional device controls and saved evidence. There is no
  right-click context menu; Menu/Shift+F10 no longer opens one either.
- Drag the top header or center logo area to move the window. Drag any edge or
  corner to resize; the pointer changes to indicate resize handles.
  The complete reference layout scales uniformly, with letterboxing when needed.
- Tab/Shift+Tab and Enter/Space work on enabled controls and assignment menus.
- The supplied `docs/Software_UI/MouseImage.png` cutout is now the default.
  The original vendor mouse is retained intact and can be selected at launch
  using **`--reference-mouse`**. No artwork toggle/context menu is needed, and
  neither source image is modified or deleted.

```sh
python3 -m evofox_blaze.gui --page performance
python3 -m evofox_blaze.gui --reference-mouse
python3 -m evofox_blaze.gui --diagnostics
python3 -m evofox_blaze.gui --render-previews .work/ui-previews
```

The last command exports `buttons.png`, `macros.png`, `performance.png` and
`backlight.png`, without opening a window or contacting the mouse. It currently
requires the same GTK/Pango/Cairo desktop dependencies and an available display.
`--capture <journal>` continues to open the original offline evidence window.

## What is and is not working

**Nothing contacts the mouse automatically.** Button assignments now start as
**Not read** (the newest baseline fix below supersedes reference startup labels).
The 500-Hz selection, DPI values, sliders, lighting and selected Media profile reproduce
the reference, **not live device state**. Tooltips and the inline status explain
this distinction. Unsupported settings remain visible but insensitive; their
reference colors are retained rather than grayed out to preserve visual fidelity.
No global key recording, audio capture, profile import/export or reset is performed.
Shortcut recording is now available only after explicitly clicking Record in the
focused editor, as described in the newer checkpoint below.
The direct assignment menu below makes unsupported menu entries clickable no-ops,
not working settings.

The existing backend remains available through F1. After an explicitly confirmed
state read (or loading valid saved state evidence), Performance allows a draft
polling target. Apply opens the existing separate confirmation and scoped-backup
workflow; Cancel discards the draft. Saved evidence is not live state, and the
backend re-reads and validates the device before a write. Frequency is not
measured. Failed reads clear the previous candidate. Closing and duplicate
operations are blocked while the backend is busy. Full-profile writes, physical
DPI values, macros and lighting are not enabled. The original button-disabled
baseline is superseded only by the bounded built-in assignments below.

## Native button integration — 2026-10-27

The original milestone below used a prerequisite read and assignment dialog.
Its interaction flow is superseded by [direct assignment menus](#direct-assignment-menus--2026-10-27);
the transport/evidence safety boundaries remain unchanged.

The approved geometry/artwork is preserved. Assignment rows 1–7 now enable only
after **Read button assignments…** (F1 or right-click) or opening a validated
button journal. Labels show stored candidates, not live physical-button events;
`2e` is shown as **Stored shortcut**, not falsely labeled Back/Forward. Row 8
remains disabled because its native slot 9 is outside the captured block.

Click a row to choose a native built-in action in a keyboard-accessible dialog.
**Keep draft** changes no device state; an asterisk marks pending assignments.
**Apply** confirms one scoped table write with durable backup/readback. **Cancel**
discards the page's drafts. At least one standard slot must retain Left Click.
Failed operations and changed/failed evidence loads clear stale draft data.
Button evidence does not enable polling and state evidence does not enable buttons.

F1 also provides **Restore button backup…**, separately confirmed and refusing
intervening edits. Busy state blocks duplicate operations, navigation and normal
window closure. A successful write/restore instructs the user to physically unplug
for about ten seconds and reconnect; no automatic reset/finalize is sent.

The side-button Back/Forward change was written/read back through the CLI backend
and the user confirmed it working after replug. Other built-in targets are
source-derived, explicitly labeled in the picker. Custom keyboard shortcuts,
custom sequences/macros and rapid-fire physical-slot assignment remain unavailable.
No live input-event listener, grab, injection or software remapping daemon exists.

Implementation: `buttons.py`, `button_read.py`, `button_write.py`, strict
`button_capture.py` / `button_config_capture.py`, offline `button_draft.py`, and
the existing GUI/service/rendering modules. The original evidence records are
immutable; [the later user report](device-captures/30fa-1440-0100-button-remap-01/behavior-validation.json)
is a separate file, not a rewritten hardware journal. Native-button restore has
offline tests only, not a live restoration claim.

Integration validation: **211 tests passed** across the full offline suite,
including seven supported row states, draft/cancel, cancelled editor/Apply,
cross-domain isolation, stale-state clearing, busy guards and native result
loading. These tests perform no device enumeration or feature I/O.

## Direct assignment menus — 2026-10-27

User-requested replacement for the F1 → read → confirm → assignment dialog →
Keep draft flow. The Button page still opens first, with the approved artwork
and geometry. **Every assignment row opens its menu immediately**, without any
device access, saved evidence or intermediate dialog. GTK's native menu shell
handles hover/click cascading to the right, screen-edge fitting, keyboard
navigation and dismissing all levels on a leaf selection.

Root entries: Left Click, Middle Click, Right Click, Backward, Forward, DPI loop,
Extend, Media, Macro, Shortcut and Profile Selection. Extend contains Show desktop,
Double Click, Rapid Fire, LED Loop, DPI + and DPI -. Media contains Browser,
Media Player, Mail, Volume Up/Down, Previous/Next Track, Mute, Play/Pause and
Calculator. Macro contains **No macros found**. Profile Selection contains
hardcoded **Office, Game 1, Game 2, Media**; these are not device profile banks.

Existing built-ins select a pending assignment immediately and update its label;
there is no Keep draft/Save button. All unimplemented leaves (including Show
desktop) are no-ops: they close the dropdown without changing labels, pending
assignments or Apply state. Slot 9's row also opens the menu for preview, but
cannot produce a programming request. Other unknown/Fn/repeat states retain
their backend refusal. No new action code, address or shortcut record is enabled.

**Apply itself is the explicit authorization** for the selected native assignments.
There is no second confirmation modal and the diagnostics window does not open.
The existing worker/subprocess backend still performs exact identity/descriptor
validation, a fresh staged read, a durable partial backup, one scoped commit
when necessary and full readback. Reference labels are never used to manufacture
the original block. Without saved evidence, Left Click/unknown-state validation
is deferred to that fresh read, before setting-data frames.

Progress, success/reconnect guidance and errors appear in the main window. All
navigation, duplicate actions and normal close are blocked while applying;
already-open diagnostics are also disabled. Apply disables only after the saved
strictly validated journal matches the requested assignments (including no-change
results). On failure or missing/mismatched verification, desired selections stay
pending, old captured state is cleared and **no automatic retry or rollback** occurs.
Review the error/evidence before explicitly applying again.

F1 remains available for optional evidence inspection, separately confirmed live
reads and explicit restores. Polling's previous confirmation flow is unchanged.
Physical replug after native writes remains necessary in the user-tested workflow;
the streamlined UI does not introduce reset/finalize commands to avoid it.

Menu data lives in `evofox_blaze/button_menu.py`; draft state remains in
`button_draft.py`. GTK construction, direct Apply and inline state are in
`desktop.py`, with the narrow backend unchanged. This UI change was tested
offline, with no new mouse reads/writes, restores or input monitoring.

Direct-menu validation at delivery: **227 tests passed**. Coverage includes exact menu
order, all placeholder leaves, native parent activation/hover selection and
right-hand cascading, menu dismissal, no prerequisite device read, direct Apply
without dialogs/diagnostics, duplicate/busy guards, worker-start failure,
request-matching saved verification, no-change completion and retained selections
on failure. Native menu and main-window renders were also visually reviewed;
generated images remain outside Git.

## Net-change and artwork polish — 2026-10-27

Apply now tracks **net changes against the starting displayed assignments**.
Choosing Left Click → Right Click → DPI loop → Left Click removes the pending
change and disables Apply if no other row differs. Reverting one row does not
discard another row's change. This works with the initial reference labels,
loaded evidence, and the newly verified baseline after Apply. Menu placeholders
remain no-ops. No extra read is performed to detect a UI revert.

The display baseline is separate from captured raw bytes: reference values are
never written wholesale or used as a device backup. On failure, raw evidence is
invalidated but the last displayed baseline and pending choices are retained.
Returning to that baseline disables Apply without claiming that an uncertain
hardware write was restored; the failure warning remains. Fresh device validation,
read, backup and readback at the next explicit Apply are unchanged.

The entire right-click context menu, its keyboard shortcuts, About popup and
artwork toggle were removed. **F1** and `--diagnostics` retain access to the
still-needed optional polling/evidence/explicit restore controls. Right-clicking
an assignment does not activate it or open another menu.

The user's supplied mouse image is now the default in the app and preview
exports. `--reference-mouse` restores the original vendor illustration at launch;
the legacy `--generated-mouse` explicitly selects the supplied image. The flags
are mutually exclusive. The original skin atlases, supplied PNG and reference
inputs are retained unchanged for future preference changes.

Validation: **238 offline tests passed**; no new live mouse operation or input
monitoring was needed for these UI changes.

## Footer, marker and window interaction polish — 2026-10-27

Routine assignment selections, returns to the baseline and Cancel now keep one
generic footer: **EvoFox Blaze — Mouse configuration**. Apply progress, failures
and reconnect guidance still appear when needed. Editing or cancelling a draft
after a failed Apply does not erase the failure/uncertain-device-state warning.
Initial labels remain reference examples; tooltips and the window title retain
the offline-state distinction. Apply's net-change behavior is unchanged.

On the supplied illustration, marker 2 stays at `(551,246)` and 4 at `(414,318)`.
Marker 1 now mirrors 2 across the wheel at `(457,246)`. The wheel, DPI, lighting,
rear side and rapid-fire markers are centered more closely on their controls:
3 `(503,242)`, 5 `(425,363)`, 6 `(503,307)`, 7 `(503,342)`, 8 `(425,240)`.
These are display coordinates, not verified input-event identities. Both source
artworks are unchanged; the reference-artwork mode retains its original markers.

The old frameless-window handler was attached only to the windowless `Gtk.Fixed`
target overlay, not the `Gtk.DrawingArea` owning the background input window.
Background press/motion/leave and tooltip handlers now attach to the canvas.
Top-header/center-logo dragging requests a native window-manager move. Every
edge and corner has an eight-pixel resize band and directional pointer; controls
are excluded, and busy-operation guards remain. The geometry follows scaling
and letterboxing; minimum size and shrink-after-grow handling are unchanged.
Packaging alone would not have repaired the event wiring.

Button 8 still opens a preview menu only. Its tooltips now explain native slot 9,
the uncaptured region and the reference-only Rapid Fire label instead of promising
that Apply can program it. This is a backend coverage restriction, **not evidence
that the physical button is hard-wired to Rapid Fire**. See the new static follow-up
in [reverse-engineering.md](reverse-engineering.md#button-8-investigation--2026-10-27).

Validation: **246 offline tests passed**, including GTK-local background-event
dispatch to move/resize requests, all eight resize directions, cursor updates,
scaled/letterboxed control exclusions, generic status and preserved errors.
PNG previews were reviewed locally. These tests do not substitute for the user's
window-manager drag test. No desktop input injection/monitoring or live mouse
read/write was performed.

## Custom shortcut recorder — 2026-10-27

Historical recorder-only milestone; the next checkpoint supersedes its Apply gate.

**Recorder/draft UI implemented; on-device shortcut programming still blocked.**
The user requested an app-styled window with Record, Re-record and Save, where
Save stages a button assignment and only the main Apply may write to the mouse.
Shortcut is no longer a menu no-op. Other placeholder entries remain unchanged.

The editor uses an undecorated, transient/modal GTK window with an explicitly
styled dark/cyan Blaze palette, branded header/drag region, target button number,
instructions, a large combination preview, status, Record/Re-record, Stop, Cancel,
Save and a custom close button. It does not use an Ubuntu-themed MessageDialog.
Reopening the editor shows the selected button's existing in-memory draft.
Save updates only that row; Cancel/close preserves the previous assignment.

Recording starts **only after Record** and uses only that window's key events.
No evdev/hidraw listener, global hook/grab, input injection or disk log is added.
The combination completes when all pressed keys are released. Auto-repeat is
ignored; modifier sides are retained. Letters, digits, F1–F24, common navigation
and punctuation keys are supported with optional Ctrl, Shift, Alt and Super.
Keymap translation separates Shift/Caps from the base key. Dead/compose/AltGr and
unsupported keys are refused rather than guessed. More than one non-modifier
key is refused as a sequence (Macro is still not implemented).

During recording, Tab/Enter/Escape/F1 are keys, not editor/parent commands. Outside
recording, Escape cancels the editor. Parent navigation, duplicate editors and
Apply are guarded while the modal is open. A modifier held before Record is
refused when visible in event state, avoiding a silently incomplete combination.
Focus loss, hiding, Stop, timeout after 20 seconds and destruction clear partial
recordings and timers. Desktop-reserved shortcuts may be intercepted by the
compositor; the UI explains this rather than installing a global grab.

`shortcuts.py` holds immutable symbolic combinations and the pure recorder state
machine; `shortcut_editor.py` owns styled GTK controls/event handling. Drafts live
in a separate `ButtonDraft.shortcuts` mapping, not the native action-code map.
They never manufacture backup bytes or pass through the fixed native writer.
Labels show the combination with `*`; long labels ellipsize, with the complete
combination in the tooltip/accessibility name. Routine footer text stays generic.

Main Cancel clears both native and shortcut drafts; choosing a built-in replaces
that row's shortcut draft. Same evidence retains drafts; changed/failed evidence
clears them according to the existing baseline rules. Existing failure warnings
are not cleared by Save. Slot 9 and unknown/Fn/repeat targets remain blocked;
the recorder opens as a preview with Save disabled for those targets.

**Apply is disabled whenever any shortcut draft exists**, including a mixed
native/shortcut draft. It must not silently write only the native subset or claim
that a recorded shortcut reached the mouse. This limitation is explicitly stated
inside the editor and on Apply/assignment tooltips. Save is temporary in-app
state, not persistent storage; drafts are discarded on app exit. Completing the
user's full workflow requires the independently backed-up, source-corroborated
shortcut-record backend, not a host remapping service or a guessed `2e` link.

Validation: **275 offline tests passed**, including actual GTK-local key-event
dispatch, modifier handling, idle/armed state, recording/re-recording/Save/Cancel,
focus/timeout/hide/close cleanup, stale-state/busy guards, mixed-draft refusal and
continued native Apply behavior. Styled editor and main-page drafts were rendered
and reviewed locally using synthetic combinations. No real keyboard capture or
mouse read/write/restore was performed during development/testing.

## Experimental shortcut Apply — 2026-10-28

The full **Shortcut → Record → Save draft → Apply** workflow is now connected to
the scoped Python backend. Save remains offline and starts no device worker.
Apply is the explicit authorization, with no extra modal or prerequisite F1 read.
Native-only drafts still use the unchanged fixed `0008` writer; any shortcut draft
routes all native and keyboard changes together through `shortcut_write.py`.
Unknown/shared layouts are refused before settings data, and original records,
auxiliary bytes and allocation metadata remain untouched.

Apply validates identity/descriptor, reads fresh scoped bytes, saves a durable
partial backup, writes only owned differences and checks full readback. It clears
drafts only after strict journal validation matches every requested native action
and chord. Failures retain both kinds of selection and the warning, invalidate raw
evidence and never retry or restore automatically. A verified shortcut is shown
by its chord, not just Stored shortcut; changing then returning to it disables
Apply, including when the underlying button link remains `2e` throughout.

F1 provides **Restore shortcut backup…**, a separate confirmation/file chooser for
`shortcut-backup.json`. It restores exact scoped transaction bytes only in recorded
states, refusing intervening edits. No live shortcut restore has been authorized
or performed. Keep backups; these are not whole-device backups. Startup, menus,
recording, Save and saved-evidence inspection never contact the mouse.

The user's F13 test opened desktop Settings; the recorder stopped safely on focus
loss. This is consistent with the desktop's Tools binding intercepting the test
key, not a recorder malfunction. The separate user report is retained beside the
immutable F13 journal. It does not confirm replug, Ctrl+Shift+Down, modifier release
or general persistence. After a completed Apply, replug then test an ordinary chord
in the intended application; no global monitor/grab is needed.

Validation: **341 offline tests passed** on an authenticated private Xvfb display.
Coverage includes the actual GTK Record/Save/Apply lifecycle with a synthetic
mouse transaction, combined requests, no-change, failures, mismatched/restore
journals, backup routing, net-change reverts, separate restore confirmation,
focus loss, and continued native-only behavior. No new hardware operation was
performed during integration. Restart a running old app to load the new code;
old in-memory drafts are lost and must be recorded again.

## Unread baseline and desktop-reserved shortcuts — 2026-10-28

The user reported two real workflow defects: restoring Left/Right after a swap
was blocked by the reference default comparison, and Ctrl+Alt+Down switched the
workspace before recording could complete. These supersede earlier reference-
baseline behavior and the original discard-on-focus-loss policy.

Button startup labels now say **Not read**, with no native comparison baseline.
No automatic hardware access or fabricated table is added. Explicit selection of
Left/Right creates a draft even when those actions match the old artwork defaults.
Apply still obtains the actual original bytes before any setting data. After a
real read or verified Apply, the captured/verified assignments become the net-change
baseline, so changes can be reverted without a redundant write. F1 → Read button
assignments remains an optional, separately confirmed way to inspect the current
board. Changed/failed evidence resets unknown baselines safely; a failed Apply
still retains its explicit warning and selected drafts.

The styled editor adds **Choose combination without triggering desktop actions**:
eight side-specific modifier checkboxes and a supported-key selector. Selecting
Ctrl, Alt and Down produces Ctrl+Alt+Down locally without ever pressing the chord,
starting a recorder, inhibiting system shortcuts or acquiring an input grab. Save
stages only the editor selection in the page draft; only Apply writes. Cancel
preserves the previous draft. The expanded editor scrolls on shorter screens.

On focus loss, recording stops, timers/held-key state clear, and no background
capture resumes. A received valid single chord is kept for review/Save even if its
release events were intercepted. A modifier-only Ctrl+Alt+… preview is retained,
with those modifiers preselected, but Save stays disabled until the user explicitly
chooses the missing main key. Unsupported keys/sequences cannot become valid
shortcuts through focus loss. Completed selections survive focus changes; closing
the editor still discards unsaved edits. No desktop-wide shortcut suppression,
permission changes, host remapping or device operations were added.

Validation: **353 offline tests passed**, including the startup Left/Right recovery,
post-Apply reverse swap, known-baseline net changes, manual Ctrl+Alt+Down selection,
intercepted-main-key recovery without guessing, complete-chord retention, modifier
sides, busy/unsupported-target guards and short-screen scrolling. Tests use only
synthetic local GTK events and fake mouse transactions, never real input monitoring.

## Six key boxes, assignment recovery and visible read — 2026-10-28

Supersedes the preceding accordion/checkbox selector and unread-only startup.
The user rejected both workflows and requested up to six individually recorded
key boxes, automatic focus progression, deletion and a complete-chord preview.

`shortcut_boxes.py` is the new pure model; `shortcut_editor.py` presents three
boxes initially, **+ Add box** up to six, and a per-box **×** (minimum one box).
Record arms the first empty box; clicking a box explicitly arms that box. Press
**and release** one key at a time: the release commits its symbolic name, then
the next empty box activates. Thus tap/release Ctrl, then Alt, then Down constructs
Ctrl+Alt+Down without holding the desktop's workspace shortcut during entry.
The mouse still receives one chord, not a sequence/macro. The preview includes
empty-box markers; Save requires every box filled, distinct keys, exactly one
regular key and optional modifiers. Two ordinary keys, duplicate keys and
modifier-only combinations cannot be saved. A previously stored >6-key chord
is not truncated into a different assignment; replacing it requires re-recording.

The accordion, keyboard dropdown and modifier checkboxes are removed entirely.
Editing, adding/deleting and Save remain offline; Re-record/Cancel leave the prior
page draft intact until Save. Busy/unsupported-target/stale-state guards remain.
Only focused-window events are accepted while a box is explicitly armed. Auto-
repeat cannot fill another box. Overlapping/held keys are refused with guidance
to tap/release separately. Focus loss, hide, Stop and timeout clear the armed/
held state and timers but retain completed boxes. No background capture resumes.
The two-row six-box layout scrolls on short screens, and the new visuals were
reviewed on a private X display with synthetic combinations.

The main Button page now has a visible **Read mouse assignments…** button, not
just F1 diagnostics. Its separate confirmation explains the experimental staged
read: 81–116 fixed eight-byte blocks (1458–2088 SET / 648–928 GET), zero settings
commits, no retry/reset/input monitoring. It validates the inspected metadata
layout before reading original record guards and recognized owned tail slots.
The strict saved journal decodes supported chords along with native actions;
button 8's native assignment is still not read or programmed. Successful reads
replace the display baseline and discard drafts as the confirmation explains;
failure retains desired edits and a warning. The new read is implemented/tested
offline, not a newly exercised or agent-authorized hardware operation.

Startup recovers the latest validated assignment journal under the configured
GUI evidence root, without a probe, subprocess or device access. Labels and a
source caption say **saved / not live**; click Read to refresh from the board.
A newer failed/incomplete operation blocks older fallback. Missing history stays
unknown with a visible read action, never hardcoded action defaults. Symlinks,
wrong operation kinds and invalid journals are refused. Native-only historical
captures cannot invent keyboard-record contents: use the full assignment read
to obtain exact chord names. Apply still fresh-reads real bytes before writing.

Validation: **377 offline tests passed**, covering separate-key Ctrl+Alt+Down,
six-box limits, deletion, mandatory fields, duplicates/sequences, modifier sides,
focus/timeout/busy cleanup, Record → Save → Apply, restart history recovery,
incomplete-history refusal, explicit read cancellation/results/failure, exact
read operation counts, original/owned chord decoding and no settings commits.
No live read/write/restore or real input monitoring was performed for this rework.

## Windows-Super launcher interception — 2026-11-02

The user reported that tapping the Windows-logo key opens the Pop!_OS launcher
without filling its key box. The compositor may withhold the press or release;
the editor cannot assume an intercepted event was delivered or keep recording
after focus loss. No global grab, shortcut inhibition or desktop-setting change
is added to work around this.

The recorder now has a **Windows / Super** button with an explicit left-Super
tooltip and launcher-interception guidance. Clicking it selects `Super_L` in
the armed box or first empty box; this is a deliberate symbolic choice, not a
claim of recording a physical tap. A full chord is never overwritten without
first clicking a box. Existing recording advances to the next empty box as with
a completed tap. An idle/focus-stopped editor stays idle with no timer; click a
box or Record to explicitly resume. Held-key, duplicate, six-box, busy, stale
target, unsupported-row and Cancel/draft safeguards remain in place.

No accordion, dropdown, modifier checkboxes, event injection or background input
service were introduced. Save stays in-memory only; Apply and the separate
unvalidated activation candidate are unchanged. Restart a running app to load
the new recorder; unsaved in-memory drafts do not survive closing it.

Validation: **400 tests passed on private authenticated Xvfb**, including eight
new model/GTK checks for Ctrl+Super+Left through explicit insertion, interrupted
physical taps without fabricated keys, delayed release, timer/idle behavior,
replacement, duplicates, busy/unsupported-row guards and Cancel preservation.
No new mouse operation or real keyboard monitoring was performed.

## Independent offline feature audit — 2026-11-02

At the user's request, expanded testing while they were unavailable rather than
performing unattended hardware experiments. **413 tests passed headlessly with
no skips**, including 13 new cross-page/menu, Windows fallback end-to-end,
saved-state restart, polling GUI-to-fake-writer and failure-diagnostic cases.
The mapped-window test also checks that shared footer chrome stays painted after
page switches, rather than relying only on offscreen skin exports.

Completed the existing partial Error details implementation: pass the renderer's
error flag, enable its target only for errors, open F1 diagnostics on its details
tab, propagate saved failure diagnostics and clear them after successful evidence.
Failure text reserves space beside the existing details button; routine styling
and the approved baseline are otherwise unchanged. The saved-capture chooser
now guards against busy operations, and polling failure details count the actual
`config_write_intent` commit event rather than silently omitting its warning.
The old smoke assertion expecting an empty error text area was updated to require
plain failure text instead of stale verified-state JSON.

See [the audit matrix](feature-audit.md) for the important distinction between
tested implemented workflows and missing features. Macro, lighting, physical CPI,
profiles/media, slot 9, input monitoring and complete-device backup are not made
functional by these tests. The separate immediate-activation candidate remains
unvalidated and disconnected from GUI Apply. No live operation, global input
capture, permission change or automatic activation was performed.

## Opt-in immediate activation — 2026-11-02

`python3 -m evofox_blaze.gui --experimental-activation` arms the source-matched
activation candidate after new native, shortcut or polling Apply. It is **off by
default**, unvalidated on the real mouse, and does nothing at startup or Save.
This is a narrow experimental addition, not a redesign of the approved baseline.

On Button, the generic footer is replaced by an explicit armed warning only in
this opt-in mode; Apply/shortcut tooltips explain that all stored settings may be
activated. Direct assignment Apply still needs no extra modal. Polling's existing
confirmation includes the extra scope. Reads and separately confirmed restores
do not activate. Original/DPI/F13 scopes are not broadened.

After real stored-byte readback, the worker requests the fixed two-report sequence
on the same locked handle. The GUI requires the saved journal to match the selected
assignments **and** activation policy before clearing drafts. It says "activation
sequence sent; test now without replug; runtime behavior unverified", never that
the physical assignment is proven active. Unchanged bytes say no write/activation
was sent. Failure retains drafts and backup with no retry; incomplete history
blocks fallback to older values. Opening recovered activation journals stays offline.

See the [backend checkpoint](reverse-engineering.md#opt-in-immediate-activation-integration--2026-11-02)
for protocol ordering, strict inspection, tests and hardware-consent limits.
Validation: **434 headless tests passed, no skips**. No new live hardware operation
or ordinary-default activation was performed/enabled.

## Saving overlay and minimal hover help — 2026-11-02

The user confirmed the opt-in no-replug test works, then requested a visible,
app-styled loading screen that cannot be dismissed or clicked through, plus
removal of verbose/redundant hover text. No new mouse operation was needed for
this UI work; the behavior report is recorded separately in the device evidence.

`operation_overlay.py` supplies a dark translucent input shield, cyan-bordered
Blaze card, spinner, "Saving to mouse…"/"Reading mouse…" title and brief keep-
connected guidance. It covers the entire window above all hit targets and has
no close/cancel controls. Underlying content is insensitive; pointer, scroll,
touch and keyboard events are consumed locally. Normal close/Escape, duplicate
Apply, navigation and diagnostics actions remain blocked while busy. No global
input grab or capture is added.

Both the skinned window and F1/standalone controls use the overlay. A diagnostic
operation shields both windows; a main-page operation also shields open diagnostics.
The overlay stays visible through backend completion and strict saved-journal
validation, then hides and stops its spinner on success/failure or worker-start
failure. It does not invent percentages or add a delay. Recorder Save remains
RAM-only and never starts a loading screen. Existing errors, drafts, backups,
no-retry safeguards and the explicit activation policy remain unchanged.

Hover help is limited to:

- **Not implemented.** for unavailable controls/menu entries.
- **Read mouse state first (F1).** for unavailable polling selection.
- A full assignment label only when it is too long for its visible row.
- One short Windows/Super insertion hint in the recorder.

Blank artwork/header areas, ordinary controls, supported menu entries, Apply,
Cancel, close/delete icons and short assignment labels have no tooltip. Removed
the canvas-wide fallback that repeated protocol/status text everywhere. Recorder
instructions and staged-read information now use short bullets/paragraphs;
accessible names and detailed failure evidence remain available without hover spam.

The overlay and shorter editor were reviewed on private authenticated Xvfb.
One screenshot attempt hit a native GDK/Cairo capture assertion for the editor;
a local debugger isolated it to `gdk_pixbuf_get_from_window`, not normal app
rendering or device code. A GTK-to-Cairo widget draw was used for that preview.
No host package installation or permission change was needed. Previews/debug
tools under `/tmp/opencode` are disposable, not project dependencies.

Validation: **442 tests passed headlessly, no skips**, including eight new overlay/
tooltip cases plus success/failure lifecycle assertions in the real fake-writer
GUI tests. Coverage includes all-edge shielding, pointer/key/close blocking, both
windows, read/save titles, saved-result verification, worker-start failure,
draft-only Save, minimal hover policy and clipped-label help. No new real mouse
operation or input monitoring was performed for this UI work.

## Live loading-phase line — 2026-11-02

The user noticed the programmed shortcut responding while the saving overlay
remained visible for another 15–30 seconds. Offline inspection of saved GUI
journals found about 26 seconds in the initial snapshot and another 26 seconds
in full post-write readback; strict saved-journal decoding took about 0.11 seconds.
The overlay added no timed wait. No new hardware operation was performed to
investigate this report, and neither verification nor durable logging was shortened.

Added one single-line label directly beneath the spinner, preserving the existing
card, shield and normal-close/keyboard/pointer protections. It shows **Checking
mouse**, **Reading settings**, **Saving backup**, **Writing settings**, **Verifying
settings**, **Sending activation sequence** or **Checking saved result** as those
phases are reached. A 450-ms GTK timeout cycles `.`, `..`, `...`; these are activity
dots, not a percentage, elapsed-time estimate or claim that settings are active.
Repeated UI refreshes do not reset the phase or create duplicate timers. Hiding,
completion and destruction remove the timer; late phase updates are ignored.

`operation_progress.py` separates best-effort phase hints from evidence. For GUI
operations, `DeviceControl.run(progress=...)` passes one private inherited pipe
descriptor to the already-authorized Python backend. A reader drains phase tokens
while the original `subprocess.run(capture_output=True)` preserves final stdout
JSON, stderr errors and no-retry behavior. There is no journal polling, raw key
monitoring, progress output on stdout, new CLI consent or new hardware command.
The pipe and reader are closed/joined even when child startup fails.

`Journal.record` reports deduplicated read/write/activation phases only after the
existing event is flushed/fsynced. Explicit backup hints precede the existing
backup functions, only when a backup is actually needed. Staging SETs remain
**Reading settings**, not setting writes. No-change and failures do not fabricate
later phases. Broken phase pipes or callback errors do not retry or interrupt the
transaction. Durable journal rows and strict offline validators remain unchanged.

Main and diagnostic operations share phase delivery across both visible shields.
Workers only queue GTK-main-loop updates; each operation owns a token that is
invalidated before saved-result checks, so queued updates from an earlier worker
cannot overwrite final verification or a later operation. Recorder Save remains
RAM-only, and activation remains opt-in and is labeled sequence-sending only.

Validation: **459 tests passed headlessly, no skips**, including 17 new cases for
phase ordering on all three fake writers, no-change/backup failure, durable-event
ordering, live delivery before child exit, unchanged result/error handling,
disconnected/callback-failed reporting, child-start cleanup, GTK-main-loop delivery,
both windows and standalone diagnostics, stale-operation rejection, real timeout
dot cycling and hide/destroy cleanup. Reviewed the verification line in a private
Xvfb screenshot using GTK-to-Cairo drawing. No real mouse access was performed.

## Preparing the reference artwork on another checkout

Vendor artwork and fonts are **not redistributed as MIT-licensed project assets**.
They remain local, outside Git, as described in [vendor-reference.md](vendor-reference.md).
No Windows executable is run. The preparation helper copies only ten named JPEG
atlases and an optional Roboto font; it does not load vendor INIs, macros, DLLs or
executables. The font is registered for the process only, not installed on the host.

From an already statically extracted installer:

```sh
python3 -m tools.prepare_ui_skin --from-directory /path/to/extracted/app/skins
```

Or, with a trusted `innoextract` binary:

```sh
python3 -m tools.prepare_ui_skin --extractor /path/to/innoextract
```

This verifies the repository installer's documented SHA-256 before extraction.
It refuses to overwrite an existing staging directory. A `provenance.json` records
the staged file hashes. A custom staging location can be passed using
`--destination` and then `gui --skin-dir`; keep third-party artwork outside Git.
If the local art is missing, the app reports the preparation command rather than
silently substituting a different design. `--diagnostics` requires no skin assets.

## Tests and visual review

Run GUI tests on a private, invisible Xvfb display, not the active desktop:

```sh
python3 -m tools.run_virtual_tests --xvfb /tmp/opencode/evofox-xvfb/root/usr/bin/Xvfb
```

The executable path above is the locally extracted, hash-checked Ubuntu package
described in [the backend checkpoint](reverse-engineering.md#f13-transaction-completed--user-behavior-test-pending).
It is temporary; pass another trusted Xvfb path if needed. The runner creates
an authenticated private display, disables TCP listening, and stops only its own
display process. No system installation or permission changes are needed.

Without Xvfb, run the non-GUI coverage without opening desktop windows:

```sh
env -u DISPLAY -u WAYLAND_DISPLAY GDK_BACKEND=x11 python3 -m unittest discover -s tests -v
```

This fallback skips GUI tests and is not full-suite validation. Do not run GUI
tests on the active desktop unless explicitly requested. On 2026-11-02, all
**377 tests passed** on private Xvfb. The active desktop lacked an `Alt_R` keymap
entry, causing two test-helper failures there; both passed unchanged on Xvfb.
No mouse access was performed.

Pure layout/preparation tests require no desktop dependencies. Native smoke tests
exercise all four screens, disabled controls, accessibility names, polling drafts,
cancelled confirmation, failure clearing, busy guards, shrinking/resizing and PNG
exports with no device access. They skip when GTK, a display or the locally staged
artwork is unavailable. Exports are useful for visual comparison against the
user-provided screenshots; they are not a claim of a measured pixel-diff match.
