import contextlib
from dataclasses import FrozenInstanceError
import io
import json
from pathlib import Path
import unittest

from evofox_blaze.read_preview import (
    Delay, GetFeature, OBSERVED_READS, SetFeature, decode_dpi_selector,
    main, preview_read,
)


class ReadPreviewTests(unittest.TestCase):
    def test_source_observed_bases_and_lengths_only(self):
        path = Path(__file__).parent / "fixtures/vendor-read-observations.json"
        fixture = json.loads(path.read_text())
        expected = {r["name"]: (r["base"], r["length"], tuple(r["call_sites"]))
                    for r in fixture["regions"]}
        self.assertEqual({name: (r.base, r.length, r.call_sites)
                          for name, r in OBSERVED_READS.items()}, expected)
        with self.assertRaises(ValueError):
            preview_read("0x1234", report_length=8)

    def test_preparation_and_read_order_matches_instructions(self):
        steps = preview_read("dpi-state", report_length=8)
        for index in range(8):
            self.assertEqual(steps[index * 2], SetFeature(bytes.fromhex(
                f"07 18 03 {index:02x} 18 00 00 07")))
            self.assertEqual(steps[index * 2 + 1], Delay(2))
        self.assertEqual(steps[16], Delay(2))
        self.assertEqual(steps[17], SetFeature(bytes.fromhex("07 18 00 00 18 00 00 00")))
        for index in range(8):
            start = 18 + index * 3
            self.assertEqual(steps[start], SetFeature(bytes.fromhex(
                f"07 18 05 {index:02x} 18 00 00 07")))
            self.assertEqual(steps[start + 1], Delay(2))
            self.assertEqual(steps[start + 2], GetFeature(7, 8, 1))
        self.assertEqual(steps[-2], Delay(2))
        # Final read close resets the base too; preparation close retains it.
        self.assertEqual(steps[-1], SetFeature(bytes.fromhex("07 18 00 00 00 00 00 00")))

    def test_counts_delays_and_no_phase_09_commit(self):
        for name in OBSERVED_READS:
            with self.subTest(name=name):
                steps = preview_read(name, report_length=8)
                writes = [s for s in steps if isinstance(s, SetFeature)]
                self.assertEqual(len(steps), 44)
                self.assertEqual(len(writes), 18)
                self.assertEqual(sum(isinstance(s, GetFeature) for s in steps), 8)
                self.assertEqual(sum(s.milliseconds for s in steps if isinstance(s, Delay)), 36)
                self.assertNotIn(9, [s.report[2] for s in writes])
                self.assertTrue(all(len(s.report) == 8 for s in writes))

    def test_comparison_base_is_little_endian(self):
        steps = preview_read("comparison-3", report_length=8)
        self.assertEqual(steps[0], SetFeature(bytes.fromhex("07 18 03 00 b8 0f 00 07")))

    def test_rejects_unverified_report_sizes(self):
        for size in (0, 7, 9, 8.0):
            with self.subTest(size=size), self.assertRaises(ValueError):
                preview_read("dpi-state", report_length=size)

    def test_steps_are_immutable(self):
        steps = preview_read("dpi-state", report_length=8)
        self.assertIsInstance(steps, tuple)
        with self.assertRaises(FrozenInstanceError):
            steps[0].report = b"changed"

    def test_selector_does_not_invent_cpi_or_clamp_unknown_values(self):
        for first in range(256):
            block = bytes((first,)) + bytes(7)
            self.assertEqual(decode_dpi_selector(block), first & 7)
        for invalid in (b"", bytes(7), bytes(9), "12345678", bytearray(8)):
            with self.subTest(block=invalid), self.assertRaises(ValueError):
                decode_dpi_selector(invalid)

    def test_cli_labels_output_as_an_unvalidated_preview(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["dpi-state", "--report-length", "8"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["mode"], "offline-preview")
        self.assertFalse(result["hardware_validated"])
        self.assertEqual(result["set_feature_count"], 18)
        self.assertEqual(result["base"], "0x0018")


if __name__ == "__main__":
    unittest.main()
