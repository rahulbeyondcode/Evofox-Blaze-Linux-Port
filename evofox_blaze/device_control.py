"""Desktop subprocess boundary for explicitly confirmed, narrowly scoped actions."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from uuid import uuid4

from .operation_progress import PHASES, PROGRESS_FD


def run_with_progress(command, cwd, progress):
    """Drain a private phase pipe while preserving final stdout/stderr semantics."""
    read_fd, write_fd = os.pipe()

    def receive():
        with os.fdopen(read_fd, "rb") as source:
            for line in source:
                phase = line.decode("ascii", errors="replace").strip()
                if phase in PHASES:
                    try:
                        progress(phase)
                    except Exception:
                        # UI reporting is not transaction success/failure evidence.
                        pass

    reader = threading.Thread(target=receive, name="blaze-operation-progress", daemon=False)
    try:
        reader.start()
    except Exception:
        os.close(read_fd)
        os.close(write_fd)
        raise
    try:
        return subprocess.run(command, capture_output=True, text=True, cwd=cwd,
                              env={**os.environ, PROGRESS_FD: str(write_fd)}, pass_fds=(write_fd,))
    finally:
        os.close(write_fd)
        reader.join()


DEFAULT_BASELINE = (Path(__file__).resolve().parents[1]
                    / "docs/device-captures/2026-10-23-30fa-1440-0100/probe.json")


@dataclass(frozen=True)
class OperationResult:
    payload: dict
    capture_directory: Path


def state_directory():
    root = Path(os.environ.get("XDG_STATE_HOME", ""))
    if not root.is_absolute():
        root = Path.home() / ".local/state"
    return root / "evofox-blaze"


class DeviceControl:
    """No device interaction until run() is explicitly authorized by the caller."""

    def __init__(self, baseline=DEFAULT_BASELINE, capture_root=None, *, experimental_activation=False):
        if type(experimental_activation) is not bool:
            raise ValueError("Experimental activation opt-in must be boolean")
        self.baseline = baseline
        self.capture_root = capture_root if capture_root is not None else state_directory()
        self.experimental_activation = experimental_activation

    def run(self, action, *, polling=None, restore_from=None, assignments=None, shortcuts=None, confirmed=False,
            progress=None):
        if confirmed is not True:
            raise ValueError("Explicit confirmation is required before starting a device action")
        if progress is not None and not callable(progress):
            raise ValueError("Progress callback must be callable")
        if assignments is not None and action not in ("buttons", "shortcuts"):
            raise ValueError("Native assignments cannot be mixed with another device action")
        if shortcuts is not None and action != "shortcuts":
            raise ValueError("Keyboard shortcuts cannot be mixed with another device action")
        if action == "read":
            if polling is not None or restore_from is not None:
                raise ValueError("Read action cannot contain setting changes")
            arguments = ["evofox_blaze.state_read", "--read-state", "--accept-staged-read-risk"]
        elif action == "polling":
            if type(polling) is not int or polling not in (125, 250, 500, 1000) or restore_from is not None:
                raise ValueError("Select one supported polling setting")
            arguments = ["evofox_blaze.config_write", "--polling", str(polling), "--accept-write-risk"]
        elif action == "restore":
            if not isinstance(restore_from, Path) or polling is not None:
                raise ValueError("Select an original-state.json backup for restore")
            arguments = ["evofox_blaze.config_write", "--restore-backup", str(restore_from), "--accept-write-risk"]
        elif action == "read-buttons":
            if polling is not None or restore_from is not None:
                raise ValueError("Button read cannot contain setting changes")
            arguments = ["evofox_blaze.button_read", "--read-buttons", "--accept-staged-read-risk"]
        elif action == "read-assignments":
            if polling is not None or restore_from is not None:
                raise ValueError("Assignment read cannot contain setting changes")
            arguments = ["evofox_blaze.assignment_read", "--read-assignments", "--accept-staged-read-risk"]
        elif action == "buttons":
            if polling is not None or restore_from is not None:
                raise ValueError("Native buttons cannot be mixed with other settings")
            from .button_write import assignment_rows
            rows = assignment_rows(assignments)
            arguments = ["evofox_blaze.button_write", "--accept-write-risk"]
            for row in rows:
                arguments.extend(("--assign", f"{row['slot']}={row['action']}"))
        elif action == "restore-buttons":
            if not isinstance(restore_from, Path) or polling is not None:
                raise ValueError("Select a button-backup.json for native restore")
            arguments = ["evofox_blaze.button_write", "--restore-backup", str(restore_from), "--accept-write-risk"]
        elif action == "shortcuts":
            if polling is not None or restore_from is not None:
                raise ValueError("Shortcut assignments cannot be mixed with other settings")
            from .shortcut_plan import normalize_request, shortcut_rows
            from .button_write import assignment_rows
            native, chords = normalize_request(assignments, shortcuts)
            arguments = ["evofox_blaze.shortcut_write", "--accept-shortcut-write-risk"]
            for row in shortcut_rows(chords):
                arguments.extend(("--shortcut", json.dumps(row, separators=(",", ":"))))
            for row in assignment_rows(native) if native else []:
                arguments.extend(("--assign", f"{row['slot']}={row['action']}"))
        elif action == "restore-shortcuts":
            if not isinstance(restore_from, Path) or polling is not None:
                raise ValueError("Select a shortcut-backup.json for scoped restore")
            arguments = ["evofox_blaze.shortcut_write", "--restore-backup", str(restore_from),
                         "--accept-shortcut-write-risk"]
        else:
            raise ValueError("Unknown device action")
        if self.experimental_activation is True and action in ("buttons", "shortcuts", "polling"):
            arguments.append("--accept-activation-risk")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        capture = self.capture_root / f"{stamp}-{action}-{uuid4().hex[:8]}"
        command = [sys.executable, "-m", *arguments, "--baseline", str(self.baseline), "--capture", str(capture)]
        # No shell, downloaded executables, retries, udev changes, or recovery.
        # The child owns the descriptor lock and durable hardware journal.
        cwd = Path(__file__).resolve().parents[1]
        result = (subprocess.run(command, capture_output=True, text=True, cwd=cwd) if progress is None else
                  run_with_progress(command, cwd, progress))
        if result.returncode != 0:
            raise RuntimeError(f"{result.stderr.strip() or 'Device operation failed'}. "
                               f"No retry. Inspect evidence in {capture}")
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise ValueError("Backend did not return a structured result; inspect its journal")
        return OperationResult(payload, capture)
