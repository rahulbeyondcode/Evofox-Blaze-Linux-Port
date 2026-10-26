"""In-memory shortcut drafts and an explicitly armed, window-local recorder.

These symbolic keys are not device bytecode. No input hooks, files or transport
are used here; only the editor forwards its own GTK key events while recording.
"""

from dataclasses import dataclass


MODIFIER_LABELS = {
    "Control_L": "Ctrl", "Control_R": "Right Ctrl",
    "Shift_L": "Shift", "Shift_R": "Right Shift",
    "Alt_L": "Alt", "Alt_R": "Right Alt",
    "Super_L": "Super", "Super_R": "Right Super",
}
KEY_LABELS = {
    "Return": "Enter", "Escape": "Esc", "space": "Space",
    "BackSpace": "Backspace", "Page_Up": "Page Up", "Page_Down": "Page Down",
    "Left": "Left", "Right": "Right", "Up": "Up", "Down": "Down",
    "Tab": "Tab", "Home": "Home", "End": "End", "Insert": "Insert",
    "Delete": "Delete", "Print": "Print Screen", "Pause": "Pause",
    "minus": "-", "equal": "=", "bracketleft": "[", "bracketright": "]",
    "backslash": "\\", "semicolon": ";", "apostrophe": "'", "grave": "`",
    "comma": ",", "period": ".", "slash": "/",
}
KEY_LABELS.update({key: key.upper() for key in "abcdefghijklmnopqrstuvwxyz0123456789"})
KEY_LABELS.update({f"F{i}": f"F{i}" for i in range(1, 25)})

SHORTCUT_DEVICE_NOTICE = (
    "Device shortcuts are experimental. Macros and Button 8 are not implemented."
)


def shortcut_device_notice(experimental_activation=False):
    if not experimental_activation:
        return SHORTCUT_DEVICE_NOTICE
    return SHORTCUT_DEVICE_NOTICE + " Apply may reload all stored settings."


@dataclass(frozen=True)
class Shortcut:
    key: str
    modifiers: tuple = ()

    def __post_init__(self):
        if not isinstance(self.key, str) or self.key not in KEY_LABELS:
            raise ValueError("Choose a letter, number, function, navigation or supported punctuation key")
        if (not isinstance(self.modifiers, tuple)
                or any(not isinstance(key, str) or key not in MODIFIER_LABELS for key in self.modifiers)
                or len(set(self.modifiers)) != len(self.modifiers)):
            raise ValueError("Expected distinct Ctrl, Shift, Alt or Super modifiers")
        object.__setattr__(self, "modifiers", tuple(key for key in MODIFIER_LABELS if key in self.modifiers))

    @property
    def label(self):
        return "+".join([*(MODIFIER_LABELS[key] for key in self.modifiers), KEY_LABELS[self.key]])


class ShortcutRecorder:
    """One chord, completed when all pressed keys are released; never a macro."""

    def __init__(self):
        self.recording = False
        self.shortcut = None
        self.error = ""
        self.held = {}
        self.key = None
        self.modifiers = set()
        self.interrupted_preview = None
        self.interrupted_modifiers = ()

    def start(self):
        self.cancel()
        self.recording = True

    def cancel(self):
        self.recording = False
        self.shortcut = None
        self.error = ""
        self.held.clear()
        self.key = None
        self.modifiers.clear()
        self.interrupted_preview = None
        self.interrupted_modifiers = ()

    def abort(self, reason):
        self.cancel()
        self.error = reason

    def interrupt(self):
        """Stop on focus loss, keeping only keys actually received for review.

        A compositor can intercept the main key and its releases. Never keep
        recording in the background, synthesize a missing key or retain held
        state across focus changes. An observed single chord can still be saved;
        a modifier-only preview needs an explicitly selected main key.
        """
        if not self.recording:
            return
        candidate = Shortcut(self.key, tuple(self.modifiers)) if self.key is not None and not self.error else None
        preview = self.preview
        modifiers = tuple(key for key in MODIFIER_LABELS
                          if key in self.modifiers or key in self.held.values())
        self.cancel()
        self.shortcut = candidate
        if candidate is None:
            self.interrupted_preview = preview
            self.interrupted_modifiers = modifiers
        self.error = ("Recording stopped because this window lost focus. "
                      + ("The received combination is kept; review it before Save." if candidate else
                         "The full combination was not received. Choose the modifiers and key below, or Re-record."))

    def press(self, key, hardware_code):
        if not self.recording or hardware_code in self.held:
            return  # Ignore idle input and key auto-repeat.
        self.held[hardware_code] = key
        if key not in MODIFIER_LABELS and key not in KEY_LABELS:
            self.error = f"Key {key!r} is not supported by this recorder. Re-record using a standard key combination."
        elif key not in MODIFIER_LABELS:
            if self.key is not None:
                self.error = "Record one key combination, not a sequence. Re-record to try again."
            else:
                self.key = key
                self.modifiers.update(value for value in self.held.values() if value in MODIFIER_LABELS)
        elif self.key is not None and self.key in self.held.values():
            self.modifiers.add(key)

    def release(self, hardware_code):
        if not self.recording or hardware_code not in self.held:
            return
        self.held.pop(hardware_code)
        if self.held:
            return
        if self.error:
            self.recording = False
        elif self.key is not None:
            self.shortcut = Shortcut(self.key, tuple(self.modifiers))
            self.recording = False
        # Modifier-only presses do not complete a shortcut. Keep waiting.

    @property
    def preview(self):
        if self.shortcut is not None:
            return self.shortcut.label
        if self.interrupted_preview is not None:
            return self.interrupted_preview
        if self.key is not None:
            return Shortcut(self.key, tuple(self.modifiers)).label
        modifiers = [MODIFIER_LABELS[key] for key in MODIFIER_LABELS if key in self.held.values()]
        return "+".join(modifiers + ["…"]) if modifiers else "Press a key combination…"
