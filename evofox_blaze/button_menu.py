"""Offline assignment-menu structure; placeholders never become device actions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MenuEntry:
    label: str
    action: str | None = None
    children: tuple = ()


ASSIGNMENT_MENU = (
    MenuEntry("Left Click", "left"),
    MenuEntry("Middle Click", "middle"),
    MenuEntry("Right Click", "right"),
    MenuEntry("Backward", "back"),
    MenuEntry("Forward", "forward"),
    MenuEntry("DPI loop", "dpi-cycle"),
    MenuEntry("Extend", children=(
        MenuEntry("Show desktop"),
        MenuEntry("Double Click", "double-click"),
        MenuEntry("Rapid Fire", "rapid-fire"),
        MenuEntry("LED Loop", "lighting-cycle"),
        MenuEntry("DPI +", "dpi-up"),
        MenuEntry("DPI -", "dpi-down"),
    )),
    MenuEntry("Media", children=tuple(MenuEntry(label) for label in (
        "Browser", "Media Player", "Mail", "Volume Up", "Volume Down",
        "Previous Track", "Next Track", "Mute", "Play/Pause", "Calculator",
    ))),
    MenuEntry("Macro", children=(MenuEntry("No macros found"),)),
    MenuEntry("Shortcut", "shortcut"),
    MenuEntry("Profile Selection", children=tuple(MenuEntry(label) for label in (
        "Office", "Game 1", "Game 2", "Media",
    ))),
)
