import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from evofox_blaze import buttons


FIXTURE = json.loads((Path(__file__).parent / "fixtures/vendor-button-observations.json").read_text())
SYNTHETIC = bytes.fromhex("21 22 23 24 25 35 00 26")


class ButtonModelTests(unittest.TestCase):
    def test_actions_and_slot_order_match_static_evidence(self):
        self.assertEqual(buttons.UI_SLOTS, tuple(FIXTURE["ui_slots"]))
        self.assertEqual(buttons.ACTION_CODES, {row["name"]: row["code"] for row in FIXTURE["native_actions"]})
        for row in FIXTURE["native_actions"]:
            value = row["file_value"]
            expected = value if value < 7 else 21 if value == 15 else value - 5
            self.assertEqual(row["code"], expected)

    def test_slot_nine_static_candidate_does_not_unlock_the_backend(self):
        from evofox_blaze.button_draft import ButtonDraft
        candidate = FIXTURE["slot_9_followup"]
        self.assertEqual(buttons.UI_SLOTS[candidate["vendor_ui_button"] - 1], candidate["native_slot"])
        self.assertEqual(int(candidate["candidate_block_base"], 16), 0x10)
        self.assertFalse(candidate["hardware_region_read"])
        self.assertFalse(candidate["hardware_region_access_enabled"])
        self.assertFalse(ButtonDraft().editable(8))
        with self.assertRaises(ValueError):
            buttons.plan_assignments(SYNTHETIC, {9: "forward"})

    def test_one_plain_assignment_changes_and_all_other_bytes_are_preserved(self):
        for slot in buttons.BLOCK_SLOTS:
            for action, code in buttons.ACTION_CODES.items():
                # Keep an alternate Left Click while testing primary-button edits.
                source = bytes.fromhex("21 21 23 24 25 35 00 26")
                result = buttons.plan_button_change(source, slot, action)
                self.assertIsInstance(result, bytes)
                self.assertEqual(result[slot - 1], 0x20 | code)
                for index in range(8):
                    if index != slot - 1:
                        self.assertEqual(result[index], source[index])

    def test_last_left_click_cannot_be_removed(self):
        with self.assertRaisesRegex(ValueError, "Left Click"):
            buttons.plan_button_change(SYNTHETIC, 1, "right")
        self.assertEqual(buttons.plan_button_change(SYNTHETIC, 1, "left"), SYNTHETIC)

    def test_unknown_other_bytes_are_preserved_not_decoded_or_replaced(self):
        block = bytes.fromhex("21 22 23 24 25 ff de be")
        result = buttons.plan_button_change(block, 4, "middle")
        self.assertEqual(result, bytes.fromhex("21 22 23 22 25 ff de be"))
        self.assertIsNone(buttons.describe_block(block)["button_slots"][6]["action_candidate"])

    def test_flags_macro_codes_and_unknown_selected_slot_are_not_overwritten(self):
        for value in range(256):
            if value & 0xe0 == 0x20 and value & 31 in (*buttons.ACTION_CODES.values(), 14):
                continue
            block = bytearray(SYNTHETIC)
            block[3] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                buttons.plan_button_change(bytes(block), 4, "left")

    def test_invalid_types_lengths_actions_and_unmapped_slots_fail_closed(self):
        for block in (None, "21 " * 8, bytearray(SYNTHETIC), bytes(7), bytes(9)):
            with self.subTest(block=block), self.assertRaises(ValueError):
                buttons.plan_button_change(block, 4, "left")
        for slot in (True, "4", 0, -1, 7, 9, 255):
            with self.subTest(slot=slot), self.assertRaises(ValueError):
                buttons.plan_button_change(SYNTHETIC, slot, "left")
        for action in (None, [], 1, "keyboard", "Ctrl+C", "macro", "disabled"):
            with self.subTest(action=action), self.assertRaises(ValueError):
                buttons.plan_button_change(SYNTHETIC, 4, action)

    def test_observed_extension_links_can_be_replaced_without_synthesizing_records(self):
        original = bytes.fromhex("21 22 23 2e 2e 35 00 26")
        self.assertEqual(buttons.plan_assignments(original, {4: "back", 5: "forward"}),
                         bytes.fromhex("21 22 23 24 25 35 00 26"))
        with self.assertRaises(ValueError):
            buttons.plan_assignments(SYNTHETIC, {4: "shortcut"})

    def test_multiple_assignments_retain_left_click_and_preserve_spare_slot(self):
        result = buttons.plan_assignments(SYNTHETIC, {1: "right", 3: "left"})
        self.assertEqual(result, bytes.fromhex("23 22 21 24 25 35 00 26"))
        for assignments in ({}, {True: "left"}, {7: "back"}, {1: "right"}, {4: "Ctrl+C"}):
            with self.subTest(assignments=assignments), self.assertRaises(ValueError):
                buttons.plan_assignments(SYNTHETIC, assignments)

    def test_description_preserves_raw_bytes_and_does_not_claim_behavior(self):
        for value in range(256):
            result = buttons.describe_block(bytes((value,)) * 8)
            self.assertEqual(result["collected_hex"], " ".join([f"{value:02x}"] * 8))
            self.assertFalse(result["physical_button_attribution_verified"])
            self.assertFalse(result["behavior_verified"])
            self.assertFalse(result["complete_configuration_backup"])
            self.assertEqual(result["button_slots"][2]["vendor_ui_button"], 2)
            self.assertIsNone(result["button_slots"][6]["vendor_ui_button"])

    def test_cli_is_offline_and_labels_plans_not_hardware_approvals(self):
        with patch("fcntl.ioctl", side_effect=AssertionError("No hardware")), \
                patch("evofox_blaze.probe.enumerate_devices", side_effect=AssertionError("No enumeration")), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(buttons.main(["--block", SYNTHETIC.hex(), "--slot", "4", "--action", "middle"]), 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["planned_hex"], "21 22 23 22 25 35 00 26")
        self.assertFalse(result["hardware_approved"])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            buttons.main(["--block", SYNTHETIC.hex(), "--slot", "4"])
