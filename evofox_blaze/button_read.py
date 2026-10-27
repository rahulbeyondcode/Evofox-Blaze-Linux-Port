"""Opt-in experimental fixed 0008 button read: 18 SETs / 8 GETs, no commit.

New read region, not covered by the earlier base-0018 hardware approvals.
No arbitrary address/length, writes, retries, finalize/reset or input monitoring.
"""

import argparse
import json
from pathlib import Path
import sys
import time

from .buttons import describe_block
from .feature_read import Journal, check_host, load_baseline, select_target, validated_handle
from .probe import enumerate_devices
from .read_preview import Delay, GetFeature, SetFeature
from .state_read import GET_FEATURE, IDENTITY, SET_FEATURE


def button_read_steps():
    """The recovered 413ac0 reader shape, fixed to the source-observed button block.

    The public capture corroborates WRITES at 0008/8 and READS at 0018/8;
    it does not contain a read at 0008. This is explicitly experimental.
    """
    steps = []
    for index in range(8):
        steps.extend((SetFeature(bytes((7, 0x18, 3, index, 8, 0, 0, 7))), Delay(2)))
    steps.extend((Delay(2), SetFeature(bytes.fromhex("07 18 00 00 08 00 00 00"))))
    for index in range(8):
        steps.extend((SetFeature(bytes((7, 0x18, 5, index, 8, 0, 0, 7))),
                      Delay(2), GetFeature(7, 8, 1)))
    steps.extend((Delay(2), SetFeature(bytes.fromhex("07 18 00 00 00 00 00 00"))))
    return tuple(steps)


def _read_buttons_on_handle(fd, record):
    """Internal only: caller owns an explicitly acknowledged, validated handle."""
    import fcntl

    collected = bytearray()
    ordinal = 0
    for step in button_read_steps():
        if isinstance(step, Delay):
            record("button_delay", milliseconds=step.milliseconds)
            time.sleep(step.milliseconds / 1000)
            continue
        ordinal += 1
        is_set = isinstance(step, SetFeature)
        request = SET_FEATURE if is_set else GET_FEATURE
        operation = "SET_FEATURE" if is_set else "GET_FEATURE"
        expected = step.report if is_set else b"\x07" + bytes(7)
        buffer = bytearray(expected)
        record("button_feature_intent", ordinal=ordinal, operation=operation,
               ioctl=f"0x{request:08x}", buffer_hex=buffer.hex(" "))
        try:
            returned = fcntl.ioctl(fd, request, buffer, True)
        except OSError as error:
            record("button_feature_error", ordinal=ordinal, operation=operation,
                   errno=error.errno, message=error.strerror, buffer_hex_after=buffer.hex(" "))
            raise
        record("button_feature_result", ordinal=ordinal, operation=operation,
               returned_length=returned, buffer_hex_after=buffer.hex(" "))
        if (type(returned) is not int or returned != 8 or len(buffer) != 8 or buffer[0] != 7
                or (is_set and buffer != expected)):
            raise ValueError("Button feature completion is short, malformed or changed; stop without cleanup/retry")
        if not is_set:
            collected.append(buffer[1])
    if len(collected) != 8:
        raise ValueError("Incomplete button table; no padding or default assignments allowed")
    return bytes(collected)


def read_buttons_once(target, record, recheck, *, accept_staged_read_risk=False):
    if accept_staged_read_risk is not True:
        raise ValueError("Explicit acknowledgement of NEW base-0008 staged-read risk is required")
    check_host()
    if target.identity() != IDENTITY:
        raise ValueError("Button read requires the exact captured Blaze identity and descriptor")
    with validated_handle(target, record, recheck, writable=True) as fd:
        return _read_buttons_on_handle(fd, record)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-buttons", action="store_true", required=True,
                        help="authorize ONE fixed 0008/8 read, not input-event monitoring")
    parser.add_argument("--accept-staged-read-risk", action="store_true", required=True,
                        help="NEW experimental region: zero-data staging SET_REPORTs, no phase 09/10 or command 20")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True, help="NEW evidence directory, never overwritten")
    parser.add_argument("--device", help="optional baseline-matching hidraw path")
    args = parser.parse_args(argv)
    journal = None
    try:
        check_host()
        baseline, digest = load_baseline(args.baseline)
        if baseline.identity() != IDENTITY:
            raise ValueError("Baseline differs from the exact captured Blaze")
        target = select_target(enumerate_devices(), baseline, args.device)
        args.capture.mkdir(parents=True, exist_ok=False)
        journal = Journal(args.capture / "button-read.jsonl")
        journal.record("button_session", identity=IDENTITY, baseline_sha256=digest,
                       report_descriptor_hex=target.descriptor.hex(" "), base="0x0008", length=8,
                       accepted_staging_risk=True,
                       scope="18 SET + 8 GET; NEW button region; no commit, retry, reset or input monitoring")

        def recheck(selected):
            if select_target(enumerate_devices(), baseline, selected.path) != selected:
                raise ValueError("Device changed before button read")

        data = read_buttons_once(target, journal.record, recheck, accept_staged_read_risk=True)
        result = {"mode": "experimental-button-read", **describe_block(data)}
        journal.record("button_complete", **result)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        if journal is not None:
            try:
                journal.record("button_failed", error_type=type(error).__name__,
                               message=error.strerror if isinstance(error, OSError) else str(error),
                               recovery="Stop; no automatic retry, cleanup writes or rollback")
            except OSError:
                pass
        print(f"Button read failed: {error}. No automatic recovery.", file=sys.stderr)
        return 1
    finally:
        if journal is not None:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
