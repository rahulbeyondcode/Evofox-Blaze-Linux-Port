import contextlib
import copy
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

from evofox_blaze import activation
from evofox_blaze import feature_read as feature
from evofox_blaze.activation_capture import decode_activation_journal
from evofox_blaze.read_preview import Delay, SetFeature
from evofox_blaze.state_read import IDENTITY, SET_FEATURE


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/device-captures/2026-10-23-30fa-1440-0100/probe.json"
FIXTURE = json.loads((ROOT / "tests/fixtures/vendor-activation-observations.json").read_text())


class ActivationPlanTests(unittest.TestCase):
    def test_exact_source_sequence_and_no_parameters_or_mutable_steps(self):
        steps = activation.activation_steps()
        self.assertIsInstance(steps, tuple)
        self.assertEqual(steps, (SetFeature(bytes.fromhex(FIXTURE["first_frame_hex"])),
                                 Delay(FIXTURE["delay_milliseconds"]),
                                 SetFeature(bytes.fromhex(FIXTURE["second_frame_hex"]))))
        self.assertEqual(steps[0].report, bytes.fromhex("07 18 10 00 00 00 00 00"))
        self.assertEqual(steps[-1].report, bytes.fromhex("07 18 00 00 00 00 00 00"))
        with self.assertRaises(TypeError):
            activation.activation_steps(0x10)
        with self.assertRaises(AttributeError):
            steps[0].report = bytes(8)
        self.assertFalse(FIXTURE["hardware_activation_tested"])
        self.assertFalse(FIXTURE["automatic_gui_activation_enabled"])

    def test_builder_argument_masks_and_relative_call_bytes_correspond_to_fixture(self):
        for arguments, key in ((FIXTURE["first_builder_arguments"], "first_frame_hex"),
                               (FIXTURE["second_builder_arguments"], "second_frame_hex")):
            flags = ((arguments[0] << 5) + (arguments[1] << 4) + arguments[2] * 4
                     + arguments[3] * 8 + arguments[4] * 2 + arguments[5]) & 255
            self.assertEqual(bytes.fromhex(FIXTURE[key]),
                             bytes((7, 0x18, flags, arguments[7], arguments[6] & 255,
                                    arguments[6] >> 8, arguments[9], arguments[8])))
        targets = {"0x413d7e": 0x413910, "0x413da2": 0x413910,
                   "0x42a142": 0x413a10, "0x42a161": 0x413d60}
        for check in FIXTURE["instruction_checks"]:
            if check["address"] in targets:
                instruction = bytes.fromhex(check["bytes"])
                self.assertEqual(instruction[0], 0xe8)
                self.assertEqual(int(check["address"], 16) + 5
                                 + int.from_bytes(instruction[1:], "little", signed=True),
                                 targets[check["address"]])

    def test_default_and_explicit_preview_never_enumerate_open_or_ioctl(self):
        with patch.object(activation, "enumerate_devices") as enum, \
                patch.object(feature.os, "open") as opened, patch("fcntl.ioctl") as ioctl:
            for arguments in ([], ["--preview"]):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(activation.main(arguments), 0)
                result = json.loads(out.getvalue())
                self.assertEqual(result["mode"], "offline-preview")
                self.assertFalse(result["hardware_access"])
                self.assertEqual(len(result["steps"]), 3)
            enum.assert_not_called()
            opened.assert_not_called()
            ioctl.assert_not_called()


class FakeActivation:
    def setUp(self):
        self.target = replace(feature.load_baseline(BASELINE)[0], path="/dev/hidraw42")
        self.events, self.features = [], []
        self.raw_info = (3, self.target.vid, self.target.pid)
        self.descriptor = self.target.descriptor
        self.overrides = {}
        self.change_at = None

    def record(self, event, **fields):
        self.events.append({"event": event, **fields})

    def ioctl(self, fd, request, buffer, mutate):
        self.assertEqual(fd, 42)
        if request == feature.HIDIOCGRAWINFO:
            buffer[:] = struct.pack("=IHH", *self.raw_info)
            return 0
        if request == feature.HIDIOCGRDESCSIZE:
            buffer[:] = struct.pack("=I", len(self.descriptor))
            return 0
        if request == feature.HIDIOCGRDESC:
            buffer[:4] = struct.pack("=I", len(self.descriptor))
            buffer[4:4 + len(self.descriptor)] = self.descriptor
            return 0
        self.assertEqual(request, SET_FEATURE)  # Never a GET or other feature command.
        self.assertEqual(self.events[-1]["event"], "activation_intent")
        self.assertEqual(self.events[-1]["frame_hex"], buffer.hex(" "))
        self.features.append(bytes(buffer))
        ordinal = len(self.features)
        if self.change_at == ordinal:
            buffer[0] ^= 1
        value = self.overrides.get(ordinal, 8)
        if isinstance(value, Exception):
            raise value
        return value

    @contextlib.contextmanager
    def fake_device(self):
        with patch.object(activation, "check_host"), patch.object(feature, "check_host"), \
                patch.object(feature.os, "open", return_value=42) as opened, \
                patch.object(feature.os, "fstat", return_value=SimpleNamespace(st_mode=stat.S_IFCHR)), \
                patch.object(feature.os, "close") as closed, patch("fcntl.flock") as lock, \
                patch("fcntl.ioctl", side_effect=self.ioctl), patch.object(activation.time, "sleep") as sleep:
            yield opened, closed, lock, sleep

    def run_activation(self, record=None, recheck=None):
        with self.fake_device():
            return activation.activate_once(self.target, record or self.record, recheck or Mock(),
                                            accept_activation_risk=True)


class ActivationTransportTests(FakeActivation, unittest.TestCase):
    def test_exact_two_sets_delay_identity_lock_and_no_behavior_claim(self):
        recheck = Mock()
        with self.fake_device() as (opened, closed, lock, sleep):
            result = activation.activate_once(self.target, self.record, recheck, accept_activation_risk=True)
        self.assertEqual(self.features, [step.report for step in activation.activation_steps()
                                        if isinstance(step, SetFeature)])
        sleep.assert_called_once_with(0.005)
        recheck.assert_called_once_with(self.target)
        lock.assert_called_once()
        closed.assert_called_once_with(42)
        self.assertEqual(opened.call_args.args[1] & feature.os.O_ACCMODE, feature.os.O_RDWR)
        self.assertTrue(opened.call_args.args[1] & feature.os.O_NOFOLLOW)
        self.assertEqual(result["outcome"], "sequence-sent")
        self.assertFalse(result["behavior_verified"])
        self.assertFalse(result["complete_configuration_backup"])

    def test_missing_strict_consent_and_wrong_identity_fail_before_open(self):
        with patch.object(feature.os, "open") as opened, patch.object(activation, "check_host"):
            for value in (False, 1, None, "yes"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    activation.activate_once(self.target, self.record, Mock(), accept_activation_risk=value)
            for change in ({"vid": 0xffff}, {"pid": 0x1e01}, {"revision": "0101"},
                           {"interface": "00"}, {"report_length": 16}, {"descriptor": bytes(8)}):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    activation.activate_once(replace(self.target, **change), self.record, Mock(),
                                             accept_activation_risk=True)
        opened.assert_not_called()

    def test_handle_identity_descriptor_recheck_and_lock_failure_send_nothing(self):
        self.raw_info = (3, 0xffff, 0x1440)
        with self.assertRaises(ValueError):
            self.run_activation()
        self.raw_info = (3, 0x30fa, 0x1440)
        self.descriptor = bytes((0,)) + self.descriptor[1:]
        with self.assertRaises(ValueError):
            self.run_activation()
        self.descriptor = self.target.descriptor
        with self.assertRaises(ValueError):
            self.run_activation(recheck=Mock(side_effect=ValueError("synthetic unplug")))
        with self.fake_device(), patch("fcntl.flock", side_effect=BlockingIOError), self.assertRaises(BlockingIOError):
            activation.activate_once(self.target, self.record, Mock(), accept_activation_risk=True)
        self.assertEqual(self.features, [])

    def test_every_intent_result_and_delay_log_failure_stops_without_cleanup(self):
        for kind, ordinal in (("activation_intent", 1), ("activation_result", 1),
                              ("activation_delay", None), ("activation_intent", 2),
                              ("activation_result", 2)):
            self.features.clear()
            self.events.clear()
            def failed(event, **fields):
                if event == kind and (ordinal is None or fields["ordinal"] == ordinal):
                    raise OSError(errno.ENOSPC, "synthetic disk full")
                self.record(event, **fields)
            with self.subTest(kind=kind, ordinal=ordinal), self.assertRaises(OSError):
                self.run_activation(record=failed)
            expected = 1 if ordinal is None else ordinal - (kind == "activation_intent")
            self.assertEqual(len(self.features), expected)

    def test_short_changed_boolean_and_failed_feature_never_retry_or_send_cleanup(self):
        for ordinal in (1, 2):
            for value in (0, 7, 9, True, OSError(errno.EPIPE, "synthetic stall"), "changed"):
                self.features.clear()
                self.events.clear()
                self.change_at = ordinal if value == "changed" else None
                self.overrides = {} if value == "changed" else {ordinal: value}
                with self.subTest(ordinal=ordinal, value=value), self.assertRaises((OSError, ValueError)):
                    self.run_activation()
                self.assertEqual(len(self.features), ordinal)

    def test_delay_failure_never_sends_the_second_frame(self):
        with self.fake_device(), patch.object(activation.time, "sleep", side_effect=OSError("synthetic interruption")), \
                self.assertRaises(OSError):
            activation.activate_once(self.target, self.record, Mock(), accept_activation_risk=True)
        self.assertEqual(len(self.features), 1)


class ActivationCaptureTests(FakeActivation, unittest.TestCase):
    def completed(self):
        self.record("activation_session", identity=IDENTITY, accepted_activation_risk=True,
                    report_descriptor_hex=self.target.descriptor.hex(" "), scope=activation.NOTICE)
        result = self.run_activation()
        self.record("activation_complete", **result)
        return copy.deepcopy(self.events)

    @staticmethod
    def encode(events):
        return b"\n".join(json.dumps(event).encode() for event in events)

    def test_completed_journal_inspects_offline_without_hardware_or_behavior_claim(self):
        raw = self.encode(self.completed())
        with patch("fcntl.ioctl", side_effect=AssertionError("No device")), \
                patch.object(activation, "enumerate_devices", side_effect=AssertionError("No probe")):
            result = decode_activation_journal(raw)
        self.assertEqual(result["mode"], "offline-activation-inspection")
        self.assertFalse(result["behavior_verified"])

    def test_incomplete_extra_failed_or_changed_journals_are_rejected(self):
        events = self.completed()
        variations = [events[:-1], events + [events[-1]], events[:3] + events[4:],
                      events[:-1] + [{"event": "activation_failed"}], [None]]
        changes = [(0, "accepted_activation_risk", False), (0, "scope", "only one button"),
                   (0, "report_descriptor_hex", "00"), (1, "bus", True),
                   (2, "frame_hex", "07 20 00 00 00 00 00 00"),
                   (3, "returned_length", True), (4, "milliseconds", 0),
                   (5, "frame_hex", "07 18 09 00 00 00 00 00"),
                   (6, "buffer_hex_after", "07 18 10 00 00 00 00 00"),
                   (7, "behavior_verified", True), (7, "complete_configuration_backup", True)]
        for index, key, value in changes:
            changed = copy.deepcopy(events)
            changed[index][key] = value
            variations.append(changed)
        for candidate in variations:
            with self.subTest(candidate=candidate), self.assertRaises((ValueError, KeyError, TypeError)):
                decode_activation_journal(self.encode(candidate))


class ActivationCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        node = next(node for node in json.loads(BASELINE.read_text())["nodes"] if node["configuration_report"])
        self.node = dict(node, path="/dev/hidraw42")
        self.args = ["--activate", "--accept-activation-risk", "--baseline", str(BASELINE),
                     "--capture", str(self.root / "capture")]

    def test_missing_consent_preview_mixed_options_and_arbitrary_commands_fail_before_enumeration(self):
        variations = [[value for value in self.args if value != "--accept-activation-risk"],
                      [value for value in self.args if value != "--activate"],
                      ["--activate", "--accept-activation-risk"],
                      ["--preview", "--device", "/dev/hidraw42"],
                      self.args + ["--frame", "07 20 00 00 00 00 00 00"],
                      self.args + ["--address", "0x10"]]
        for args in variations:
            with patch.object(activation, "enumerate_devices") as enum, \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                activation.main(args)
            enum.assert_not_called()

    def test_exclusive_private_capture_and_real_synthetic_journal(self):
        @contextlib.contextmanager
        def handle(target, record, recheck, *, writable=False):
            self.assertTrue(writable)
            recheck(target)
            record("handle_validated", identity=IDENTITY, bus=3, lock_mode="exclusive-advisory")
            yield 42
        with patch.object(activation, "enumerate_devices", return_value=[self.node]), \
                patch.object(activation, "validated_handle", side_effect=handle), \
                patch("fcntl.ioctl", return_value=8) as ioctl, patch.object(activation.time, "sleep"), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(activation.main(self.args), 0)
        self.assertEqual(ioctl.call_count, 2)
        capture = self.root / "capture"
        path = capture / "activation.jsonl"
        self.assertEqual(capture.stat().st_mode & 0o777, 0o700)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("hidraw42", path.read_text())
        self.assertFalse(decode_activation_journal(path.read_bytes())["behavior_verified"])
        self.assertEqual(list(capture.iterdir()), [path])  # No invented configuration backup.
        with patch.object(activation, "enumerate_devices") as enum, \
                patch.object(activation, "activate_once") as send, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(activation.main(self.args), 1)
        enum.assert_not_called()
        send.assert_not_called()

    def test_failed_send_is_logged_once_and_not_retried(self):
        with patch.object(activation, "enumerate_devices", return_value=[self.node]), \
                patch.object(activation, "activate_once", side_effect=OSError(errno.EPIPE, "synthetic stall")) as send, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(activation.main(self.args), 1)
        send.assert_called_once()
        events = [json.loads(line) for line in (self.root / "capture/activation.jsonl").read_text().splitlines()]
        self.assertEqual(events[-1]["event"], "activation_failed")
        self.assertNotIn("hidraw42", str(events))

    def test_symlink_or_wrong_baseline_is_refused_before_device_access(self):
        symlink = self.root / "baseline.json"
        symlink.symlink_to(BASELINE)
        for path in (symlink, self.root / "missing.json"):
            args = self.args.copy()
            args[args.index("--baseline") + 1] = str(path)
            with patch.object(activation, "enumerate_devices") as enum, \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(activation.main(args), 1)
            enum.assert_not_called()
