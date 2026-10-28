"""Strict offline inspection of the fixed shortcut-metadata read journal."""

import argparse
import hashlib
import json
from pathlib import Path

from .evidence import read_evidence_file
from .read_preview import Delay, SetFeature
from .shortcut_read import HEADER_BASES, describe_headers, header_read_steps
from .state_read import GET_FEATURE, IDENTITY, SET_FEATURE


def consume_header(take, base):
    return consume_fixed_block(take, base, header_read_steps(base))


def consume_fixed_block(take, base, steps):
    begin = take("shortcut_block_begin")
    if begin["base"] != f"0x{base:04x}" or type(begin["length"]) is not int or begin["length"] != 8:
        raise ValueError("Shortcut metadata block scope differs")
    ordinal = 0
    collected = bytearray()
    for step in steps:
        if isinstance(step, Delay):
            delay = take("shortcut_delay")["milliseconds"]
            if type(delay) is not int or delay != step.milliseconds:
                raise ValueError("Shortcut metadata delay differs")
            continue
        ordinal += 1
        is_set = isinstance(step, SetFeature)
        operation = "SET_FEATURE" if is_set else "GET_FEATURE"
        request = SET_FEATURE if is_set else GET_FEATURE
        expected = step.report if is_set else b"\x07" + bytes(7)
        intent = take("shortcut_feature_intent")
        if (type(intent["ordinal"]) is not int or intent["ordinal"] != ordinal
                or intent["operation"] != operation or intent["ioctl"] != f"0x{request:08x}"
                or bytes.fromhex(intent["buffer_hex"]) != expected):
            raise ValueError("Shortcut metadata intent differs from the fixed read")
        result = take("shortcut_feature_result")
        data = bytes.fromhex(result["buffer_hex_after"])
        if (type(result["ordinal"]) is not int or result["ordinal"] != ordinal
                or result["operation"] != operation or type(result["returned_length"]) is not int
                or result["returned_length"] != 8 or len(data) != 8 or data[0] != 7
                or (is_set and data != expected)):
            raise ValueError("Shortcut metadata completion is short or malformed")
        if not is_set:
            collected.append(data[1])
    complete = take("shortcut_block_complete")
    if complete["base"] != f"0x{base:04x}" or bytes.fromhex(complete["collected_hex"]) != collected:
        raise ValueError("Shortcut block completion differs")
    return bytes(collected)


def decode_shortcut_header_journal(raw):
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if any(not isinstance(event, dict) for event in events):
        raise ValueError("Shortcut metadata journal events must be objects")
    position = 0

    def take(kind):
        nonlocal position
        if position >= len(events) or events[position].get("event") != kind:
            raise ValueError(f"Expected {kind}; incomplete, failed or unexpected operation")
        event = events[position]
        position += 1
        return event

    session = take("shortcut_header_session")
    if (session["identity"] != IDENTITY or session["accepted_staging_risk"] is not True
            or session["bases"] != [f"0x{base:04x}" for base in HEADER_BASES]
            or type(session["length"]) is not int or session["length"] != 8
            or hashlib.sha256(bytes.fromhex(session["report_descriptor_hex"])).hexdigest()
            != IDENTITY["report_descriptor_sha256"]):
        raise ValueError("Shortcut metadata session identity/scope differs")
    handle = take("handle_validated")
    if handle["identity"] != IDENTITY or handle["bus"] != 3:
        raise ValueError("Shortcut metadata handle differs")
    description = describe_headers({base: consume_header(take, base) for base in HEADER_BASES})
    complete = take("shortcut_header_complete")
    if (position != len(events) or complete.get("mode") != "experimental-shortcut-headers"
            or any(type(complete.get(key)) is not type(value) or complete[key] != value
                   for key, value in description.items())):
        raise ValueError("Shortcut completion differs or overclaims verification")
    return {"mode": "offline-shortcut-header-inspection", "identity": IDENTITY,
            "capture_sha256": hashlib.sha256(raw).hexdigest(),
            "set_feature_count": 1332, "get_feature_count": 592, "settings_commits": 0, **description}


def decode_shortcut_header_capture(path):
    return decode_shortcut_header_journal(read_evidence_file(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = decode_shortcut_header_capture(args.capture)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Shortcut metadata inspection failed: {error}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
