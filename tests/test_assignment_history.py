from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from evofox_blaze.assignment_history import latest_assignments
from evofox_blaze.button_draft import ButtonDraft


ROOT = Path(__file__).resolve().parents[1]
CAPTURES = ROOT / "docs/device-captures"


class AssignmentHistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir="/tmp/opencode")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def capture(self, stamp, action="shortcuts"):
        directory = self.root / f"20261028T12000{stamp}.000000Z-{action}-0123abcd"
        directory.mkdir()
        if action == "shortcuts":
            source = CAPTURES / "30fa-1440-0100-shortcut-f13-test-01/shortcut-configuration.jsonl"
        else:
            source = CAPTURES / "30fa-1440-0100-button-remap-01/button-configuration.jsonl"
        path = directory / source.name
        shutil.copyfile(source, path)
        return path

    def test_latest_verified_saved_shortcuts_load_offline_without_device_or_subprocess(self):
        self.capture(0, "buttons")
        path = self.capture(1)
        with patch("fcntl.ioctl", side_effect=AssertionError("No hardware")), \
                patch("subprocess.run", side_effect=AssertionError("No subprocess")):
            model, selected = latest_assignments(self.root)
        self.assertEqual(selected, path)
        draft = ButtonDraft()
        draft.sync(model.presentation.details)
        self.assertEqual(draft.labels()[3], "F13")
        self.assertEqual(draft.labels()[:3], ("Left Click", "Right Click", "Middle Click"))
        self.assertFalse(draft.can_apply)

    def test_later_incomplete_or_failed_attempt_never_falls_back_to_old_values(self):
        self.capture(0)
        path = self.root / "20261028T120001.000000Z-buttons-0123abcd"
        path.mkdir()
        model, selected = latest_assignments(self.root)
        self.assertIsNone(model.presentation)
        self.assertIsNone(selected)
        self.assertIn("older values were not loaded", model.error)

    def test_missing_history_creates_nothing_and_symlink_is_refused(self):
        root = self.root / "absent"
        model, selected = latest_assignments(root)
        self.assertIsNone(model.presentation)
        self.assertEqual(model.error, "")
        self.assertFalse(root.exists())
        path = self.capture(1)
        original = path.read_bytes()
        path.unlink()
        target = self.root / "target.jsonl"
        target.write_bytes(original)
        path.symlink_to(target)
        model, selected = latest_assignments(self.root)
        self.assertIsNone(model.presentation)
        self.assertIn("Cannot recover", model.error)

    def test_wrong_operation_and_symlink_capture_directories_are_not_loaded(self):
        path = self.capture(0)
        changed = self.root / "20261028T120000.000000Z-buttons-0123abcd"
        path.parent.rename(changed)
        (changed / path.name).rename(changed / "button-configuration.jsonl")
        model, _ = latest_assignments(self.root)
        self.assertIsNone(model.presentation)
        self.assertIn("does not match", model.error)
        link = self.root / "20261028T120001.000000Z-shortcuts-0123abcd"
        link.symlink_to(changed, target_is_directory=True)
        model, _ = latest_assignments(self.root)
        self.assertIsNone(model.presentation)
        self.assertIn("symlink", model.error)
