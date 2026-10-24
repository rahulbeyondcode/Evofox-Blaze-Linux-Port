"""Offline lighting-field experiments, never a device write API."""

import argparse
from dataclasses import dataclass, replace
import json
import sys


@dataclass(frozen=True)
class Command13Frame:
    """An outbound command frame, not a GET reply or original-setting backup.

    The host builder at 0x432030 writes LED_BRIGHT & 7 into byte 5 and clears
    its upper bits. Other bytes are retained as opaque context, not inferred
    from defaults. Representable codes are not verified hardware levels.
    """

    raw: bytes

    def __post_init__(self):
        if not isinstance(self.raw, bytes) or len(self.raw) != 8 or self.raw[:2] != b"\x07\x13":
            raise ValueError("Expected an eight-byte outbound command 07 13, not a GET reply")
        if self.raw[5] & 0xF8:
            raise ValueError("Byte 5 has bits outside the observed command-13 brightness layout")

    @property
    def brightness_code(self) -> int:
        return self.raw[5]

    def with_brightness_code(self, value: int):
        """Return a synthetic frame differing only at byte 5; perform no I/O."""
        if type(value) is not int or not 0 <= value <= 7:
            raise ValueError("Brightness code must be an integer in 0..7; no silent masking")
        return replace(self, raw=self.raw[:5] + bytes((value,)) + self.raw[6:])


def preview_brightness(frame: Command13Frame, code: int):
    """Preview field replacement; never label the supplied frame a backup."""
    modified = frame.with_brightness_code(code)
    return {
        "mode": "offline-command13-brightness-preview",
        "input_command_hex": frame.raw.hex(" "),
        "input_brightness_code": frame.brightness_code,
        "preview_command_hex": modified.raw.hex(" "),
        "preview_brightness_code": modified.brightness_code,
        "changed_byte_offsets": [i for i in range(8) if frame.raw[i] != modified.raw[i]],
        "hardware_validated": False,
        "original_device_value_known": False,
        "safe_to_send": False,
        "limitations": [
            "Static host mapping only; no percent, light-output direction, or persistence established",
            "Caller-supplied outbound bytes are not a device backup or a readback",
            "No lighting readback/restore path established; no transport or write operation exists here",
        ],
    }


def model_storage_brightness(*, code: int, companion: int, mode_enabled: bool):
    """Model cached serializer arithmetic, not a device address/read/write API.

    At 0x41ce61 and 0x424d70, the enabled branch assigns the low byte of
    ((LED_BRIGHT << 4) & 0x70) + companion. The companion is a signed 32-bit
    cached integer; it is NOT masked to a nibble in that code. With the guard
    cleared the serializer writes zero. Inputs are supplied, never acquired.
    """
    if type(code) is not int or not 0 <= code <= 7:
        raise ValueError("Brightness code must be an integer in 0..7; no silent masking")
    if type(companion) is not int or not -(1 << 31) <= companion < (1 << 31):
        raise ValueError("Companion must be a signed 32-bit integer")
    if type(mode_enabled) is not bool:
        raise ValueError("The serializer mode guard must be explicitly True or False")
    value = ((code << 4) + companion) & 255 if mode_enabled else 0
    return {
        "mode": "offline-storage-arithmetic-model",
        "brightness_code": code,
        "companion": companion,
        "serializer_mode_enabled": mode_enabled,
        "serialized_byte_hex": f"{value:02x}",
        "brightness_isolated_in_bits_4_to_6": mode_enabled and 0 <= companion <= 15,
        "candidate_logical_byte": "0x003f",
        "hardware_validated": False,
        "original_device_value_known": False,
        "safe_to_send": False,
        "limitations": [
            "Writer argument arithmetic only; no firmware address or profile-bank layout established",
            "Companion addition may carry into brightness bits; this is not a readback decoder",
            "No read range added, packet generated, or device operation performed",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    context = parser.add_mutually_exclusive_group(required=True)
    context.add_argument("--command13", help="eight outbound command bytes in hex; not a GET reply")
    context.add_argument("--storage-companion", type=int, help="signed cached companion for storage arithmetic only")
    parser.add_argument("--storage-mode", choices=("enabled", "disabled"), help="explicit host serializer guard; not a device state")
    parser.add_argument("--brightness-code", required=True, type=int, help="raw host code 0..7, not a percentage")
    args = parser.parse_args(argv)
    if (args.storage_companion is not None) != (args.storage_mode is not None):
        parser.error("--storage-companion and --storage-mode must be supplied together")
    try:
        if args.command13 is not None:
            result = preview_brightness(Command13Frame(bytes.fromhex(args.command13)), args.brightness_code)
        else:
            result = model_storage_brightness(code=args.brightness_code, companion=args.storage_companion,
                                              mode_enabled=args.storage_mode == "enabled")
    except (ValueError, TypeError) as error:
        print(f"Lighting preview failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
