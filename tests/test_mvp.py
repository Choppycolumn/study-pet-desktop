from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from pet.character import CharacterPackageLoader
from pet.classifier import ActivityClassifier, Classification
from pet.monitor import ActivitySnapshot
from pet.reminder import ReminderEngine
from pet.renderers import StaticRenderer, renderer_class
from pet.settings import PetSettings, ensure_settings_file, load_settings
from pet.storage import PetStorage
from pet.sync import SyncClient


ROOT = Path(__file__).resolve().parents[1]


def snapshot(title: str, process: str, domain: str = "", idle: int = 0) -> ActivitySnapshot:
    return ActivitySnapshot(title, process, 123, domain, idle, time.time())


class SettingsAndClassificationTests(unittest.TestCase):
    def test_first_launch_creates_user_config_from_example(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"EXAM_PLANNER_PET_HOME": directory}):
                path = ensure_settings_file()
                settings = load_settings()
                self.assertEqual(path, Path(directory) / "config.json")
                self.assertTrue(path.exists())
                self.assertEqual(settings.timezone, "Asia/Shanghai")

    def test_timezone_is_forced_to_shanghai(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"timezone": "Asia/Tokyo"}), encoding="utf-8")
            settings = load_settings(path)
        self.assertEqual(settings.timezone, "Asia/Shanghai")
        self.assertEqual(settings.character_id, "default_pet")

    def test_rule_priority_for_domain_process_and_keyword(self) -> None:
        classifier = ActivityClassifier(PetSettings())
        self.assertEqual(classifier.classify(snapshot("video", "chrome.exe", "bilibili.com")).category, "entertainment")
        self.assertEqual(classifier.classify(snapshot("course PDF", "chrome.exe", "docs.example.com")).category, "study")
        self.assertEqual(classifier.classify(snapshot("workspace", "code.exe")).category, "tool")


class StorageReminderAndSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"EXAM_PLANNER_PET_HOME": self.temp.name})
        self.environment.start()
        self.settings = PetSettings(target_study_minutes=1, entertainment_limit_minutes=1, reminder_cooldown_minutes=0)
        self.storage = PetStorage(self.settings)

    def tearDown(self) -> None:
        self.environment.stop()
        self.temp.cleanup()

    def test_storage_survives_reopen_and_builds_report(self) -> None:
        item = snapshot("bilibili.com - video", "chrome.exe", "bilibili.com")
        classification = Classification("entertainment", "test", "bilibili.com")
        self.storage.record_activity(item, classification, 15, site_visit=True)
        reopened = PetStorage(self.settings)
        report = reopened.get_report_payload()
        self.assertEqual(report["timezone"], "Asia/Shanghai")
        self.assertEqual(report["totalComputerSeconds"], 15)
        self.assertEqual(report["entertainmentSeconds"], 15)
        self.assertEqual(report["sites"][0]["visits"], 1)

    def test_reminder_threshold_and_emergency_pause(self) -> None:
        reminder = ReminderEngine(self.settings)
        decision = reminder.update(Classification("entertainment", "test", ""), 60)
        self.assertTrue(decision.trigger)
        reminder.emergency_pause()
        self.assertFalse(reminder.update(Classification("entertainment", "test", ""), 60).trigger)

    def test_failed_sync_is_queued_without_token_leak(self) -> None:
        self.settings.server_url = "https://example.invalid"
        self.settings.api_token = "top-secret-token"

        class FailingRequests:
            @staticmethod
            def post(*_args, **_kwargs):
                raise RuntimeError("offline")

        from pet import sync as sync_module

        with patch.object(sync_module, "requests", FailingRequests):
            ok, message = SyncClient(self.settings, self.storage).sync_today()
        self.assertFalse(ok)
        self.assertIn("队列", message)
        items = self.storage.pending_sync_items()
        self.assertEqual(len(items), 1)
        self.assertNotIn("top-secret-token", str(dict(items[0])))


class CharacterTests(unittest.TestCase):
    def test_default_package_and_state_fallbacks(self) -> None:
        package = CharacterPackageLoader(emit_warnings=False).load(ROOT / "characters" / "default_pet")
        self.assertEqual(package.renderer, "webview_skin_rig")
        self.assertEqual(len(package.rig.parts), 28)
        self.assertTrue({"idle", "study", "warning", "angry"}.issubset(package.states))
        payload = package.to_web_payload()
        self.assertTrue(str(payload["packageUrl"]).endswith("character.json"))

    def test_unknown_renderer_has_static_extension_fallback(self) -> None:
        self.assertIs(renderer_class("future_renderer"), StaticRenderer)


if __name__ == "__main__":
    unittest.main()
