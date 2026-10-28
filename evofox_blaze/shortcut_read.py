"""Explicitly opt-in inspection of fixed, source-derived shortcut metadata.

Reads the native table, three metadata blocks and the 56 ten-byte descriptors.
No payload-region access, setting commit, arbitrary address or automatic retry.
The read uses zero-data staging SETs; it is NOT a harmless GET-only operation.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from .feature_read import Journal, check_host, load_baseline, select_target, validated_handle
from .probe import enumerate_devices
from .read_preview import Delay, GetFeature, SetFeature
from .state_read import GET_FEATURE, IDENTITY, SET_FEATURE


HEADER_BASES = (0x0008, 0x0068, 0x0070, 0x0078) + tuple(range(0x00a0, 0x02d0, 8))


def header_read_steps(base):
    if type(base) is not int or base not in HEADER_BASES:
        raise ValueError("Only the fixed shortcut metadata blocks may be read")
    return _eight_byte_read_steps(base)


def _eight_byte_read_steps(base):
    # Internal builder only; public readers supply their own fixed allowlist.
    lo, hi = base & 255, base >> 8
    steps = []
    for index in range(8):
        steps.extend((SetFeature(bytes((7, 0x18, 3, index, lo, hi, 0, 7))), Delay(2)))
    steps.extend((Delay(2), SetFeature(bytes((7, 0x18, 0, 0, lo, hi, 0, 0)))))
    for index in range(8):
        steps.extend((SetFeature(bytes((7, 0x18, 5, index, lo, hi, 0, 7))),
                      Delay(2), GetFeature(7, 8, 1)))
    steps.extend((Delay(2), SetFeature(bytes.fromhex("07 18 00 00 00 00 00 00"))))
    return tuple(steps)


def _read_header_on_handle(fd, base, record):
    return _read_fixed_block(fd, base, header_read_steps(base), record)


def _read_fixed_block(fd, base, steps, record):
    import fcntl

    record("shortcut_block_begin", base=f"0x{base:04x}", length=8)
    collected = bytearray()
    ordinal = 0
    for step in steps:
        if isinstance(step, Delay):
            record("shortcut_delay", milliseconds=step.milliseconds)
            time.sleep(step.milliseconds / 1000)
            continue
        ordinal += 1
        is_set = isinstance(step, SetFeature)
        request = SET_FEATURE if is_set else GET_FEATURE
        operation = "SET_FEATURE" if is_set else "GET_FEATURE"
        expected = step.report if is_set else b"\x07" + bytes(7)
        buffer = bytearray(expected)
        record("shortcut_feature_intent", ordinal=ordinal, operation=operation,
               ioctl=f"0x{request:08x}", buffer_hex=buffer.hex(" "))
        try:
            returned = fcntl.ioctl(fd, request, buffer, True)
        except OSError as error:
            record("shortcut_feature_error", ordinal=ordinal, operation=operation,
                   errno=error.errno, message=error.strerror, buffer_hex_after=buffer.hex(" "))
            raise
        record("shortcut_feature_result", ordinal=ordinal, operation=operation,
               returned_length=returned, buffer_hex_after=buffer.hex(" "))
        if (type(returned) is not int or returned != 8 or len(buffer) != 8 or buffer[0] != 7
                or (is_set and buffer != expected)):
            raise ValueError("Shortcut metadata completion is malformed; stop without cleanup/retry")
        if not is_set:
            collected.append(buffer[1])
    data = bytes(collected)
    record("shortcut_block_complete", base=f"0x{base:04x}", collected_hex=data.hex(" "))
    return data


def describe_headers(blocks):
    if (not isinstance(blocks, dict) or tuple(blocks) != HEADER_BASES
            or any(not isinstance(data, bytes) or len(data) != 8 for data in blocks.values())):
        raise ValueError("Expected all 74 fixed metadata blocks in their original order")
    table = b"".join(blocks[base] for base in HEADER_BASES[4:])
    descriptors = []
    for index in range(56):
        data = table[index * 10:index * 10 + 10]
        descriptors.append({
            "vendor_table_group": index // 14, "native_slot": index % 14 + 1,
            "raw_hex": data.hex(" "), "nonzero": any(data),
            "tick_milliseconds_candidate": data[0] + 1,
            "event_count_candidate": (data[1] & 0x7f) | ((data[7] & 0x3f) << 7),
            "keyboard_usage_candidate": data[2],
            "consumer_usage_candidate": int.from_bytes(data[3:5], "little"),
            "record_pointer_candidate": f"0x{data[5] | ((data[6] & 0x3f) << 8):04x}",
            "repeat_flags_candidate": [bool(data[1] & 0x80), bool(data[6] & 0x80),
                                        bool(data[6] & 0x40), bool(data[7] & 0x40)],
        })
    return {
        "blocks": [{"base": f"0x{base:04x}", "collected_hex": data.hex(" "),
                    "sha256": hashlib.sha256(data).hexdigest()} for base, data in blocks.items()],
        "native_button_hex": blocks[8].hex(" "),
        "macro_end_candidate": f"0x{int.from_bytes(blocks[0x68][6:8], 'little'):04x}",
        "auxiliary_pointer_candidates": [f"0x{int.from_bytes(blocks[0x70][i:i + 2], 'little'):04x}"
                                          for i in (0, 2, 4)],
        "stored_end_candidate": f"0x{blocks[0x78][1] | ((blocks[0x78][2] & 0x3f) << 8):04x}",
        "record_descriptors": descriptors,
        "complete_configuration_backup": False,
        "record_payloads_read": False, "behavior_verified": False,
        "interpretation": "Source-derived candidates; no firmware capacity, profile bank or safe allocation inferred",
    }


def read_headers_once(target, record, recheck, *, accept_staged_read_risk=False):
    if accept_staged_read_risk is not True:
        raise ValueError("Explicit acknowledgement of NEW shortcut metadata staged-read risk is required")
    check_host()
    if target.identity() != IDENTITY:
        raise ValueError("Shortcut metadata read requires the exact captured Blaze identity/descriptor")
    with validated_handle(target, record, recheck, writable=True) as fd:
        return {base: _read_header_on_handle(fd, base, record) for base in HEADER_BASES}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-shortcut-headers", action="store_true", required=True)
    parser.add_argument("--accept-staged-read-risk", action="store_true", required=True,
                        help="authorize 74 fixed reads: 1332 staging/request SETs, 592 GETs, no commit")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True, help="NEW private evidence directory")
    parser.add_argument("--device")
    args = parser.parse_args(argv)
    journal = None
    try:
        check_host()
        baseline, digest = load_baseline(args.baseline)
        if baseline.identity() != IDENTITY:
            raise ValueError("Baseline differs from the exact captured Blaze")
        target = select_target(enumerate_devices(), baseline, args.device)
        args.capture.mkdir(parents=True, exist_ok=False, mode=0o700)
        journal = Journal(args.capture / "shortcut-headers.jsonl")
        # Persist the journal name and newly created capture-directory entry
        # before the first feature intent can reach the device.
        for directory in (args.capture, args.capture.parent):
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        journal.record("shortcut_header_session", identity=IDENTITY, baseline_sha256=digest,
                       report_descriptor_hex=target.descriptor.hex(" "), accepted_staging_risk=True,
                       bases=[f"0x{base:04x}" for base in HEADER_BASES], length=8,
                       scope="Fixed metadata only; NEW regions; 1332 SET / 592 GET; no commit, payload access or retry")

        def recheck(selected):
            if select_target(enumerate_devices(), baseline, selected.path) != selected:
                raise ValueError("Device changed before shortcut metadata read")

        result = {"mode": "experimental-shortcut-headers",
                  **describe_headers(read_headers_once(target, journal.record, recheck,
                                                       accept_staged_read_risk=True))}
        journal.record("shortcut_header_complete", **result)
        # Summarize counts, not stored keyboard contents, on the terminal.
        print(json.dumps({"outcome": "metadata-read", "blocks_read": len(HEADER_BASES),
                          "nonzero_descriptors": sum(row["nonzero"] for row in result["record_descriptors"]),
                          "record_payloads_read": False, "settings_commits": 0}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        if journal is not None:
            try:
                journal.record("shortcut_header_failed", error_type=type(error).__name__,
                               message=error.strerror if isinstance(error, OSError) else str(error),
                               recovery="Stop; no automatic retry, cleanup writes or rollback")
            except OSError:
                pass
        print(f"Shortcut metadata read failed: {error}. No automatic recovery.", file=sys.stderr)
        return 1
    finally:
        if journal is not None:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
