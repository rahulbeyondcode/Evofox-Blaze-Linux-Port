"""Strict offline validation of scoped shortcut change/explicit-restore journals."""

import hashlib
import json

from .activation import activation_completion_matches, check_activation_option
from .activation_capture import consume_activation

from .evidence import read_shortcut_journal
from .shortcut_capture import consume_fixed_block
from .shortcut_plan import (HEADER_BASES, normalize_request, parse_shortcuts, payload_bases,
                            plan_change, restore_plan, snapshot_digest)
from .shortcut_read import _eight_byte_read_steps, header_read_steps
from .shortcut_write import (complete_result, fragment_description, fragment_frames, guard_first_tail_test,
                            parse_rows, validate_backup)
from .state_read import IDENTITY, SET_FEATURE


def consume_snapshot(take, shortcuts, phase, header_guard=None):
    def phased(kind):
        row = take(kind)
        if row.get("phase") != phase:
            raise ValueError("Shortcut snapshot phase differs")
        return row

    blocks = {base: consume_fixed_block(phased, base, header_read_steps(base)) for base in HEADER_BASES}
    if header_guard is not None:
        header_guard(blocks)
    for base in payload_bases(blocks, shortcuts):
        blocks[base] = consume_fixed_block(phased, base, _eight_byte_read_steps(base))
    complete = phased("shortcut_snapshot_complete")
    if (complete["snapshot_sha256"] != snapshot_digest(blocks)
            or type(complete["block_count"]) is not int or complete["block_count"] != len(blocks)):
        raise ValueError("Shortcut snapshot completion differs")
    return blocks


def decode_shortcut_config_journal(raw):
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if any(not isinstance(event, dict) for event in events):
        raise ValueError("Shortcut journal events must be objects")
    position = 0

    def take(kind):
        nonlocal position
        if position >= len(events) or events[position].get("event") != kind:
            raise ValueError(f"Expected {kind}; incomplete, failed or unexpected operation")
        event = events[position]
        position += 1
        return event

    session = take("shortcut_config_session")
    if (session["identity"] != IDENTITY or session["accepted_write_risk"] is not True
            or session["scope"] != "blaze-shortcut-tail-v1" or session["operation"] not in ("change", "restore")
            or hashlib.sha256(bytes.fromhex(session["report_descriptor_hex"])).hexdigest()
            != IDENTITY["report_descriptor_sha256"]):
        raise ValueError("Shortcut configuration session identity/scope differs")
    native = parse_rows(session["assignments"]) if session["assignments"] else {}
    shortcuts = parse_shortcuts(session["shortcuts"])
    normalize_request(native, shortcuts)
    first_test = session.get("first_tail_test", False)
    if type(first_test) is not bool:
        raise ValueError("Shortcut field-test scope flag differs")
    activation_requested = check_activation_option(session.get("accepted_activation_risk", False),
                                                   restore=session["operation"] == "restore", first_tail_test=first_test)
    if first_test and (native or session["operation"] != "change" or session["shortcuts"] !=
                       [{"slot": 5, "key": "F13", "modifiers": []}]):
        raise ValueError("First field-test request differs")
    basis = session["restore_basis"]
    if session["operation"] == "restore":
        original, desired, basis_native, basis_shortcuts, original_fragments = validate_backup(basis)
        if native != basis_native or shortcuts != basis_shortcuts:
            raise ValueError("Shortcut restore request differs from its original backup")
    elif basis is not None:
        raise ValueError("New shortcut change cannot contain restore state")
    handle = take("handle_validated")
    if handle["identity"] != IDENTITY or handle["bus"] != 3:
        raise ValueError("Shortcut handle differs")
    before = consume_snapshot(take, shortcuts, "before", guard_first_tail_test if first_test else None)
    if session["operation"] == "change":
        after, fragments = plan_change(before, native, shortcuts)
    else:
        fragments = restore_plan(before, original, desired, original_fragments)
        after = original
    if fragments:
        durable = take("shortcut_backup_durable")
        saved_before, saved_after, saved_native, saved_shortcuts, _ = validate_backup(durable["backup"])
        if (durable["filename"] != "shortcut-backup.json" or saved_native != native or saved_shortcuts != shortcuts
                or durable["before_sha256"] != snapshot_digest(before)
                or durable["after_sha256"] != snapshot_digest(after)
                or (basis is None and (saved_before != before or saved_after != after))
                or (basis is not None and durable["backup"] != basis)):
            raise ValueError("Shortcut backup is inconsistent with the owned-field transaction")
        for fragment in fragments:
            begin = take("shortcut_write_begin")
            if any(begin.get(key) != value for key, value in fragment_description(fragment).items()):
                raise ValueError("Shortcut write span differs")
            for index, frame in enumerate(fragment_frames(fragment)):
                if index >= len(fragment.data):
                    delay = take("shortcut_write_delay")["milliseconds"]
                    if type(delay) is not int or delay != (4 if index == len(fragment.data) else 2):
                        raise ValueError("Shortcut writer delay differs")
                intent = take("shortcut_write_intent")
                result = take("shortcut_write_result")
                if (type(intent["ordinal"]) is not int or intent["ordinal"] != index + 1
                        or intent["ioctl"] != f"0x{SET_FEATURE:08x}" or bytes.fromhex(intent["frame_hex"]) != frame
                        or type(result["ordinal"]) is not int or result["ordinal"] != index + 1
                        or type(result["returned_length"]) is not int or result["returned_length"] != 8
                        or bytes.fromhex(result["buffer_hex_after"]) != frame):
                    raise ValueError("Shortcut write completion differs")
        if consume_snapshot(take, shortcuts, "verify") != after:
            raise ValueError("Shortcut readback differs")
        if activation_requested:
            consume_activation(take, verified_change=True)
    expected = complete_result(after, native, shortcuts, "written-and-read-back" if fragments else "no-change",
                               len(fragments), len(before), sum(len(fragment_frames(fragment)) for fragment in fragments),
                               operation=session["operation"], backup=bool(fragments), activation_requested=activation_requested)
    complete = take("shortcut_config_complete")
    if (position != len(events) or not activation_completion_matches(complete, activation_requested, bool(fragments))
            or any(type(complete.get(key)) is not type(value) or complete[key] != value
                   for key, value in expected.items())):
        raise ValueError("Shortcut completion differs or overclaims verification")
    return {"mode": "offline-shortcut-configuration-inspection", "identity": IDENTITY,
            "capture_sha256": hashlib.sha256(raw).hexdigest(), **expected}


def decode_shortcut_config_capture(path):
    return decode_shortcut_config_journal(read_shortcut_journal(path))
