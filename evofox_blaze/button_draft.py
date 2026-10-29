"""Offline desktop draft state, separate from device programming and consent."""

import json

from .buttons import ACTION_CODES, ACTION_LABELS, BLOCK_SLOTS, UI_SLOTS, describe_block, plan_assignments
from .shortcuts import Shortcut


UNREAD_LABELS = ("Not read",) * 7 + ("Not read (slot 9)",)


class ButtonDraft:
    def __init__(self):
        self.signature = None
        self.block = None
        self.pending = {}
        self.shortcuts = {}
        self.baseline_shortcuts = {}
        self.baseline_labels = UNREAD_LABELS
        self.baseline_actions = (None,) * 8

    def sync(self, details):
        if details == self.signature:
            return
        self.signature = details
        self.block = None
        self.pending.clear()
        self.shortcuts.clear()
        self.baseline_shortcuts.clear()
        self.baseline_labels = UNREAD_LABELS
        self.baseline_actions = (None,) * 8
        if details:
            data = json.loads(details)
            if data.get("mode") in ("offline-button-inspection", "offline-button-configuration-inspection",
                                     "offline-shortcut-configuration-inspection", "offline-assignment-inspection"):
                block = bytes.fromhex(data["collected_hex"])
                describe_block(block)
                self.block = block
                if data.get("mode") in ("offline-shortcut-configuration-inspection", "offline-assignment-inspection") and data.get("verified_shortcuts"):
                    from .shortcut_plan import parse_shortcuts
                    self.baseline_shortcuts = parse_shortcuts(data["verified_shortcuts"])
                actions, labels = [], []
                for slot in UI_SLOTS:
                    if slot > 8:
                        actions.append(None)
                        labels.append("Not read (slot 9)")
                        continue
                    value = block[slot - 1]
                    if slot in self.baseline_shortcuts:
                        actions.append(None)
                        labels.append(self.baseline_shortcuts[slot].label)
                        continue
                    action = next((name for name, code in ACTION_CODES.items() if value == (0x20 | code)), None)
                    actions.append(action)
                    labels.append(ACTION_LABELS[action] if action else
                                  "Stored shortcut" if value == 0x2e else f"Unknown ({value:02x})")
                self.baseline_actions = tuple(actions)
                self.baseline_labels = tuple(labels)

    def invalidate_evidence(self):
        """Drop raw captured state after a failure, but retain the UI baseline.

        The last shown assignments still define whether the user's selection
        changed. They are not a device backup or current hardware state.
        """
        self.signature = None
        self.block = None

    def editable(self, ui_button):
        if type(ui_button) is not int or not 1 <= ui_button <= 8:
            return False
        slot = UI_SLOTS[ui_button - 1]
        return (slot in BLOCK_SLOTS and (self.block is None
                or (self.block[slot - 1] & 0xe0 == 0x20
                    and self.block[slot - 1] & 31 in (*ACTION_CODES.values(), 14))))

    def assign(self, ui_button, action):
        if not self.editable(ui_button) or not isinstance(action, str) or action not in ACTION_CODES:
            raise ValueError("Choose a supported native button slot and built-in action")
        slot = UI_SLOTS[ui_button - 1]
        self.shortcuts.pop(slot, None)
        if self.baseline_actions[ui_button - 1] == action:
            self.pending.pop(slot, None)
        else:
            self.pending[slot] = action

    def assign_shortcut(self, ui_button, shortcut):
        if not self.editable(ui_button) or not isinstance(shortcut, Shortcut):
            raise ValueError("Choose a supported button and a recorded shortcut")
        slot = UI_SLOTS[ui_button - 1]
        self.pending.pop(slot, None)
        if self.baseline_shortcuts.get(slot) == shortcut:
            self.shortcuts.pop(slot, None)
        else:
            self.shortcuts[slot] = shortcut

    def shortcut(self, ui_button):
        if type(ui_button) is not int or not 1 <= ui_button <= 8:
            return None
        slot = UI_SLOTS[ui_button - 1]
        if slot in self.pending:
            return None
        return self.shortcuts.get(slot, self.baseline_shortcuts.get(slot))

    @property
    def has_changes(self):
        return bool(self.pending or self.shortcuts)

    @property
    def can_apply(self):
        if not self.has_changes:
            return False
        # Without saved evidence, do not invent an original table from UI
        # placeholders. Apply's backend validates a fresh real read before
        # any setting data, including the mandatory retained Left Click.
        if self.block is None:
            return True
        try:
            if self.shortcuts:
                from .shortcut_plan import plan_button_links
                plan_button_links(self.block, self.pending, self.shortcuts)
                return True  # The chord can differ even when its 2e link does not.
            return plan_assignments(self.block, self.pending) != self.block
        except ValueError:
            return False

    def labels(self):
        labels = []
        for index, slot in enumerate(UI_SLOTS):
            if slot in self.shortcuts:
                labels.append(self.shortcuts[slot].label + " *")
            elif slot in self.pending:
                labels.append(ACTION_LABELS[self.pending[slot]] + " *")
            else:
                labels.append(self.baseline_labels[index])
        return tuple(labels)

    def cancel(self):
        self.pending.clear()
        self.shortcuts.clear()
