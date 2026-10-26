"""Source-derived keyboard-only shortcut codec. No device transport/allocation.

The exact application's US-layout VK converter, descriptor serializer and
keyboard-event branch supply these encodings. Mixed mouse/media/macro streams
are deliberately not generated or treated as ordinary keyboard records.
"""

from dataclasses import dataclass

from .shortcuts import Shortcut


KEY_USAGES = {key: index + 4 for index, key in enumerate("abcdefghijklmnopqrstuvwxyz")}
KEY_USAGES.update({key: index + 0x1e for index, key in enumerate("1234567890")})
KEY_USAGES.update({f"F{i}": i + 0x39 for i in range(1, 13)})
KEY_USAGES.update({f"F{i}": i + 0x5b for i in range(13, 25)})
KEY_USAGES.update({
    "Return": 0x28, "Escape": 0x29, "BackSpace": 0x2a, "Tab": 0x2b, "space": 0x2c,
    "minus": 0x2d, "equal": 0x2e, "bracketleft": 0x2f, "bracketright": 0x30,
    "backslash": 0x31, "semicolon": 0x33, "apostrophe": 0x34, "grave": 0x35,
    "comma": 0x36, "period": 0x37, "slash": 0x38,
    "Print": 0x46, "Pause": 0x48, "Insert": 0x49, "Home": 0x4a, "Page_Up": 0x4b,
    "Delete": 0x4c, "End": 0x4d, "Page_Down": 0x4e, "Right": 0x4f, "Left": 0x50,
    "Down": 0x51, "Up": 0x52,
})
MODIFIER_USAGES = {"Control_L": 0xe0, "Shift_L": 0xe1, "Alt_L": 0xe2, "Super_L": 0xe3,
                   "Control_R": 0xe4, "Shift_R": 0xe5, "Alt_R": 0xe6, "Super_R": 0xe7}
USAGE_KEYS = {usage: key for key, usage in KEY_USAGES.items()}
USAGE_MODIFIERS = {usage: key for key, usage in MODIFIER_USAGES.items()}


@dataclass(frozen=True)
class KeyboardEvent:
    usage: int
    pressed: bool
    ticks: int

    def __post_init__(self):
        if (type(self.usage) is not int or self.usage not in (*USAGE_KEYS, *USAGE_MODIFIERS)
                or type(self.pressed) is not bool or type(self.ticks) is not int or not 1 <= self.ticks <= 127):
            raise ValueError("Expected a supported keyboard event and a 1..127 tick delay")

    def encode(self):
        return bytes((self.ticks | (0x80 if self.pressed else 0), self.usage))


@dataclass(frozen=True)
class KeyboardRecord:
    events: tuple
    repeat_count: int = 1

    def __post_init__(self):
        if (type(self.repeat_count) is not int or not 1 <= self.repeat_count <= 65535
                or not isinstance(self.events, tuple) or not self.events
                or any(not isinstance(event, KeyboardEvent) for event in self.events)):
            raise ValueError("Expected keyboard events and a nonzero 16-bit repeat count")

    def encode(self, *, padded=True):
        data = self.repeat_count.to_bytes(2, "little") + b"".join(event.encode() for event in self.events)
        return data + bytes((-len(data)) % 8) if padded else data

    def as_shortcut(self, *, allow_press_only=False):
        if self.repeat_count != 1:
            raise ValueError("Repeated sequences are not a single shortcut")
        presses, releases = [], []
        for event in self.events:
            if event.pressed:
                if releases or event.usage in presses:
                    raise ValueError("Multiple chords/repeated presses are not a single shortcut")
                presses.append(event.usage)
            else:
                releases.append(event.usage)
        if releases != list(reversed(presses)) and not (allow_press_only and not releases):
            raise ValueError("Shortcut release order is not balanced")
        mains = [usage for usage in presses if usage in USAGE_KEYS]
        if len(mains) != 1 or presses[-1] != mains[0]:
            raise ValueError("Expected modifiers followed by exactly one main key")
        return Shortcut(USAGE_KEYS[mains[0]], tuple(USAGE_MODIFIERS[usage] for usage in presses[:-1]))


def encode_shortcut(shortcut, *, ticks=10):
    if not isinstance(shortcut, Shortcut):
        raise ValueError("Expected a recorded symbolic shortcut")
    usages = tuple(MODIFIER_USAGES[key] for key in shortcut.modifiers) + (KEY_USAGES[shortcut.key],)
    events = tuple(KeyboardEvent(usage, True, ticks) for usage in usages)
    events += tuple(KeyboardEvent(usage, False, ticks) for usage in reversed(usages))
    return KeyboardRecord(events)


def encode_held_shortcut(shortcut):
    """Match the captured Blaze's press-only, mouse-release-managed chords."""
    balanced = encode_shortcut(shortcut, ticks=4)
    return KeyboardRecord(balanced.events[:len(balanced.events) // 2])


def encode_held_descriptor(pointer, record):
    if (type(pointer) is not int or pointer % 8 or not 0x400 <= pointer
            or pointer + len(record.encode()) > 0xf20):
        raise ValueError("Invalid bounded keyboard record pointer")
    record.as_shortcut(allow_press_only=True)
    if any(not event.pressed for event in record.events):
        raise ValueError("Held-key descriptor requires press-only events")
    count = len(record.events)
    return bytes((0, 0x80 | count, 0xff, 0xb7, 0, pointer & 255, pointer >> 8, 0, 0, 0))


def decode_keyboard_record(data, event_count):
    if (not isinstance(data, bytes) or type(event_count) is not int or not 1 <= event_count <= 8191
            or len(data) < 2 + 2 * event_count):
        raise ValueError("Incomplete keyboard record; no padding or inferred events")
    events = tuple(KeyboardEvent(data[i + 1], bool(data[i] & 0x80), data[i] & 0x7f)
                   for i in range(2, 2 + 2 * event_count, 2))
    return KeyboardRecord(events, int.from_bytes(data[:2], "little"))


def encode_descriptor(pointer, record, *, tick_milliseconds=1):
    """Single-shot custom-function 0x21 descriptor, not a native button byte.

    ff/b700 are the exact helper outputs for this cached custom-function value,
    also present in all three captured Blaze descriptors. Flags remain zero for
    one-shot playback. No allocation/end pointer is inferred by this function.
    """
    if (type(pointer) is not int or not 0x400 <= pointer <= 0xf18 or pointer % 8
            or not isinstance(record, KeyboardRecord) or len(record.events) > 8191
            or type(tick_milliseconds) is not int or not 1 <= tick_milliseconds <= 256):
        raise ValueError("Invalid aligned record pointer, event count or tick unit")
    record.as_shortcut()  # Only balanced, single-shot keyboard chords are emitted.
    if pointer + len(record.encode()) > 0xf20:
        raise ValueError("Record exceeds the source writer's bounded payload range")
    count = len(record.events)
    return bytes((tick_milliseconds - 1, count & 0x7f, 0xff, 0xb7, 0,
                  pointer & 255, pointer >> 8, count >> 7, 0, 0))
