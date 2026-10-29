"""Recover only the latest GUI assignment journal, offline, never stale fallback."""

import os
import json
from pathlib import Path
import re

from .capture_view import CaptureModel


JOURNALS = {"buttons": "button-configuration.jsonl", "restore-buttons": "button-configuration.jsonl",
            "read-buttons": "button-read.jsonl", "shortcuts": "shortcut-configuration.jsonl",
            "restore-shortcuts": "shortcut-configuration.jsonl", "read-assignments": "assignments.jsonl"}
DIRECTORY = re.compile(r"\d{8}T\d{6}\.\d{6}Z-(read-assignments|restore-shortcuts|shortcuts|restore-buttons|read-buttons|buttons)-[0-9a-f]{8}\Z")


def latest_assignments(root):
    """Return a strictly validated saved model and its path, or an error model.

    A later failed/interrupted attempt blocks loading older evidence as current.
    Only bounded, named journal files in real GUI capture directories are read.
    No directory/file is created, and no probe or device operation is called.
    """
    model = CaptureModel()
    selected = None
    try:
        root = Path(root)
        if root.is_symlink():
            raise ValueError("Assignment history must not be a symlink directory")
        try:
            with os.scandir(root) as entries:
                for count, entry in enumerate(entries):
                    if count >= 8192:
                        raise ValueError("Too many history entries; read assignments explicitly")
                    match = DIRECTORY.fullmatch(entry.name)
                    if match and (selected is None or entry.name > selected[0]):
                        if not entry.is_dir(follow_symlinks=False):
                            raise ValueError("Assignment history contains a non-directory/symlink capture")
                        selected = entry.name, match[1]
        except FileNotFoundError:
            return model, None
        if selected is None:
            return model, None
        path = root / selected[0] / JOURNALS[selected[1]]
        if not model.load(path):
            raise ValueError("Latest assignment operation is incomplete or invalid; older values were not loaded. " + model.error)
        data = json.loads(model.presentation.details)
        expected = ("offline-assignment-inspection" if selected[1] == "read-assignments" else
                    "offline-button-inspection" if selected[1] == "read-buttons" else
                    "offline-shortcut-configuration-inspection" if "shortcuts" in selected[1] else
                    "offline-button-configuration-inspection")
        if data.get("mode") != expected or (not selected[1].startswith("read-") and
                data.get("operation") != ("restore" if selected[1].startswith("restore-") else "change")):
            raise ValueError("Latest assignment journal does not match its operation directory; no older fallback")
        return model, path
    except (OSError, ValueError, TypeError) as error:
        model.presentation = None
        model.error = f"Cannot recover saved assignments: {error}. Read mouse assignments to refresh."
        if not model.error_details:
            model.error_details = model.error
        return model, None
