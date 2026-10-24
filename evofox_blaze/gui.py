"""EvoFox Blaze reference UI and confirmed experimental device controls (GTK 3)."""

import argparse
from pathlib import Path
import sys
import threading

from .capture_view import CaptureModel
from .device_control import DeviceControl


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
        self.busy = False
        self.last_backup = None
        self.window = Gtk.Window(title="EvoFox Blaze — Experimental controls")
        self.window.connect("delete-event", self.prevent_close_while_busy)
        self.window.set_default_size(900, 640)
        self.window.set_border_width(16)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.window.add(content)
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

        self.message = Gtk.Label(xalign=0)
        self.message.set_line_wrap(True)
        self.message.set_selectable(True)
        content.pack_start(self.message, False, False, 0)

        tabs = Gtk.Notebook()
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
            "No automatic device access: each read, polling change or restore requires confirmation.\n"
            "Polling bytes have been written/read back/restored; actual frequency is not measured.\n"
            "Lighting, CPI values, buttons, profiles and macros are not implemented. Backups cover one block, not the whole mouse."
        ), xalign=0)
        warning.set_line_wrap(True)
        content.pack_start(warning, False, False, 0)
        self.refresh()

    def refresh(self):
        self.rows.clear()
        self.details.set_text("")
        state_loaded = (self.model.presentation is not None
                        and json_mode(self.model.presentation.details) in
                        ("offline-state-inspection", "offline-configuration-inspection"))
        for widget in (self.opened, self.read_button, self.restore_button):
            widget.set_sensitive(not self.busy)
        for widget in (self.polling, self.apply_button):
            widget.set_sensitive(not self.busy and state_loaded)
        if self.model.presentation is None:
            self.message.set_text(self.model.error or "Open a completed feature-read.jsonl or state-read.jsonl capture to inspect it offline.")
            return
        self.message.set_text("Saved capture loaded. Field interpretations are candidates, not verified behavior measurements.")
        for row in self.model.presentation.rows:
            self.rows.append(row)
        self.details.set_text(self.model.presentation.details)

    def prevent_close_while_busy(self, _window, _event):
        if self.busy:
            self.message.set_text("A device operation is in progress. Wait for its result; do not interrupt a settings commit.")
        return self.busy

    def confirm_operation(self, action, **arguments):
        if self.busy:
            return
        Gtk = self.Gtk
        if action == "read":
            title = "Read one eight-byte state block?"
            explanation = ("Sends 18 SET_REPORTs including zero-data staging and 8 GET_REPORTs. "
                           "No settings commit, reset or firmware command. No retry on failure.")
        else:
            title = (f"Change polling setting to {arguments['polling']} Hz?" if action == "polling"
                     else "Restore this saved block change?")
            explanation = ("Reads the current block, saves a durable eight-byte backup, commits one owned-field change, "
                           "and reads it back. Restore refuses intervening edits. No automatic retry or rollback. "
                           "This is not a full mouse backup; actual polling frequency is not measured. "
                           "Do not press DPI/profile buttons during the operation.")
            if action == "polling" and arguments["polling"] in (125, 250):
                explanation += " This target code is source-derived but has not been exercised on this mouse yet."
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
        self.busy = True
        self.refresh()
        self.message.set_text("Device operation in progress. No automatic retries.")
        from gi.repository import GLib
        def work():
            try:
                result = self.control.run(action, confirmed=True, **arguments)
            except Exception as error:
                GLib.idle_add(self.operation_finished, action, None, str(error))
            else:
                GLib.idle_add(self.operation_finished, action, result, None)
        threading.Thread(target=work, daemon=False).start()

    def operation_finished(self, action, result, error):
        self.busy = False
        if error is not None:
            self.model.presentation = None
            self.model.error = error
            self.refresh()
            return False
        filename = "state-read.jsonl" if action == "read" else "configuration.jsonl"
        self.model.load(result.capture_directory / filename)
        self.refresh()
        if self.model.presentation is not None:
            self.message.set_text(f"{result.payload.get('outcome', 'State captured')}. "
                                  f"Behavior not measured. Evidence: {result.capture_directory}")
            if action == "polling" and result.payload.get("backup_file") == "original-state.json":
                self.last_backup = result.capture_directory / "original-state.json"
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


def json_mode(details):
    import json
    return json.loads(details)["mode"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, help="optional saved feature/state journal; never a device path")
    parser.add_argument("--diagnostics", action="store_true", help="open the original evidence and device controls directly")
    parser.add_argument("--skin-dir", type=Path, help="locally staged reference artwork (default: .work/ui-skin in the repository)")
    parser.add_argument("--page", choices=("buttons", "macros", "performance", "backlight"), default="buttons")
    parser.add_argument("--generated-mouse", action="store_true", help="use docs/Software_UI/MouseImage.png instead of the exact reference mouse")
    parser.add_argument("--render-previews", type=Path, metavar="DIRECTORY", help="export all four UI pages to PNG, without opening a window or contacting hardware")
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
    if args.diagnostics or args.capture is not None:
        view = CaptureWindow(Gtk, model)
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
                               generated_mouse=args.generated_mouse)
        except (OSError, ValueError, ImportError) as error:
            print(f"Cannot open reference UI: {error}", file=sys.stderr)
            return 1
    view.window.connect("destroy", lambda _window: Gtk.main_quit())
    view.window.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
