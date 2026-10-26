"""Explicitly armed, one-key-at-a-time shortcut boxes. No input transport."""

from .shortcuts import KEY_LABELS, MODIFIER_LABELS, Shortcut


class ShortcutBoxes:
    limit = 6

    def __init__(self, initial=None):
        keys = [*initial.modifiers, initial.key] if initial else []
        self.values = keys if keys and len(keys) <= self.limit else [None] * 3
        self.active = None
        self.held = None
        self.error = ("The stored chord exceeds six keys. Re-record to replace it; the existing assignment is unchanged."
                      if len(keys) > self.limit else "")

    @property
    def recording(self):
        return self.active is not None

    @property
    def shortcut(self):
        if not all(self.values) or len(set(self.values)) != len(self.values):
            return None
        main = [key for key in self.values if key in KEY_LABELS]
        if len(main) != 1:
            return None
        return Shortcut(main[0], tuple(key for key in self.values if key in MODIFIER_LABELS))

    @property
    def preview(self):
        return "+".join(MODIFIER_LABELS.get(key, KEY_LABELS.get(key, "…")) for key in self.values)

    @property
    def validation(self):
        if not all(self.values):
            return "Fill every box, or delete unused boxes with ×."
        if len(set(self.values)) != len(self.values):
            return "Each key must be different. Change or delete the duplicate box."
        if self.shortcut is None:
            return "Use modifiers and exactly one regular key. Multiple regular keys are a macro, not a shortcut."
        return "Shortcut ready. Save stages it in the app; Apply programs the mouse."

    def start(self, index=None):
        if index is None:
            index = next((i for i, value in enumerate(self.values) if value is None), 0)
        if type(index) is not int or not 0 <= index < len(self.values):
            raise ValueError("Choose an existing key box")
        self.stop()
        self.error = ""
        self.active = index

    def stop(self, reason=""):
        self.active = None
        self.held = None
        self.error = reason

    def reset(self):
        self.stop()
        self.values = [None] * len(self.values)

    def add(self):
        if len(self.values) >= self.limit:
            raise ValueError("At most six key boxes are supported")
        self.stop()
        self.values.append(None)

    def delete(self, index):
        if type(index) is not int or not 0 <= index < len(self.values) or len(self.values) == 1:
            raise ValueError("Keep at least one key box")
        self.stop()
        del self.values[index]

    def press(self, key, code):
        if not self.recording:
            return
        if self.held is not None:
            if self.held[1] != code:
                self.stop("Press and release one key at a time. Do not hold Ctrl or Alt while entering the next box.")
            return
        if key not in MODIFIER_LABELS and key not in KEY_LABELS:
            self.stop(f"Key {key!r} is not supported. Click the box and try a standard key.")
            return
        self.held = (key, code)

    def release(self, code):
        if not self.recording or self.held is None or self.held[1] != code:
            return
        self._fill_active(self.held[0])

    def _fill_active(self, key):
        index = self.active
        self.values[index] = key
        self.held = None
        self.active = next((i for i in [*range(index + 1, len(self.values)), *range(index)]
                            if self.values[i] is None), None)

    def insert_super(self):
        """Explicit left Windows/Super choice, never inferred from lost events.

        Fill the armed box or first empty box. Continue only an already armed
        recording; an idle/focus-stopped editor stays idle. Never overwrite a
        full chord without an explicitly selected box or accept a held key.
        """
        if self.held is not None:
            self.stop("Release all keys, then click Windows / Super again.")
            return False
        if self.recording:
            self._fill_active("Super_L")
        else:
            index = next((i for i, value in enumerate(self.values) if value is None), None)
            if index is None:
                self.error = "Click a key box first to replace it with Windows / Super."
                return False
            self.values[index] = "Super_L"
        self.error = ""
        return True
