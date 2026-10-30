import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from evofox_blaze.capture_view import CaptureModel, present_capture
from evofox_blaze import gui


CAPTURE = (Path(__file__).resolve().parents[1]
           / "docs/device-captures/30fa-1440-0100-get-feature-01/feature-read.jsonl")


class CaptureViewTests(unittest.TestCase):
    def test_large_saved_shortcut_capture_is_offline_and_does_not_enable_polling(self):
        path = CAPTURE.parents[1] / "30fa-1440-0100-shortcut-f13-test-01/shortcut-configuration.jsonl"
        self.assertGreater(path.stat().st_size, 1024 * 1024)
        with patch("fcntl.ioctl", side_effect=AssertionError("No hardware")), \
                patch("evofox_blaze.probe.enumerate_devices", side_effect=AssertionError("No enumeration")):
            view = present_capture(path)
        data = json.loads(view.details)
        self.assertEqual(data["verified_shortcuts"], [{"slot": 5, "key": "F13", "modifiers": []}])
        self.assertNotIn("Polling setting candidate", dict(view.rows))
        self.assertIn("no custom macros", dict(view.rows)["Keyboard / macro programming"])
        self.assertFalse(data["behavior_verified"])

    def test_saved_capture_is_labeled_offline_and_unverified(self):
        view = present_capture(CAPTURE)
        rows = dict(view.rows)
        self.assertEqual(rows["USB identity"], "30fa:1440")
        self.assertEqual(rows["Captured response"], "07 00 58 09 1f 00 23 7b")
        self.assertEqual(rows["Profile index candidate"], "0 — not hardware-validated")
        self.assertIn("not live", rows["Source"])
        self.assertEqual(rows["Lighting readback"], "Unavailable")
        self.assertEqual(rows["Full configuration backup"], "Unavailable")
        self.assertIn("explicit confirmation", rows["Device writes"])
        self.assertFalse(json.loads(view.details)["hardware_field_validation"])

    def test_loading_never_enumerates_or_contacts_a_device(self):
        with patch("evofox_blaze.probe.enumerate_devices", side_effect=AssertionError("No enumeration")), \
                patch("evofox_blaze.feature_read.get_feature_once", side_effect=AssertionError("No GET")), \
                patch("fcntl.ioctl", side_effect=AssertionError("No ioctl")):
            model = CaptureModel()
            self.assertTrue(model.load(CAPTURE))
            self.assertIsNotNone(model.presentation)
            self.assertEqual(model.error, "")

    def test_failed_load_clears_previous_capture_and_recovery_works(self):
        model = CaptureModel()
        self.assertTrue(model.load(CAPTURE))
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "bad.jsonl"
            bad.write_text("not JSON")
            self.assertFalse(model.load(bad))
        self.assertIsNone(model.presentation)
        self.assertIn("Cannot inspect capture", model.error)
        self.assertTrue(model.load(CAPTURE))
        self.assertEqual(model.error, "")

    def test_failure_details_count_each_backend_commit_without_accepting_partial_state(self):
        from evofox_blaze.capture_view import failure_details
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as temporary:
            path = Path(temporary) / "incomplete.jsonl"
            for kind in ("shortcut_write_intent", "button_write_intent", "config_write_intent"):
                with self.subTest(kind=kind):
                    events = [{"event": kind, "frame_hex": "07 18 09 00 18 00 00 07"},
                              {"event": "config_failed", "message": "Synthetic commit interruption"}]
                    path.write_text("\n".join(json.dumps(event) for event in events) + '\n{"event":')
                    with patch("fcntl.ioctl", side_effect=AssertionError("No device")):
                        details = failure_details(path, "Synthetic incomplete journal")
                    self.assertIn("Recorded settings-commit requests: 1", details)
                    self.assertIn("Settings may already have changed", details)
                    self.assertIn("No partial capture is accepted", details)

    def test_symlink_input_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            link = Path(directory) / "link.jsonl"
            link.symlink_to(CAPTURE)
            model = CaptureModel()
            self.assertFalse(model.load(link))
            self.assertIsNone(model.presentation)

    def test_help_does_not_require_gtk_or_a_display(self):
        with patch.object(gui, "load_gtk", side_effect=AssertionError("No GUI initialization")), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
            gui.main(["--help"])
        self.assertEqual(raised.exception.code, 0)

    def test_experimental_activation_launch_only_arms_explicit_future_apply(self):
        Gtk = SimpleNamespace(init_check=lambda args: (True, args), main=Mock(), main_quit=Mock())
        for arguments, target in ((["--experimental-activation"], "evofox_blaze.desktop.BlazeWindow"),
                                  (["--experimental-activation", "--diagnostics"], "evofox_blaze.gui.CaptureWindow"),
                                  (["--experimental-activation", "--capture", str(CAPTURE)], "evofox_blaze.gui.CaptureWindow")):
            with self.subTest(arguments=arguments), patch.object(gui, "load_gtk", return_value=Gtk), \
                    patch(target) as window, patch("fcntl.ioctl", side_effect=AssertionError("No device")), \
                    patch("evofox_blaze.probe.enumerate_devices", side_effect=AssertionError("No probe")), \
                    patch("evofox_blaze.activation._activate_on_handle", side_effect=AssertionError("No activation")):
                self.assertEqual(gui.main(arguments), 0)
                self.assertTrue(window.call_args.kwargs["control"].experimental_activation)

    def test_missing_desktop_dependencies_are_reported(self):
        with patch.object(gui, "load_gtk", side_effect=ImportError("missing gi")), \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(gui.main([]), 1)
        self.assertIn("PyGObject and GTK 3", errors.getvalue())

    def test_missing_display_is_reported_without_loading_a_capture(self):
        Gtk = SimpleNamespace(init_check=lambda args: (False, args))
        with patch.object(gui, "load_gtk", return_value=Gtk), \
                patch.object(gui, "CaptureModel", side_effect=AssertionError("No capture loading")), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(gui.main(["--capture", str(CAPTURE)]), 1)

    def test_main_loads_only_the_requested_capture_before_starting_ui(self):
        from unittest.mock import Mock
        Gtk = SimpleNamespace(init_check=lambda args: (True, args), main=Mock(), main_quit=Mock())
        with patch.object(gui, "load_gtk", return_value=Gtk), patch.object(gui, "CaptureWindow") as window:
            self.assertEqual(gui.main(["--capture", str(CAPTURE)]), 0)
        passed_gtk, model = window.call_args.args
        self.assertIs(passed_gtk, Gtk)
        self.assertEqual(dict(model.presentation.rows)["USB identity"], "30fa:1440")
        window.return_value.window.show_all.assert_called_once_with()
        Gtk.main.assert_called_once_with()

    def test_supplied_artwork_is_default_and_reference_is_an_explicit_option(self):
        Gtk = SimpleNamespace(init_check=lambda args: (True, args), main=Mock(), main_quit=Mock())
        for arguments, expected in (([], True), (["--generated-mouse"], True), (["--reference-mouse"], False)):
            with self.subTest(arguments=arguments), patch.object(gui, "load_gtk", return_value=Gtk), \
                    patch("evofox_blaze.desktop.BlazeWindow") as window:
                self.assertEqual(gui.main(arguments), 0)
                self.assertEqual(window.call_args.kwargs["generated_mouse"], expected)
                self.assertEqual(window.call_args.kwargs["mouse_image"].name, "MouseImage.png")

    def test_artwork_choices_are_mutually_exclusive_before_initialization(self):
        with patch.object(gui, "load_gtk") as load, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            gui.main(["--reference-mouse", "--generated-mouse"])
        load.assert_not_called()


class NativeWindowSmokeTests(unittest.TestCase):
    def test_standalone_phase_updates_and_completion_keep_saved_validation_shielded(self):
        Gtk, view, control = self.shortcut_window()
        from gi.repository import GLib
        view.busy = True
        view.operation_action = "read"
        view.refresh()
        progress = view.operation_progress.start()
        progress("reading")
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        self.assertEqual(view.operation_overlay.status.get_text(), "Reading settings.")
        def load(path):
            self.assertEqual(view.operation_overlay.status.get_text(), "Checking saved result.")
            self.assertTrue(view.operation_overlay.shield.get_visible())
            return False
        with patch.object(view.model, "load", side_effect=load):
            view.operation_finished("read", SimpleNamespace(capture_directory=Path("/synthetic")), None)
        progress("writing")
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        self.assertFalse(view.operation_overlay.shield.get_visible())
        self.assertIsNone(view.operation_overlay.timer)
        control.run.assert_not_called()

    def test_standalone_controls_show_a_non_dismissible_busy_shield_and_clear_on_failure(self):
        Gtk, view, control = self.shortcut_window()
        view.window.show_all()
        self.assertFalse(view.operation_overlay.shield.get_visible())
        dialog = Mock()
        dialog.run.return_value = Gtk.ResponseType.ACCEPT
        with patch.object(Gtk, "MessageDialog", return_value=dialog), patch("evofox_blaze.gui.threading.Thread") as worker:
            view.confirm_operation("polling", polling=1000)
            self.assertTrue(view.operation_overlay.shield.get_visible())
            self.assertTrue(view.operation_overlay.spinner.get_property("active"))
            self.assertFalse(view.tabs.is_sensitive())
            self.assertTrue(view.prevent_close_while_busy(None, None))
            self.assertEqual(view.operation_overlay.title.get_text(), "Saving to mouse…")
            worker.assert_called_once()
        view.operation_finished("polling", None, "Synthetic interrupted write")
        self.assertFalse(view.operation_overlay.shield.get_visible())
        self.assertFalse(view.operation_overlay.spinner.get_property("active"))
        self.assertTrue(view.tabs.is_sensitive())
        self.assertIn("interrupted write", view.message.get_text())
        control.run.assert_not_called()

    def test_failure_diagnostics_are_visible_and_cleared_after_a_successful_load(self):
        Gtk, view, control = self.shortcut_window()
        view.model.error = "Synthetic readback failure"
        view.model.error_details = "Synthetic detailed commit failure; backup retained"
        with patch("fcntl.ioctl", side_effect=AssertionError("No device")):
            view.refresh()
            text = view.details.get_text(view.details.get_start_iter(), view.details.get_end_iter(), False)
            self.assertIn("backup retained", text)
            self.assertTrue(view.model.load(CAPTURE))
            view.refresh()
        self.assertEqual(view.model.error_details, "")
        text = view.details.get_text(view.details.get_start_iter(), view.details.get_end_iter(), False)
        self.assertNotIn("Synthetic detailed", text)
        control.run.assert_not_called()

    def test_capture_chooser_cannot_bypass_busy_operation_guard(self):
        Gtk, view, control = self.shortcut_window()
        view.busy = True
        view.refresh()
        with patch.object(Gtk, "FileChooserDialog") as chooser:
            view.choose_capture(None)
        chooser.assert_not_called()
        control.run.assert_not_called()

    def shortcut_window(self):
        try:
            Gtk = gui.load_gtk()
        except (ImportError, ValueError) as error:
            self.skipTest(f"Optional GTK unavailable: {error}")
        if not Gtk.init_check([])[0]:
            self.skipTest("No desktop display")
        control = SimpleNamespace(capture_root=Path("/synthetic/evidence"), run=Mock())
        view = gui.CaptureWindow(Gtk, CaptureModel(), control=control)
        self.addCleanup(view.window.destroy)
        return Gtk, view, control

    def test_shortcut_restore_chooser_only_starts_a_separately_confirmed_request(self):
        Gtk, view, control = self.shortcut_window()
        backup = CAPTURE.parents[1] / "30fa-1440-0100-shortcut-f13-test-01/shortcut-backup.json"
        view.last_shortcut_backup = backup
        chooser = Mock()
        chooser.run.return_value = Gtk.ResponseType.ACCEPT
        chooser.get_filename.return_value = str(backup)
        with patch.object(Gtk, "FileChooserDialog", return_value=chooser), patch.object(view, "confirm_operation") as confirm:
            view.restore_shortcuts.clicked()
            chooser.set_filename.assert_called_once_with(str(backup))
            confirm.assert_called_once_with("restore-shortcuts", restore_from=backup)
        control.run.assert_not_called()
        view.busy = True
        view.refresh()
        self.assertFalse(view.restore_shortcuts.get_sensitive())
        with patch.object(Gtk, "FileChooserDialog") as dialog:
            view.choose_shortcut_backup(None)
        dialog.assert_not_called()

    def test_shortcut_restore_cancel_is_offline_and_confirmation_explains_scope(self):
        Gtk, view, control = self.shortcut_window()
        dialog = Mock()
        dialog.run.return_value = Gtk.ResponseType.CANCEL
        with patch.object(Gtk, "MessageDialog", return_value=dialog), patch("evofox_blaze.gui.threading.Thread") as worker:
            view.confirm_operation("restore-shortcuts", restore_from=Path("shortcut-backup.json"))
        worker.assert_not_called()
        control.run.assert_not_called()
        text = dialog.format_secondary_text.call_args.args[0]
        self.assertIn("intervening edits", text)
        self.assertIn("partial backup", text)
        self.assertIn("No retry", text)

    def test_shortcut_restore_loads_real_synthetic_restore_journal_and_tracks_backup(self):
        from test_shortcut_write import ShortcutTransactionTests
        Gtk, view, control = self.shortcut_window()
        mouse = ShortcutTransactionTests("test_fresh_backup_minimal_writes_and_complete_readback")
        mouse.setUp()
        self.addCleanup(mouse.doCleanups)
        mouse.change()
        backup = mouse.capture / "shortcut-backup.json"
        mouse.capture = mouse.root / "restore-ui"
        payload = mouse.change(restore_from=backup)
        result = SimpleNamespace(capture_directory=mouse.capture, payload=payload)
        view.operation_finished("restore-shortcuts", result, None)
        self.assertEqual(json.loads(view.model.presentation.details)["operation"], "restore")
        self.assertEqual(view.last_shortcut_backup, mouse.capture / "shortcut-backup.json")
        self.assertIn("Physically unplug", view.message.get_text())
        self.assertFalse(view.apply_button.get_sensitive())
        view.operation_finished("restore-shortcuts", None, "Synthetic uncertain restore")
        self.assertIsNone(view.model.presentation)
        self.assertEqual(view.message.get_text(), "Synthetic uncertain restore")
        control.run.assert_not_called()

    def test_shortcut_restore_does_not_accept_a_change_journal_as_restoration(self):
        Gtk, view, control = self.shortcut_window()
        result = SimpleNamespace(capture_directory=CAPTURE.parents[1] / "30fa-1440-0100-shortcut-f13-test-01", payload={})
        view.operation_finished("restore-shortcuts", result, None)
        self.assertIsNone(view.model.presentation)
        self.assertIn("does not describe a shortcut restore", view.message.get_text())

    def test_shortcut_restore_thread_start_failure_clears_busy_without_device_access(self):
        Gtk, view, control = self.shortcut_window()
        dialog = Mock()
        dialog.run.return_value = Gtk.ResponseType.ACCEPT
        with patch.object(Gtk, "MessageDialog", return_value=dialog), \
                patch("evofox_blaze.gui.threading.Thread", side_effect=RuntimeError("Synthetic thread failure")):
            view.confirm_operation("restore-shortcuts", restore_from=Path("shortcut-backup.json"))
        self.assertFalse(view.busy)
        self.assertIn("Synthetic thread failure", view.message.get_text())
        control.run.assert_not_called()

    def test_native_result_loads_its_journal_and_failure_clears_stale_evidence(self):
        try:
            Gtk = gui.load_gtk()
        except (ImportError, ValueError) as error:
            self.skipTest(f"Optional GTK unavailable: {error}")
        if not Gtk.init_check([])[0]:
            self.skipTest("No desktop display")
        control = SimpleNamespace(capture_root=Path("/synthetic/evidence"), run=Mock())
        view = gui.CaptureWindow(Gtk, CaptureModel(), control=control)
        directory = CAPTURE.parents[1] / "30fa-1440-0100-button-remap-01"
        result = SimpleNamespace(capture_directory=directory,
                                 payload={"outcome": "written-and-read-back", "backup_file": "button-backup.json"})
        try:
            with patch("fcntl.ioctl", side_effect=AssertionError("No hardware")):
                view.operation_finished("buttons", result, None)
                self.assertEqual(json.loads(view.model.presentation.details)["mode"], "offline-button-configuration-inspection")
                self.assertEqual(view.last_button_backup, directory / "button-backup.json")
                self.assertIn("Physically unplug", view.message.get_text())
                self.assertFalse(view.apply_button.get_sensitive())
                view.operation_finished("buttons", None, "Synthetic failure")
                self.assertIsNone(view.model.presentation)
                self.assertEqual(view.message.get_text(), "Synthetic failure")
                self.assertTrue(view.read_buttons.get_sensitive())
        finally:
            view.window.destroy()
        control.run.assert_not_called()

    def test_construct_refresh_and_clear_native_window(self):
        try:
            Gtk = gui.load_gtk()
        except (ImportError, ValueError) as error:
            self.skipTest(f"Optional GTK 3 unavailable: {error}")
        if not Gtk.init_check([])[0]:
            self.skipTest("No desktop display for optional native-window smoke test")
        model = CaptureModel()
        view = gui.CaptureWindow(Gtk, model)
        try:
            self.assertEqual(len(view.rows), 0)
            self.assertTrue(model.load(CAPTURE))
            view.refresh()
            self.assertEqual(dict(tuple(row) for row in view.rows)["USB identity"], "30fa:1440")
            self.assertTrue(view.details.get_char_count())
            model.presentation = None
            model.error = "Synthetic failure <not markup>"
            view.refresh()
            self.assertEqual(len(view.rows), 0)
            # Verified-state JSON must be replaced with plain failure details,
            # not silently erased or left showing the previous saved state.
            self.assertEqual(view.details.get_text(view.details.get_start_iter(),
                                                  view.details.get_end_iter(), False), model.error)
            self.assertEqual(view.message.get_text(), model.error)
        finally:
            view.window.destroy()

    def test_cancelled_confirmation_and_busy_window_do_not_run_device_actions(self):
        try:
            Gtk = gui.load_gtk()
        except (ImportError, ValueError) as error:
            self.skipTest(f"Optional GTK unavailable: {error}")
        if not Gtk.init_check([])[0]:
            self.skipTest("No desktop display")
        control = SimpleNamespace(capture_root=Path("/synthetic/evidence"), run=Mock())
        view = gui.CaptureWindow(Gtk, CaptureModel(), control=control)
        try:
            self.assertFalse(view.apply_button.get_sensitive())
            cancelled = Mock()
            cancelled.run.return_value = Gtk.ResponseType.CANCEL
            with patch.object(Gtk, "MessageDialog", return_value=cancelled):
                view.confirm_operation("read")
            control.run.assert_not_called()
            self.assertFalse(view.busy)
            view.busy = True
            self.assertTrue(view.prevent_close_while_busy(None, None))
            view.confirm_operation("read")
            control.run.assert_not_called()
        finally:
            view.window.destroy()


if __name__ == "__main__":
    unittest.main()
