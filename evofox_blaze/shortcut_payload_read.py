"""Opt-in first shortcut-record inspection, fixed to 0400..045f (96 bytes).

Scope is based on the separately captured Blaze metadata. Includes the three
existing records, ancillary bytes and a 40-byte candidate tail backup. No setting
commit, allocation/write, arbitrary address, input monitoring or automatic retry.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from .feature_read import Journal, check_host, load_baseline, select_target, validated_handle
from .probe import enumerate_devices
from .shortcut_capture import consume_fixed_block, decode_shortcut_header_capture
from .shortcut_read import _eight_byte_read_steps, _read_fixed_block
from .state_read import IDENTITY
from .evidence import read_evidence_file


PAYLOAD_BASES = tuple(range(0x0400, 0x0460, 8))


def payload_read_steps(base):
    if type(base) is not int or base not in PAYLOAD_BASES:
        raise ValueError("First shortcut payload inspection is fixed to 0400..045f")
    return _eight_byte_read_steps(base)


def validate_basis(basis):
    if (basis.get("mode") != "offline-shortcut-header-inspection" or basis["identity"] != IDENTITY
            or basis["macro_end_candidate"] != "0x0418"
            or basis["auxiliary_pointer_candidates"] != ["0x0420", "0x0428", "0x0430"]
            or basis["stored_end_candidate"] != "0x0438"):
        raise ValueError("Payload inspection requires the captured 0418/0438 metadata layout")
    expected = [(0, 4, "0x0400", 3), (0, 5, "0x0408", 3), (0, 9, "0x0410", 2)]
    actual = [(row["vendor_table_group"], row["native_slot"], row["record_pointer_candidate"],
               row["event_count_candidate"]) for row in basis["record_descriptors"] if row["nonzero"]]
    if actual != expected:
        raise ValueError("Payload inspection descriptor boundaries differ from the reviewed snapshot")


def read_payload_once(target, record, recheck, basis, *, accept_staged_read_risk=False):
    if accept_staged_read_risk is not True:
        raise ValueError("Explicit acknowledgement of NEW shortcut payload staged-read risk is required")
    validate_basis(basis)
    check_host()
    if target.identity() != IDENTITY:
        raise ValueError("Shortcut payload read requires the exact captured Blaze identity/descriptor")
    with validated_handle(target, record, recheck, writable=True) as fd:
        return b"".join(_read_fixed_block(fd, base, payload_read_steps(base), record) for base in PAYLOAD_BASES)


def describe_payload(data):
    if not isinstance(data, bytes) or len(data) != 96:
        raise ValueError("Expected exactly 96 collected bytes; no padding/default payloads")
    return {"base": "0x0400", "length": 96, "collected_hex": data.hex(" "),
            "sha256": hashlib.sha256(data).hexdigest(),
            "complete_configuration_backup": False, "behavior_verified": False,
            "settings_commits": 0,
            "interpretation": "Partial payload snapshot, not proof of free allocation or current metadata equality"}


def decode_payload_journal(raw):
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if any(not isinstance(event, dict) for event in events):
        raise ValueError("Payload journal events must be objects")
    position = 0

    def take(kind):
        nonlocal position
        if position >= len(events) or events[position].get("event") != kind:
            raise ValueError(f"Expected {kind}; incomplete, failed or unexpected operation")
        event = events[position]
        position += 1
        return event

    session = take("shortcut_payload_session")
    basis = session["header_basis"]
    validate_basis(basis)
    if (session["identity"] != IDENTITY or session["accepted_staging_risk"] is not True
            or session["bases"] != [f"0x{base:04x}" for base in PAYLOAD_BASES]
            or hashlib.sha256(bytes.fromhex(session["report_descriptor_hex"])).hexdigest()
            != IDENTITY["report_descriptor_sha256"]):
        raise ValueError("Payload session identity/scope differs")
    handle = take("handle_validated")
    if handle["identity"] != IDENTITY or handle["bus"] != 3:
        raise ValueError("Payload handle differs")
    data = b"".join(consume_fixed_block(take, base, payload_read_steps(base)) for base in PAYLOAD_BASES)
    expected = describe_payload(data)
    complete = take("shortcut_payload_complete")
    if (position != len(events) or any(type(complete.get(key)) is not type(value) or complete[key] != value
                                       for key, value in expected.items())):
        raise ValueError("Payload completion differs or overclaims verification")
    return {"mode": "offline-shortcut-payload-inspection", "identity": IDENTITY,
            "capture_sha256": hashlib.sha256(raw).hexdigest(), "header_basis": basis,
            "set_feature_count": 216, "get_feature_count": 96, **expected}


def decode_payload_capture(path):
    return decode_payload_journal(read_evidence_file(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-shortcut-payload", action="store_true", required=True)
    parser.add_argument("--accept-staged-read-risk", action="store_true", required=True)
    parser.add_argument("--headers", type=Path, required=True, help="validated saved metadata journal; not a live read")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--device")
    args = parser.parse_args(argv)
    journal = None
    try:
        basis = decode_shortcut_header_capture(args.headers)
        validate_basis(basis)
        check_host()
        baseline, _ = load_baseline(args.baseline)
        if baseline.identity() != IDENTITY:
            raise ValueError("Baseline differs from the exact captured Blaze")
        target = select_target(enumerate_devices(), baseline, args.device)
        args.capture.mkdir(parents=True, exist_ok=False, mode=0o700)
        journal = Journal(args.capture / "shortcut-payload.jsonl")
        for directory in (args.capture, args.capture.parent):
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        journal.record("shortcut_payload_session", identity=IDENTITY,
                       report_descriptor_hex=target.descriptor.hex(" "), accepted_staging_risk=True,
                       header_basis=basis, bases=[f"0x{base:04x}" for base in PAYLOAD_BASES],
                       scope="216 SET / 96 GET; fixed 0400..045f only; no commit, allocation, retry or input monitoring")

        def recheck(selected):
            if select_target(enumerate_devices(), baseline, selected.path) != selected:
                raise ValueError("Device changed before payload read")

        data = read_payload_once(target, journal.record, recheck, basis, accept_staged_read_risk=True)
        journal.record("shortcut_payload_complete", **describe_payload(data))
        print(json.dumps({"outcome": "payload-read", "collected_length": len(data), "settings_commits": 0}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        if journal is not None:
            try:
                journal.record("shortcut_payload_failed", error_type=type(error).__name__,
                               message=error.strerror if isinstance(error, OSError) else str(error),
                               recovery="Stop; no automatic retry, cleanup writes or rollback")
            except OSError:
                pass
        print(f"Shortcut payload read failed: {error}. No automatic recovery.", file=sys.stderr)
        return 1
    finally:
        if journal is not None:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
