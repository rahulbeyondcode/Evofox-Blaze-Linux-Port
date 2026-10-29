"""Bounded reads of saved evidence, never input streams or device contents."""

import os
import json
from pathlib import Path
import stat


class EvidenceTooLarge(ValueError):
    pass


def read_evidence_file(path: Path, limit: int = 1024 * 1024) -> bytes:
    if type(limit) is not int or not 1 <= limit <= 1024 * 1024:
        raise ValueError("Evidence read limit must be an integer in 1..1048576")
    return _read_regular_file(path, limit)


def read_shortcut_journal(path: Path) -> bytes:
    """Larger but fixed bound for the fully journaled multi-block transaction."""
    raw = _read_regular_file(path, 8 * 1024 * 1024)
    first = next((json.loads(line) for line in raw.splitlines() if line.strip()), None)
    if not isinstance(first, dict) or first.get("event") != "shortcut_config_session":
        raise ValueError("The larger evidence limit is reserved for scoped shortcut journals")
    return raw


def read_assignment_journal(path: Path) -> bytes:
    raw = _read_regular_file(path, 8 * 1024 * 1024)
    first = next((json.loads(line) for line in raw.splitlines() if line.strip()), None)
    if not isinstance(first, dict) or first.get("event") != "assignment_read_session":
        raise ValueError("The larger assignment evidence limit requires a scoped assignment journal")
    return raw


def _read_regular_file(path: Path, limit: int) -> bytes:
    # Refuse devices, FIFOs and symlinks before opening, and check the actual
    # handle too. NONBLOCK prevents a raced-in FIFO from hanging inspection.
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("Saved evidence must be a regular, non-symlink file")
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("Saved evidence handle is not a regular file")
        with os.fdopen(fd, "rb", closefd=False) as source:
            raw = source.read(limit + 1)
        if len(raw) > limit:
            raise EvidenceTooLarge(f"Saved evidence exceeds the {limit}-byte inspection limit")
        return raw
    finally:
        os.close(fd)
