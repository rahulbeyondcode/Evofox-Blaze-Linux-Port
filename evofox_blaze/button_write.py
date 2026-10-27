"""Experimental native button assignments in fixed 0008/8, with backup/readback.

No extension-record writes, keyboard/macro bytecode, profile banks, reset,
arbitrary addresses, retries or blind rollback. Experimental activation is a
separate explicit opt-in, only after a new change's verified readback.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from .button_read import _read_buttons_on_handle
from .activation import NOTICE, activate_verified_change, activation_fields, check_activation_option
from .buttons import ACTION_CODES, BLOCK_SLOTS, plan_assignments
from .evidence import read_evidence_file
from .feature_read import Journal, check_host, load_baseline, select_target, validated_handle
from .probe import enumerate_devices
from .state_read import IDENTITY, SET_FEATURE


def assignment_rows(assignments):
    if (not isinstance(assignments, dict) or not assignments
            or any(type(slot) is not int or slot not in BLOCK_SLOTS
                   or not isinstance(action, str) or action not in ACTION_CODES
                   for slot, action in assignments.items())):
        raise ValueError("Unsupported native slot/action assignments")
    return [{"slot": slot, "action": assignments[slot]} for slot in sorted(assignments)]


def parse_rows(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError("Expected a nonempty list of native slot/action assignments")
    assignments = {}
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {"slot", "action"}
                or type(row["slot"]) is not int or row["slot"] not in BLOCK_SLOTS
                or not isinstance(row["action"], str) or row["action"] not in ACTION_CODES
                or row["slot"] in assignments):
            raise ValueError("Unsupported or duplicate native button assignment")
        assignments[row["slot"]] = row["action"]
    return assignments


def validate_backup(saved):
    if (not isinstance(saved, dict) or type(saved.get("schema_version")) is not int
            or saved["schema_version"] != 1 or saved["identity"] != IDENTITY
            or saved["base"] != "0x0008" or type(saved["length"]) is not int or saved["length"] != 8
            or saved["complete_configuration_backup"] is not False
            or saved["extension_records_modified"] is not False):
        raise ValueError("Not a scoped native-button backup")
    before, after = bytes.fromhex(saved["before_hex"]), bytes.fromhex(saved["after_hex"])
    assignments = parse_rows(saved["assignments"])
    if (hashlib.sha256(before).hexdigest() != saved["before_sha256"]
            or hashlib.sha256(after).hexdigest() != saved["after_sha256"]
            or plan_assignments(before, assignments) != after or before == after):
        raise ValueError("Button backup hashes or owned-field differences are inconsistent")
    return before, after, assignments


def load_backup(path):
    raw = read_evidence_file(path)
    saved = json.loads(raw)
    return saved, *validate_backup(saved)


def _save_backup(path, saved):
    """Persist both directions before data frames, including for an explicit restore."""
    validate_backup(saved)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "w") as out:
        out.write(json.dumps(saved, indent=2) + "\n")
        out.flush()
        os.fsync(out.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    loaded, _, _, _ = load_backup(path)
    if loaded != saved:
        raise ValueError("Durable button backup verification failed")


def button_write_frames(data):
    if not isinstance(data, bytes) or len(data) != 8:
        raise ValueError("Only a complete eight-byte button table is supported")
    frames = [bytes((7, 0x18, 3, i, 8, 0, value, 7)) for i, value in enumerate(data)]
    frames.extend((bytes.fromhex("07 18 09 00 08 00 00 07"), bytes.fromhex("07 18 00 00 08 00 00 00")))
    return tuple(frames)


def _write_buttons_on_handle(fd, data, record):
    import fcntl

    for index, frame in enumerate(button_write_frames(data)):
        if index in (8, 9):
            milliseconds = 4 if index == 8 else 2
            record("button_write_delay", milliseconds=milliseconds)
            time.sleep(milliseconds / 1000)
        record("button_write_intent", ordinal=index + 1, ioctl=f"0x{SET_FEATURE:08x}", frame_hex=frame.hex(" "))
        buffer = bytearray(frame)
        try:
            returned = fcntl.ioctl(fd, SET_FEATURE, buffer, True)
        except OSError as error:
            record("button_write_error", ordinal=index + 1, errno=error.errno, message=error.strerror)
            raise
        record("button_write_result", ordinal=index + 1, returned_length=returned, buffer_hex_after=buffer.hex(" "))
        if type(returned) is not int or returned != 8 or buffer != frame:
            raise ValueError("Button write completion is short or changed; state may be uncertain")


def change_buttons(target, assignments, capture, recheck, *, accept_write_risk=False, restore_from=None,
                   accept_activation_risk=False):
    if accept_write_risk is not True:
        raise ValueError("Explicit native button-write risk acknowledgement is required")
    check_activation_option(accept_activation_risk, restore=restore_from is not None)
    check_host()
    if target.identity() != IDENTITY:
        raise ValueError("Native button writes require the exact captured Blaze identity/descriptor")
    restored = required = saved = None
    if restore_from is not None:
        if assignments:
            raise ValueError("Do not mix restore and new assignments")
        saved, restored, required, assignments = load_backup(restore_from)
    else:
        # Check all request values before enumeration/open or a staged read.
        assignments = parse_rows(assignment_rows(assignments))
    capture = Path(capture)
    capture.mkdir(parents=True, exist_ok=False)
    journal = Journal(capture / "button-configuration.jsonl")
    try:
        journal.record("button_config_session", identity=IDENTITY,
                       report_descriptor_hex=target.descriptor.hex(" "), base="0x0008", length=8,
                       operation="restore" if restore_from is not None else "change",
                        assignments=assignment_rows(assignments), accepted_write_risk=True,
                        restore_basis=saved,
                        scope=("Fixed button block; extension records untouched; explicit activation candidate after readback; no reset/retry"
                               if accept_activation_risk else
                               "Fixed button block only; extension records untouched; no activation/reset or automatic recovery"),
                        **({"accepted_activation_risk": True} if accept_activation_risk else {}))
        with validated_handle(target, journal.record, recheck, writable=True) as fd:
            before = _read_buttons_on_handle(fd, lambda event, **fields: journal.record(event, phase="before", **fields))
            if restore_from is not None:
                if before not in (required, restored):
                    raise ValueError("Current table differs from both backup states; refusing intervening edits")
                after = restored
            else:
                after = plan_assignments(before, assignments)
            if before == after:
                result = {"outcome": "no-change", "before_hex": before.hex(" "), "after_hex": after.hex(" ")}
            else:
                if saved is None:
                    saved = {"schema_version": 1, "identity": IDENTITY, "base": "0x0008", "length": 8,
                             "assignments": assignment_rows(assignments), "before_hex": before.hex(" "),
                             "after_hex": after.hex(" "), "before_sha256": hashlib.sha256(before).hexdigest(),
                             "after_sha256": hashlib.sha256(after).hexdigest(),
                             "complete_configuration_backup": False, "extension_records_modified": False}
                # A restore copies the original validated two-state backup into
                # its NEW directory. This preserves opaque original links without
                # pretending they are synthesizable built-in actions.
                journal.progress("backup")
                _save_backup(capture / "button-backup.json", saved)
                journal.record("button_backup_durable", filename="button-backup.json", backup=saved,
                               before_sha256=hashlib.sha256(before).hexdigest(),
                               after_sha256=hashlib.sha256(after).hexdigest())
                _write_buttons_on_handle(fd, after, journal.record)
                verified = _read_buttons_on_handle(fd, lambda event, **fields: journal.record(event, phase="verify", **fields))
                if verified != after:
                    raise ValueError("Button readback differs; backup retained, no automatic retry or rollback")
                if accept_activation_risk:
                    recheck(target)
                    activate_verified_change(fd, journal.record)
                result = {"outcome": "written-and-read-back", "before_hex": before.hex(" "),
                          "after_hex": after.hex(" "), "backup_file": "button-backup.json"}
        result.update(behavior_verified=False, complete_configuration_backup=False, extension_records_modified=False)
        result.update(activation_fields(accept_activation_risk, before != after))
        journal.record("button_config_complete", **result)
        return result
    except (OSError, ValueError, KeyError, TypeError) as error:
        try:
            journal.record("button_config_failed", error_type=type(error).__name__,
                           message=error.strerror if isinstance(error, OSError) else str(error),
                           recovery="Stop; retain backup and review uncertain state. No retry, cleanup or rollback.")
        except OSError:
            pass
        raise
    finally:
        journal.close()


def parse_cli_assignments(values):
    rows = []
    for value in values or []:
        slot, separator, action = value.partition("=")
        if not separator or not slot.isascii() or not slot.isdecimal():
            raise ValueError("Use --assign SLOT=ACTION (for example 4=back)")
        rows.append({"slot": int(slot), "action": action})
    return parse_rows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--assign", action="append", metavar="SLOT=ACTION", help="repeat for multiple native assignments in one block")
    group.add_argument("--restore-backup", type=Path)
    parser.add_argument("--accept-write-risk", action="store_true", required=True,
                        help="authorize fresh staged reads, one button commit and readback; runtime activation not guaranteed")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True, help="NEW directory for journal/backup")
    parser.add_argument("--device")
    parser.add_argument("--accept-activation-risk", action="store_true", help=NOTICE)
    args = parser.parse_args(argv)
    try:
        check_activation_option(args.accept_activation_risk, restore=args.restore_backup is not None)
        assignments = parse_cli_assignments(args.assign) if args.assign else None
        if args.restore_backup:
            load_backup(args.restore_backup)
        check_host()
        baseline, _ = load_baseline(args.baseline)
        if baseline.identity() != IDENTITY:
            raise ValueError("Baseline differs from the exact captured Blaze")
        target = select_target(enumerate_devices(), baseline, args.device)

        def recheck(selected):
            if select_target(enumerate_devices(), baseline, selected.path) != selected:
                raise ValueError("Device changed before native button transaction")

        result = change_buttons(target, assignments, args.capture, recheck, accept_write_risk=True,
                                restore_from=args.restore_backup, accept_activation_risk=args.accept_activation_risk)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Native button operation failed: {error}. No automatic retry or recovery.", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
