"""Blaze-styled, window-local six-box shortcut editor. Save is draft-only."""

from .shortcuts import MODIFIER_LABELS, KEY_LABELS, shortcut_device_notice
from .shortcut_boxes import ShortcutBoxes


class ShortcutEditor:
    def __init__(self, owner, index, initial=None):
        from gi.repository import GLib
        self.owner, self.Gtk, self.Gdk, self.GLib = owner, owner.Gtk, owner.Gdk, GLib
        Gtk = self.Gtk
        self.index = index
        self.signature = owner.button_draft.signature
        self.boxes = ShortcutBoxes(initial)
        self.timeout = None
        self.assignable = owner.button_draft.editable(index)
        self.window = Gtk.Window(title=f"EvoFox Blaze — Shortcut for Button {index}")
        self.window.set_name("blaze-shortcut-editor")
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_transient_for(owner.window)
        self.window.set_destroy_with_parent(True)
        self.window.set_modal(True)
        self.window.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        self.window.set_default_size(660, -1)
        self.window.connect("key-press-event", self.key_pressed)
        self.window.connect("key-release-event", self.key_released)
        self.window.connect("focus-out-event", self.focus_lost)
        self.window.connect("unmap", self.unmapped)
        self.window.connect("destroy", self.destroyed)

        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroller.set_propagate_natural_height(True)
        display = self.window.get_display()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        self.scroller.set_max_content_height(max(360, monitor.get_workarea().height - 48))
        self.window.add(self.scroller)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_border_width(24)
        self.scroller.add(content)
        header = Gtk.EventBox()
        header.add_events(self.Gdk.EventMask.BUTTON_PRESS_MASK)
        header.connect("button-press-event", self.drag)
        content.pack_start(header, False, False, 0)
        titles = Gtk.Box(spacing=16)
        header.add(titles)
        titlebox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        titles.pack_start(titlebox, True, True, 0)
        titlebox.pack_start(self.label("EVOFOX  /  BLAZE", "brand"), False, False, 0)
        titlebox.pack_start(self.label("Build a keyboard shortcut", "title"), False, False, 0)
        titlebox.pack_start(self.label(f"Assign to Button {index}", "subtitle"), False, False, 0)
        close = Gtk.Button(label="×")
        close.get_accessible().set_name("Close without saving")
        close.set_valign(Gtk.Align.START)
        close.connect("clicked", lambda _button: self.window.destroy())
        titles.pack_end(close, False, False, 0)

        content.pack_start(self.label(
            "• Click a box or Record. Tap and release one key at a time.\n"
            "• Use 1–6 boxes: modifiers plus one regular key. Delete unused boxes with ×.\n"
            "• Ctrl+Alt+Down: tap Ctrl, then Alt, then Down. Never hold them together during entry.",
            "instructions"), False, False, 0)

        self.key_grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        self.key_grid.set_column_homogeneous(True)
        content.pack_start(self.key_grid, False, False, 0)
        self.key_buttons, self.delete_buttons = [], []
        self.value = self.label("", "key-combination")
        self.value.set_name("shortcut-preview")
        self.value.set_line_wrap_mode(owner.skin.Pango.WrapMode.WORD_CHAR)
        self.value.set_max_width_chars(40)
        self.value.set_xalign(0.5)
        content.pack_start(self.value, False, False, 0)
        self.status = self.label("", "status")
        content.pack_start(self.status, False, False, 0)
        recording = Gtk.Box(spacing=10)
        self.add_button = Gtk.Button(label="+ Add box")
        self.add_button.connect("clicked", self.add_box)
        self.record_button = Gtk.Button(label="Record")
        self.record_button.connect("clicked", self.start_recording)
        self.stop_button = Gtk.Button(label="Stop")
        self.stop_button.connect("clicked", self.stop_recording)
        for button in (self.add_button, self.record_button, self.stop_button):
            recording.pack_start(button, False, False, 0)
        content.pack_start(recording, False, False, 0)
        windows = Gtk.Box(spacing=10)
        self.super_button = Gtk.Button(label="Windows / Super")
        self.super_button.set_tooltip_text(
            "Insert the left Windows key without opening the launcher.")
        self.super_button.connect("clicked", self.insert_super)
        windows.pack_start(self.super_button, False, False, 0)
        windows.pack_start(self.label(
            "Use this if the Windows key opens the launcher.",
            "privacy"), True, True, 0)
        content.pack_start(windows, False, False, 0)
        content.pack_start(self.label(
            "Window-only recording. Focus loss or 20 seconds stops recording; filled boxes stay.", "privacy"), False, False, 0)
        content.pack_start(self.label(shortcut_device_notice(owner.experimental_activation) if self.assignable else
                                      "Not implemented for this button.", "notice"), False, False, 0)
        content.pack_start(self.label(
            "Save keeps a draft. Apply writes to the mouse. Cancel keeps the previous assignment.", "privacy"), False, False, 0)
        actions = Gtk.Box(spacing=10)
        self.save_button = Gtk.Button(label="Save")
        self.save_button.get_style_context().add_class("primary")
        self.save_button.connect("clicked", self.save)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _button: self.window.destroy())
        actions.pack_end(self.save_button, False, False, 0)
        actions.pack_end(cancel, False, False, 0)
        content.pack_start(actions, False, False, 0)
        self.provider = Gtk.CssProvider()
        self.provider.load_from_data(b"""
            #blaze-shortcut-editor { background-color: #0c1118; background-image: linear-gradient(130deg, #18212b, #070a10); border: 1px solid #487083; }
            #blaze-shortcut-editor label { color: #d9e5ec; font-family: Roboto, sans-serif; }
            #blaze-shortcut-editor .brand { color: #08bce5; font-weight: bold; font-size: 12px; }
            #blaze-shortcut-editor .title { color: #ffffff; font-size: 25px; font-weight: bold; }
            #blaze-shortcut-editor .subtitle { color: #93bacb; font-size: 14px; }
            #blaze-shortcut-editor .instructions { font-size: 13px; }
            #blaze-shortcut-editor .privacy { color: #a6bac5; font-size: 12px; }
            #blaze-shortcut-editor .notice { color: #ebc17b; font-size: 12px; }
            #blaze-shortcut-editor .status { color: #8ed7e9; font-size: 13px; }
            #shortcut-preview { background-color: #05090f; border: 1px solid #008bb6; padding: 16px 12px; }
            #blaze-shortcut-editor .key-combination { color: #f3fbff; font-size: 23px; font-weight: bold; }
            #blaze-shortcut-editor button { color: #ecf5fa; background-image: linear-gradient(#34434e, #111b24); border: 1px solid #607987; border-radius: 3px; padding: 8px 12px; box-shadow: none; text-shadow: none; }
            #blaze-shortcut-editor button:hover { border-color: #18c6ef; }
            #blaze-shortcut-editor button:focus { outline: 1px dashed #5cdbff; outline-offset: -4px; }
            #blaze-shortcut-editor button.primary, #blaze-shortcut-editor button.active-box { border-color: #00cfff; background-image: linear-gradient(#006c91, #003650); }
            #blaze-shortcut-editor button.key-box { min-height: 42px; }
            #blaze-shortcut-editor button:disabled { color: #778992; background-image: none; background-color: #111820; border-color: #34424a; }
        """)
        Gtk.StyleContext.add_provider_for_screen(self.window.get_screen(), self.provider,
                                                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.rebuild_boxes()
        self.refresh()

    def label(self, text, style):
        label = self.Gtk.Label(label=text)
        label.set_xalign(0)
        label.set_line_wrap(True)
        label.set_max_width_chars(74)
        label.get_style_context().add_class(style)
        return label

    def rebuild_boxes(self):
        for child in self.key_grid.get_children():
            child.destroy()
        self.key_buttons, self.delete_buttons = [], []
        for index in range(len(self.boxes.values)):
            cell = self.Gtk.Box(orientation=self.Gtk.Orientation.VERTICAL, spacing=4)
            title = self.Gtk.Box(spacing=4)
            title.pack_start(self.label(f"Key {index + 1}", "privacy"), True, True, 0)
            delete = self.Gtk.Button(label="×")
            delete.get_accessible().set_name(f"Delete key box {index + 1}")
            delete.connect("clicked", self.delete_box, index)
            title.pack_end(delete, False, False, 0)
            cell.pack_start(title, False, False, 0)
            button = self.Gtk.Button()
            button.get_style_context().add_class("key-box")
            button.connect("clicked", self.select_box, index)
            cell.pack_start(button, True, True, 0)
            self.key_buttons.append(button)
            self.delete_buttons.append(delete)
            self.key_grid.attach(cell, index % 3, index // 3, 1, 1)
        self.key_grid.show_all()

    def refresh(self):
        boxes = self.boxes
        self.value.set_text(boxes.preview)
        for index, button in enumerate(self.key_buttons):
            key = boxes.values[index]
            button.set_label(MODIFIER_LABELS.get(key, KEY_LABELS.get(key, "Click to record")))
            button.set_sensitive(not self.owner.busy)
            style = button.get_style_context()
            style.add_class("active-box") if boxes.active == index else style.remove_class("active-box")
            button.get_accessible().set_name(f"Key box {index + 1}: {key or 'empty'}")
            self.delete_buttons[index].set_sensitive(not self.owner.busy and len(boxes.values) > 1)
        self.record_button.set_label("Re-record" if all(boxes.values) else "Record")
        self.record_button.set_sensitive(not self.owner.busy and not boxes.recording)
        self.stop_button.set_sensitive(boxes.recording)
        self.add_button.set_sensitive(not self.owner.busy and len(boxes.values) < boxes.limit)
        self.super_button.set_sensitive(not self.owner.busy and boxes.held is None
                                        and (boxes.recording or None in boxes.values))
        self.save_button.set_sensitive(self.assignable and not self.owner.busy
                                       and not boxes.recording and boxes.shortcut is not None)
        self.status.set_text(boxes.error or (f"Key {boxes.active + 1}: press and RELEASE one key. Do not hold a combination."
                                            if boxes.recording else boxes.validation))

    def select_box(self, _button, index):
        if self.owner.busy:
            return
        self.boxes.start(index)
        self.arm()

    def start_recording(self, _button=None):
        if self.owner.busy or self.boxes.recording:
            return
        if all(self.boxes.values):
            self.boxes.reset()
        self.boxes.start()
        self.arm()

    def arm(self):
        self.clear_timeout()
        self.timeout = self.GLib.timeout_add_seconds(20, self.expired)
        self.refresh()
        self.key_buttons[self.boxes.active].grab_focus()

    def add_box(self, _button=None):
        if self.owner.busy or len(self.boxes.values) >= self.boxes.limit:
            return
        self.boxes.add()
        self.clear_timeout()
        self.rebuild_boxes()
        self.refresh()

    def insert_super(self, _button=None):
        if self.owner.busy:
            return
        inserted = self.boxes.insert_super()
        self.clear_timeout()
        if self.boxes.recording:
            self.arm()
        else:
            self.refresh()
            if inserted and self.boxes.shortcut is None:
                self.status.set_text(self.boxes.validation + " Click a box or Record to continue.")

    def delete_box(self, _button, index):
        if self.owner.busy or len(self.boxes.values) == 1:
            return
        self.boxes.delete(index)
        self.clear_timeout()
        self.rebuild_boxes()
        self.refresh()

    def clear_timeout(self):
        if self.timeout is not None:
            self.GLib.source_remove(self.timeout)
            self.timeout = None

    def stop_recording(self, _button=None):
        self.boxes.stop("Recording stopped. Filled boxes are kept; click an empty box to continue.")
        self.clear_timeout()
        self.refresh()

    def expired(self):
        self.timeout = None
        self.boxes.stop("Recording timed out after 20 seconds. Filled boxes are kept.")
        self.refresh()
        return False

    def event_key(self, event):
        name = self.Gdk.keyval_name(event.keyval)
        if name in MODIFIER_LABELS:
            return name
        keymap = self.Gdk.Keymap.get_for_display(self.window.get_display())
        translated = keymap.translate_keyboard_state(event.hardware_keycode, self.Gdk.ModifierType(0), event.group)
        return self.Gdk.keyval_name(self.Gdk.keyval_to_lower(translated[1])) if translated[0] else None

    def key_pressed(self, _widget, event):
        if self.boxes.recording:
            masks = self.Gdk.ModifierType
            held_modifiers = masks.CONTROL_MASK | masks.SHIFT_MASK | masks.MOD1_MASK | masks.SUPER_MASK | masks.MOD4_MASK
            if event.state & held_modifiers and self.boxes.held is None:
                self.boxes.stop("Release all keys. Click a box, then press and release ONE key at a time.")
            else:
                self.boxes.press(self.event_key(event), event.hardware_keycode)
            if not self.boxes.recording:
                self.clear_timeout()
            self.refresh()
            return True
        if self.Gdk.keyval_name(event.keyval) == "Escape":
            self.window.destroy()
            return True
        return False

    def key_released(self, _widget, event):
        if not self.boxes.recording:
            return False
        self.boxes.release(event.hardware_keycode)
        if self.boxes.recording:
            self.arm()
        else:
            self.clear_timeout()
            self.refresh()
        return True

    def focus_lost(self, _widget, _event):
        if self.boxes.recording:
            self.boxes.stop("Recording stopped because this window lost focus. Filled boxes are kept; click a box to continue. "
                            "For the Windows key, use the Windows / Super button instead.")
            self.clear_timeout()
            self.refresh()
        return False

    def unmapped(self, _widget):
        self.focus_lost(None, None)

    def drag(self, _widget, event):
        if event.button == 1 and not self.boxes.recording:
            self.window.begin_move_drag(1, int(event.x_root), int(event.y_root), event.time)
            return True
        return False

    def save(self, _button=None):
        if not self.save_button.get_sensitive() or self.boxes.recording or self.boxes.shortcut is None:
            return
        if self.owner.save_shortcut(self.index, self.boxes.shortcut, self.signature):
            self.window.destroy()
        else:
            self.status.set_text("The assignment state changed. Close this editor and open Shortcut again.")
            self.save_button.set_sensitive(False)

    def destroyed(self, _widget):
        self.clear_timeout()
        self.boxes.stop()
        self.Gtk.StyleContext.remove_provider_for_screen(self.window.get_screen(), self.provider)
        if self.owner.shortcut_editor is self:
            self.owner.shortcut_editor = None
            self.owner.sync_controls()
