"""EvoFox Blaze reference UI and confirmed experimental device controls (GTK 3)."""

import argparse
from pathlib import Path
import sys
import threading

from .capture_view import CaptureModel
from .device_control import DeviceControl
from .operation_overlay import OperationOverlay
from .operation_progress import OperationProgress


def load_gtk():
    # Optional desktop dependencies: CLI/research tools and model tests remain
    # usable without PyGObject, GTK, or a display server.
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    return Gtk


class CaptureWindow:
    def __init__(self, Gtk, model: CaptureModel, control=None):
        self.Gtk = Gtk
        self.model = model
        self.control = control if control is not None else DeviceControl()
        self.experimental_activation = getattr(self.control, "experimental_activation", False) is True
        self.busy = False
        self.operation_action = None
        self.last_backup = None
        self.last_button_backup = None
        self.last_shortcut_backup = None
        self.window = Gtk.Window(title="EvoFox Blaze — Experimental controls")
        self.window.connect("delete-event", self.prevent_close_while_busy)
        self.window.connect("key-press-event", lambda *_args: self.busy)
        self.window.set_default_size(900, 640)
        self.window.set_border_width(16)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        overlay = Gtk.Overlay()
        overlay.add(content)
        self.window.add(overlay)
        self.operation_overlay = OperationOverlay(Gtk, overlay, content)
        self.operation_progress = OperationProgress(self.progress_overlays)
        toolbar = Gtk.Box(spacing=12)
        content.pack_start(toolbar, False, False, 0)
        self.opened = Gtk.Button(label="Open saved capture…")
        self.opened.connect("clicked", self.choose_capture)
        toolbar.pack_start(self.opened, False, False, 0)
        self.read_button = Gtk.Button(label="Read mouse state…")
        self.read_button.connect("clicked", lambda _button: self.confirm_operation("read"))
        toolbar.pack_start(self.read_button, False, False, 0)

        controls = Gtk.Box(spacing=12)
        content.pack_start(controls, False, False, 0)
        controls.pack_start(Gtk.Label(label="Polling target"), False, False, 0)
        self.polling = Gtk.ComboBoxText()
        for hz in (125, 250, 500, 1000):
            qualifier = " (source-derived)" if hz in (125, 250) else ""
            self.polling.append(str(hz), f"{hz} Hz{qualifier}")
        self.polling.set_active_id("500")
        controls.pack_start(self.polling, False, False, 0)
        self.apply_button = Gtk.Button(label="Apply polling…")
        self.apply_button.connect("clicked", lambda _button: self.confirm_operation("polling", polling=int(self.polling.get_active_id())))
        controls.pack_start(self.apply_button, False, False, 0)
        self.restore_button = Gtk.Button(label="Restore block backup…")
        self.restore_button.connect("clicked", self.choose_backup)
        controls.pack_start(self.restore_button, False, False, 0)

        native = Gtk.Box(spacing=12)
        content.pack_start(native, False, False, 0)
        self.read_buttons = Gtk.Button(label="Read button assignments…")
        self.read_buttons.connect("clicked", lambda _button: self.confirm_operation("read-buttons"))
        native.pack_start(self.read_buttons, False, False, 0)
        self.restore_buttons = Gtk.Button(label="Restore button backup…")
        self.restore_buttons.connect("clicked", self.choose_button_backup)
        native.pack_start(self.restore_buttons, False, False, 0)
        self.restore_shortcuts = Gtk.Button(label="Restore shortcut backup…")
        self.restore_shortcuts.connect("clicked", self.choose_shortcut_backup)
        native.pack_start(self.restore_shortcuts, False, False, 0)

        self.message = Gtk.Label(xalign=0)
        self.message.set_line_wrap(True)
        self.message.set_selectable(True)
        content.pack_start(self.message, False, False, 0)

        tabs = Gtk.Notebook()
        self.tabs = tabs
        content.pack_start(tabs, True, True, 0)
        self.rows = Gtk.ListStore(str, str)
        table = Gtk.TreeView(model=self.rows)
        for index, title in enumerate(("Field", "Saved evidence / limitation")):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=index)
            column.set_resizable(True)
            table.append_column(column)
        summary = Gtk.ScrolledWindow()
        summary.add(table)
        tabs.append_page(summary, Gtk.Label(label="Summary"))

        details = Gtk.TextView()
        details.set_editable(False)
        details.set_cursor_visible(False)
        details.set_monospace(True)
        details.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.details = details.get_buffer()
        evidence = Gtk.ScrolledWindow()
        evidence.add(details)
        tabs.append_page(evidence, Gtk.Label(label="Decoded evidence"))

        warning = Gtk.Label(label=(
            "No automatic device access: use Apply on Button to authorize a change, or confirm actions here.\n"
            "Polling bytes have been written/read back/restored; actual frequency is not measured.\n" +
            ("Native buttons: experimental activation armed for new Apply changes; restores stay unchanged.\n"
             if self.experimental_activation else
             "Native button assignments: choose directly on the Button page, then Apply. Replug after writing.\n") +
            "Keyboard chords are experimental; Save is draft-only, Apply writes. Macros, lighting, CPI values and profiles remain unavailable. Backups are partial."
        ), xalign=0)
        warning.set_line_wrap(True)
        content.pack_start(warning, False, False, 0)
        self.refresh()

    def refresh(self):
        self.operation_overlay.set_busy(self.busy, reading=bool(self.operation_action and self.operation_action.startswith("read")))
        self.rows.clear()
        self.details.set_text("")
        state_loaded = (self.model.presentation is not None
                        and json_mode(self.model.presentation.details) in
                        ("offline-state-inspection", "offline-configuration-inspection"))
        for widget in (self.opened, self.read_button, self.restore_button, self.read_buttons, self.restore_buttons,
                       self.restore_shortcuts):
            widget.set_sensitive(not self.busy)
        for widget in (self.polling, self.apply_button):
            widget.set_sensitive(not self.busy and state_loaded)
        if self.model.presentation is None:
            self.message.set_text(self.model.error or "Open a completed feature-read.jsonl or state-read.jsonl capture to inspect it offline.")
            self.details.set_text(self.model.error_details or self.model.error)
            return
        self.message.set_text("Saved capture loaded. Field interpretations are candidates, not verified behavior measurements.")
        for row in self.model.presentation.rows:
            self.rows.append(row)
        self.details.set_text(self.model.presentation.details)

    def prevent_close_while_busy(self, _window, _event):
        if self.busy:
            self.message.set_text("A device operation is in progress. Wait for its result; do not interrupt a settings commit.")
        return self.busy

    def progress_overlays(self):
        return [self.operation_overlay]

    def confirm_operation(self, action, **arguments):
        if self.busy:
            return
        Gtk = self.Gtk
        if action in ("read", "read-buttons"):
            title = "Read eight-byte button assignments?" if action == "read-buttons" else "Read one eight-byte state block?"
            explanation = ("Sends 18 SET_REPORTs including zero-data staging and 8 GET_REPORTs. "
                           "No settings commit, reset or firmware command. No retry on failure.")
        elif action == "restore-shortcuts":
            title = "Restore the saved shortcut transaction?"
            explanation = ("Fresh staged reads, durable scoped backup, restore of the recorded button links, "
                           "descriptors and tail-record bytes, then complete scoped readback. "
                           "Only the inspected allocation layout is supported; intervening edits are refused. "
                           "This is a partial backup, not a whole-device restore. Original records, auxiliary data "
                           "and allocation metadata remain untouched. No retry, automatic rollback or reset.\n\n"
                           "Do not press buttons or unplug during the operation. After completion, unplug for about "
                           "10 seconds and reconnect. Physical shortcut behavior is not established by readback.")
        elif action in ("buttons", "restore-buttons"):
            from .button_write import assignment_rows
            from .buttons import ACTION_LABELS
            title = "Restore the original native button table?" if action == "restore-buttons" else "Program native button assignments?"
            explanation = ("Fresh staged read, durable eight-byte backup, at most ONE button-table commit, then full readback. "
                           "Up to 46 SET_REPORTs / 16 GET_REPORTs. Existing extension records remain untouched. "
                           "Restore refuses intervening changes. No retries, automatic rollback, reset or activation command.\n\n"
                           "Physically unplug for about 10 seconds and reconnect AFTER completion to load the mapping. "
                           "Back/Forward on the side buttons was user-tested after replug; other actions are source-derived. "
                            "This native-only operation does not program keyboard records, macros or button 8.")
            if action == "buttons":
                explanation += "\n\n" + "\n".join(
                    f"Native slot {row['slot']}: {ACTION_LABELS[row['action']]}"
                    for row in assignment_rows(arguments["assignments"]))
            else:
                explanation += ("\n\nThe backup includes the table only, not shortcut records. "
                                "Original shortcuts cannot be recovered if another tool changed those records.")
        else:
            title = (f"Change polling setting to {arguments['polling']} Hz?" if action == "polling"
                     else "Restore this saved block change?")
            explanation = ("Reads the current block, saves a durable eight-byte backup, commits one owned-field change, "
                           "and reads it back. Restore refuses intervening edits. No automatic retry or rollback. "
                           "This is not a full mouse backup; actual polling frequency is not measured. "
                           "Do not press DPI/profile buttons during the operation.")
            if action == "polling" and arguments["polling"] in (125, 250):
                explanation += " This target code is source-derived but has not been exercised on this mouse yet."
        if self.experimental_activation and action in ("polling", "buttons"):
            from .activation import APPLY_NOTICE
            explanation += "\n\n" + APPLY_NOTICE
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True,
                                   message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.NONE, text=title)
        dialog.format_secondary_text(explanation + "\n\nTargets the captured 30fa:1440 / 0100 interface only."
                                     + f"\nEvidence and backups: {self.control.capture_root}")
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Proceed", Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        try:
            accepted = dialog.run() == Gtk.ResponseType.ACCEPT
        finally:
            dialog.destroy()
        if not accepted:
            return
        self.operation_action = action
        self.busy = True
        self.refresh()
        progress = self.operation_progress.start()
        self.message.set_text("Device operation in progress. No automatic retries.")
        from gi.repository import GLib
        def work():
            try:
                result = self.control.run(action, confirmed=True, progress=progress, **arguments)
            except Exception as error:
                GLib.idle_add(self.operation_finished, action, None, str(error))
            else:
                GLib.idle_add(self.operation_finished, action, result, None)
        try:
            threading.Thread(target=work, daemon=False).start()
        except RuntimeError as error:
            self.operation_finished(action, None, f"Could not start the device worker: {error}")

    def operation_finished(self, action, result, error):
        self.operation_progress.finish(checking=error is None)
        self.busy = False
        if error is not None:
            self.model.presentation = None
            self.model.error = error
            self.model.error_details = error
            self.refresh()
            return False
        filename = {"read": "state-read.jsonl", "read-buttons": "button-read.jsonl",
                    "restore-shortcuts": "shortcut-configuration.jsonl",
                    "buttons": "button-configuration.jsonl", "restore-buttons": "button-configuration.jsonl"}.get(action, "configuration.jsonl")
        self.model.load(result.capture_directory / filename)
        self.refresh()
        if self.model.presentation is not None:
            import json
            data = json.loads(self.model.presentation.details)
            expected_activation = self.experimental_activation and action in ("polling", "buttons")
            if data.get("activation_requested", False) is not expected_activation:
                self.model.presentation = None
                self.model.error = "Saved verification does not match the requested activation policy"
                self.model.error_details = self.model.error
                self.refresh()
                return False
            self.message.set_text(f"{result.payload.get('outcome', 'State captured')}. "
                                  f"Behavior not measured. Evidence: {result.capture_directory}")
            if action == "polling" and result.payload.get("backup_file") == "original-state.json":
                self.last_backup = result.capture_directory / "original-state.json"
            if action in ("buttons", "restore-buttons"):
                if result.payload.get("backup_file") == "button-backup.json":
                    self.last_button_backup = result.capture_directory / "button-backup.json"
                self.message.set_text(f"{result.payload['outcome']}. Physically unplug for about 10 seconds and reconnect "
                                       f"to load native mappings. Evidence: {result.capture_directory}")
            if action == "restore-shortcuts":
                import json
                data = json.loads(self.model.presentation.details)
                if data.get("mode") != "offline-shortcut-configuration-inspection" or data.get("operation") != "restore":
                    self.model.presentation = None
                    self.model.error = "Saved verification does not describe a shortcut restore"
                    self.model.error_details = self.model.error
                    self.refresh()
                    return False
                if data.get("backup_file") == "shortcut-backup.json":
                    self.last_shortcut_backup = result.capture_directory / "shortcut-backup.json"
                self.message.set_text(f"{data['outcome']}. Physically unplug for about 10 seconds and reconnect. "
                                       f"Behavior not measured. Evidence: {result.capture_directory}")
            if data.get("activation_outcome") == "sequence-sent":
                self.message.set_text(f"Settings read back; activation sequence sent. Test now without replug. "
                                      f"Runtime effect unverified. Evidence: {result.capture_directory}")
            elif data.get("activation_outcome") == "skipped-no-change":
                self.message.set_text(f"Settings already stored; no write or activation sent. "
                                      f"Runtime behavior unverified. Evidence: {result.capture_directory}")
        return False

    def choose_backup(self, _button):
        if self.busy:
            return
        Gtk = self.Gtk
        dialog = Gtk.FileChooserDialog(title="Choose original-state.json backup", parent=self.window,
                                       action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Select", Gtk.ResponseType.ACCEPT)
        if self.last_backup is not None:
            dialog.set_filename(str(self.last_backup))
        try:
            selected = dialog.get_filename() if dialog.run() == Gtk.ResponseType.ACCEPT else None
        finally:
            dialog.destroy()
        if selected:
            self.confirm_operation("restore", restore_from=Path(selected))

    def choose_capture(self, _button):
        if self.busy:
            return
        Gtk = self.Gtk
        dialog = Gtk.FileChooserDialog(title="Open completed feature/state capture", parent=self.window,
                                       action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Open", Gtk.ResponseType.ACCEPT)
        capture_filter = Gtk.FileFilter()
        capture_filter.set_name("Saved feature/state journals (*.jsonl)")
        capture_filter.add_pattern("*.jsonl")
        dialog.add_filter(capture_filter)
        try:
            if dialog.run() == Gtk.ResponseType.ACCEPT:
                selected = dialog.get_filename()
                if selected:
                    self.model.load(Path(selected))
                    self.refresh()
        finally:
            dialog.destroy()

    def choose_button_backup(self, _button):
        if self.busy:
            return
        Gtk = self.Gtk
        dialog = Gtk.FileChooserDialog(title="Choose button-backup.json", parent=self.window,
                                       action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Select", Gtk.ResponseType.ACCEPT)
        if self.last_button_backup is not None:
            dialog.set_filename(str(self.last_button_backup))
        try:
            selected = dialog.get_filename() if dialog.run() == Gtk.ResponseType.ACCEPT else None
        finally:
            dialog.destroy()
        if selected:
            self.confirm_operation("restore-buttons", restore_from=Path(selected))

    def choose_shortcut_backup(self, _button):
        if self.busy:
            return
        Gtk = self.Gtk
        dialog = Gtk.FileChooserDialog(title="Choose shortcut-backup.json", parent=self.window,
                                       action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Select", Gtk.ResponseType.ACCEPT)
        if self.last_shortcut_backup is not None:
            dialog.set_filename(str(self.last_shortcut_backup))
        try:
            selected = dialog.get_filename() if dialog.run() == Gtk.ResponseType.ACCEPT else None
        finally:
            dialog.destroy()
        if selected:
            self.confirm_operation("restore-shortcuts", restore_from=Path(selected))


def json_mode(details):
    import json
    return json.loads(details)["mode"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, help="optional saved feature/state journal; never a device path")
    parser.add_argument("--diagnostics", action="store_true", help="open the original evidence and device controls directly")
    parser.add_argument("--skin-dir", type=Path, help="locally staged reference artwork (default: .work/ui-skin in the repository)")
    parser.add_argument("--page", choices=("buttons", "macros", "performance", "backlight"), default="buttons")
    artwork = parser.add_mutually_exclusive_group()
    artwork.add_argument("--generated-mouse", dest="generated_mouse", action="store_true",
                         help="use the supplied docs/Software_UI/MouseImage.png (default)")
    artwork.add_argument("--reference-mouse", dest="generated_mouse", action="store_false",
                         help="use the preserved original vendor mouse artwork instead")
    parser.set_defaults(generated_mouse=True)
    parser.add_argument("--render-previews", type=Path, metavar="DIRECTORY", help="export all four UI pages to PNG, without opening a window or contacting hardware")
    from .activation import APPLY_NOTICE
    parser.add_argument("--experimental-activation", action="store_true", help=APPLY_NOTICE)
    args = parser.parse_args(argv)
    try:
        Gtk = load_gtk()
    except (ImportError, ValueError) as error:
        print(f"Desktop viewer requires PyGObject and GTK 3: {error}. CLI tools do not require them.", file=sys.stderr)
        return 1
    if not Gtk.init_check([])[0]:
        print("Cannot open a desktop display. Use evofox_blaze.status for offline CLI inspection.", file=sys.stderr)
        return 1
    model = CaptureModel()
    if args.capture is not None:
        model.load(args.capture)
    control_options = ({"control": DeviceControl(experimental_activation=True)} if args.experimental_activation else {})
    if args.diagnostics or args.capture is not None:
        view = CaptureWindow(Gtk, model, **control_options)
    else:
        from .ui_layout import DEFAULT_SKIN
        root = Path(__file__).resolve().parents[1]
        directory = args.skin_dir if args.skin_dir is not None else root / DEFAULT_SKIN
        mouse = root / "docs/Software_UI/MouseImage.png"
        try:
            if args.render_previews is not None:
                from .ui_skin import Skin
                skin = Skin(directory, mouse if mouse.is_file() else None)
                skin.export(args.render_previews, generated_mouse=args.generated_mouse)
                print(f"Four UI previews saved to {args.render_previews}")
                return 0
            from .desktop import BlazeWindow
            view = BlazeWindow(Gtk, directory, model=model, page=args.page,
                                mouse_image=mouse if mouse.is_file() else None,
                                generated_mouse=args.generated_mouse, **control_options)
        except (OSError, ValueError, ImportError) as error:
            print(f"Cannot open reference UI: {error}", file=sys.stderr)
            return 1
    view.window.connect("destroy", lambda _window: Gtk.main_quit())
    view.window.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
