"""Experimental vendor end-of-settings sequence; default operation is offline.

Default/--preview is offline. --activate --accept-activation-risk explicitly
authorizes exactly two fixed SET_FEATUREs, separated by 5 ms. The sequence may
reload ALL stored settings, not just one button. Its effect on Blaze firmware
has not been validated. No setting-data frames, GETs, command 20, USB reset,
driver detach, retry, rollback or input monitoring are performed.
"""

import argparse
import json
import os
from pathlib import Path
import sys
import time

from .feature_read import Journal, check_host, load_baseline, select_target, validated_handle
from .probe import enumerate_devices
from .read_preview import Delay, SetFeature
from .state_read import IDENTITY, SET_FEATURE


NOTICE = ("Experimental end-of-settings candidate; may activate all stored settings. "
          "Runtime effect unverified; no configuration backup, retry or automatic recovery.")
APPLY_NOTICE = ("Experimental immediate activation is armed: Apply also sends two fixed reload-candidate reports "
                "after backup and verified readback. May activate ALL stored settings; firmware effects are unverified. "
                "No automatic retry. Save and startup remain offline.")
APPLY_BANNER = "Experimental activation armed — Apply may reload ALL stored settings. Firmware effects unverified; no retry."


def check_activation_option(value, *, restore=False, field=None, first_tail_test=False):
    if type(value) is not bool:
        raise ValueError("Activation risk opt-in must be boolean")
    if value and (restore or first_tail_test or (field is not None and field != "polling")):
        raise ValueError("Experimental activation is only supported for new button/shortcut/polling changes, not restores or field tests")
    return value


def activation_fields(requested, written):
    return ({"activation_requested": True, "activation_outcome": "sequence-sent" if written else "skipped-no-change",
             "activation_behavior_verified": False} if requested else {})


def activation_summary():
    return {"outcome": "sequence-sent", "set_features": 2, "get_features": 0,
            "behavior_verified": False, "complete_configuration_backup": False}


def activation_completion_matches(complete, requested, written):
    expected = activation_fields(True, written)
    return (all(type(complete.get(key)) is type(value) and complete.get(key) == value
                for key, value in expected.items()) if requested else
            not any(key in complete for key in expected))


def activation_steps():
    """Literal 0x413d60 sequence; no address, payload or delay parameters."""
    return (SetFeature(bytes.fromhex("07 18 10 00 00 00 00 00")),
            Delay(5), SetFeature(bytes.fromhex("07 18 00 00 00 00 00 00")))


def preview():
    return {"mode": "offline-preview", "hardware_access": False,
            "steps": [{"operation": "SET_FEATURE", "frame_hex": step.report.hex(" ")}
                      if isinstance(step, SetFeature) else
                      {"operation": "delay", "milliseconds": step.milliseconds}
                      for step in activation_steps()],
            "notice": NOTICE}


def _activate_on_handle(fd, record):
    """Fixed sequence on an already validated, locked handle; never cleanup."""
    import fcntl

    ordinal = 0
    for step in activation_steps():
        if isinstance(step, Delay):
            record("activation_delay", milliseconds=step.milliseconds)
            time.sleep(step.milliseconds / 1000)
            continue
        ordinal += 1
        frame = step.report
        record("activation_intent", ordinal=ordinal, ioctl=f"0x{SET_FEATURE:08x}", frame_hex=frame.hex(" "))
        buffer = bytearray(frame)
        try:
            returned = fcntl.ioctl(fd, SET_FEATURE, buffer, True)
        except OSError as error:
            record("activation_error", ordinal=ordinal, errno=error.errno, message=error.strerror)
            raise
        record("activation_result", ordinal=ordinal, returned_length=returned, buffer_hex_after=buffer.hex(" "))
        if type(returned) is not int or returned != 8 or buffer != frame:
            raise ValueError("Activation completion is short or changed; runtime state may be uncertain")
    return activation_summary()


def activate_verified_change(fd, record):
    """Called only after durable backup, successful writes and matching readback."""
    record("activation_begin", scope=NOTICE, stage="after-verified-readback")
    result = _activate_on_handle(fd, record)
    record("activation_complete", **result)


def activate_once(target, record, recheck, *, accept_activation_risk=False):
    """Standalone test: strict opt-in, fresh handle validation and no settings write."""
    if accept_activation_risk is not True:
        raise ValueError("Explicit activation-risk acknowledgement is required")
    check_host()
    if target.identity() != IDENTITY:
        raise ValueError("Activation requires the exact captured Blaze identity/descriptor")
    with validated_handle(target, record, recheck, writable=True) as fd:
        return _activate_on_handle(fd, record)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true", help="offline preview (the default)")
    mode.add_argument("--activate", action="store_true", help="send the experimental fixed sequence once")
    parser.add_argument("--accept-activation-risk", action="store_true", help=NOTICE)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--capture", type=Path, help="NEW private evidence directory; not a configuration backup")
    parser.add_argument("--device")
    args = parser.parse_args(argv)
    if not args.activate:
        if args.accept_activation_risk or args.baseline or args.capture or args.device:
            parser.error("Live-operation options require --activate; preview never contacts hardware")
        print(json.dumps(preview(), indent=2))
        return 0
    if not args.accept_activation_risk or not args.baseline or not args.capture:
        parser.error("--activate requires --accept-activation-risk, --baseline and --capture")
    journal = None
    try:
        check_host()
        baseline, baseline_hash = load_baseline(args.baseline)
        if baseline.identity() != IDENTITY:
            raise ValueError("Baseline differs from the exact captured Blaze")
        # Refuse an existing destination before enumeration/opening hardware.
        args.capture.mkdir(parents=True, mode=0o700, exist_ok=False)
        journal = Journal(args.capture / "activation.jsonl")
        directory = os.open(args.capture, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        journal.record("activation_session", identity=IDENTITY,
                       report_descriptor_hex=baseline.descriptor.hex(" "),
                       baseline_sha256=baseline_hash, accepted_activation_risk=True,
                       scope=NOTICE)
        target = select_target(enumerate_devices(), baseline, args.device)

        def recheck(selected):
            if select_target(enumerate_devices(), baseline, selected.path) != selected:
                raise ValueError("Device changed before activation sequence")

        result = activate_once(target, journal.record, recheck, accept_activation_risk=True)
        journal.record("activation_complete", **result)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        if journal is not None:
            try:
                journal.record("activation_failed", error_type=type(error).__name__,
                               message=error.strerror if isinstance(error, OSError) else str(error),
                               recovery="Stop. Runtime effect may be uncertain. No retry or cleanup command.")
            except OSError:
                pass
        print(f"Activation failed: {error}. No automatic retry or recovery.", file=sys.stderr)
        return 1
    finally:
        if journal is not None:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
