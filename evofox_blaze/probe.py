"""Linux sysfs-only probe. Never opens a /dev node or sends a HID request."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys

from . import __version__
from .hid_descriptor import Descriptor, Report, parse_report_descriptor


SUPPORTED_IDS = {(0x30FA, 0x1440), (0x30FA, 0x1E01)}


def configuration_report(descriptor: Descriptor) -> Report | None:
    """Return report 07 only when owned by a top-level ff01/0001 collection."""
    owners = {
        index
        for index, collection in enumerate(descriptor.collections)
        if collection.parent is None
        and (collection.usage_page, collection.usage) == (0xFF01, 1)
    }
    return next(
        (
            report
            for report in descriptor.reports
            if report.kind == "feature" and report.report_id == 7
            and owners.intersection(report.collection_indices)
        ),
        None,
    )


def _attributes(path, names):
    return {name: (path / name).read_text().strip() for name in names}


def enumerate_devices(sysfs=Path("/sys/class/hidraw"), dev=Path("/dev")):
    """Read matching USB devices and descriptors; preserve per-node failures."""
    nodes = []
    for entry in sorted(sysfs.glob("hidraw*")):
        try:
            properties = dict(
                line.split("=", 1)
                for line in (entry / "device/uevent").read_text().splitlines()
                if "=" in line
            )
            bus, vendor, product = (
                int(value, 16)
                for value in properties.get("HID_ID", "0:0:0").split(":")
            )
        except (OSError, ValueError):
            continue  # An unreadable identity cannot select a target device.
        if bus != 3 or (vendor, product) not in SUPPORTED_IDS:
            continue
        node = {"path": str(dev / entry.name), "vid": f"{vendor:04x}", "pid": f"{product:04x}"}
        nodes.append(node)
        try:
            device = (entry / "device").resolve(strict=True)
            interface = next(p for p in device.parents if (p / "bInterfaceNumber").exists())
            usb = next(p for p in interface.parents if (p / "idVendor").exists())
            node["usb"] = _attributes(
                usb, ("bcdDevice", "manufacturer", "product", "bNumInterfaces", "speed")
            )
            node["interface"] = _attributes(
                interface,
                ("bInterfaceNumber", "bInterfaceClass", "bInterfaceSubClass", "bInterfaceProtocol"),
            )
            raw = (device / "report_descriptor").read_bytes()
            node["report_descriptor_hex"] = raw.hex(" ")
            node["report_descriptor_sha256"] = hashlib.sha256(raw).hexdigest()
            node["usb_descriptors_hex"] = (usb / "descriptors").read_bytes().hex(" ")
            descriptor = parse_report_descriptor(raw)
            node["collections"] = [asdict(c) for c in descriptor.collections]
            node["reports"] = [dict(asdict(r), byte_length=r.byte_length) for r in descriptor.reports]
            report = configuration_report(descriptor)
            node["configuration_report"] = (
                None if report is None
                else {"report_id": 7, "byte_length": report.byte_length}
            )
            path = dev / entry.name
            node["access"] = {"read": os.access(path, os.R_OK), "write": os.access(path, os.W_OK)}
        except (OSError, ValueError, StopIteration) as error:
            node["error"] = f"{type(error).__name__}: {error}"
            node["error_type"] = type(error).__name__
    return nodes


def capture(nodes, output):
    """Write a new sanitized snapshot; never overwrite a previous capture."""
    output.mkdir(parents=True, exist_ok=False)
    sanitized = []
    for index, node in enumerate(nodes):
        saved = {key: value for key, value in node.items() if key not in ("path", "error")}
        saved["capture_node"] = index
        if "error" in node:
            # Exception messages may include private host paths.
            saved["error"] = "Incomplete node inspection; rerun the probe locally for diagnostics"
        sanitized.append(saved)
    result = {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "tool": f"evofox_blaze.probe {__version__}",
        "command": "python3 -m evofox_blaze.probe --capture <new-directory>",
        "environment": {
            "kernel": platform.release(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
        },
        "device_interaction": "sysfs reads only; no device nodes opened or feature requests sent",
        "nodes": sanitized,
    }
    (output / "probe.json").write_text(json.dumps(result, indent=2) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, help="save a sanitized snapshot to a NEW directory")
    args = parser.parse_args(argv)
    nodes = enumerate_devices()
    print(json.dumps({"nodes": nodes}, indent=2))
    if args.capture:
        try:
            capture(nodes, args.capture)
        except OSError as error:
            print(f"Capture failed: {error}", file=sys.stderr)
            return 1
    if not nodes:
        print("No supported USB HID device found", file=sys.stderr)
        return 1
    if any("error" in node for node in nodes):
        return 1
    if not any(node.get("configuration_report") for node in nodes):
        print("No ff01/0001 collection with feature report 07 found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
