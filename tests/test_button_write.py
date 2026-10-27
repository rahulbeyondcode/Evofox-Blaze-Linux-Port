import contextlib
import copy
from dataclasses import replace
import errno
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from evofox_blaze import button_write as write
from evofox_blaze.button_config_capture import decode_button_config_capture, decode_button_config_journal
from evofox_blaze.feature_read import Journal, load_baseline
from evofox_blaze.state_read import GET_FEATURE, IDENTITY, SET_FEATURE


BASELINE = (Path(__file__).resolve().parents[1]
            / "docs/device-captures/2026-10-23-30fa-1440-0100/probe.json")
ORIGINAL = bytes.fromhex("21 22 23 2e 2e 35 00 26")
CHANGED = bytes.fromhex("21 22 23 24 25 35 00 26")
ASSIGNMENTS = {4: "back", 5: "forward"}


class FakeNativeButtons:
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.capture = self.root / "change"
        baseline, _ = load_baseline(BASELINE)
        self.target = replace(baseline, path="/dev/hidraw99")
        self.memory = ORIGINAL
        self.staged = {}
        self.index = None
        self.features = []
        self.commits = 0
        self.stall_commit = False
        self.bad_readback = False

    @contextlib.contextmanager
    def handle(self, target, record, recheck, *, writable=False):
        self.assertTrue(writable)
        self.assertEqual(target.identity(), IDENTITY)
        recheck(target)
        record("handle_validated", identity=IDENTITY, bus=3, lock_mode="exclusive-advisory")
        yield 42

    def ioctl(self, fd, request, buffer, mutate):
        self.assertEqual(fd, 42)
        latest = json.loads((self.capture / "button-configuration.jsonl").read_text().splitlines()[-1])
        self.assertIn(latest["event"], ("button_feature_intent", "button_write_intent"))
        self.features.append((request, bytes(buffer)))
        if request == GET_FEATURE:
            self.assertIsNotNone(self.index)
            value = self.memory[self.index]
            if self.bad_readback and self.commits:
                value ^= 1
            buffer[:] = bytes((7, value, 0, 0, 0, 0, 0, 0))
            return 8
        self.assertEqual(request, SET_FEATURE)
        self.assertEqual(buffer[:2], b"\x07\x18")
        self.assertIn(buffer[2], (0, 3, 5, 9))
        self.assertIn(int.from_bytes(buffer[4:6], "little"), (0, 8))
        operation, index, value = buffer[2], buffer[3], buffer[6]
        if operation == 3:
            if value:
                self.assertTrue((self.capture / "button-backup.json").is_file())
                write.load_backup(self.capture / "button-backup.json")
            self.staged[index] = value
        elif operation == 5:
            self.index = index
        elif operation == 0:
            self.staged.clear()
        elif operation == 9:
            self.assertEqual(buffer.hex(" "), "07 18 09 00 08 00 00 07")
            self.commits += 1
            self.memory = bytes(self.staged[i] for i in range(8))
            if self.stall_commit:
                raise OSError(errno.EPIPE, "synthetic ambiguous commit")
        return 8

    def change(self, assignments=None, *, restore_from=None, recheck=None):
        with patch.object(write, "validated_handle", side_effect=self.handle), \
                patch.object(write, "check_host"), patch("fcntl.ioctl", side_effect=self.ioctl), \
                patch("time.sleep"):
            return write.change_buttons(self.target, assignments if assignments is not None else
                                        (None if restore_from is not None else ASSIGNMENTS),
                                        self.capture, recheck or Mock(), accept_write_risk=True,
                                        restore_from=restore_from)


class ButtonTransactionTests(FakeNativeButtons, unittest.TestCase):
    def test_fresh_read_backup_one_commit_and_full_readback(self):
        result = self.change()
        self.assertEqual(self.memory, CHANGED)
        self.assertEqual(self.commits, 1)
        self.assertEqual(sum(r == SET_FEATURE for r, _ in self.features), 46)
        self.assertEqual(sum(r == GET_FEATURE for r, _ in self.features), 16)
        self.assertEqual(result["outcome"], "written-and-read-back")
        self.assertFalse(result["behavior_verified"])
        saved, before, after, assignments = write.load_backup(self.capture / "button-backup.json")
        self.assertEqual((before, after, assignments), (ORIGINAL, CHANGED, ASSIGNMENTS))
        self.assertFalse(saved["extension_records_modified"])
        self.assertEqual((self.capture / "button-backup.json").stat().st_mode & 0o777, 0o600)
        result = decode_button_config_capture(self.capture / "button-configuration.jsonl")
        self.assertEqual(result["after_hex"], CHANGED.hex(" "))

    def test_exact_restore_recovers_opaque_links_without_extension_writes(self):
        self.change()
        backup = self.capture / "button-backup.json"
        self.capture = self.root / "restore"
        self.features.clear()
        result = self.change(restore_from=backup)
        self.assertEqual(self.memory, ORIGINAL)
        self.assertEqual(result["after_hex"], ORIGINAL.hex(" "))
        self.assertFalse(result["extension_records_modified"])
        inspected = decode_button_config_capture(self.capture / "button-configuration.jsonl")
        self.assertEqual(inspected["operation"], "restore")
        self.assertEqual(inspected["after_hex"], ORIGINAL.hex(" "))

    def test_already_matching_change_or_restore_performs_no_commit(self):
        self.memory = CHANGED
        result = self.change()
        self.assertEqual(result["outcome"], "no-change")
        self.assertFalse((self.capture / "button-backup.json").exists())
        self.assertEqual(self.commits, 0)
        self.assertEqual(len(self.features), 26)
        decode_button_config_capture(self.capture / "button-configuration.jsonl")
        self.memory = ORIGINAL
        self.capture = self.root / "first"
        self.change()
        backup = self.capture / "button-backup.json"
        self.memory = ORIGINAL
        self.capture = self.root / "already-restored"
        result = self.change(restore_from=backup)
        self.assertEqual(result["outcome"], "no-change")
        decode_button_config_capture(self.capture / "button-configuration.jsonl")

    def test_restore_refuses_intervening_edits_before_any_commit(self):
        self.change()
        backup = self.capture / "button-backup.json"
        self.memory = bytes.fromhex("21 22 23 24 25 35 01 26")
        self.capture = self.root / "intervening"
        self.features.clear()
        with self.assertRaisesRegex(ValueError, "intervening"):
            self.change(restore_from=backup)
        self.assertEqual(self.commits, 1)
        self.assertEqual(len(self.features), 26)

    def test_failed_backup_prevents_all_setting_data_frames(self):
        with patch.object(write, "_save_backup", side_effect=OSError(errno.ENOSPC, "synthetic disk full")), \
                self.assertRaises(OSError):
            self.change()
        self.assertEqual(self.commits, 0)
        self.assertEqual(self.memory, ORIGINAL)
        self.assertEqual(len(self.features), 26)

    def test_failed_write_intent_or_result_stops_at_that_operation(self):
        original_record = Journal.record
        for event_kind in ("button_write_intent", "button_write_result"):
            for ordinal in range(1, 11):
                self.capture = self.root / f"{event_kind}-{ordinal}"
                self.memory = ORIGINAL
                self.features.clear()
                self.staged.clear()
                def record(journal, event, **fields):
                    if event == event_kind and fields["ordinal"] == ordinal:
                        raise OSError(errno.ENOSPC, "synthetic disk full")
                    return original_record(journal, event, **fields)
                with self.subTest(kind=event_kind, ordinal=ordinal), \
                        patch.object(Journal, "record", record), self.assertRaises(OSError):
                    self.change()
                self.assertEqual(len(self.features), 26 + ordinal - (event_kind == "button_write_intent"))

    def test_ambiguous_commit_has_no_retry_readback_or_rollback(self):
        self.stall_commit = True
        with self.assertRaises(OSError):
            self.change()
        self.assertEqual(self.commits, 1)
        self.assertEqual(len(self.features), 35)
        self.assertEqual(self.memory, CHANGED)
        self.assertTrue((self.capture / "button-backup.json").exists())

    def test_wrong_readback_stops_without_recovery(self):
        self.bad_readback = True
        with self.assertRaisesRegex(ValueError, "readback"):
            self.change()
        self.assertEqual(self.commits, 1)
        self.assertEqual(self.memory, CHANGED)
        self.assertEqual(len(self.features), 62)

    def test_short_boolean_changed_or_failed_writer_completion_never_retries(self):
        for ordinal in (1, 9, 10):
            for failure in (0, 7, 9, True, "changed", OSError(errno.EPIPE, "synthetic stall")):
                calls = []
                def ioctl(fd, request, buffer, mutate):
                    calls.append(bytes(buffer))
                    if len(calls) == ordinal:
                        if isinstance(failure, Exception):
                            raise failure
                        if failure == "changed":
                            buffer[6] ^= 1
                            return 8
                        return failure
                    return 8
                with self.subTest(ordinal=ordinal, failure=failure), patch("fcntl.ioctl", side_effect=ioctl), \
                        patch("time.sleep"), self.assertRaises((OSError, ValueError)):
                    write._write_buttons_on_handle(42, CHANGED, Mock())
                self.assertEqual(len(calls), ordinal)

    def test_no_optin_wrong_target_or_invalid_request_does_not_open(self):
        with patch.object(write, "validated_handle") as opened:
            for consent in (False, 1, None):
                with self.assertRaises(ValueError):
                    write.change_buttons(self.target, ASSIGNMENTS, self.capture, Mock(), accept_write_risk=consent)
            with self.assertRaises(ValueError):
                write.change_buttons(replace(self.target, revision="0101"), ASSIGNMENTS, self.capture, Mock(), accept_write_risk=True)
            for assignments in ({}, None, {7: "back"}, {True: "left"}, {4: "keyboard"}):
                with self.assertRaises(ValueError):
                    write.change_buttons(self.target, assignments, self.capture, Mock(), accept_write_risk=True)
        opened.assert_not_called()

    def test_existing_destination_or_tampered_backup_is_refused_before_open(self):
        self.capture.mkdir()
        with patch.object(write, "validated_handle") as opened, self.assertRaises(FileExistsError):
            write.change_buttons(self.target, ASSIGNMENTS, self.capture, Mock(), accept_write_risk=True)
        opened.assert_not_called()
        self.capture = self.root / "original"
        self.change()
        path = self.capture / "button-backup.json"
        saved = json.loads(path.read_text())
        saved["after_hex"] = ORIGINAL.hex(" ")
        path.write_text(json.dumps(saved))
        with patch.object(write, "validated_handle") as opened, self.assertRaises(ValueError):
            write.change_buttons(self.target, None, self.root / "bad", Mock(), accept_write_risk=True, restore_from=path)
        opened.assert_not_called()

    def test_cli_rejects_invalid_duplicates_and_missing_optin_before_enumeration(self):
        args = ["--assign", "4=back", "--accept-write-risk", "--baseline", str(BASELINE), "--capture", str(self.capture)]
        variations = ([a for a in args if a != "--accept-write-risk"], args + ["--address", "0x10"],
                      args + ["--assign", "4=forward"], args + ["--assign", "9=back"],
                      args + ["--assign", "five=back"], args + ["--assign", "5=Ctrl+C"])
        for variant in variations:
            with patch.object(write, "enumerate_devices") as enum, contextlib.redirect_stderr(io.StringIO()):
                try:
                    result = write.main(variant)
                except SystemExit as error:
                    self.assertNotEqual(error.code, 0)
                else:
                    self.assertEqual(result, 1)
            enum.assert_not_called()


class ButtonConfigurationCaptureTests(FakeNativeButtons, unittest.TestCase):
    def events(self):
        self.change()
        return [json.loads(line) for line in (self.capture / "button-configuration.jsonl").read_text().splitlines()]

    def decode(self, events):
        return decode_button_config_journal(b"\n".join(json.dumps(e).encode() for e in events))

    def test_partial_extra_wrong_phase_and_false_completion_are_refused(self):
        source = self.events()
        for events in (source[:-1], source + [source[-1]], source[:4] + [{"event": "button_config_failed"}]):
            with self.assertRaises(ValueError):
                self.decode(events)
        for field, value in (("behavior_verified", True), ("extension_records_modified", True),
                             ("complete_configuration_backup", True), ("after_hex", ORIGINAL.hex(" "))):
            events = copy.deepcopy(source)
            events[-1][field] = value
            with self.assertRaises(ValueError):
                self.decode(events)
        events = copy.deepcopy(source)
        next(e for e in events if e["event"] == "button_feature_intent")["phase"] = "verify"
        with self.assertRaises(ValueError):
            self.decode(events)

    def test_unowned_byte_writes_or_tampered_backup_are_not_validated(self):
        source = self.events()
        for field, value in (("frame_hex", "07 18 03 00 10 00 21 07"), ("ordinal", True)):
            events = copy.deepcopy(source)
            next(e for e in events if e["event"] == "button_write_intent")[field] = value
            with self.assertRaises(ValueError):
                self.decode(events)
        events = copy.deepcopy(source)
        next(e for e in events if e["event"] == "button_backup_durable")["backup"]["before_hex"] = "00 " * 8
        with self.assertRaises(ValueError):
            self.decode(events)
        events = copy.deepcopy(source)
        events[0]["assignments"] = [{"slot": 4, "action": "left"}]
        with self.assertRaises(ValueError):
            self.decode(events)

    def test_literal_writer_shape_matches_source_and_public_capture(self):
        frames = write.button_write_frames(CHANGED)
        self.assertEqual(frames[:8], tuple(bytes((7, 0x18, 3, i, 8, 0, b, 7)) for i, b in enumerate(CHANGED)))
        self.assertEqual(frames[8:], (bytes.fromhex("07 18 09 00 08 00 00 07"),
                                            bytes.fromhex("07 18 00 00 08 00 00 00")))
        for invalid in (bytes(7), bytearray(CHANGED), "21 " * 8):
            with self.assertRaises(ValueError):
                write.button_write_frames(invalid)

    def test_live_remap_evidence_and_original_backup_remain_unchanged(self):
        directory = BASELINE.parents[1] / "30fa-1440-0100-button-remap-01"
        self.assertEqual(hashlib.sha256((directory / "button-configuration.jsonl").read_bytes()).hexdigest(),
                         "a8e271a7ff4ca8b1fb2255470f24e462b9b94f23466b3dab6df6c495d3783229")
        self.assertEqual(hashlib.sha256((directory / "button-backup.json").read_bytes()).hexdigest(),
                         "9b2d6e5d36a8cb84ade22d043d11051d273d60218ee20619b089e2adfb050d8b")
        inspected = decode_button_config_capture(directory / "button-configuration.jsonl")
        self.assertEqual(inspected["before_hex"], ORIGINAL.hex(" "))
        self.assertEqual(inspected["after_hex"], CHANGED.hex(" "))
        self.assertFalse(inspected["behavior_verified"])
        report = json.loads((directory / "behavior-validation.json").read_text())
        self.assertTrue(report["user_reported_back_and_forward_working"])
        self.assertEqual(report["user_selected_test_result"], "Works after replug")
        self.assertFalse(report["input_monitoring_performed_by_agent"])
