from pathlib import Path
import unittest
from unittest.mock import patch

from evofox_blaze.button_draft import ButtonDraft, UNREAD_LABELS
from evofox_blaze.capture_view import CaptureModel, present_capture
from evofox_blaze.shortcuts import Shortcut


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "docs/device-captures/30fa-1440-0100-button-read-01/button-read.jsonl"
CHANGED = ROOT / "docs/device-captures/30fa-1440-0100-button-remap-01/button-configuration.jsonl"
STATE = ROOT / "docs/device-captures/30fa-1440-0100-state-read-01/state-read.jsonl"


class ButtonDraftTests(unittest.TestCase):
    def setUp(self):
        self.draft = ButtonDraft()
        self.model = CaptureModel()

    def load(self, path=CAPTURE):
        self.assertTrue(self.model.load(path), self.model.error)
        self.draft.sync(self.model.presentation.details)

    def test_startup_has_no_readings_but_supports_offline_menu_choices(self):
        self.assertIsNone(self.draft.block)
        self.assertEqual(self.draft.labels(), UNREAD_LABELS)
        self.assertFalse(self.draft.can_apply)
        self.assertTrue(all(self.draft.editable(index) for index in range(1, 8)))
        self.assertFalse(self.draft.editable(8))
        self.draft.assign(5, "middle")
        self.assertTrue(self.draft.can_apply)
        self.assertEqual(self.draft.pending, {4: "middle"})
        self.assertEqual(self.draft.labels()[4], "Middle Click *")
        self.assertIsNone(self.draft.block)  # No synthetic original from reference labels.
        self.draft.sync(None)
        self.assertEqual(self.draft.pending, {4: "middle"})
        self.draft.cancel()
        self.assertEqual(self.draft.labels(), UNREAD_LABELS)
        self.assertFalse(self.draft.can_apply)

    def test_shortcut_save_replaces_one_row_with_a_local_draft_not_native_bytes(self):
        self.draft.assign(4, "middle")
        shortcut = Shortcut("Left", ("Control_L", "Super_L"))
        self.draft.assign_shortcut(4, shortcut)
        self.assertEqual(self.draft.shortcuts, {5: shortcut})
        self.assertEqual(self.draft.pending, {})
        self.assertEqual(self.draft.labels()[3], "Ctrl+Super+Left *")
        self.assertIs(self.draft.shortcut(4), shortcut)
        self.assertTrue(self.draft.has_changes)
        self.assertTrue(self.draft.can_apply)
        self.assertIsNone(self.draft.block)

    def test_mixed_draft_is_eligible_for_a_combined_transaction(self):
        self.load(CHANGED)
        self.draft.assign(5, "middle")
        self.draft.assign_shortcut(4, Shortcut("k", ("Control_L",)))
        self.assertEqual(self.draft.pending, {4: "middle"})
        self.assertTrue(self.draft.can_apply)
        self.draft.assign(4, "forward")  # Return to the captured baseline.
        self.assertEqual(self.draft.shortcuts, {})
        self.assertTrue(self.draft.can_apply)  # The other native row is still changed.
        self.draft.assign(5, "back")
        self.assertFalse(self.draft.has_changes)

    def test_verified_shortcut_baseline_tracks_net_changes_and_native_replacement(self):
        path = ROOT / "docs/device-captures/30fa-1440-0100-shortcut-f13-test-01/shortcut-configuration.jsonl"
        self.load(path)
        self.assertEqual(self.draft.labels()[3], "F13")
        self.assertEqual(self.draft.shortcut(4), Shortcut("F13"))
        self.assertFalse(self.draft.can_apply)
        self.draft.assign_shortcut(4, Shortcut("Down", ("Control_L", "Shift_L")))
        self.assertTrue(self.draft.can_apply)  # Same 2e link, different actual chord.
        self.draft.assign_shortcut(4, Shortcut("F13"))
        self.assertFalse(self.draft.has_changes)
        self.draft.assign(4, "right")
        self.assertIsNone(self.draft.shortcut(4))
        self.assertTrue(self.draft.can_apply)
        self.draft.cancel()
        self.assertEqual(self.draft.shortcut(4), Shortcut("F13"))

    def test_combined_final_table_must_keep_left_click_when_state_is_known(self):
        self.load(CHANGED)
        self.draft.assign_shortcut(1, Shortcut("F13"))
        self.assertFalse(self.draft.can_apply)
        self.draft.assign(2, "left")
        self.assertTrue(self.draft.can_apply)

    def test_failed_apply_keeps_shortcut_display_baseline_without_raw_backup_bytes(self):
        path = ROOT / "docs/device-captures/30fa-1440-0100-shortcut-f13-test-01/shortcut-configuration.jsonl"
        self.load(path)
        self.draft.assign_shortcut(4, Shortcut("k"))
        self.draft.invalidate_evidence()
        self.draft.sync(None)
        self.assertIsNone(self.draft.block)
        self.assertTrue(self.draft.can_apply)
        self.draft.assign_shortcut(4, Shortcut("F13"))
        self.assertFalse(self.draft.can_apply)
        self.assertEqual(self.draft.labels()[3], "F13")

    def test_cancel_and_changed_evidence_clear_shortcuts_but_same_evidence_keeps_them(self):
        self.load()
        shortcut = Shortcut("k")
        self.draft.assign_shortcut(4, shortcut)
        self.draft.sync(self.model.presentation.details)
        self.assertEqual(self.draft.shortcut(4), shortcut)
        self.load(CHANGED)
        self.assertEqual(self.draft.shortcuts, {})
        self.draft.assign_shortcut(4, shortcut)
        self.draft.cancel()
        self.assertFalse(self.draft.has_changes)
        self.assertEqual(self.draft.labels()[3], "Forward")
        self.draft.assign_shortcut(4, shortcut)
        self.draft.sync(None)
        self.assertEqual(self.draft.shortcuts, {})

    def test_unsupported_shortcut_target_and_invalid_values_are_rejected(self):
        for index, value in ((8, Shortcut("a")), (True, Shortcut("a")), (1, "Ctrl+C"), (1, None)):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.draft.assign_shortcut(index, value)
        self.assertEqual(self.draft.shortcuts, {})
        for index in (None, True, 0, 9):
            self.assertIsNone(self.draft.shortcut(index))

    def test_fresh_read_validation_is_deferred_instead_of_guessing_a_table(self):
        self.draft.assign(1, "right")
        self.assertTrue(self.draft.can_apply)
        self.assertIsNone(self.draft.block)
        # The real backend, not the displayed reference, enforces a remaining
        # Left Click and refuses unknown current encodings after its fresh read.
        from evofox_blaze.buttons import plan_assignments
        with self.assertRaises(ValueError):
            plan_assignments(bytes.fromhex("21 22 23 24 25 35 00 26"), self.draft.pending)

    def test_initial_example_actions_do_not_block_restoring_left_and_right_after_restart(self):
        self.draft.assign(1, "left")
        self.draft.assign(2, "right")
        self.assertEqual(self.draft.pending, {1: "left", 3: "right"})
        self.assertTrue(self.draft.can_apply)
        self.assertIsNone(self.draft.block)
        from evofox_blaze.buttons import plan_assignments
        # The real backend will see swapped buttons, not the old UI defaults.
        after = plan_assignments(bytes.fromhex("23 22 21 24 25 35 00 26"), self.draft.pending)
        self.assertEqual(after, bytes.fromhex("21 22 23 24 25 35 00 26"))

    def test_returning_to_a_captured_option_disables_apply(self):
        self.load(CHANGED)
        self.draft.assign(4, "forward")
        self.assertFalse(self.draft.can_apply)
        for action in ("right", "dpi-cycle", "middle", "double-click"):
            self.draft.assign(4, action)
            self.assertTrue(self.draft.can_apply)
        self.draft.assign(4, "forward")
        self.assertEqual(self.draft.pending, {})
        self.assertFalse(self.draft.can_apply)
        self.assertEqual(self.draft.labels()[3], "Forward")
        self.assertIsNotNone(self.draft.block)

    def test_reverting_one_row_keeps_apply_enabled_if_another_row_changed(self):
        self.load(CHANGED)
        self.draft.assign(1, "middle")
        self.draft.assign(4, "right")
        self.draft.assign(1, "left")
        self.assertEqual(self.draft.pending, {5: "right"})
        self.assertTrue(self.draft.can_apply)
        self.draft.assign(4, "forward")
        self.assertFalse(self.draft.can_apply)

    def test_saved_baseline_not_reference_values_controls_undo(self):
        self.load(CHANGED)
        self.draft.assign(4, "middle")
        self.draft.assign(4, "dpi-cycle")
        self.assertTrue(self.draft.can_apply)
        self.draft.assign(4, "forward")
        self.assertFalse(self.draft.can_apply)
        self.assertEqual(self.draft.labels()[3], "Forward")

    def test_failure_drops_raw_evidence_but_preserves_the_last_shown_baseline(self):
        import json
        from evofox_blaze.buttons import describe_block
        self.draft.sync(json.dumps({"mode": "offline-button-inspection",
                                    **describe_block(bytes.fromhex("21 22 23 24 22 35 00 26"))}))
        self.draft.assign(4, "right")  # UI button 4 originally showed Middle Click.
        self.draft.invalidate_evidence()
        self.draft.sync(None)
        self.assertIsNone(self.draft.block)
        self.assertTrue(self.draft.can_apply)
        self.draft.assign(4, "middle")
        self.assertFalse(self.draft.can_apply)
        self.assertEqual(self.draft.labels()[3], "Middle Click")

    def test_saved_block_enables_seven_ui_buttons_and_leaves_slot_nine_disabled(self):
        self.load()
        self.assertTrue(all(self.draft.editable(index) for index in range(1, 8)))
        self.assertFalse(self.draft.editable(8))
        self.assertEqual(self.draft.labels()[3:5], ("Stored shortcut", "Stored shortcut"))
        self.assertIn("Not read", self.draft.labels()[7])

    def test_two_drafts_use_vendor_slot_order_and_cancel_preserves_capture(self):
        self.load()
        self.draft.assign(4, "forward")
        self.draft.assign(5, "back")
        self.assertEqual(self.draft.pending, {5: "forward", 4: "back"})
        self.assertEqual(self.draft.labels()[3:5], ("Forward *", "Backward *"))
        self.assertTrue(self.draft.can_apply)
        self.draft.sync(self.model.presentation.details)
        self.assertTrue(self.draft.can_apply)
        self.draft.cancel()
        self.assertFalse(self.draft.can_apply)
        self.assertEqual(self.draft.block.hex(" "), "21 22 23 2e 2e 35 00 26")

    def test_last_left_click_is_not_applicable_until_another_button_has_left(self):
        self.load()
        self.draft.assign(1, "right")
        self.assertFalse(self.draft.can_apply)
        self.draft.assign(2, "left")
        self.assertTrue(self.draft.can_apply)

    def test_new_evidence_or_failed_load_discards_old_drafts(self):
        self.load()
        self.draft.assign(4, "middle")
        self.load(CHANGED)
        self.assertEqual(self.draft.pending, {})
        self.assertEqual(self.draft.labels()[3:5], ("Forward", "Backward"))
        self.draft.assign(4, "forward")
        self.assertEqual(self.draft.pending, {})
        self.load(STATE)
        self.assertIsNone(self.draft.block)
        self.load()
        self.draft.sync(None)
        self.assertIsNone(self.draft.block)
        self.assertFalse(self.draft.can_apply)

    def test_unsupported_actions_and_slots_are_not_drafted(self):
        self.load()
        for index, action in ((8, "back"), (True, "left"), (1, "Ctrl+C"), (1, "macro")):
            with self.subTest(index=index, action=action), self.assertRaises(ValueError):
                self.draft.assign(index, action)

    def test_offline_capture_presentation_does_not_claim_live_state_or_macro_programming(self):
        with patch("fcntl.ioctl", side_effect=AssertionError("No device")), \
                patch("evofox_blaze.probe.enumerate_devices", side_effect=AssertionError("No enumeration")):
            for capture in (CAPTURE, CHANGED):
                rows = dict(present_capture(capture).rows)
                self.assertIn("saved file, not live", rows["Source"])
                self.assertIn("unplug/replug", rows["Native button activation"])
                self.assertIn("Not implemented", rows["Keyboard / macro programming"])
                self.assertNotIn("Polling setting candidate", rows)
