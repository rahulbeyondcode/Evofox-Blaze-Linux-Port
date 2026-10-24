"""Experimental DPI-stage/polling changes in fixed block 0018, with backup/readback.

No lighting, CPI-value, button, macro, firmware, reset or arbitrary-address API.
Nothing runs on import. Hardware use requires an explicit write-risk opt-in.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from .evidence import read_evidence_file
from .feature_read import Journal, check_host, load_baseline, select_target, validated_handle
from .probe import enumerate_devices
from .state_read import IDENTITY, SET_FEATURE, _read_on_validated_handle, fixed_read_steps


POLLING_CODES = {125: 7, 250: 3, 500: 1, 1000: 0}


def _validate_requested_value(field, value):
    if type(value) is not int:
        raise ValueError("Setting value must be an integer, not a coerced value")
    if field == "dpi-stage":
        if not 0 <= value <= 5:
            raise ValueError("DPI stage index must be in 0..5")
    elif field == "polling":
        if value not in POLLING_CODES:
            raise ValueError("Polling setting must be 125, 250, 500 or 1000 Hz")
    else:
        raise ValueError("Only dpi-stage and polling fields are implemented")


def plan_change(original: bytes, field: str, value: int) -> bytes:
    """Change just one owned byte, preserving all other captured state."""
    if (not isinstance(original, bytes) or len(original) != 8 or original[0] & 0xF8 != 0x18
            or original[0] & 7 >= 6 or not original[1] or original[1] & 0xC0
            or not original[1] & (1 << (original[0] & 7))
            or original[6] not in POLLING_CODES.values()):
        raise ValueError("Unrecognized state block; refusing to build a setting write")
    _validate_requested_value(field, value)
    changed = bytearray(original)
    if field == "dpi-stage":
        if not 0 <= value <= 5 or not original[1] & (1 << value):
            raise ValueError("Choose an already-enabled DPI stage index in 0..5")
        changed[0] = (original[0] & 0xF8) | value
    elif field == "polling":
        if value not in POLLING_CODES:
            raise ValueError("Polling setting must be 125, 250, 500 or 1000 Hz")
        changed[6] = POLLING_CODES[value]
    else:
        raise ValueError("Only dpi-stage and polling fields are implemented")
    return bytes(changed)


def load_backup(path: Path):
    raw = read_evidence_file(path)
    saved = json.loads(raw)
    if (saved["schema_version"] != 1 or saved["identity"] != IDENTITY
            or saved["base"] != "0x0018" or saved["length"] != 8
            or saved["complete_configuration_backup"] is not False):
        raise ValueError("Backup is not a scoped base-0018 configuration change")
    before = bytes.fromhex(saved["before_hex"])
    after = bytes.fromhex(saved["after_hex"])
    if (hashlib.sha256(before).hexdigest() != saved["before_sha256"]
            or hashlib.sha256(after).hexdigest() != saved["after_sha256"]
            or plan_change(before, saved["field"], saved["value"]) != after):
        raise ValueError("Backup bytes, hashes or owned-field change are inconsistent")
    return saved, before, after


def _save_backup(path, before, after, field, value):
    saved = {
        "schema_version": 1, "identity": IDENTITY, "base": "0x0018", "length": 8,
        "field": field, "value": value, "before_hex": before.hex(" "), "after_hex": after.hex(" "),
        "before_sha256": hashlib.sha256(before).hexdigest(),
        "after_sha256": hashlib.sha256(after).hexdigest(), "complete_configuration_backup": False,
    }
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "w") as destination:
        destination.write(json.dumps(saved, indent=2) + "\n")
        destination.flush()
        os.fsync(destination.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    # Read the durable file back before any setting-data frame is sent.
    _, loaded_before, loaded_after = load_backup(path)
    if (loaded_before, loaded_after) != (before, after):
        raise ValueError("Durable backup verification failed")


def _write_block(fd, data, record):
    """Exact 0x413a10 shape for base 0018 only; no session-finalize commands."""
    import fcntl

    if not isinstance(data, bytes) or len(data) != 8:
        raise ValueError("Only one complete eight-byte state block may be written")
    frames = [bytes((7, 0x18, 3, index, 0x18, 0, byte, 7)) for index, byte in enumerate(data)]
    frames.extend((bytes.fromhex("07 18 09 00 18 00 00 07"), bytes.fromhex("07 18 00 00 18 00 00 00")))
    for index, frame in enumerate(frames):
        if index in (8, 9):
            delay = 4 if index == 8 else 2
            record("config_delay", milliseconds=delay)
            time.sleep(delay / 1000)
        record("config_write_intent", ordinal=index + 1, ioctl=f"0x{SET_FEATURE:08x}", frame_hex=frame.hex(" "))
        buffer = bytearray(frame)
        try:
            returned = fcntl.ioctl(fd, SET_FEATURE, buffer, True)
        except OSError as error:
            record("config_write_error", ordinal=index + 1, errno=error.errno, message=error.strerror)
            raise
        record("config_write_result", ordinal=index + 1, returned_length=returned, buffer_hex_after=buffer.hex(" "))
        if type(returned) is not int or returned != 8 or buffer != frame:
            raise ValueError("Setting-write result is short or changed; state may be uncertain")


def change_setting(target, field, value, capture: Path, recheck, *, accept_write_risk=False, restore_from=None):
    """Fresh read -> durable partial backup -> one write -> fresh readback.

    On failure, stop. Never retry, blindly roll back, or send guessed activation
    commands. Restore is a separate opt-in operation and refuses intervening edits.
    """
    if accept_write_risk is not True:
        raise ValueError("Explicit setting-write risk acknowledgement is required")
    check_host()
    if target.identity() != IDENTITY:
        raise ValueError("Setting changes require the exact captured Blaze identity and descriptor")
    fixed_read_steps()
    required = restored = None
    if restore_from is not None:
        saved, restored, required = load_backup(restore_from)
        field = saved["field"]
        value = restored[0] & 7 if field == "dpi-stage" else next(hz for hz, code in POLLING_CODES.items() if code == restored[6])
    _validate_requested_value(field, value)
    capture.mkdir(parents=True, exist_ok=False)
    journal = Journal(capture / "configuration.jsonl")
    try:
        journal.record("config_session", identity=target.identity(), field=field, value=value,
                       operation="restore" if restore_from is not None else "change",
                       accepted_write_risk=True, scope="Base 0018, 8 bytes only; no full-device backup")
        with validated_handle(target, journal.record, recheck, writable=True) as fd:
            before = _read_on_validated_handle(fd, lambda event, **fields: journal.record(event, phase="before", **fields))
            if required is not None and before not in (required, restored):
                raise ValueError("Current bytes differ from both backup states; refusing to overwrite intervening changes")
            after = plan_change(before, field, value)
            if restored is not None and after != restored:
                raise ValueError("Restore would change bytes outside the original owned-field difference")
            if before == after:
                result = {"outcome": "no-change", "before_hex": before.hex(" "), "after_hex": after.hex(" ")}
            else:
                _save_backup(capture / "original-state.json", before, after, field, value)
                journal.record("config_backup_durable", filename="original-state.json",
                               before_sha256=hashlib.sha256(before).hexdigest())
                _write_block(fd, after, journal.record)
                verified = _read_on_validated_handle(fd, lambda event, **fields: journal.record(event, phase="verify", **fields))
                if verified != after:
                    raise ValueError("Readback differs from intended bytes; backup retained, no automatic recovery")
                result = {"outcome": "written-and-read-back", "before_hex": before.hex(" "),
                          "after_hex": after.hex(" "), "backup_file": "original-state.json"}
        result.update(behavior_verified=False, complete_configuration_backup=False)
        journal.record("config_complete", **result)
        return result
    except (OSError, ValueError, KeyError, TypeError) as error:
        try:
            journal.record("config_failed", error_type=type(error).__name__,
                           message=error.strerror if isinstance(error, OSError) else str(error),
                           recovery="Stop; retained backup requires a separately authorized restore. No retry or rollback attempted.")
        except OSError:
            pass  # No further device interaction even when failure logging fails.
        raise
    finally:
        journal.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dpi-stage", type=int, choices=range(6), help="already-enabled stage INDEX, not CPI")
    action.add_argument("--polling", type=int, choices=POLLING_CODES, help="source-derived polling setting; frequency not measured")
    action.add_argument("--restore-backup", type=Path, help="original-state.json from an earlier scoped change")
    parser.add_argument("--accept-write-risk", action="store_true", required=True,
                        help="authorize fresh reads, one settings commit and readback; experimental, no automatic rollback")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True, help="NEW directory for journal and durable partial backup")
    parser.add_argument("--device", help="optional baseline-matching hidraw path")
    args = parser.parse_args(argv)
    try:
        check_host()
        baseline, _ = load_baseline(args.baseline)
        if baseline.identity() != IDENTITY:
            raise ValueError("Baseline differs from the exact captured Blaze")
        target = select_target(enumerate_devices(), baseline, args.device)
        def recheck(selected):
            if select_target(enumerate_devices(), baseline, selected.path) != selected:
                raise ValueError("Device identity changed before configuration transaction")
        field = "dpi-stage" if args.dpi_stage is not None else "polling"
        value = args.dpi_stage if args.dpi_stage is not None else args.polling
        result = change_setting(target, field, value, args.capture, recheck, accept_write_risk=True,
                                restore_from=args.restore_backup)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Configuration operation failed: {error}. No automatic retry or recovery.", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
