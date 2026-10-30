"""App-local, non-dismissible busy shield. No device access or input grabs."""


class OperationOverlay:
    def __init__(self, Gtk, overlay, content):
        from gi.repository import Gdk, GLib
        self.GLib = GLib
        self.timer = None
        self.phase = "validating"
        self.dots = 1
        self.destroyed = False
        self.content = content
        self.shield = Gtk.EventBox()
        self.shield.set_name("blaze-operation-shield")
        self.shield.set_visible_window(True)
        self.shield.set_above_child(True)
        self.shield.set_halign(Gtk.Align.FILL)
        self.shield.set_valign(Gtk.Align.FILL)
        self.shield.set_hexpand(True)
        self.shield.set_vexpand(True)
        self.shield.set_can_focus(True)
        self.shield.set_no_show_all(True)
        self.shield.get_accessible().set_name("Mouse operation in progress")
        self.shield.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                               | Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.SCROLL_MASK
                               | Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.KEY_RELEASE_MASK
                               | Gdk.EventMask.TOUCH_MASK)
        for event in ("button-press-event", "button-release-event", "motion-notify-event", "scroll-event",
                      "key-press-event", "key-release-event", "touch-event"):
            self.shield.connect(event, lambda *_args: True)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        card.set_name("blaze-operation-card")
        card.set_halign(Gtk.Align.CENTER)
        card.set_valign(Gtk.Align.CENTER)
        card.set_size_request(380, -1)
        card.set_border_width(32)
        brand = Gtk.Label(label="EVOFOX  /  BLAZE")
        brand.get_style_context().add_class("brand")
        card.pack_start(brand, False, False, 0)
        self.spinner = Gtk.Spinner()
        self.spinner.set_halign(Gtk.Align.CENTER)
        self.spinner.set_size_request(42, 42)
        card.pack_start(self.spinner, False, False, 0)
        self.status = Gtk.Label()
        self.status.set_single_line_mode(True)
        self.status.set_width_chars(32)
        card.pack_start(self.status, False, False, 0)
        self.title = Gtk.Label(label="Saving to mouse…")
        self.title.get_style_context().add_class("title")
        card.pack_start(self.title, False, False, 0)
        note = Gtk.Label(label="Keep the mouse connected.\nDo not press mouse buttons until this finishes.")
        note.set_justify(Gtk.Justification.CENTER)
        note.set_line_wrap(True)
        card.pack_start(note, False, False, 0)
        self.shield.add(card)
        card.show_all()
        self.provider = Gtk.CssProvider()
        self.provider.load_from_data(b"""
            #blaze-operation-shield { background-color: rgba(0, 0, 0, 0.78); }
            #blaze-operation-card { background-image: linear-gradient(130deg, #182733, #090f17);
                border: 1px solid #158eaf; border-radius: 5px; padding: 16px; }
            #blaze-operation-card label { color: #c6dce7; font-family: Roboto, sans-serif; font-size: 13px; }
            #blaze-operation-card .brand { color: #18c6ec; font-size: 12px; font-weight: bold; }
            #blaze-operation-card .title { color: #ffffff; font-size: 24px; font-weight: bold; }
            #blaze-operation-card spinner { color: #18d4ff; }
        """)
        def style(widget):
            widget.get_style_context().add_provider(self.provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            if isinstance(widget, Gtk.Container):
                for child in widget.get_children():
                    style(child)
        style(self.shield)
        overlay.add_overlay(self.shield)
        overlay.set_overlay_pass_through(self.shield, False)
        self.shield.hide()
        self.shield.connect("hide", lambda *_args: self.stop_animation())
        self.shield.connect("destroy", self.destroy)

    def render_status(self):
        from .operation_progress import PHASES
        self.status.set_text(PHASES[self.phase] + "." * self.dots)

    def set_phase(self, phase):
        from .operation_progress import PHASES
        if not self.destroyed and self.shield.get_visible() and phase in PHASES:
            self.phase, self.dots = phase, 1
            self.render_status()

    def tick(self):
        if self.destroyed or not self.shield.get_visible():
            self.timer = None
            return False
        self.dots = self.dots % 3 + 1
        self.render_status()
        return True

    def stop_animation(self):
        if self.timer is not None:
            self.GLib.source_remove(self.timer)
            self.timer = None
        self.spinner.stop()

    def destroy(self, *_args):
        self.destroyed = True
        self.stop_animation()

    def set_busy(self, busy, *, reading=False):
        if self.destroyed:
            return
        self.content.set_sensitive(not busy)
        self.title.set_text("Reading mouse…" if reading else "Saving to mouse…")
        if busy:
            if not self.shield.get_visible():
                self.phase, self.dots = "validating", 1
                self.render_status()
                self.shield.show()
                self.spinner.start()
                self.timer = self.GLib.timeout_add(450, self.tick)
                self.shield.grab_focus()
        else:
            self.stop_animation()
            self.shield.hide()
