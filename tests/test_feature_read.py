import contextlib
from dataclasses import replace
import errno
import hashlib
import io
import json
from pathlib import Path
import stat
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from evofox_blaze import feature_read as read


BASELINE = (Path(__file__).resolve().parents[1]
            / "docs/device-captures/2026-10-23-30fa-1440-0100/probe.json")


class FeatureTransportTests(unittest.TestCase):
    def setUp(self):
        self.baseline, _ = read.load_baseline(BASELINE)
        self.target = replace(self.baseline, path="/dev/hidraw42")
        self.response = bytes.fromhex("07 11 22 33 44 55 66 77")  # Synthetic, not captured.
        self.returned = 8
        self.info = (3, 0x30FA, 0x1440)
        self.descriptor = self.target.descriptor
        self.descriptor_size = len(self.descriptor)
        self.events = []
        self.requests = []

    def ioctl(self, fd, request, buffer, mutate):
        self.assertEqual(fd, 42)
        self.assertTrue(mutate)
        self.requests.append(request)
        if request == read.HIDIOCGRAWINFO:
            buffer[:] = struct.pack("=IHH", *self.info)
        elif request == read.HIDIOCGRDESCSIZE:
            buffer[:] = struct.pack("=I", self.descriptor_size)
        elif request == read.HIDIOCGRDESC:
            self.assertEqual(len(buffer), 4100)
            buffer[:4] = struct.pack("=I", len(self.descriptor))
            buffer[4:4 + len(self.descriptor)] = self.descriptor
        elif request & 0xFFFF == 0x4807:
            self.assertEqual(buffer, bytearray([7]) + bytearray(len(buffer) - 1))
            self.assertEqual(self.events[-1][0], "get_feature_intent")
            buffer[:len(self.response)] = self.response
            return self.returned
        else:
            self.fail(f"Unexpected ioctl, including any SET_REPORT: {request:#x}")
        return 0

    def record(self, event, **fields):
        self.events.append((event, fields))

    def run_read(self, *, record=None, recheck=None, mode=stat.S_IFCHR):
        with patch.object(read, "check_host"), \
                patch.object(read.os, "open", return_value=42) as opened, \
                patch.object(read.os, "fstat", return_value=SimpleNamespace(st_mode=mode)), \
                patch.object(read.os, "close") as closed, \
                patch("fcntl.ioctl", side_effect=self.ioctl), \
                contextlib.redirect_stderr(io.StringIO()):
            try:
                return read.get_feature_once(self.target, record or self.record, recheck or Mock())
            finally:
                if opened.called:
                    flags = opened.call_args.args[1]
                    self.assertEqual(flags & read.os.O_ACCMODE, read.os.O_RDONLY)
                    self.assertTrue(flags & read.os.O_NOFOLLOW)
                    self.assertTrue(flags & read.os.O_CLOEXEC)
                    closed.assert_called_once_with(42)

    def assert_no_feature_request(self):
        self.assertFalse(any(request & 0xFFFF == 0x4807 for request in self.requests))

    def test_one_get_only_after_handle_and_descriptor_checks(self):
        recheck = Mock()
        self.assertEqual(self.run_read(recheck=recheck), self.response)
        self.assertEqual(self.requests, [read.HIDIOCGRAWINFO, read.HIDIOCGRDESCSIZE,
                                        read.HIDIOCGRDESC, 0xC0084807])
        recheck.assert_called_once_with(self.target)
        self.assertEqual([event for event, _ in self.events],
                         ["handle_validated", "get_feature_intent", "get_feature_response"])

    def test_real_capture_replays_offline_and_matches_descriptor_baseline(self):
        path = (BASELINE.parents[1]
                / "30fa-1440-0100-get-feature-01/feature-read.jsonl")
        events = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual([event["event"] for event in events], [
            "session", "handle_validated", "get_feature_intent",
            "get_feature_response", "complete",
        ])
        self.assertEqual(events[0]["baseline_sha256"],
                         hashlib.sha256(BASELINE.read_bytes()).hexdigest())
        self.assertEqual(events[0]["identity"], self.target.identity())
        self.assertEqual(bytes.fromhex(events[0]["report_descriptor_hex"]), self.descriptor)
        self.assertEqual(events[2]["ioctl"], "0xc0084807")
        self.assertEqual(events[2]["request_buffer_hex"], "07 00 00 00 00 00 00 00")
        self.response = bytes.fromhex(events[3]["buffer_hex_after"])
        self.returned = events[3]["returned_length"]
        self.assertEqual(self.run_read().hex(" "), events[4]["response_hex"])

    def test_length_is_derived_not_fixed_to_eight(self):
        raw = bytes.fromhex("06 01 ff 09 01 a1 01 85 07 75 08 95 0f b1 02 c0")
        self.target = replace(self.target, descriptor=raw, report_length=16)
        self.descriptor, self.descriptor_size = raw, len(raw)
        self.response, self.returned = bytes([7]) + bytes(15), 16
        self.assertEqual(len(self.run_read()), 16)
        self.assertEqual(self.requests[-1], 0xC0104807)

    def test_wrong_vid_pid_or_bus_never_gets_a_feature(self):
        for identity in ((3, 0xFFFF, 0x1440), (3, 0x30FA, 0xFFFF), (5, 0x30FA, 0x1440)):
            self.info = identity
            self.requests.clear()
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                self.run_read()
            self.assert_no_feature_request()

    def test_not_a_character_device_is_refused(self):
        with self.assertRaises(ValueError):
            self.run_read(mode=stat.S_IFREG)
        self.assertEqual(self.requests, [])

    def test_descriptor_size_or_bytes_changed_never_gets_feature(self):
        self.descriptor_size += 1
        with self.assertRaises(ValueError):
            self.run_read()
        self.assert_no_feature_request()
        self.descriptor_size -= 1
        self.descriptor = bytes([0]) + self.descriptor[1:]
        with self.assertRaises(ValueError):
            self.run_read()
        self.assert_no_feature_request()

    def test_sysfs_recheck_failure_never_gets_feature(self):
        with self.assertRaises(ValueError):
            self.run_read(recheck=Mock(side_effect=ValueError("device changed")))
        self.assert_no_feature_request()

    def test_failed_intent_logging_prevents_feature_request(self):
        def record(event, **fields):
            if event == "get_feature_intent":
                raise OSError(errno.ENOSPC, "synthetic full disk")
        with self.assertRaises(OSError):
            self.run_read(record=record)
        self.assert_no_feature_request()

    def test_short_zero_and_oversized_returns_are_not_padded_success(self):
        for returned in (0, 7, 9):
            self.returned = returned
            with self.subTest(returned=returned), self.assertRaises(ValueError):
                self.run_read()
            self.assertEqual(self.events[-1][1]["returned_length"], returned)

    def test_wrong_response_report_id_is_rejected_but_logged(self):
        self.response = b"\x06" + self.response[1:]
        with self.assertRaises(ValueError):
            self.run_read()
        self.assertEqual(self.events[-1][1]["buffer_hex_after"].split()[0], "06")

    def test_get_error_is_logged_once_without_retry(self):
        original = self.ioctl
        def failed(fd, request, buffer, mutate):
            if request & 0xFFFF == 0x4807:
                self.requests.append(request)
                raise OSError(errno.EPIPE, "synthetic stall")
            return original(fd, request, buffer, mutate)
        self.ioctl = failed
        with self.assertRaises(OSError):
            self.run_read()
        self.assertEqual(self.requests.count(0xC0084807), 1)
        self.assertEqual(self.events[-1], ("get_feature_error", {
            "errno": errno.EPIPE, "message": "synthetic stall",
            "buffer_hex_after": "07 00 00 00 00 00 00 00",
        }))

    def test_mismatched_declared_report_length_refused_before_open(self):
        self.target = replace(self.target, report_length=9)
        with patch.object(read, "check_host"), patch.object(read.os, "open") as opened:
            with self.assertRaises(ValueError):
                read.get_feature_once(self.target, self.record, Mock())
            opened.assert_not_called()

    def test_unsupported_ioctl_abi_refused_before_open(self):
        with patch.object(read.platform, "machine", return_value="mips"), \
                patch.object(read.os, "open") as opened:
            with self.assertRaises(ValueError):
                read.get_feature_once(self.target, self.record, Mock())
            opened.assert_not_called()


class FeatureCLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        saved = json.loads(BASELINE.read_text())
        self.node = next(n for n in saved["nodes"] if n["configuration_report"])
        self.node = dict(self.node, path="/dev/hidraw99")
        self.args = ["--read-feature", "--baseline", str(BASELINE),
                     "--capture", str(self.root / "result")]

    def test_explicit_opt_in_is_required_before_enumeration(self):
        with patch.object(read, "enumerate_devices") as enumerate_, \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                read.main(self.args[1:])
            self.assertEqual(error.exception.code, 2)
            enumerate_.assert_not_called()

    def test_baseline_hashes_and_ambiguity_are_checked(self):
        baseline, _ = read.load_baseline(BASELINE)
        self.assertEqual(read.select_target([self.node], baseline).path, "/dev/hidraw99")
        other = dict(self.node, path="/dev/hidraw1")
        with self.assertRaises(ValueError):
            read.select_target([self.node, other], baseline)
        self.assertEqual(read.select_target([self.node, other], baseline,
                                           "/dev/hidraw1").path, "/dev/hidraw1")
        for change in ({"report_descriptor_sha256": "bad"},
                       {"usb": dict(self.node["usb"], bcdDevice="9999")},
                       {"interface": dict(self.node["interface"], bInterfaceNumber="00")},
                       {"pid": "9999"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                read.select_target([self.node | change], baseline)

    def test_missing_or_ambiguous_baseline_is_rejected(self):
        path = self.root / "baseline.json"
        for data in ([], {"schema_version": 2, "nodes": []},
                     {"schema_version": 1, "nodes": []},
                     {"schema_version": 1, "nodes": [self.node, self.node]}):
            path.write_text(json.dumps(data))
            with self.subTest(data=data), self.assertRaises(ValueError):
                read.load_baseline(path)

    def test_capture_is_exclusive_and_never_overwritten(self):
        directory = self.root / "result"
        directory.mkdir()
        with patch.object(read, "enumerate_devices", return_value=[self.node]), \
                patch.object(read, "get_feature_once") as get_, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(read.main(self.args), 1)
            get_.assert_not_called()

    def test_successful_capture_is_sanitized_and_retains_raw_response(self):
        response = bytes.fromhex("07 11 22 33 44 55 66 77")
        def get_(target, record, recheck):
            recheck(target)
            record("get_feature_intent", request_buffer_hex="07 00 00 00 00 00 00 00")
            record("get_feature_response", returned_length=8, buffer_hex_after=response.hex(" "))
            return response
        with patch.object(read, "enumerate_devices", return_value=[self.node]), \
                patch.object(read, "get_feature_once", side_effect=get_), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(read.main(self.args), 0)
        text = (self.root / "result/feature-read.jsonl").read_text()
        self.assertNotIn(str(self.root), text)
        self.assertNotIn("hidraw99", text)
        self.assertEqual(json.loads(text.splitlines()[-1])["response_hex"], response.hex(" "))
        self.assertEqual((self.root / "result/feature-read.jsonl").stat().st_mode & 0o777, 0o600)

    def test_permission_error_is_logged_without_host_path(self):
        error = PermissionError(errno.EACCES, "Permission denied", "/home/private/file")
        with patch.object(read, "enumerate_devices", return_value=[self.node]), \
                patch.object(read, "get_feature_once", side_effect=error), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(read.main(self.args), 1)
        text = (self.root / "result/feature-read.jsonl").read_text()
        self.assertNotIn("/home/private", text)
        self.assertEqual(json.loads(text.splitlines()[-1])["errno"], errno.EACCES)


if __name__ == "__main__":
    unittest.main()
