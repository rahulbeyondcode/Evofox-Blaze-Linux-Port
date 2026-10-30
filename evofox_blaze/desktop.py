"""Resizable native GTK shell for the reference Blaze interface.

Focusable GTK buttons supply real hit targets and accessibility semantics;
Cairo paints the skin beneath them so host themes cannot alter its geometry.
Unsupported settings are insensitive or explicit menu no-ops, never simulated
as successful device edits.
"""

import json
import threading
from functools import lru_cache
from pathlib import Path

from .capture_view import CaptureModel
from .gui import CaptureWindow
from .ui_layout import HEIGHT, WIDTH, PAGES, Viewport, controls_for
from .ui_skin import Skin
from .button_draft import ButtonDraft
from .button_menu import ASSIGNMENT_MENU
from .activation import APPLY_BANNER
from .operation_overlay import OperationOverlay
from .operation_progress import OperationProgress


BUTTON_MESSAGE = "EvoFox Blaze — Mouse configuration"


@lru_cache(maxsize=1)
def target_layer_type(Gtk):
    class TargetLayer(Gtk.Fixed):
        # Scaled child requests must not become the window's minimum size;
        # otherwise growing once would prevent subsequently shrinking it.
        def do_get_preferred_width(self):
            return 0, 0

        def do_get_preferred_height(self):
            return 0, 0

        def do_size_allocate(self, allocation):
            # Update child geometry before Gtk.Fixed allocates its children.
            # A size-allocate signal handler runs after that allocation and
            # would leave click targets one resize behind the painted artwork.
            if hasattr(self, "on_allocate"):
                self.on_allocate(self, allocation)
            Gtk.Fixed.do_size_allocate(self, allocation)

    return TargetLayer


class LinkedCaptureWindow(CaptureWindow):
    def __init__(self, owner):
        self.owner = owner
        super().__init__(owner.Gtk, owner.model, control=owner.control)

    def refresh(self):
        super().refresh()
        self.owner.sync_controls()

    def confirm_operation(self, action, **arguments):
        if self.owner.button_busy or self.owner.shortcut_editor is not None:
            return
        super().confirm_operation(action, **arguments)

    def progress_overlays(self):
        return self.owner.progress_overlays()


class BlazeWindow:
    def __init__(self, Gtk, skin_directory, model=None, control=None, page="buttons",
                 mouse_image=None, generated_mouse=True):
        from gi.repository import Gdk
        self.Gtk, self.Gdk = Gtk, Gdk
        if mouse_image is None:
            mouse_image = Path(__file__).resolve().parents[1] / "docs/Software_UI/MouseImage.png"
        self.skin = Skin(skin_directory, mouse_image)
        self.model = model if model is not None else CaptureModel()
        # DeviceControl construction does not enumerate or open a device.
        if control is None:
            from .device_control import DeviceControl
            control = DeviceControl()
        self.control = control
        self.experimental_activation = getattr(control, "experimental_activation", False) is True
        self.history_path = None
        if self.model.presentation is None and not self.model.error:
            from .assignment_history import latest_assignments
            recovered, self.history_path = latest_assignments(self.control.capture_root)
            if recovered.presentation is not None or recovered.error:
                self.model.presentation, self.model.error = recovered.presentation, recovered.error
                self.model.error_details = recovered.error_details
        self.diagnostics = None
        self.page = page
        self.generated_mouse = generated_mouse
        self.hover = None
        self.polling = None
        self.captured_polling = None
        self.evidence_signature = None
        self.button_draft = ButtonDraft()
        self.button_busy = False
        self.button_operation = None
        self.button_message = self.model.error or BUTTON_MESSAGE
        self.assignment_menu = None
        self.shortcut_editor = None
        self.last_button_backup = None
        self.last_shortcut_backup = None
        self.viewport = Viewport.fit(WIDTH, HEIGHT)
        self.buttons = {}
        self.specs = {}
        self.window = Gtk.Window(title="EvoFox Blaze — UI preview (no device read)")
        self.window.set_decorated(False)
        self.window.set_resizable(True)
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.set_size_request(640, 461)
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        workarea = monitor.get_workarea()
        scale = min(1.25, workarea.width * 0.92 / WIDTH, workarea.height * 0.9 / HEIGHT)
        self.window.set_default_size(round(WIDTH * scale), round(HEIGHT * scale))
        self.window.connect("delete-event", self.prevent_close)
        self.window.connect("destroy", self.destroy_children)
        self.window.connect("key-press-event", self.key_pressed)
        overlay = Gtk.Overlay()
        self.window.add(overlay)
        self.canvas = Gtk.DrawingArea()
        self.canvas.set_hexpand(True)
        self.canvas.set_vexpand(True)
        overlay.add(self.canvas)
        self.targets = target_layer_type(Gtk)()
        overlay.add_overlay(self.targets)
        self.targets.set_hexpand(True)
        self.targets.set_vexpand(True)
        self.operation_overlay = OperationOverlay(Gtk, overlay, self.targets)
        self.operation_progress = OperationProgress(self.progress_overlays)
        self.canvas.connect("draw", self.draw)
        self.targets.on_allocate = self.allocate
        # Fixed is a windowless overlay: background input belongs to the
        # DrawingArea's GdkWindow, not the layer containing the GTK buttons.
        self.canvas.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK
                               | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.canvas.connect("button-press-event", self.background_pressed)
        self.canvas.connect("motion-notify-event", self.background_motion)
        self.canvas.connect("leave-notify-event", self.background_left)
        self.canvas.set_has_tooltip(True)
        self.canvas.connect("query-tooltip", self.query_tooltip)
        self.background_cursors = {}
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
            .blaze-hit-target, .blaze-hit-target:hover, .blaze-hit-target:active,
            .blaze-hit-target:disabled, .blaze-hit-target:focus {
                background: transparent; background-image: none; border: none;
                box-shadow: none; outline: none; padding: 0; margin: 0;
                min-width: 0; min-height: 0; border-radius: 0;
            }
        """)
        self.provider = provider
        self.menu_provider = Gtk.CssProvider()
        self.menu_provider.load_from_data(b"""
            .blaze-assignment-menu { background-color: #101820; color: #eeeeee; }
            menu.blaze-assignment-menu { border: 1px solid #456073; padding: 4px 0; }
            menuitem.blaze-assignment-menu { padding: 5px 14px; min-height: 18px; }
            menuitem.blaze-assignment-menu:hover { background-color: #006b91; }
            menuitem.blaze-assignment-menu arrow { color: #eeeeee; }
        """)
        self.build_targets()

    @property
    def busy(self):
        return self.button_busy or (self.diagnostics is not None and self.diagnostics.busy)

    @property
    def can_apply(self):
        if self.busy or self.shortcut_editor is not None:
            return False
        if self.page == "buttons":
            return self.button_draft.can_apply
        return (self.page == "performance" and self.captured_polling is not None
                and self.polling is not None and self.polling != self.captured_polling)

    def build_targets(self):
        for button in self.buttons.values():
            button.destroy()
        self.buttons.clear()
        self.specs = {spec.name: spec for spec in controls_for(self.page)}
        for spec in self.specs.values():
            button = self.Gtk.Button()
            button.set_can_focus(True)
            button.set_focus_on_click(False)
            button.set_name(f"blaze-{spec.name}")
            button.get_style_context().add_class("blaze-hit-target")
            button.get_style_context().add_provider(self.provider, self.Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            accessible = button.get_accessible()
            accessible.set_name(spec.label)
            accessible.set_description(spec.limitation or spec.label)
            button.connect("clicked", self.activate, spec.name)
            button.connect("enter-notify-event", self.enter, spec.name)
            button.connect("leave-notify-event", self.leave)
            button.connect("focus-in-event", self.focus_changed)
            button.connect("focus-out-event", self.focus_changed)
            button.connect("button-press-event", self.target_pressed)
            self.targets.put(button, 0, 0)
            self.buttons[spec.name] = button
        self.sync_controls()
        self.place_targets()
        self.targets.show_all()

    def sync_controls(self):
        details = self.model.presentation.details if self.model.presentation is not None else None
        self.button_draft.sync(details)
        if details != self.evidence_signature:
            self.evidence_signature = details
            self.captured_polling = None
            if details:
                data = json.loads(details)
                if data.get("mode") in ("offline-state-inspection", "offline-configuration-inspection"):
                    candidate = data.get("polling_hz_candidate")
                    if candidate in (125, 250, 500, 1000):
                        self.captured_polling = candidate
            self.polling = self.captured_polling
        for name, button in self.buttons.items():
            spec = self.specs[name]
            enabled = bool(spec.action) and not self.busy
            tooltip = "Not implemented." if not spec.action else None
            if spec.action == "polling":
                enabled = enabled and self.captured_polling is not None
                tooltip = "Read mouse state first (F1)." if self.captured_polling is None else None
            elif spec.action == "apply":
                enabled = self.can_apply
            elif spec.action == "button":
                index = int(name.split("-")[1])
                labels = self.button_draft.labels()
                if labels is not None:
                    button.get_accessible().set_name(f"Button {index}: {labels[index - 1]} (stored/draft)")
                else:
                    button.get_accessible().set_name(spec.label)
                tooltip = ("Not implemented." if index == 8 else
                           labels[index - 1] if len(labels[index - 1]) > 22 else None)
            elif spec.action == "operation-details":
                enabled = enabled and bool(self.model.error)
            if name in ("close", "minimize"):
                enabled = not self.busy
            button.set_sensitive(enabled)
            button.set_tooltip_text(None if self.busy else tooltip)
        if self.busy:
            self.close_assignment_menu()
        operation = self.button_operation if self.button_busy else getattr(self.diagnostics, "operation_action", None)
        self.operation_overlay.set_busy(self.busy, reading=bool(operation and operation.startswith("read")))
        self.window.set_title("EvoFox Blaze — " + (
            "operation in progress" if self.busy else
            "saved evidence (not live)" if self.captured_polling is not None or self.button_draft.block is not None else
            "UI preview (no device read)"))
        self.window.get_accessible().set_description(self.button_message)
        self.canvas.queue_draw()

    def place_targets(self):
        for name, button in self.buttons.items():
            x, y, width, height = self.viewport.place(self.specs[name].rect)
            self.targets.move(button, x, y)
            button.set_size_request(width, height)

    def allocate(self, _widget, allocation):
        viewport = Viewport.fit(allocation.width, allocation.height)
        if viewport != self.viewport:
            self.viewport = viewport
            self.place_targets()
            self.canvas.queue_draw()

    def draw(self, _widget, ctx):
        ctx.set_source_rgb(0.015, 0.018, 0.025)
        ctx.paint()
        ctx.save()
        ctx.translate(self.viewport.x, self.viewport.y)
        ctx.scale(self.viewport.scale, self.viewport.scale)
        focused = next((self.specs[name].rect for name, button in self.buttons.items()
                        if button.has_visible_focus()), None)
        message = APPLY_BANNER if self.experimental_activation and self.button_message == BUTTON_MESSAGE else self.button_message
        self.skin.draw(ctx, self.page, self.hover, focused, self.polling,
                        self.generated_mouse, self.can_apply, self.button_draft.labels(), message,
                        "Saved assignments (not live)\nRead to refresh" if self.button_draft.block is not None else
                        "No saved assignments\nRead mouse to load", has_error=bool(self.model.error))
        ctx.restore()
        return False

    def select_page(self, page):
        if page not in PAGES:
            raise ValueError(f"Unknown UI page: {page}")
        if self.busy or self.shortcut_editor is not None:
            return
        self.close_assignment_menu()
        self.page = page
        self.hover = None
        self.build_targets()

    def activate(self, _button, name):
        # Check sensitivity here as well: programmatic clicked emissions must
        # not bypass disabled unsupported controls or a busy operation.
        if self.shortcut_editor is not None or not self.buttons[name].get_sensitive():
            return
        action = self.specs[name].action
        if action == "page":
            self.select_page(name)
        elif action == "minimize":
            self.window.iconify()
        elif action == "close":
            self.window.close()
        elif action == "cancel":
            if self.page == "buttons" and self.button_draft.has_changes:
                self.button_draft.cancel()
                if not self.model.error:
                    self.button_message = BUTTON_MESSAGE
                self.sync_controls()
            elif self.page == "performance" and self.polling != self.captured_polling:
                self.polling = self.captured_polling
                self.sync_controls()
            else:
                self.window.close()
        elif action == "polling":
            self.polling = int(name.split("-")[1])
            self.sync_controls()
        elif action == "button":
            self.choose_button_action(int(name.split("-")[1]))
        elif action == "read-assignments":
            self.read_assignments()
        elif action == "operation-details":
            self.show_devices()
            self.diagnostics.tabs.set_current_page(1)
        elif action == "apply" and self.can_apply:
            if self.page == "buttons":
                self.apply_buttons()
            else:
                self.show_devices()
                self.diagnostics.polling.set_active_id(str(self.polling))
                self.diagnostics.confirm_operation("polling", polling=self.polling)
            self.sync_controls()

    def choose_button_action(self, index):
        if self.busy or self.shortcut_editor is not None or type(index) is not int or not 1 <= index <= 8:
            return
        Gtk = self.Gtk
        self.close_assignment_menu()
        root = Gtk.Menu()

        def populate(menu, entries):
            menu.set_direction(Gtk.TextDirection.LTR)
            menu.get_style_context().add_class("blaze-assignment-menu")
            menu.get_style_context().add_provider(self.menu_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            for entry in entries:
                item = Gtk.MenuItem(label=entry.label)
                item.get_style_context().add_class("blaze-assignment-menu")
                item.get_style_context().add_provider(self.menu_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
                if entry.children:
                    submenu = Gtk.Menu()
                    populate(submenu, entry.children)
                    item.set_submenu(submenu)
                    # GTK's menu shell handles click, hover and keyboard
                    # cascading, with a right-facing arrow and screen-edge fit.
                else:
                    item.set_tooltip_text("Not implemented." if index == 8 or entry.action is None else None)
                    item.connect("activate", self.assignment_chosen, index, entry, root)
                menu.append(item)

        populate(root, ASSIGNMENT_MENU)
        self.assignment_menu = root
        root.show_all()
        root.popup_at_widget(self.buttons[f"button-{index}"], self.Gdk.Gravity.SOUTH_WEST,
                             self.Gdk.Gravity.NORTH_WEST, Gtk.get_current_event())

    def close_assignment_menu(self):
        if self.assignment_menu is not None:
            self.assignment_menu.popdown()
            self.assignment_menu.destroy()
            self.assignment_menu = None

    def assignment_chosen(self, _item, index, entry, root):
        root.popdown()  # Also dismiss every cascaded submenu, including placeholders.
        if entry.action == "shortcut":
            self.choose_shortcut(index)
            return
        if self.busy or entry.action is None or not self.button_draft.editable(index):
            return
        try:
            self.button_draft.assign(index, entry.action)
        except ValueError as error:
            self.button_message = f"Assignment not available: {error}. No device changes."
        else:
            if not self.model.error:
                self.button_message = BUTTON_MESSAGE
        self.sync_controls()

    def choose_shortcut(self, index):
        if self.busy or type(index) is not int or not 1 <= index <= 8:
            return
        if self.shortcut_editor is None:
            from .shortcut_editor import ShortcutEditor
            self.close_assignment_menu()
            self.shortcut_editor = ShortcutEditor(self, index, self.button_draft.shortcut(index))
        self.shortcut_editor.window.show_all()
        self.shortcut_editor.window.present()
        self.sync_controls()

    def save_shortcut(self, index, shortcut, signature):
        # Save is local draft state only. Never pass a shortcut through the
        # native-action writer or fabricate extension-table bytes/backups.
        if self.busy or self.page != "buttons" or self.button_draft.signature != signature:
            return False
        try:
            self.button_draft.assign_shortcut(index, shortcut)
        except ValueError:
            return False
        if not self.model.error:
            self.button_message = BUTTON_MESSAGE
        self.sync_controls()
        return True

    def apply_buttons(self):
        """The visible Apply click is authorization; menu selection is offline."""
        if self.page != "buttons" or not self.can_apply:
            return
        from gi.repository import GLib
        assignments = dict(self.button_draft.pending)
        shortcuts = dict(self.button_draft.shortcuts)
        self.close_assignment_menu()
        self.button_busy = True
        self.button_operation = "save"
        self.button_message = "Applying assignments: validating, backing up and verifying. Do not press buttons or unplug yet."
        if self.experimental_activation:
            self.button_message += " Then sending the experimental activation candidate."
        if self.diagnostics is not None:
            self.diagnostics.busy = True
            self.diagnostics.operation_action = "shortcuts" if shortcuts else "buttons"
            self.diagnostics.refresh()
        self.sync_controls()
        progress = self.operation_progress.start()

        def work():
            try:
                if shortcuts:
                    result = self.control.run("shortcuts", assignments=assignments, shortcuts=shortcuts,
                                              confirmed=True, progress=progress)
                else:
                    result = self.control.run("buttons", assignments=assignments, confirmed=True, progress=progress)
            except Exception as error:
                GLib.idle_add(self.buttons_finished, assignments, None, str(error), shortcuts)
            else:
                GLib.idle_add(self.buttons_finished, assignments, result, None, shortcuts)

        try:
            threading.Thread(target=work, daemon=False).start()
        except RuntimeError as error:
            self.buttons_finished(assignments, None, f"Could not start the device worker: {error}", shortcuts)

    def read_assignments(self):
        if self.busy or self.shortcut_editor is not None:
            return
        Gtk = self.Gtk
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True,
                                   message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.NONE,
                                   text="Read current mouse assignments and keyboard shortcuts?")
        dialog.format_secondary_text(
            "• Reads stored buttons and shortcuts: 81–116 fixed blocks.\n"
            "• 1,458–2,088 staged SETs / 648–928 GETs; zero-data staging risk. No settings commit.\n"
            "• Replaces drafts only on success. Button 8 is not implemented.\n\n"
            "Unknown layouts are refused. No reset, input monitoring or automatic retry.")
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Read assignments", Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        try:
            accepted = dialog.run() == Gtk.ResponseType.ACCEPT
        finally:
            dialog.destroy()
        if not accepted:
            return
        from gi.repository import GLib
        self.button_busy = True
        self.button_operation = "read-assignments"
        self.button_message = "Reading mouse assignments and keyboard records. Do not press buttons or unplug yet."
        if self.diagnostics is not None:
            self.diagnostics.busy = True
            self.diagnostics.operation_action = "read-assignments"
            self.diagnostics.refresh()
        self.sync_controls()
        progress = self.operation_progress.start()

        def work():
            try:
                result = self.control.run("read-assignments", confirmed=True, progress=progress)
            except Exception as error:
                GLib.idle_add(self.assignments_read_finished, None, str(error))
            else:
                GLib.idle_add(self.assignments_read_finished, result, None)
        try:
            threading.Thread(target=work, daemon=False).start()
        except RuntimeError as error:
            self.assignments_read_finished(None, f"Could not start the read worker: {error}")

    def assignments_read_finished(self, result, error):
        self.operation_progress.finish(checking=error is None)
        self.button_busy = False
        if self.diagnostics is not None:
            self.diagnostics.busy = False
        checked = CaptureModel()
        if error is None:
            if not checked.load(result.capture_directory / "assignments.jsonl"):
                error = checked.error
            elif json.loads(checked.presentation.details).get("mode") != "offline-assignment-inspection":
                error = "Saved result is not a scoped assignment read"
        if error is not None:
            self.model.presentation = None
            self.model.error = error
            self.model.error_details = checked.error_details or error
            self.button_draft.invalidate_evidence()
            self.button_message = f"Read failed. Existing drafts kept; no automatic retry. {error}"
        else:
            self.model.presentation, self.model.error = checked.presentation, ""
            self.model.error_details = ""
            self.button_draft.cancel()
            self.button_draft.sync(checked.presentation.details)
            self.history_path = result.capture_directory / "assignments.jsonl"
            self.button_message = "Mouse assignments read. Labels show stored assignments, not physical button events."
        if self.diagnostics is not None:
            self.diagnostics.refresh()
        self.sync_controls()
        return False

    def buttons_finished(self, assignments, result, error, shortcuts=None):
        self.operation_progress.finish(checking=error is None)
        from .button_write import assignment_rows
        from .shortcut_plan import shortcut_rows
        shortcuts = shortcuts or {}
        error_details = ""
        self.button_busy = False
        if self.diagnostics is not None:
            self.diagnostics.busy = False
        if error is None:
            checked = CaptureModel()
            filename = "shortcut-configuration.jsonl" if shortcuts else "button-configuration.jsonl"
            if not checked.load(result.capture_directory / filename):
                error = checked.error
                error_details = checked.error_details
            else:
                data = json.loads(checked.presentation.details)
                expected_mode = "offline-shortcut-configuration-inspection" if shortcuts else "offline-button-configuration-inspection"
                if (data.get("mode") != expected_mode
                        or data.get("operation") != "change"
                        or data.get("assignments") != (assignment_rows(assignments) if assignments else [])
                         or (shortcuts and data.get("shortcuts") != shortcut_rows(shortcuts))
                        or data.get("activation_requested", False) is not self.experimental_activation
                        or data.get("outcome") not in ("written-and-read-back", "no-change")):
                    error = "Saved verification does not match the requested assignments"
        if error is not None:
            self.model.presentation = None
            self.model.error = error
            self.model.error_details = error_details or error
            self.button_draft.invalidate_evidence()
            self.button_draft.pending.clear()
            self.button_draft.pending.update(assignments)
            self.button_draft.shortcuts.clear()
            self.button_draft.shortcuts.update(shortcuts)
            self.button_message = f"Apply failed. No automatic retry; review evidence before trying again. {error}"
        else:
            self.model.presentation = checked.presentation
            self.model.error = ""
            self.model.error_details = ""
            self.button_draft.cancel()
            self.button_draft.sync(checked.presentation.details)
            if data["outcome"] == "written-and-read-back":
                self.button_message = ("Assignments saved/read back; activation sequence sent. Test now without replug. Runtime behavior unverified."
                                       if data.get("activation_outcome") == "sequence-sent" else
                                       "Assignments saved and read back. Unplug for about 10 seconds and reconnect to activate.")
            else:
                self.button_message = ("Assignments already stored; no write or activation sent. Reconnect if the running mapping differs."
                                       if self.experimental_activation else
                                       "Assignments already stored; no write needed. Reconnect if the running mapping differs.")
            if data.get("backup_file") == "button-backup.json":
                self.last_button_backup = result.capture_directory / "button-backup.json"
                if self.diagnostics is not None:
                    self.diagnostics.last_button_backup = self.last_button_backup
            elif data.get("backup_file") == "shortcut-backup.json":
                self.last_shortcut_backup = result.capture_directory / "shortcut-backup.json"
                if self.diagnostics is not None:
                    self.diagnostics.last_shortcut_backup = self.last_shortcut_backup
        if self.diagnostics is not None:
            self.diagnostics.refresh()
        self.sync_controls()
        return False

    def progress_overlays(self):
        overlays = [self.operation_overlay]
        if self.diagnostics is not None:
            overlays.append(self.diagnostics.operation_overlay)
        return overlays

    def show_devices(self):
        if self.button_busy or self.shortcut_editor is not None:
            return
        if self.diagnostics is None:
            view = LinkedCaptureWindow(self)
            self.diagnostics = view
            view.last_button_backup = self.last_button_backup
            view.last_shortcut_backup = self.last_shortcut_backup
            view.window.set_transient_for(self.window)
            view.window.connect("destroy", self.devices_destroyed)
        self.diagnostics.window.show_all()
        self.diagnostics.window.present()
        self.sync_controls()

    def devices_destroyed(self, _window):
        self.diagnostics = None
        self.sync_controls()

    def read_state(self, _item=None):
        if not self.busy:
            self.show_devices()
            self.diagnostics.confirm_operation("read")

    def read_button_assignments(self, _item=None):
        if not self.busy:
            self.show_devices()
            self.diagnostics.confirm_operation("read-buttons")

    def enter(self, _button, _event, name):
        self.hover = name
        self.canvas.queue_draw()
        return False

    def leave(self, _button, _event):
        self.hover = None
        self.canvas.queue_draw()
        return False

    def focus_changed(self, _button, _event):
        self.canvas.queue_draw()
        return False

    def target_pressed(self, _button, event):
        # Right-click has no context menu and must not activate an assignment.
        return event.button == 3

    def background_pressed(self, _widget, event):
        if event.button == 3:
            return True
        if event.button != 1:
            return False
        gesture = self.background_gesture(event.x, event.y)
        if gesture is None:
            return False
        self.close_assignment_menu()
        args = (1, int(event.x_root), int(event.y_root), event.time)
        if gesture == "move":
            self.window.begin_move_drag(*args)
        else:
            self.window.begin_resize_drag(getattr(self.Gdk.WindowEdge, gesture.upper()), *args)
        return True

    def background_gesture(self, x, y):
        if self.busy:
            return None
        rx, ry = self.viewport.to_reference(x, y)
        # Never turn controls (including disabled ones) into drag handles.
        if any(spec.rect.contains(rx, ry) for spec in self.specs.values()):
            return None
        allocation = self.canvas.get_allocation()
        if not (0 <= x < allocation.width and 0 <= y < allocation.height):
            return None
        # Keep the physical hit band usable at every artwork scale, including
        # the letterboxed margins of a non-proportional window.
        vertical = "north" if y < 8 else "south" if y >= allocation.height - 8 else ""
        horizontal = "west" if x < 8 else "east" if x >= allocation.width - 8 else ""
        if vertical or horizontal:
            return "_".join(part for part in (vertical, horizontal) if part)
        if (0 <= rx < 935 and 0 <= ry < 65) or (367 <= rx < 681 and 0 <= ry < 134):
            return "move"
        return None

    def background_motion(self, _widget, event):
        gesture = self.background_gesture(event.x, event.y)
        names = {"move": "grab", "north": "n-resize", "south": "s-resize",
                 "west": "w-resize", "east": "e-resize", "north_west": "nw-resize",
                 "north_east": "ne-resize", "south_west": "sw-resize", "south_east": "se-resize"}
        window = self.canvas.get_window()
        if window is not None:
            if gesture is not None and gesture not in self.background_cursors:
                self.background_cursors[gesture] = self.Gdk.Cursor.new_from_name(window.get_display(), names[gesture])
            window.set_cursor(self.background_cursors.get(gesture))
        return False

    def background_left(self, _widget, _event):
        window = self.canvas.get_window()
        if window is not None:
            window.set_cursor(None)
        return False

    def query_tooltip(self, _widget, x, y, _keyboard, tooltip):
        if self.busy:
            return False
        x, y = self.viewport.to_reference(x, y)
        for name, spec in self.specs.items():
            if spec.rect.contains(x, y):
                text = self.buttons[name].get_tooltip_text()
                if text:
                    tooltip.set_text(text)
                    return True
                return False
        return False

    def key_pressed(self, _widget, event):
        if self.busy:
            return True
        if self.shortcut_editor is not None:
            return True  # Editor recordings must not trigger parent shortcuts.
        name = self.Gdk.keyval_name(event.keyval)
        if name == "F1":
            self.show_devices()
            return True
        if event.state & self.Gdk.ModifierType.CONTROL_MASK and name in ("1", "2", "3", "4"):
            self.select_page(PAGES[int(name) - 1])
            return True
        if name == "Escape" and not self.busy:
            self.activate(None, "cancel")
            return True
        return False

    def prevent_close(self, _window, _event):
        if self.busy:
            if self.button_busy:
                self.button_message = "A mouse operation is in progress. Wait for completion before closing or unplugging."
                self.canvas.queue_draw()
            elif self.diagnostics is not None:
                self.diagnostics.prevent_close_while_busy(None, None)
                self.diagnostics.window.present()
        return self.busy

    def destroy_children(self, _window):
        self.close_assignment_menu()
        if self.shortcut_editor is not None:
            self.shortcut_editor.window.destroy()
        if self.diagnostics is not None:
            self.diagnostics.window.destroy()
