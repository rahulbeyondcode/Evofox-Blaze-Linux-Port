import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import unittest

from evofox_blaze.device_control import DeviceControl, state_directory


class DeviceControlTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.control = DeviceControl(baseline=self.root / "probe.json", capture_root=self.root / "captures")

    def test_constructing_service_or_refusing_confirmation_performs_no_operation(self):
        with patch("subprocess.run") as run:
            for confirmed in (False, None, 1, "yes"):
                with self.subTest(confirmed=confirmed), self.assertRaises(ValueError):
                    self.control.run("read", confirmed=confirmed)
            run.assert_not_called()
        self.assertFalse((self.root / "captures").exists())

    def test_read_and_polling_commands_are_fixed_python_modules_without_a_shell(self):
        result = subprocess.CompletedProcess([], 0, stdout=json.dumps({"outcome": "no-change"}), stderr="")
        with patch("subprocess.run", return_value=result) as run:
            read = self.control.run("read", confirmed=True)
            command = run.call_args.args[0]
            self.assertEqual(command[:3], [sys.executable, "-m", "evofox_blaze.state_read"])
            self.assertIn("--accept-staged-read-risk", command)
            self.assertNotIn("shell", run.call_args.kwargs)
            changed = self.control.run("polling", polling=1000, confirmed=True)
            command = run.call_args.args[0]
            self.assertEqual(command[2:5], ["evofox_blaze.config_write", "--polling", "1000"])
            self.assertIn("--accept-write-risk", command)
        self.assertNotEqual(read.capture_directory, changed.capture_directory)

    def test_restore_requires_a_selected_backup(self):
        result = subprocess.CompletedProcess([], 0, stdout="{}", stderr="")
        backup = self.root / "an earlier change/original-state.json"
        with patch("subprocess.run", return_value=result) as run:
            self.control.run("restore", restore_from=backup, confirmed=True)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--restore-backup") + 1], str(backup))

    def test_unknown_or_mixed_actions_do_not_start_a_backend(self):
        for action, arguments in (("firmware", {}), ("read", {"polling": 1000}),
                                  ("polling", {"polling": True}), ("polling", {"polling": 300}),
                                  ("restore", {"restore_from": "not-a-Path"})):
            with self.subTest(action=action, arguments=arguments), patch("subprocess.run") as run:
                with self.assertRaises(ValueError):
                    self.control.run(action, confirmed=True, **arguments)
                run.assert_not_called()

    def test_backend_error_is_not_retried(self):
        result = subprocess.CompletedProcess([], 1, stdout="", stderr="Synthetic failure")
        with patch("subprocess.run", return_value=result) as run:
            with self.assertRaisesRegex(RuntimeError, "No retry"):
                self.control.run("read", confirmed=True)
        run.assert_called_once()

    def test_state_directory_uses_absolute_xdg_path_or_home_fallback(self):
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(self.root)}):
            self.assertEqual(state_directory(), self.root / "evofox-blaze")
        with patch.dict(os.environ, {"XDG_STATE_HOME": "relative-is-not-an-xdg-state-home"}):
            self.assertEqual(state_directory(), Path.home() / ".local/state/evofox-blaze")


if __name__ == "__main__":
    unittest.main()
