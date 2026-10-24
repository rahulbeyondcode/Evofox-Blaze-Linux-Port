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

**Stopped at:** the user-approved visual UI milestone. No subsequent hardware
feature has been selected or authorized in this checkpoint.

1. Read the root `AGENTS.md`, this checkpoint, and the implementation/next-task
   sections in `README.md`. Check `git status` before editing existing work.
2. Keep the approved appearance. The next work should build on this UI, not
   recreate or redesign it. Ask the user which remaining feature to prioritize.
3. Existing state reads, polling changes and scoped restore already have backend
   support. Physical DPI values, lighting readback, buttons, profiles and macros
   remain incomplete; keep their controls disabled until validated.
4. The README identifies a consent-gated DPI-stage index exercise as the next
   protocol task. It is not permission to perform it automatically. Prior UI or
   polling-test approval does not authorize new hardware operations.
5. Use the launch, test and artwork-preparation commands below to recover the
   development environment. The last full local run passed 159 tests; rerun after
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
- **F1** or right-click opens the existing device controls and saved evidence.
- Drag the logo area to move the window. Drag the bottom-right corner to resize.
  The complete reference layout scales uniformly, with letterboxing when needed.
- Tab/Shift+Tab and Enter/Space work on enabled controls. The Menu key or
  Shift+F10 opens the context menu.
- Right-click → **Use supplied mouse image** switches to the cutout derived from
  `docs/Software_UI/MouseImage.png`. The default keeps the original mouse artwork
  because the generated illustration is not identical to the screenshots. The
  source image is never modified.

```sh
python3 -m evofox_blaze.gui --page performance
python3 -m evofox_blaze.gui --generated-mouse
python3 -m evofox_blaze.gui --diagnostics
python3 -m evofox_blaze.gui --render-previews .work/ui-previews
```

The last command exports `buttons.png`, `macros.png`, `performance.png` and
`backlight.png`, without opening a window or contacting the mouse. It currently
requires the same GTK/Pango/Cairo desktop dependencies and an available display.
`--capture <journal>` continues to open the original offline evidence window.

## What is and is not working

**Nothing contacts the mouse automatically.** Initial button assignments, 500-Hz
selection, DPI values, sliders, lighting and selected Media profile reproduce
the reference, **not live device state**. Tooltips and the About dialog explain
this distinction. Unsupported settings remain visible but insensitive; their
reference colors are retained rather than grayed out to preserve visual fidelity.
No key recording, audio capture, profile import/export or reset is performed.

The existing backend remains available through F1. After an explicitly confirmed
state read (or loading valid saved state evidence), Performance allows a draft
polling target. Apply opens the existing separate confirmation and scoped-backup
workflow; Cancel discards the draft. Saved evidence is not live state, and the
backend re-reads and validates the device before a write. Frequency is not
measured. Failed reads clear the previous candidate. Closing and duplicate
operations are blocked while the backend is busy. Full-profile writes, physical
DPI values, buttons, macros and lighting are not enabled.

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

```sh
python3 -m unittest discover -s tests -v
```

Pure layout/preparation tests require no desktop dependencies. Native smoke tests
exercise all four screens, disabled controls, accessibility names, polling drafts,
cancelled confirmation, failure clearing, busy guards, shrinking/resizing and PNG
exports with no device access. They skip when GTK, a display or the locally staged
artwork is unavailable. Exports are useful for visual comparison against the
user-provided screenshots; they are not a claim of a measured pixel-diff match.
