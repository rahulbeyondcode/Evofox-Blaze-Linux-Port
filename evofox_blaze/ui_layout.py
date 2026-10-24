"""Reference-skin geometry, in the original application's 1024 × 737 pixels.

This module is deliberately independent of GTK and of device access. Reference
values describe the video, not a configuration read from a connected mouse.
"""

from dataclasses import dataclass


WIDTH, HEIGHT = 1024, 737
PAGES = ("buttons", "macros", "performance", "backlight")
PAGE_LABELS = ("Button", "Macro", "Performance", "Backlight")
DEFAULT_SKIN = ".work/ui-skin"


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    def contains(self, x, y):
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height


@dataclass(frozen=True)
class Control:
    name: str
    label: str
    rect: Rect
    action: str = ""
    limitation: str = ""


@dataclass(frozen=True)
class Viewport:
    scale: float
    x: float
    y: float

    @classmethod
    def fit(cls, width, height):
        scale = max(0.001, min(width / WIDTH, height / HEIGHT))
        return cls(scale, (width - WIDTH * scale) / 2, (height - HEIGHT * scale) / 2)

    def to_reference(self, x, y):
        return (x - self.x) / self.scale, (y - self.y) / self.scale

    def place(self, rect):
        left = round(self.x + rect.x * self.scale)
        top = round(self.y + rect.y * self.scale)
        return (left, top,
                max(1, round(self.x + (rect.x + rect.width) * self.scale) - left),
                max(1, round(self.y + (rect.y + rect.height) * self.scale) - top))


TABS = tuple(Control(page, label, Rect(x, 66, 140, 48), "page")
             for page, label, x in zip(PAGES, PAGE_LABELS, (33, 203, 688, 852)))
PROFILES = tuple(Control(f"profile-{i}", label, Rect(x, 620, 67, 70),
                         limitation="Profile switching is not implemented.")
                 for i, (label, x) in enumerate(zip(("Office", "Game I", "Game II", "Media"),
                                                    (24, 117, 208, 300))))
COMMON = TABS + PROFILES + (
    Control("minimize", "Minimize", Rect(940, 7, 32, 28), "minimize"),
    Control("close", "Close", Rect(977, 7, 34, 28), "close"),
    Control("import", "Import", Rect(419, 648, 40, 40), limitation="Profile import is not implemented; use Device controls to open saved evidence."),
    Control("export", "Export", Rect(493, 648, 40, 40), limitation="Full-profile export is not implemented."),
    Control("reset", "Reset", Rect(563, 648, 40, 40), limitation="Factory reset is unavailable. No reset command will be sent."),
    Control("apply", "Apply", Rect(700, 647, 140, 44), "apply"),
    Control("cancel", "Cancel", Rect(852, 647, 140, 44), "cancel"),
)
BUTTON_LABELS = ("Left Click", "Right Click", "Middle Click", "Forward",
                 "Backward", "DPI Loop", "LED Loop", "Rapid Fire")
BUTTON_CONTROLS = tuple(
    Control(f"button-{i + 1}", f"Button {i + 1}: {label}",
            Rect(186 if i < 4 else 657, (234, 309, 383, 458)[i % 4], 181, 40),
            limitation="Button assignment is not implemented. Shown assignment is a reference example, not mouse state.")
    for i, label in enumerate(BUTTON_LABELS)
) + (Control("music", "Music-lighting", Rect(12, 523, 80, 67),
             limitation="Music-reactive lighting is not implemented; no audio is captured."),)
PERFORMANCE_CONTROLS = tuple(
    Control(f"polling-{hz}", f"{hz} Hz", Rect(x, 247, 55, 35), "polling")
    for hz, x in zip((125, 250, 500, 1000), (566, 656, 747, 837))
) + tuple(
    Control(name, label, rect, limitation="This setting is not implemented. The displayed value is a reference example, not a device measurement.")
    for name, label, rect in (
        ("sensitivity", "Mouse Sensitivity", Rect(139, 242, 291, 25)),
        ("scroll", "Scroll Speed", Rect(139, 358, 291, 25)),
        ("double-click", "Double Click Speed", Rect(139, 474, 291, 25)),
        ("dpi-slider", "DPI value", Rect(574, 450, 314, 30)),
    )
) + tuple(
    Control(f"dpi-{i}", f"DPI stage {i + 1}: {dpi}", Rect(x, 360, 32, 83),
            limitation="Physical DPI values and stage enabling are not validated; reference values only.")
    for i, (dpi, x) in enumerate(zip((600, 1200, 2400, 4800, 7200, 12800), (573, 628, 683, 741, 798, 855)))
)
MACRO_CONTROLS = tuple(
    Control(name, label, rect, limitation="Macro editing and recording are not implemented. No keyboard input is captured.")
    for name, label, rect in (
        ("macro-list", "Macro List", Rect(38, 197, 202, 319)),
        ("macro-events", "Key in macro", Rect(280, 197, 202, 319)),
        ("macro-led", "Led parameters in macro", Rect(520, 197, 202, 352)),
        ("record", "Record", Rect(38, 517, 205, 32)),
        ("insert", "Insert Event", Rect(280, 517, 205, 32)),
        ("repeat-release", "Cycle until the key released", Rect(752, 186, 250, 24)),
        ("repeat-toggle", "Cycle until the key clicked again", Rect(752, 226, 250, 24)),
        ("repeat-count", "Specified cycle times", Rect(752, 262, 252, 24)),
    )
)
BACKLIGHT_CONTROLS = tuple(
    Control(name, label, rect, limitation="Lighting writes and original-value readback are not implemented. Reference appearance only.")
    for name, label, rect in (
        ("effect", "Flowing Water Effect", Rect(657, 225, 166, 25)),
        ("brightness", "Brightness", Rect(662, 370, 180, 30)),
        ("speed", "Speed", Rect(662, 399, 180, 30)),
        ("symmetry", "Symmetry", Rect(615, 443, 90, 17)),
        ("clockwise", "Clockwise", Rect(615, 466, 115, 17)),
        ("anticlockwise", "Anti Clockwise", Rect(753, 466, 120, 17)),
        ("two-way", "Two way", Rect(615, 488, 100, 17)),
        ("overwrite", "Overwrite", Rect(753, 488, 110, 17)),
    )
) + tuple(Control(f"color-{i}", f"Lighting color {i + 1}", Rect(x, 286, 23, 60),
                  limitation="Lighting color editing is not implemented.")
          for i, x in enumerate((632, 666, 700, 733, 767, 800, 834)))
PAGE_CONTROLS = dict(zip(PAGES, (BUTTON_CONTROLS, MACRO_CONTROLS,
                               PERFORMANCE_CONTROLS, BACKLIGHT_CONTROLS)))


def controls_for(page):
    return COMMON + PAGE_CONTROLS[page]
