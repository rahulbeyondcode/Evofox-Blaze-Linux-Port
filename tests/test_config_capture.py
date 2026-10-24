import copy
import hashlib
import json
from pathlib import Path
import unittest

from evofox_blaze.config_capture import decode_config_journal
from evofox_blaze.config_write import load_backup


ROOT = Path(__file__).resolve().parents[1] / "docs/device-captures"
CHANGE = ROOT / "30fa-1440-0100-polling-test-01"
RESTORE = ROOT / "30fa-1440-0100-polling-restore-01"


class ConfigurationCaptureTests(unittest.TestCase):
    def test_actual_change_and_restore_are_exact_and_restore_original_bytes(self):
        changed = decode_config_journal((CHANGE / "configuration.jsonl").read_bytes())
        restored = decode_config_journal((RESTORE / "configuration.jsonl").read_bytes())
        self.assertEqual(changed["before_hex"], "19 3f 32 00 f3 ff 01 00")
        self.assertEqual(changed["after_hex"], "19 3f 32 00 f3 ff 00 00")
        self.assertEqual(restored["before_hex"], changed["after_hex"])
        self.assertEqual(restored["after_hex"], changed["before_hex"])
        for result in (changed, restored):
            self.assertEqual(result["set_feature_count"], 46)
            self.assertEqual(result["get_feature_count"], 16)
            self.assertFalse(result["behavior_verified"])
            self.assertFalse(result["complete_configuration_backup"])
        _, before, after = load_backup(CHANGE / "original-state.json")
        self.assertEqual(before.hex(" "), changed["before_hex"])
        self.assertEqual(after.hex(" "), changed["after_hex"])

    def test_live_evidence_files_remain_unchanged(self):
        expected = {
            CHANGE / "configuration.jsonl": "d529366e7a281b5cced250c96d8b0f3d35486c703d3dee2dd3e4a1d5a6cd4669",
            CHANGE / "original-state.json": "d2277c9acd65c9a2e2477166479674834dbe1e153ea1b1a20fc0605ce22e4168",
            RESTORE / "configuration.jsonl": "5591ad2dafb41614eed94bb653807f700e98a184141332f8aa5ab4965f3e225f",
            RESTORE / "original-state.json": "b7105a03e09529977b701dae87a431e57e6c09398a5b890e66908f7246b84505",
        }
        for path, digest in expected.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_failed_partial_extra_or_changed_write_is_not_a_verified_change(self):
        original = [json.loads(line) for line in (CHANGE / "configuration.jsonl").read_text().splitlines()]
        variants = [original[:-1], original + [original[-1]], original[:3] + [{"event": "config_failed"}]]
        changed = copy.deepcopy(original)
        next(event for event in changed if event["event"] == "config_write_intent")["frame_hex"] = "07 18 10 00 00 00 00 00"
        variants.append(changed)
        changed = copy.deepcopy(original)
        changed[-1]["behavior_verified"] = True
        variants.append(changed)
        for events in variants:
            with self.subTest(events=len(events)), self.assertRaises(ValueError):
                decode_config_journal(b"\n".join(json.dumps(event).encode() for event in events))


if __name__ == "__main__":
    unittest.main()
