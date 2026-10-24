"""Preview statically observed vendor reads. No device access or execution."""

import argparse
from dataclasses import dataclass
import json

from .codec import encode_command18


@dataclass(frozen=True)
class ObservedRead:
    base: int
    length: int
    call_sites: tuple[str, ...]


# These are source-code observations, NOT a hardware-safe address whitelist.
OBSERVED_READS = {
    "dpi-state": ObservedRead(0x0018, 8, ("0x44cc46", "0x44e606")),
    "comparison-0": ObservedRead(0x0FA0, 8, ("0x44ca69",)),
    "comparison-1": ObservedRead(0x0FA8, 8, ("0x44ca69",)),
    "comparison-2": ObservedRead(0x0FB0, 8, ("0x44ca69",)),
    "comparison-3": ObservedRead(0x0FB8, 8, ("0x44ca69",)),
}


@dataclass(frozen=True)
class SetFeature:
    report: bytes


@dataclass(frozen=True)
class GetFeature:
    report_id: int
    byte_length: int
    result_byte: int


@dataclass(frozen=True)
class Delay:
    milliseconds: int


def preview_read(name: str, *, report_length: int) -> tuple[SetFeature | GetFeature | Delay, ...]:
    """Reconstruct 0x413ac0/0x413b90 as immutable inspection-only steps.

    No executor is provided. SET_REPORT preparation effects remain unknown.
    Only the five source-observed eight-byte reads can be selected; this is
    not an arbitrary-address memory reader or a model of the entire caller.
    """
    if name not in OBSERVED_READS:
        raise ValueError("Choose a source-observed read, not an arbitrary address")
    observed = OBSERVED_READS[name]
    steps = []

    def frame(flags, index=0, base=observed.base, control=0):
        return SetFeature(encode_command18(
            flags=flags, index=index, base=base, data=0, control=control,
            report_length=report_length,
        ))

    for index in range(observed.length):
        steps.extend((frame(3, index, control=observed.length - 1), Delay(2)))
    steps.extend((Delay(2), frame(0)))
    for index in range(observed.length):
        steps.extend((
            frame(5, index, control=observed.length - 1), Delay(2),
            GetFeature(7, report_length, 1),
        ))
    steps.extend((Delay(2), frame(0, base=0)))
    return tuple(steps)


def decode_dpi_selector(block: bytes) -> int:
    """Extract the application's low-three-bit selector from a base-0018 block.

    This takes eight collected configuration bytes, NOT one GET_FEATURE reply.
    Values 6 and 7 remain visible rather than being clamped to the six UI stages.
    No hardware read, DPI-in-CPI mapping, or device-supported range is implied.
    """
    if not isinstance(block, bytes) or len(block) != 8:
        raise ValueError("Expected the eight bytes collected from base 0018")
    return block[0] & 7


def decode_state_block(block: bytes):
    """Interpret collected base-0018 bytes, never a standalone feature reply.

    Stage, enable-mask, and polling-code positions follow the exact Blaze
    serializer. Frequency names additionally follow the independent A825
    reference's mapping; no physical CPI or polling measurement is implied.
    """
    selector = decode_dpi_selector(block)
    divisor = block[6]
    return {
        "collected_hex": block.hex(" "),
        "dpi_stage_selector_candidate": selector,
        "dpi_cpi": None,
        "dpi_enabled_mask_hex": f"{block[1]:02x}",
        "enabled_stage_indices_candidate": [i for i in range(6) if block[1] & (1 << i)],
        "unassigned_enable_mask_bits_hex": f"{block[1] & 0xC0:02x}",
        "polling_divisor_raw": divisor,
        "usb_speed_index_candidate": {0: 3, 1: 2, 3: 1, 7: 0}.get(divisor),
        "polling_hz_candidate": {0: 1000, 1: 500, 3: 250, 7: 125}.get(divisor),
        "polling_frequency_measured": False,
        "opaque_bytes_hex": {str(i): f"{block[i]:02x}" for i in (2, 3, 4, 5, 7)},
        "complete_configuration_backup": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("region", choices=OBSERVED_READS)
    parser.add_argument("--report-length", type=int, required=True,
                        help="descriptor-derived feature-report length")
    args = parser.parse_args(argv)
    try:
        steps = preview_read(args.region, report_length=args.report_length)
    except ValueError as error:
        parser.error(str(error))
    observed = OBSERVED_READS[args.region]
    rows = []
    for step in steps:
        if isinstance(step, SetFeature):
            rows.append({"operation": "SET_FEATURE", "report_hex": step.report.hex(" ")})
        elif isinstance(step, GetFeature):
            rows.append({"operation": "GET_FEATURE", "report_id": step.report_id,
                         "byte_length": step.byte_length, "copy_response_byte": step.result_byte})
        else:
            rows.append({"operation": "DELAY", "milliseconds": step.milliseconds})
    print(json.dumps({
        "mode": "offline-preview",
        "hardware_validated": False,
        "runtime_observed": False,
        "warning": "Contains SET_REPORT; preparation effects unknown. No executor exists.",
        "scope": "Bulk-read helper only; additional caller operations are not included",
        "region": args.region,
        "base": f"0x{observed.base:04x}",
        "length": observed.length,
        "source_call_sites": observed.call_sites,
        "set_feature_count": sum(isinstance(s, SetFeature) for s in steps),
        "get_feature_count": sum(isinstance(s, GetFeature) for s in steps),
        "explicit_delay_ms": sum(s.milliseconds for s in steps if isinstance(s, Delay)),
        "steps": rows,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
