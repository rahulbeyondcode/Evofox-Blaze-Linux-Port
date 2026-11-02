# Continuing this project

Do not depend on a previous chat/session. Start with repository files:

1. Inspect `git status --short --branch`; preserve uncommitted work from other sessions.
2. Read `README.md` for the current entry points and overall status.
3. Read the **Protocol/backend checkpoint** in `docs/reverse-engineering.md`.
   Also read the newer **Native button checkpoint** there before button work.
4. Read `docs/hid-protocol.md` and `docs/device-captures/README.md` before transport work.
5. Read `docs/ui-development.md` before UI work; preserve the separately approved visual baseline.
6. Run tests headlessly; the user explicitly requested no repeated test windows
   on their active desktop. Use `python3 -m tools.run_virtual_tests --xvfb
   /path/to/trusted/Xvfb` for the full suite (see `docs/ui-development.md`).
   If Xvfb is unavailable, use `env -u DISPLAY -u WAYLAND_DISPLAY GDK_BACKEND=x11
   python3 -m unittest discover -s tests -v`; report the skipped GUI coverage.
   Never fall back to the active display implicitly. Historical checkpoint test
   counts are not assertions about the latest tree.

## Boundaries

- The full app is not finished. Polling stored-byte change/readback/restore was
  exercised; this does not prove actual polling frequency or power-cycle persistence.
- The eight-byte block backup is not a whole-device backup. Arbitrary memory
  access, lighting writes, CPI-value programming and macros are not unlocked
  by polling. Native built-in button assignments use a separate fixed `0x0008`
  backend; do not extend it to slot 9 or shortcut records implicitly.
- Previous hardware approvals were consumed by the recorded operations. Obtain
  fresh, explicit authorization for live reads, writes, restores or input monitoring.
  Opening the app or saved evidence must not contact the mouse automatically.
- Never execute vendor Windows software, replay generic/full vendor memory
  images, issue firmware/bootloader/erase/reset commands, detach drivers, or
  change system permissions/udev rules as an implicit implementation step.
- No live click/button monitor is implemented. UI button labels are not device
  event evidence; DPI/lighting/rapid-fire buttons may not emit distinct events.
- The 2026-10-27 side Back/Forward change was user-tested after physical replug
  and intentionally left programmed. Its read/write approvals were consumed.
  Native restore has offline coverage only. Keyboard chords now use the separate
  experimental scoped backend; custom sequences remain unavailable. Preserve
  original records and auxiliary data.
- The user subsequently requested direct assignment menus. Opening menus is
  offline; Apply itself explicitly authorizes the selected assignment transaction,
  without an extra modal/F1 read/Keep draft step. Preserve this workflow and the
  existing fresh-read, backup, readback and no-automatic-retry safeguards.
  Unimplemented menu entries are clickable no-ops, never fake device settings.
- Latest UI preference: no right-click context menu; supplied mouse artwork is
  default, with original art retained behind `--reference-mouse`. Apply tracks
  net changes from real read/verified assignments, not each menu click.
  Newest startup fix: recover latest verified GUI assignment journal offline,
  labeled saved/not live; no stale fallback past an incomplete operation.
  Without history, no assumed native defaults. Selecting Left/Right must work
  before a read. Visible Read mouse assignments has a separate staged-read
  confirmation and reads supported chord records, not just the native table.
  New reader has offline coverage only; no agent hardware approval. Display
  baselines must never become synthetic device backup bytes.
- Routine footer text stays generic; retain real Apply progress/errors and
  reconnect guidance. Canvas pointer handlers support header/logo dragging and
  all-edge resizing; do not reattach them only to the windowless target layer.
- Button 8 is software-gated, not proven hard-wired. Static slot-9 candidate is
  byte 0 of mixed-settings block `0x0010` (see newer investigation checkpoint);
  no live read/backup/write/restore exists for it. Do not broaden `0x0008` writes.
- Shortcut now opens a custom-styled, explicitly armed window-local recorder.
  Save stages only an in-memory button draft; never a mouse write. Shortcut Apply
  now uses the separate scoped backend, combining all native/shortcut selections.
  Do not silently apply the native subset or fake shortcut success. Only matching
  strict saved verification clears drafts. F1 shortcut restore is separately
  confirmed; its backend has offline coverage, not a live restore test.
  No global capture/grab/logging; stop recording on focus loss, hide, close or
  timeout. Re-record/Cancel must preserve the previous draft until Save.
  Newest recorder UX: remove accordion/dropdown/modifier checkboxes. Use 1–6
  individually armed key boxes (three initially), +/× add/delete, tap/release one
  key per box, then auto-advance. All boxes must be filled; distinct modifiers
  plus exactly one regular key. Save remains draft-only. Enter Ctrl+Alt+Down as
  separate taps, never a held desktop shortcut. Focus loss/hide/Stop/timeout
  clears armed/held state and timers but keeps filled boxes. No background
  resumption. Never infer intercepted keys or silently truncate >6-key chords.
  Newest Pop!_OS correction: the Windows key may open the launcher instead of
  reaching the recorder. A Windows / Super button explicitly inserts left
  Super_L into the armed/first empty box, without synthesizing input or using a
  global grab. A full chord requires selecting a box first. Continue an already
  armed recording, but never rearm idle/focus-stopped capture from insertion.
  No dropdown/checkbox panel was restored. 400 tests passed headlessly; no live
  operation. See the 2026-11-02 UI checkpoint before changing this behavior.
- Preserve original captures. New operations need new destinations, identity
  and descriptor validation, durable intent logs, and no automatic retries or
  blind rollback. Follow the existing scoped backend rather than broadening it.
- Active shortcut-backend work: metadata + 96-byte payload inspections were
  separately approved and completed; both approvals are consumed. Fresh table
  `21 22 23 24 23 35 00 26` supersedes the older observed slot-5 Forward state.
  The codec/planner/write/restore/inspector have offline tests. A separately
  approved F13 tail test has now been written/read back (approval consumed):
  recorded table `21 22 23 24 2e 35 00 26`, UI 4/native 5 stored as F13. User
  reported the test opened desktop Settings (consistent with Tools interception);
  screenshots show focus-loss recording stop. No raw event capture or replug/
  ordinary-chord/modifier-release proof. The user since reports other Apply
  changes (Left/Right swaps); do not treat F13 as the current board state.
  Experimental GUI Apply is now connected; intended chord is Ctrl+Alt+Down.
  On 2026-11-02 the user reported Ctrl+Alt+Down working after the prompted GUI
  mouse-button test. This is user behavior evidence, not raw events; reconnect/
  persistence and modifier release were not separately confirmed. No current
  table/journal was inspected for this report. No shortcut restore has been
  approved or performed. Never repeat the F13 transaction on resume.
  Read the newest checkpoint before any live operation. Do not use this note
  as authorization for payload reads, writes, restores or monitoring.
- Current priority is immediate activation after Apply, not slot 9. Read the
  2026-11-02 **Immediate activation investigation** checkpoint before continuing.
  The hash-checked vendor writer ends with `07 18 10 00 00 00 00 00`, 5 ms, then
  `07 18 00 00 00 00 00 00`; a related capture corroborates these bytes, not their
  Blaze effect. `activation.py`/`activation_capture.py` retain the standalone
  opt-in tool; default/--preview is offline. No agent-side live activation
  approval/test exists. Ordinary GUI Apply is unchanged by default; explicit
  opt-in integration is described below. The user subsequently reported the
  prompted GUI test working without replug (newest checkpoint); do not ask them
  to repeat that consumed test automatically. Any new agent-side operation
  needs fresh scope-specific approval. The candidate may activate all
  stored settings, not just one button; firmware effects unproven, no settings
  backup from this operation. Never append command 20/reset or retry implicitly.
- Newest independent audit: the user was unavailable and requested test-only
  verification across all features. Read `docs/feature-audit.md` and the latest
  UI/backend audit checkpoints. 413 tests passed headlessly, no skips. Added
  GUI-to-fake-writer/restart coverage for Windows/Super and polling, all native
  menu rows, mapped footer rendering and inactive-feature guards. Completed
  existing Error details wiring/propagation, polling commit-warning diagnostics
  and the saved-capture busy guard. No real mouse operation was performed or
  authorized by this request. Passing tests do not implement macros/lighting/
  physical CPI/profiles/media/slot 9 or prove activation/release/persistence.
- Newest implementation: the user selected **Immediate activation** to build.
  `gui --experimental-activation` now explicitly arms new native/shortcut/polling
  Apply only. Read the **Opt-in immediate activation integration** checkpoint.
  After durable backup and matching readback, recheck identity and send the fixed
  pair on the same validated/locked handle. Default, no-change, reads, startup,
  restores, DPI-stage and the old F13 test scope do not activate. CLI writers
  require separate `--accept-activation-risk`. Strict journals and GUI must match
  both assignment and activation policy before drafts clear. Failure stops with
  backup/drafts retained, no retry/cleanup/rollback; incomplete history blocks
  stale fallback. Success means sequence-sent, never runtime behavior proven.
  434 headless tests passed, no skips. No real mouse operation was authorized or
  performed for this build. Do not silently enable the default or treat the GUI
  launch flag / implementation request as agent-side live-operation approval.
- Newest user report/UX: the user confirmed the prompted opt-in GUI assignment
  works without unplug/replug. No current board bytes/journal/raw input was
  independently inspected; no new agent hardware operation was performed. Keep
  activation opt-in and original captures unchanged. Follow-up UI request added
  a non-dismissible app-styled saving/reading overlay across main/diagnostics,
  with underlying controls and normal close/Escape blocked until completion and
  strict saved verification. Hide/stop it on success/failure/start failure;
  recorder Save remains RAM-only. No fake percentage, extra Apply confirmation,
  global grab or background capture. Tooltips now only: Not implemented, polling
  read prerequisite, clipped full assignment labels and the short Windows key
  hint. No blanket canvas/ordinary-control/protocol hover text. Recorder/read
  guidance uses short bullets. 442 headless tests passed, no skips. Read the
  newest UI/backend checkpoints before editing these paths.
- Newest overlay refinement: live backend phases now appear in one line under
  the spinner with cycling `.`, `..`, `...`. Read the **Live loading-phase line**
  UI checkpoint and **Live loading phases and post-write wait** backend checkpoint.
  A private inherited pipe carries deduplicated best-effort phase tokens, never
  evidence or final results. Preserve stdout JSON, durable per-intent fsync,
  backups/full readback and activation ordering. Staging SETs are reading, not
  setting writes. GTK updates are main-loop-only with per-operation stale-update
  guards; hide/destroy/completion removes dot timers. No-change skips unwarranted
  phases. Recorder Save stays draft-only. The observed ~26-second post-write
  wait was real readback, not an overlay delay; do not remove verification or
  dismiss early based on apparent behavior. 459 headless tests passed, no skips;
  no new live operation was performed.

## Filesystem handoff

Essential implementation, fixtures and sanitized captures must be retained
together. Inspect untracked files as well as tracked changes; do not assume the
latest checkpoint is already committed. Commit/push only when the user requests it.
`.work/` is ignored and `/tmp/opencode/evofox-re-tools/` is disposable. Recreate
analysis tools from `docs/reverse-engineering.md` and local UI artwork from
`docs/ui-development.md`; neither is required to remember protocol progress.
