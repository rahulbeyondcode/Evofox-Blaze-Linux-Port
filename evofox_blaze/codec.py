"""Fixture-only packet encoding. This module contains no transport or I/O."""


def encode_command18(
    *, flags: int, index: int, base: int, data: int, control: int,
    report_length: int,
) -> bytes:
    """Encode the statically recovered eight-byte layout, not a setting API.

    The caller must supply a descriptor-derived length. Only the observed
    eight-byte format is supported; other sizes are refused, not padded.
    Field names do not establish address safety or operation side effects.
    """
    if type(report_length) is not int or report_length != 8:
        raise ValueError("Only the verified eight-byte report layout is supported")
    for name, value, maximum in (
        ("flags", flags, 255), ("index", index, 255), ("base", base, 65535),
        ("data", data, 255), ("control", control, 255),
    ):
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError(f"{name} must be an integer in 0..{maximum}")
    return bytes((7, 0x18, flags, index, base & 255, base >> 8, data, control))
