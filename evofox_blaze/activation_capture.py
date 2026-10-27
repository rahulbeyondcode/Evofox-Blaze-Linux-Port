"""Strict offline inspection of an experimental two-report activation journal."""

import argparse
import hashlib
import json
from pathlib import Path

from .activation import NOTICE, activation_steps, activation_summary
from .evidence import read_evidence_file
from .read_preview import Delay
from .state_read import IDENTITY, SET_FEATURE


def consume_activation(take, *, verified_change=False):
    if verified_change:
        begin = take("activation_begin")
        if begin["scope"] != NOTICE or begin["stage"] != "after-verified-readback":
            raise ValueError("Activation must follow verified readback in the opted-in transaction")
    ordinal = 0
    for step in activation_steps():
        if isinstance(step, Delay):
            delay = take("activation_delay")["milliseconds"]
            if type(delay) is not int or delay != step.milliseconds:
                raise ValueError("Activation delay differs")
            continue
        ordinal += 1
        intent = take("activation_intent")
        result = take("activation_result")
        if (type(intent["ordinal"]) is not int or intent["ordinal"] != ordinal
                or intent["ioctl"] != f"0x{SET_FEATURE:08x}"
                or bytes.fromhex(intent["frame_hex"]) != step.report
                or type(result["ordinal"]) is not int or result["ordinal"] != ordinal
                or type(result["returned_length"]) is not int or result["returned_length"] != 8
                or bytes.fromhex(result["buffer_hex_after"]) != step.report):
            raise ValueError("Activation intent/completion differs")
    complete = take("activation_complete")
    expected = activation_summary()
    if any(type(complete.get(key)) is not type(value) or complete.get(key) != value for key, value in expected.items()):
        raise ValueError("Activation completion is inconsistent or overclaims behavior")
    return expected


def decode_activation_journal(raw):
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if any(not isinstance(event, dict) for event in events):
        raise ValueError("Activation events must be objects")
    position = 0

    def take(kind):
        nonlocal position
        if position >= len(events) or events[position].get("event") != kind:
            raise ValueError(f"Expected {kind}; incomplete, failed or unexpected operation")
        event = events[position]
        position += 1
        return event

    session = take("activation_session")
    if (session["identity"] != IDENTITY or session["accepted_activation_risk"] is not True
            or session["scope"] != NOTICE
            or hashlib.sha256(bytes.fromhex(session["report_descriptor_hex"])).hexdigest()
            != IDENTITY["report_descriptor_sha256"]):
        raise ValueError("Activation session scope, consent or descriptor differs")
    handle = take("handle_validated")
    if (handle["identity"] != IDENTITY or type(handle["bus"]) is not int or handle["bus"] != 3
            or handle["lock_mode"] != "exclusive-advisory"):
        raise ValueError("Activation handle identity/lock differs")
    expected = consume_activation(take)
    if position != len(events):
        raise ValueError("Extra operations after activation completion")
    return {"mode": "offline-activation-inspection", "identity": IDENTITY,
            "capture_sha256": hashlib.sha256(raw).hexdigest(), **expected}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = decode_activation_journal(read_evidence_file(args.capture))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Activation inspection failed: {error}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
