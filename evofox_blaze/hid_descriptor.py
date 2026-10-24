"""Decode HID collections and report sizes without contacting a device."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Collection:
    usage_page: int | None
    usage: int | None
    kind: int
    parent: int | None


@dataclass(frozen=True)
class Report:
    kind: str
    report_id: int
    payload_bits: int
    collection_indices: tuple[int, ...]

    @property
    def byte_length(self) -> int:
        """Wire length, including a report-ID byte only for numbered reports."""
        return (self.payload_bits + 7) // 8 + bool(self.report_id)


@dataclass(frozen=True)
class Descriptor:
    collections: tuple[Collection, ...]
    reports: tuple[Report, ...]


def parse_report_descriptor(data: bytes) -> Descriptor:
    """Parse short HID items; reject malformed or unsupported descriptors.

    Report sizes aggregate all fields, including constant padding. Collections
    are not assumed to correspond one-to-one with Linux hidraw nodes.
    """
    if not data or len(data) > 4096:
        raise ValueError("Expected a nonempty HID descriptor of at most 4096 bytes")
    globals_ = {
        "usage_page": None, "report_size": 0, "report_count": 0, "report_id": 0
    }
    global_stack = []
    collection_stack = []
    collections = []
    usages = []
    fields = {}
    offset = 0
    while offset < len(data):
        prefix = data[offset]
        offset += 1
        if prefix == 0xFE:
            raise ValueError("Long HID items are not supported")
        size = (0, 1, 2, 4)[prefix & 3]
        if offset + size > len(data):
            raise ValueError("Truncated HID item")
        value = int.from_bytes(data[offset : offset + size], "little")
        offset += size
        type_ = (prefix >> 2) & 3
        tag = prefix >> 4
        if type_ == 1:
            key = {
                0: "usage_page", 7: "report_size", 8: "report_id", 9: "report_count"
            }.get(tag)
            if key:
                if tag == 8 and not 1 <= value <= 255:
                    raise ValueError("Invalid HID report ID")
                globals_[key] = value
            elif tag == 10:
                global_stack.append(globals_.copy())
            elif tag == 11:
                if not global_stack:
                    raise ValueError("HID global POP without PUSH")
                globals_ = global_stack.pop()
            elif tag not in (1, 2, 3, 4, 5, 6):
                raise ValueError(f"Unsupported HID global item {tag}")
        elif type_ == 2:
            if tag == 0:
                usages.append(
                    (value >> 16, value & 0xFFFF)
                    if size == 4 else (globals_["usage_page"], value)
                )
            elif tag not in (1, 2, 3, 4, 5, 7, 8, 9):
                raise ValueError(f"Unsupported HID local item {tag}")
        elif type_ == 0:
            if tag == 10:
                page, usage = usages[0] if usages else (globals_["usage_page"], None)
                parent = collection_stack[-1] if collection_stack else None
                collections.append(Collection(page, usage, value, parent))
                collection_stack.append(len(collections) - 1)
            elif tag == 12:
                if not collection_stack:
                    raise ValueError("HID END_COLLECTION without COLLECTION")
                collection_stack.pop()
            elif tag in (8, 9, 11):
                if not collection_stack:
                    raise ValueError("HID report outside a collection")
                bits = globals_["report_size"] * globals_["report_count"]
                if not 0 < bits <= 65536:
                    raise ValueError("Invalid or unsupported HID field size")
                kind = {8: "input", 9: "output", 11: "feature"}[tag]
                key = kind, globals_["report_id"]
                total, owners = fields.setdefault(key, [0, set()])
                if total + bits > 65536:
                    raise ValueError("HID report exceeds supported size")
                fields[key][0] += bits
                owners.add(collection_stack[0])
            else:
                raise ValueError(f"Unsupported HID main item {tag}")
            usages.clear()
        else:
            raise ValueError("Reserved HID item type")
    if collection_stack or global_stack:
        raise ValueError("Unbalanced HID collection or global stack")
    reports = tuple(
        Report(kind, report_id, bits, tuple(sorted(owners)))
        for (kind, report_id), (bits, owners) in sorted(fields.items())
    )
    if any(r.report_id == 0 for r in reports) and any(r.report_id != 0 for r in reports):
        raise ValueError("Mixed numbered and unnumbered HID reports")
    return Descriptor(tuple(collections), reports)
