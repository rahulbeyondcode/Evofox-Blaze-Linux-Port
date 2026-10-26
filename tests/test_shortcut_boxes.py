import unittest

from evofox_blaze.shortcut_boxes import ShortcutBoxes
from evofox_blaze.shortcuts import Shortcut


class ShortcutBoxTests(unittest.TestCase):
    def tap(self, boxes, key, code):
        boxes.press(key, code)
        boxes.release(code)

    def test_separate_presses_build_one_chord_and_advance_only_after_release(self):
        boxes = ShortcutBoxes()
        boxes.start()
        for index, key in enumerate(("Control_L", "Alt_L", "Down")):
            boxes.press(key, index)
            self.assertEqual(boxes.active, index)
            self.assertIsNone(boxes.values[index])
            boxes.release(index)
        self.assertFalse(boxes.recording)
        self.assertEqual(boxes.preview, "Ctrl+Alt+Down")
        self.assertEqual(boxes.shortcut, Shortcut("Down", ("Control_L", "Alt_L")))

    def test_add_delete_limit_and_all_boxes_required(self):
        boxes = ShortcutBoxes(Shortcut("a"))
        for _ in range(5):
            boxes.add()
        self.assertEqual(len(boxes.values), 6)
        self.assertIsNone(boxes.shortcut)
        with self.assertRaises(ValueError):
            boxes.add()
        for _ in range(5):
            boxes.delete(1)
        self.assertEqual(boxes.shortcut, Shortcut("a"))
        with self.assertRaises(ValueError):
            boxes.delete(0)

    def test_overlapping_keys_and_unsupported_input_are_not_guessed(self):
        boxes = ShortcutBoxes()
        boxes.start()
        boxes.press("Control_L", 1)
        boxes.press("Alt_L", 2)
        self.assertFalse(boxes.recording)
        self.assertIsNone(boxes.shortcut)
        self.assertEqual(boxes.values, [None] * 3)
        boxes.start()
        boxes.press("Tools", 3)
        self.assertIn("not supported", boxes.error)

    def test_repeated_key_press_is_not_recorded_into_more_than_one_box(self):
        boxes = ShortcutBoxes()
        boxes.start()
        for _ in range(5):
            boxes.press("Control_L", 1)
        boxes.release(1)
        self.assertEqual(boxes.values, ["Control_L", None, None])

    def test_stop_focus_loss_idle_and_reset_preserve_only_completed_boxes(self):
        boxes = ShortcutBoxes()
        boxes.start()
        self.tap(boxes, "Control_L", 1)
        boxes.press("Alt_L", 2)
        boxes.stop("Lost focus")
        self.assertEqual(boxes.values, ["Control_L", None, None])
        self.assertIsNone(boxes.held)
        self.tap(boxes, "Down", 3)
        self.assertIsNone(boxes.shortcut)
        boxes.reset()
        self.assertEqual(boxes.values, [None] * 3)

    def test_duplicate_multiple_regular_keys_and_modifier_only_are_invalid(self):
        for keys in (("Control_L", "Control_L", "Down"), ("a", "b", "Control_L"),
                     ("Control_L", "Alt_L", "Shift_L")):
            boxes = ShortcutBoxes()
            boxes.start()
            for i, key in enumerate(keys):
                self.tap(boxes, key, i)
            self.assertIsNone(boxes.shortcut)

    def test_initial_sides_editing_and_legacy_long_chord_are_not_truncated(self):
        initial = Shortcut("Down", ("Control_R", "Alt_R"))
        boxes = ShortcutBoxes(initial)
        self.assertEqual(boxes.shortcut, initial)
        boxes.start(2)
        self.tap(boxes, "Up", 1)
        self.assertEqual(boxes.shortcut, Shortcut("Up", initial.modifiers))
        long = Shortcut("Down", ("Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L", "Shift_R"))
        boxes = ShortcutBoxes(long)
        self.assertIsNone(boxes.shortcut)
        self.assertIn("exceeds six", boxes.error)

    def test_explicit_super_fills_idle_box_without_arming_or_inventing_events(self):
        boxes = ShortcutBoxes()
        self.assertTrue(boxes.insert_super())
        self.assertEqual(boxes.values, ["Super_L", None, None])
        self.assertFalse(boxes.recording)
        self.assertIsNone(boxes.held)
        boxes.start()
        self.tap(boxes, "Control_L", 1)
        self.tap(boxes, "Left", 2)
        self.assertEqual(boxes.shortcut, Shortcut("Left", ("Control_L", "Super_L")))

    def test_explicit_super_replaces_only_armed_box_and_advances_existing_recording(self):
        boxes = ShortcutBoxes(Shortcut("Left", ("Control_L", "Alt_L")))
        boxes.start(1)
        self.assertTrue(boxes.insert_super())
        self.assertEqual(boxes.shortcut, Shortcut("Left", ("Control_L", "Super_L")))
        self.assertFalse(boxes.recording)
        boxes.reset()
        boxes.start(1)
        boxes.insert_super()
        self.assertEqual(boxes.values, [None, "Super_L", None])
        self.assertEqual(boxes.active, 2)

    def test_intercepted_super_is_not_inferred_and_explicit_choice_does_not_resume(self):
        boxes = ShortcutBoxes()
        boxes.start()
        self.tap(boxes, "Control_L", 1)
        boxes.press("Super_L", 2)
        boxes.stop("Lost focus")
        self.assertEqual(boxes.values, ["Control_L", None, None])
        boxes.insert_super()
        self.assertEqual(boxes.values, ["Control_L", "Super_L", None])
        self.assertFalse(boxes.recording)
        self.assertIsNone(boxes.held)
        boxes.release(2)  # A delayed release must not fill another box.
        self.assertEqual(boxes.values, ["Control_L", "Super_L", None])

    def test_super_does_not_overwrite_full_chord_or_accept_held_keys_or_hide_duplicates(self):
        original = Shortcut("Left", ("Control_L", "Alt_L"))
        boxes = ShortcutBoxes(original)
        self.assertFalse(boxes.insert_super())
        self.assertEqual(boxes.shortcut, original)
        boxes.start(1)
        boxes.press("Shift_L", 1)
        self.assertFalse(boxes.insert_super())
        self.assertEqual(boxes.shortcut, original)
        self.assertFalse(boxes.recording)
        self.assertIsNone(boxes.held)
        boxes.reset()
        boxes.insert_super()
        boxes.insert_super()
        boxes.start(2)
        self.tap(boxes, "Left", 2)
        self.assertIsNone(boxes.shortcut)
        self.assertIn("different", boxes.validation)
