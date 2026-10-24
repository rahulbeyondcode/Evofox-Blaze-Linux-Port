"""Experimental fixed base-0018 read: SET_REPORT preparation, no commit or retries."""

import argparse
import json
from pathlib import Path
import platform
import sys
import time

from . import __version__
from .feature_read import Journal, check_host, load_baseline, select_target, validated_handle
from .probe import enumerate_devices
from .read_preview import Delay, GetFeature, SetFeature, decode_state_block, preview_read


# This is deliberately narrower than the descriptor probe and standalone GET.
# No generic A825 identity, alternate revision, address, or report length.
IDENTITY = {
    "vid": "30fa", "pid": "1440", "bcdDevice": "0100", "interface": "01",
    "report_descriptor_sha256": "0ec3eb2dc293bd8edcb490f5cee9ab272ebec8f4e0edc5f9f365f1bab53b2018",
    "report_id": 7, "report_length": 8,
}
SET_FEATURE = 0xC0084806
GET_FEATURE = 0xC0084807


def fixed_read_steps():
    """Fail closed if the offline planner ever adds a different operation."""
    steps = preview_read("dpi-state", report_length=8)
    expected = []
    for index in range(8):
        expected.extend((SetFeature(bytes((7, 0x18, 3, index, 0x18, 0, 0, 7))), Delay(2)))
    expected.extend((Delay(2), SetFeature(bytes.fromhex("07 18 00 00 18 00 00 00"))))
    for index in range(8):
        expected.extend((SetFeature(bytes((7, 0x18, 5, index, 0x18, 0, 0, 7))),
                         Delay(2), GetFeature(7, 8, 1)))
    expected.extend((Delay(2), SetFeature(bytes.fromhex("07 18 00 00 00 00 00 00"))))
    if steps != tuple(expected):
        raise ValueError("Planner differs from the exact source/capture-matched base-0018 read")
    return steps


def read_state_once(target, record, recheck, *, accept_staged_read_risk=False):
    """Collect eight bytes once. Not a full configuration backup or safe-write API.

    Requires explicit acknowledgement even for direct Python callers. Hardware
    failure or a logging failure aborts immediately: no retries or speculative
    cleanup requests, and never phase 09/10 or command 20.
    """
    if accept_staged_read_risk is not True:
        raise ValueError("Explicit acknowledgement of SET_REPORT staging risk is required")
    check_host()
    if target.identity() != IDENTITY:
        raise ValueError("State read requires the exact captured 30fa:1440/0100 interface and descriptor")
    fixed_read_steps()
    with validated_handle(target, record, recheck, writable=True) as fd:
        return _read_on_validated_handle(fd, record)


def _read_on_validated_handle(fd, record):
    """Internal fixed read; callers must own an acknowledged, validated handle."""
    import fcntl

    collected = bytearray()
    ordinal = 0
    for step in fixed_read_steps():
        if isinstance(step, Delay):
            record("state_delay", milliseconds=step.milliseconds)
            time.sleep(step.milliseconds / 1000)
            continue
        ordinal += 1
        is_set = isinstance(step, SetFeature)
        operation = "SET_FEATURE" if is_set else "GET_FEATURE"
        request = SET_FEATURE if is_set else GET_FEATURE
        buffer = bytearray(step.report if is_set else b"\x07" + bytes(7))
        # Must be durable before *each* feature operation, not just before
        # the transaction. A failed intent log prevents the ioctl.
        record("state_feature_intent", ordinal=ordinal, operation=operation,
               ioctl=f"0x{request:08x}", buffer_hex=buffer.hex(" "))
        try:
            returned = fcntl.ioctl(fd, request, buffer, True)
        except OSError as error:
            record("state_feature_error", ordinal=ordinal, operation=operation,
                   errno=error.errno, message=error.strerror, buffer_hex_after=buffer.hex(" "))
            raise
        record("state_feature_result", ordinal=ordinal, operation=operation,
               returned_length=returned, buffer_hex_after=buffer.hex(" "))
        if type(returned) is not int or returned != 8 or len(buffer) != 8 or buffer[0] != 7:
            raise ValueError("Feature result is short, malformed, or has the wrong report ID; aborted")
        if not is_set:
            collected.append(buffer[step.result_byte])
    if len(collected) != 8:
        raise ValueError("Incomplete state read; no padded data accepted")
    return bytes(collected)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-state", action="store_true", required=True,
                        help="authorize ONE fixed eight-byte read, not a scan or a full backup")
    parser.add_argument("--accept-staged-read-risk", action="store_true", required=True,
                        help="acknowledge 18 SET_REPORTs including zero-data staging; experimental fixed-block operation")
    parser.add_argument("--baseline", type=Path, required=True, help="saved descriptor probe.json")
    parser.add_argument("--capture", type=Path, required=True, help="NEW evidence directory; never overwritten")
    parser.add_argument("--device", help="optional session-specific baseline-matching hidraw path")
    args = parser.parse_args(argv)
    journal = None
    try:
        check_host()
        baseline, baseline_hash = load_baseline(args.baseline)
        if baseline.identity() != IDENTITY:
            raise ValueError("Baseline is not the exact captured Blaze interface/revision/descriptor")
        target = select_target(enumerate_devices(), baseline, args.device)
        args.capture.mkdir(parents=True, exist_ok=False)
        journal = Journal(args.capture / "state-read.jsonl")
        journal.record("state_session", tool=f"evofox_blaze.state_read {__version__}",
                       kernel=platform.release(), architecture=platform.machine(),
                       baseline_sha256=baseline_hash, identity=target.identity(),
                       report_descriptor_hex=target.descriptor.hex(" "), base="0x0018", length=8,
                       accepted_staging_risk=True,
                       scope="18 SET_FEATURE + 8 GET_FEATURE; no phase 09/10, command 20, scan, retry or settings commit")

        def recheck(selected):
            if select_target(enumerate_devices(), baseline, selected.path) != selected:
                raise ValueError("Device identity changed before the transaction")

        print("Experimental base-0018 read: 18 SET_REPORTs + 8 GET_REPORTs. "
              "Zero-data staging is included; no commit, retry, or automatic recovery.",
              file=sys.stderr, flush=True)
        data = read_state_once(target, journal.record, recheck, accept_staged_read_risk=True)
        result = {"mode": "experimental-state-read", "base": "0x0018", "length": 8,
                  **decode_state_block(data),
                  "interpretation": "Raw fixed-block read; selector is not a CPI value or a complete backup",
                  "complete_configuration_backup": False}
        journal.record("state_complete", **result)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        if journal is not None:
            try:
                journal.record("state_failed", error_type=type(error).__name__,
                               errno=getattr(error, "errno", None),
                               message=error.strerror if isinstance(error, OSError) else str(error),
                               recovery="No automatic requests; transaction may be incomplete")
            except OSError as log_error:
                print(f"Could not persist failure: {log_error}. Inspect the existing journal; do not retry blindly.",
                      file=sys.stderr)
        print(f"State read failed: {error}", file=sys.stderr)
        return 1
    finally:
        if journal is not None:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
