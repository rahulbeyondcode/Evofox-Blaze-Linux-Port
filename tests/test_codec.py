import unittest

from evofox_blaze.codec import encode_command18


class Command18Tests(unittest.TestCase):
    def encode(self, **changes):
        values = dict(flags=3, index=0, base=0x1234, data=0xAB, control=2, report_length=8)
        return encode_command18(**(values | changes))

    def test_data_frame_golden_bytes(self):
        # Layout recovered at 0x413910; phase 03 from 0x413a10's data loop.
        self.assertEqual(self.encode(), bytes.fromhex("07 18 03 00 34 12 ab 02"))

    def test_phase_09_frame_golden_bytes(self):
        self.assertEqual(self.encode(flags=9, data=0), bytes.fromhex("07 18 09 00 34 12 00 02"))

    def test_phase_05_frame_golden_bytes(self):
        # 0x413ac0's request layout; fixture only, not a hardware read command.
        self.assertEqual(self.encode(flags=5, index=1, data=0), bytes.fromhex("07 18 05 01 34 12 00 02"))

    def test_zero_frame_golden_bytes(self):
        self.assertEqual(self.encode(flags=0, base=0, data=0, control=0), bytes.fromhex("07 18 00 00 00 00 00 00"))

    def test_no_silent_truncation_or_type_coercion(self):
        for field in ("flags", "index", "base", "data", "control"):
            for value in (-1, 65536 if field == "base" else 256, True, 1.0, "1"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.encode(**{field: value})

    def test_rejects_other_report_lengths(self):
        for length in (0, 7, 9, 256, 8.0, "8"):
            with self.subTest(length=length), self.assertRaises(ValueError):
                self.encode(report_length=length)


if __name__ == "__main__":
    unittest.main()
