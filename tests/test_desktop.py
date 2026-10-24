"""Offline UI tests. Optional native tests never enumerate or contact a mouse."""

import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from evofox_blaze.ui_layout import HEIGHT, WIDTH, PAGES, Rect, Viewport, controls_for
from tools.prepare_ui_skin import IMAGES, stage


ROOT = Path(__file__).resolve().parents[1]
SKIN = ROOT / ".work/ui-skin"
STATE = ROOT / "docs/device-captures/30fa-1440-0100-state-read-01/state-read.jsonl"


class LayoutTests(unittest.TestCase):
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
            if self.view.diagnostics is not None:
                self.view.diagnostics.busy = False
            self.view.window.destroy()
            self.control.run.assert_not_called()

    @staticmethod
    def settle():
        from gi.repository import GLib
        loop = GLib.MainLoop()
        GLib.timeout_add(60, lambda: (loop.quit(), False)[1])
        loop.run()

    def test_four_native_pages_disable_unsupported_controls_and_keep_navigation(self):
        with patch("fcntl.ioctl", side_effect=AssertionError("No ioctl")):
            for page in PAGES:
                self.view.select_page(page)
                for name, button in self.view.buttons.items():
                    spec = self.view.specs[name]
                    self.assertEqual(button.get_accessible().get_name(), spec.label)
                    if not spec.action:
                        self.assertFalse(button.get_sensitive(), name)
                        self.assertTrue(button.get_tooltip_text())
                        self.view.activate(None, name)
                self.assertFalse(self.view.buttons["apply"].get_sensitive())
                self.assertTrue(self.view.buttons["buttons"].get_sensitive())
            self.assertIn("no device read", self.view.window.get_title())

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

    def test_all_four_pages_export_without_any_device_operations(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("fcntl.ioctl", side_effect=AssertionError("No ioctl")):
            self.view.skin.export(directory)
            for page in PAGES:
                data = (Path(directory) / f"{page}.png").read_bytes()
                self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertGreater(len(data), 10000)
            original = (Path(directory) / "buttons.png").read_bytes()
            self.view.skin.export(directory, generated_mouse=True)
            self.assertNotEqual(original, (Path(directory) / "buttons.png").read_bytes())


if __name__ == "__main__":
    unittest.main()
