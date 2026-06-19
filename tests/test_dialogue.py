from __future__ import annotations

import unittest

from pet.dialogue import BUBBLE_LINES, DialogueAgent, choose_bubble_line


class PickLast:
    def choice(self, values):
        return values[-1]


class Character:
    bubble_lines = {
        "feed": ("角色专属投喂文案一", "角色专属投喂文案二"),
    }


class DialogueTests(unittest.TestCase):
    def test_required_actions_have_chinese_line_pools(self) -> None:
        actions = {
            "feed",
            "play",
            "gift",
            "pet_head",
            "study_together",
            "check_progress",
            "entertainment_timeout",
            "status_view",
        }
        self.assertTrue(actions.issubset(BUBBLE_LINES))
        for action in actions:
            line = choose_bubble_line(action, random=lambda values: values[0])
            self.assertRegex(line, r"[\u4e00-\u9fff]")

    def test_manifest_action_lines_take_priority_and_use_injected_random(self) -> None:
        agent = DialogueAgent(Character(), random=PickLast())
        self.assertEqual(agent.select("feed"), "角色专属投喂文案二")

    def test_raw_manifest_and_action_aliases_are_supported(self) -> None:
        manifest = {"bubbleLines": {"娱乐超时": ["角色提醒：该回来学习啦。"]}}
        self.assertEqual(
            choose_bubble_line("entertainment-overrun", manifest, random=lambda values: values[0]),
            "角色提醒：该回来学习啦。",
        )

    def test_missing_manifest_action_uses_builtin_action_before_manifest_default(self) -> None:
        manifest = {"bubbleLines": {"default": ["角色默认文案"]}}
        line = choose_bubble_line("gift", manifest, random=lambda values: values[0])
        self.assertIn(line, BUBBLE_LINES["gift"])

    def test_unknown_action_uses_safe_manifest_default(self) -> None:
        manifest = {"bubbleLines": {"default": ["角色默认文案"]}}
        self.assertEqual(
            choose_bubble_line("unknown-action", manifest, random=lambda values: values[0]),
            "角色默认文案",
        )

    def test_sensitive_manifest_lines_are_never_returned(self) -> None:
        secret = "apiToken: top-secret-token"
        manifest = {"bubbleLines": {"feed": [secret]}}
        line = choose_bubble_line("feed", manifest, random=lambda values: values[0])
        self.assertNotIn("top-secret-token", line)
        self.assertIn(line, BUBBLE_LINES["feed"])


if __name__ == "__main__":
    unittest.main()
