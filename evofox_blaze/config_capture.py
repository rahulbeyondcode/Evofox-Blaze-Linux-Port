"""Offline consistency checks for one scoped configuration change/readback journal."""

import hashlib
import json

from .config_write import plan_change
from .read_preview import decode_state_block
from .state_capture import consume_state_read
from .state_read import IDENTITY, SET_FEATURE


def decode_config_journal(raw: bytes):
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if any(not isinstance(event, dict) for event in events):
        raise ValueError("Configuration journal events must be objects")
    position = 0

    def take(kind):
        nonlocal position
        if position >= len(events) or events[position].get("event") != kind:
            raise ValueError(f"Expected {kind}; configuration operation is failed, incomplete, or out of scope")
        event = events[position]
        position += 1
        return event

    def phase_reader(phase):
        def reader(kind):
            event = take(kind)
            if event.get("phase") != phase:
                raise ValueError("Configuration read phase is inconsistent")
            return event
        return reader

    session = take("config_session")
    if (session["identity"] != IDENTITY or session["accepted_write_risk"] is not True
            or session["operation"] not in ("change", "restore")):
        raise ValueError("Configuration journal identity or acknowledged operation differs")
    handle = take("handle_validated")
    if handle["identity"] != IDENTITY or handle["bus"] != 3:
        raise ValueError("Configuration handle does not match the exact baseline")
    before = consume_state_read(phase_reader("before"))
    after = plan_change(before, session["field"], session["value"])
    written = before != after
    if written:
        backup = take("config_backup_durable")
        if backup["filename"] != "original-state.json" or backup["before_sha256"] != hashlib.sha256(before).hexdigest():
            raise ValueError("Configuration journal backup declaration differs")
        frames = [bytes((7, 0x18, 3, i, 0x18, 0, value, 7)) for i, value in enumerate(after)]
        frames.extend((bytes.fromhex("07 18 09 00 18 00 00 07"), bytes.fromhex("07 18 00 00 18 00 00 00")))
        for i, expected in enumerate(frames):
            if i in (8, 9) and take("config_delay")["milliseconds"] != (4 if i == 8 else 2):
                raise ValueError("Configuration write delay differs from the source helper")
            intent = take("config_write_intent")
            if (intent["ordinal"] != i + 1 or intent["ioctl"] != f"0x{SET_FEATURE:08x}"
                    or bytes.fromhex(intent["frame_hex"]) != expected):
                raise ValueError("Configuration write changes bytes outside the planned operation")
            result = take("config_write_result")
            if (result["ordinal"] != i + 1 or type(result["returned_length"]) is not int
                    or result["returned_length"] != 8 or bytes.fromhex(result["buffer_hex_after"]) != expected):
                raise ValueError("Configuration write result is short or inconsistent")
        if consume_state_read(phase_reader("verify")) != after:
            raise ValueError("Saved readback differs from the intended block")
    complete = take("config_complete")
    outcome = "written-and-read-back" if written else "no-change"
    if (position != len(events) or complete["outcome"] != outcome
            or bytes.fromhex(complete["before_hex"]) != before or bytes.fromhex(complete["after_hex"]) != after
            or complete["behavior_verified"] is not False or complete["complete_configuration_backup"] is not False):
        raise ValueError("Configuration completion is inconsistent or contains extra operations")
    return {
        "mode": "offline-configuration-inspection", "identity": session["identity"],
        "capture_sha256": hashlib.sha256(raw).hexdigest(), "base": "0x0018", "length": 8,
        "set_feature_count": 46 if written else 18, "get_feature_count": 16 if written else 8,
        "operation": session["operation"], "outcome": outcome,
        "before_hex": before.hex(" "), "after_hex": after.hex(" "),
        "behavior_verified": False, "hardware_field_validation": False,
        **decode_state_block(after),
    }
