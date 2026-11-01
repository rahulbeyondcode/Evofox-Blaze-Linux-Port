"""Verified-change activation integration on fake device memory only."""

import copy
import contextlib
import errno
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from evofox_blaze import activation, button_write, config_write, shortcut_write
from evofox_blaze.button_config_capture import decode_button_config_journal
from evofox_blaze.config_capture import decode_config_journal
from evofox_blaze.feature_read import Journal
from evofox_blaze.shortcut_config_capture import decode_shortcut_config_journal
from evofox_blaze.shortcuts import Shortcut
from evofox_blaze.state_read import GET_FEATURE, SET_FEATURE
import test_button_write as buttons_fixture
import test_config_write as config_fixture
import test_shortcut_write as shortcut_fixture


KINDS = ("buttons", "polling", "shortcuts")


class FakeChange:
    def __init__(self, test, kind):
        self.test, self.kind = test, kind
        if kind == "buttons":
            self.mouse = buttons_fixture.ButtonTransactionTests("test_fresh_read_backup_one_commit_and_full_readback")
            self.backend, self.decoder = button_write, decode_button_config_journal
            self.filename, self.backup = "button-configuration.jsonl", "button-backup.json"
        elif kind == "polling":
            self.mouse = config_fixture.ConfigurationTransactionTests("test_read_backup_write_readback_preserves_every_unowned_byte")
            self.backend, self.decoder = config_write, decode_config_journal
            self.filename, self.backup = "configuration.jsonl", "original-state.json"
        else:
            self.mouse = shortcut_fixture.ShortcutTransactionTests("test_fresh_backup_minimal_writes_and_complete_readback")
            self.backend, self.decoder = shortcut_write, decode_shortcut_config_journal
            self.filename, self.backup = "shortcut-configuration.jsonl", "shortcut-backup.json"
        self.mouse.setUp()
        test.addCleanup(self.mouse.doCleanups)
        self.mouse.capture = self.mouse.root / "change"
        self.features = self.mouse.operations if kind == "polling" else self.mouse.features
        self.events, self.activation_frames = [], []
        self.fail_event = None
        self.fail_ordinal = None
        self.activation_response = 8
        self.recheck = Mock()

    @property
    def path(self):
        return self.mouse.capture / self.filename

    def run(self, requested=True, *, assignments=None, shortcuts=None, **options):
        original_record = Journal.record
        latest = None
        def record(journal, event, **fields):
            nonlocal latest
            if self.fail_event == (event, fields.get("ordinal")):
                raise OSError(errno.ENOSPC, "Synthetic activation log failure")
            original_record(journal, event, **fields)
            latest = {"event": event, **fields}
            self.events.append(latest)
            self.mouse.last_event = event, fields
        def ioctl(fd, request, buffer, mutate):
            if latest["event"] != "activation_intent":
                return self.mouse.ioctl(fd, request, buffer, mutate)
            self.test.assertEqual((fd, request), (42, SET_FEATURE))
            ordinal = latest["ordinal"]
            self.test.assertEqual(bytes(buffer), activation.activation_steps()[0 if ordinal == 1 else 2].report)
            self.test.assertTrue((self.mouse.capture / self.backup).is_file())
            begin = next(i for i, row in enumerate(self.events) if row["event"] == "activation_begin")
            self.test.assertTrue(any(row.get("phase") == "verify" for row in self.events[:begin]))
            self.activation_frames.append(bytes(buffer))
            self.features.append((request, bytes(buffer)))
            if ordinal == self.fail_ordinal:
                if isinstance(self.activation_response, Exception):
                    raise self.activation_response
                if self.activation_response == "changed":
                    buffer[0] = 0
                    return 8
                return self.activation_response
            return 8
        common = dict(accept_write_risk=True, accept_activation_risk=requested, **options)
        with patch.object(self.backend, "validated_handle", side_effect=self.mouse.handle) as handle, \
                patch.object(self.backend, "check_host"), patch.object(Journal, "record", record), \
                patch("fcntl.ioctl", side_effect=ioctl), patch("time.sleep"), patch("os.fsync"):
            self.handle = handle
            if self.kind == "buttons":
                return button_write.change_buttons(self.mouse.target,
                                                   buttons_fixture.ASSIGNMENTS if assignments is None else assignments, self.mouse.capture,
                                                   self.recheck, **common)
            if self.kind == "polling":
                return config_write.change_setting(self.mouse.target, "polling", 1000, self.mouse.capture,
                                                   self.recheck, **common)
            return shortcut_write.change_shortcuts(self.mouse.target, {4: "middle"} if assignments is None else assignments,
                                                   {5: Shortcut("Down", ("Control_L", "Alt_L"))} if shortcuts is None else shortcuts,
                                                   self.mouse.capture, self.recheck, **common)

    def inspect(self):
        return self.decoder(self.path.read_bytes())


class ApplyActivationTests(unittest.TestCase):
    def test_all_backends_keep_the_same_handle_and_activate_only_after_verified_readback(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                case = FakeChange(self, kind)
                result = case.run()
                self.assertEqual(case.activation_frames, [activation.activation_steps()[i].report for i in (0, 2)])
                self.assertEqual([frame for _, frame in case.features[-2:]], case.activation_frames)
                case.handle.assert_called_once()
                self.assertEqual(case.recheck.call_count, 2)
                self.assertEqual(result["activation_outcome"], "sequence-sent")
                self.assertFalse(result["activation_behavior_verified"])
                inspected = case.inspect()
                self.assertTrue(inspected["activation_requested"])
                self.assertEqual(inspected["activation_outcome"], "sequence-sent")
                self.assertFalse(inspected["behavior_verified"])
                self.assertEqual(inspected["set_feature_count"], sum(request == SET_FEATURE for request, _ in case.features))
                self.assertEqual(inspected["get_feature_count"], sum(request == GET_FEATURE for request, _ in case.features))

    def test_default_change_does_not_add_reports_fields_or_activation_events(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                case = FakeChange(self, kind)
                result = case.run(False)
                self.assertEqual(case.activation_frames, [])
                self.assertNotIn("activation_requested", result)
                self.assertNotIn("activation_requested", case.inspect())
                self.assertFalse(any(row["event"].startswith("activation_") for row in case.events))
                case.recheck.assert_called_once()

    def test_no_change_does_not_send_activation_or_create_a_new_backup(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                case = FakeChange(self, kind)
                case.run(False)
                case.mouse.capture = case.mouse.root / "unchanged"
                case.features.clear()
                case.events.clear()
                case.recheck.reset_mock()
                result = case.run()
                self.assertEqual(result["outcome"], "no-change")
                self.assertEqual(result["activation_outcome"], "skipped-no-change")
                self.assertFalse((case.mouse.capture / case.backup).exists())
                self.assertEqual(case.activation_frames, [])
                self.assertEqual(case.inspect()["activation_outcome"], "skipped-no-change")
                case.recheck.assert_called_once()

    def test_invalid_optin_and_restore_are_rejected_before_any_handle_or_capture(self):
        for kind in KINDS:
            for requested, options in ((None, {}), (1, {}), ("yes", {}),
                                       (True, {"restore_from": Path("missing-backup.json")})):
                with self.subTest(kind=kind, requested=requested, options=options):
                    case = FakeChange(self, kind)
                    with self.assertRaises(ValueError):
                        case.run(requested, **options)
                    case.handle.assert_not_called()
                    self.assertFalse(case.mouse.capture.exists())

    def test_first_f13_scope_and_dpi_stage_cannot_gain_activation_implicitly(self):
        with patch.object(shortcut_write, "validated_handle") as opened, self.assertRaises(ValueError):
            shortcut_write.change_shortcuts(None, {}, {}, None, Mock(), accept_write_risk=True,
                                            accept_activation_risk=True, first_tail_test=True)
        opened.assert_not_called()
        with patch.object(config_write, "validated_handle") as opened, self.assertRaises(ValueError):
            config_write.change_setting(None, "dpi-stage", 1, None, Mock(), accept_write_risk=True,
                                        accept_activation_risk=True)
        opened.assert_not_called()

    def test_cli_rejects_restore_dpi_and_old_field_test_scope_expansion_before_enumeration(self):
        requests = ((button_write, ["--restore-backup", "missing", "--accept-write-risk"]),
                    (config_write, ["--restore-backup", "missing", "--accept-write-risk"]),
                    (config_write, ["--dpi-stage", "1", "--accept-write-risk"]),
                    (shortcut_write, ["--restore-backup", "missing", "--accept-shortcut-write-risk"]),
                    (shortcut_write, ["--shortcut", '{"slot":5,"key":"F13","modifiers":[]}',
                                      "--first-tail-test", "--accept-shortcut-write-risk"]))
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as temporary:
            for backend, arguments in requests:
                args = [*arguments, "--accept-activation-risk", "--baseline", str(config_fixture.BASELINE),
                        "--capture", str(Path(temporary) / "never-created")]
                with self.subTest(backend=backend.__name__, arguments=arguments), \
                        patch.object(backend, "enumerate_devices") as enum, contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(backend.main(args), 1)
                enum.assert_not_called()
                self.assertFalse((Path(temporary) / "never-created").exists())

    def test_failed_backup_never_commits_or_sends_activation(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                case = FakeChange(self, kind)
                with patch.object(case.backend, "_save_backup", side_effect=OSError("Synthetic backup failure")), \
                        self.assertRaises(OSError):
                    case.run()
                self.assertEqual(case.mouse.commits, 0)
                self.assertEqual(case.activation_frames, [])

    def test_bad_readback_never_runs_the_activation_suffix(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                case = FakeChange(self, kind)
                setattr(case.mouse, {"buttons": "bad_readback", "polling": "fail_verify", "shortcuts": "corrupt_readback"}[kind], True)
                with self.assertRaises(ValueError):
                    case.run()
                self.assertEqual(case.activation_frames, [])
                self.assertFalse(any(row["event"] == "activation_begin" for row in case.events))
                with self.assertRaises((ValueError, KeyError)):
                    case.inspect()

    def test_ambiguous_setting_commit_never_sends_activation_or_retries(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                case = FakeChange(self, kind)
                setattr(case.mouse, {"buttons": "stall_commit", "polling": "fail_commit", "shortcuts": "stall_commit"}[kind],
                        1 if kind == "shortcuts" else True)
                with self.assertRaises(OSError):
                    case.run()
                self.assertEqual(case.mouse.commits, 1)
                self.assertEqual(case.activation_frames, [])
                self.assertTrue((case.mouse.capture / case.backup).exists())

    def test_changed_identity_after_readback_stops_without_activation(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                case = FakeChange(self, kind)
                case.recheck.side_effect = [None, ValueError("Synthetic device changed after readback")]
                with self.assertRaisesRegex(ValueError, "changed after readback"):
                    case.run()
                self.assertEqual(case.activation_frames, [])
                self.assertTrue((case.mouse.capture / case.backup).exists())

    def test_activation_stall_or_short_result_never_retries_or_claims_verified_success(self):
        for kind in KINDS:
            for ordinal, response in ((1, OSError(errno.EPIPE, "Synthetic activation stall")), (2, 7), (1, True), (2, "changed")):
                with self.subTest(kind=kind, ordinal=ordinal, response=response):
                    case = FakeChange(self, kind)
                    case.fail_ordinal, case.activation_response = ordinal, response
                    with self.assertRaises((ValueError, OSError)):
                        case.run()
                    self.assertEqual(len(case.activation_frames), ordinal)
                    self.assertTrue(case.events[-1]["event"].endswith("_failed"))
                    self.assertTrue((case.mouse.capture / case.backup).exists())
                    with self.assertRaises((ValueError, KeyError)):
                        case.inspect()

    def test_failed_activation_logging_at_every_stage_stops_without_a_completion_claim(self):
        for kind in KINDS:
            for event, ordinal, sent in (("activation_begin", None, 0), ("activation_intent", 1, 0),
                                         ("activation_result", 1, 1), ("activation_delay", None, 1),
                                         ("activation_intent", 2, 1), ("activation_result", 2, 2),
                                         ("activation_complete", None, 2)):
                with self.subTest(kind=kind, event=event, ordinal=ordinal):
                    case = FakeChange(self, kind)
                    case.fail_event = event, ordinal
                    with self.assertRaises(OSError):
                        case.run()
                    self.assertEqual(len(case.activation_frames), sent)
                    with self.assertRaises((ValueError, KeyError)):
                        case.inspect()

    def test_inspectors_refuse_missing_consent_reordered_suffix_and_false_behavior_claims(self):
        for kind in KINDS:
            case = FakeChange(self, kind)
            case.run()
            events = [json.loads(line) for line in case.path.read_bytes().splitlines()]
            begin = next(i for i, event in enumerate(events) if event["event"] == "activation_begin")
            mutations = [(0, "accepted_activation_risk", False), (0, "accepted_activation_risk", 1),
                         (begin, "stage", "before-readback"),
                         (begin + 1, "frame_hex", "07 20 00 00 00 00 00 00"),
                         (begin + 2, "returned_length", True),
                         (begin + 6, "behavior_verified", True),
                         (len(events) - 1, "activation_behavior_verified", True),
                         (len(events) - 1, "activation_outcome", "active")]
            for index, key, value in mutations:
                with self.subTest(kind=kind, key=key, value=value):
                    changed = copy.deepcopy(events)
                    changed[index][key] = value
                    with self.assertRaises((ValueError, KeyError)):
                        case.decoder(b"\n".join(json.dumps(event).encode() for event in changed))
            for changed in (events[:begin + 1] + events[begin + 2:], events + [events[-1]],
                            events[:2] + events[begin:begin + 7] + events[2:begin] + events[begin + 7:]):
                with self.subTest(kind=kind, malformed_suffix=True), self.assertRaises((ValueError, KeyError)):
                    case.decoder(b"\n".join(json.dumps(event).encode() for event in changed))

    def test_legacy_completion_cannot_invent_an_activation_claim_without_requests(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                case = FakeChange(self, kind)
                case.run(False)
                events = [json.loads(line) for line in case.path.read_bytes().splitlines()]
                events[-1].update(activation.activation_fields(True, True))
                with self.assertRaises(ValueError):
                    case.decoder(b"\n".join(json.dumps(event).encode() for event in events))
