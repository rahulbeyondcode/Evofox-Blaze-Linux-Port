import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evofox_blaze import probe


FEATURE = bytes.fromhex("06 01 ff 09 01 a1 01 85 07 75 08 95 07 b1 02 c0")


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sysfs = self.root / "hidraw"
        self.sysfs.mkdir()
        self.dev = self.root / "dev"
        self.dev.mkdir()

    def add_node(self, name="hidraw99", pid="1440", descriptor=FEATURE):
        usb = self.root / name / "usb"
        interface = usb / "interface"
        device = interface / "hid"
        device.mkdir(parents=True)
        for key, value in {
            "idVendor": "30fa", "idProduct": pid, "bcdDevice": "0100",
            "manufacturer": "INSTANT", "product": "USB GAMING MOUSE",
            "bNumInterfaces": "2", "speed": "12",
        }.items():
            (usb / key).write_text(value + "\n")
        (usb / "descriptors").write_bytes(bytes.fromhex("12 01 10 01"))
        for key, value in {
            "bInterfaceNumber": "01", "bInterfaceClass": "03",
            "bInterfaceSubClass": "00", "bInterfaceProtocol": "01",
        }.items():
            (interface / key).write_text(value + "\n")
        (device / "uevent").write_text(f"HID_ID=0003:000030FA:0000{pid}\n")
        (device / "report_descriptor").write_bytes(descriptor)
        entry = self.sysfs / name
        entry.mkdir()
        (entry / "device").symlink_to(device, target_is_directory=True)
        # This sentinel is not a real device; no file in /dev is needed.
        return device

    def test_enumerates_by_identity_not_number_without_opening_dev(self):
        self.add_node()
        self.add_node("hidraw2", pid="1e01")
        self.add_node("hidraw0", pid="9999")
        original = Path.open

        def no_dev_open(path, *args, **kwargs):
            self.assertFalse(path.is_relative_to(self.dev), "Probe tried to open a device node")
            return original(path, *args, **kwargs)

        with patch.object(Path, "open", no_dev_open):
            nodes = probe.enumerate_devices(self.sysfs, self.dev)
        self.assertEqual({n["pid"] for n in nodes}, {"1440", "1e01"})
        self.assertEqual(len(nodes), 2)
        self.assertTrue(all(n["configuration_report"]["byte_length"] == 8 for n in nodes))
        self.assertTrue(all(n["access"] == {"read": False, "write": False} for n in nodes))

    def test_bad_descriptor_is_reported_not_silently_accepted(self):
        self.add_node(descriptor=b"\x06")
        nodes = probe.enumerate_devices(self.sysfs, self.dev)
        self.assertEqual(len(nodes), 1)
        self.assertIn("Truncated HID item", nodes[0]["error"])
        self.assertNotIn("configuration_report", nodes[0])
        self.assertEqual(nodes[0]["report_descriptor_hex"], "06")

    def test_disconnected_node_is_reported(self):
        device = self.add_node()
        (device / "report_descriptor").unlink()
        nodes = probe.enumerate_devices(self.sysfs, self.dev)
        self.assertIn("error", nodes[0])

    def test_cli_rejects_no_device_wrong_collection_and_partial_capture(self):
        for nodes in ([], [{"configuration_report": None}], [{"error": "unreadable"}]):
            with self.subTest(nodes=nodes), patch.object(probe, "enumerate_devices", return_value=nodes):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(probe.main([]), 1)

    def test_cli_success_and_capture(self):
        self.add_node()
        nodes = probe.enumerate_devices(self.sysfs, self.dev)
        destination = self.root / "snapshot"
        with patch.object(probe, "enumerate_devices", return_value=nodes):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(probe.main(["--capture", str(destination)]), 0)
        saved = json.loads((destination / "probe.json").read_text())
        self.assertNotIn(str(self.root), json.dumps(saved))
        self.assertEqual(saved["nodes"][0]["configuration_report"]["byte_length"], 8)


if __name__ == "__main__":
    unittest.main()
