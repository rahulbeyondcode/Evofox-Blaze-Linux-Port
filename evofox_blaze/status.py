"""Offline interpretation of standalone GET_FEATURE 07, using vendor-code masks."""

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys

from .evidence import read_evidence_file
from .hid_descriptor import parse_report_descriptor
from .probe import SUPPORTED_IDS, configuration_report


@dataclass(frozen=True)
class StandaloneStatus:
    """Static application candidates, not hardware-verified settings.

    The input must be from a standalone GET_FEATURE, not a command-18 memory
    read. A shared report ID does not establish the response's transaction type.
    Unknown bits and bytes remain available verbatim.
    """

    raw: bytes

    def __post_init__(self):
        if not isinstance(self.raw, bytes) or len(self.raw) != 8 or self.raw[0] != 7:
            raise ValueError("Expected an eight-byte standalone report with ID 07")

    @property
    def profile_index_candidate(self) -> int:
        # 0x44f55e / 0x44fc3e: byte 6 -> (value >> 2) & 3 -> CurConfig.
        return (self.raw[6] >> 2) & 3

    @property
    def initializer_local_constant(self) -> int:
        # 0x41a4e3 / 0x422143: bit 1 selects a local with no subsequent use
        # found in recovered pseudocode. Not a demonstrated device address.
        return 0x0FF8 if self.raw[6] & 2 else 0x07F8

    @property
    def unknown_byte6_bits(self) -> int:
        # Only the profile bits have a semantic mapping. Bit 1's firmware
        # meaning remains unknown despite its observed initializer branch.
        return self.raw[6] & 0xF3

    def as_dict(self):
        return {
            "raw_response_hex": self.raw.hex(" "),
            "interpretation": "Static vendor-code candidates; hardware meanings not verified",
            "profile_index_candidate": self.profile_index_candidate,
            "byte6_hex": f"0x{self.raw[6]:02x}",
            "unknown_byte6_bits": {"mask": "0xf3", "value": f"0x{self.unknown_byte6_bits:02x}"},
            "opaque_bytes_hex": {str(i): f"{self.raw[i]:02x}" for i in (1, 2, 3, 4, 5, 7)},
            "static_initializer_observation": {
                "byte6_bit1_set": bool(self.raw[6] & 2),
                "local_constant": f"0x{self.initializer_local_constant:04x}",
                "limitation": "No subsequent use found in recovered pseudocode; not a device address",
            },
        }


def decode_status_capture(path: Path):
    """Interpret one complete, internally consistent GET-only journal offline.

    This validates recording structure, not its authenticity or the firmware's
    behavior. No new device observations are acquired here.
    """
    return decode_status_journal(read_evidence_file(path))


def decode_status_journal(raw: bytes):
    """Validate already-loaded saved bytes; not an input stream or HID read."""
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    expected = ["session", "handle_validated", "get_feature_intent", "get_feature_response", "complete"]
    if (any(not isinstance(event, dict) for event in events)
            or [event.get("event") for event in events] != expected):
        raise ValueError("Expected exactly one complete GET-only session, without errors or retries")
    session, handle, intent, response, complete = events
    identity = session["identity"]
    if (int(identity["vid"], 16), int(identity["pid"], 16)) not in SUPPORTED_IDS:
        raise ValueError("Journal USB identity is not supported by this decoder")
    if (identity != handle["identity"] or handle["bus"] != 3
            or identity["report_id"] != 7 or identity["report_length"] != 8):
        raise ValueError("Journal handle/report identity is inconsistent")
    descriptor = bytes.fromhex(session["report_descriptor_hex"])
    if hashlib.sha256(descriptor).hexdigest() != identity["report_descriptor_sha256"]:
        raise ValueError("Journal descriptor hash does not match its identity")
    report = configuration_report(parse_report_descriptor(descriptor))
    if report is None or report.byte_length != 8:
        raise ValueError("Journal descriptor does not define the eight-byte configuration report")
    if (intent["ioctl"] != "0xc0084807" or intent["requested_length"] != 8
            or bytes.fromhex(intent["request_buffer_hex"]) != b"\x07" + bytes(7)):
        raise ValueError("Journal does not describe a zero-initialized standalone GET_FEATURE 07")
    data = bytes.fromhex(response["buffer_hex_after"])
    if response["returned_length"] != 8 or data != bytes.fromhex(complete["response_hex"]):
        raise ValueError("Journal completion and returned bytes differ")
    status = StandaloneStatus(data)
    return {
        "mode": "offline-status-inspection",
        "capture_sha256": hashlib.sha256(raw).hexdigest(),
        "identity": identity,
        "hardware_field_validation": False,
        **status.as_dict(),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True, help="completed feature-read.jsonl, not a live device")
    args = parser.parse_args(argv)
    try:
        result = decode_status_capture(args.capture)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Status inspection failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
