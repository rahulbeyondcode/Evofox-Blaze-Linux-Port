"""Strict offline inspection of the fixed 0008 button-read journal."""

import argparse
import hashlib
import json
from pathlib import Path

from .button_read import button_read_steps
from .buttons import describe_block
from .evidence import read_evidence_file
from .read_preview import Delay, SetFeature
from .state_read import GET_FEATURE, IDENTITY, SET_FEATURE


def consume_button_read(take):
    collected = bytearray()
    ordinal = 0
    for step in button_read_steps():
        if isinstance(step, Delay):
            delay = take("button_delay")["milliseconds"]
            if type(delay) is not int or delay != step.milliseconds:
                raise ValueError("Button delay differs from the fixed sequence")
            continue
        ordinal += 1
        is_set = isinstance(step, SetFeature)
        operation = "SET_FEATURE" if is_set else "GET_FEATURE"
        request = SET_FEATURE if is_set else GET_FEATURE
        expected = step.report if is_set else b"\x07" + bytes(7)
        intent = take("button_feature_intent")
        if (type(intent["ordinal"]) is not int or intent["ordinal"] != ordinal
                or intent["operation"] != operation or intent["ioctl"] != f"0x{request:08x}"
                or bytes.fromhex(intent["buffer_hex"]) != expected):
            raise ValueError("Button intent differs from the exact fixed 0008 read")
        result = take("button_feature_result")
        data = bytes.fromhex(result["buffer_hex_after"])
        if (type(result["ordinal"]) is not int or result["ordinal"] != ordinal
                or result["operation"] != operation or type(result["returned_length"]) is not int
                or result["returned_length"] != 8 or len(data) != 8 or data[0] != 7
                or (is_set and data != expected)):
            raise ValueError("Incomplete or changed button feature completion")
        if not is_set:
            collected.append(data[1])
    return bytes(collected)


def decode_button_journal(raw):
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if any(not isinstance(event, dict) for event in events):
        raise ValueError("Button journal events must be objects")
    position = 0

    def take(kind):
        nonlocal position
        if position >= len(events) or events[position].get("event") != kind:
            raise ValueError(f"Expected {kind}; incomplete, failed or unexpected operation")
        event = events[position]
        position += 1
        return event

    session = take("button_session")
    if (session["identity"] != IDENTITY or session["base"] != "0x0008"
            or type(session["length"]) is not int or session["length"] != 8
            or session["accepted_staging_risk"] is not True):
        raise ValueError("Button read session scope/identity differs")
    if hashlib.sha256(bytes.fromhex(session["report_descriptor_hex"])).hexdigest() != IDENTITY["report_descriptor_sha256"]:
        raise ValueError("Button read descriptor differs")
    handle = take("handle_validated")
    if handle["identity"] != IDENTITY or handle["bus"] != 3:
        raise ValueError("Button handle identity differs")
    data = consume_button_read(take)
    complete = take("button_complete")
    description = describe_block(data)
    if (position != len(events) or complete.get("mode") != "experimental-button-read"
            or any(type(complete.get(key)) is not type(value) or complete.get(key) != value
                   for key, value in description.items())):
        raise ValueError("Button completion is inconsistent or overclaims verification")
    return {"mode": "offline-button-inspection", "identity": IDENTITY,
            "capture_sha256": hashlib.sha256(raw).hexdigest(),
            "set_feature_count": 18, "get_feature_count": 8, **description}


def decode_button_capture(path):
    return decode_button_journal(read_evidence_file(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = decode_button_capture(args.capture)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Button capture inspection failed: {error}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
