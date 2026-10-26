"""Offline native button-table model. No device access or keyboard/macro bytecode."""

import argparse
import json


# Exact vendor FUN_STRING -> cached action -> serializer low-five-bit mapping.
# Back/Forward was user-tested after replug; remaining actions are host-code
# candidates until separately exercised with this physical mouse.
ACTION_CODES = {
    "left": 1, "middle": 2, "right": 3, "back": 4, "forward": 5,
    "dpi-cycle": 6, "double-click": 8, "rapid-fire": 9,
    "dpi-up": 11, "dpi-down": 12, "lighting-cycle": 21,
}
ACTION_LABELS = {
    "left": "Left Click", "middle": "Middle Click", "right": "Right Click",
    "back": "Backward", "forward": "Forward", "dpi-cycle": "DPI Loop",
    "double-click": "Double Click", "rapid-fire": "Rapid Fire",
    "dpi-up": "DPI +", "dpi-down": "DPI -", "lighting-cycle": "LED Loop",
}
# config.ini K1_MAP..K8_MAP. Slot 9 is outside the first button block.
# Indexes are vendor UI indexes, NOT physical-button event observations.
UI_SLOTS = (1, 3, 2, 5, 4, 8, 6, 9)
BLOCK_SLOTS = (1, 2, 3, 4, 5, 6, 8)
# Source serializer sends extension codes 0d/0e/0f/1e/1f to per-slot records.
# Only 0e is observed on this Blaze so far. We may replace its LINK with a
# built-in assignment while leaving all extension data untouched. Restore must
# copy the exact original link from a validated backup, never synthesize it.
OPAQUE_EXTENSION_CODE = 14


def validate_block(block):
    if not isinstance(block, bytes) or len(block) != 8:
        raise ValueError("Expected eight collected bytes from button block 0008, not a feature reply")


def describe_block(block):
    validate_block(block)
    reverse = {code: name for name, code in ACTION_CODES.items()}
    return {
        "base": "0x0008", "length": 8, "collected_hex": block.hex(" "),
        "button_slots": [
            {"slot": i + 1, "raw_hex": f"{value:02x}", "flags_hex": f"{value & 0xe0:02x}",
             "action_code": value & 31,
             "action_candidate": reverse.get(value & 31) if value & 0xe0 == 0x20 else None,
             "vendor_ui_button": UI_SLOTS.index(i + 1) + 1 if i + 1 in UI_SLOTS else None}
            for i, value in enumerate(block)
        ],
        "physical_button_attribution_verified": False, "behavior_verified": False,
        "complete_configuration_backup": False,
    }


def plan_button_change(block, slot, action):
    """Replace one ordinary native assignment, preserving seven bytes and flags.

    Reject unknown/Fn/repeat assignments, unknown selected slots and a table without a
    plain left-click assignment on the five standard switch slots. Never invent
    defaults, profile banks, activation commands or extension-table records.
    """
    validate_block(block)
    if type(slot) is not int or slot not in BLOCK_SLOTS:
        raise ValueError("Choose a mapped slot in 1..6 or 8; slot 9 and spare slot 7 are not supported")
    return plan_assignments(block, {slot: action})


def plan_assignments(block, assignments):
    """Plan one fixed-block commit for one or more distinct mapped slots."""
    validate_block(block)
    if not isinstance(assignments, dict) or not assignments:
        raise ValueError("At least one explicit slot/action assignment is required")
    # Validate every selected original byte before building anything. Left-click
    # retention is checked on the final table, permitting a single-commit swap.
    changed = bytearray(block)
    for slot, action in assignments.items():
        if type(slot) is not int or slot not in BLOCK_SLOTS:
            raise ValueError("Unsupported button slot")
        if not isinstance(action, str) or action not in ACTION_CODES:
            raise ValueError("Unsupported native button action")
        original = block[slot - 1]
        if original & 0xe0 != 0x20 or original & 31 not in (*ACTION_CODES.values(), OPAQUE_EXTENSION_CODE):
            raise ValueError("Selected slot is unknown/Fn/repeat state; refusing to overwrite it")
        changed[slot - 1] = (original & 0xe0) | ACTION_CODES[action]
    if 0x21 not in changed[:5]:
        raise ValueError("Keep at least one plain Left Click assignment on a standard button")
    return bytes(changed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--block", required=True, help="eight collected button-table bytes; synthetic inputs allowed")
    parser.add_argument("--slot", type=int, choices=BLOCK_SLOTS)
    parser.add_argument("--action", choices=ACTION_CODES)
    args = parser.parse_args(argv)
    try:
        data = bytes.fromhex(args.block)
        result = describe_block(data)
        if (args.slot is None) != (args.action is None):
            raise ValueError("Use --slot and --action together")
        if args.slot is not None:
            result["planned_hex"] = plan_button_change(data, args.slot, args.action).hex(" ")
        result["mode"] = "offline-button-model"
        result["hardware_approved"] = False
    except ValueError as error:
        parser.exit(1, f"Button model failed: {error}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
