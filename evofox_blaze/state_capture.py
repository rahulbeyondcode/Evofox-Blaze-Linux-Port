"""Offline validation of a complete fixed state-read journal, not hardware I/O."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

from .evidence import read_evidence_file
from .read_preview import Delay, SetFeature, decode_dpi_selector, decode_state_block
from .state_read import GET_FEATURE, IDENTITY, SET_FEATURE, fixed_read_steps


def consume_state_read(take):
    """Validate one exact read subsequence using a caller's checked event reader."""
    collected = bytearray()
    ordinal = 0
    for step in fixed_read_steps():
        if isinstance(step, Delay):
            if take("state_delay")["milliseconds"] != step.milliseconds:
                raise ValueError("State journal delays differ from the source sequence")
            continue
        ordinal += 1
        is_set = isinstance(step, SetFeature)
        operation = "SET_FEATURE" if is_set else "GET_FEATURE"
        request = SET_FEATURE if is_set else GET_FEATURE
        expected = step.report if is_set else b"\x07" + bytes(7)
        intent = take("state_feature_intent")
        if (intent["ordinal"] != ordinal or intent["operation"] != operation
                or intent["ioctl"] != f"0x{request:08x}"
                or bytes.fromhex(intent["buffer_hex"]) != expected):
            raise ValueError("State journal feature request differs from the fixed source sequence")
        result = take("state_feature_result")
        data = bytes.fromhex(result["buffer_hex_after"])
        if (result["ordinal"] != ordinal or result["operation"] != operation
                or type(result["returned_length"]) is not int or result["returned_length"] != 8
                or len(data) != 8 or data[0] != 7 or (is_set and data != expected)):
            raise ValueError("State journal feature completion is short, changed, or inconsistent")
        if not is_set:
            collected.append(data[step.result_byte])
    return bytes(collected)


def decode_state_journal(raw: bytes):
    """Check exact request/result order, not recording authenticity or behavior."""
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if any(not isinstance(event, dict) for event in events):
        raise ValueError("State journal events must be objects")
    position = 0

    def take(kind):
        nonlocal position
        if position >= len(events) or events[position].get("event") != kind:
            raise ValueError(f"Expected {kind}; incomplete, failed, or unexpected state operation")
        event = events[position]
        position += 1
        return event

    session = take("state_session")
    if (session["identity"] != IDENTITY or session["base"] != "0x0018" or session["length"] != 8
            or session["accepted_staging_risk"] is not True):
        raise ValueError("State journal scope or acknowledged identity differs")
    descriptor = bytes.fromhex(session["report_descriptor_hex"])
    if hashlib.sha256(descriptor).hexdigest() != IDENTITY["report_descriptor_sha256"]:
        raise ValueError("State journal descriptor differs from the exact baseline")
    handle = take("handle_validated")
    if handle["identity"] != IDENTITY or handle["bus"] != 3:
        raise ValueError("State journal handle validation differs from its session")
    collected = consume_state_read(take)
    complete = take("state_complete")
    if (position != len(events) or complete["base"] != "0x0018" or complete["length"] != 8
            or bytes.fromhex(complete["collected_hex"]) != collected
            or complete["dpi_stage_selector_candidate"] != decode_dpi_selector(bytes(collected))
            or complete["complete_configuration_backup"] is not False):
        raise ValueError("State journal completion is inconsistent or contains extra operations")
    return {
        "mode": "offline-state-inspection", "identity": session["identity"],
        "capture_sha256": hashlib.sha256(raw).hexdigest(),
        "base": "0x0018", "length": 8, "set_feature_count": 18, "get_feature_count": 8,
        "hardware_field_validation": False,
        "interpretation": "Captured fixed state block; field candidates are not behavior measurements",
        **decode_state_block(bytes(collected)),
    }


def decode_state_capture(path: Path):
    return decode_state_journal(read_evidence_file(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True, type=Path, help="completed state-read.jsonl; not a live device")
    args = parser.parse_args(argv)
    try:
        result = decode_state_capture(args.capture)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"State inspection failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
