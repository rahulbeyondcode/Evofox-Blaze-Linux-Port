"""Display model for saved evidence. No device enumeration or transport."""

from dataclasses import dataclass
import json
from pathlib import Path

from .config_capture import decode_config_journal
from .evidence import EvidenceTooLarge, read_evidence_file, read_shortcut_journal, read_assignment_journal
from .state_capture import decode_state_journal
from .status import decode_status_journal
from .button_capture import decode_button_journal
from .button_config_capture import decode_button_config_journal
from .shortcut_config_capture import decode_shortcut_config_journal
from .assignment_read import decode_assignment_journal


@dataclass(frozen=True)
class CapturePresentation:
    rows: tuple[tuple[str, str], ...]
    details: str


def read_capture_bytes(path: Path):
    try:
        return read_evidence_file(path)
    except EvidenceTooLarge:
        try:
            return read_shortcut_journal(path)
        except ValueError:
            return read_assignment_journal(path)


def failure_details(path: Path, validation_error: str):
    """Explain an unsuccessful journal, never turn partial bytes into state."""
    lines = [f"Evidence: {path}", f"Validation: {validation_error}", ""]
    try:
        raw = read_capture_bytes(path)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return "\n".join(lines + [f"Cannot inspect failure details: {error}"])
    failures, commits = [], 0
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            break  # A torn final line is not a completed request/result.
        if not isinstance(event, dict):
            break
        kind = event.get("event", "")
        if kind in ("shortcut_write_intent", "button_write_intent", "config_write_intent", "write_intent"):
            try:
                frame = bytes.fromhex(event.get("frame_hex", ""))
                commits += int(len(frame) == 8 and frame[:3] == b"\x07\x18\x09")
            except (ValueError, TypeError):
                pass
        if isinstance(kind, str) and kind.endswith(("_error", "_failed")):
            failures.append("; ".join(f"{key}={str(event[key])[:2048]}" for key in
                                       ("event", "operation", "phase", "ordinal", "errno", "message") if key in event))
    lines.extend(failures[-8:] or ["The journal ended without a completed result."])
    if commits:
        lines.extend(["", f"Recorded settings-commit requests: {commits}.",
                      "Settings may already have changed, but full verification did not complete.",
                      "Keep the original backup. Do not automatically retry or restore."])
    lines.extend(["", "These are failure diagnostics only. No partial capture is accepted as verified assignments."])
    return "\n".join(lines)


def present_capture(path: Path) -> CapturePresentation:
    raw = read_capture_bytes(path)
    first = next((json.loads(line) for line in raw.splitlines() if line.strip()), None)
    if not isinstance(first, dict):
        raise ValueError("Expected a saved feature or state journal")
    kind = first.get("event")
    is_shortcuts = kind in ("shortcut_config_session", "assignment_read_session")
    is_buttons = is_shortcuts or kind in ("button_session", "button_config_session")
    is_state = kind in ("state_session", "config_session")
    if is_shortcuts:
        result = decode_assignment_journal(raw) if kind == "assignment_read_session" else decode_shortcut_config_journal(raw)
    elif is_buttons:
        result = decode_button_journal(raw) if kind == "button_session" else decode_button_config_journal(raw)
    elif kind == "config_session":
        result = decode_config_journal(raw)
    else:
        result = decode_state_journal(raw) if is_state else decode_status_journal(raw)
    identity = result["identity"]
    if is_buttons:
        fields = (
            ("Captured button block", result["collected_hex"]),
            ("Button assignments", "Stored candidates; physical numbering is vendor-derived"),
            ("Native button activation", "Physical unplug/replug used in the user-tested side-button change"),
            ("Keyboard / macro programming", "Stored chord records decoded; no write or behavior test; no custom macros"
             if kind == "assignment_read_session" else
             "Keyboard chords stored/read back; physical behavior validation pending; no custom macros"
             if is_shortcuts else "Not implemented by this native-only transaction; existing extension records are left untouched"),
            ("Transaction", f"{result['set_feature_count']} SET / {result['get_feature_count']} GET"),
        )
    elif is_state:
        polling = result["polling_hz_candidate"]
        fields = (
            ("Captured state block", result["collected_hex"]),
            ("DPI stage index candidate", f"{result['dpi_stage_selector_candidate']} (CPI not read)"),
            ("Enabled-stage mask", result["dpi_enabled_mask_hex"]),
            ("Polling setting candidate", f"{polling} Hz (not measured)" if polling is not None else "Unassigned code"),
            ("Transaction", f"{result['set_feature_count']} SET / {result['get_feature_count']} GET"),
        )
    else:
        unknown = result["unknown_byte6_bits"]
        fields = (
            ("Captured response", result["raw_response_hex"]),
            ("Profile index candidate", f"{result['profile_index_candidate']} — not hardware-validated"),
            ("Unassigned byte-6 bits", f"{unknown['value']} (mask {unknown['mask']})"),
        )
    return CapturePresentation(
        rows=(
            ("Source", f"{path.name} (saved file, not live)"),
            ("USB identity", f"{identity['vid']}:{identity['pid']}"),
            ("Device revision", identity["bcdDevice"]),
            ("USB interface", identity["interface"]),
            ("Feature report", f"{identity['report_id']:02x} / {identity['report_length']} bytes"),
             *fields,
            *((("Activation candidate", result["activation_outcome"]),
               ("Runtime activation behavior", "Unverified; reports sent are not behavior evidence"))
              if result.get("activation_requested") else ()),
            ("Lighting readback", "Unavailable"),
            ("Full configuration backup", "Unavailable"),
            ("Device writes", "Polling / native buttons / experimental chords / scoped restore, with explicit confirmation and partial backup"),
            ("Capture SHA-256", result["capture_sha256"]),
        ),
        details=json.dumps(result, indent=2),
    )


@dataclass
class CaptureModel:
    presentation: CapturePresentation | None = None
    error: str = ""
    error_details: str = ""

    def load(self, path: Path) -> bool:
        # Never leave the previous capture visible as though a failed load
        # succeeded. Errors are shown as plain text, not GTK markup.
        self.presentation = None
        self.error = ""
        self.error_details = ""
        try:
            self.presentation = present_capture(path)
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.error = f"Cannot inspect capture: {error}"
            self.error_details = failure_details(path, self.error)
            return False
        return True
