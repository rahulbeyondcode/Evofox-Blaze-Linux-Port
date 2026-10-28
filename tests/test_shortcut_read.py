import contextlib
from dataclasses import replace
import errno
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from evofox_blaze import shortcut_read as read
from evofox_blaze.shortcut_capture import decode_shortcut_header_journal
from evofox_blaze.feature_read import load_baseline
from evofox_blaze.read_preview import Delay, GetFeature, SetFeature
from evofox_blaze.state_read import GET_FEATURE, IDENTITY, SET_FEATURE


BASELINE = (Path(__file__).resolve().parents[1]
            / "docs/device-captures/2026-10-23-30fa-1440-0100/probe.json")


class MetadataFixture:
    def setUp(self):
        self.target = replace(load_baseline(BASELINE)[0], path="/dev/hidraw99")
        self.blocks = {base: bytes((base + i) & 255 for i in range(8)) for base in read.HEADER_BASES}
        self.features = []
        self.selected = None
        self.events = []

    def record(self, event, **fields):
        self.events.append({"event": event, **fields})

    @contextlib.contextmanager
    def handle(self, target, record, recheck, *, writable=False):
        self.assertTrue(writable)
        recheck(target)
        record("handle_validated", identity=IDENTITY, bus=3, lock_mode="exclusive-advisory")
        yield 42

    def ioctl(self, fd, request, buffer, mutate):
        self.assertEqual(fd, 42)
        self.assertEqual(self.events[-1]["event"], "shortcut_feature_intent")
        self.features.append((request, bytes(buffer)))
        if request == GET_FEATURE:
            self.assertIsNotNone(self.selected)
            base, index = self.selected
            buffer[:] = bytes((7, self.blocks[base][index], 0, 0, 0, 0, 0, 0))
        else:
            self.assertEqual(request, SET_FEATURE)
            self.assertEqual(buffer[:2], b"\x07\x18")
            self.assertIn(buffer[2], (0, 3, 5))  # No setting commit/reset/finalize.
            base = int.from_bytes(buffer[4:6], "little")
            self.assertIn(base, (0, *read.HEADER_BASES))
            if buffer[2] == 5:
                self.selected = base, buffer[3]
            else:
                self.selected = None
            self.assertEqual(buffer[6], 0)
        return 8

    def collect(self):
        with patch.object(read, "validated_handle", side_effect=self.handle), \
                patch.object(read, "check_host"), patch("fcntl.ioctl", side_effect=self.ioctl), patch("time.sleep"):
            return read.read_headers_once(self.target, self.record, Mock(), accept_staged_read_risk=True)

    def journal(self):
        self.record("shortcut_header_session", identity=IDENTITY, accepted_staging_risk=True,
                    report_descriptor_hex=self.target.descriptor.hex(" "), length=8,
                    bases=[f"0x{base:04x}" for base in read.HEADER_BASES])
        blocks = self.collect()
        self.record("shortcut_header_complete", mode="experimental-shortcut-headers", **read.describe_headers(blocks))
        return self.events

    @staticmethod
    def encode(events):
        return b"\n".join(json.dumps(event).encode() for event in events)


class ShortcutHeaderTests(MetadataFixture, unittest.TestCase):
    def test_fixed_table_geometry_matches_the_retained_static_fixture(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/vendor-shortcut-observations.json").read_text())
        table = fixture["descriptor_table"]
        self.assertEqual(table["length"], table["entry_length"] * table["vendor_table_groups"] * table["entries_per_group"])
        self.assertEqual(read.HEADER_BASES[:4], tuple(int(value, 16) for value in fixture["header_blocks"]))
        self.assertEqual(len(read.HEADER_BASES[4:]) * 8, table["length"])
        self.assertTrue(fixture["hardware_shortcut_headers_read"])

    def test_new_metadata_capture_is_immutable_and_does_not_replace_historical_values(self):
        from evofox_blaze.shortcut_capture import decode_shortcut_header_capture
        path = BASELINE.parents[1] / "30fa-1440-0100-shortcut-headers-01/shortcut-headers.jsonl"
        result = decode_shortcut_header_capture(path)
        self.assertEqual(result["capture_sha256"], "d651e58b5be4822da18924944ce9261aefbe9dcfff8af885a71759e6a2f172e5")
        self.assertEqual(result["native_button_hex"], "21 22 23 24 23 35 00 26")
        self.assertEqual(result["macro_end_candidate"], "0x0418")
        self.assertEqual(result["stored_end_candidate"], "0x0438")
        self.assertEqual(sum(row["nonzero"] for row in result["record_descriptors"]), 3)

    def test_public_capture_auditor_rejects_unpinned_files(self):
        from tools.audit_public_capture import audit_capture
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            audit_capture(bytes(128))

    def test_only_the_source_bounded_metadata_regions_are_exposed(self):
        self.assertEqual(len(read.HEADER_BASES), 74)
        self.assertEqual(read.HEADER_BASES[:4], (8, 0x68, 0x70, 0x78))
        self.assertEqual(read.HEADER_BASES[4:], tuple(range(0xa0, 0x2d0, 8)))
        for base in (True, "8", 0, 0x10, 0xa1, 0x2d0, 0x400, 0xf20):
            with self.subTest(base=base), self.assertRaises(ValueError):
                read.header_read_steps(base)

    def test_each_block_matches_the_known_reader_without_a_commit(self):
        for base in read.HEADER_BASES:
            steps = read.header_read_steps(base)
            sets = [step.report for step in steps if isinstance(step, SetFeature)]
            self.assertEqual(len(sets), 18)
            self.assertEqual(sum(isinstance(step, GetFeature) for step in steps), 8)
            self.assertEqual(sum(step.milliseconds for step in steps if isinstance(step, Delay)), 36)
            self.assertEqual(sets[0], bytes((7, 0x18, 3, 0, base & 255, base >> 8, 0, 7)))
            self.assertEqual(sets[8], bytes((7, 0x18, 0, 0, base & 255, base >> 8, 0, 0)))
            self.assertEqual(sets[-1], bytes.fromhex("07 18 00 00 00 00 00 00"))
            self.assertTrue(all(frame[2] in (0, 3, 5) and frame[6] == 0 for frame in sets))

    def test_complete_read_returns_exact_bytes_and_operation_counts(self):
        result = self.collect()
        self.assertEqual(result, self.blocks)
        self.assertEqual(sum(request == SET_FEATURE for request, _ in self.features), 1332)
        self.assertEqual(sum(request == GET_FEATURE for request, _ in self.features), 592)
        description = read.describe_headers(result)
        self.assertEqual(len(description["record_descriptors"]), 56)
        self.assertFalse(description["record_payloads_read"])
        self.assertFalse(description["complete_configuration_backup"])
        self.assertFalse(description["behavior_verified"])

    def test_read_requires_strict_optin_and_exact_identity_before_open(self):
        with patch.object(read, "validated_handle") as opened, patch.object(read, "check_host"):
            for value in (False, 1, None):
                with self.assertRaises(ValueError):
                    read.read_headers_once(self.target, Mock(), Mock(), accept_staged_read_risk=value)
            with self.assertRaises(ValueError):
                read.read_headers_once(replace(self.target, revision="0101"), Mock(), Mock(),
                                       accept_staged_read_risk=True)
        opened.assert_not_called()

    def test_failed_request_or_log_stops_without_retry_or_later_blocks(self):
        for fail_after in (1, 9, 10, 26, 27, 1924):
            self.events.clear()
            self.features.clear()
            original = self.ioctl
            def failed(fd, request, buffer, mutate):
                result = original(fd, request, buffer, mutate)
                if len(self.features) == fail_after:
                    raise OSError(errno.EPIPE, "synthetic failure")
                return result
            with self.subTest(ordinal=fail_after), patch.object(read, "validated_handle", side_effect=self.handle), \
                    patch("fcntl.ioctl", side_effect=failed), patch("time.sleep"), self.assertRaises(OSError):
                read.read_headers_once(self.target, self.record, Mock(), accept_staged_read_risk=True)
            self.assertEqual(len(self.features), fail_after)

    def test_every_intent_or_result_log_failure_stops_the_block_immediately(self):
        for event_kind in ("shortcut_feature_intent", "shortcut_feature_result"):
            for ordinal in range(1, 27):
                calls = []
                def record(event, **fields):
                    if event == event_kind and fields["ordinal"] == ordinal:
                        raise OSError(errno.ENOSPC, "synthetic disk full")
                def ioctl(fd, request, buffer, mutate):
                    calls.append(bytes(buffer))
                    return 8
                with self.subTest(kind=event_kind, ordinal=ordinal), patch("fcntl.ioctl", side_effect=ioctl), \
                        patch("time.sleep"), self.assertRaises(OSError):
                    read._read_header_on_handle(42, 0xa0, record)
                self.assertEqual(len(calls), ordinal - (event_kind == "shortcut_feature_intent"))

    def test_bad_short_boolean_changed_and_wrong_id_results_fail_closed(self):
        for ordinal in (1, 10, 11, 26):
            for failure in (0, 7, 9, True, "changed", "wrong-id"):
                calls = []
                def ioctl(fd, request, buffer, mutate):
                    calls.append(bytes(buffer))
                    if len(calls) == ordinal:
                        if failure == "changed":
                            buffer[0] = 0
                            return 8
                        if failure == "wrong-id":
                            buffer[0] = 6
                            return 8
                        return failure
                    return 8
                with self.subTest(ordinal=ordinal, failure=failure), patch("fcntl.ioctl", side_effect=ioctl), \
                        patch("time.sleep"), self.assertRaises(ValueError):
                    read._read_header_on_handle(42, 0xa0, Mock())
                self.assertEqual(len(calls), ordinal)

    def test_descriptor_arithmetic_spans_block_boundaries_without_losing_raw_bits(self):
        blocks = {base: bytes(8) for base in read.HEADER_BASES}
        table = bytearray(560)
        data = bytes.fromhex("03 81 ff b7 00 28 c4 41 92 77")
        table[30:40] = data  # Slot 4 crosses the 00b8/00c0 boundary.
        for index, base in enumerate(read.HEADER_BASES[4:]):
            blocks[base] = bytes(table[index * 8:index * 8 + 8])
        descriptor = read.describe_headers(blocks)["record_descriptors"][3]
        self.assertEqual(descriptor["native_slot"], 4)
        self.assertEqual(descriptor["raw_hex"], data.hex(" "))
        self.assertEqual(descriptor["record_pointer_candidate"], "0x0428")
        self.assertEqual(descriptor["event_count_candidate"], 129)
        self.assertEqual(descriptor["tick_milliseconds_candidate"], 4)
        self.assertEqual(descriptor["repeat_flags_candidate"], [True, True, True, True])


class ShortcutHeaderCaptureTests(MetadataFixture, unittest.TestCase):
    def test_saved_inspection_is_offline_and_not_a_payload_backup(self):
        events = self.journal()
        with patch("fcntl.ioctl", side_effect=AssertionError("No device")), \
                patch("evofox_blaze.probe.enumerate_devices", side_effect=AssertionError("No enumeration")):
            result = decode_shortcut_header_journal(self.encode(events))
        self.assertEqual(result["set_feature_count"], 1332)
        self.assertEqual(result["get_feature_count"], 592)
        self.assertEqual(result["settings_commits"], 0)
        self.assertFalse(result["record_payloads_read"])

    def test_extra_partial_wrong_scope_and_false_completion_are_rejected(self):
        import copy
        source = self.journal()
        for events in (source[:-1], source + [source[-1]], source[1:]):
            with self.assertRaises((KeyError, ValueError)):
                decode_shortcut_header_journal(self.encode(events))
        for field, value in (("record_payloads_read", True), ("complete_configuration_backup", True),
                              ("behavior_verified", True), ("native_button_hex", "00 " * 8)):
            events = copy.deepcopy(source)
            events[-1][field] = value
            with self.assertRaises(ValueError):
                decode_shortcut_header_journal(self.encode(events))
        for field, value in (("ordinal", True), ("buffer_hex", "07 18 09 00 a0 00 00 07")):
            events = copy.deepcopy(source)
            next(row for row in events if row["event"] == "shortcut_feature_intent")[field] = value
            with self.assertRaises(ValueError):
                decode_shortcut_header_journal(self.encode(events))
        events = copy.deepcopy(source)
        events[0]["bases"] += ["0x0400"]
        with self.assertRaises(ValueError):
            decode_shortcut_header_journal(self.encode(events))

    def test_cli_missing_optins_and_arbitrary_ranges_fail_before_enumeration(self):
        args = ["--read-shortcut-headers", "--accept-staged-read-risk", "--baseline", str(BASELINE),
                "--capture", "/synthetic/new"]
        for variant in (args[1:], [arg for arg in args if arg != "--accept-staged-read-risk"],
                        args + ["--address", "0x400"], args + ["--length", "16"]):
            with patch.object(read, "enumerate_devices") as enum, contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit):
                read.main(variant)
            enum.assert_not_called()

    def test_cli_exclusive_private_destination_and_summary(self):
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as temporary:
            capture = Path(temporary) / "headers"
            args = ["--read-shortcut-headers", "--accept-staged-read-risk", "--baseline", str(BASELINE),
                    "--capture", str(capture)]
            with patch.object(read, "enumerate_devices", return_value=[]), \
                    patch.object(read, "select_target", return_value=self.target), patch.object(read, "check_host"), \
                    patch.object(read, "read_headers_once", return_value=self.blocks) as collect, \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(read.main(args), 0)
            self.assertEqual(json.loads(out.getvalue())["settings_commits"], 0)
            self.assertEqual((capture / "shortcut-headers.jsonl").stat().st_mode & 0o777, 0o600)
            self.assertEqual(capture.stat().st_mode & 0o777, 0o700)
            self.assertTrue(collect.call_args.kwargs["accept_staged_read_risk"])
            with patch.object(read, "enumerate_devices", return_value=[]), \
                    patch.object(read, "select_target", return_value=self.target), \
                    patch.object(read, "read_headers_once") as collect, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(read.main(args), 1)
            collect.assert_not_called()
