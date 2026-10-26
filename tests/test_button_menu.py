import unittest

from evofox_blaze.button_menu import ASSIGNMENT_MENU
from evofox_blaze.buttons import ACTION_CODES


class AssignmentMenuTests(unittest.TestCase):
    def test_root_order_matches_requested_native_menu(self):
        self.assertEqual([entry.label for entry in ASSIGNMENT_MENU], [
            "Left Click", "Middle Click", "Right Click", "Backward", "Forward", "DPI loop",
            "Extend", "Media", "Macro", "Shortcut", "Profile Selection",
        ])

    def test_cascaded_groups_have_the_requested_order_and_placeholders(self):
        groups = {entry.label: entry.children for entry in ASSIGNMENT_MENU if entry.children}
        self.assertEqual([entry.label for entry in groups["Extend"]],
                         ["Show desktop", "Double Click", "Rapid Fire", "LED Loop", "DPI +", "DPI -"])
        self.assertEqual([entry.label for entry in groups["Media"]], [
            "Browser", "Media Player", "Mail", "Volume Up", "Volume Down", "Previous Track",
            "Next Track", "Mute", "Play/Pause", "Calculator",
        ])
        self.assertEqual([entry.label for entry in groups["Macro"]], ["No macros found"])
        self.assertEqual([entry.label for entry in groups["Profile Selection"]],
                         ["Office", "Game 1", "Game 2", "Media"])
        self.assertTrue(all(entry.action is None for name in ("Media", "Macro", "Profile Selection")
                            for entry in groups[name]))

    def test_actions_are_native_assignments_or_the_local_shortcut_editor(self):
        actions = []
        def walk(entries):
            for entry in entries:
                self.assertFalse(entry.action is not None and entry.children)
                if entry.action is not None:
                    actions.append(entry.action)
                walk(entry.children)
        walk(ASSIGNMENT_MENU)
        self.assertEqual(set(actions), set(ACTION_CODES) | {"shortcut"})
        self.assertEqual(len(actions), len(ACTION_CODES) + 1)
        self.assertIsNone(ASSIGNMENT_MENU[6].children[0].action)  # Show desktop
        self.assertEqual(ASSIGNMENT_MENU[9].action, "shortcut")
        self.assertNotIn("shortcut", ACTION_CODES)  # Never a native writer action.
