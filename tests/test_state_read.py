import contextlib
from dataclasses import replace
import errno
import io
import json
from pathlib import Path
import stat
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from evofox_blaze import feature_read as feature
from evofox_blaze import state_read as state
from evofox_blaze.read_preview import SetFeature


BASELINE = (Path(__file__).resolve().parents[1]
            / "docs/device-captures/2026-10-23-30fa-1440-0100/probe.json")
FIXTURE = json.loads((Path(__file__).parent / "fixtures/anko-read-corroboration.json").read_text())


class StateTransportTests(unittest.TestCase):
    def setUp(self):
        baseline, _ = feature.load_baseline(BASELINE)
        self.target = replace(baseline, path="/dev/hidraw42")
        self.descriptor = self.target.descriptor
        self.info = (3, self.target.vid, self.target.pid)
        self.events = []
        self.features = []
        self.overrides = {}
        self.wrong_report = False

    def record(self, event, **fields):
        self.events.append((event, fields))

    def ioctl(self, fd, request, buffer, mutate):
        self.assertEqual(fd, 42)
        self.assertTrue(mutate)
        if request == feature.HIDIOCGRAWINFO:
            buffer[:] = struct.pack("=IHH", *self.info)
        elif request == feature.HIDIOCGRDESCSIZE:
            buffer[:] = struct.pack("=I", len(self.descriptor))
        elif request == feature.HIDIOCGRDESC:
            buffer[:4] = struct.pack("=I", len(self.descriptor))
            buffer[4:4 + len(self.descriptor)] = self.descriptor
        else:
            self.assertIn(request, (state.SET_FEATURE, state.GET_FEATURE))
            self.assertEqual(self.events[-1][0], "state_feature_intent")
            operation, _, expected = FIXTURE["feature_events"][len(self.features)]
            if request == state.SET_FEATURE:
                self.assertEqual(operation, "SET_FEATURE")
                self.assertEqual(buffer, bytes.fromhex(expected))
                self.features.append(("SET_FEATURE", bytes(buffer)))
            else:
                self.assertEqual(operation, "GET_FEATURE")
                self.assertEqual(buffer, b"\x07" + bytes(7))
                self.features.append(("GET_FEATURE", bytes(buffer)))
                buffer[:] = bytes.fromhex(expected)
                if self.wrong_report:
                    buffer[0] = 6
            ordinal = len(self.features)
            self.assertEqual(self.events[-1][1]["ordinal"], ordinal)
            override = self.overrides.get(ordinal, 8)
            if isinstance(override, Exception):
                raise override
            return override
        return 0

    def run_read(self, *, record=None, recheck=None):
        with patch.object(state, "check_host"), patch.object(feature, "check_host"), \
                patch.object(feature.os, "open", return_value=42) as opened, \
                patch.object(feature.os, "fstat", return_value=SimpleNamespace(st_mode=stat.S_IFCHR)), \
                patch.object(feature.os, "close") as closed, \
                patch("fcntl.flock"), \
                patch("fcntl.ioctl", side_effect=self.ioctl), patch.object(state.time, "sleep") as sleep:
            try:
                return state.read_state_once(self.target, record or self.record, recheck or Mock(),
                                             accept_staged_read_risk=True)
            finally:
                if opened.called:
                    flags = opened.call_args.args[1]
                    self.assertEqual(flags & feature.os.O_ACCMODE, feature.os.O_RDWR)
                    self.assertTrue(flags & feature.os.O_NOFOLLOW)
                    self.assertTrue(flags & feature.os.O_CLOEXEC)
                    closed.assert_called_once_with(42)
                self.sleeps = sleep.call_args_list

    def test_exact_capture_matched_read_returns_eight_collected_bytes(self):
        recheck = Mock()
        self.assertEqual(self.run_read(recheck=recheck).hex(" "), FIXTURE["collected_hex"])
        self.assertEqual(len(self.features), 26)
        self.assertEqual(sum(op == "SET_FEATURE" for op, _ in self.features), 18)
        self.assertEqual(sum(op == "GET_FEATURE" for op, _ in self.features), 8)
        self.assertEqual(self.features[-1], ("SET_FEATURE", bytes.fromhex("07 18 00 00 00 00 00 00")))
        self.assertEqual(len(self.sleeps), 18)
        self.assertAlmostEqual(sum(call.args[0] for call in self.sleeps), 0.036)
        recheck.assert_called_once_with(self.target)
        for op, report in self.features:
            if op == "SET_FEATURE":
                self.assertEqual(report[1], 0x18)
                self.assertIn(report[2], (0, 3, 5))
                self.assertEqual(report[6], 0)

    def test_third_party_descriptor_envelope_matches_but_is_not_a_Blaze_backup(self):
        baseline = json.loads(BASELINE.read_text())["nodes"][1]
        self.assertEqual(bytes.fromhex(baseline["usb_descriptors_hex"]),
                         bytes.fromhex(FIXTURE["usb_device_descriptor_hex"])
                         + bytes.fromhex(FIXTURE["usb_configuration_descriptor_hex"]))
        self.assertFalse(FIXTURE["hid_report_descriptor_observed_in_public_capture"])
        self.assertEqual(FIXTURE["collected_hex"], FIXTURE["last_committed_block"]["data_hex"])

    def test_direct_call_requires_explicit_risk_acknowledgement(self):
        with patch.object(feature.os, "open") as opened:
            for acknowledgement in (False, None, 1, "yes"):
                with self.subTest(acknowledgement=acknowledgement), self.assertRaises(ValueError):
                    state.read_state_once(self.target, self.record, Mock(),
                                          accept_staged_read_risk=acknowledgement)
            opened.assert_not_called()

    def test_other_revision_interface_identity_or_descriptor_refused_before_open(self):
        original = self.target
        changes = ({"vid": 0xFFFF}, {"pid": 0x1E01}, {"revision": "0101"},
                   {"interface": "00"}, {"report_length": 16}, {"descriptor": bytes(8)})
        with patch.object(feature.os, "open") as opened:
            for change in changes:
                self.target = replace(original, **change)
                with self.subTest(change=change), self.assertRaises(ValueError):
                    self.run_read()
            opened.assert_not_called()

    def test_planner_change_cannot_inject_a_commit(self):
        altered = state.fixed_read_steps() + (SetFeature(bytes.fromhex("07 18 09 00 18 00 00 07")),)
        with patch.object(state, "preview_read", return_value=altered), \
                patch.object(feature.os, "open") as opened, self.assertRaises(ValueError):
            state.read_state_once(self.target, self.record, Mock(), accept_staged_read_risk=True)
        opened.assert_not_called()

    def test_handle_usb_identity_or_descriptor_mismatch_never_sends_a_feature(self):
        self.info = (3, 0xFFFF, 0x1440)
        with self.assertRaises(ValueError):
            self.run_read()
        self.assertEqual(self.features, [])
        self.info = (3, self.target.vid, self.target.pid)
        self.descriptor = bytes([0]) + self.descriptor[1:]
        with self.assertRaises(ValueError):
            self.run_read()
        self.assertEqual(self.features, [])

    def test_sysfs_recheck_failure_prevents_all_features(self):
        with self.assertRaises(ValueError):
            self.run_read(recheck=Mock(side_effect=ValueError("device changed")))
        self.assertEqual(self.features, [])

    def test_each_failed_intent_log_prevents_that_operation_and_any_cleanup(self):
        for failed_ordinal in (1, 9, 11, 26):
            self.events.clear()
            self.features.clear()
            def failed(event, **fields):
                if event == "state_feature_intent" and fields["ordinal"] == failed_ordinal:
                    raise OSError(errno.ENOSPC, "synthetic disk full")
                self.record(event, **fields)
            with self.subTest(ordinal=failed_ordinal), self.assertRaises(OSError):
                self.run_read(record=failed)
            self.assertEqual(len(self.features), failed_ordinal - 1)

    def test_failed_result_log_also_stops_without_another_request(self):
        def failed(event, **fields):
            if event == "state_feature_result" and fields["ordinal"] == 11:
                raise OSError(errno.ENOSPC, "synthetic disk full")
            self.record(event, **fields)
        with self.assertRaises(OSError):
            self.run_read(record=failed)
        self.assertEqual(len(self.features), 11)

    def test_ioctl_error_is_recorded_once_without_retry_or_cleanup(self):
        self.overrides[11] = OSError(errno.EPIPE, "synthetic stalled GET")
        with self.assertRaises(OSError):
            self.run_read()
        self.assertEqual(len(self.features), 11)
        self.assertEqual(self.events[-1][0], "state_feature_error")
        self.assertEqual(self.events[-1][1]["ordinal"], 11)

    def test_short_zero_oversized_and_boolean_ioctl_results_are_refused(self):
        for ordinal, result in ((1, 0), (1, 7), (1, 9), (1, True), (11, 7), (11, 0)):
            self.features.clear()
            self.events.clear()
            self.overrides = {ordinal: result}
            with self.subTest(ordinal=ordinal, result=result), self.assertRaises(ValueError):
                self.run_read()
            self.assertEqual(len(self.features), ordinal)

    def test_wrong_get_report_id_is_recorded_and_aborts(self):
        self.wrong_report = True
        with self.assertRaises(ValueError):
            self.run_read()
        self.assertEqual(len(self.features), 11)
        self.assertTrue(self.events[-1][1]["buffer_hex_after"].startswith("06 "))


class StateCLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        saved = json.loads(BASELINE.read_text())
        node = next(node for node in saved["nodes"] if node["configuration_report"])
        self.node = dict(node, path="/dev/hidraw99")
        self.args = ["--read-state", "--accept-staged-read-risk", "--baseline", str(BASELINE),
                     "--capture", str(self.root / "result")]

    def test_both_opt_ins_are_required_before_enumeration(self):
        with patch.object(state, "enumerate_devices") as enumerate_:
            for flag in ("--read-state", "--accept-staged-read-risk"):
                args = [arg for arg in self.args if arg != flag]
                with self.subTest(flag=flag), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    state.main(args)
            enumerate_.assert_not_called()

    def test_no_arbitrary_address_or_scan_options_exist(self):
        with patch.object(state, "enumerate_devices") as enumerate_, \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            state.main(self.args + ["--address", "0x003f"])
        enumerate_.assert_not_called()

    def test_success_saves_exclusive_sanitized_evidence_and_does_not_claim_full_backup(self):
        with patch.object(state, "enumerate_devices", return_value=[self.node]), \
                patch.object(state, "read_state_once", return_value=bytes.fromhex(FIXTURE["collected_hex"])) as read_, \
                contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(state.main(self.args), 0)
        self.assertTrue(read_.call_args.kwargs["accept_staged_read_risk"])
        self.assertFalse(json.loads(output.getvalue())["complete_configuration_backup"])
        journal = self.root / "result/state-read.jsonl"
        saved = journal.read_text()
        self.assertNotIn("hidraw99", saved)
        self.assertEqual(journal.stat().st_mode & 0o777, 0o600)
        events = [json.loads(line) for line in saved.splitlines()]
        self.assertEqual(events[-1]["event"], "state_complete")
        self.assertEqual(events[-1]["dpi_stage_selector_candidate"], 1)

    def test_existing_capture_is_not_overwritten_or_reused(self):
        (self.root / "result").mkdir()
        with patch.object(state, "enumerate_devices", return_value=[self.node]), \
                patch.object(state, "read_state_once") as read_, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(state.main(self.args), 1)
        read_.assert_not_called()

    def test_failed_transaction_is_logged_with_no_automatic_recovery(self):
        with patch.object(state, "enumerate_devices", return_value=[self.node]), \
                patch.object(state, "read_state_once", side_effect=OSError(errno.EPIPE, "synthetic stall")) as read_, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(state.main(self.args), 1)
        read_.assert_called_once()
        events = [json.loads(line) for line in (self.root / "result/state-read.jsonl").read_text().splitlines()]
        self.assertEqual(events[-1]["event"], "state_failed")
        self.assertIn("No automatic requests", events[-1]["recovery"])


if __name__ == "__main__":
    unittest.main()
