"""Scoped experimental keyboard-chord programming with backup/readback/restore.

Only the inspected allocation layout is accepted. No metadata/auxiliary-data
relocation, arbitrary address API, slot 9, reset, retry or automatic rollback.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from .activation import NOTICE, activate_verified_change, activation_fields, check_activation_option
from .button_write import assignment_rows, parse_cli_assignments, parse_rows
from .evidence import read_evidence_file
from .feature_read import Journal, check_host, load_baseline, select_target, validated_handle
from .probe import enumerate_devices
from .shortcut_plan import (Fragment, HEADER_BASES, POOL, describe_state, normalize_request,
                            header_owners, parse_shortcuts, parse_snapshot, payload_bases, plan_change, restore_plan,
                            shortcut_rows, snapshot_digest, snapshot_rows)
from .shortcut_read import _eight_byte_read_steps, _read_fixed_block, header_read_steps
from .state_read import IDENTITY, SET_FEATURE
from .shortcuts import Shortcut


def guard_first_tail_test(headers):
    if headers[8] != bytes.fromhex("21 22 23 24 23 35 00 26") or header_owners(headers):
        raise ValueError("First tail-test state changed; no payload expansion or setting write is authorized")


def _read_snapshot(fd, record, shortcuts, phase, expected_bases=None, header_guard=None):
    emit = lambda event, **fields: record(event, phase=phase, **fields)
    blocks = {base: _read_fixed_block(fd, base, header_read_steps(base), emit) for base in HEADER_BASES}
    if header_guard is not None:
        header_guard(blocks)
    bases = payload_bases(blocks, shortcuts)
    if expected_bases is not None and tuple(HEADER_BASES) + bases != tuple(expected_bases):
        raise ValueError("Shortcut verification/restore scope changed; stop without retry")
    allowed = set(range(0x400, 0x550, 8))
    if any(base not in allowed for base in bases):
        raise ValueError("Shortcut payload read exceeds the bounded preservation policy")
    for base in bases:
        blocks[base] = _read_fixed_block(fd, base, _eight_byte_read_steps(base), emit)
    emit("shortcut_snapshot_complete", snapshot_sha256=snapshot_digest(blocks), block_count=len(blocks))
    return blocks


def fragment_frames(fragment):
    if not isinstance(fragment, Fragment) or not isinstance(fragment.data, bytes):
        raise ValueError("Expected a validated shortcut write fragment")
    base, data = fragment.base, fragment.data
    if type(base) is not int or base % 8 or not data or len(data) % 8:
        raise ValueError("Shortcut fragment must be aligned and backed by complete blocks")
    if fragment.kind == "record":
        valid = base in POOL and len(data) <= 24
    elif fragment.kind == "descriptors":
        valid = 0xa0 <= base and base + len(data) <= 0xf0
    elif fragment.kind == "buttons":
        valid = base == 8 and len(data) == 8
    else:
        valid = False
    if not valid:
        raise ValueError("Shortcut fragment exceeds the owned table/tail ranges")
    lo, hi, last = base & 255, base >> 8, len(data) - 1
    frames = [bytes((7, 0x18, 3, index, lo, hi, value, last)) for index, value in enumerate(data)]
    return tuple(frames + [bytes((7, 0x18, 9, 0, lo, hi, 0, last)),
                           bytes((7, 0x18, 0, 0, lo, hi, 0, 0))])


def fragment_description(fragment):
    return {"kind": fragment.kind, "base": f"0x{fragment.base:04x}", "length": len(fragment.data),
            "sha256": hashlib.sha256(fragment.data).hexdigest()}


def _write_fragment(fd, fragment, record):
    import fcntl

    frames = fragment_frames(fragment)
    record("shortcut_write_begin", **fragment_description(fragment))
    for index, frame in enumerate(frames):
        if index >= len(fragment.data):
            delay = 4 if index == len(fragment.data) else 2
            record("shortcut_write_delay", milliseconds=delay)
            time.sleep(delay / 1000)
        record("shortcut_write_intent", ordinal=index + 1, ioctl=f"0x{SET_FEATURE:08x}", frame_hex=frame.hex(" "))
        buffer = bytearray(frame)
        try:
            returned = fcntl.ioctl(fd, SET_FEATURE, buffer, True)
        except OSError as error:
            record("shortcut_write_error", ordinal=index + 1, errno=error.errno, message=error.strerror)
            raise
        record("shortcut_write_result", ordinal=index + 1, returned_length=returned, buffer_hex_after=buffer.hex(" "))
        if type(returned) is not int or returned != 8 or buffer != frame:
            raise ValueError("Shortcut write completion is malformed; state may be uncertain")


def validate_backup(saved):
    if (not isinstance(saved, dict) or type(saved.get("schema_version")) is not int or saved["schema_version"] != 1
            or saved["identity"] != IDENTITY or saved["scope"] != "blaze-shortcut-tail-v1"
            or saved["complete_configuration_backup"] is not False
            or saved["allocation_metadata_modified"] is not False
            or saved["existing_payload_and_auxiliary_preserved"] is not True):
        raise ValueError("Not a scoped shortcut backup")
    native = parse_rows(saved["assignments"]) if saved["assignments"] else {}
    shortcuts = parse_shortcuts(saved["shortcuts"])
    normalize_request(native, shortcuts)
    before = parse_snapshot(saved["before"], shortcuts)
    after = parse_snapshot(saved["after"], shortcuts)
    expected, fragments = plan_change(before, native, shortcuts)
    if (after != expected or not fragments or saved["before_sha256"] != snapshot_digest(before)
            or saved["after_sha256"] != snapshot_digest(after)):
        raise ValueError("Shortcut backup hashes or owned-field differences are inconsistent")
    return before, after, native, shortcuts, fragments


def load_backup(path):
    saved = json.loads(read_evidence_file(path))
    return saved, *validate_backup(saved)


def _save_backup(path, saved):
    validate_backup(saved)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "w") as output:
        output.write(json.dumps(saved, indent=2) + "\n")
        output.flush()
        os.fsync(output.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    if load_backup(path)[0] != saved:
        raise ValueError("Durable shortcut backup verification failed")


def _backup(before, after, native, shortcuts):
    return {"schema_version": 1, "identity": IDENTITY, "scope": "blaze-shortcut-tail-v1",
            "assignments": assignment_rows(native) if native else [], "shortcuts": shortcut_rows(shortcuts),
            "before": snapshot_rows(before), "after": snapshot_rows(after),
            "before_sha256": snapshot_digest(before), "after_sha256": snapshot_digest(after),
            "complete_configuration_backup": False, "allocation_metadata_modified": False,
            "existing_payload_and_auxiliary_preserved": True}


def complete_result(after, native, shortcuts, outcome, commits, block_count, write_sets, *, operation, backup=False,
                    activation_requested=False):
    result = {"operation": operation, "outcome": outcome,
              "assignments": assignment_rows(native) if native else [], "shortcuts": shortcut_rows(shortcuts),
              "set_feature_count": 18 * block_count * (2 if backup else 1) + write_sets,
              "get_feature_count": 8 * block_count * (2 if backup else 1), "settings_commits": commits,
              "allocation_metadata_modified": False, **describe_state(after)}
    if backup:
        result["backup_file"] = "shortcut-backup.json"
    result.update(activation_fields(activation_requested, backup))
    if activation_requested and backup:
        result["set_feature_count"] += 2
    return result


def change_shortcuts(target, assignments, shortcuts, capture, recheck, *, accept_write_risk=False, restore_from=None,
                     first_tail_test=False, accept_activation_risk=False):
    if accept_write_risk is not True:
        raise ValueError("Explicit shortcut/tail-write risk acknowledgement is required")
    if type(first_tail_test) is not bool:
        raise ValueError("Field-test scope flag must be boolean")
    check_activation_option(accept_activation_risk, restore=restore_from is not None, first_tail_test=first_tail_test)
    check_host()
    if target.identity() != IDENTITY:
        raise ValueError("Shortcut writes require the exact captured Blaze identity/descriptor")
    saved = None
    if restore_from is None:
        native, shortcuts = normalize_request(assignments, shortcuts)
    else:
        if assignments or shortcuts:
            raise ValueError("Do not mix shortcut restore with new assignments")
        saved, original, desired, native, shortcuts, original_fragments = load_backup(restore_from)
    if first_tail_test and (restore_from is not None or native or shortcuts != {5: Shortcut("F13")}):
        raise ValueError("First tail test authorizes only native slot 5 = F13, without other changes")
    capture = Path(capture)
    capture.mkdir(parents=True, exist_ok=False, mode=0o700)
    journal = Journal(capture / "shortcut-configuration.jsonl")
    try:
        for directory in (capture, capture.parent):
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        operation = "restore" if restore_from is not None else "change"
        journal.record("shortcut_config_session", identity=IDENTITY, report_descriptor_hex=target.descriptor.hex(" "),
                       accepted_write_risk=True, scope="blaze-shortcut-tail-v1", operation=operation,
                       assignments=assignment_rows(native) if native else [], shortcuts=shortcut_rows(shortcuts),
                       restore_basis=saved, first_tail_test=first_tail_test,
                       **({"accepted_activation_risk": True} if accept_activation_risk else {}))
        with validated_handle(target, journal.record, recheck, writable=True) as fd:
            before = _read_snapshot(fd, journal.record, shortcuts, "before",
                                    header_guard=guard_first_tail_test if first_tail_test else None)
            if restore_from is None:
                after, fragments = plan_change(before, native, shortcuts)
            else:
                fragments = restore_plan(before, original, desired, original_fragments)
                after = original
            if fragments:
                if saved is None:
                    saved = _backup(before, after, native, shortcuts)
                journal.progress("backup")
                _save_backup(capture / "shortcut-backup.json", saved)
                journal.record("shortcut_backup_durable", filename="shortcut-backup.json", backup=saved,
                               before_sha256=snapshot_digest(before), after_sha256=snapshot_digest(after))
                for fragment in fragments:
                    _write_fragment(fd, fragment, journal.record)
                verified = _read_snapshot(fd, journal.record, shortcuts, "verify", tuple(before))
                if verified != after:
                    raise ValueError("Shortcut readback differs; retain backup, no automatic retry or rollback")
                if accept_activation_risk:
                    recheck(target)
                    activate_verified_change(fd, journal.record)
                outcome = "written-and-read-back"
            else:
                outcome = "no-change"
        result = complete_result(after, native, shortcuts, outcome, len(fragments), len(before),
                                 sum(len(fragment_frames(fragment)) for fragment in fragments),
                                  operation=operation, backup=bool(fragments), activation_requested=accept_activation_risk)
        journal.record("shortcut_config_complete", **result)
        return result
    except (OSError, ValueError, KeyError, TypeError) as error:
        try:
            journal.record("shortcut_config_failed", error_type=type(error).__name__,
                           message=error.strerror if isinstance(error, OSError) else str(error),
                           recovery="Stop; retain backup and review uncertain state. No retry, cleanup or rollback.")
        except OSError:
            pass
        raise
    finally:
        journal.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--shortcut", action="append", help='JSON object: {"slot":5,"key":"F13","modifiers":[]}')
    group.add_argument("--restore-backup", type=Path)
    parser.add_argument("--assign", action="append", help="optional native SLOT=ACTION in the same Apply")
    parser.add_argument("--accept-shortcut-write-risk", action="store_true", required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--device")
    parser.add_argument("--accept-activation-risk", action="store_true", help=NOTICE)
    parser.add_argument("--first-tail-test", action="store_true",
                        help="restrict the initial field test to slot 5 = F13 and the inspected original button state")
    args = parser.parse_args(argv)
    try:
        check_activation_option(args.accept_activation_risk, restore=args.restore_backup is not None,
                                first_tail_test=args.first_tail_test)
        native = parse_cli_assignments(args.assign) if args.assign else {}
        shortcuts = parse_shortcuts([json.loads(value) for value in args.shortcut]) if args.shortcut else {}
        if args.restore_backup:
            if native:
                raise ValueError("Restore cannot contain new assignments")
            load_backup(args.restore_backup)
        else:
            normalize_request(native, shortcuts)
        if args.first_tail_test and (args.restore_backup is not None or native or shortcut_rows(shortcuts) !=
                                     [{"slot": 5, "key": "F13", "modifiers": []}]):
            raise ValueError("First tail test authorizes only slot 5 = F13")
        check_host()
        baseline, _ = load_baseline(args.baseline)
        if baseline.identity() != IDENTITY:
            raise ValueError("Baseline differs from the exact captured Blaze")
        target = select_target(enumerate_devices(), baseline, args.device)

        def recheck(selected):
            if select_target(enumerate_devices(), baseline, selected.path) != selected:
                raise ValueError("Device changed before shortcut transaction")

        result = change_shortcuts(target, native, shortcuts, args.capture, recheck,
                                  accept_write_risk=True, restore_from=args.restore_backup,
                                  first_tail_test=args.first_tail_test, accept_activation_risk=args.accept_activation_risk)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Shortcut operation failed: {error}. No automatic recovery.", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
