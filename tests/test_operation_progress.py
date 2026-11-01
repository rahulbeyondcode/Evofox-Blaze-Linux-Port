"""Phase hints use fake transactions or plain Python children, never hardware."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from evofox_blaze.device_control import DeviceControl, run_with_progress
from evofox_blaze.feature_read import Journal
from evofox_blaze.operation_progress import PROGRESS_FD, PhaseReporter, event_phase


class PhaseReportingTests(unittest.TestCase):
    def test_event_mapping_distinguishes_staged_reads_from_setting_writes(self):
        for event in ("state_feature_intent", "button_feature_intent", "shortcut_block_begin"):
            for phase in ("before", "read", None):
                self.assertEqual(event_phase(event, {"phase": phase, "operation": "SET_FEATURE"}), "reading")
            self.assertEqual(event_phase(event, {"phase": "verify"}), "verifying")
        for event in ("config_write_intent", "button_write_intent", "shortcut_write_begin"):
            self.assertEqual(event_phase(event, {}), "writing")
        self.assertEqual(event_phase("activation_begin", {}), "activating")
        self.assertIsNone(event_phase("shortcut_config_complete", {}))
        self.assertIsNone(event_phase("config_failed", {}))

    def test_reporter_is_opt_in_deduplicated_and_never_uses_stdout(self):
        with patch.dict(os.environ, {}, clear=True), patch("os.write") as write:
            PhaseReporter().report("reading")
            write.assert_not_called()
        with patch.dict(os.environ, {PROGRESS_FD: "123"}), patch("os.write") as write:
            reporter = PhaseReporter()
            for phase in (None, "unknown", "reading", "reading", "verifying"):
                reporter.report(phase)
            self.assertEqual([call.args for call in write.call_args_list],
                             [(123, b"reading\n"), (123, b"verifying\n")])

    def test_disconnected_progress_does_not_interrupt_or_retry(self):
        with patch.dict(os.environ, {PROGRESS_FD: "123"}), patch("os.write", side_effect=BrokenPipeError) as write:
            reporter = PhaseReporter()
            reporter.report("writing")
            reporter.report("verifying")
            write.assert_called_once()

    def test_invalid_or_standard_stream_descriptors_are_ignored(self):
        for fd in ("", "invalid", "-1", "0", "1", "2", "99999999999999999999999999"):
            with self.subTest(fd=fd), patch.dict(os.environ, {PROGRESS_FD: fd}), patch("os.write") as write:
                PhaseReporter().report("reading")
                write.assert_not_called()

    def test_journal_intent_remains_durable_before_phase_and_has_no_new_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.jsonl"
            journal = Journal(path)
            self.addCleanup(journal.close)
            order = []
            with patch("os.fsync", side_effect=lambda *_: order.append("durable")), \
                    patch.object(journal.reporter, "report", side_effect=lambda phase: order.append(phase)):
                journal.record("state_feature_intent", phase="verify")
            self.assertEqual(order, ["durable", "verifying"])
            self.assertEqual(len(path.read_text().splitlines()), 1)
            self.assertEqual(json.loads(path.read_text())["event"], "state_feature_intent")
            with patch("os.fsync", side_effect=OSError("Synthetic disk failure")), \
                    patch.object(journal.reporter, "report") as report, self.assertRaises(OSError):
                journal.record("config_write_intent")
            report.assert_not_called()

    def test_fake_transactions_report_only_phases_actually_reached(self):
        from test_apply_activation import FakeChange, KINDS
        for kind in KINDS:
            for activation in (False, True):
                with self.subTest(kind=kind, activation=activation):
                    case = FakeChange(self, kind)
                    with patch.dict(os.environ, {PROGRESS_FD: "123"}), patch("os.write") as write:
                        case.run(activation)
                    phases = [call.args[1].decode().strip() for call in write.call_args_list]
                    self.assertEqual(phases, ["reading", "backup", "writing", "verifying"] +
                                     (["activating"] if activation else []))
                    case.inspect()  # Strict evidence validation is unchanged.
                    case.mouse.capture = case.mouse.root / "unchanged"
                    with patch.dict(os.environ, {PROGRESS_FD: "123"}), patch("os.write") as write:
                        case.run(activation)
                    self.assertEqual([call.args[1] for call in write.call_args_list], [b"reading\n"])

    def test_failed_backup_never_reports_writing_verifying_or_activation(self):
        from test_apply_activation import FakeChange, KINDS
        for kind in KINDS:
            case = FakeChange(self, kind)
            with patch.dict(os.environ, {PROGRESS_FD: "123"}), patch("os.write") as write, \
                    patch.object(case.backend, "_save_backup", side_effect=OSError("Synthetic backup failure")), \
                    self.assertRaises(OSError):
                case.run()
            self.assertEqual([call.args[1] for call in write.call_args_list], [b"reading\n", b"backup\n"])

    def test_plain_python_child_streams_before_exit_without_changing_final_output(self):
        # The child waits for acknowledgment: a buffered-after-exit implementation
        # cannot pass. This program has no mouse imports or device operations.
        with tempfile.TemporaryDirectory() as directory:
            ack = Path(directory) / "ack"
            code = ("import os, pathlib, time, sys; "
                    f"os.write(int(os.environ[{PROGRESS_FD!r}]), b'reading\\nunknown\\nverifying\\n'); "
                    f"ack = pathlib.Path({str(ack)!r}); "
                    "deadline = time.monotonic() + 5\n"
                    "while not ack.exists() and time.monotonic() < deadline: time.sleep(.01)\n"
                    "assert ack.exists(), 'progress was buffered'\n"
                    "print('{\"outcome\":\"synthetic\"}'); print('diagnostic', file=sys.stderr)")
            phases = []
            def progress(phase):
                phases.append(phase)
                ack.touch()
            result = run_with_progress([sys.executable, "-c", code], Path(directory), progress)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(phases, ["reading", "verifying"])
            self.assertEqual(json.loads(result.stdout), {"outcome": "synthetic"})
            self.assertEqual(result.stderr.strip(), "diagnostic")

    def test_callback_failure_is_nonfatal_and_pipe_is_drained(self):
        code = ("import os; "
                f"os.write(int(os.environ[{PROGRESS_FD!r}]), b'writing\\nverifying\\n'); print('{{}}')")
        callback = Mock(side_effect=RuntimeError("Synthetic UI error"))
        result = run_with_progress([sys.executable, "-c", code], Path.cwd(), callback)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(callback.call_count, 2)

    def test_progress_does_not_bypass_consent_or_change_commands_or_error_handling(self):
        control = DeviceControl(capture_root=Path("/synthetic"))
        with patch("subprocess.run") as run:
            with self.assertRaises(ValueError):
                control.run("read", progress=Mock())
            run.assert_not_called()
            with self.assertRaises(ValueError):
                control.run("read", confirmed=True, progress=True)
            run.assert_not_called()
        callback = Mock()
        with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "Synthetic failure")) as run:
            with self.assertRaisesRegex(RuntimeError, "Synthetic failure.*No retry"):
                control.run("read", confirmed=True, progress=callback)
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0][:3], [sys.executable, "-m", "evofox_blaze.state_read"])
            self.assertEqual(len(run.call_args.kwargs["pass_fds"]), 1)
        callback.assert_not_called()

    def test_child_start_failure_cleans_up_pipe_and_reader(self):
        import threading
        before = {thread.ident for thread in threading.enumerate()}
        with patch("subprocess.run", side_effect=OSError("Synthetic spawn failure")), self.assertRaises(OSError):
            run_with_progress(["synthetic"], Path.cwd(), Mock())
        self.assertEqual({thread.ident for thread in threading.enumerate()}, before)
