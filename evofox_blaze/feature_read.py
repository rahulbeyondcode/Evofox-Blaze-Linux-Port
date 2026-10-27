"""Opt-in, one-shot HID GET_FEATURE 07. No SET_REPORT or input-event reads."""

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import struct
import sys

from . import __version__
from .evidence import read_evidence_file
from .hid_descriptor import parse_report_descriptor
from .probe import SUPPORTED_IDS, configuration_report, enumerate_devices
from .operation_progress import PhaseReporter, event_phase


# Linux x86-64 UAPI: linux/hidraw.h and asm-generic/ioctl.h. Other ABIs fail
# closed below; do not assume their direction/size bit layout is identical.
HIDIOCGRDESCSIZE = 0x80044801
HIDIOCGRDESC = 0x90044802  # struct: u32 size + 4096 descriptor bytes
HIDIOCGRAWINFO = 0x80084803


@dataclass(frozen=True)
class Target:
    path: str
    vid: int
    pid: int
    revision: str
    interface: str
    descriptor: bytes
    report_length: int

    def identity(self):
        return {
            "vid": f"{self.vid:04x}", "pid": f"{self.pid:04x}",
            "bcdDevice": self.revision, "interface": self.interface,
            "report_descriptor_sha256": hashlib.sha256(self.descriptor).hexdigest(),
            "report_id": 7, "report_length": self.report_length,
        }


def target_from_node(node):
    if "error" in node:
        raise ValueError("Incomplete descriptor inspection")
    vid, pid = int(node["vid"], 16), int(node["pid"], 16)
    if (vid, pid) not in SUPPORTED_IDS:
        raise ValueError("Unsupported USB identity")
    raw = bytes.fromhex(node["report_descriptor_hex"])
    if hashlib.sha256(raw).hexdigest() != node["report_descriptor_sha256"]:
        raise ValueError("Report descriptor hash mismatch")
    report = configuration_report(parse_report_descriptor(raw))
    if report is None or not 2 <= report.byte_length <= 256:
        raise ValueError("No bounded ff01/0001 feature report 07")
    return Target(
        node.get("path", ""), vid, pid, node["usb"]["bcdDevice"],
        node["interface"]["bInterfaceNumber"], raw, report.byte_length,
    )


def load_baseline(path):
    raw = read_evidence_file(path)
    saved = json.loads(raw)
    if (not isinstance(saved, dict) or saved.get("schema_version") != 1
            or not isinstance(saved.get("nodes"), list)):
        raise ValueError("Expected a version-1 descriptor capture")
    candidates = []
    for node in saved["nodes"]:
        try:
            candidates.append(target_from_node(node))
        except (KeyError, TypeError, ValueError):
            continue
    if len(candidates) != 1:
        raise ValueError("Baseline must contain exactly one complete configuration node")
    return candidates[0], hashlib.sha256(raw).hexdigest()


def select_target(nodes, baseline, requested_path=None):
    matches = []
    for node in nodes:
        try:
            target = target_from_node(node)
        except (KeyError, TypeError, ValueError):
            continue
        if target.identity() == baseline.identity():
            if requested_path is None or target.path == requested_path:
                matches.append(target)
    if len(matches) != 1:
        raise ValueError("Expected one baseline-matching node; use --device if several match")
    return matches[0]


def check_host():
    if sys.platform != "linux" or platform.machine() != "x86_64":
        raise ValueError("Feature ioctl transport currently supports Linux x86-64 only")


@contextmanager
def validated_handle(target, record, recheck, *, writable=False):
    """Pin and validate one HID handle. No feature request is issued here."""
    check_host()
    import fcntl

    # Re-derive the length even if the caller constructed Target manually.
    report = configuration_report(parse_report_descriptor(target.descriptor))
    if ((target.vid, target.pid) not in SUPPORTED_IDS or report is None
            or report.byte_length != target.report_length
            or not 2 <= target.report_length <= 256):
        raise ValueError("Invalid target identity or descriptor-derived length")
    access = os.O_RDWR if writable else os.O_RDONLY
    fd = os.open(target.path, access | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        if not stat.S_ISCHR(os.fstat(fd).st_mode):
            raise ValueError("Selected path is not a character device")
        # Cooperative cross-process serialization for all of our feature tools.
        # Does not claim the USB interface or detach/lock out the kernel driver.
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        info = bytearray(8)
        fcntl.ioctl(fd, HIDIOCGRAWINFO, info, True)
        bus, vid, pid = struct.unpack("=IHH", info)
        if (bus, vid, pid) != (3, target.vid, target.pid):
            raise ValueError("Open handle USB identity differs from selected node")
        size_buffer = bytearray(4)
        fcntl.ioctl(fd, HIDIOCGRDESCSIZE, size_buffer, True)
        size = struct.unpack("=I", size_buffer)[0]
        if not 1 <= size <= 4096 or size != len(target.descriptor):
            raise ValueError("Open handle report descriptor size differs from baseline")
        descriptor_buffer = bytearray(struct.pack("=I", size)) + bytearray(4096)
        fcntl.ioctl(fd, HIDIOCGRDESC, descriptor_buffer, True)
        if (struct.unpack_from("=I", descriptor_buffer)[0] != size
                or descriptor_buffer[4:4 + size] != target.descriptor):
            raise ValueError("Open handle report descriptor differs from baseline")
        # Refresh sysfs revision/interface immediately before the first feature
        # request. This is not an atomic hotplug lock or exclusive device claim.
        recheck(target)
        record("handle_validated", identity=target.identity(), bus=bus, lock_mode="exclusive-advisory")
        yield fd
    finally:
        os.close(fd)


def get_feature_once(target, record, recheck):
    """Issue exactly one GET_FEATURE on a validated handle, with no retries.

    The ioctl's READ|WRITE bits describe its in/out userspace buffer. This is
    HIDIOCGFEATURE, not a USB SET_REPORT. Metadata ioctls do not fetch features.
    """
    import fcntl

    with validated_handle(target, record, recheck) as fd:
        request = 0xC0004807 | (target.report_length << 16)
        buffer = bytearray(target.report_length)
        buffer[0] = 7
        print(f"GET_FEATURE only: {target.path}, ioctl=0x{request:08x}, "
              f"buffer={buffer.hex(' ')}", file=sys.stderr, flush=True)
        # A durable intent must exist before any feature interaction. This
        # buffer is a syscall argument, not an outbound USB payload capture.
        record("get_feature_intent", ioctl=f"0x{request:08x}",
               request_buffer_hex=buffer.hex(" "), requested_length=len(buffer))
        try:
            returned = fcntl.ioctl(fd, request, buffer, True)
        except OSError as error:
            record("get_feature_error", errno=error.errno, message=error.strerror,
                   buffer_hex_after=buffer.hex(" "))
            raise
        record("get_feature_response", returned_length=returned,
               buffer_hex_after=buffer.hex(" "))
        if type(returned) is not int or returned != target.report_length:
            raise ValueError("Feature response length differs from descriptor; no padded data accepted")
        if buffer[0] != 7:
            raise ValueError("Feature response report ID differs from 07")
        return bytes(buffer)


class Journal:
    """Exclusive, append-only JSONL evidence; flush intent before the ioctl."""

    def __init__(self, path):
        self.reporter = PhaseReporter()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
        self.file = os.fdopen(fd, "w")

    def record(self, event, **fields):
        self.file.write(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
                                   "event": event, **fields}) + "\n")
        self.file.flush()
        os.fsync(self.file.fileno())
        self.progress(event_phase(event, fields))

    def progress(self, phase):
        self.reporter.report(phase)

    def close(self):
        self.file.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-feature", action="store_true", required=True,
                        help="explicitly authorize one GET_FEATURE 07, never SET_REPORT")
    parser.add_argument("--baseline", type=Path, required=True, help="existing probe.json capture")
    parser.add_argument("--capture", type=Path, required=True, help="NEW directory for durable evidence")
    parser.add_argument("--device", help="session-specific path, only if it matches the baseline")
    args = parser.parse_args(argv)
    journal = None
    try:
        check_host()
        baseline, baseline_hash = load_baseline(args.baseline)
        target = select_target(enumerate_devices(), baseline, args.device)
        args.capture.mkdir(parents=True, exist_ok=False)
        journal = Journal(args.capture / "feature-read.jsonl")
        journal.record("session", tool=f"evofox_blaze.feature_read {__version__}",
                       kernel=platform.release(), architecture=platform.machine(),
                       python=platform.python_version(), baseline_sha256=baseline_hash,
                       identity=target.identity(),
                       report_descriptor_hex=target.descriptor.hex(" "),
                       command="python3 -m evofox_blaze.feature_read --read-feature "
                               "--baseline <probe.json> --capture <new-directory>",
                       scope="One GET_FEATURE 07; no SET_REPORT, input reads, or retries")

        def recheck(selected):
            refreshed = select_target(enumerate_devices(), baseline, selected.path)
            if refreshed != selected:
                raise ValueError("Device identity changed before feature request")

        response = get_feature_once(target, journal.record, recheck)
        journal.record("complete", response_hex=response.hex(" "),
                       interpretation="Raw feature response; no configuration fields decoded")
        print(json.dumps({"response_hex": response.hex(" "), "length": len(response),
                          "interpretation": "Raw feature response; not a configuration backup"}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        if journal is not None:
            message = error.strerror if isinstance(error, OSError) else str(error)
            try:
                journal.record("failed", error_type=type(error).__name__,
                               errno=getattr(error, "errno", None), message=message)
            except OSError as log_error:
                print(f"Could not persist failure: {log_error}. Inspect the existing "
                      "journal; an intended request may already have completed. "
                      "No automatic retry.", file=sys.stderr)
        print(f"Feature read failed: {error}", file=sys.stderr)
        return 1
    finally:
        if journal is not None:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
