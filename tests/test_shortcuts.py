import unittest

from evofox_blaze.shortcuts import Shortcut, ShortcutRecorder


class ShortcutTests(unittest.TestCase):
    def test_symbolic_shortcut_has_canonical_order_and_preserves_modifier_sides(self):
        shortcut = Shortcut("Left", ("Super_L", "Control_L", "Shift_R"))
        self.assertEqual(shortcut.modifiers, ("Control_L", "Shift_R", "Super_L"))
        self.assertEqual(shortcut.label, "Ctrl+Right Shift+Super+Left")
        self.assertEqual(shortcut, Shortcut("Left", ("Control_L", "Shift_R", "Super_L")))
        self.assertNotEqual(Shortcut("a", ("Alt_R",)), Shortcut("a", ("Alt_L",)))

    def test_invalid_key_modifier_or_duplicate_is_refused_not_guessed(self):
        for key in (None, [], "dead_acute", "ISO_Level3_Shift", "Ctrl+C", "A", "macro"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                Shortcut(key)
        for modifiers in ([], ("Ctrl",), ("Control_L", "Control_L"), (None,), ([],)):
            with self.subTest(modifiers=modifiers), self.assertRaises(ValueError):
                Shortcut("a", modifiers)

    def test_standard_keys_and_unmodified_keys_have_readable_labels(self):
        for key, label in (("a", "A"), ("1", "1"), ("F12", "F12"), ("space", "Space"),
                           ("Return", "Enter"), ("Escape", "Esc"), ("slash", "/")):
            self.assertEqual(Shortcut(key).label, label)


class ShortcutRecorderTests(unittest.TestCase):
    def setUp(self):
        self.recorder = ShortcutRecorder()

    def chord(self):
        self.recorder.press("Control_L", 37)
        self.recorder.press("Super_L", 133)
        self.recorder.press("Left", 113)

    def test_idle_input_is_ignored_until_explicitly_started(self):
        self.chord()
        self.recorder.release(113)
        self.assertIsNone(self.recorder.shortcut)
        self.assertEqual(self.recorder.held, {})

    def test_chord_completes_only_after_all_keys_are_released(self):
        self.recorder.start()
        self.chord()
        self.assertEqual(self.recorder.preview, "Ctrl+Super+Left")
        for code in (37, 113):
            self.recorder.release(code)
            self.assertTrue(self.recorder.recording)
            self.assertIsNone(self.recorder.shortcut)
        self.recorder.release(133)
        self.assertFalse(self.recorder.recording)
        self.assertEqual(self.recorder.shortcut, Shortcut("Left", ("Control_L", "Super_L")))
        self.assertEqual(self.recorder.held, {})

    def test_auto_repeat_does_not_add_more_keys(self):
        self.recorder.start()
        for _ in range(5):
            self.recorder.press("a", 38)
        self.recorder.release(38)
        self.assertEqual(self.recorder.shortcut, Shortcut("a"))

    def test_modifier_only_does_not_finish_or_leak_into_next_chord(self):
        self.recorder.start()
        self.recorder.press("Alt_L", 64)
        self.assertEqual(self.recorder.preview, "Alt+…")
        self.recorder.release(64)
        self.assertTrue(self.recorder.recording)
        self.recorder.press("a", 38)
        self.recorder.release(38)
        self.assertEqual(self.recorder.shortcut, Shortcut("a"))

    def test_modifier_added_while_main_key_is_held_is_included(self):
        self.recorder.start()
        self.recorder.press("a", 38)
        self.recorder.press("Control_R", 105)
        self.recorder.release(38)
        self.recorder.release(105)
        self.assertEqual(self.recorder.shortcut, Shortcut("a", ("Control_R",)))

    def test_multiple_main_keys_or_sequences_are_rejected(self):
        for released in (False, True):
            self.recorder.start()
            self.recorder.press("Control_L", 37)
            self.recorder.press("a", 38)
            if released:
                self.recorder.release(38)
            self.recorder.press("b", 56)
            for code in (38, 56, 37):
                self.recorder.release(code)
            self.assertIsNone(self.recorder.shortcut)
            self.assertIn("not a sequence", self.recorder.error)
            self.assertFalse(self.recorder.recording)

    def test_unsupported_key_is_rejected_until_release_without_guessing(self):
        self.recorder.start()
        self.recorder.press(None, 204)
        self.assertTrue(self.recorder.recording)
        self.recorder.release(204)
        self.assertFalse(self.recorder.recording)
        self.assertIsNone(self.recorder.shortcut)
        self.assertIn("not supported", self.recorder.error)

    def test_focus_timeout_stop_and_cancel_can_clear_partial_input(self):
        self.recorder.start()
        self.chord()
        self.recorder.abort("Lost focus")
        self.assertFalse(self.recorder.recording)
        self.assertEqual(self.recorder.held, {})
        self.assertIsNone(self.recorder.shortcut)
        self.assertEqual(self.recorder.error, "Lost focus")
        self.recorder.start()
        self.assertEqual(self.recorder.error, "")
        self.recorder.press("Escape", 9)
        self.recorder.release(9)
        self.assertEqual(self.recorder.shortcut, Shortcut("Escape"))
        self.recorder.cancel()
        self.assertIsNone(self.recorder.shortcut)

    def test_focus_loss_keeps_an_observed_chord_even_when_releases_are_intercepted(self):
        self.recorder.start()
        self.chord()
        self.recorder.interrupt()
        self.assertFalse(self.recorder.recording)
        self.assertEqual(self.recorder.held, {})
        self.assertEqual(self.recorder.shortcut, Shortcut("Left", ("Control_L", "Super_L")))
        self.assertIn("kept", self.recorder.error)
        self.recorder.press("a", 38)  # No capture continues outside focus.
        self.assertEqual(self.recorder.shortcut.key, "Left")

    def test_intercepted_main_key_is_not_guessed_from_modifiers(self):
        self.recorder.start()
        self.recorder.press("Control_L", 37)
        self.recorder.press("Alt_L", 64)
        self.recorder.interrupt()  # Down never reached this application.
        self.assertIsNone(self.recorder.shortcut)
        self.assertEqual(self.recorder.preview, "Ctrl+Alt+…")
        self.assertEqual(self.recorder.interrupted_modifiers, ("Control_L", "Alt_L"))
        self.assertEqual(self.recorder.held, {})
        self.assertFalse(self.recorder.recording)
        self.recorder.start()
        self.assertIsNone(self.recorder.interrupted_preview)
        self.assertEqual(self.recorder.interrupted_modifiers, ())

    def test_invalid_sequence_cannot_be_preserved_as_a_valid_shortcut_on_focus_loss(self):
        self.recorder.start()
        self.recorder.press("a", 38)
        self.recorder.press("b", 56)
        self.recorder.interrupt()
        self.assertIsNone(self.recorder.shortcut)
        self.assertFalse(self.recorder.recording)
