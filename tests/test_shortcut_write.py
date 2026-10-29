import contextlib
import copy
from dataclasses import replace
import errno
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from evofox_blaze import shortcut_write as write
from evofox_blaze.feature_read import Journal, load_baseline
from evofox_blaze.shortcut_capture import decode_shortcut_header_capture
from evofox_blaze.shortcut_config_capture import decode_shortcut_config_capture, decode_shortcut_config_journal
from evofox_blaze.shortcut_payload_read import decode_payload_capture
from evofox_blaze.shortcut_plan import (Fragment, POOL, active_shortcuts, header_owners, payload_bases,
                                       plan_change, snapshot_rows)
from evofox_blaze.shortcuts import MODIFIER_LABELS, Shortcut
from evofox_blaze.state_read import GET_FEATURE, IDENTITY, SET_FEATURE


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/device-captures/2026-10-23-30fa-1440-0100/probe.json"
HEADERS = ROOT / "docs/device-captures/30fa-1440-0100-shortcut-headers-01/shortcut-headers.jsonl"
PAYLOAD = ROOT / "docs/device-captures/30fa-1440-0100-shortcut-payload-01/shortcut-payload.jsonl"


def initial_blocks():
    header = decode_shortcut_header_capture(HEADERS)
    blocks = {int(row["base"], 16): bytes.fromhex(row["collected_hex"]) for row in header["blocks"]}
    raw = bytes.fromhex(decode_payload_capture(PAYLOAD)["collected_hex"])
    for offset in range(0, len(raw), 8):
        blocks[0x400 + offset] = raw[offset:offset + 8]
    return blocks


class ShortcutPlanTests(unittest.TestCase):
    def test_first_field_test_rejects_a_changed_native_table_or_an_existing_tail_owner(self):
        before = initial_blocks()
        write.guard_first_tail_test(before)
        changed = dict(before)
        changed[8] = bytes.fromhex("21 22 23 24 25 35 00 26")
        with self.assertRaises(ValueError):
            write.guard_first_tail_test(changed)
        after, _ = plan_change(before, {}, {5: Shortcut("F13")})
        with self.assertRaises(ValueError):
            write.guard_first_tail_test(after)

    def test_original_bytes_are_retained_and_only_owned_fields_change(self):
        before = initial_blocks()
        after, fragments = plan_change(before, {}, {5: Shortcut("F13")})
        self.assertEqual([fragment.kind for fragment in fragments], ["record", "descriptors", "buttons"])
        self.assertEqual([(fragment.base, len(fragment.data)) for fragment in fragments], [(0x438, 8), (0xc8, 8), (8, 8)])
        self.assertEqual(after[8].hex(" "), "21 22 23 24 2e 35 00 26")
        self.assertEqual(after[0x438].hex(" "), "01 00 84 68 00 00 00 00")
        for base in before:
            if base not in (8, 0xc8, 0x438):
                self.assertEqual(after[base], before[base], hex(base))
        self.assertEqual(after[0x440][0], 0xff)  # Candidate tail was not assumed blank.
        self.assertEqual(active_shortcuts(after), {5: Shortcut("F13")})

    def test_actual_old_chords_decode_without_altering_their_original_payload(self):
        before = initial_blocks()
        before[8] = bytes.fromhex("21 22 23 2e 2e 35 00 26")
        self.assertEqual(active_shortcuts(before), {
            4: Shortcut("Left", ("Control_L", "Super_L")),
            5: Shortcut("Right", ("Control_L", "Super_L")),
        })
        after, fragments = plan_change(before, {}, {5: Shortcut("Right", ("Control_L", "Super_L"))})
        self.assertEqual(after, before)
        self.assertEqual(fragments, ())

    def test_unknown_layout_shared_descriptors_and_slot_nine_are_refused(self):
        before = initial_blocks()
        for base, data in ((0x68, bytes(8)), (0x78, bytes(8)), (0xf0, bytes(8))):
            changed = dict(before)
            changed[base] = data
            with self.subTest(base=base), self.assertRaises(ValueError):
                plan_change(changed, {}, {5: Shortcut("F13")})
        with self.assertRaises(ValueError):
            plan_change(before, {}, {9: Shortcut("F13")})
        with self.assertRaises(ValueError):
            plan_change(before, {5: "back"}, {5: Shortcut("F13")})

    def test_last_left_click_retention_is_checked_on_the_combined_final_table(self):
        before = initial_blocks()
        with self.assertRaisesRegex(ValueError, "Left Click"):
            plan_change(before, {}, {1: Shortcut("F13")})
        after, _ = plan_change(before, {2: "left"}, {1: Shortcut("F13")})
        self.assertEqual(after[8][:2], bytes.fromhex("2e 21"))


class FakeShortcutMouse:
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir="/tmp/opencode")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.capture = self.root / "change"
        self.target = replace(load_baseline(BASELINE)[0], path="/dev/hidraw99")
        initial = initial_blocks()
        self.memory = {base + index: value for base, data in initial.items() for index, value in enumerate(data)}
        for address in range(0x460, 0x550):
            self.memory[address] = address & 255  # More unallocated space is opaque, not invented zeros.
        self.original_memory = dict(self.memory)
        self.staged = {}
        self.selected = None
        self.features = []
        self.commits = 0
        self.last_event = None
        self.write_frames = []
        self.stall_commit = 0
        self.corrupt_readback = False

    @contextlib.contextmanager
    def handle(self, target, record, recheck, *, writable=False):
        self.assertTrue(writable)
        self.assertEqual(target.identity(), IDENTITY)
        recheck(target)
        record("handle_validated", identity=IDENTITY, bus=3)
        yield 42

    def ioctl(self, fd, request, buffer, mutate):
        self.assertEqual(fd, 42)
        self.assertIn(self.last_event[0], ("shortcut_feature_intent", "shortcut_write_intent"))
        self.features.append((request, bytes(buffer)))
        if request == GET_FEATURE:
            value = self.memory[self.selected]
            if self.corrupt_readback and self.commits:
                value ^= 1
            buffer[:] = bytes((7, value, 0, 0, 0, 0, 0, 0))
            return 8
        self.assertEqual(request, SET_FEATURE)
        self.assertEqual(buffer[:2], b"\x07\x18")
        self.assertIn(buffer[2], (0, 3, 5, 9))
        base = int.from_bytes(buffer[4:6], "little")
        if self.last_event[0] == "shortcut_write_intent":
            self.assertTrue((self.capture / "shortcut-backup.json").is_file())
            write.load_backup(self.capture / "shortcut-backup.json")
            self.write_frames.append(bytes(buffer))
        else:
            self.assertNotEqual(buffer[2], 9)
            self.assertEqual(buffer[6], 0)
        if buffer[2] == 3:
            self.staged[(base, buffer[3])] = buffer[6]
        elif buffer[2] == 5:
            self.selected = base + buffer[3]
        elif buffer[2] == 0:
            self.staged.clear()
        elif buffer[2] == 9:
            self.commits += 1
            for index in range(buffer[7] + 1):
                self.memory[base + index] = self.staged[(base, index)]
            if self.stall_commit == self.commits:
                raise OSError(errno.EPIPE, "Synthetic uncertain commit")
        return 8

    def change(self, shortcuts=None, assignments=None, restore_from=None):
        original_record = Journal.record
        def record(journal, event, **fields):
            self.last_event = event, fields
            return original_record(journal, event, **fields)
        with patch.object(write, "validated_handle", side_effect=self.handle), patch.object(write, "check_host"), \
                patch.object(Journal, "record", record), patch("fcntl.ioctl", side_effect=self.ioctl), \
                patch("time.sleep"), patch("os.fsync"):
            return write.change_shortcuts(self.target, assignments or {},
                                           shortcuts if shortcuts is not None else ({} if restore_from else {5: Shortcut("F13")}),
                                           self.capture, Mock(), accept_write_risk=True, restore_from=restore_from)


class ShortcutTransactionTests(FakeShortcutMouse, unittest.TestCase):
    def test_fresh_backup_minimal_writes_and_complete_readback(self):
        result = self.change()
        self.assertEqual(result["settings_commits"], 3)
        self.assertEqual(self.commits, 3)
        self.assertEqual(result["set_feature_count"], 3126)
        self.assertEqual(result["get_feature_count"], 1376)
        self.assertEqual(sum(request == SET_FEATURE for request, _ in self.features), result["set_feature_count"])
        self.assertEqual(sum(request == GET_FEATURE for request, _ in self.features), result["get_feature_count"])
        self.assertFalse(result["behavior_verified"])
        self.assertFalse(result["allocation_metadata_modified"])
        self.assertEqual(result["verified_shortcuts"], [{"slot": 5, "key": "F13", "modifiers": []}])
        self.assertEqual((self.capture / "shortcut-backup.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(bytes(self.memory[i] for i in range(0x400, 0x438)),
                         bytes(self.original_memory[i] for i in range(0x400, 0x438)))
        self.assertEqual(self.memory[0x440], 0xff)
        inspected = decode_shortcut_config_capture(self.capture / "shortcut-configuration.jsonl")
        self.assertEqual(inspected["verified_shortcuts"], result["verified_shortcuts"])

    def test_explicit_restore_recovers_all_original_bytes_and_already_restored_is_no_change(self):
        self.change()
        backup = self.capture / "shortcut-backup.json"
        self.capture = self.root / "restore"
        result = self.change(restore_from=backup)
        self.assertEqual(self.memory, self.original_memory)
        self.assertEqual(result["operation"], "restore")
        inspected = decode_shortcut_config_capture(self.capture / "shortcut-configuration.jsonl")
        self.assertEqual(inspected["operation"], "restore")
        self.capture = self.root / "already-restored"
        result = self.change(restore_from=backup)
        self.assertEqual(result["outcome"], "no-change")
        decode_shortcut_config_capture(self.capture / "shortcut-configuration.jsonl")

    def test_identical_request_does_not_write_and_keeps_the_verified_shortcut(self):
        self.change()
        self.capture = self.root / "no-change"
        self.write_frames.clear()
        result = self.change()
        self.assertEqual(result["outcome"], "no-change")
        self.assertEqual(self.write_frames, [])
        self.assertFalse((self.capture / "shortcut-backup.json").exists())
        decode_shortcut_config_capture(self.capture / "shortcut-configuration.jsonl")

    def test_multiple_rows_use_unshared_slots_and_native_changes_are_not_omitted(self):
        result = self.change({4: Shortcut("k", ("Control_L",)), 5: Shortcut("F13")}, {8: "middle"})
        self.assertEqual(result["collected_hex"], "21 22 23 2e 2e 35 00 22")
        self.assertEqual(result["verified_shortcuts"], [{"slot": 4, "key": "k", "modifiers": ["Control_L"]},
                                                       {"slot": 5, "key": "F13", "modifiers": []}])
        decode_shortcut_config_capture(self.capture / "shortcut-configuration.jsonl")

    def test_largest_supported_chord_uses_24_byte_record_with_all_modifiers(self):
        result = self.change({5: Shortcut("F24", tuple(MODIFIER_LABELS))})
        self.assertEqual(result["verified_shortcuts"][0]["key"], "F24")
        self.assertEqual(len(result["verified_shortcuts"][0]["modifiers"]), 8)
        decode_shortcut_config_capture(self.capture / "shortcut-configuration.jsonl")

    def test_failed_backup_or_unknown_layout_sends_no_setting_data(self):
        with patch.object(write, "_save_backup", side_effect=OSError(errno.ENOSPC, "Synthetic disk full")), \
                self.assertRaises(OSError):
            self.change()
        self.assertEqual(self.write_frames, [])
        self.capture = self.root / "unknown-layout"
        self.memory[0x6e] = 0
        with self.assertRaisesRegex(ValueError, "allocation layout"):
            self.change()
        self.assertEqual(self.write_frames, [])

    def test_uncertain_commit_stops_and_explicit_restore_accepts_only_recorded_prefix_states(self):
        self.stall_commit = 1
        with self.assertRaises(OSError):
            self.change()
        self.assertEqual(self.commits, 1)
        self.assertEqual(len(self.write_frames), 9)
        backup = self.capture / "shortcut-backup.json"
        self.capture = self.root / "prefix-restore"
        self.stall_commit = 0
        self.change(restore_from=backup)
        self.assertEqual(self.memory, self.original_memory)
        decode_shortcut_config_capture(self.capture / "shortcut-configuration.jsonl")

    def test_intervening_change_or_bad_readback_does_not_trigger_recovery(self):
        self.change()
        backup = self.capture / "shortcut-backup.json"
        self.capture = self.root / "intervening"
        self.memory[9] = 0x23
        self.write_frames.clear()
        with self.assertRaisesRegex(ValueError, "intervening"):
            self.change(restore_from=backup)
        self.assertEqual(self.write_frames, [])
        self.memory = dict(self.original_memory)
        self.commits = 0
        self.capture = self.root / "bad-readback"
        self.corrupt_readback = True
        with self.assertRaises(ValueError):
            self.change()
        self.assertEqual(self.commits, 3)  # No extra rollback/retry commit.

    def test_no_consent_wrong_identity_or_bad_request_fails_before_open(self):
        with patch.object(write, "validated_handle") as opened, patch.object(write, "check_host"):
            for consent in (False, 1, None):
                with self.assertRaises(ValueError):
                    write.change_shortcuts(self.target, {}, {5: Shortcut("F13")}, self.capture, Mock(),
                                           accept_write_risk=consent)
            with self.assertRaises(ValueError):
                write.change_shortcuts(replace(self.target, revision="0101"), {}, {5: Shortcut("F13")},
                                       self.capture, Mock(), accept_write_risk=True)
            with self.assertRaises(ValueError):
                write.change_shortcuts(self.target, {}, {9: Shortcut("F13")}, self.capture, Mock(), accept_write_risk=True)
        opened.assert_not_called()

    def test_saved_verification_rejects_extra_events_wrong_frames_and_false_claims(self):
        self.change()
        source = [json.loads(line) for line in (self.capture / "shortcut-configuration.jsonl").read_text().splitlines()]
        encode = lambda events: b"\n".join(json.dumps(event).encode() for event in events)
        for field, value in (("behavior_verified", True), ("allocation_metadata_modified", True),
                              ("collected_hex", "00 " * 8), ("settings_commits", 1)):
            events = copy.deepcopy(source)
            events[-1][field] = value
            with self.assertRaises(ValueError):
                decode_shortcut_config_journal(encode(events))
        events = copy.deepcopy(source)
        next(event for event in events if event["event"] == "shortcut_write_intent")["frame_hex"] = "07 18 09 00 00 00 00 00"
        with self.assertRaises(ValueError):
            decode_shortcut_config_journal(encode(events))
        for events in (source[:-1], source + [source[-1]]):
            with self.assertRaises(ValueError):
                decode_shortcut_config_journal(encode(events))


class ShortcutWriterFramesTests(unittest.TestCase):
    def test_short_changed_boolean_and_failed_completions_never_retry(self):
        fragment = Fragment("record", 0x438, bytes.fromhex("01 00 84 68 00 00 00 00"))
        for ordinal in (1, 9, 10):
            for failure in (0, 7, 9, True, "changed", OSError(errno.EPIPE, "Synthetic failure")):
                calls = []
                def ioctl(fd, request, buffer, mutate):
                    calls.append(bytes(buffer))
                    if len(calls) == ordinal:
                        if isinstance(failure, OSError):
                            raise failure
                        if failure == "changed":
                            buffer[6] ^= 1
                            return 8
                        return failure
                    return 8
                with self.subTest(ordinal=ordinal, failure=failure), patch("fcntl.ioctl", side_effect=ioctl), \
                        patch("time.sleep"), self.assertRaises((OSError, ValueError)):
                    write._write_fragment(42, fragment, Mock())
                self.assertEqual(len(calls), ordinal)

    def test_cli_missing_optin_duplicates_restore_mixing_and_arbitrary_addresses_fail_before_enumeration(self):
        args = ["--shortcut", '{"slot":5,"key":"F13","modifiers":[]}', "--accept-shortcut-write-risk",
                "--baseline", str(BASELINE), "--capture", "/synthetic/new"]
        variants = ([arg for arg in args if arg != "--accept-shortcut-write-risk"],
                    args + ["--address", "0x438"], args + ["--assign", "5=back"],
                    args + ["--shortcut", '{"slot":5,"key":"F14","modifiers":[]}'],
                    args + ["--shortcut", '{"slot":9,"key":"F13","modifiers":[]}'])
        import io
        for variant in variants:
            with patch.object(write, "enumerate_devices") as enum, contextlib.redirect_stderr(io.StringIO()):
                try:
                    result = write.main(variant)
                except SystemExit as error:
                    self.assertNotEqual(error.code, 0)
                else:
                    self.assertEqual(result, 1)
            enum.assert_not_called()

    def test_scope_rejects_auxiliary_firmware_metadata_and_slot_nine_addresses(self):
        for fragment in (Fragment("record", 0x418, bytes(8)), Fragment("record", 0x438, bytes(32)),
                         Fragment("descriptors", 0xf0, bytes(8)), Fragment("buttons", 0x10, bytes(8)),
                         Fragment("metadata", 0x78, bytes(8))):
            with self.subTest(fragment=fragment), self.assertRaises(ValueError):
                write.fragment_frames(fragment)

    def test_each_write_intent_and_result_fault_stops_without_another_feature(self):
        fragment = Fragment("record", 0x438, bytes.fromhex("01 00 84 68 00 00 00 00"))
        for kind in ("shortcut_write_intent", "shortcut_write_result"):
            for ordinal in range(1, 11):
                calls = []
                def record(event, **fields):
                    if event == kind and fields["ordinal"] == ordinal:
                        raise OSError(errno.ENOSPC, "Synthetic disk full")
                def ioctl(fd, request, buffer, mutate):
                    calls.append(bytes(buffer))
                    return 8
                with self.subTest(kind=kind, ordinal=ordinal), patch("fcntl.ioctl", side_effect=ioctl), \
                        patch("time.sleep"), self.assertRaises(OSError):
                    write._write_fragment(42, fragment, record)
                self.assertEqual(len(calls), ordinal - (kind == "shortcut_write_intent"))
