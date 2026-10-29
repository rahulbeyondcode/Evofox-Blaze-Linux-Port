"""Explicit, scoped read of native assignments and supported keyboard records.

No automatic startup read, settings commit, arbitrary address, retry or monitor.
Only the inspected allocation layout is accepted. Original guard blocks and all
recognized owned tail slots are read using the existing zero-data staged reader.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from .feature_read import Journal, check_host, load_baseline, select_target, validated_handle
from .probe import enumerate_devices
from .shortcut_write import _read_snapshot
from .shortcut_config_capture import consume_snapshot
from .shortcut_plan import describe_state
from .evidence import read_assignment_journal
from .state_read import IDENTITY


def summary(blocks):
    return {"outcome": "assignments-read", "block_count": len(blocks),
            "set_feature_count": len(blocks) * 18, "get_feature_count": len(blocks) * 8,
            "settings_commits": 0, **describe_state(blocks)}


def read_assignments_once(target, record, recheck, *, accept_staged_read_risk=False):
    if accept_staged_read_risk is not True:
        raise ValueError("Explicit shortcut-assignment staged-read risk acknowledgement is required")
    check_host()
    if target.identity() != IDENTITY:
        raise ValueError("Assignment reads require the captured Blaze identity and descriptor")
    with validated_handle(target, record, recheck, writable=True) as fd:
        return _read_snapshot(fd, record, {}, "read")


def decode_assignment_journal(raw):
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if any(not isinstance(event, dict) for event in events):
        raise ValueError("Assignment events must be objects")
    position = 0

    def take(kind):
        nonlocal position
        if position >= len(events) or events[position].get("event") != kind:
            raise ValueError(f"Expected {kind}; incomplete, failed or unexpected read")
        event = events[position]
        position += 1
        return event

    session = take("assignment_read_session")
    if (session["identity"] != IDENTITY or session["accepted_staging_risk"] is not True
            or session["scope"] != "blaze-shortcut-assignments-v1"
            or hashlib.sha256(bytes.fromhex(session["report_descriptor_hex"])).hexdigest()
            != IDENTITY["report_descriptor_sha256"]):
        raise ValueError("Assignment session identity/descriptor/scope differs")
    handle = take("handle_validated")
    if handle["identity"] != IDENTITY or handle["bus"] != 3:
        raise ValueError("Assignment handle differs")
    blocks = consume_snapshot(take, {}, "read")
    expected = summary(blocks)
    complete = take("assignment_read_complete")
    if position != len(events) or any(type(complete.get(k)) is not type(v) or complete[k] != v
                                       for k, v in expected.items()):
        raise ValueError("Assignment completion differs or overclaims verification")
    return {"mode": "offline-assignment-inspection", "identity": IDENTITY,
            "capture_sha256": hashlib.sha256(raw).hexdigest(), **expected}


def decode_assignment_capture(path):
    return decode_assignment_journal(read_assignment_journal(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-assignments", action="store_true", required=True)
    parser.add_argument("--accept-staged-read-risk", action="store_true", required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--device")
    args = parser.parse_args(argv)
    journal = None
    try:
        check_host()
        baseline, _ = load_baseline(args.baseline)
        if baseline.identity() != IDENTITY:
            raise ValueError("Baseline differs from the exact captured Blaze")
        target = select_target(enumerate_devices(), baseline, args.device)
        args.capture.mkdir(parents=True, exist_ok=False, mode=0o700)
        journal = Journal(args.capture / "assignments.jsonl")
        for directory in (args.capture, args.capture.parent):
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        journal.record("assignment_read_session", identity=IDENTITY, report_descriptor_hex=target.descriptor.hex(" "),
                       accepted_staging_risk=True, scope="blaze-shortcut-assignments-v1")

        def recheck(selected):
            if select_target(enumerate_devices(), baseline, selected.path) != selected:
                raise ValueError("Device changed before assignment read")

        blocks = read_assignments_once(target, journal.record, recheck, accept_staged_read_risk=True)
        result = summary(blocks)
        journal.record("assignment_read_complete", **result)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        if journal is not None:
            try:
                journal.record("assignment_read_failed", message=str(error), recovery="Stop; no automatic retry or recovery")
            except OSError:
                pass
        print(f"Assignment read failed: {error}. No automatic recovery.", file=sys.stderr)
        return 1
    finally:
        if journal is not None:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
