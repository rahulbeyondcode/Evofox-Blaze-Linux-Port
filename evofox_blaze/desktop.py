"""Resizable native GTK shell for the reference Blaze interface.

Focusable GTK buttons supply real hit targets and accessibility semantics;
Cairo paints the skin beneath them so host themes cannot alter its geometry.
Unsupported settings are insensitive, not simulated as successful device edits.
"""

import json
from functools import lru_cache

from .capture_view import CaptureModel
from .gui import CaptureWindow
from .ui_layout import HEIGHT, WIDTH, PAGES, Viewport, controls_for
from .ui_skin import Skin


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


class BlazeWindow:
    def __init__(self, Gtk, skin_directory, model=None, control=None, page="buttons",
                 mouse_image=None, generated_mouse=False):
        from gi.repository import Gdk
        self.Gtk, self.Gdk = Gtk, Gdk
        self.skin = Skin(skin_directory, mouse_image)
        self.model = model if model is not None else CaptureModel()
        # DeviceControl construction does not enumerate or open a device.
        if control is None:
            from .device_control import DeviceControl
            control = DeviceControl()
        self.control = control
        self.diagnostics = None
        self.page = page
        self.generated_mouse = generated_mouse
        self.hover = None
        self.polling = None
        self.captured_polling = None
        self.evidence_signature = None
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
        self.canvas.connect("draw", self.draw)
        self.targets.on_allocate = self.allocate
        self.targets.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.targets.connect("button-press-event", self.background_pressed)
        self.targets.set_has_tooltip(True)
        self.targets.connect("query-tooltip", self.query_tooltip)
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
        self.build_targets()

    @property
    def busy(self):
        return self.diagnostics is not None and self.diagnostics.busy

    @property
    def can_apply(self):
        return (not self.busy and self.page == "performance"
                and self.captured_polling is not None and self.polling is not None
                and self.polling != self.captured_polling)

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
        if details != self.evidence_signature:
            self.evidence_signature = details
            self.captured_polling = None
            if details:
                data = json.loads(details)
                if data.get("mode") != "offline-status-inspection":
                    candidate = data.get("polling_hz_candidate")
                    if candidate in (125, 250, 500, 1000):
                        self.captured_polling = candidate
            self.polling = self.captured_polling
        for name, button in self.buttons.items():
            spec = self.specs[name]
            enabled = bool(spec.action) and not self.busy
            tooltip = spec.limitation
            if spec.action == "polling":
                enabled = enabled and self.captured_polling is not None
                tooltip = ("Select a draft polling target; Apply asks for separate confirmation. "
                           "Stored setting candidate, not measured frequency." if enabled else
                           "Read mouse state first: press F1 or right-click → Read mouse state. "
                           "The initial 500 Hz highlight is from the reference, not a live reading.")
            elif spec.action == "apply":
                enabled = self.can_apply
                tooltip = ("Apply only the selected polling setting, with confirmation and a scoped backup."
                           if enabled else "No supported pending changes. Only polling can currently be applied; use F1 to read state first.")
            elif spec.action == "page":
                tooltip = f"{spec.label} — Ctrl+{PAGES.index(name) + 1}"
            elif spec.action == "cancel":
                tooltip = "Discard the draft polling selection; close if no selection is pending."
            if name in ("close", "minimize"):
                enabled = not self.busy
            button.set_sensitive(enabled)
            button.set_tooltip_text(tooltip or spec.label)
        self.window.set_title("EvoFox Blaze — " + (
            "operation in progress" if self.busy else
            "saved evidence (not live)" if self.captured_polling is not None else
            "UI preview (no device read)"))
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
        self.skin.draw(ctx, self.page, self.hover, focused, self.polling,
                       self.generated_mouse, self.can_apply)
        ctx.restore()
        return False

    def select_page(self, page):
        if page not in PAGES:
            raise ValueError(f"Unknown UI page: {page}")
        if self.busy:
            return
        self.page = page
        self.hover = None
        self.build_targets()

    def activate(self, _button, name):
        # Check sensitivity here as well: programmatic clicked emissions must
        # not bypass disabled unsupported controls or a busy operation.
        if not self.buttons[name].get_sensitive():
            return
        action = self.specs[name].action
        if action == "page":
            self.select_page(name)
        elif action == "minimize":
            self.window.iconify()
        elif action == "close":
            self.window.close()
        elif action == "cancel":
            if self.polling != self.captured_polling:
                self.polling = self.captured_polling
                self.sync_controls()
            else:
                self.window.close()
        elif action == "polling":
            self.polling = int(name.split("-")[1])
            self.sync_controls()
        elif action == "apply" and self.can_apply:
            self.show_devices()
            self.diagnostics.polling.set_active_id(str(self.polling))
            self.diagnostics.confirm_operation("polling", polling=self.polling)
            self.sync_controls()

    def show_devices(self):
        if self.diagnostics is None:
            view = LinkedCaptureWindow(self)
            self.diagnostics = view
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
        if event.button == 3:
            self.context_menu(event)
            return True
        return False

    def background_pressed(self, _widget, event):
        if event.button == 3:
            self.context_menu(event)
            return True
        if event.button == 1:
            x, y = self.viewport.to_reference(event.x, event.y)
            allocation = self.targets.get_allocation()
            if event.x > allocation.width - 16 and event.y > allocation.height - 16:
                self.window.begin_resize_drag(self.Gdk.WindowEdge.SOUTH_EAST, 1,
                                               int(event.x_root), int(event.y_root), event.time)
            elif y < 65 and x < 935:
                self.window.begin_move_drag(1, int(event.x_root), int(event.y_root), event.time)
            return True
        return False

    def context_menu(self, event=None):
        Gtk = self.Gtk
        menu = Gtk.Menu()
        read = Gtk.MenuItem(label="Read mouse state… (confirmation required)")
        read.set_sensitive(not self.busy)
        read.connect("activate", self.read_state)
        menu.append(read)
        devices = Gtk.MenuItem(label="Device controls & saved captures…    F1")
        devices.connect("activate", lambda _item: self.show_devices())
        menu.append(devices)
        menu.append(Gtk.SeparatorMenuItem())
        mouse = Gtk.CheckMenuItem(label="Use supplied mouse image (alternative artwork)")
        mouse.set_active(self.generated_mouse)
        mouse.set_sensitive(self.skin.mouse is not None)
        mouse.connect("toggled", self.toggle_mouse)
        menu.append(mouse)
        about = Gtk.MenuItem(label="About this UI milestone…")
        about.connect("activate", self.about)
        menu.append(about)
        menu.show_all()
        self.menu = menu  # Keep the popup alive until GTK has dismissed it.
        if event is not None:
            menu.popup_at_pointer(event)
        else:
            menu.popup_at_widget(self.targets, self.Gdk.Gravity.CENTER, self.Gdk.Gravity.CENTER, None)

    def toggle_mouse(self, item):
        self.generated_mouse = item.get_active()
        self.canvas.queue_draw()

    def query_tooltip(self, _widget, x, y, _keyboard, tooltip):
        x, y = self.viewport.to_reference(x, y)
        for name, spec in self.specs.items():
            if spec.rect.contains(x, y):
                tooltip.set_text(self.buttons[name].get_tooltip_text())
                return True
        tooltip.set_text("UI reference preview — values are not live mouse state.\n"
                         "Unsupported settings are disabled. F1 / right-click: device controls.\n"
                         "Ctrl+1–4: pages. Drag the logo area to move; bottom-right corner to resize.")
        return True

    def key_pressed(self, _widget, event):
        name = self.Gdk.keyval_name(event.keyval)
        if name == "F1":
            self.show_devices()
            return True
        if name == "Menu" or (name == "F10" and event.state & self.Gdk.ModifierType.SHIFT_MASK):
            self.context_menu()
            return True
        if event.state & self.Gdk.ModifierType.CONTROL_MASK and name in ("1", "2", "3", "4"):
            self.select_page(PAGES[int(name) - 1])
            return True
        if name == "Escape" and not self.busy:
            self.activate(None, "cancel")
            return True
        return False

    def about(self, _item=None):
        dialog = self.Gtk.MessageDialog(transient_for=self.window, modal=True,
                                         message_type=self.Gtk.MessageType.INFO,
                                         buttons=self.Gtk.ButtonsType.CLOSE,
                                         text="EvoFox Blaze — Linux UI milestone")
        dialog.format_secondary_text(
            "Four native GTK screens reproduce the original 1024 × 737 skin. "
            "The initial assignments, DPI, lighting and 500 Hz highlight are reference examples, not device readings. "
            "Unsupported settings are visible but disabled.\n\n"
            "F1 opens the existing confirmed read / polling / scoped-restore controls. "
            "Nothing contacts the mouse automatically. Frequency is not measured.\n\n"
            "Vendor artwork remains local and is not covered by the project's MIT license.")
        try:
            dialog.run()
        finally:
            dialog.destroy()

    def prevent_close(self, _window, _event):
        if self.busy:
            self.diagnostics.prevent_close_while_busy(None, None)
            self.diagnostics.window.present()
        return self.busy

    def destroy_children(self, _window):
        if self.diagnostics is not None:
            self.diagnostics.window.destroy()
