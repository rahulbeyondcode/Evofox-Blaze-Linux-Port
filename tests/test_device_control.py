import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import unittest

from evofox_blaze.device_control import DeviceControl, state_directory
from evofox_blaze.shortcuts import Shortcut


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

    def test_experimental_activation_is_explicit_and_never_added_to_reads_or_restores(self):
        with patch("subprocess.run") as run:
            for value in (1, None, "yes"):
                with self.assertRaises(ValueError):
                    DeviceControl(experimental_activation=value)
            control = DeviceControl(experimental_activation=True, capture_root=self.root / "armed")
            run.assert_not_called()
            with self.assertRaises(ValueError):
                control.run("buttons", assignments={4: "back"})
            run.assert_not_called()
        reply = subprocess.CompletedProcess([], 0, stdout="{}", stderr="")
        actions = (("read", {}), ("read-buttons", {}), ("read-assignments", {}),
                   ("restore", {"restore_from": Path("original-state.json")}),
                   ("restore-buttons", {"restore_from": Path("button-backup.json")}),
                   ("restore-shortcuts", {"restore_from": Path("shortcut-backup.json")}),
                   ("buttons", {"assignments": {4: "back"}}), ("polling", {"polling": 1000}),
                   ("shortcuts", {"assignments": {}, "shortcuts": {5: Shortcut("a")}}))
        with patch("subprocess.run", return_value=reply) as run:
            for action, arguments in actions:
                control.run(action, confirmed=True, **arguments)
                self.assertEqual("--accept-activation-risk" in run.call_args.args[0],
                                 action in ("buttons", "polling", "shortcuts"), action)
                self.control.run(action, confirmed=True, **arguments)
                self.assertNotIn("--accept-activation-risk", run.call_args.args[0], action)

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

    def test_native_button_commands_are_scoped_modules_with_explicit_consent(self):
        result = subprocess.CompletedProcess([], 0, stdout="{}", stderr="")
        with patch("subprocess.run", return_value=result) as run:
            self.control.run("read-buttons", confirmed=True)
            self.assertEqual(run.call_args.args[0][2:5],
                             ["evofox_blaze.button_read", "--read-buttons", "--accept-staged-read-risk"])
            self.control.run("buttons", assignments={5: "forward", 4: "back"}, confirmed=True)
            command = run.call_args.args[0]
            self.assertEqual(command[2:8], ["evofox_blaze.button_write", "--accept-write-risk",
                                            "--assign", "4=back", "--assign", "5=forward"])
            backup = self.root / "button-backup.json"
            self.control.run("restore-buttons", restore_from=backup, confirmed=True)
            self.assertIn(str(backup), run.call_args.args[0])
            self.assertNotIn("shell", run.call_args.kwargs)

    def test_unknown_or_mixed_actions_do_not_start_a_backend(self):
        for action, arguments in (("firmware", {}), ("read", {"polling": 1000}),
                                  ("polling", {"polling": True}), ("polling", {"polling": 300}),
                                  ("restore", {"restore_from": "not-a-Path"}),
                                  ("read-buttons", {"assignments": {4: "back"}}),
                                  ("buttons", {"assignments": {9: "back"}}),
                                  ("buttons", {"assignments": {4: "Ctrl+C"}}),
                                  ("buttons", {"assignments": {4: "back"}, "polling": 500}),
                                  ("restore-buttons", {"restore_from": "not-a-Path"}),
                                  ("buttons", {"assignments": {4: "back"}, "shortcuts": {5: Shortcut("a")}}),
                                  ("shortcuts", {"assignments": {}, "shortcuts": {9: Shortcut("a")}}),
                                  ("shortcuts", {"assignments": {5: "back"}, "shortcuts": {5: Shortcut("a")}}),
                                  ("shortcuts", {"assignments": {}, "shortcuts": {5: Shortcut("a")}, "polling": 500}),
                                  ("restore-shortcuts", {"restore_from": "not-a-Path"}),
                                  ("restore-shortcuts", {"restore_from": Path("backup"), "shortcuts": {5: Shortcut("a")}})):
            with self.subTest(action=action, arguments=arguments), patch("subprocess.run") as run:
                with self.assertRaises(ValueError):
                    self.control.run(action, confirmed=True, **arguments)
                run.assert_not_called()

    def test_shortcut_command_includes_every_native_and_chord_request_without_shell_or_test_replay(self):
        result = subprocess.CompletedProcess([], 0, stdout="{}", stderr="")
        with patch("subprocess.run", return_value=result) as run:
            self.control.run("shortcuts", assignments={4: "back"},
                             shortcuts={5: Shortcut("Down", ("Control_L", "Shift_L"))}, confirmed=True)
        command = run.call_args.args[0]
        self.assertEqual(command[:4], [sys.executable, "-m", "evofox_blaze.shortcut_write", "--accept-shortcut-write-risk"])
        self.assertEqual(json.loads(command[command.index("--shortcut") + 1]),
                         {"slot": 5, "key": "Down", "modifiers": ["Control_L", "Shift_L"]})
        self.assertEqual(command[command.index("--assign") + 1], "4=back")
        self.assertNotIn("--first-tail-test", command)
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_shortcut_restore_has_separate_scope_and_requires_explicit_consent(self):
        backup = self.root / "shortcut-backup.json"
        with patch("subprocess.run") as run:
            with self.assertRaises(ValueError):
                self.control.run("restore-shortcuts", restore_from=backup)
            run.assert_not_called()
        result = subprocess.CompletedProcess([], 0, stdout="{}", stderr="")
        with patch("subprocess.run", return_value=result) as run:
            self.control.run("restore-shortcuts", restore_from=backup, confirmed=True)
        command = run.call_args.args[0]
        self.assertEqual(command[2:6], ["evofox_blaze.shortcut_write", "--restore-backup", str(backup),
                                       "--accept-shortcut-write-risk"])

    def test_assignment_read_is_an_explicit_scoped_module_without_setting_flags(self):
        result = subprocess.CompletedProcess([], 0, stdout="{}", stderr="")
        with patch("subprocess.run", return_value=result) as run:
            self.control.run("read-assignments", confirmed=True)
        command = run.call_args.args[0]
        self.assertEqual(command[2:5], ["evofox_blaze.assignment_read", "--read-assignments", "--accept-staged-read-risk"])
        self.assertNotIn("--accept-shortcut-write-risk", command)
        with patch("subprocess.run") as run:
            with self.assertRaises(ValueError):
                self.control.run("read-assignments", confirmed=True, shortcuts={5: Shortcut("a")})
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
