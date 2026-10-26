import unittest

from evofox_blaze.shortcut_codec import (KEY_USAGES, MODIFIER_USAGES, KeyboardEvent, KeyboardRecord,
                                         decode_keyboard_record, encode_descriptor, encode_shortcut)
from evofox_blaze.shortcuts import KEY_LABELS, MODIFIER_LABELS, Shortcut


class ShortcutCodecTests(unittest.TestCase):
    def test_ui_symbols_are_covered_by_source_verified_usages(self):
        self.assertEqual(set(KEY_USAGES), set(KEY_LABELS))
        self.assertEqual(set(MODIFIER_USAGES), set(MODIFIER_LABELS))
        self.assertEqual(len(set(KEY_USAGES.values())), len(KEY_USAGES))
        self.assertEqual(KEY_USAGES["F13"], 0x68)
        self.assertEqual(KEY_USAGES["F24"], 0x73)
        self.assertEqual(MODIFIER_USAGES["Control_R"], 0xe4)

    def test_balanced_ctrl_super_left_record_has_exact_source_event_bytes(self):
        shortcut = Shortcut("Left", ("Control_L", "Super_L"))
        record = encode_shortcut(shortcut)
        self.assertEqual(record.encode().hex(" "), "01 00 8a e0 8a e3 8a 50 0a 50 0a e3 0a e0 00 00")
        self.assertEqual(record.as_shortcut(), shortcut)
        self.assertEqual(decode_keyboard_record(record.encode(), 6), record)
        self.assertEqual(encode_descriptor(0x438, record).hex(" "), "00 06 ff b7 00 38 04 00 00 00")

    def test_every_supported_key_and_modifier_roundtrips(self):
        for key in KEY_LABELS:
            for modifiers in ((), ("Control_L",), tuple(MODIFIER_LABELS)):
                shortcut = Shortcut(key, modifiers)
                record = encode_shortcut(shortcut)
                encoded = record.encode()
                self.assertEqual(len(encoded) % 8, 0)
                self.assertLessEqual(len(encoded), 40)
                self.assertEqual(decode_keyboard_record(encoded, len(record.events)).as_shortcut(), shortcut)

    def test_press_only_old_records_require_explicit_decoder_permission(self):
        record = KeyboardRecord((KeyboardEvent(0xe0, True, 1), KeyboardEvent(0xe3, True, 1),
                                 KeyboardEvent(0x50, True, 1)))
        self.assertEqual(len(record.encode()), 8)
        self.assertEqual(record.as_shortcut(allow_press_only=True), Shortcut("Left", ("Control_L", "Super_L")))
        with self.assertRaises(ValueError):
            record.as_shortcut()
        with self.assertRaises(ValueError):
            encode_descriptor(0x438, record)

    def test_mixed_macro_events_and_incomplete_or_zero_delay_data_are_not_guessed(self):
        for data, count in ((b"", 1), (bytes(8), 1), (bytes.fromhex("01 00 81 f8"), 1),
                             (bytes.fromhex("01 00 81 04"), True), (bytearray(8), 1)):
            with self.subTest(data=data, count=count), self.assertRaises(ValueError):
                decode_keyboard_record(data, count)

    def test_invalid_timing_types_and_modifiers_are_refused(self):
        for event in ((True, True, 1), (4, 1, 1), (4, True, 0), (4, True, 128), (4, True, True)):
            with self.subTest(event=event), self.assertRaises(ValueError):
                KeyboardEvent(*event)
        for ticks in (0, 128, True, None):
            with self.assertRaises(ValueError):
                encode_shortcut(Shortcut("a"), ticks=ticks)

    def test_repeated_sequences_multiple_main_keys_or_release_reordering_are_not_chords(self):
        sequences = (
            KeyboardRecord((KeyboardEvent(4, True, 1), KeyboardEvent(4, False, 1)), repeat_count=2),
            KeyboardRecord((KeyboardEvent(4, True, 1), KeyboardEvent(5, True, 1),
                            KeyboardEvent(5, False, 1), KeyboardEvent(4, False, 1))),
            KeyboardRecord((KeyboardEvent(0xe0, True, 1), KeyboardEvent(4, True, 1),
                            KeyboardEvent(0xe0, False, 1), KeyboardEvent(4, False, 1))),
        )
        for record in sequences:
            with self.subTest(record=record), self.assertRaises(ValueError):
                record.as_shortcut()

    def test_descriptor_does_not_infer_arbitrary_addresses_or_silently_overflow(self):
        record = encode_shortcut(Shortcut("a"))
        for pointer in (True, 0, 0x3f8, 0x401, 0xf20, 0x4000):
            with self.subTest(pointer=pointer), self.assertRaises(ValueError):
                encode_descriptor(pointer, record)
        with self.assertRaises(ValueError):
            encode_descriptor(0xf18, encode_shortcut(Shortcut("a", tuple(MODIFIER_LABELS))))
        for tick in (0, 257, True):
            with self.assertRaises(ValueError):
                encode_descriptor(0x438, record, tick_milliseconds=tick)
