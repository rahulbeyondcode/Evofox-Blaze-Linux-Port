"""Offline validation of native button changes and explicit exact-block restores."""

import argparse
import hashlib
import json
from pathlib import Path

from .button_capture import consume_button_read
from .activation import activation_completion_matches, activation_fields, check_activation_option
from .activation_capture import consume_activation
from .button_write import assignment_rows, button_write_frames, parse_rows, validate_backup
from .buttons import describe_block, plan_assignments
from .evidence import read_evidence_file
from .state_read import IDENTITY, SET_FEATURE


def decode_button_config_journal(raw):
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if any(not isinstance(event, dict) for event in events):
        raise ValueError("Button configuration events must be objects")
    position = 0

    def take(kind, phase=None):
        nonlocal position
        if position >= len(events) or events[position].get("event") != kind:
            raise ValueError(f"Expected {kind}; incomplete, failed or unexpected button operation")
        event = events[position]
        position += 1
        if phase is not None and event.get("phase") != phase:
            raise ValueError("Button read phase differs")
        return event

    session = take("button_config_session")
    if (session["identity"] != IDENTITY or session["base"] != "0x0008"
            or type(session["length"]) is not int or session["length"] != 8
            or session["accepted_write_risk"] is not True
            or session["operation"] not in ("change", "restore")
            or hashlib.sha256(bytes.fromhex(session["report_descriptor_hex"])).hexdigest() != IDENTITY["report_descriptor_sha256"]):
        raise ValueError("Button configuration session identity/scope differs")
    assignments = parse_rows(session["assignments"])
    activation_requested = check_activation_option(session.get("accepted_activation_risk", False),
                                                   restore=session["operation"] == "restore")
    basis = session.get("restore_basis")
    restored = required = None
    if session["operation"] == "restore":
        restored, required, original_assignments = validate_backup(basis)
        if original_assignments != assignments:
            raise ValueError("Restore assignment lineage differs from its backup")
    elif basis is not None:
        raise ValueError("A new button change must not contain restore state")
    handle = take("handle_validated")
    if handle["identity"] != IDENTITY or handle["bus"] != 3:
        raise ValueError("Button configuration handle differs")
    before = consume_button_read(lambda kind: take(kind, "before"))
    if session["operation"] == "restore":
        if before not in (restored, required):
            raise ValueError("Restore would overwrite intervening edits")
        after = restored
    else:
        after = plan_assignments(before, assignments)
    if before != after:
        durable = take("button_backup_durable")
        backup = durable["backup"]
        original_before, original_after, original_assignments = validate_backup(backup)
        matching_backup = ((original_before, original_after) == (before, after)
                           if basis is None else backup == basis)
        if (durable["filename"] != "button-backup.json" or original_assignments != assignments
                or durable["before_sha256"] != hashlib.sha256(before).hexdigest()
                or durable["after_sha256"] != hashlib.sha256(after).hexdigest()
                or not matching_backup):
            raise ValueError("Durable button backup is inconsistent with the owned-field change")
        for index, frame in enumerate(button_write_frames(after)):
            if index in (8, 9):
                delay = take("button_write_delay")["milliseconds"]
                if type(delay) is not int or delay != (4 if index == 8 else 2):
                    raise ValueError("Button writer delay differs")
            intent = take("button_write_intent")
            if (type(intent["ordinal"]) is not int or intent["ordinal"] != index + 1
                    or intent["ioctl"] != f"0x{SET_FEATURE:08x}" or bytes.fromhex(intent["frame_hex"]) != frame):
                raise ValueError("Button writer intent differs from the exact scoped write")
            result = take("button_write_result")
            if (type(result["ordinal"]) is not int or result["ordinal"] != index + 1
                    or type(result["returned_length"]) is not int or result["returned_length"] != 8
                    or bytes.fromhex(result["buffer_hex_after"]) != frame):
                raise ValueError("Button write is short, changed or inconsistent")
        if consume_button_read(lambda kind: take(kind, "verify")) != after:
            raise ValueError("Button readback differs from the planned complete block")
        if activation_requested:
            consume_activation(take, verified_change=True)
    complete = take("button_config_complete")
    outcome = "no-change" if before == after else "written-and-read-back"
    if (position != len(events) or complete["outcome"] != outcome
            or bytes.fromhex(complete["before_hex"]) != before or bytes.fromhex(complete["after_hex"]) != after
            or complete["behavior_verified"] is not False or complete["complete_configuration_backup"] is not False
            or complete["extension_records_modified"] is not False
            or not activation_completion_matches(complete, activation_requested, before != after)
            or (before != after and complete["backup_file"] != "button-backup.json")):
        raise ValueError("Button completion overclaims verification or has extra operations")
    return {"mode": "offline-button-configuration-inspection", "identity": IDENTITY,
            "operation": session["operation"], "assignments": assignment_rows(assignments),
            "capture_sha256": hashlib.sha256(raw).hexdigest(), "outcome": outcome,
            "before_hex": before.hex(" "), "after_hex": after.hex(" "),
            "set_feature_count": (18 if before == after else 46) + (2 if activation_requested and before != after else 0),
            "get_feature_count": 8 if before == after else 16,
            **({"backup_file": "button-backup.json"} if before != after else {}),
            "settings_commits": int(before != after), "extension_records_modified": False,
            **describe_block(after), **activation_fields(activation_requested, before != after)}


def decode_button_config_capture(path):
    return decode_button_config_journal(read_evidence_file(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = decode_button_config_capture(args.capture)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Button configuration inspection failed: {error}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
