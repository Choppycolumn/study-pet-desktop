from __future__ import annotations

import unittest

from pet.action_library import (
    ACTION_CATEGORIES,
    ACTION_FALLBACKS,
    ALL_ACTIONS,
    ALL_STANDARD_ACTIONS,
    actions_for_category,
    get_action_category,
    resolve_action,
)
from pet.behavior import PetBehaviorScheduler


EXPECTED_CATEGORIES = {
    "idle": (
        "idle_normal", "idle_blink", "idle_breathe", "idle_look_left",
        "idle_look_right", "idle_stretch", "idle_sit", "idle_lie",
        "idle_bored", "idle_random_01", "idle_random_02", "idle_random_03",
    ),
    "study": (
        "study_normal", "study_focus", "study_reading", "study_typing",
        "study_writing", "study_thinking", "study_encourage", "study_complete",
        "ask_study", "study_together", "check_progress", "praise_study",
    ),
    "discipline": (
        "warning_soft", "warning_medium", "warning_strong", "angry_soft",
        "angry_strong", "disappointed", "stare", "block_screen",
        "force_study", "forgive",
    ),
    "emotion": (
        "happy", "excited", "proud", "shy", "sad", "wronged", "angry",
        "surprised", "confused", "tired", "sleepy", "calm",
    ),
    "interaction": (
        "click", "double_click", "pet_head", "drag_start", "dragging",
        "drag_end", "greet", "wave", "nod", "shake_head", "poke", "hide",
        "return_back",
    ),
    "routine": (
        "wake_up", "sleep", "nap", "good_morning", "good_afternoon",
        "good_evening", "late_night_warning", "break_time", "back_to_work",
    ),
    "system": (
        "syncing", "sync_success", "sync_error", "network_error",
        "config_error", "loading", "update_available", "achievement",
    ),
    "easter_egg": (
        "dance", "cheer", "celebrate", "roll", "hide_and_peek", "special_01",
        "special_02", "special_03",
    ),
    "care": (
        "feed", "eating", "full", "hungry", "play", "playing", "gift", "love",
        "pet_head", "shy", "spoiled", "lonely", "want_attention",
    ),
    "menu": ("menu_open", "menu_hover", "menu_select", "settings_open"),
}


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FirstRandom:
    @staticmethod
    def choice(values):
        return values[0]

    @staticmethod
    def uniform(low, _high):
        return low


class ActionLibraryTests(unittest.TestCase):
    def test_categories_match_the_complete_protocol(self) -> None:
        self.assertIsInstance(ACTION_CATEGORIES, dict)
        self.assertEqual(ACTION_CATEGORIES, EXPECTED_CATEGORIES)
        expected_all = tuple(dict.fromkeys(a for values in EXPECTED_CATEGORIES.values() for a in values))
        self.assertEqual(ALL_ACTIONS, expected_all)
        self.assertIs(ALL_STANDARD_ACTIONS, ALL_ACTIONS)

    def test_category_queries_include_extensions(self) -> None:
        self.assertEqual(actions_for_category("menu"), EXPECTED_CATEGORIES["menu"])
        self.assertEqual(get_action_category("idle-look-left"), "idle")
        self.assertEqual(get_action_category("ask_study"), "study")
        self.assertEqual(get_action_category("pet_head"), "care")
        self.assertIsNone(get_action_category("not_an_action"))

    def test_mature_protocol_fallback_chains_are_exact(self) -> None:
        expected = {
            "idle_blink": ("idle_normal",),
            "idle_random_01": ("idle_normal",),
            "study_typing": ("study_normal", "idle_normal"),
            "study_complete": ("happy", "idle_normal"),
            "warning_strong": ("warning_medium", "warning_soft", "idle_normal"),
            "angry_strong": ("angry_soft", "warning_strong", "idle_normal"),
            "disappointed": ("sad", "warning_soft", "idle_normal"),
            "pet_head": ("shy", "happy", "click", "idle_normal"),
            "dragging": ("drag_start", "idle_normal"),
            "sleep": ("idle_lie", "idle_normal"),
            "sync_error": ("warning_soft", "idle_normal"),
            "celebrate": ("happy", "idle_normal"),
        }
        for action, chain in expected.items():
            with self.subTest(action=action):
                self.assertEqual(ACTION_FALLBACKS[action], chain)

    def test_care_and_menu_fallback_chains_are_exact(self) -> None:
        expected = {
            "feed": ("happy", "idle_normal"),
            "eating": ("feed", "idle_normal"),
            "gift": ("happy", "idle_normal"),
            "play": ("excited", "happy", "idle_normal"),
            "pet_head": ("shy", "happy", "click", "idle_normal"),
            "hungry": ("sad", "idle_normal"),
            "want_attention": ("idle_bored", "idle_normal"),
            "menu_open": ("click", "idle_normal"),
        }
        for action, chain in expected.items():
            with self.subTest(action=action):
                self.assertEqual(ACTION_FALLBACKS[action], chain)

    def test_resolution_reports_requested_actual_and_attempted_chain(self) -> None:
        direct = resolve_action({"idle_normal", "study_focus"}, "study-focus")
        fallback = resolve_action({"idle_normal", "warning_soft"}, "warning_strong")
        care = resolve_action({"idle_normal", "shy"}, "pet_head")
        self.assertEqual(direct.actual, "study_focus")
        self.assertEqual(direct.fallback_chain, ("study_focus",))
        self.assertEqual(fallback.actual, "warning_soft")
        self.assertEqual(
            fallback.fallback_chain,
            ("warning_strong", "warning_medium", "warning_soft"),
        )
        self.assertEqual(care.fallback_chain, ("pet_head", "shy"))
        self.assertEqual(care["actual"], "shy")

    def test_unknown_and_alias_resolve_to_idle_normal(self) -> None:
        unknown = resolve_action({"idle_normal"}, "future_action")
        alias = resolve_action({"idle_normal"}, "idle")
        self.assertEqual(unknown.actual, "idle_normal")
        self.assertEqual(unknown.fallback_chain, ("future_action", "idle_normal"))
        self.assertEqual(alias.fallback_chain, ("idle", "idle_normal"))

    def test_mature_actions_can_target_legacy_character_states(self) -> None:
        available = {"idle", "study", "warning", "angry", "drag", "error"}
        self.assertEqual(resolve_action(available, "idle_normal").actual, "idle")
        self.assertEqual(resolve_action(available, "study_typing").actual, "study")
        self.assertEqual(resolve_action(available, "warning_strong").actual, "warning")
        self.assertEqual(resolve_action(available, "dragging").actual, "drag")
        self.assertEqual(resolve_action(available, "sync_error").actual, "error")


class BehaviorSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.available = {
            "idle_normal", "idle_blink", "idle_breathe", "study_normal", "study_focus",
            "study_complete", "warning_soft", "warning_medium", "warning_strong",
            "angry_soft", "angry_strong", "disappointed", "drag_start", "dragging",
            "drag_end", "sleep", "nap", "syncing", "sync_success", "sync_error",
            "happy", "shy", "click", "feed",
        }
        self.scheduler = PetBehaviorScheduler(
            self.available,
            random=FirstRandom(),
            clock=self.clock,
            random_idle_interval=(10, 10),
            random_idle_duration=(2, 2),
        )

    def test_default_and_random_idle_use_exact_names(self) -> None:
        self.assertEqual(self.scheduler.main_action, "idle_normal")
        self.assertEqual(self.scheduler.current_action, "idle_normal")
        self.clock.advance(10)
        self.assertEqual(self.scheduler.tick(), "idle_blink")
        self.clock.advance(2)
        self.assertEqual(self.scheduler.tick(), "idle_normal")
        self.clock.advance(10)
        self.assertEqual(self.scheduler.tick(), "idle_breathe")

    def test_temporary_action_returns_to_latest_main_state(self) -> None:
        self.scheduler.schedule_study("focus")
        self.scheduler.schedule_interaction("pet_head", 5)
        self.assertEqual(self.scheduler.current_action, "shy")
        self.scheduler.set_main_state("study_normal")
        self.clock.advance(5)
        self.assertEqual(self.scheduler.tick(), "study_normal")

    def test_study_and_entertainment_levels(self) -> None:
        self.assertEqual(self.scheduler.schedule_study("focus"), "study_focus")
        self.assertEqual(self.scheduler.schedule_entertainment(1), "warning_soft")
        self.assertEqual(self.scheduler.schedule_entertainment(2), "warning_strong")
        self.assertEqual(self.scheduler.schedule_entertainment(3), "angry_soft")
        self.assertEqual(self.scheduler.schedule_entertainment(4), "angry_strong")
        self.assertEqual(self.scheduler.schedule_entertainment(6), "disappointed")

    def test_idle_sync_failure_and_care(self) -> None:
        self.assertEqual(self.scheduler.schedule_idle(180), "nap")
        self.assertEqual(self.scheduler.schedule_idle(600), "sleep")
        self.assertEqual(self.scheduler.schedule_sync("failed", 1), "sync_error")
        self.clock.advance(1)
        self.assertEqual(self.scheduler.tick(), "sleep")
        self.assertEqual(self.scheduler.schedule_care("eating", 2), "feed")

    def test_drag_phases_are_temporary_and_restore_main_state(self) -> None:
        self.scheduler.schedule_study("normal")
        self.assertEqual(self.scheduler.drag_start(), "drag_start")
        self.assertEqual(self.scheduler.dragging(), "dragging")
        self.assertEqual(self.scheduler.drag_end(1), "drag_end")
        self.clock.advance(1)
        self.assertEqual(self.scheduler.tick(), "study_normal")

    def test_random_idle_never_interrupts_a_non_idle_main_state(self) -> None:
        self.scheduler.schedule_study("focus")
        self.clock.advance(50)
        self.assertEqual(self.scheduler.tick(), "study_focus")

    def test_available_actions_keyword_is_supported(self) -> None:
        scheduler = PetBehaviorScheduler(
            available_actions={"idle_normal", "warning_soft"},
            clock=self.clock,
            random_idle_interval=None,
        )
        self.assertEqual(scheduler.schedule_sync("failed", 1), "warning_soft")


if __name__ == "__main__":
    unittest.main()
