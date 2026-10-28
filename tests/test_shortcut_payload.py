import contextlib
import copy
from dataclasses import replace
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from evofox_blaze import shortcut_payload_read as payload
from evofox_blaze.feature_read import load_baseline
from evofox_blaze.shortcut_capture import decode_shortcut_header_capture
from evofox_blaze.state_read import GET_FEATURE, IDENTITY, SET_FEATURE


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/device-captures/2026-10-23-30fa-1440-0100/probe.json"
HEADERS = ROOT / "docs/device-captures/30fa-1440-0100-shortcut-headers-01/shortcut-headers.jsonl"


class ShortcutPayloadTests(unittest.TestCase):
    def test_original_payload_capture_is_immutable_and_confirms_the_source_codec(self):
        from evofox_blaze.shortcut_codec import decode_keyboard_record
        from evofox_blaze.shortcuts import Shortcut
        path = ROOT / "docs/device-captures/30fa-1440-0100-shortcut-payload-01/shortcut-payload.jsonl"
        result = payload.decode_payload_capture(path)
        self.assertEqual(result["capture_sha256"], "92ae5407d085c8792674164cfd83f7c6d3da0ba315f997dfd3c106a4f646b579")
        data = bytes.fromhex(result["collected_hex"])
        self.assertEqual(decode_keyboard_record(data[:8], 3).as_shortcut(allow_press_only=True),
                         Shortcut("Left", ("Control_L", "Super_L")))
        self.assertEqual(data[64], 0xff)  # 0440: original candidate space is not all zero.

    def setUp(self):
        self.basis = decode_shortcut_header_capture(HEADERS)
        self.target = replace(load_baseline(BASELINE)[0], path="/dev/hidraw99")
        self.data = bytes(range(96))
        self.selected = None
        self.features = []
        self.events = []

    def record(self, event, **fields):
        self.events.append({"event": event, **fields})

    @contextlib.contextmanager
    def handle(self, target, record, recheck, *, writable=False):
        self.assertTrue(writable)
        recheck(target)
        record("handle_validated", identity=IDENTITY, bus=3)
        yield 42

    def ioctl(self, fd, request, buffer, mutate):
        self.assertEqual(fd, 42)
        self.assertEqual(self.events[-1]["event"], "shortcut_feature_intent")
        self.features.append((request, bytes(buffer)))
        if request == GET_FEATURE:
            self.assertIsNotNone(self.selected)
            buffer[:] = bytes((7, self.data[self.selected], 0, 0, 0, 0, 0, 0))
        else:
            self.assertEqual(request, SET_FEATURE)
            self.assertIn(buffer[2], (0, 3, 5))
            base = int.from_bytes(buffer[4:6], "little")
            self.assertIn(base, (0, *payload.PAYLOAD_BASES))
            self.assertEqual(buffer[6], 0)
            self.selected = base - 0x400 + buffer[3] if buffer[2] == 5 else None
        return 8

    def collect(self):
        with patch.object(payload, "validated_handle", side_effect=self.handle), patch.object(payload, "check_host"), \
                patch("fcntl.ioctl", side_effect=self.ioctl), patch("time.sleep"):
            return payload.read_payload_once(self.target, self.record, Mock(), self.basis,
                                             accept_staged_read_risk=True)

    def test_payload_plan_is_fixed_to_the_exact_first_inspection_scope(self):
        self.assertEqual(payload.PAYLOAD_BASES, tuple(range(0x400, 0x460, 8)))
        for base in (True, 8, 0x3f8, 0x401, 0x460, 0xf18):
            with self.subTest(base=base), self.assertRaises(ValueError):
                payload.payload_read_steps(base)

    def test_all_96_bytes_and_exact_counts_are_collected_without_commit(self):
        self.assertEqual(self.collect(), self.data)
        self.assertEqual(sum(request == SET_FEATURE for request, _ in self.features), 216)
        self.assertEqual(sum(request == GET_FEATURE for request, _ in self.features), 96)
        self.assertFalse(payload.describe_payload(self.data)["complete_configuration_backup"])

    def test_wrong_basis_identity_or_missing_consent_fails_before_open(self):
        with patch.object(payload, "validated_handle") as opened, patch.object(payload, "check_host"):
            for consent in (False, 1, None):
                with self.assertRaises(ValueError):
                    payload.read_payload_once(self.target, Mock(), Mock(), self.basis,
                                              accept_staged_read_risk=consent)
            basis = copy.deepcopy(self.basis)
            basis["stored_end_candidate"] = "0x0500"
            with self.assertRaises(ValueError):
                payload.read_payload_once(self.target, Mock(), Mock(), basis, accept_staged_read_risk=True)
            with self.assertRaises(ValueError):
                payload.read_payload_once(replace(self.target, revision="0101"), Mock(), Mock(), self.basis,
                                          accept_staged_read_risk=True)
        opened.assert_not_called()

    def test_any_failure_stops_without_later_blocks_or_recovery(self):
        calls = []
        def failed(fd, request, buffer, mutate):
            calls.append(bytes(buffer))
            raise OSError("Synthetic failure")
        with patch.object(payload, "validated_handle", side_effect=self.handle), \
                patch("fcntl.ioctl", side_effect=failed), self.assertRaises(OSError):
            payload.read_payload_once(self.target, self.record, Mock(), self.basis, accept_staged_read_risk=True)
        self.assertEqual(len(calls), 1)

    def test_strict_offline_journal_rejects_scope_changes_and_false_claims(self):
        self.record("shortcut_payload_session", identity=IDENTITY, accepted_staging_risk=True,
                    report_descriptor_hex=self.target.descriptor.hex(" "), header_basis=self.basis,
                    bases=[f"0x{base:04x}" for base in payload.PAYLOAD_BASES])
        self.collect()
        self.record("shortcut_payload_complete", **payload.describe_payload(self.data))
        encode = lambda events: b"\n".join(json.dumps(event).encode() for event in events)
        with patch("fcntl.ioctl", side_effect=AssertionError("No hardware")):
            result = payload.decode_payload_journal(encode(self.events))
        self.assertEqual(result["collected_hex"], self.data.hex(" "))
        for field, value in (("settings_commits", 1), ("behavior_verified", True),
                              ("complete_configuration_backup", True), ("collected_hex", "00 " * 96)):
            events = copy.deepcopy(self.events)
            events[-1][field] = value
            with self.assertRaises(ValueError):
                payload.decode_payload_journal(encode(events))
        for events in (self.events[:-1], self.events + [self.events[-1]]):
            with self.assertRaises(ValueError):
                payload.decode_payload_journal(encode(events))

    def test_cli_refuses_arbitrary_ranges_and_missing_risk_flags_before_enumeration(self):
        args = ["--read-shortcut-payload", "--accept-staged-read-risk", "--headers", str(HEADERS),
                "--baseline", str(BASELINE), "--capture", "/synthetic/new"]
        for variant in (args[1:], [arg for arg in args if arg != "--accept-staged-read-risk"],
                        args + ["--address", "0x460"]):
            with patch.object(payload, "enumerate_devices") as enum, contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit):
                payload.main(variant)
            enum.assert_not_called()
