from pathlib import Path
import hashlib
import json
import tempfile
import unittest

from evofox_blaze.hid_descriptor import parse_report_descriptor
from evofox_blaze.probe import capture, configuration_report


# Actual interface 1 descriptor, 30fa:1440 / bcdDevice 0100.
COMPOSITE = bytes.fromhex(
    "05 01 09 06 a1 01 85 03 05 07 19 e0 29 e7 15 00 25 01 95 08 75 01 81 02 "
    "95 06 75 08 15 00 26 ff 00 05 07 19 00 29 e7 81 00 c0 "
    "05 0c 09 01 a1 01 85 02 19 00 2a 9c 02 15 00 26 9c 02 95 01 75 10 81 00 c0 "
    "06 00 ff 09 01 a1 01 85 06 15 00 26 ff 00 09 2f 95 02 75 08 81 02 c0 "
    "06 01 ff 09 01 a1 01 85 07 15 00 26 ff 00 09 20 95 07 75 08 b1 02 c0 "
    "05 01 09 80 a1 01 85 08 19 81 29 83 15 00 25 01 75 01 95 03 81 02 95 05 81 01 c0"
)


class DescriptorTests(unittest.TestCase):
    def test_saved_hardware_capture_matches_parser_and_hashes(self):
        path = Path(__file__).resolve().parents[1] / "docs/device-captures/2026-10-23-30fa-1440-0100/probe.json"
        capture_ = json.loads(path.read_text())
        for node in capture_["nodes"]:
            raw = bytes.fromhex(node["report_descriptor_hex"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), node["report_descriptor_sha256"])
            descriptor = parse_report_descriptor(raw)
            observed = {(r.kind, r.report_id): r.byte_length for r in descriptor.reports}
            recorded = {(r["kind"], r["report_id"]): r["byte_length"] for r in node["reports"]}
            self.assertEqual(observed, recorded)
            if node["interface"]["bInterfaceNumber"] == "01":
                self.assertEqual(raw, COMPOSITE)

    def test_composite_collections_share_one_node(self):
        descriptor = parse_report_descriptor(COMPOSITE)
        self.assertEqual([(c.usage_page, c.usage) for c in descriptor.collections],
                         [(1, 6), (12, 1), (0xFF00, 1), (0xFF01, 1), (1, 0x80)])
        report = configuration_report(descriptor)
        self.assertEqual(report.byte_length, 8)
        self.assertEqual(report.payload_bits, 56)
        self.assertEqual(report.collection_indices, (3,))

    def test_report_sizes_include_padding_and_id(self):
        descriptor = parse_report_descriptor(COMPOSITE)
        self.assertEqual({(r.kind, r.report_id): r.byte_length for r in descriptor.reports},
                         {("input", 2): 3, ("input", 3): 8, ("input", 6): 3,
                          ("input", 8): 2, ("feature", 7): 8})

    def test_wrong_usage_is_not_configuration(self):
        descriptor = parse_report_descriptor(COMPOSITE.replace(b"\x06\x01\xff", b"\x06\x02\xff"))
        self.assertIsNone(configuration_report(descriptor))

    def test_report_07_must_belong_to_configuration_collection(self):
        raw = bytes.fromhex("06 01 ff 09 01 a1 01 85 06 75 08 95 07 81 02 c0 "
                            "06 00 ff 09 01 a1 01 85 07 75 08 95 07 b1 02 c0")
        self.assertIsNone(configuration_report(parse_report_descriptor(raw)))

    def test_unnumbered_report_has_no_wire_id_byte(self):
        raw = bytes.fromhex("05 01 09 02 a1 01 75 01 95 03 81 02 c0")
        self.assertEqual(parse_report_descriptor(raw).reports[0].byte_length, 1)

    def test_global_push_pop_and_nested_collection(self):
        raw = bytes.fromhex("05 01 09 02 a1 01 09 01 a1 00 75 08 95 02 a4 "
                            "75 01 95 03 81 02 b4 81 02 c0 c0")
        descriptor = parse_report_descriptor(raw)
        self.assertEqual(descriptor.reports[0].payload_bits, 19)
        self.assertEqual(descriptor.reports[0].collection_indices, (0,))
        self.assertEqual(descriptor.collections[1].parent, 0)

    def test_32bit_usage_contains_its_own_page(self):
        raw = bytes.fromhex("0b 01 00 01 ff a1 01 85 07 75 08 95 07 b1 02 c0")
        self.assertEqual(configuration_report(parse_report_descriptor(raw)).byte_length, 8)

    def test_malformed_descriptors_fail_closed(self):
        for raw in (b"", b"\x06\x01", b"\xc0", b"\xb4", b"\xfe\x00\x00",
                    bytes.fromhex("05 01 09 02 a1 01"),
                    bytes.fromhex("05 01 09 02 a1 01 85 00 c0"),
                    bytes.fromhex("05 01 09 02 a1 01 b1 02 c0")):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_report_descriptor(raw)


class CaptureTests(unittest.TestCase):
    def test_capture_sanitizes_paths_and_preserves_descriptor(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "capture"
            capture([{"path": "/dev/hidraw42", "vid": "30fa", "pid": "1440",
                      "report_descriptor_hex": COMPOSITE.hex(" "),
                      "error": "permission denied /home/private/file"}], output)
            text = (output / "probe.json").read_text()
            self.assertNotIn("hidraw42", text)
            self.assertNotIn("/home/private", text)
            self.assertEqual(json.loads(text)["nodes"][0]["report_descriptor_hex"], COMPOSITE.hex(" "))
            with self.assertRaises(FileExistsError):
                capture([], output)


if __name__ == "__main__":
    unittest.main()
