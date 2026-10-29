"""Narrow shortcut allocation/preservation policy for the inspected Blaze layout.

No arbitrary allocator, metadata relocation, profile replay or device access.
Original 0400..0437 records/auxiliary bytes remain untouched. New records use at
most seven disjoint 40-byte tail slots after the inspected 0438 stored endpoint.
Whether firmware follows those new pointers needs an explicitly approved test.
"""

from dataclasses import dataclass
import hashlib
import json

from .buttons import ACTION_CODES, BLOCK_SLOTS, describe_block
from .button_write import assignment_rows, parse_rows
from .shortcuts import Shortcut
from .shortcut_codec import decode_keyboard_record, encode_held_descriptor, encode_held_shortcut
from .shortcut_read import HEADER_BASES


POOL = tuple(0x438 + 40 * i for i in range(7))
ORIGINAL_BASES = tuple(range(0x400, 0x438, 8))
ORIGINAL_DESCRIPTORS = {
    4: bytes.fromhex("00 83 ff b7 00 00 04 00 00 00"),
    5: bytes.fromhex("00 83 ff b7 00 08 04 00 00 00"),
    9: bytes.fromhex("00 82 ff b7 00 10 04 00 00 00"),
}


def shortcut_rows(shortcuts):
    if (not isinstance(shortcuts, dict) or not shortcuts
            or any(type(slot) is not int or slot not in BLOCK_SLOTS or not isinstance(value, Shortcut)
                   for slot, value in shortcuts.items())):
        raise ValueError("Choose mapped native slots 1..6 or 8 and recorded keyboard chords")
    return [{"slot": slot, "key": value.key, "modifiers": list(value.modifiers)}
            for slot, value in sorted(shortcuts.items())]


def parse_shortcuts(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError("Expected recorded shortcuts")
    result = {}
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {"slot", "key", "modifiers"}
                or type(row["slot"]) is not int or row["slot"] not in BLOCK_SLOTS
                or row["slot"] in result or not isinstance(row["modifiers"], list)):
            raise ValueError("Unsupported or duplicate shortcut assignment")
        result[row["slot"]] = Shortcut(row["key"], tuple(row["modifiers"]))
    return result


def normalize_request(assignments, shortcuts):
    native = parse_rows(assignment_rows(assignments)) if assignments else {}
    if not isinstance(assignments, dict):
        raise ValueError("Expected a native-assignment dictionary (possibly empty)")
    chords = parse_shortcuts(shortcut_rows(shortcuts))
    if set(native) & set(chords):
        raise ValueError("One button cannot have both a native action and a shortcut")
    return native, chords


def descriptor_table(blocks):
    return b"".join(blocks[base] for base in HEADER_BASES[4:])


def header_owners(blocks):
    if any(base not in blocks or not isinstance(blocks[base], bytes) or len(blocks[base]) != 8
           for base in HEADER_BASES):
        raise ValueError("Incomplete fresh shortcut metadata")
    if (blocks[0x68][6:8] != b"\x18\x04" or blocks[0x70][:6] != bytes.fromhex("20 04 28 04 30 04")
            or blocks[0x78][:3] != bytes.fromhex("00 38 04")):
        raise ValueError("Unrecognized allocation layout; refusing to relocate or guess existing settings")
    table = descriptor_table(blocks)
    owners = {}
    for index in range(56):
        raw = table[index * 10:index * 10 + 10]
        if not any(raw):
            continue
        group, slot = index // 14, index % 14 + 1
        if group == 0 and raw == ORIGINAL_DESCRIPTORS.get(slot):
            continue
        pointer = raw[5] | ((raw[6] & 0x3f) << 8)
        if (group != 0 or slot not in BLOCK_SLOTS or pointer not in POOL
                or raw[0] != 0 or not 0x81 <= raw[1] <= 0x89
                or raw[2:5] != bytes.fromhex("ff b7 00") or raw[6] & 0xc0 or raw[7:] != bytes(3)
                or pointer in owners.values()):
            raise ValueError("Unknown/shared shortcut descriptor; refusing to overwrite existing records")
        owners[slot] = pointer
    # Slot 9 may contain a live Super+Tab record; never assume it is Rapid Fire.
    if table[80:90] != ORIGINAL_DESCRIPTORS[9]:
        raise ValueError("Unrecognized slot-9 record; preserve it rather than expanding this backend")
    return owners


def allocation(blocks, shortcuts):
    owners = header_owners(blocks)
    selected = {}
    used = set(owners.values())
    for slot in sorted(shortcuts):
        if slot in owners:
            selected[slot] = owners[slot]
        else:
            pointer = next((pointer for pointer in POOL if pointer not in used), None)
            if pointer is None:
                raise ValueError("No unshared scoped shortcut slot available")
            selected[slot] = pointer
            used.add(pointer)
    return owners, selected


def payload_bases(headers, shortcuts):
    owners, selected = allocation(headers, shortcuts)
    pools = set(owners.values()) | set(selected.values())
    return ORIGINAL_BASES + tuple(sorted(base + offset for base in pools for offset in range(0, 40, 8)))


def snapshot_rows(blocks):
    return [{"base": f"0x{base:04x}", "data_hex": data.hex(" "), "sha256": hashlib.sha256(data).hexdigest()}
            for base, data in blocks.items()]


def snapshot_digest(blocks):
    return hashlib.sha256(json.dumps(snapshot_rows(blocks), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def parse_snapshot(rows, shortcuts):
    if not isinstance(rows, list):
        raise ValueError("Expected exact snapshot block rows")
    blocks = {}
    allowed = set(HEADER_BASES) | set(range(0x400, 0x550, 8))
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"base", "data_hex", "sha256"}:
            raise ValueError("Invalid snapshot row")
        base = int(row["base"], 16)
        data = bytes.fromhex(row["data_hex"])
        if (base not in allowed or row["base"] != f"0x{base:04x}" or base in blocks or len(data) != 8
                or hashlib.sha256(data).hexdigest() != row["sha256"]):
            raise ValueError("Snapshot scope/bytes/hash differs")
        blocks[base] = data
    expected = HEADER_BASES + payload_bases(blocks, shortcuts)
    if tuple(blocks) != expected:
        raise ValueError("Snapshot must contain precisely its scoped blocks, in order")
    return blocks


def read_bytes(blocks, base, length):
    if base % 8 or length % 8:
        raise ValueError("Internal shortcut ranges must be eight-byte aligned")
    return b"".join(blocks[base + offset] for offset in range(0, length, 8))


def replace_bytes(blocks, base, data):
    if base % 8 or len(data) % 8 or not data:
        raise ValueError("Internal shortcut ranges must be eight-byte aligned")
    for offset in range(0, len(data), 8):
        if base + offset not in blocks:
            raise ValueError("Cannot write an unbacked-up shortcut byte")
        blocks[base + offset] = data[offset:offset + 8]


@dataclass(frozen=True)
class Fragment:
    kind: str
    base: int
    data: bytes


def _descriptor_fragment(before, after):
    old, new = descriptor_table(before), descriptor_table(after)
    changed = [index for index, (a, b) in enumerate(zip(old, new)) if a != b]
    if not changed:
        return []
    first, end = min(changed) // 8 * 8, (max(changed) // 8 + 1) * 8
    return [Fragment("descriptors", 0xa0 + first, new[first:end])]


def active_shortcuts(blocks):
    table = descriptor_table(blocks)
    result = {}
    for slot in BLOCK_SLOTS:
        if blocks[8][slot - 1] != 0x2e:
            continue
        raw = table[(slot - 1) * 10:slot * 10]
        count = raw[1] & 0x7f
        pointer = raw[5] | ((raw[6] & 0x3f) << 8)
        if raw[:1] != b"\0" or not raw[1] & 0x80 or not 1 <= count <= 9:
            continue
        data = read_bytes(blocks, pointer, ((2 + count * 2 + 7) // 8) * 8)
        result[slot] = decode_keyboard_record(data, count).as_shortcut(allow_press_only=True)
    return result


def plan_change(before, assignments, shortcuts):
    assignments, shortcuts = normalize_request(assignments, shortcuts)
    parse_snapshot(snapshot_rows(before), shortcuts)
    owners, selected = allocation(before, shortcuts)
    # Previously app-owned tail records must still decode as the supported chord
    # shape; unknown records are not silently reclaimed or reinterpreted.
    table = descriptor_table(before)
    for slot, pointer in owners.items():
        count = table[(slot - 1) * 10 + 1] & 0x7f
        decode_keyboard_record(read_bytes(before, pointer, 40), count).as_shortcut(allow_press_only=True)
    existing = active_shortcuts(before)
    after = dict(before)
    native = plan_button_links(before[8], assignments, shortcuts)
    for slot in set(assignments) | set(shortcuts):
        value = before[8][slot - 1]
        if value == 0x2e and slot not in existing:
            raise ValueError("Selected existing shortcut cannot be decoded safely; refusing replacement")
    records = []
    for slot, shortcut in sorted(shortcuts.items()):
        if existing.get(slot) == shortcut:
            continue
        pointer = selected[slot]
        record = encode_held_shortcut(shortcut)
        data = record.encode()
        if read_bytes(before, pointer, len(data)) != data:
            records.append(Fragment("record", pointer, data))
            replace_bytes(after, pointer, data)
        updated = bytearray(descriptor_table(after))
        updated[(slot - 1) * 10:slot * 10] = encode_held_descriptor(pointer, record)
        for index, base in enumerate(HEADER_BASES[4:]):
            after[base] = bytes(updated[index * 8:index * 8 + 8])
    after[8] = native
    fragments = records + _descriptor_fragment(before, after)
    if before[8] != after[8]:
        fragments.append(Fragment("buttons", 8, after[8]))
    return after, tuple(fragments)


def plan_button_links(block, assignments, shortcuts):
    """Validate combined final button links without inventing record/backup bytes."""
    assignments, shortcuts = normalize_request(assignments, shortcuts)
    describe_block(block)
    native = bytearray(block)
    for slot in set(assignments) | set(shortcuts):
        value = block[slot - 1]
        if value & 0xe0 != 0x20 or value & 31 not in (*ACTION_CODES.values(), 14):
            raise ValueError("Selected button is unknown/Fn/repeat state; refusing replacement")
    for slot, action in assignments.items():
        native[slot - 1] = 0x20 | ACTION_CODES[action]
    for slot in shortcuts:
        native[slot - 1] = 0x2e
    if 0x21 not in native[:5]:
        raise ValueError("Keep at least one plain Left Click assignment on a standard button")
    return bytes(native)


def restore_plan(current, before, after, fragments):
    state = dict(before)
    permitted = [dict(state)]
    for fragment in fragments:
        replace_bytes(state, fragment.base, fragment.data)
        permitted.append(dict(state))
    if current not in permitted:
        raise ValueError("Current shortcut state differs from the recorded transaction states; refusing intervening edits")
    if current == before:
        return ()
    restored = []
    # Restore descriptors/links before reclaiming the new tail bytes.
    for kind in ("descriptors", "buttons", "record"):
        for fragment in fragments:
            if fragment.kind != kind:
                continue
            original = read_bytes(before, fragment.base, len(fragment.data))
            if read_bytes(current, fragment.base, len(fragment.data)) != original:
                restored.append(Fragment(kind, fragment.base, original))
    return tuple(restored)


def describe_state(blocks):
    return {**describe_block(blocks[8]), "verified_shortcuts": shortcut_rows(active_shortcuts(blocks))
            if active_shortcuts(blocks) else [], "snapshot_sha256": snapshot_digest(blocks),
            "existing_payload_and_auxiliary_preserved": True}
