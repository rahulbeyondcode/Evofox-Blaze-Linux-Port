"""Audit the pinned ANKO USB capture offline; never execute or replay its reports.

Usage: python3 -m tools.audit_public_capture --capture <downloaded.pcapng>
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct

from evofox_blaze.evidence import read_evidence_file


FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/anko-read-corroboration.json"
BUTTON_FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/vendor-button-observations.json"
SHORTCUT_FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/vendor-shortcut-observations.json"
ACTIVATION_FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/vendor-activation-observations.json"
DIGEST = "db3a3ba224069226ce75d9ded8a37d9363e71deb15737d749a2f951ad637c9c8"


def audit_capture(raw):
    if hashlib.sha256(raw).hexdigest() != DIGEST:
        raise ValueError("This auditor accepts only the reviewed source capture SHA-256")
    fixture = json.loads(read_evidence_file(FIXTURE))
    button_fixture = json.loads(read_evidence_file(BUTTON_FIXTURE))["public_capture"]
    shortcut_fixture = json.loads(read_evidence_file(SHORTCUT_FIXTURE))["public_capture"]
    activation_fixture = json.loads(read_evidence_file(ACTIVATION_FIXTURE))
    position = packet_number = 0
    pending = {}
    descriptors = {}
    events = []
    staged = {}
    button_staged = {}
    button_commits = []
    descriptor_staged = {}
    descriptor_commits = []
    read_bases = set()
    finish_pairs = []
    pending_finish = None
    committed = before_read = None
    while position < len(raw):
        kind, length = struct.unpack_from("<II", raw, position)
        if length < 12 or length % 4 or position + length > len(raw):
            raise ValueError("Malformed PCAPNG block length")
        if struct.unpack_from("<I", raw, position + length - 4)[0] != length:
            raise ValueError("PCAPNG block length trailer differs")
        if kind == 6:
            packet_number += 1
            captured = struct.unpack_from("<I", raw, position + 20)[0]
            if captured > length - 32:
                raise ValueError("Truncated enhanced packet")
            packet = raw[position + 28:position + 28 + captured]
            if len(packet) >= 28:
                header, irp, status, _function, info, bus, device, _endpoint, transfer, size = struct.unpack_from("<HQIHBHHBBI", packet)
                if transfer == 2 and (bus, device) == (3, 1):
                    data = packet[header:]
                    if header < 28 or header > len(packet) or len(data) != size:
                        raise ValueError("USBPcap control-data bounds differ")
                    if info == 0 and packet[27] == 0 and len(data) >= 8:
                        setup = struct.unpack_from("<BBHHH", data)
                        pending[irp] = setup
                        if setup == (0x21, 9, 0x307, 1, 8):
                            report = data[8:]
                            if len(report) != 8:
                                raise ValueError("Feature SET length differs")
                            if pending_finish is not None:
                                if report.hex(" ") != activation_fixture["second_frame_hex"]:
                                    raise ValueError("End-of-settings candidate lacks its immediate phase-zero SET")
                                finish_pairs.append([pending_finish, packet_number])
                                pending_finish = None
                            if report.hex(" ") == activation_fixture["first_frame_hex"]:
                                pending_finish = packet_number
                            if 1943 <= packet_number <= 1995:
                                if before_read is None:
                                    before_read = committed
                                events.append(["SET_FEATURE", packet_number, report.hex(" ")])
                            if report[:2] == b"\x07\x18":
                                base = int.from_bytes(report[4:6], "little")
                                if base in range(0xa0, 0x2d0, 8):
                                    if report[2] == 3:
                                        descriptor_staged[(base, report[3])] = report[6]
                                    elif report[2] == 9:
                                        block = bytes(descriptor_staged[(base, i)] for i in range(report[7] + 1))
                                        descriptor_commits.append((packet_number, base, block))
                                    elif report[2] == 0:
                                        descriptor_staged.clear()
                                if report[2] == 5:
                                    read_bases.add(f"0x{int.from_bytes(report[4:6], 'little'):04x}")
                                if report[4:6] == b"\x08\x00":
                                    if report[2] == 3:
                                        button_staged[report[3]] = report[6]
                                    elif report[2] == 9:
                                        button_data = bytes(button_staged[i] for i in range(report[7] + 1))
                                        button_commits.append((packet_number, report[7], button_data.hex(" ")))
                                    elif report[2] == 0:
                                        button_staged.clear()
                            if report[:2] == b"\x07\x18" and report[4:6] == b"\x18\x00":
                                if report[2] == 3:
                                    staged[report[3]] = report[6]
                                elif report[2] == 9:
                                    committed = bytes(staged[i] for i in range(report[7] + 1))
                                elif report[2] == 0:
                                    staged.clear()
                    elif info == 1 and irp in pending:
                        setup = pending.pop(irp)
                        if status:
                            raise ValueError("Failed USB control completion in reviewed device stream")
                        if setup[0:2] == (0x80, 6) and setup[2] in (0x100, 0x200):
                            descriptors[setup[2]] = data
                        if setup == (0xA1, 1, 0x307, 1, 8) and 1943 <= packet_number <= 1995:
                            if len(data) != 8 or data[0] != 7:
                                raise ValueError("Feature GET completion differs")
                            events.append(["GET_FEATURE", packet_number, data.hex(" ")])
        position += length
    collected = bytes(bytes.fromhex(data)[1] for operation, _, data in events if operation == "GET_FEATURE")
    if (events != fixture["feature_events"] or collected != before_read
            or collected.hex(" ") != fixture["collected_hex"]
            or descriptors[0x100] != bytes.fromhex(fixture["usb_device_descriptor_hex"])
            or descriptors[0x200] != bytes.fromhex(fixture["usb_configuration_descriptor_hex"])):
        raise ValueError("Reviewed excerpt, prior committed bytes or USB descriptor envelope differs")
    expected_buttons = [(number, button_fixture["length_minus_one"], button_fixture["button_committed_hex"])
                        for number in button_fixture["button_commit_packets"]]
    if (button_commits != expected_buttons or sorted(read_bases) != button_fixture["read_bases_observed"]
            or button_fixture["button_read_observed"] is not False):
        raise ValueError("Reviewed button commits/read-region coverage differs")
    expected_descriptors = [(first + index * 22, 0xa0 + index * 8, bytes(8))
                            for first in shortcut_fixture["first_commit_packets"] for index in range(70)]
    if (descriptor_commits != expected_descriptors
            or [descriptor_commits[69][0], descriptor_commits[139][0]] != shortcut_fixture["last_commit_packets"]
            or shortcut_fixture["all_descriptor_bytes_zero"] is not True):
        raise ValueError("Reviewed shortcut descriptor address/chunking corroboration differs")
    if (pending_finish is not None or activation_fixture["public_capture"]["sha256"] != DIGEST
            or finish_pairs != activation_fixture["public_capture"]["finish_packet_pairs"]):
        raise ValueError("Reviewed end-of-settings candidate sequences differ")
    return {"capture_sha256": DIGEST, "excerpt_feature_operations": len(events),
            "collected_hex": collected.hex(" "), "matches_prior_committed_block": True,
            "no_commit_in_read": True, "button_write_blocks": len(button_commits),
             "button_read_observed": False,
              "shortcut_descriptor_write_passes": 2, "nonzero_shortcut_record_corroborated": False,
              "end_of_settings_candidate_pairs": finish_pairs, "blaze_runtime_activation_proven": False,
            "limitation": "Related-product capture, not a Blaze backup or full firmware proof"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit_capture(read_evidence_file(args.capture))
    except (OSError, ValueError, KeyError, struct.error) as error:
        parser.exit(1, f"Capture audit failed: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
