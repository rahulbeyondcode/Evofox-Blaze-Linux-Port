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


class NativeWindowSmokeTests(unittest.TestCase):
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
            self.assertEqual(view.details.get_char_count(), 0)
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
