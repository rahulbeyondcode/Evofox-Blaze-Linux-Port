from contextlib import contextmanager
import contextlib
from dataclasses import replace
import errno
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from evofox_blaze import config_write as config
from evofox_blaze.feature_read import load_baseline
from evofox_blaze.state_read import GET_FEATURE, SET_FEATURE


BASELINE = (Path(__file__).resolve().parents[1]
            / "docs/device-captures/2026-10-23-30fa-1440-0100/probe.json")
ORIGINAL = bytes.fromhex("19 3f 32 00 f3 ff 01 00")  # Saved read, not a write-approved default.


class ChangePlanTests(unittest.TestCase):
    def test_field_positions_and_codes_match_the_evidence_fixture(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/vendor-state-fields.json").read_text())
        for divisor, hz in fixture["polling"]["divisor_to_hz_candidate"].items():
            self.assertEqual(config.POLLING_CODES[hz], int(divisor))
        for hz in config.POLLING_CODES:
            result = config.plan_change(ORIGINAL, "polling", hz)
            self.assertTrue(all(result[i] == ORIGINAL[i] for i in fixture["preserved_byte_offsets"]))
    def test_polling_changes_only_byte_six_for_each_supported_code(self):
        for hz, code in config.POLLING_CODES.items():
            with self.subTest(hz=hz):
                changed = config.plan_change(ORIGINAL, "polling", hz)
                self.assertEqual(changed[:6], ORIGINAL[:6])
                self.assertEqual(changed[6], code)
                self.assertEqual(changed[7], ORIGINAL[7])

    def test_active_stage_changes_only_low_three_bits_of_byte_zero(self):
        for stage in range(6):
            changed = config.plan_change(ORIGINAL, "dpi-stage", stage)
            self.assertEqual(changed[0], 0x18 | stage)
            self.assertEqual(changed[1:], ORIGINAL[1:])

    def test_disabled_stage_is_not_silently_enabled(self):
        restricted = bytes((0x19, 2)) + ORIGINAL[2:]
        with self.assertRaises(ValueError):
            config.plan_change(restricted, "dpi-stage", 0)
        self.assertEqual(config.plan_change(restricted, "dpi-stage", 1), restricted)

    def test_invalid_values_shapes_and_unknown_state_refused(self):
        for field, value in (("lighting", 1), ("polling", 300), ("polling", True),
                             ("dpi-stage", 6), ("dpi-stage", -1), ("dpi-stage", 1.0)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                config.plan_change(ORIGINAL, field, value)
        for raw in (bytes(8), ORIGINAL[:-1], bytearray(ORIGINAL), b"\x1f" + ORIGINAL[1:],
                    ORIGINAL[:1] + b"\x00" + ORIGINAL[2:], ORIGINAL[:6] + b"\x02" + ORIGINAL[7:],
                    ORIGINAL[:1] + b"\xc0" + ORIGINAL[2:]):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                config.plan_change(raw, "polling", 1000)


class ConfigurationTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target, _ = load_baseline(BASELINE)
        self.target = replace(self.target, path="/dev/hidraw42")
        self.memory = ORIGINAL
        self.pending = {}
        self.request_index = None
        self.operations = []
        self.commits = 0
        self.fail_commit = False
        self.fail_verify = False

    @contextmanager
    def handle(self, target, record, recheck, *, writable):
        self.assertTrue(writable)
        self.assertEqual(target, self.target)
        recheck(target)
        record("handle_validated", identity=target.identity(), bus=3)
        yield 42

    def ioctl(self, fd, request, buffer, mutate):
        self.assertEqual(fd, 42)
        self.assertTrue(mutate)
        self.operations.append((request, bytes(buffer)))
        if request == GET_FEATURE:
            if self.fail_verify and self.commits:
                return 7
            self.assertIsNotNone(self.request_index)
            buffer[:] = bytes((7, self.memory[self.request_index], 0x62, 9, 15, 0, 0x27, 0xDB))
        else:
            self.assertEqual(request, SET_FEATURE)
            self.assertEqual(buffer[:2], b"\x07\x18")
            phase, index = buffer[2:4]
            self.assertIn(phase, (0, 3, 5, 9))
            base = int.from_bytes(buffer[4:6], "little")
            self.assertIn(base, (0, 0x18))
            if phase == 3:
                self.pending[index] = buffer[6]
            elif phase == 0:
                self.pending.clear()
                self.request_index = None
            elif phase == 5:
                self.request_index = index
            else:
                self.assertEqual(base, 0x18)
                self.assertEqual(buffer[7], 7)
                self.assertEqual(set(self.pending), set(range(8)))
                # A durable validated backup must precede the settings commit.
                backups = list(self.root.glob("*/original-state.json"))
                self.assertTrue(backups)
                self.assertTrue(any(config.load_backup(path)[1] == self.memory for path in backups))
                self.memory = bytes(self.pending[i] for i in range(8))
                self.commits += 1
                if self.fail_commit:
                    raise OSError(errno.EPIPE, "synthetic ambiguous commit")
        return 8

    def run_change(self, *, field="polling", value=1000, name="change", restore_from=None, **kwargs):
        with patch.object(config, "validated_handle", side_effect=self.handle), \
                patch("fcntl.ioctl", side_effect=self.ioctl), patch("time.sleep"):
            return config.change_setting(self.target, field, value, self.root / name, Mock(),
                                         accept_write_risk=True, restore_from=restore_from, **kwargs)

    def test_read_backup_write_readback_preserves_every_unowned_byte(self):
        result = self.run_change()
        self.assertEqual(result["outcome"], "written-and-read-back")
        self.assertFalse(result["behavior_verified"])
        self.assertEqual(self.memory, ORIGINAL[:6] + b"\x00" + ORIGINAL[7:])
        self.assertEqual(self.commits, 1)
        self.assertEqual(len(self.operations), 62)  # 26 read + 10 write + 26 verify.
        path = self.root / "change/original-state.json"
        saved, before, after = config.load_backup(path)
        self.assertEqual(before, ORIGINAL)
        self.assertEqual(after, self.memory)
        self.assertFalse(saved["complete_configuration_backup"])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_separate_restore_recovers_original_bytes_without_a_generic_replay(self):
        self.run_change()
        result = self.run_change(name="restore", restore_from=self.root / "change/original-state.json")
        self.assertEqual(result["outcome"], "written-and-read-back")
        self.assertEqual(self.memory, ORIGINAL)
        self.assertEqual(self.commits, 2)

    def test_already_matching_setting_does_not_commit_or_make_a_write_backup(self):
        result = self.run_change(value=500)
        self.assertEqual(result["outcome"], "no-change")
        self.assertEqual(self.commits, 0)
        self.assertEqual(len(self.operations), 26)
        self.assertFalse((self.root / "change/original-state.json").exists())
        from evofox_blaze.config_capture import decode_config_journal
        saved = decode_config_journal((self.root / "change/configuration.jsonl").read_bytes())
        self.assertEqual(saved["outcome"], "no-change")
        self.assertEqual(saved["set_feature_count"], 18)

    def test_restore_does_not_overwrite_intervening_changes(self):
        self.run_change()
        self.memory = bytes((0x1A,)) + self.memory[1:]  # Someone changed the stage afterwards.
        with self.assertRaisesRegex(ValueError, "intervening"):
            self.run_change(name="restore", restore_from=self.root / "change/original-state.json")
        self.assertEqual(self.commits, 1)
        self.assertEqual(self.memory[0], 0x1A)

    def test_failed_backup_prevents_setting_data_frames_or_commit(self):
        with patch.object(config, "_save_backup", side_effect=OSError(errno.ENOSPC, "synthetic full disk")):
            with self.assertRaises(OSError):
                self.run_change()
        self.assertEqual(self.commits, 0)
        self.assertEqual(len(self.operations), 26)
        self.assertEqual(self.memory, ORIGINAL)

    def test_failed_commit_intent_log_prevents_the_commit_and_cleanup(self):
        original_record = config.Journal.record
        def failing(journal, event, **fields):
            if event == "config_write_intent" and fields["ordinal"] == 9:
                raise OSError(errno.ENOSPC, "synthetic failed intent")
            original_record(journal, event, **fields)
        with patch.object(config.Journal, "record", failing), self.assertRaises(OSError):
            self.run_change()
        self.assertEqual(self.commits, 0)
        self.assertEqual(len(self.operations), 34)
        self.assertEqual(self.memory, ORIGINAL)

    def test_failed_commit_result_logging_stops_without_retry_or_cleanup(self):
        original_record = config.Journal.record
        def failing(journal, event, **fields):
            if event == "config_write_result" and fields["ordinal"] == 9:
                raise OSError(errno.ENOSPC, "synthetic failed result")
            original_record(journal, event, **fields)
        with patch.object(config.Journal, "record", failing), self.assertRaises(OSError):
            self.run_change()
        self.assertEqual(self.commits, 1)
        self.assertEqual(len(self.operations), 35)

    def test_ambiguous_commit_stops_without_retry_verification_or_rollback(self):
        self.fail_commit = True
        with self.assertRaises(OSError):
            self.run_change()
        self.assertEqual(self.commits, 1)
        self.assertEqual(len(self.operations), 35)  # Stop at first commit, before exit/verify.
        events = [json.loads(line) for line in (self.root / "change/configuration.jsonl").read_text().splitlines()]
        self.assertEqual(events[-1]["event"], "config_failed")
        self.assertIn("No retry or rollback", events[-1]["recovery"])

    def test_short_readback_retains_backup_without_automatic_recovery(self):
        self.fail_verify = True
        with self.assertRaises(ValueError):
            self.run_change()
        self.assertEqual(self.commits, 1)
        self.assertTrue((self.root / "change/original-state.json").exists())

    def test_no_opt_in_invalid_request_or_wrong_target_never_opens_device(self):
        with patch.object(config, "validated_handle") as handle:
            for acknowledgement in (False, 1, "yes"):
                with self.assertRaises(ValueError):
                    config.change_setting(self.target, "polling", 1000, self.root / "bad", Mock(),
                                          accept_write_risk=acknowledgement)
            for field, value in (("polling", 999), ("dpi-stage", 6), ("lighting", 1)):
                with self.assertRaises(ValueError):
                    config.change_setting(self.target, field, value, self.root / "bad", Mock(), accept_write_risk=True)
            with self.assertRaises(ValueError):
                config.change_setting(replace(self.target, revision="9999"), "polling", 1000,
                                      self.root / "bad", Mock(), accept_write_risk=True)
            handle.assert_not_called()

    def test_existing_output_or_tampered_backup_is_refused_before_device_open(self):
        self.run_change()
        with patch.object(config, "validated_handle") as handle:
            with self.assertRaises(FileExistsError):
                config.change_setting(self.target, "polling", 1000, self.root / "change", Mock(), accept_write_risk=True)
            backup = self.root / "change/original-state.json"
            value = json.loads(backup.read_text())
            value["before_hex"] = bytes(8).hex()
            backup.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                config.change_setting(self.target, None, None, self.root / "restore", Mock(),
                                      accept_write_risk=True, restore_from=backup)
            handle.assert_not_called()


class ConfigurationCLITests(unittest.TestCase):
    def test_write_opt_in_is_required_before_enumeration(self):
        with patch.object(config, "enumerate_devices") as devices, \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            config.main(["--polling", "1000", "--baseline", str(BASELINE), "--capture", "unused"])
        devices.assert_not_called()

    def test_arbitrary_address_and_report_options_are_not_accepted(self):
        with patch.object(config, "enumerate_devices") as devices, \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            config.main(["--polling", "1000", "--accept-write-risk", "--baseline", str(BASELINE),
                         "--capture", "unused", "--address", "0x003f"])
        devices.assert_not_called()


if __name__ == "__main__":
    unittest.main()
