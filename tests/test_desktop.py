"""Offline UI tests. Optional native tests never enumerate or contact a mouse."""

import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import ANY, Mock, patch

from evofox_blaze.ui_layout import HEIGHT, WIDTH, PAGES, Rect, Viewport, controls_for
from tools.prepare_ui_skin import IMAGES, stage


ROOT = Path(__file__).resolve().parents[1]
SKIN = ROOT / ".work/ui-skin"
STATE = ROOT / "docs/device-captures/30fa-1440-0100-state-read-01/state-read.jsonl"


class LayoutTests(unittest.TestCase):
    def test_supplied_mouse_markers_match_the_requested_control_centers(self):
        from evofox_blaze.ui_skin import MOUSE_MARKERS
        markers = {label: (x, y) for label, x, y in MOUSE_MARKERS}
        self.assertEqual(set(markers), set(range(1, 9)))
        self.assertEqual(markers[2], (551, 246))  # Keep the approved placement.
        self.assertEqual(markers[4], (414, 318))
        self.assertEqual(markers[1], (457, 246))  # Mirror 2 about the wheel.
        self.assertEqual(markers[3], (503, 242))
        self.assertEqual(markers[5], (425, 363))
        self.assertEqual(markers[6], (503, 307))
        self.assertEqual(markers[7], (503, 342))
        self.assertEqual(markers[8], (425, 240))

    def test_all_controls_are_named_unique_and_inside_reference_frame(self):
        for page in PAGES:
            controls = controls_for(page)
            self.assertEqual(len({control.name for control in controls}), len(controls))
            for control in controls:
                self.assertTrue(control.label)
                rect = control.rect
                self.assertGreaterEqual(rect.x, 0)
                self.assertGreaterEqual(rect.y, 0)
                self.assertLessEqual(rect.x + rect.width, WIDTH)
                self.assertLessEqual(rect.y + rect.height, HEIGHT)
                self.assertTrue(control.action or control.limitation)

    def test_uniform_scaling_letterboxes_and_round_trips_at_multiple_sizes(self):
        for width, height in ((640, 461), (1366, 768), (1920, 1080), (900, 1200), (2048, 1474)):
            viewport = Viewport.fit(width, height)
            self.assertGreater(viewport.scale, 0)
            self.assertGreaterEqual(viewport.x, 0)
            self.assertGreaterEqual(viewport.y, 0)
            self.assertLessEqual(viewport.x + WIDTH * viewport.scale, width + 0.001)
            self.assertLessEqual(viewport.y + HEIGHT * viewport.scale, height + 0.001)
            for x, y in ((0, 0), (512, 368), (1024, 737)):
                rx, ry = viewport.to_reference(viewport.x + x * viewport.scale,
                                               viewport.y + y * viewport.scale)
                self.assertAlmostEqual(rx, x)
                self.assertAlmostEqual(ry, y)

    def test_hit_rectangles_have_exclusive_right_and_bottom_edges(self):
        rect = Rect(10, 20, 30, 40)
        self.assertTrue(rect.contains(10, 20))
        self.assertTrue(rect.contains(39.9, 59.9))
        self.assertFalse(rect.contains(40, 30))
        self.assertFalse(rect.contains(20, 60))


class SkinPreparationTests(unittest.TestCase):
    def test_only_allowlisted_artwork_is_staged_with_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            source, destination = Path(directory) / "source", Path(directory) / "destination"
            source.mkdir()
            for name in IMAGES:
                (source / name).write_bytes(b"synthetic-artwork-" + name.encode())
            (source / "Gaming Mouse 3.0.exe").write_bytes(b"must not be copied")
            (source / "config.ini").write_text("must not be interpreted")
            stage(source, destination)
            self.assertEqual({p.name for p in destination.iterdir()}, set(IMAGES) | {"provenance.json"})
            provenance = json.loads((destination / "provenance.json").read_text())
            for name in IMAGES:
                self.assertEqual(provenance["files"][name], hashlib.sha256((source / name).read_bytes()).hexdigest())
            with self.assertRaises(ValueError):
                stage(source, destination)

    def test_incomplete_or_symlink_source_does_not_create_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            source, destination = Path(directory) / "source", Path(directory) / "destination"
            source.mkdir()
            with self.assertRaises(ValueError):
                stage(source, destination)
            self.assertFalse(destination.exists())
            for name in IMAGES:
                (source / name).write_bytes(b"synthetic")
            (source / IMAGES[0]).unlink()
            (source / IMAGES[0]).symlink_to(source / IMAGES[1])
            with self.assertRaises(ValueError):
                stage(source, destination)
            self.assertFalse(destination.exists())


class NativeDesktopTests(unittest.TestCase):
    def setUp(self):
        from evofox_blaze.gui import load_gtk
        try:
            self.Gtk = load_gtk()
        except (ImportError, ValueError) as error:
            self.skipTest(f"Optional GTK unavailable: {error}")
        if not self.Gtk.init_check([])[0]:
            self.skipTest("No desktop display")
        if not SKIN.is_dir():
            self.skipTest("Local vendor artwork is intentionally not distributed; stage it for native-skin tests")
        self.control = SimpleNamespace(capture_root=Path("/synthetic/evidence"), run=Mock())
        from evofox_blaze.desktop import BlazeWindow
        with patch("fcntl.ioctl", side_effect=AssertionError("No device ioctl")), \
                patch("evofox_blaze.probe.enumerate_devices", side_effect=AssertionError("No enumeration")):
            self.view = BlazeWindow(self.Gtk, SKIN, control=self.control,
                                    mouse_image=ROOT / "docs/Software_UI/MouseImage.png")

    def tearDown(self):
        if hasattr(self, "view"):
            self.view.button_busy = False
            if self.view.diagnostics is not None:
                self.view.diagnostics.busy = False
            self.view.window.destroy()
            self.control.run.assert_not_called()

    @staticmethod
    def settle(milliseconds=60):
        from gi.repository import GLib
        loop = GLib.MainLoop()
        GLib.timeout_add(milliseconds, lambda: (loop.quit(), False)[1])
        loop.run()

    def test_four_native_pages_disable_unsupported_controls_and_keep_navigation(self):
        with patch("fcntl.ioctl", side_effect=AssertionError("No ioctl")):
            for page in PAGES:
                self.view.select_page(page)
                for name, button in self.view.buttons.items():
                    spec = self.view.specs[name]
                    if spec.action == "button":
                        self.assertIn("Not read", button.get_accessible().get_name())
                    else:
                        self.assertEqual(button.get_accessible().get_name(), spec.label)
                    if not spec.action:
                        self.assertFalse(button.get_sensitive(), name)
                        self.assertTrue(button.get_tooltip_text())
                        self.view.activate(None, name)
                self.assertFalse(self.view.buttons["apply"].get_sensitive())
                self.assertTrue(self.view.buttons["buttons"].get_sensitive())
            self.assertIn("no device read", self.view.window.get_title())

    def test_saving_overlay_covers_controls_and_cannot_be_dismissed_before_completion(self):
        self.view.window.show_all()
        self.settle()
        overlay = self.view.operation_overlay
        self.assertFalse(overlay.shield.get_visible())  # show_all must not reveal an idle overlay.
        self.view.button_draft.assign(4, "middle")
        self.view.sync_controls()
        with patch("evofox_blaze.desktop.threading.Thread") as worker:
            self.view.buttons["apply"].clicked()
            self.settle()
            self.assertTrue(overlay.shield.get_mapped())
            self.assertTrue(overlay.spinner.get_property("active"))
            self.assertEqual(overlay.title.get_text(), "Saving to mouse…")
            self.assertFalse(self.view.targets.is_sensitive())
            self.assertTrue(all(not button.is_sensitive() for button in self.view.buttons.values()))
            allocation = overlay.shield.get_allocation()
            canvas = self.view.canvas.get_allocation()
            self.assertEqual((allocation.x, allocation.y, allocation.width, allocation.height),
                             (0, 0, canvas.width, canvas.height))
            event = self.view.Gdk.Event.new(self.view.Gdk.EventType.BUTTON_PRESS)
            event.button = 1
            for x, y in ((1, 1), (canvas.width - 1, canvas.height - 1), (700, 650)):
                event.x, event.y = x, y
                self.assertTrue(overlay.shield.emit("button-press-event", event))
            for name in ("cancel", "close", "minimize", "apply", "macros", "read-assignments"):
                self.view.buttons[name].clicked()
            for name in ("Escape", "F1", "Return", "Tab"):
                key = SimpleNamespace(keyval=self.view.Gdk.keyval_from_name(name), state=0)
                self.assertTrue(self.view.key_pressed(None, key))
            self.view.window.close()
            self.settle()
            self.assertTrue(self.view.window.get_visible())
            self.assertTrue(overlay.shield.get_visible())
            self.assertEqual(self.view.page, "buttons")
            self.assertEqual(self.view.button_draft.pending, {5: "middle"})
            worker.assert_called_once()
        self.view.buttons_finished({5: "middle"}, None, "Synthetic write failure")
        self.assertFalse(overlay.shield.get_visible())
        self.assertFalse(overlay.spinner.get_property("active"))
        self.assertTrue(self.view.targets.is_sensitive())
        self.assertTrue(self.view.can_apply)
        self.assertIn("Synthetic write failure", self.view.button_message)

    def test_phase_line_cycles_dots_without_resetting_on_refresh_and_cleans_up(self):
        overlay = self.view.operation_overlay
        self.assertIsNone(overlay.timer)
        self.view.button_busy = True
        self.view.sync_controls()
        self.assertEqual(overlay.status.get_text(), "Checking mouse.")
        timer = overlay.timer
        overlay.set_phase("verifying")
        for suffix in ("..", "...", "."):
            self.assertTrue(overlay.tick())
            self.assertEqual(overlay.status.get_text(), "Verifying settings" + suffix)
        self.view.sync_controls()
        self.assertEqual(overlay.timer, timer)
        self.assertEqual(overlay.status.get_text(), "Verifying settings.")
        self.assertTrue(overlay.status.get_single_line_mode())
        self.view.button_busy = False
        self.view.sync_controls()
        self.assertIsNone(overlay.timer)
        text = overlay.status.get_text()
        overlay.set_phase("writing")
        self.assertFalse(overlay.tick())
        self.assertEqual(overlay.status.get_text(), text)
        self.view.button_busy = True
        self.view.sync_controls()
        self.assertEqual(overlay.status.get_text(), "Checking mouse.")
        overlay.shield.destroy()
        self.assertIsNone(overlay.timer)
        self.assertFalse(overlay.tick())
        overlay.set_phase("writing")  # A late callback cannot touch a destroyed label.

    def test_worker_phase_updates_reach_both_windows_only_on_main_loop_and_ignore_late_updates(self):
        import threading
        self.view.show_devices()
        self.view.button_draft.assign(4, "middle")
        with patch("evofox_blaze.desktop.threading.Thread") as worker:
            self.view.apply_buttons()
        callback_target = worker.call_args.kwargs["target"]
        phases = ("reading", "backup", "writing", "verifying", "activating")
        def run(action, *, assignments, confirmed, progress):
            self.assertTrue(callable(progress))
            for phase in phases:
                progress(phase)
            return None
        overlays = self.view.progress_overlays()
        with patch.object(self.control, "run", side_effect=run), \
                patch.object(overlays[0], "set_phase", wraps=overlays[0].set_phase) as update, \
                patch.object(self.view, "buttons_finished", return_value=False):
            thread = threading.Thread(target=callback_target)
            thread.start()
            thread.join()
            update.assert_not_called()  # Worker only schedules; it never touches GTK.
            self.settle()
            self.assertEqual([call.args[0] for call in update.call_args_list[:5]], list(phases))
        for overlay in overlays:
            self.assertEqual(overlay.status.get_text(), "Sending activation sequence.")
            self.assertTrue(overlay.shield.get_visible())
        self.assertTrue(self.view.prevent_close(None, None))
        self.view.buttons_finished({5: "middle"}, None, "Synthetic test completion")
        self.assertTrue(all(overlay.timer is None for overlay in overlays))

    def test_diagnostics_phase_callback_updates_both_overlays_and_finish_stops_timers(self):
        self.view.show_devices()
        diagnostics = self.view.diagnostics
        dialog = Mock()
        dialog.run.return_value = self.Gtk.ResponseType.ACCEPT
        with patch.object(self.Gtk, "MessageDialog", return_value=dialog), \
                patch("evofox_blaze.gui.threading.Thread") as worker:
            diagnostics.confirm_operation("read")
        def run(action, *, confirmed, progress):
            self.assertEqual(action, "read")
            progress("reading")
            raise RuntimeError("Synthetic read failure")
        with patch.object(self.control, "run", side_effect=run), \
                patch.object(diagnostics, "operation_finished", return_value=False) as finished:
            worker.call_args.kwargs["target"]()
            self.settle()
            self.assertEqual(finished.call_args.args[2], "Synthetic read failure")
        for overlay in self.view.progress_overlays():
            self.assertEqual(overlay.status.get_text(), "Reading settings.")
        diagnostics.operation_finished("read", None, "Synthetic read failure")
        self.assertTrue(all(overlay.timer is None for overlay in self.view.progress_overlays()))

    def test_completed_progress_token_cannot_override_new_operation_or_saved_check(self):
        self.view.button_busy = True
        self.view.sync_controls()
        old_progress = self.view.operation_progress.start()
        old_progress("writing")
        self.view.operation_progress.finish(checking=True)
        self.assertEqual(self.view.operation_overlay.status.get_text(), "Checking saved result.")
        self.settle()
        self.assertEqual(self.view.operation_overlay.status.get_text(), "Checking saved result.")
        new_progress = self.view.operation_progress.start()
        old_progress("activating")
        new_progress("verifying")
        self.settle()
        self.assertEqual(self.view.operation_overlay.status.get_text(), "Verifying settings.")
        self.view.operation_progress.finish()
        self.view.button_busy = False
        self.view.sync_controls()
        old_progress("writing")
        new_progress("reading")
        self.settle()
        self.assertFalse(self.view.operation_overlay.shield.get_visible())
        self.assertIsNone(self.view.operation_overlay.timer)

    def test_phase_animation_runs_on_timeout_and_stops_when_hidden(self):
        overlay = self.view.operation_overlay
        overlay.set_busy(True)
        overlay.set_phase("reading")
        self.settle(500)
        self.assertEqual(overlay.status.get_text(), "Reading settings..")
        overlay.shield.hide()
        self.assertIsNone(overlay.timer)
        self.assertFalse(overlay.spinner.get_property("active"))
        text = overlay.status.get_text()
        self.settle(500)
        self.assertEqual(overlay.status.get_text(), text)

    def test_loading_overlay_stays_visible_until_saved_verification_finishes(self):
        self.view.button_draft.assign(4, "middle")
        with patch("evofox_blaze.desktop.threading.Thread"):
            self.view.apply_buttons()
        overlay = self.view.operation_overlay
        def verify(model, path):
            self.assertTrue(overlay.shield.get_visible())
            self.assertFalse(self.view.targets.is_sensitive())
            model.error = "Synthetic invalid verification"
            return False
        with patch("evofox_blaze.desktop.CaptureModel.load", autospec=True, side_effect=verify):
            self.view.buttons_finished({5: "middle"}, SimpleNamespace(capture_directory=Path("/synthetic")), None)
        self.assertFalse(overlay.shield.get_visible())
        self.assertIn("invalid verification", self.view.button_message)
        self.assertEqual(self.view.button_draft.pending, {5: "middle"})

    def test_diagnostics_save_shields_both_windows_and_read_has_its_own_title(self):
        self.view.window.show_all()
        self.view.show_devices()
        dialog = Mock()
        dialog.run.return_value = self.Gtk.ResponseType.ACCEPT
        with patch.object(self.Gtk, "MessageDialog", return_value=dialog), \
                patch("evofox_blaze.gui.threading.Thread") as worker:
            self.view.diagnostics.confirm_operation("polling", polling=1000)
            self.assertTrue(self.view.operation_overlay.shield.get_visible())
            self.assertTrue(self.view.diagnostics.operation_overlay.shield.get_visible())
            self.assertFalse(self.view.diagnostics.operation_overlay.content.is_sensitive())
            self.assertTrue(self.view.diagnostics.prevent_close_while_busy(None, None))
            self.assertTrue(self.view.prevent_close(None, None))
            worker.assert_called_once()
        self.view.diagnostics.operation_finished("polling", None, "Synthetic polling failure")
        self.assertFalse(self.view.operation_overlay.shield.get_visible())
        self.assertFalse(self.view.diagnostics.operation_overlay.shield.get_visible())
        with patch.object(self.Gtk, "MessageDialog", return_value=dialog), patch("evofox_blaze.desktop.threading.Thread"):
            self.view.read_assignments()
            self.assertEqual(self.view.operation_overlay.title.get_text(), "Reading mouse…")
            self.assertEqual(self.view.diagnostics.operation_overlay.title.get_text(), "Reading mouse…")
        self.view.assignments_read_finished(None, "Synthetic read failure")
        self.assertFalse(self.view.operation_overlay.shield.get_visible())
        self.assertFalse(self.view.diagnostics.operation_overlay.shield.get_visible())

    def test_thread_start_failure_and_draft_save_never_leave_a_loading_overlay(self):
        self.windows_draft()
        self.assertFalse(self.view.operation_overlay.shield.get_visible())  # Recorder Save is RAM-only.
        with patch("evofox_blaze.desktop.threading.Thread", side_effect=RuntimeError("Synthetic start failure")):
            self.view.apply_buttons()
        self.assertFalse(self.view.operation_overlay.shield.get_visible())
        self.assertFalse(self.view.operation_overlay.spinner.get_property("active"))
        self.assertTrue(self.view.can_apply)
        self.assertIn("start failure", self.view.button_message)

    def test_only_minimal_necessary_tooltips_remain_and_background_has_none(self):
        for page in PAGES:
            self.view.select_page(page)
            for name, button in self.view.buttons.items():
                spec = self.view.specs[name]
                expected = ("Not implemented." if not spec.action or name == "button-8" else
                            "Read mouse state first (F1)." if spec.action == "polling" else None)
                self.assertEqual(button.get_tooltip_text(), expected, (page, name))
            tooltip = Mock()
            for x, y in ((500, 50), (500, 600), (5, 140)):
                self.assertFalse(self.view.query_tooltip(None, x, y, False, tooltip))
            tooltip.set_text.assert_not_called()
        self.view.select_page("buttons")
        tooltip = Mock()
        spec = self.view.specs["music"]
        x, y, width, height = self.view.viewport.place(spec.rect)
        self.assertTrue(self.view.query_tooltip(None, x + width / 2, y + height / 2, False, tooltip))
        tooltip.set_text.assert_called_once_with("Not implemented.")

    def test_truncated_assignment_tooltip_is_only_the_full_label_and_clears_after_edit(self):
        from evofox_blaze.shortcuts import Shortcut
        self.view.button_draft.assign_shortcut(4, Shortcut("Page_Down", ("Control_R", "Shift_R", "Alt_R", "Super_R")))
        self.view.sync_controls()
        self.assertEqual(self.view.buttons["button-4"].get_tooltip_text(), self.view.button_draft.labels()[3])
        self.view.button_draft.assign_shortcut(4, Shortcut("a"))
        self.view.sync_controls()
        self.assertIsNone(self.view.buttons["button-4"].get_tooltip_text())
        self.view.button_busy = True
        self.view.sync_controls()
        self.assertTrue(all(button.get_tooltip_text() is None for button in self.view.buttons.values()))

    def test_menu_and_recorder_tooltips_do_not_repeat_visible_labels_or_protocol(self):
        menu = self.open_assignment()
        self.assertIsNone(self.menu_item(menu, "Left Click").get_tooltip_text())
        self.assertIsNone(self.menu_item(menu, "Shortcut").get_tooltip_text())
        self.assertEqual(self.menu_item(menu, "Media", "Mute").get_tooltip_text(), "Not implemented.")
        editor = self.open_shortcut()
        self.assertLess(len(editor.super_button.get_tooltip_text()), 70)
        def visit(widget):
            if isinstance(widget, self.Gtk.Button) and widget is not editor.super_button:
                self.assertIsNone(widget.get_tooltip_text())
            if isinstance(widget, self.Gtk.Container):
                for child in widget.get_children():
                    visit(child)
        visit(editor.window)

    def test_page_switches_keep_common_footer_painted_in_the_actual_window(self):
        self.view.window.show_all()
        self.view.window.resize(WIDTH, HEIGHT)
        self.settle(200)
        for page in PAGES:
            self.view.select_page(page)
            self.settle(200)
            x, y, width, height = self.view.viewport.place(Rect(700, 647, 140, 44))
            for window in (self.view.canvas.get_window(), self.view.window.get_window()):
                image = self.view.Gdk.pixbuf_get_from_window(window, x, y, width, height)
                # Check the real mapped window, not just an offscreen Skin export.
                # The shared Apply chrome must not turn into a black invisible hit target.
                pixels = image.get_pixels()
                channels, stride = image.get_n_channels(), image.get_rowstride()
                visible = sum(any(pixels[row * stride + column * channels + channel] > 24 for channel in range(3))
                              for row in range(height) for column in range(width))
                self.assertGreater(visible, width * height // 4, page)

    def test_unsupported_controls_on_every_page_preserve_drafts_and_never_start_workers(self):
        from evofox_blaze.shortcuts import Shortcut
        self.assertTrue(self.view.model.load(STATE))
        self.view.sync_controls()
        self.view.button_draft.assign_shortcut(4, Shortcut("Left", ("Super_L",)))
        self.view.select_page("performance")
        self.view.activate(None, "polling-1000")
        before = (self.view.model.presentation, dict(self.view.button_draft.shortcuts), self.view.polling)
        with patch("fcntl.ioctl", side_effect=AssertionError("No hardware")), \
                patch("evofox_blaze.probe.enumerate_devices", side_effect=AssertionError("No probe")), \
                patch("evofox_blaze.desktop.threading.Thread") as worker:
            for page in PAGES:
                self.view.select_page(page)
                for name, spec in self.view.specs.items():
                    if not spec.action:
                        with self.subTest(page=page, control=name):
                            self.assertFalse(self.view.buttons[name].get_sensitive())
                            self.view.buttons[name].clicked()
                            self.view.activate(None, name)
                            self.assertEqual((self.view.model.presentation,
                                              self.view.button_draft.shortcuts, self.view.polling), before)
                if page in ("macros", "backlight"):
                    self.assertFalse(self.view.can_apply)
                    self.view.buttons["apply"].clicked()
            worker.assert_not_called()

    def test_error_details_control_is_disabled_without_error_and_displays_failures_offline(self):
        self.assertFalse(self.view.buttons["operation-details"].get_sensitive())
        self.view.assignments_read_finished(None, "Synthetic assignment-read failure")
        self.assertTrue(self.view.buttons["operation-details"].get_sensitive())
        with patch("fcntl.ioctl", side_effect=AssertionError("No device")), \
                patch("evofox_blaze.desktop.threading.Thread") as worker:
            self.view.buttons["operation-details"].clicked()
            self.assertIsNotNone(self.view.diagnostics)
            details = self.view.diagnostics.details
            self.assertIn("Synthetic assignment-read failure",
                          details.get_text(details.get_start_iter(), details.get_end_iter(), False))
            worker.assert_not_called()

    def test_error_details_rendering_and_busy_guard_match_the_actual_control(self):
        self.view.buttons_finished({5: "middle"}, None, "Synthetic uncertain commit")
        surface = self.view.skin.cairo.ImageSurface(self.view.skin.cairo.FORMAT_ARGB32, WIDTH, HEIGHT)
        with patch.object(self.view.skin, "draw") as draw:
            self.view.draw(None, self.view.skin.cairo.Context(surface))
        self.assertTrue(draw.call_args.kwargs["has_error"])
        self.view.button_busy = True
        self.view.sync_controls()
        self.assertFalse(self.view.buttons["operation-details"].get_sensitive())
        self.view.activate(None, "operation-details")
        self.assertIsNone(self.view.diagnostics)

    def test_partial_apply_diagnostics_keep_commit_warning_and_clear_on_valid_evidence(self):
        from evofox_blaze.shortcuts import Shortcut
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as temporary:
            root = Path(temporary)
            events = [{"event": "shortcut_config_session"},
                      {"event": "shortcut_write_intent", "frame_hex": "07 18 09 00 38 04 00 07"},
                      {"event": "shortcut_config_failed", "message": "Synthetic write verification interrupted"}]
            (root / "shortcut-configuration.jsonl").write_text("\n".join(json.dumps(event) for event in events))
            chords = {5: Shortcut("Left", ("Super_L",))}
            self.view.buttons_finished({}, SimpleNamespace(capture_directory=root, payload={}), None, chords)
            self.assertEqual(self.view.button_draft.shortcuts, chords)
            self.assertIsNone(self.view.model.presentation)
            self.assertIn("Settings may already have changed", self.view.model.error_details)
            self.view.buttons["operation-details"].clicked()
            details = self.view.diagnostics.details
            self.assertIn("verification interrupted", details.get_text(details.get_start_iter(), details.get_end_iter(), False))
            self.assertEqual(self.view.diagnostics.tabs.get_current_page(), 1)
            self.assertTrue(self.view.model.load(ROOT / "docs/device-captures/30fa-1440-0100-button-read-01/button-read.jsonl"))
            self.view.diagnostics.refresh()
            self.assertEqual(self.view.model.error_details, "")
            self.assertFalse(self.view.buttons["operation-details"].get_sensitive())

    def test_saved_state_enables_only_confirmed_polling_and_cancel_discards_draft(self):
        self.view.select_page("performance")
        self.assertFalse(self.view.buttons["polling-1000"].get_sensitive())
        self.assertTrue(self.view.model.load(STATE))
        self.view.sync_controls()
        self.assertEqual(self.view.captured_polling, 500)
        self.view.activate(None, "polling-1000")
        self.assertEqual(self.view.polling, 1000)
        self.assertTrue(self.view.can_apply)
        self.view.activate(None, "cancel")
        self.assertEqual(self.view.polling, 500)
        self.assertFalse(self.view.can_apply)
        self.assertFalse(self.view.buttons["dpi-0"].get_sensitive())

    def test_cancelled_apply_never_runs_the_backend(self):
        self.view.select_page("performance")
        self.assertTrue(self.view.model.load(STATE))
        self.view.sync_controls()
        self.view.activate(None, "polling-1000")
        dialog = Mock()
        dialog.run.return_value = self.Gtk.ResponseType.CANCEL
        with patch.object(self.Gtk, "MessageDialog", return_value=dialog):
            self.view.activate(None, "apply")
        self.assertIsNotNone(self.view.diagnostics)
        self.control.run.assert_not_called()
        self.assertFalse(self.view.busy)

    def test_busy_operations_prevent_main_close_navigation_and_duplicate_actions(self):
        self.view.show_devices()
        self.view.diagnostics.busy = True
        self.view.sync_controls()
        self.assertTrue(self.view.prevent_close(None, None))
        self.view.select_page("macros")
        self.assertEqual(self.view.page, "buttons")
        self.assertFalse(self.view.buttons["close"].get_sensitive())
        self.view.activate(None, "close")
        self.view.read_state()
        self.control.run.assert_not_called()

    def test_failed_state_load_clears_the_old_polling_candidate(self):
        self.view.select_page("performance")
        self.assertTrue(self.view.model.load(STATE))
        self.view.sync_controls()
        self.assertEqual(self.view.polling, 500)
        self.view.model.presentation = None
        self.view.model.error = "Synthetic error"
        self.view.sync_controls()
        self.assertIsNone(self.view.polling)
        self.assertFalse(self.view.buttons["polling-1000"].get_sensitive())

    def test_native_button_drafts_use_saved_evidence_and_cancel_without_backend(self):
        capture = ROOT / "docs/device-captures/30fa-1440-0100-button-read-01/button-read.jsonl"
        self.assertTrue(self.view.buttons["button-4"].get_sensitive())
        self.assertTrue(self.view.model.load(capture))
        self.view.sync_controls()
        self.assertTrue(self.view.buttons["button-4"].get_sensitive())
        self.assertTrue(self.view.buttons["button-8"].get_sensitive())  # Preview menu only.
        self.assertFalse(self.view.button_draft.editable(8))
        self.assertIn("Stored shortcut", self.view.buttons["button-4"].get_accessible().get_name())
        self.view.button_draft.assign(4, "forward")
        self.view.button_draft.assign(5, "back")
        self.view.sync_controls()
        self.assertTrue(self.view.buttons["apply"].get_sensitive())
        self.assertIn("Forward *", self.view.buttons["button-4"].get_accessible().get_name())
        self.view.activate(None, "cancel")
        self.assertFalse(self.view.can_apply)
        self.assertEqual(self.view.button_draft.pending, {})

    def open_assignment(self, index=4):
        self.view.window.show_all()
        self.settle()
        # Supply a local popup trigger (not sent to the input system). A real
        # user click/keyboard activation supplies this through GTK automatically.
        event = self.view.Gdk.Event.new(self.view.Gdk.EventType.KEY_PRESS)
        event.window = self.view.window.get_window()
        event.keyval = self.view.Gdk.KEY_Menu
        event.time = self.view.Gdk.CURRENT_TIME
        event.set_device(self.view.Gdk.Display.get_default().get_default_seat().get_keyboard())
        with patch.object(self.Gtk, "get_current_event", return_value=event):
            self.view.activate(None, f"button-{index}")
        self.settle()  # Map the popup before activating a nested native menu.
        return self.view.assignment_menu

    @staticmethod
    def menu_item(menu, *labels):
        for index, label in enumerate(labels):
            item = next(child for child in menu.get_children() if child.get_label() == label)
            if index < len(labels) - 1:
                menu = item.get_submenu()
        return item

    def test_direct_assignment_menu_opens_without_read_or_dialog(self):
        with patch.object(self.Gtk, "Dialog", side_effect=AssertionError("No assignment dialog")), \
                patch.object(self.Gtk, "MessageDialog", side_effect=AssertionError("No confirmation")), \
                patch("fcntl.ioctl", side_effect=AssertionError("No hardware")):
            menu = self.open_assignment()
            self.assertEqual([item.get_label() for item in menu.get_children()], [
                "Left Click", "Middle Click", "Right Click", "Backward", "Forward", "DPI loop",
                "Extend", "Media", "Macro", "Shortcut", "Profile Selection",
            ])
            self.menu_item(menu, "Middle Click").activate()
        self.assertFalse(menu.get_visible())
        self.assertEqual(self.view.button_draft.pending, {5: "middle"})
        self.assertTrue(self.view.buttons["apply"].get_sensitive())
        self.assertIsNone(self.view.diagnostics)
        self.assertIsNone(self.view.button_draft.block)

    def test_startup_is_unread_and_default_left_right_selections_can_be_applied(self):
        self.assertEqual(self.view.button_draft.labels()[:7], ("Not read",) * 7)
        self.assertIsNone(self.view.buttons["button-1"].get_tooltip_text())
        with patch("fcntl.ioctl", side_effect=AssertionError("No device")):
            for index, label in ((1, "Left Click"), (2, "Right Click")):
                menu = self.open_assignment(index)
                self.menu_item(menu, label).activate()
        self.assertEqual(self.view.button_draft.pending, {1: "left", 3: "right"})
        self.assertTrue(self.view.can_apply)
        self.assertEqual(self.view.button_draft.labels()[:2], ("Left Click *", "Right Click *"))

    def test_restart_recovers_latest_verified_assignments_without_contacting_mouse(self):
        import shutil
        from evofox_blaze.desktop import BlazeWindow
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as temporary:
            root = Path(temporary)
            directory = root / "20261028T120001.000000Z-shortcuts-0123abcd"
            directory.mkdir()
            shutil.copyfile(ROOT / "docs/device-captures/30fa-1440-0100-shortcut-f13-test-01/shortcut-configuration.jsonl",
                            directory / "shortcut-configuration.jsonl")
            control = SimpleNamespace(capture_root=root, run=Mock())
            with patch("fcntl.ioctl", side_effect=AssertionError("No device")):
                view = BlazeWindow(self.Gtk, SKIN, control=control)
                try:
                    self.assertEqual(view.button_draft.labels()[3], "F13")
                    self.assertEqual(view.button_draft.labels()[:3], ("Left Click", "Right Click", "Middle Click"))
                    self.assertIn("saved evidence (not live)", view.window.get_title())
                    self.assertFalse(view.can_apply)
                    control.run.assert_not_called()
                finally:
                    view.window.destroy()

    def assignment_read_result(self):
        from test_assignment_read import AssignmentReadTests
        mouse = AssignmentReadTests("test_original_active_records_are_decoded_without_a_commit")
        mouse.setUp()
        self.addCleanup(mouse.doCleanups)
        mouse.memory[11] = mouse.memory[12] = 0x2e
        result = mouse.collect_read()
        return SimpleNamespace(capture_directory=mouse.capture, payload=result)

    def test_visible_assignment_read_requires_confirmation_and_loads_shortcut_names(self):
        from gi.repository import GLib
        result = self.assignment_read_result()
        dialog = Mock()
        dialog.run.return_value = self.Gtk.ResponseType.CANCEL
        with patch.object(self.Gtk, "MessageDialog", return_value=dialog), \
                patch("evofox_blaze.desktop.threading.Thread") as worker:
            self.view.buttons["read-assignments"].clicked()
        worker.assert_not_called()
        self.view.button_draft.assign(4, "middle")
        dialog.run.return_value = self.Gtk.ResponseType.ACCEPT
        with patch.object(self.Gtk, "MessageDialog", return_value=dialog), \
                patch("evofox_blaze.desktop.threading.Thread") as worker, \
                patch.object(self.control, "run", return_value=result) as run, patch.object(GLib, "idle_add") as idle:
            self.view.buttons["read-assignments"].clicked()
            self.assertTrue(self.view.busy)
            self.view.read_assignments()
            worker.assert_called_once()
            worker.call_args.kwargs["target"]()
            run.assert_called_once_with("read-assignments", confirmed=True, progress=ANY)
            callback, *arguments = idle.call_args.args
            callback(*arguments)
        self.assertFalse(self.view.busy)
        self.assertEqual(self.view.button_draft.labels()[3:5], ("Ctrl+Super+Right", "Ctrl+Super+Left"))
        self.assertFalse(self.view.button_draft.has_changes)
        self.assertFalse(self.view.can_apply)
        self.assertIsNone(self.view.diagnostics)

    def test_failed_assignment_read_keeps_drafts_and_does_not_retry(self):
        self.view.button_draft.assign(4, "middle")
        with patch("evofox_blaze.desktop.threading.Thread") as worker:
            self.view.assignments_read_finished(None, "Synthetic read failure")
        worker.assert_not_called()
        self.assertEqual(self.view.button_draft.pending, {5: "middle"})
        self.assertTrue(self.view.can_apply)
        self.assertIn("Synthetic read failure", self.view.button_message)

    def test_assignment_read_thread_failure_clears_busy_and_keeps_draft(self):
        self.view.button_draft.assign(4, "middle")
        dialog = Mock()
        dialog.run.return_value = self.Gtk.ResponseType.ACCEPT
        with patch.object(self.Gtk, "MessageDialog", return_value=dialog), \
                patch("evofox_blaze.desktop.threading.Thread", side_effect=RuntimeError("Synthetic thread failure")):
            self.view.read_assignments()
        self.assertFalse(self.view.busy)
        self.assertTrue(self.view.can_apply)
        self.assertIn("Synthetic thread failure", self.view.button_message)

    def test_swapped_left_right_can_be_changed_back_after_a_verified_apply(self):
        from test_button_write import ButtonTransactionTests
        mouse = ButtonTransactionTests("test_fresh_read_backup_one_commit_and_full_readback")
        mouse.setUp()
        self.addCleanup(mouse.doCleanups)
        payload = mouse.change({1: "right", 3: "left"})
        self.view.buttons_finished({1: "right", 3: "left"},
                                   SimpleNamespace(capture_directory=mouse.capture, payload=payload), None)
        self.assertFalse(self.view.can_apply)
        self.assertEqual(self.view.button_draft.labels()[:2], ("Right Click", "Left Click"))
        for index, label in ((1, "Left Click"), (2, "Right Click")):
            menu = self.open_assignment(index)
            self.menu_item(menu, label).activate()
        self.assertEqual(self.view.button_draft.pending, {1: "left", 3: "right"})
        self.assertTrue(self.view.can_apply)

    def test_returning_to_the_original_menu_choice_disables_apply(self):
        self.assertTrue(self.view.model.load(ROOT / "docs/device-captures/30fa-1440-0100-button-remap-01/button-configuration.jsonl"))
        self.view.sync_controls()
        for label in ("Right Click", "DPI loop", "Middle Click"):
            menu = self.open_assignment(4)
            self.menu_item(menu, label).activate()
            self.assertTrue(self.view.buttons["apply"].get_sensitive())
        menu = self.open_assignment(4)
        self.menu_item(menu, "Forward").activate()
        self.assertFalse(self.view.buttons["apply"].get_sensitive())
        self.assertFalse(self.view.can_apply)
        self.assertEqual(self.view.button_draft.pending, {})
        self.assertNotIn("*", self.view.buttons["button-4"].get_accessible().get_name())
        from evofox_blaze.desktop import BUTTON_MESSAGE
        self.assertEqual(self.view.button_message, BUTTON_MESSAGE)
        with patch("evofox_blaze.desktop.threading.Thread") as thread:
            self.view.activate(None, "apply")
        thread.assert_not_called()

    def test_right_click_and_context_menu_shortcuts_do_nothing(self):
        event = SimpleNamespace(button=3)
        with patch.object(self.Gtk, "Menu", side_effect=AssertionError("No context menu")):
            self.assertTrue(self.view.target_pressed(None, event))
            self.assertTrue(self.view.background_pressed(None, event))
            for name, state in (("Menu", 0), ("F10", self.view.Gdk.ModifierType.SHIFT_MASK)):
                event = SimpleNamespace(keyval=self.view.Gdk.keyval_from_name(name), state=state)
                self.assertFalse(self.view.key_pressed(None, event))
        self.assertIsNone(self.view.assignment_menu)
        self.assertIsNone(self.view.diagnostics)
        self.assertFalse(hasattr(self.view, "context_menu"))

    def test_optional_diagnostics_remain_available_through_f1(self):
        event = SimpleNamespace(keyval=self.view.Gdk.keyval_from_name("F1"), state=0)
        self.assertTrue(self.view.key_pressed(None, event))
        self.assertIsNotNone(self.view.diagnostics)
        self.control.run.assert_not_called()

    def test_reverting_after_failure_does_not_claim_a_hardware_restore(self):
        self.assertTrue(self.view.model.load(ROOT / "docs/device-captures/30fa-1440-0100-button-remap-01/button-configuration.jsonl"))
        self.view.sync_controls()
        self.view.button_draft.assign(4, "middle")
        self.view.buttons_finished({5: "middle"}, None, "Synthetic uncertain write")
        menu = self.open_assignment(4)
        self.menu_item(menu, "Forward").activate()
        self.assertFalse(self.view.can_apply)
        self.assertEqual(self.view.button_draft.pending, {})
        self.assertIn("Apply failed", self.view.button_message)
        self.assertIn("Synthetic uncertain write", self.view.button_message)
        self.assertNotIn("restored", self.view.button_message)

    def test_routine_assignment_changes_reverts_and_cancel_keep_one_generic_footer(self):
        from evofox_blaze.desktop import BUTTON_MESSAGE
        self.assertEqual(self.view.button_message, BUTTON_MESSAGE)
        for label in ("Right Click", "DPI loop", "Left Click", "Middle Click"):
            menu = self.open_assignment(1)
            self.menu_item(menu, label).activate()
            self.assertEqual(self.view.button_message, BUTTON_MESSAGE)
        self.view.activate(None, "cancel")
        self.assertEqual(self.view.button_message, BUTTON_MESSAGE)
        self.assertFalse(self.view.can_apply)

    def test_cancel_after_failed_apply_does_not_hide_the_uncertain_device_state(self):
        self.view.button_draft.assign(4, "middle")
        self.view.buttons_finished({5: "middle"}, None, "Synthetic uncertain write")
        message = self.view.button_message
        self.view.activate(None, "cancel")
        self.assertFalse(self.view.can_apply)
        self.assertEqual(self.view.button_message, message)

    def test_supplied_mouse_is_default_and_reference_artwork_is_preserved(self):
        from evofox_blaze.desktop import BlazeWindow
        self.assertTrue(self.view.generated_mouse)
        self.assertIsNotNone(self.view.skin.mouse)
        original = (SKIN / "main_normal.jpg").read_bytes()
        supplied = (ROOT / "docs/Software_UI/MouseImage.png").read_bytes()
        reference = BlazeWindow(self.Gtk, SKIN, control=self.control, generated_mouse=False)
        try:
            self.assertFalse(reference.generated_mouse)
            self.assertIsNotNone(reference.skin.mouse)
            self.assertEqual(reference.skin.directory, SKIN)
        finally:
            reference.window.destroy()
        self.assertEqual((SKIN / "main_normal.jpg").read_bytes(), original)
        self.assertEqual((ROOT / "docs/Software_UI/MouseImage.png").read_bytes(), supplied)

    def test_cascaded_native_submenus_open_on_parent_activation(self):
        menu = self.open_assignment()
        extend = self.menu_item(menu, "Extend")
        submenu = extend.get_submenu()
        self.assertIsNotNone(submenu)
        self.assertIs(submenu.get_attach_widget(), extend)
        self.assertEqual(submenu.get_direction(), self.Gtk.TextDirection.LTR)
        menu.select_item(extend)
        self.settle()
        # activate-item is GTK's parent-menu click/keyboard activation signal;
        # activate is the leaf command signal and deliberately does not cascade.
        extend.emit("activate-item")
        self.settle()
        self.assertTrue(submenu.get_visible())
        self.menu_item(menu, "Extend", "Double Click").activate()
        self.assertFalse(menu.get_visible())
        self.assertFalse(submenu.get_visible())
        self.assertEqual(self.view.button_draft.pending, {5: "double-click"})

    def test_native_menu_parent_selection_opens_the_right_hand_cascade(self):
        menu = self.open_assignment()
        extend = self.menu_item(menu, "Extend")
        menu.select_item(extend)  # Native hover/selection opens after GTK's delay.
        self.settle(400)
        submenu = extend.get_submenu()
        self.assertTrue(submenu.get_visible())
        self.assertTrue(submenu.get_mapped())
        self.assertGreaterEqual(submenu.get_window().get_origin()[1], menu.get_window().get_origin()[1])
        self.assertEqual(self.view.button_draft.pending, {})

    def test_placeholder_leaves_close_the_entire_menu_without_enabling_apply(self):
        paths = [("Extend", "Show desktop"), ("Macro", "No macros found")]
        for group in ("Media", "Profile Selection"):
            menu = self.open_assignment()
            paths.extend((group, item.get_label()) for item in self.menu_item(menu, group).get_submenu().get_children())
        for path in paths:
            menu = self.open_assignment()
            self.menu_item(menu, *path).activate()
            self.assertFalse(menu.get_visible(), path)
            self.assertEqual(self.view.button_draft.pending, {}, path)
            self.assertFalse(self.view.can_apply)
        self.control.run.assert_not_called()

    def test_placeholder_selection_preserves_an_existing_supported_change(self):
        self.view.button_draft.assign(4, "middle")
        menu = self.open_assignment()
        self.menu_item(menu, "Profile Selection", "Office").activate()
        self.assertEqual(self.view.button_draft.pending, {5: "middle"})
        self.assertTrue(self.view.can_apply)
        self.assertFalse(menu.get_visible())

    def test_every_native_menu_leaf_routes_all_rows_to_the_exact_slot_without_device_access(self):
        from evofox_blaze.button_menu import ASSIGNMENT_MENU
        from evofox_blaze.buttons import ACTION_CODES, UI_SLOTS
        def leaves(entries, path=()):
            for entry in entries:
                if entry.children:
                    yield from leaves(entry.children, path + (entry.label,))
                elif entry.action in ACTION_CODES:
                    yield path + (entry.label,), entry.action
        native = list(leaves(ASSIGNMENT_MENU))
        self.assertEqual({action for _, action in native}, set(ACTION_CODES))
        with patch("fcntl.ioctl", side_effect=AssertionError("No device")), \
                patch("evofox_blaze.desktop.threading.Thread") as worker:
            for index in range(1, 9):
                menu = self.open_assignment(index)
                for path, action in native:
                    with self.subTest(row=index, action=action):
                        self.view.button_draft.cancel()
                        self.menu_item(menu, *path).activate()
                        self.assertEqual(self.view.button_draft.pending,
                                         {UI_SLOTS[index - 1]: action} if index < 8 else {})
                self.view.button_draft.cancel()
            worker.assert_not_called()

    def test_polling_apply_runs_the_selected_target_through_actual_fake_transaction(self):
        from gi.repository import GLib
        from test_config_write import ConfigurationTransactionTests, ORIGINAL
        mouse = ConfigurationTransactionTests("test_read_backup_write_readback_preserves_every_unowned_byte")
        mouse.setUp()
        self.addCleanup(mouse.doCleanups)
        self.assertTrue(self.view.model.load(STATE))
        self.view.select_page("performance")
        self.view.activate(None, "polling-1000")
        dialog = Mock()
        dialog.run.return_value = self.Gtk.ResponseType.ACCEPT
        def run(action, *, polling, confirmed, progress):
            self.assertEqual(action, "polling")
            self.assertEqual(polling, 1000)
            self.assertTrue(confirmed)
            payload = mouse.run_change(value=polling)
            return SimpleNamespace(capture_directory=mouse.root / "change", payload=payload)
        with patch("fcntl.ioctl", side_effect=AssertionError("No real mouse")), \
                patch("evofox_blaze.activation.activate_once", side_effect=AssertionError("No activation")), \
                patch.object(self.Gtk, "MessageDialog", return_value=dialog), \
                patch("evofox_blaze.gui.threading.Thread") as worker, \
                patch.object(self.control, "run", side_effect=run) as service, patch.object(GLib, "idle_add") as idle:
            self.view.buttons["apply"].clicked()
            self.assertTrue(self.view.busy)
            worker.assert_called_once()
            worker.call_args.kwargs["target"]()
            callback, *arguments = idle.call_args.args
            callback(*arguments)
            service.assert_called_once()
        self.assertFalse(self.view.busy)
        self.assertFalse(self.view.can_apply)
        self.assertEqual(self.view.captured_polling, 1000)
        self.assertEqual(mouse.memory[:6] + mouse.memory[7:], ORIGINAL[:6] + ORIGINAL[7:])
        self.assertEqual(mouse.commits, 1)
        self.assertFalse(json.loads(self.view.model.presentation.details)["behavior_verified"])

    def test_eighth_row_has_a_preview_menu_but_cannot_program_slot_nine(self):
        message = self.view.button_message
        menu = self.open_assignment(8)
        self.assertEqual(self.view.buttons["button-8"].get_tooltip_text(), "Not implemented.")
        self.assertIn("slot 9", self.view.buttons["button-8"].get_accessible().get_description())
        self.assertEqual(self.menu_item(menu, "Forward").get_tooltip_text(), "Not implemented.")
        self.menu_item(menu, "Forward").activate()
        self.assertFalse(menu.get_visible())
        self.assertEqual(self.view.button_draft.pending, {})
        self.assertFalse(self.view.can_apply)
        self.assertEqual(self.view.button_message, message)

    def open_shortcut(self, index=4):
        menu = self.open_assignment(index)
        self.menu_item(menu, "Shortcut").activate()
        self.settle()
        self.assertIsNotNone(self.view.shortcut_editor)
        return self.view.shortcut_editor

    def shortcut_key(self, editor, key, pressed=True, state=0):
        # Symbolic GTK-local event dispatch, never sent to the desktop/input
        # server. Resolve against the active keymap rather than hard-code X11.
        Gdk = self.view.Gdk
        keyval = Gdk.keyval_from_name(key)
        keymap = Gdk.Keymap.get_for_display(editor.window.get_display())
        found, entries = keymap.get_entries_for_keyval(keyval)
        self.assertTrue(found, key)
        entry = entries[0]
        event = Gdk.Event.new(Gdk.EventType.KEY_PRESS if pressed else Gdk.EventType.KEY_RELEASE)
        event.window = editor.window.get_window()
        event.send_event = True
        event.time = Gdk.CURRENT_TIME
        event.keyval = keyval
        event.hardware_keycode = entry.keycode
        event.group = entry.group
        event.state = state
        event.set_device(Gdk.Display.get_default().get_default_seat().get_keyboard())
        self.Gtk.main_do_event(event)

    def record_shortcut(self, editor, keys=("Control_L", "Super_L", "Left")):
        while len(editor.boxes.values) > len(keys):
            editor.delete_box(None, len(editor.boxes.values) - 1)
        while len(editor.boxes.values) < len(keys):
            editor.add_box()
        editor.boxes.reset()
        editor.refresh()
        editor.record_button.clicked()
        for key in keys:
            self.shortcut_key(editor, key)
            self.assertFalse(editor.save_button.get_sensitive())
            self.shortcut_key(editor, key, pressed=False)

    def test_shortcut_menu_opens_custom_styled_modal_without_recording_or_device_access(self):
        with patch.object(self.Gtk, "Dialog", side_effect=AssertionError("No stock dialog")), \
                patch.object(self.Gtk, "MessageDialog", side_effect=AssertionError("No stock popup")), \
                patch("fcntl.ioctl", side_effect=AssertionError("No device")):
            editor = self.open_shortcut()
        self.assertEqual(editor.window.get_name(), "blaze-shortcut-editor")
        self.assertFalse(editor.window.get_decorated())
        self.assertTrue(editor.window.get_modal())
        self.assertIs(editor.window.get_transient_for(), self.view.window)
        self.assertFalse(editor.boxes.recording)
        self.assertIsNone(editor.timeout)
        self.assertFalse(editor.save_button.get_sensitive())
        self.assertFalse(self.view.button_draft.has_changes)
        self.assertIsNone(self.view.button_draft.block)

    def test_shortcut_record_save_stages_one_assignment_but_never_writes(self):
        from evofox_blaze.shortcuts import Shortcut
        from evofox_blaze.desktop import BUTTON_MESSAGE
        editor = self.open_shortcut()
        with patch("fcntl.ioctl", side_effect=AssertionError("No device")), \
                patch("evofox_blaze.probe.enumerate_devices", side_effect=AssertionError("No enumeration")), \
                patch("evofox_blaze.desktop.threading.Thread") as worker:
            self.record_shortcut(editor)
            self.assertEqual(editor.boxes.shortcut, Shortcut("Left", ("Control_L", "Super_L")))
            self.assertIsNone(editor.timeout)
            self.assertTrue(editor.save_button.get_sensitive())
            editor.save_button.clicked()
            worker.assert_not_called()
        self.assertIsNone(self.view.shortcut_editor)
        self.assertEqual(self.view.button_draft.labels()[3], "Ctrl+Super+Left *")
        self.assertEqual(self.view.button_draft.pending, {})
        self.assertIsNone(self.view.button_draft.block)
        self.assertEqual(self.view.button_message, BUTTON_MESSAGE)
        self.assertIn("Ctrl+Super+Left", self.view.buttons["button-4"].get_accessible().get_name())
        self.assertIsNone(self.view.buttons["button-4"].get_tooltip_text())
        self.assertTrue(self.view.buttons["apply"].get_sensitive())
        self.assertIsNone(self.view.buttons["apply"].get_tooltip_text())

    def test_idle_editor_does_not_record_keys(self):
        editor = self.open_shortcut()
        self.shortcut_key(editor, "a")
        self.shortcut_key(editor, "a", pressed=False)
        self.assertIsNone(editor.boxes.shortcut)
        self.assertIsNone(editor.boxes.held)
        self.assertFalse(editor.save_button.get_sensitive())

    def test_enter_tab_escape_and_f1_record_without_activating_controls_or_parent_actions(self):
        editor = self.open_shortcut()
        for key in ("Return", "Tab", "Escape", "F1"):
            self.record_shortcut(editor, (key,))
            self.assertEqual(editor.boxes.shortcut.key, key)
            self.assertTrue(editor.window.get_visible())
            self.assertFalse(self.view.button_draft.has_changes)
            self.assertIsNone(self.view.diagnostics)
            self.assertEqual(self.view.page, "buttons")

    def test_separate_shift_key_and_base_letter_build_the_correct_shortcut(self):
        from evofox_blaze.shortcuts import Shortcut
        editor = self.open_shortcut()
        self.record_shortcut(editor, ("Control_L", "Shift_L", "a"))
        self.assertEqual(editor.boxes.shortcut, Shortcut("a", ("Control_L", "Shift_L")))

    def test_modifier_held_before_record_is_refused_instead_of_recording_a_partial_chord(self):
        editor = self.open_shortcut()
        editor.start_recording()
        self.shortcut_key(editor, "k", state=self.view.Gdk.ModifierType.CONTROL_MASK)
        self.assertFalse(editor.boxes.recording)
        self.assertIsNone(editor.boxes.shortcut)
        self.assertIn("Release all keys", editor.status.get_text())
        self.assertFalse(editor.save_button.get_sensitive())
        self.assertIsNone(editor.timeout)

    def test_rerecord_and_cancel_preserve_the_preexisting_local_assignment(self):
        from evofox_blaze.shortcuts import Shortcut
        original = Shortcut("Left", ("Control_L", "Super_L"))
        self.view.button_draft.assign_shortcut(4, original)
        editor = self.open_shortcut()
        self.assertEqual(editor.value.get_text(), original.label)
        self.assertEqual(editor.record_button.get_label(), "Re-record")
        self.record_shortcut(editor, ("Control_L", "k"))
        self.assertEqual(self.view.button_draft.shortcut(4), original)
        editor.window.destroy()  # Close/Cancel must not stage the new recording.
        self.assertEqual(self.view.button_draft.shortcut(4), original)
        self.assertIsNone(editor.boxes.held)
        editor = self.open_shortcut()
        self.record_shortcut(editor, ("Control_L", "k"))
        editor.save_button.clicked()
        self.assertEqual(self.view.button_draft.shortcut(4), Shortcut("k", ("Control_L",)))

    def test_focus_loss_timeout_and_stop_discard_partial_recordings(self):
        editor = self.open_shortcut()
        editor.start_recording()
        self.shortcut_key(editor, "Control_L")
        editor.focus_lost(None, None)
        self.assertIn("lost focus", editor.status.get_text())
        self.assertIsNone(editor.boxes.held)
        self.assertIsNone(editor.timeout)
        self.assertFalse(editor.save_button.get_sensitive())
        editor.start_recording()
        editor.clear_timeout()  # Deliver the scheduled callback locally, not after 20 s.
        editor.expired()
        self.assertIn("timed out", editor.status.get_text())
        self.assertFalse(editor.save_button.get_sensitive())
        editor.start_recording()
        editor.stop_button.clicked()
        self.assertIn("stopped", editor.status.get_text())
        self.assertIsNone(editor.timeout)
        editor.start_recording()
        editor.window.hide()
        self.assertFalse(editor.boxes.recording)
        self.assertIsNone(editor.timeout)

    def test_reserved_shortcut_is_built_from_separate_taps_without_a_chord_or_worker(self):
        from evofox_blaze.shortcuts import Shortcut
        editor = self.open_shortcut()
        with patch("fcntl.ioctl", side_effect=AssertionError("No device")), \
                patch("evofox_blaze.desktop.threading.Thread") as worker:
            self.record_shortcut(editor, ("Control_L", "Alt_L", "Down"))
            self.assertEqual(editor.boxes.shortcut, Shortcut("Down", ("Control_L", "Alt_L")))
            self.assertEqual(editor.value.get_text(), "Ctrl+Alt+Down")
            self.assertFalse(editor.boxes.recording)
            self.assertIsNone(editor.timeout)
            editor.focus_lost(None, None)
            self.assertTrue(editor.save_button.get_sensitive())
            editor.save_button.clicked()
            worker.assert_not_called()
        self.assertEqual(self.view.button_draft.shortcuts, {5: Shortcut("Down", ("Control_L", "Alt_L"))})
        self.assertTrue(self.view.can_apply)

    def test_focus_loss_keeps_filled_boxes_and_requires_explicit_rearming(self):
        from evofox_blaze.shortcuts import Shortcut
        editor = self.open_shortcut()
        editor.start_recording()
        self.shortcut_key(editor, "Control_L")
        self.shortcut_key(editor, "Control_L", pressed=False)
        self.shortcut_key(editor, "Alt_L")
        self.shortcut_key(editor, "Alt_L", pressed=False)
        editor.focus_lost(None, None)
        self.assertFalse(editor.boxes.recording)
        self.assertIsNone(editor.timeout)
        self.assertEqual(editor.value.get_text(), "Ctrl+Alt+…")
        self.assertEqual(editor.boxes.values, ["Control_L", "Alt_L", None])
        self.assertFalse(editor.save_button.get_sensitive())
        self.assertIsNone(editor.boxes.held)
        self.shortcut_key(editor, "Down")  # Idle input must not finish it.
        self.assertIsNone(editor.boxes.shortcut)
        editor.key_buttons[2].clicked()
        self.shortcut_key(editor, "Down")
        self.shortcut_key(editor, "Down", pressed=False)
        self.assertEqual(editor.boxes.shortcut, Shortcut("Down", ("Control_L", "Alt_L")))
        editor.save_button.clicked()
        self.assertEqual(self.view.button_draft.shortcuts[5].label, "Ctrl+Alt+Down")

    def test_completed_box_chord_survives_focus_loss_and_ignores_idle_keys(self):
        from evofox_blaze.shortcuts import Shortcut
        editor = self.open_shortcut()
        self.record_shortcut(editor, ("Control_L", "Alt_L", "Down"))
        editor.focus_lost(None, None)
        self.assertTrue(editor.save_button.get_sensitive())
        self.assertEqual(editor.boxes.shortcut, Shortcut("Down", ("Control_L", "Alt_L")))
        self.assertFalse(editor.boxes.recording)
        self.assertIsNone(editor.boxes.held)
        self.assertIsNone(editor.timeout)
        self.shortcut_key(editor, "a")
        self.assertEqual(editor.boxes.shortcut.key, "Down")
        editor.window.hide()
        self.assertEqual(editor.boxes.shortcut.key, "Down")

    def test_key_boxes_preserve_modifier_sides_and_cancel_preserves_prior_draft(self):
        from evofox_blaze.shortcuts import Shortcut
        original = Shortcut("Left", ("Control_L",))
        self.view.button_draft.assign_shortcut(4, original)
        editor = self.open_shortcut()
        self.assertEqual(editor.boxes.values, ["Control_L", "Left"])
        self.record_shortcut(editor, ("Control_R", "Alt_R", "Down"))
        self.assertEqual(editor.boxes.shortcut, Shortcut("Down", ("Control_R", "Alt_R")))
        editor.window.destroy()
        self.assertEqual(self.view.button_draft.shortcut(4), original)

    def test_windows_button_builds_ctrl_super_left_without_pressing_super_or_writing(self):
        from evofox_blaze.shortcuts import Shortcut
        editor = self.open_shortcut()
        with patch("fcntl.ioctl", side_effect=AssertionError("No device")), \
                patch("evofox_blaze.probe.enumerate_devices", side_effect=AssertionError("No probe")), \
                patch("evofox_blaze.desktop.threading.Thread") as worker:
            editor.start_recording()
            self.shortcut_key(editor, "Control_L")
            self.shortcut_key(editor, "Control_L", pressed=False)
            editor.super_button.clicked()
            self.assertEqual(editor.boxes.values, ["Control_L", "Super_L", None])
            self.assertEqual(editor.boxes.active, 2)
            self.shortcut_key(editor, "Left")
            self.shortcut_key(editor, "Left", pressed=False)
            self.assertEqual(editor.value.get_text(), "Ctrl+Super+Left")
            self.assertIsNone(editor.timeout)
            self.assertTrue(editor.save_button.get_sensitive())
            editor.save_button.clicked()
            worker.assert_not_called()
        self.assertEqual(self.view.button_draft.shortcut(4), Shortcut("Left", ("Control_L", "Super_L")))

    def test_windows_button_after_launcher_focus_loss_keeps_boxes_without_rearming(self):
        editor = self.open_shortcut()
        editor.start_recording()
        self.shortcut_key(editor, "Control_L")
        self.shortcut_key(editor, "Control_L", pressed=False)
        self.shortcut_key(editor, "Super_L")  # Simulate only the observed press.
        self.assertFalse(editor.super_button.get_sensitive())  # Release keys before manual entry.
        editor.focus_lost(None, None)
        self.assertEqual(editor.boxes.values, ["Control_L", None, None])
        self.assertIn("Windows / Super", editor.status.get_text())
        self.assertTrue(editor.super_button.get_sensitive())
        editor.super_button.clicked()
        self.assertEqual(editor.boxes.values, ["Control_L", "Super_L", None])
        self.assertFalse(editor.boxes.recording)
        self.assertIsNone(editor.boxes.held)
        self.assertIsNone(editor.timeout)
        self.shortcut_key(editor, "Super_L", pressed=False)
        self.shortcut_key(editor, "Left")  # Still idle until the user arms the next box.
        self.assertIsNone(editor.boxes.shortcut)
        editor.key_buttons[2].clicked()
        self.shortcut_key(editor, "Left")
        self.shortcut_key(editor, "Left", pressed=False)
        self.assertEqual(editor.value.get_text(), "Ctrl+Super+Left")
        self.assertTrue(editor.save_button.get_sensitive())

    def test_idle_windows_choice_does_not_start_recording_and_cancel_preserves_previous_draft(self):
        from evofox_blaze.shortcuts import Shortcut
        editor = self.open_shortcut()
        editor.super_button.clicked()
        self.assertEqual(editor.boxes.values, ["Super_L", None, None])
        self.assertFalse(editor.boxes.recording)
        self.assertIsNone(editor.timeout)
        self.assertFalse(self.view.button_draft.has_changes)
        editor.window.destroy()
        original = Shortcut("Left", ("Control_L",))
        self.view.button_draft.assign_shortcut(4, original)
        editor = self.open_shortcut()
        self.assertFalse(editor.super_button.get_sensitive())  # Full chord: no implicit replacement.
        editor.key_buttons[0].clicked()
        self.assertTrue(editor.super_button.get_sensitive())
        editor.super_button.clicked()
        self.assertEqual(editor.boxes.shortcut, Shortcut("Left", ("Super_L",)))
        editor.window.destroy()
        self.assertEqual(self.view.button_draft.shortcut(4), original)

    def test_windows_choice_keeps_duplicate_busy_and_unsupported_target_guards(self):
        editor = self.open_shortcut()
        self.view.button_busy = True
        editor.refresh()
        self.assertFalse(editor.super_button.get_sensitive())
        editor.insert_super()
        self.assertEqual(editor.boxes.values, [None] * 3)
        self.view.button_busy = False
        editor.refresh()
        editor.super_button.clicked()
        editor.super_button.clicked()
        editor.key_buttons[2].clicked()
        self.shortcut_key(editor, "Left")
        self.shortcut_key(editor, "Left", pressed=False)
        self.assertFalse(editor.save_button.get_sensitive())
        self.assertIn("different", editor.status.get_text())
        editor.window.destroy()
        editor = self.open_shortcut(8)
        editor.super_button.clicked()
        editor.start_recording()
        for key in ("Control_L", "Left"):
            self.shortcut_key(editor, key)
            self.shortcut_key(editor, key, pressed=False)
        self.assertIsNotNone(editor.boxes.shortcut)
        self.assertFalse(editor.save_button.get_sensitive())
        editor.save()
        self.assertFalse(self.view.button_draft.has_changes)

    def test_add_delete_six_box_limit_and_no_dropdown_or_checkbox_widgets(self):
        editor = self.open_shortcut()
        for _ in range(4):
            editor.add_button.clicked()
        self.assertEqual(len(editor.key_buttons), 6)
        self.assertFalse(editor.add_button.get_sensitive())
        self.assertFalse(editor.save_button.get_sensitive())
        editor.delete_buttons[5].clicked()
        self.assertEqual(len(editor.key_buttons), 5)
        self.assertTrue(editor.add_button.get_sensitive())
        def visit(widget):
            self.assertNotIsInstance(widget, (self.Gtk.ComboBox, self.Gtk.CheckButton, self.Gtk.Expander))
            if isinstance(widget, self.Gtk.Container):
                for child in widget.get_children():
                    visit(child)
        visit(editor.window)

    def test_unused_duplicate_and_multiple_regular_key_boxes_cannot_be_saved(self):
        editor = self.open_shortcut()
        self.record_shortcut(editor, ("Control_L", "Alt_L", "Down"))
        self.assertTrue(editor.save_button.get_sensitive())
        editor.add_button.clicked()
        self.assertFalse(editor.save_button.get_sensitive())
        editor.delete_buttons[3].clicked()
        self.assertTrue(editor.save_button.get_sensitive())
        editor.key_buttons[1].clicked()
        self.shortcut_key(editor, "Control_L")
        self.shortcut_key(editor, "Control_L", pressed=False)
        self.assertFalse(editor.save_button.get_sensitive())
        self.assertIn("different", editor.status.get_text())
        editor.key_buttons[1].clicked()
        self.shortcut_key(editor, "a")
        self.shortcut_key(editor, "a", pressed=False)
        self.assertFalse(editor.save_button.get_sensitive())
        self.assertIn("one regular key", editor.status.get_text())

    def test_holding_keys_together_is_refused_instead_of_building_a_partial_chord(self):
        editor = self.open_shortcut()
        editor.start_recording()
        self.shortcut_key(editor, "Control_L")
        self.shortcut_key(editor, "Alt_L")
        self.assertFalse(editor.boxes.recording)
        self.assertIsNone(editor.timeout)
        self.assertEqual(editor.boxes.values, [None] * 3)
        self.assertFalse(editor.save_button.get_sensitive())
        self.assertIn("one key at a time", editor.status.get_text())

    def test_six_boxes_scroll_instead_of_hiding_save_on_short_screens(self):
        editor = self.open_shortcut()
        editor.scroller.set_max_content_height(440)
        for _ in range(3):
            editor.add_button.clicked()
        self.settle(200)
        self.assertLessEqual(editor.window.get_size()[1], 460)
        self.assertEqual(editor.scroller.get_policy()[1], self.Gtk.PolicyType.AUTOMATIC)
        self.record_shortcut(editor, ("Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L", "Down"))
        self.assertTrue(editor.save_button.get_sensitive())

    def test_unsupported_target_opens_recorder_preview_but_cannot_save(self):
        editor = self.open_shortcut(8)
        self.assertFalse(editor.assignable)
        self.record_shortcut(editor)
        self.assertFalse(editor.save_button.get_sensitive())
        editor.save()
        self.assertFalse(self.view.button_draft.has_changes)

    def test_changed_evidence_while_editor_is_open_refuses_to_save_stale_target(self):
        editor = self.open_shortcut()
        self.record_shortcut(editor)
        changed = ROOT / "docs/device-captures/30fa-1440-0100-button-remap-01/button-configuration.jsonl"
        self.assertTrue(self.view.model.load(changed))
        self.view.sync_controls()
        editor.save_button.clicked()
        self.assertIs(self.view.shortcut_editor, editor)
        self.assertFalse(editor.save_button.get_sensitive())
        self.assertIn("state changed", editor.status.get_text())
        self.assertFalse(self.view.button_draft.has_changes)

    def test_mixed_drafts_enable_combined_apply_and_native_replacement_removes_the_shortcut(self):
        from evofox_blaze.shortcuts import Shortcut
        self.assertTrue(self.view.model.load(ROOT / "docs/device-captures/30fa-1440-0100-button-remap-01/button-configuration.jsonl"))
        self.view.sync_controls()
        self.view.button_draft.assign(5, "middle")
        self.view.button_draft.assign_shortcut(4, Shortcut("k", ("Control_L",)))
        self.view.sync_controls()
        self.assertTrue(self.view.can_apply)
        menu = self.open_assignment(4)
        self.menu_item(menu, "Forward").activate()
        self.assertTrue(self.view.can_apply)
        self.assertEqual(self.view.button_draft.pending, {4: "middle"})
        self.view.activate(None, "cancel")
        self.assertFalse(self.view.button_draft.has_changes)

    def shortcut_result(self, shortcuts, assignments=None, no_change=False, restore=False):
        # Use the actual scoped writer/journal validator with the existing fake
        # mouse, never enumerate or open a real device.
        from test_shortcut_write import ShortcutTransactionTests
        mouse = ShortcutTransactionTests("test_fresh_backup_minimal_writes_and_complete_readback")
        mouse.setUp()
        self.addCleanup(mouse.doCleanups)
        result = mouse.change(shortcuts, assignments)
        if no_change or restore:
            backup = mouse.capture / "shortcut-backup.json"
            mouse.capture = mouse.root / "second"
            result = mouse.change(restore_from=backup) if restore else mouse.change(shortcuts, assignments)
        return SimpleNamespace(capture_directory=mouse.capture, payload=result)

    def test_record_save_apply_runs_one_combined_shortcut_transaction_and_verifies_baseline(self):
        from gi.repository import GLib
        from evofox_blaze.shortcuts import Shortcut
        chords = {5: Shortcut("Down", ("Control_L", "Shift_L"))}
        result = self.shortcut_result(chords, {4: "middle"})
        self.view.button_draft.assign(5, "middle")
        editor = self.open_shortcut()
        self.record_shortcut(editor, ("Control_L", "Shift_L", "Down"))
        editor.save_button.clicked()
        self.assertTrue(self.view.can_apply)
        with patch("evofox_blaze.desktop.threading.Thread") as worker, \
                patch.object(self.Gtk, "MessageDialog", side_effect=AssertionError("No extra modal")), \
                patch.object(self.control, "run", return_value=result) as run, patch.object(GLib, "idle_add") as idle:
            self.view.activate(None, "apply")
            self.assertTrue(self.view.busy)
            self.view.activate(None, "apply")
            worker.assert_called_once()
            worker.call_args.kwargs["target"]()
            run.assert_called_once_with("shortcuts", assignments={4: "middle"}, shortcuts=chords, confirmed=True, progress=ANY)
            callback, *arguments = idle.call_args.args
            callback(*arguments)
        self.assertFalse(self.view.busy)
        self.assertFalse(self.view.can_apply)
        self.assertEqual(self.view.button_draft.labels()[3:5], ("Ctrl+Shift+Down", "Middle Click"))
        self.assertEqual(self.view.last_shortcut_backup, result.capture_directory / "shortcut-backup.json")
        self.assertEqual(self.view.button_draft.baseline_shortcuts, chords)
        self.view.button_draft.assign_shortcut(4, Shortcut("F13"))
        self.assertTrue(self.view.can_apply)
        self.view.button_draft.assign_shortcut(4, chords[5])
        self.assertFalse(self.view.can_apply)

    def windows_draft(self):
        """Explicit Windows choice plus focused local taps; no physical Super."""
        editor = self.open_shortcut()
        while len(editor.boxes.values) < 3:
            editor.add_box()
        while len(editor.boxes.values) > 3:
            editor.delete_box(None, len(editor.boxes.values) - 1)
        editor.boxes.reset()
        editor.refresh()
        editor.start_recording()
        self.shortcut_key(editor, "Control_L")
        self.shortcut_key(editor, "Control_L", pressed=False)
        editor.super_button.clicked()
        self.shortcut_key(editor, "Left")
        self.shortcut_key(editor, "Left", pressed=False)
        editor.save_button.clicked()

    def arm_experimental_activation(self, root=None):
        from evofox_blaze.desktop import BlazeWindow
        self.view.window.destroy()
        self.control.experimental_activation = True
        if root is not None:
            self.control.capture_root = root
        with patch("fcntl.ioctl", side_effect=AssertionError("Startup is offline")), \
                patch("evofox_blaze.probe.enumerate_devices", side_effect=AssertionError("No enumeration")):
            self.view = BlazeWindow(self.Gtk, SKIN, control=self.control)

    def test_experimental_apply_uses_fake_locked_transaction_and_recovers_journal_offline(self):
        from test_apply_activation import FakeChange
        from gi.repository import GLib
        from evofox_blaze.desktop import BlazeWindow
        from evofox_blaze.activation import APPLY_BANNER
        from evofox_blaze.shortcuts import Shortcut
        for kind in ("buttons", "shortcuts"):
            with self.subTest(kind=kind):
                case = FakeChange(self, kind)
                self.arm_experimental_activation(case.mouse.root)
                case.mouse.capture = case.mouse.root / f"20261102T140000.000000Z-{kind}-0123abcd"
                if kind == "buttons":
                    self.view.button_draft.assign(4, "forward")
                    self.view.button_draft.assign(5, "back")
                else:
                    self.view.button_draft.assign(5, "middle")
                    self.windows_draft()
                self.view.sync_controls()
                self.assertIsNone(self.view.buttons["apply"].get_tooltip_text())
                surface = self.view.skin.cairo.ImageSurface(self.view.skin.cairo.FORMAT_ARGB32, WIDTH, HEIGHT)
                with patch.object(self.view.skin, "draw") as draw:
                    self.view.draw(None, self.view.skin.cairo.Context(surface))
                self.assertEqual(draw.call_args.args[8], APPLY_BANNER)
                def run(action, *, assignments, confirmed, progress, shortcuts=None):
                    self.assertEqual(action, kind)
                    self.assertTrue(confirmed)
                    result = case.run(assignments=assignments, shortcuts=shortcuts)
                    return SimpleNamespace(capture_directory=case.mouse.capture, payload=result)
                with patch("fcntl.ioctl", side_effect=AssertionError("No real device")), \
                        patch.object(self.control, "run", side_effect=run) as service, \
                        patch("evofox_blaze.desktop.threading.Thread") as worker, patch.object(GLib, "idle_add") as idle:
                    self.view.buttons["apply"].clicked()
                    worker.call_args.kwargs["target"]()
                    callback, *arguments = idle.call_args.args
                    callback(*arguments)
                    service.assert_called_once()
                self.assertFalse(self.view.busy)
                self.assertFalse(self.view.can_apply)
                self.assertIn("activation sequence sent", self.view.button_message)
                self.assertIn("unverified", self.view.button_message)
                self.assertNotIn("Unplug for", self.view.button_message)
                self.assertEqual(len(case.activation_frames), 2)
                self.assertFalse(case.inspect()["activation_behavior_verified"])
                with patch("fcntl.ioctl", side_effect=AssertionError("Recovery is offline")), \
                        patch("evofox_blaze.activation._activate_on_handle", side_effect=AssertionError("No activation on startup")):
                    restarted = BlazeWindow(self.Gtk, SKIN, control=self.control)
                    try:
                        self.assertFalse(restarted.can_apply)
                        self.assertIn("not live", restarted.window.get_title())
                        if kind == "shortcuts":
                            self.assertEqual(restarted.button_draft.baseline_shortcuts,
                                             {5: Shortcut("Left", ("Control_L", "Super_L"))})
                    finally:
                        restarted.window.destroy()

    def test_experimental_activation_failure_keeps_draft_and_incomplete_history_blocks_fallback(self):
        from test_apply_activation import FakeChange
        from gi.repository import GLib
        from evofox_blaze.desktop import BlazeWindow
        for kind in ("buttons", "shortcuts"):
            with self.subTest(kind=kind):
                case = FakeChange(self, kind)
                import shutil
                older = case.mouse.root / "20261102T130000.000000Z-shortcuts-abcdef01"
                older.mkdir()
                shutil.copyfile(ROOT / "docs/device-captures/30fa-1440-0100-shortcut-f13-test-01/shortcut-configuration.jsonl",
                                older / "shortcut-configuration.jsonl")
                self.arm_experimental_activation(case.mouse.root)
                if kind == "buttons":
                    self.view.button_draft.assign(4, "forward")
                    self.view.button_draft.assign(5, "back")
                else:
                    self.windows_draft()
                desired = (dict(self.view.button_draft.pending), dict(self.view.button_draft.shortcuts))
                case.mouse.capture = case.mouse.root / f"20261102T140000.000000Z-{kind}-0123abcd"
                case.fail_ordinal, case.activation_response = 1, OSError("Synthetic activation failure")
                def run(action, *, assignments, confirmed, progress, shortcuts=None):
                    result = case.run(assignments=assignments, shortcuts=shortcuts)
                    return SimpleNamespace(capture_directory=case.mouse.capture, payload=result)
                self.view.sync_controls()
                with patch.object(self.control, "run", side_effect=run) as service, \
                        patch("evofox_blaze.desktop.threading.Thread") as worker, patch.object(GLib, "idle_add") as idle:
                    self.view.buttons["apply"].clicked()
                    worker.call_args.kwargs["target"]()
                    callback, *arguments = idle.call_args.args
                    callback(*arguments)
                    service.assert_called_once()
                self.assertFalse(self.view.busy)
                self.assertTrue(self.view.can_apply)
                self.assertEqual((self.view.button_draft.pending, self.view.button_draft.shortcuts), desired)
                self.assertIn("activation failure", self.view.button_message)
                self.assertNotIn("sequence sent", self.view.button_message)
                self.assertEqual(len(case.activation_frames), 1)
                self.assertTrue((case.mouse.capture / case.backup).exists())
                restarted = BlazeWindow(self.Gtk, SKIN, control=self.control)
                try:
                    self.assertIn("incomplete", restarted.model.error)
                    self.assertEqual(restarted.button_draft.labels()[:7], ("Not read",) * 7)
                finally:
                    restarted.window.destroy()

    def test_experimental_apply_refuses_old_verification_that_did_not_include_activation(self):
        from evofox_blaze.shortcuts import Shortcut
        result = self.shortcut_result({5: Shortcut("F13")})
        self.arm_experimental_activation()
        requested = {5: Shortcut("F13")}
        self.view.buttons_finished({}, result, None, requested)
        self.assertTrue(self.view.can_apply)
        self.assertEqual(self.view.button_draft.shortcuts, requested)
        self.assertIn("does not match", self.view.button_message)

    def test_experimental_polling_apply_confirms_scope_and_verifies_candidate_journal(self):
        from test_apply_activation import FakeChange
        from gi.repository import GLib
        case = FakeChange(self, "polling")
        self.arm_experimental_activation()
        self.assertTrue(self.view.model.load(STATE))
        self.view.select_page("performance")
        self.view.activate(None, "polling-1000")
        dialog = Mock()
        dialog.run.return_value = self.Gtk.ResponseType.ACCEPT
        def run(action, *, polling, confirmed, progress):
            self.assertEqual((action, polling, confirmed), ("polling", 1000, True))
            return SimpleNamespace(capture_directory=case.mouse.capture, payload=case.run())
        with patch.object(self.Gtk, "MessageDialog", return_value=dialog), \
                patch.object(self.control, "run", side_effect=run) as service, \
                patch("evofox_blaze.gui.threading.Thread") as worker, patch.object(GLib, "idle_add") as idle:
            self.view.buttons["apply"].clicked()
            self.assertIn("ALL stored settings", dialog.format_secondary_text.call_args.args[0])
            worker.call_args.kwargs["target"]()
            callback, *arguments = idle.call_args.args
            callback(*arguments)
            service.assert_called_once()
        self.assertFalse(self.view.busy)
        self.assertFalse(self.view.can_apply)
        self.assertEqual(self.view.captured_polling, 1000)
        self.assertIn("activation sequence sent", self.view.diagnostics.message.get_text())
        self.assertEqual(len(case.activation_frames), 2)

    def test_experimental_unchanged_apply_does_not_claim_to_have_activated(self):
        from test_apply_activation import FakeChange
        from gi.repository import GLib
        case = FakeChange(self, "buttons")
        case.run(False)
        case.mouse.capture = case.mouse.root / "unchanged"
        self.arm_experimental_activation()
        self.view.button_draft.assign(4, "forward")
        self.view.button_draft.assign(5, "back")
        self.view.sync_controls()
        def run(action, *, assignments, confirmed, progress):
            return SimpleNamespace(capture_directory=case.mouse.capture, payload=case.run(assignments=assignments))
        with patch.object(self.control, "run", side_effect=run), \
                patch("evofox_blaze.desktop.threading.Thread") as worker, patch.object(GLib, "idle_add") as idle:
            self.view.buttons["apply"].clicked()
            worker.call_args.kwargs["target"]()
            callback, *arguments = idle.call_args.args
            callback(*arguments)
        self.assertFalse(self.view.can_apply)
        self.assertIn("no write or activation sent", self.view.button_message)
        self.assertEqual(case.activation_frames, [])

    def apply_to_fake_shortcut_mouse(self, mouse):
        """Run actual GUI worker routing + scoped transaction on fake memory only."""
        from gi.repository import GLib
        def run(action, *, assignments, shortcuts, confirmed, progress):
            self.assertEqual(action, "shortcuts")
            self.assertTrue(confirmed)
            payload = mouse.change(shortcuts, assignments)
            return SimpleNamespace(capture_directory=mouse.capture, payload=payload)
        with patch("fcntl.ioctl", side_effect=AssertionError("No real device")), \
                patch("evofox_blaze.probe.enumerate_devices", side_effect=AssertionError("No enumeration")), \
                patch("evofox_blaze.activation.activate_once", side_effect=AssertionError("No automatic activation")), \
                patch("evofox_blaze.desktop.threading.Thread") as worker, \
                patch.object(self.control, "run", side_effect=run) as service, patch.object(GLib, "idle_add") as idle:
            self.view.activate(None, "apply")
            self.assertTrue(self.view.busy)
            self.assertTrue(self.view.operation_overlay.shield.get_visible())
            self.view.activate(None, "apply")
            worker.assert_called_once()
            worker.call_args.kwargs["target"]()
            service.assert_called_once()
            callback, *arguments = idle.call_args.args
            callback(*arguments)
        self.assertFalse(self.view.busy)
        self.assertFalse(self.view.operation_overlay.shield.get_visible())
        self.assertFalse(self.view.operation_overlay.spinner.get_property("active"))

    def test_windows_fallback_save_apply_verifies_real_fake_device_journal_and_restart(self):
        from test_shortcut_write import ShortcutTransactionTests
        from evofox_blaze.desktop import BlazeWindow
        from evofox_blaze.shortcuts import Shortcut
        from evofox_blaze.shortcut_config_capture import decode_shortcut_config_capture
        mouse = ShortcutTransactionTests("test_fresh_backup_minimal_writes_and_complete_readback")
        mouse.setUp()
        self.addCleanup(mouse.doCleanups)
        mouse.capture = mouse.root / "20261102T120000.000000Z-shortcuts-0123abcd"
        self.view.button_draft.assign(5, "middle")
        self.windows_draft()
        self.assertEqual(mouse.features, [])  # Save alone did not reach even the fake transport.
        self.apply_to_fake_shortcut_mouse(mouse)
        expected = {5: Shortcut("Left", ("Control_L", "Super_L"))}
        self.assertEqual(self.view.button_draft.baseline_shortcuts, expected)
        self.assertFalse(self.view.can_apply)
        self.assertEqual(self.view.button_draft.labels()[3:5], ("Ctrl+Super+Left", "Middle Click"))
        self.assertEqual(bytes(mouse.memory[address] for address in range(0x438, 0x440)),
                         bytes.fromhex("01 00 84 e0 84 e3 84 50"))
        self.assertEqual(bytes(mouse.memory[address] for address in range(0x400, 0x438)),
                         bytes(mouse.original_memory[address] for address in range(0x400, 0x438)))
        inspected = decode_shortcut_config_capture(mouse.capture / "shortcut-configuration.jsonl")
        self.assertEqual(inspected["verified_shortcuts"],
                         [{"slot": 5, "key": "Left", "modifiers": ["Control_L", "Super_L"]}])
        self.assertFalse(inspected["behavior_verified"])
        with patch("fcntl.ioctl", side_effect=AssertionError("No device")), \
                patch("evofox_blaze.probe.enumerate_devices", side_effect=AssertionError("No probe")):
            restarted = BlazeWindow(self.Gtk, SKIN, control=SimpleNamespace(capture_root=mouse.root, run=Mock()))
            try:
                self.assertEqual(restarted.button_draft.baseline_shortcuts, expected)
                self.assertIn("not live", restarted.window.get_title())
                self.assertFalse(restarted.can_apply)
            finally:
                restarted.window.destroy()

    def test_windows_fallback_uncertain_fake_commit_retains_draft_and_never_retries(self):
        from test_shortcut_write import ShortcutTransactionTests
        from evofox_blaze.shortcuts import Shortcut
        mouse = ShortcutTransactionTests("test_fresh_backup_minimal_writes_and_complete_readback")
        mouse.setUp()
        self.addCleanup(mouse.doCleanups)
        mouse.stall_commit = 1
        self.windows_draft()
        self.apply_to_fake_shortcut_mouse(mouse)
        self.assertEqual(mouse.commits, 1)
        self.assertEqual(self.view.button_draft.shortcuts, {5: Shortcut("Left", ("Control_L", "Super_L"))})
        self.assertTrue(self.view.can_apply)
        self.assertIn("Synthetic uncertain commit", self.view.button_message)
        self.assertIsNone(self.view.model.presentation)
        self.assertTrue((mouse.capture / "shortcut-backup.json").is_file())

    def test_windows_last_box_after_timeout_can_enable_save_without_background_capture(self):
        from evofox_blaze.shortcuts import Shortcut
        editor = self.open_shortcut()
        editor.key_buttons[0].clicked()
        self.shortcut_key(editor, "Control_L")
        self.shortcut_key(editor, "Control_L", pressed=False)
        editor.key_buttons[2].clicked()
        self.shortcut_key(editor, "Left")
        self.shortcut_key(editor, "Left", pressed=False)
        editor.clear_timeout()
        editor.expired()
        self.assertEqual(editor.boxes.values, ["Control_L", None, "Left"])
        editor.super_button.clicked()
        self.assertEqual(editor.boxes.shortcut, Shortcut("Left", ("Control_L", "Super_L")))
        self.assertTrue(editor.save_button.get_sensitive())
        self.assertFalse(editor.boxes.recording)
        self.assertIsNone(editor.timeout)

    def test_shortcut_failure_keeps_both_draft_types_and_never_retries(self):
        from evofox_blaze.shortcuts import Shortcut
        chords = {5: Shortcut("k", ("Control_L",))}
        self.view.button_draft.assign(5, "middle")
        self.view.button_draft.assign_shortcut(4, chords[5])
        self.view.button_busy = True
        with patch("evofox_blaze.desktop.threading.Thread") as worker:
            self.view.buttons_finished({4: "middle"}, None, "Synthetic uncertain commit", chords)
        worker.assert_not_called()
        self.assertTrue(self.view.can_apply)
        self.assertEqual(self.view.button_draft.pending, {4: "middle"})
        self.assertEqual(self.view.button_draft.shortcuts, chords)
        self.assertIsNone(self.view.button_draft.block)
        self.assertIn("Synthetic uncertain commit", self.view.button_message)
        self.view.activate(None, "cancel")
        self.assertFalse(self.view.can_apply)
        self.assertIn("Synthetic uncertain commit", self.view.button_message)

    def test_wrong_chord_native_subset_or_restore_journal_cannot_clear_shortcut_drafts(self):
        from evofox_blaze.shortcuts import Shortcut
        result = self.shortcut_result({5: Shortcut("F13")})
        chords = {5: Shortcut("Down", ("Control_L", "Shift_L"))}
        for assignments, requested in (({}, chords), ({4: "middle"}, {5: Shortcut("F13")})):
            self.view.buttons_finished(assignments, result, None, requested)
            self.assertTrue(self.view.can_apply)
            self.assertIn("does not match", self.view.button_message)
            self.assertEqual(self.view.button_draft.shortcuts, requested)
        restored = self.shortcut_result({5: Shortcut("F13")}, restore=True)
        self.view.buttons_finished({}, restored, None, {5: Shortcut("F13")})
        self.assertIn("does not match", self.view.button_message)
        self.assertTrue(self.view.can_apply)

    def test_shortcut_no_change_uses_verified_labels_without_inventing_a_backup(self):
        from evofox_blaze.shortcuts import Shortcut
        chords = {5: Shortcut("F13")}
        result = self.shortcut_result(chords, no_change=True)
        self.view.buttons_finished({}, result, None, chords)
        self.assertFalse(self.view.can_apply)
        self.assertEqual(self.view.button_draft.labels()[3], "F13")
        self.assertIsNone(self.view.last_shortcut_backup)
        self.assertIn("no write needed", self.view.button_message)

    def test_shortcut_worker_start_failure_retains_the_chord(self):
        from evofox_blaze.shortcuts import Shortcut
        chord = Shortcut("Down", ("Control_L", "Shift_L"))
        self.view.button_draft.assign_shortcut(4, chord)
        with patch("evofox_blaze.desktop.threading.Thread", side_effect=RuntimeError("Synthetic thread failure")):
            self.view.apply_buttons()
        self.assertFalse(self.view.busy)
        self.assertEqual(self.view.button_draft.shortcuts, {5: chord})
        self.assertTrue(self.view.can_apply)
        self.assertIn("Synthetic thread failure", self.view.button_message)

    def test_main_cancel_discards_shortcut_draft_without_closing_or_writing(self):
        from evofox_blaze.shortcuts import Shortcut
        self.view.button_draft.assign_shortcut(4, Shortcut("k"))
        self.view.sync_controls()
        self.view.window.show_all()
        self.view.activate(None, "cancel")
        self.assertFalse(self.view.button_draft.has_changes)
        self.assertTrue(self.view.window.get_visible())
        self.assertEqual(self.view.button_draft.labels()[:7], ("Not read",) * 7)

    def test_open_editor_guards_parent_actions_duplicate_editors_and_busy_saves(self):
        from evofox_blaze.shortcuts import Shortcut
        self.view.button_draft.assign(5, "middle")
        editor = self.open_shortcut()
        self.assertFalse(self.view.can_apply)
        self.view.select_page("performance")
        self.view.activate(None, "cancel")
        self.view.show_devices()
        self.view.choose_shortcut(5)
        self.assertIs(self.view.shortcut_editor, editor)
        self.assertEqual(editor.index, 4)
        self.assertEqual(self.view.page, "buttons")
        self.assertIsNone(self.view.diagnostics)
        self.assertEqual(self.view.button_draft.pending, {4: "middle"})
        event = SimpleNamespace(keyval=self.view.Gdk.KEY_F1, state=0)
        self.assertTrue(self.view.key_pressed(None, event))
        self.assertIsNone(self.view.diagnostics)
        self.view.button_busy = True
        editor.start_recording()
        self.assertFalse(editor.boxes.recording)
        self.assertFalse(self.view.save_shortcut(4, Shortcut("k"), editor.signature))

    def test_closing_main_window_cleans_editor_recording_and_timer(self):
        editor = self.open_shortcut()
        editor.start_recording()
        self.shortcut_key(editor, "Control_L")
        self.assertIsNotNone(editor.timeout)
        self.view.window.destroy()
        self.assertIsNone(self.view.shortcut_editor)
        self.assertIsNone(editor.timeout)
        self.assertFalse(editor.boxes.recording)
        self.assertIsNone(editor.boxes.held)

    def test_apply_uses_one_confirmed_worker_without_diagnostics_or_extra_dialog(self):
        from gi.repository import GLib
        self.assertTrue(self.view.model.load(ROOT / "docs/device-captures/30fa-1440-0100-button-read-01/button-read.jsonl"))
        self.view.sync_controls()
        self.view.button_draft.assign(4, "forward")
        self.view.button_draft.assign(5, "back")
        self.view.sync_controls()
        directory = ROOT / "docs/device-captures/30fa-1440-0100-button-remap-01"
        result = SimpleNamespace(capture_directory=directory, payload={"backup_file": "button-backup.json"})
        with patch("evofox_blaze.desktop.threading.Thread") as worker, \
                patch.object(self.Gtk, "MessageDialog", side_effect=AssertionError("No confirmation dialog")), \
                patch.object(self.control, "run", return_value=result) as run, \
                patch.object(GLib, "idle_add") as idle:
            self.view.activate(None, "apply")
            self.assertTrue(self.view.busy)
            self.assertIsNone(self.view.diagnostics)
            self.assertFalse(self.view.buttons["apply"].get_sensitive())
            self.assertTrue(self.view.prevent_close(None, None))
            self.view.select_page("performance")
            self.assertEqual(self.view.page, "buttons")
            self.view.activate(None, "apply")
            self.view.show_devices()
            self.assertIsNone(self.view.diagnostics)
            worker.assert_called_once()
            worker.return_value.start.assert_called_once()
            worker.call_args.kwargs["target"]()
            run.assert_called_once_with("buttons", assignments={5: "forward", 4: "back"}, confirmed=True, progress=ANY)
            callback, *arguments = idle.call_args.args
            callback(*arguments)
        self.assertFalse(self.view.busy)
        self.assertFalse(self.view.can_apply)
        self.assertFalse(self.view.buttons["apply"].get_sensitive())
        self.assertEqual(self.view.button_draft.pending, {})
        self.assertEqual(self.view.button_draft.labels()[3:5], ("Forward", "Backward"))
        self.assertIn("saved and read back", self.view.button_message)
        self.assertEqual(self.view.last_button_backup, directory / "button-backup.json")

    def test_failed_apply_keeps_the_selection_but_never_retries_or_claims_success(self):
        self.view.button_draft.assign(4, "middle")
        self.view.button_busy = True
        self.view.buttons_finished({5: "middle"}, None, "Synthetic failure; inspect the journal")
        self.assertFalse(self.view.busy)
        self.assertTrue(self.view.can_apply)
        self.assertEqual(self.view.button_draft.pending, {5: "middle"})
        self.assertIsNone(self.view.button_draft.block)
        self.assertIn("Apply failed", self.view.button_message)
        self.assertIn("No automatic retry", self.view.button_message)

    def test_worker_start_failure_does_not_leave_the_window_busy(self):
        self.view.button_draft.assign(5, "middle")
        self.view.sync_controls()
        with patch("evofox_blaze.desktop.threading.Thread") as thread:
            thread.return_value.start.side_effect = RuntimeError("Synthetic thread failure")
            self.view.activate(None, "apply")
        self.assertFalse(self.view.busy)
        self.assertTrue(self.view.can_apply)
        self.assertEqual(self.view.button_draft.pending, {4: "middle"})
        self.assertIn("Could not start", self.view.button_message)

    def test_mismatched_saved_result_does_not_clear_the_requested_selection(self):
        directory = ROOT / "docs/device-captures/30fa-1440-0100-button-remap-01"
        result = SimpleNamespace(capture_directory=directory, payload={})
        self.view.button_draft.assign(4, "middle")
        self.view.buttons_finished({5: "middle"}, result, None)
        self.assertEqual(self.view.button_draft.pending, {5: "middle"})
        self.assertIn("does not match", self.view.button_message)
        self.assertTrue(self.view.can_apply)

    def test_missing_saved_verification_cannot_report_success(self):
        with tempfile.TemporaryDirectory() as directory:
            result = SimpleNamespace(capture_directory=Path(directory), payload={"outcome": "written-and-read-back"})
            self.view.button_draft.assign(5, "middle")
            self.view.buttons_finished({4: "middle"}, result, None)
        self.assertIn("Apply failed", self.view.button_message)
        self.assertTrue(self.view.can_apply)
        self.assertEqual(self.view.button_draft.pending, {4: "middle"})

    def test_verified_no_change_also_disables_apply(self):
        # Construct a no-change journal from the saved verification read, not
        # from any device operation. Keep exact request order and result bytes.
        directory = ROOT / "docs/device-captures/30fa-1440-0100-button-remap-01"
        self.assertTrue(self.view.model.load(ROOT / "docs/device-captures/30fa-1440-0100-button-read-01/button-read.jsonl"))
        self.view.sync_controls()
        source = [json.loads(line) for line in (directory / "button-configuration.jsonl").read_text().splitlines()]
        events = source[:2] + [dict(event, phase="before") for event in source if event.get("phase") == "verify"]
        complete = dict(source[-1], outcome="no-change", before_hex=source[-1]["after_hex"])
        complete.pop("backup_file", None)
        events.append(complete)
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            (target / "button-configuration.jsonl").write_text("\n".join(json.dumps(event) for event in events))
            self.view.button_draft.assign(4, "forward")
            self.view.button_draft.assign(5, "back")
            self.view.buttons_finished({5: "forward", 4: "back"}, SimpleNamespace(capture_directory=target, payload={}), None)
        self.assertFalse(self.view.can_apply)
        self.assertEqual(self.view.button_draft.pending, {})
        self.assertIn("no write needed", self.view.button_message)

    def test_direct_apply_disables_open_diagnostics_and_restores_controls_on_failure(self):
        self.view.show_devices()
        self.view.button_draft.assign(4, "middle")
        self.view.sync_controls()
        with patch("evofox_blaze.desktop.threading.Thread"):
            self.view.activate(None, "apply")
        self.assertTrue(self.view.diagnostics.busy)
        self.assertFalse(self.view.diagnostics.read_buttons.get_sensitive())
        self.assertFalse(self.view.diagnostics.restore_buttons.get_sensitive())
        self.view.buttons_finished({5: "middle"}, None, "Synthetic failure")
        self.assertFalse(self.view.diagnostics.busy)
        self.assertTrue(self.view.diagnostics.read_buttons.get_sensitive())
        self.assertTrue(self.view.can_apply)

    def test_button_drafts_clear_on_failed_capture_and_do_not_enable_polling(self):
        capture = ROOT / "docs/device-captures/30fa-1440-0100-button-read-01/button-read.jsonl"
        self.assertTrue(self.view.model.load(capture))
        self.view.sync_controls()
        self.view.button_draft.assign(4, "middle")
        self.view.select_page("performance")
        self.assertFalse(self.view.buttons["polling-1000"].get_sensitive())
        self.assertFalse(self.view.can_apply)
        self.view.model.presentation = None
        self.view.sync_controls()
        self.assertEqual(self.view.button_draft.pending, {})
        self.view.select_page("buttons")
        self.assertTrue(self.view.buttons["button-4"].get_sensitive())
        self.assertFalse(self.view.can_apply)

    def test_window_can_shrink_after_growing_and_targets_follow_scaled_artwork(self):
        self.view.window.show_all()
        self.view.window.resize(1280, 921)
        self.settle()
        self.view.window.resize(800, 576)
        self.settle()
        width, height = self.view.window.get_size()
        self.assertLessEqual(width, 820)
        self.assertLessEqual(height, 600)
        for name in ("buttons", "performance", "close", "cancel"):
            expected = self.view.viewport.place(self.view.specs[name].rect)
            actual = self.view.buttons[name].get_allocation()
            self.assertEqual((actual.x, actual.y, actual.width, actual.height), expected)

    def background_event(self, kind, x, y):
        # Dispatch only inside this GTK process, never to the desktop/input
        # system. No pointer polling, input listener or hardware event injection.
        event = self.view.Gdk.Event.new(kind)
        event.window = self.view.canvas.get_window()
        event.send_event = True
        event.time = self.view.Gdk.CURRENT_TIME
        event.x, event.y = x, y
        event.x_root, event.y_root = x + 100, y + 100
        event.set_device(self.view.Gdk.Display.get_default().get_default_seat().get_pointer())
        if kind == self.view.Gdk.EventType.BUTTON_PRESS:
            event.button = 1
        return event

    def test_real_background_event_window_routes_header_and_logo_drags(self):
        self.view.window.show_all()
        self.settle()
        self.assertFalse(self.view.targets.get_has_window())
        self.assertTrue(self.view.canvas.get_has_window())
        self.assertTrue(self.view.canvas.get_events() & self.view.Gdk.EventMask.BUTTON_PRESS_MASK)
        with patch.object(self.view.window, "begin_move_drag") as move, \
                patch.object(self.view.window, "begin_resize_drag") as resize:
            for rx, ry in ((300, 30), (510, 95)):
                viewport = self.view.viewport
                x, y = viewport.x + rx * viewport.scale, viewport.y + ry * viewport.scale
                event = self.background_event(self.view.Gdk.EventType.BUTTON_PRESS, x, y)
                self.assertIs(self.Gtk.get_event_widget(event), self.view.canvas)
                self.Gtk.main_do_event(event)
                move.assert_called_with(1, int(x + 100), int(y + 100), event.time)
            self.assertEqual(move.call_count, 2)
            resize.assert_not_called()

    def test_all_resize_edges_and_corners_receive_actual_canvas_events(self):
        self.view.window.show_all()
        self.settle()
        allocation = self.view.canvas.get_allocation()
        w, h = allocation.width, allocation.height
        with patch.object(self.view.window, "begin_move_drag") as move, \
                patch.object(self.view.window, "begin_resize_drag") as resize:
            for x, y, edge in ((1, 1, "NORTH_WEST"), (w / 2, 1, "NORTH"),
                               (w - 1, 1, "NORTH_EAST"), (1, h / 2, "WEST"),
                               (w - 1, h / 2, "EAST"), (1, h - 1, "SOUTH_WEST"),
                               (w / 2, h - 1, "SOUTH"), (w - 1, h - 1, "SOUTH_EAST")):
                event = self.background_event(self.view.Gdk.EventType.BUTTON_PRESS, x, y)
                self.Gtk.main_do_event(event)
                resize.assert_called_with(getattr(self.view.Gdk.WindowEdge, edge), 1,
                                          int(x + 100), int(y + 100), event.time)
            self.assertEqual(resize.call_count, 8)
            move.assert_not_called()

    def test_drag_gestures_preserve_scaled_controls_letterboxing_and_busy_guard(self):
        self.view.window.show_all()
        self.settle()
        for width, height in ((640, 461), (1280, 921), (1100, 500), (700, 800)):
            self.view.window.resize(width, height)
            self.settle()
            viewport = self.view.viewport
            x, y = viewport.x + 500 * viewport.scale, viewport.y + 30 * viewport.scale
            self.assertEqual(self.view.background_gesture(x, y), "move")
            for spec in self.view.specs.values():
                r = spec.rect
                x, y = viewport.x + (r.x + r.width / 2) * viewport.scale, \
                    viewport.y + (r.y + r.height / 2) * viewport.scale
                self.assertIsNone(self.view.background_gesture(x, y), spec.name)
            self.assertEqual(self.view.background_gesture(1, 1), "north_west")
        self.view.button_busy = True
        with patch.object(self.view.window, "begin_move_drag") as move, \
                patch.object(self.view.window, "begin_resize_drag") as resize:
            self.Gtk.main_do_event(self.background_event(self.view.Gdk.EventType.BUTTON_PRESS, 1, 1))
            self.assertIsNone(self.view.background_gesture(500, 30))
            move.assert_not_called()
            resize.assert_not_called()

    def test_canvas_motion_sets_resize_cursor_and_clears_it_over_plain_background(self):
        self.view.window.show_all()
        self.settle()
        event = self.background_event(self.view.Gdk.EventType.MOTION_NOTIFY, 1, 1)
        self.Gtk.main_do_event(event)
        self.assertIsNotNone(self.view.canvas.get_window().get_cursor())
        self.assertIn("north_west", self.view.background_cursors)
        x = self.view.viewport.x + 500 * self.view.viewport.scale
        y = self.view.viewport.y + 500 * self.view.viewport.scale
        self.Gtk.main_do_event(self.background_event(self.view.Gdk.EventType.MOTION_NOTIFY, x, y))
        self.assertIsNone(self.view.canvas.get_window().get_cursor())
        self.Gtk.main_do_event(event)
        self.view.background_left(None, None)
        self.assertIsNone(self.view.canvas.get_window().get_cursor())

    def test_all_four_pages_export_without_any_device_operations(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("fcntl.ioctl", side_effect=AssertionError("No ioctl")):
            self.view.skin.export(directory, generated_mouse=False)
            for page in PAGES:
                data = (Path(directory) / f"{page}.png").read_bytes()
                self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertGreater(len(data), 10000)
            original = (Path(directory) / "buttons.png").read_bytes()
            self.view.skin.export(directory)
            self.assertNotEqual(original, (Path(directory) / "buttons.png").read_bytes())


if __name__ == "__main__":
    unittest.main()
