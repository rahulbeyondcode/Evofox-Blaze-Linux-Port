"""Display model for saved evidence. No device enumeration or transport."""

from dataclasses import dataclass
import json
from pathlib import Path

from .config_capture import decode_config_journal
from .evidence import read_evidence_file
from .state_capture import decode_state_journal
from .status import decode_status_journal


@dataclass(frozen=True)
class CapturePresentation:
    rows: tuple[tuple[str, str], ...]
    details: str


def present_capture(path: Path) -> CapturePresentation:
    raw = read_evidence_file(path)
    first = next((json.loads(line) for line in raw.splitlines() if line.strip()), None)
    if not isinstance(first, dict):
        raise ValueError("Expected a saved feature or state journal")
    kind = first.get("event")
    is_state = kind in ("state_session", "config_session")
    if kind == "config_session":
        result = decode_config_journal(raw)
    else:
        result = decode_state_journal(raw) if is_state else decode_status_journal(raw)
    identity = result["identity"]
    if is_state:
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
            ("Lighting readback", "Unavailable"),
            ("Full configuration backup", "Unavailable"),
            ("Device writes", "Polling / scoped restore, with explicit confirmation and block backup"),
            ("Capture SHA-256", result["capture_sha256"]),
        ),
        details=json.dumps(result, indent=2),
    )


@dataclass
class CaptureModel:
    presentation: CapturePresentation | None = None
    error: str = ""

    def load(self, path: Path) -> bool:
        # Never leave the previous capture visible as though a failed load
        # succeeded. Errors are shown as plain text, not GTK markup.
        self.presentation = None
        self.error = ""
        try:
            self.presentation = present_capture(path)
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.error = f"Cannot inspect capture: {error}"
            return False
        return True
