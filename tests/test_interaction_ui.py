from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QToolButton

from pet.character import CharacterPackageLoader
from pet.classifier import Classification
from pet.interaction_ui import CharacterPanel, HoverQuickMenu
from pet.monitor import ActivitySnapshot
from pet.renderers import StaticRenderer
from pet.settings import load_settings
from pet.ui import PetWindow, SettingsDialog


ROOT = Path(__file__).resolve().parents[1]


def static_renderer(character, parent):
    renderer = StaticRenderer(parent)
    renderer.set_character(character)
    return renderer


class InteractionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_hover_menu_emits_actions_and_hides_after_delay(self) -> None:
        menu = HoverQuickMenu()
        selected: list[str] = []
        menu.action_requested.connect(selected.append)
        menu.reveal()
        buttons = menu.findChildren(QToolButton)
        self.assertEqual(len(buttons), 5)
        buttons[0].click()
        self.assertEqual(selected, ["pet_head"])
        menu.hide_later(100)
        self.assertTrue(menu._hide_timer.isActive())
        menu._hide_timer.timeout.emit()
        self.assertTrue(menu.isHidden())
        menu.close()

    def test_character_panel_lists_profiles_and_previews_fallback(self) -> None:
        loader = CharacterPackageLoader(emit_warnings=False)
        profiles = {
            "default_pet": loader.load(ROOT / "characters" / "default_pet"),
            "line_dog_xiaobai": loader.load(ROOT / "characters" / "line_dog_xiaobai"),
        }
        panel = CharacterPanel(profiles, "line_dog_xiaobai", [("broken", "missing character.json")])
        self.assertEqual(panel.character_list.count(), 3)
        self.assertIn("支持动作", panel.metadata.text())
        category = panel.action_category.findData("system")
        panel.action_category.setCurrentIndex(category)
        action = panel.action_name.findData("sync_error")
        panel.action_name.setCurrentIndex(action)
        self.assertIn("fallback", panel.fallback.text())
        emitted: list[tuple[str, str]] = []
        panel.preview_requested.connect(lambda character, state: emitted.append((character, state)))
        panel._preview_action()
        self.assertEqual(emitted, [("line_dog_xiaobai", "sync_error")])
        panel.close()

    def test_pet_window_builds_all_menu_levels_and_persists_care_interaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"EXAM_PLANNER_PET_HOME": directory}):
                with patch("pet.ui.create_renderer", side_effect=static_renderer):
                    window = PetWindow()
                    window.care.set_cooldown("feed", 0)
                    before = window.care.get_status()
                    window.perform_interaction("feed")
                    after = window.care.get_status()
                    self.assertEqual(after.hunger, max(0, before.hunger - 20))
                    self.assertEqual(after.mood, min(100, before.mood + 5))
                    self.assertEqual(window.care.recent_interactions(1)[0]["action"], "feed")

                    click_labels = [action.text() for action in window._interaction_menu().actions()]
                    self.assertEqual(
                        click_labels,
                        ["摸摸头", "陪我学习", "学习打卡", "玩一会儿", "喂食", "送礼物", "聊一句", "查看状态"],
                    )
                    full_labels = [action.text() for action in window._full_menu().actions()]
                    for expected in ("开始学习模式", "暂停提醒 15 分钟", "今日统计", "角色切换", "动作预览", "设置", "重新同步", "退出"):
                        self.assertIn(expected, full_labels)
                    window.shutdown()

                reopened = load_settings()
                self.assertEqual(reopened.character_id, "default_pet")

    def test_interaction_settings_are_saved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"EXAM_PLANNER_PET_HOME": directory}):
                settings = load_settings()
                profile = CharacterPackageLoader(emit_warnings=False).load(ROOT / "characters" / "default_pet")
                dialog = SettingsDialog(settings, {profile.character_id: profile}, care_status=None)
                dialog.care_enabled.setChecked(False)
                dialog.hover_menu_enabled.setChecked(False)
                dialog.interaction_bubbles_enabled.setChecked(False)
                dialog.feed_cooldown.setValue(0)
                dialog.play_cooldown.setValue(7)
                dialog.gift_cooldown.setValue(13)
                dialog.accept()
                raw = json.loads((Path(directory) / "config.json").read_text(encoding="utf-8"))
                self.assertFalse(raw["careEnabled"])
                self.assertFalse(raw["hoverMenuEnabled"])
                self.assertFalse(raw["interactionBubblesEnabled"])
                self.assertEqual(raw["feedCooldownMinutes"], 0)
                self.assertEqual(raw["playCooldownMinutes"], 7)
                self.assertEqual(raw["giftCooldownMinutes"], 13)

    def test_character_selection_persists_and_missing_character_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"EXAM_PLANNER_PET_HOME": directory}):
                loader = CharacterPackageLoader(emit_warnings=False)
                profiles = {
                    "default_pet": loader.load(ROOT / "characters" / "default_pet"),
                    "line_dog_xiaobai": loader.load(ROOT / "characters" / "line_dog_xiaobai"),
                }
                settings = load_settings()
                dialog = SettingsDialog(settings, profiles)
                for row in range(dialog.character_panel.character_list.count()):
                    item = dialog.character_panel.character_list.item(row)
                    if item.data(Qt.UserRole) == "line_dog_xiaobai":
                        dialog.character_panel.character_list.setCurrentRow(row)
                        break
                dialog.accept()
                self.assertEqual(load_settings().character_id, "line_dog_xiaobai")

                config_path = Path(directory) / "config.json"
                raw = json.loads(config_path.read_text(encoding="utf-8"))
                raw["characterId"] = "missing_character"
                config_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
                with patch("pet.ui.create_renderer", side_effect=static_renderer):
                    window = PetWindow()
                    self.assertEqual(window.character.character_id, "default_pet")
                    self.assertEqual(load_settings().character_id, "default_pet")
                    window.shutdown()

    def test_animation_and_interaction_do_not_interrupt_activity_accounting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"EXAM_PLANNER_PET_HOME": directory}):
                with patch("pet.ui.create_renderer", side_effect=static_renderer):
                    window = PetWindow()
                    window.monitor.current = lambda: ActivitySnapshot(
                        "课程 PDF", "chrome.exe", 42, "docs.example.com", 0, 1.0
                    )
                    window.classifier.classify = lambda _snapshot: Classification(
                        "study", "test", "docs.example.com"
                    )
                    window._play_action("click", 2.0)
                    window._sample()
                    report = window.storage.get_report_payload()
                    self.assertEqual(report["studySeconds"], window.settings.sample_interval_seconds)
                    self.assertEqual(report["totalComputerSeconds"], window.settings.sample_interval_seconds)
                    self.assertTrue(window.behavior.is_temporary)
                    window.shutdown()

    def test_entertainment_behavior_escalates_without_stopping_accounting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"EXAM_PLANNER_PET_HOME": directory}):
                with patch("pet.ui.create_renderer", side_effect=static_renderer):
                    window = PetWindow()
                    window.settings.entertainment_limit_minutes = 1
                    window.settings.strong_mode_enabled = False
                    window.monitor.current = lambda: ActivitySnapshot(
                        "视频", "chrome.exe", 42, "bilibili.com", 0, 1.0
                    )
                    window.classifier.classify = lambda _snapshot: Classification(
                        "entertainment", "test", "bilibili.com"
                    )
                    for _ in range(24):
                        window._sample()
                    self.assertEqual(window.behavior.main_action, "warning_soft")
                    for _ in range(6):
                        window._sample()
                    self.assertEqual(window.behavior.main_action, "angry_soft")
                    for _ in range(15):
                        window._sample()
                    self.assertEqual(window.behavior.last_resolution.requested, "angry_strong")
                    self.assertEqual(window.behavior.main_action, "angry_soft")
                    report = window.storage.get_report_payload()
                    self.assertEqual(report["entertainmentSeconds"], 90)
                    self.assertEqual(report["entertainmentOvertimeCount"], 1)
                    window.shutdown()


if __name__ == "__main__":
    unittest.main()
