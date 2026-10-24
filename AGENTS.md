# Continuing this project

Do not depend on a previous chat/session. Start with repository files:

1. Inspect `git status --short --branch`; preserve uncommitted work from other sessions.
2. Read `README.md` for the current entry points and overall status.
3. Read the **Protocol/backend checkpoint** in `docs/reverse-engineering.md`.
4. Read `docs/hid-protocol.md` and `docs/device-captures/README.md` before transport work.
5. Read `docs/ui-development.md` before UI work; preserve the separately approved visual baseline.
6. Run `python3 -m unittest discover -s tests -v` for the current offline result.
   Historical checkpoint test counts are not assertions about the latest tree.

## Boundaries

- The full app is not finished. Polling stored-byte change/readback/restore was
  exercised; this does not prove actual polling frequency or power-cycle persistence.
- The eight-byte block backup is not a whole-device backup. Arbitrary memory
  access, lighting writes, CPI-value programming, button remapping and macros
  are not unlocked by the existing polling implementation.
- Previous hardware approvals were consumed by the recorded operations. Obtain
  fresh, explicit authorization for live reads, writes, restores or input monitoring.
  Opening the app or saved evidence must not contact the mouse automatically.
- Never execute vendor Windows software, replay generic/full vendor memory
  images, issue firmware/bootloader/erase/reset commands, detach drivers, or
  change system permissions/udev rules as an implicit implementation step.
- No live click/button monitor is implemented. UI button labels are not device
  event evidence; DPI/lighting/rapid-fire buttons may not emit distinct events.
- Preserve original captures. New operations need new destinations, identity
  and descriptor validation, durable intent logs, and no automatic retries or
  blind rollback. Follow the existing scoped backend rather than broadening it.

## Filesystem handoff

Essential implementation, fixtures and sanitized captures must be retained
together. Inspect untracked files as well as tracked changes; do not assume the
latest checkpoint is already committed. Commit/push only when the user requests it.
`.work/` is ignored and `/tmp/opencode/evofox-re-tools/` is disposable. Recreate
analysis tools from `docs/reverse-engineering.md` and local UI artwork from
`docs/ui-development.md`; neither is required to remember protocol progress.
