"""Desktop subprocess boundary for explicitly confirmed, narrowly scoped actions."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4


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

    def __init__(self, baseline=DEFAULT_BASELINE, capture_root=None):
        self.baseline = baseline
        self.capture_root = capture_root if capture_root is not None else state_directory()

    def run(self, action, *, polling=None, restore_from=None, confirmed=False):
        if confirmed is not True:
            raise ValueError("Explicit confirmation is required before starting a device action")
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
        else:
            raise ValueError("Unknown device action")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        capture = self.capture_root / f"{stamp}-{action}-{uuid4().hex[:8]}"
        command = [sys.executable, "-m", *arguments, "--baseline", str(self.baseline), "--capture", str(capture)]
        # No shell, downloaded executables, retries, udev changes, or recovery.
        # The child owns the descriptor lock and durable hardware journal.
        result = subprocess.run(command, capture_output=True, text=True,
                                cwd=Path(__file__).resolve().parents[1])
        if result.returncode != 0:
            raise RuntimeError(f"{result.stderr.strip() or 'Device operation failed'}. "
                               f"No retry. Inspect evidence in {capture}")
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise ValueError("Backend did not return a structured result; inspect its journal")
        return OperationResult(payload, capture)
