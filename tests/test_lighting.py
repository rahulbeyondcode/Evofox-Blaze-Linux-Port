import contextlib
from dataclasses import FrozenInstanceError
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from evofox_blaze.lighting import Command13Frame, main, model_storage_brightness, preview_brightness


# Synthetic outbound data; this was never acquired from or sent to the mouse.
SYNTHETIC = bytes.fromhex("07 13 81 92 a3 04 b5 c6")


class LightingTests(unittest.TestCase):
    def test_static_fixture_examples_and_observed_byte_position(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/lighting-brightness-observations.json").read_text())
        brightness = fixture["brightness"]
        for example in fixture["synthetic_examples"]:
            with self.subTest(example=example):
                original = Command13Frame(bytes.fromhex(example["input_hex"]))
                self.assertEqual(original.raw[0], brightness["report_id"])
                self.assertEqual(original.raw[1], brightness["command"])
                self.assertEqual(original.brightness_code,
                                 original.raw[brightness["byte_offset"]] & brightness["mask"])
                self.assertEqual(original.with_brightness_code(example["brightness_code"]).raw,
                                 bytes.fromhex(example["output_hex"]))
        self.assertFalse(fixture["readback_assessment"]["restore_path_established"])

    def test_synthetic_golden_frame_changes_only_brightness(self):
        frame = Command13Frame(SYNTHETIC)
        self.assertEqual(frame.brightness_code, 4)
        modified = frame.with_brightness_code(2)
        self.assertEqual(modified.raw, bytes.fromhex("07 13 81 92 a3 02 b5 c6"))
        self.assertEqual(frame.raw, SYNTHETIC)

    def test_all_codes_round_trip_without_altering_context(self):
        for old in range(8):
            original = Command13Frame(SYNTHETIC[:5] + bytes((old,)) + SYNTHETIC[6:])
            for new in range(8):
                with self.subTest(old=old, new=new):
                    modified = original.with_brightness_code(new)
                    self.assertEqual(modified.brightness_code, new)
                    self.assertEqual(modified.raw[:5], original.raw[:5])
                    self.assertEqual(modified.raw[6:], original.raw[6:])
                    # Byte reversibility only, not hardware restore evidence.
                    self.assertEqual(modified.with_brightness_code(old), original)

    def test_context_bytes_remain_opaque(self):
        for index in (2, 3, 4, 6, 7):
            for value in range(256):
                raw = bytearray(SYNTHETIC)
                raw[index] = value
                with self.subTest(index=index, value=value):
                    modified = Command13Frame(bytes(raw)).with_brightness_code(7)
                    self.assertEqual(modified.raw[index], value)

    def test_rejects_get_reply_other_commands_and_malformed_frames(self):
        for raw in (b"", bytes(8), SYNTHETIC[:-1], SYNTHETIC + b"\0",
                    bytes.fromhex("07 00 58 09 1f 00 23 7b"),
                    bytes.fromhex("07 18 05 00 18 00 00 07"),
                    bytearray(SYNTHETIC), SYNTHETIC.hex(), None):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                Command13Frame(raw)

    def test_rejects_unobserved_upper_bits_in_brightness_byte(self):
        for value in range(8, 256):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Command13Frame(SYNTHETIC[:5] + bytes((value,)) + SYNTHETIC[6:])

    def test_rejects_silent_truncation_and_coercion(self):
        for value in (-1, 8, 256, True, False, 2.0, "2", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Command13Frame(SYNTHETIC).with_brightness_code(value)

    def test_frame_is_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            Command13Frame(SYNTHETIC).raw = bytes(8)

    def test_preview_never_claims_backup_or_hardware_safety(self):
        result = preview_brightness(Command13Frame(SYNTHETIC), 2)
        self.assertFalse(result["hardware_validated"])
        self.assertFalse(result["original_device_value_known"])
        self.assertFalse(result["safe_to_send"])
        self.assertEqual(result["changed_byte_offsets"], [5])
        unchanged = preview_brightness(Command13Frame(SYNTHETIC), 4)
        self.assertEqual(unchanged["changed_byte_offsets"], [])

    def test_cli_is_offline(self):
        output = io.StringIO()
        with patch("os.open", side_effect=AssertionError("No device open")), \
                patch("evofox_blaze.probe.enumerate_devices", side_effect=AssertionError("No enumeration")), \
                contextlib.redirect_stdout(output):
            self.assertEqual(main(["--command13", SYNTHETIC.hex(), "--brightness-code", "2"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["preview_command_hex"], "07 13 81 92 a3 02 b5 c6")
        self.assertFalse(result["safe_to_send"])

    def test_cli_reports_invalid_input(self):
        for raw, code in (("not hex", "2"), (SYNTHETIC.hex(), "8"),
                          ("07 00 58 09 1f 00 23 7b", "2")):
            with self.subTest(raw=raw, code=code), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--command13", raw, "--brightness-code", code]), 1)


class StorageArithmeticTests(unittest.TestCase):
    def test_fixture_examples_match_native_arithmetic(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/lighting-storage-observations.json").read_text())
        for example in fixture["synthetic_examples"]:
            with self.subTest(example=example):
                result = model_storage_brightness(code=example["code"], companion=example["companion"],
                                                  mode_enabled=example["mode_enabled"])
                self.assertEqual(result["serialized_byte_hex"], example["byte_hex"])
                self.assertEqual(result["brightness_isolated_in_bits_4_to_6"], example["isolated"])

    def test_both_writer_argument_paths_reach_the_same_candidate(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/lighting-storage-observations.json").read_text())
        for source in fixture["serializer_paths"]:
            base = source["initial_base"] + sum(source["base_increments"])
            self.assertEqual(base, source["writer_base"])
            self.assertLess(source["brightness_byte_index"], source["length"])
            self.assertEqual(base + source["brightness_byte_index"], fixture["candidate_logical_byte"])

    def test_storage_candidate_does_not_expand_observed_reads(self):
        from evofox_blaze.read_preview import OBSERVED_READS, preview_read
        candidate = 0x3F
        self.assertFalse(any(region.base <= candidate < region.base + region.length
                             for region in OBSERVED_READS.values()))
        with self.assertRaises(ValueError):
            preview_read("lighting-brightness", report_length=8)

    def test_companion_addition_and_byte_truncation_are_not_replaced_with_or(self):
        for code in range(8):
            for companion in range(-256, 257):
                result = model_storage_brightness(code=code, companion=companion, mode_enabled=True)
                self.assertEqual(int(result["serialized_byte_hex"], 16), ((code * 16) + companion) % 256)
                self.assertEqual(result["brightness_isolated_in_bits_4_to_6"], 0 <= companion <= 15)
        result = model_storage_brightness(code=1, companion=16, mode_enabled=True)
        self.assertEqual(result["serialized_byte_hex"], "20")  # OR would give 10.

    def test_disabled_branch_overrides_both_cached_values(self):
        for code in range(8):
            for companion in (-(1 << 31), -1, 0, 15, 16, (1 << 31) - 1):
                result = model_storage_brightness(code=code, companion=companion, mode_enabled=False)
                self.assertEqual(result["serialized_byte_hex"], "00")
                self.assertFalse(result["brightness_isolated_in_bits_4_to_6"])

    def test_signed_int32_companion_boundaries_match_low_byte_semantics(self):
        for companion in (-(1 << 31), (1 << 31) - 1):
            result = model_storage_brightness(code=7, companion=companion, mode_enabled=True)
            self.assertEqual(int(result["serialized_byte_hex"], 16), (112 + companion) & 255)

    def test_bad_values_are_not_coerced_or_silently_truncated(self):
        for code in (-1, 8, True, 1.0, "1", None):
            with self.subTest(code=code), self.assertRaises(ValueError):
                model_storage_brightness(code=code, companion=0, mode_enabled=True)
        for companion in (-(1 << 31) - 1, 1 << 31, True, 1.0, "0", None):
            with self.subTest(companion=companion), self.assertRaises(ValueError):
                model_storage_brightness(code=1, companion=companion, mode_enabled=True)
        for enabled in (0, 1, "enabled", None):
            with self.subTest(enabled=enabled), self.assertRaises(ValueError):
                model_storage_brightness(code=1, companion=0, mode_enabled=enabled)

    def test_storage_cli_is_offline_and_does_not_generate_a_report(self):
        output = io.StringIO()
        with patch("os.open", side_effect=AssertionError("No device open")), contextlib.redirect_stdout(output):
            self.assertEqual(main(["--storage-companion", "16", "--storage-mode", "enabled",
                                   "--brightness-code", "1"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["serialized_byte_hex"], "20")
        self.assertEqual(result["candidate_logical_byte"], "0x003f")
        self.assertNotIn("preview_command_hex", result)
        self.assertFalse(result["original_device_value_known"])
        self.assertFalse(result["safe_to_send"])

    def test_cli_requires_explicit_guard_and_rejects_mixed_context(self):
        for args in (["--storage-companion", "0", "--brightness-code", "4"],
                     ["--storage-mode", "enabled", "--command13", SYNTHETIC.hex(), "--brightness-code", "4"],
                     ["--storage-companion", "0", "--command13", SYNTHETIC.hex(), "--brightness-code", "4"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                main(args)
            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
