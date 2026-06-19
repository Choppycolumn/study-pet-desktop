from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from pet.care import PetCareSystem, PetStatus
from pet.settings import PetSettings
from pet.storage import PetStorage


class MutableClock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: float) -> None:
        self.value += timedelta(**kwargs)


class PetCareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"EXAM_PLANNER_PET_HOME": self.temp.name})
        self.environment.start()
        self.settings = PetSettings(
            feed_cooldown_minutes=0,
            play_cooldown_minutes=0,
            gift_cooldown_minutes=0,
        )
        self.storage = PetStorage(self.settings)
        self.clock = MutableClock(datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc))

    def tearDown(self) -> None:
        self.environment.stop()
        self.temp.cleanup()

    def test_each_character_has_persistent_independent_status(self) -> None:
        cat = PetCareSystem(self.storage, "cat", clock=self.clock)
        dog = PetCareSystem(self.storage, "dog", clock=self.clock)

        cat_status = cat.feed()
        dog_status = dog.get_status()
        self.assertIsInstance(cat_status, PetStatus)
        self.assertLess(cat_status.hunger, dog_status.hunger)
        self.assertEqual(dog_status.hunger, PetCareSystem.INITIAL_STATUS["hunger"])

        reopened = PetCareSystem(PetStorage(self.settings), "cat", clock=self.clock)
        self.assertEqual(reopened.get_status(), cat_status)
        events = reopened.recent_interactions()
        self.assertEqual([event["action"] for event in events], ["feed"])
        self.assertEqual(events[0]["character_id"], "cat")

    def test_actions_apply_only_the_specified_rule_deltas_and_timestamps(self) -> None:
        care = PetCareSystem(self.storage, "cat", cooldowns={"pet_head": 0}, clock=self.clock)
        initial = care.get_status()

        fed = care.feed()
        self.assertEqual((fed.hunger, fed.mood, fed.affection), (initial.hunger - 20, initial.mood + 5, initial.affection + 2))
        self.assertEqual((fed.energy, fed.discipline), (initial.energy, initial.discipline))
        self.assertEqual(fed.last_fed_at, fed.updated_at)

        self.clock.advance(seconds=1)
        played = care.play()
        self.assertEqual((played.mood, played.energy, played.affection), (fed.mood + 8, fed.energy - 5, fed.affection + 3))
        self.assertEqual((played.hunger, played.discipline), (fed.hunger, fed.discipline))
        self.assertEqual(played.last_played_at, played.updated_at)

        self.clock.advance(seconds=1)
        gifted = care.gift()
        self.assertEqual((gifted.affection, gifted.mood), (played.affection + 5, played.mood + 10))
        self.assertEqual(gifted.last_gift_at, gifted.updated_at)

        self.clock.advance(seconds=1)
        petted = care.pet_head()
        self.assertEqual((petted.affection, petted.mood), (gifted.affection + 1, gifted.mood + 2))

        studied = care.study_tick(2)
        self.assertEqual(
            (studied.discipline, studied.affection, studied.mood),
            (petted.discipline + 2, petted.affection + 2, petted.mood + 2),
        )
        overtime = care.entertainment_overtime()
        self.assertEqual((overtime.discipline, overtime.mood), (studied.discipline - 2, studied.mood - 3))
        self.assertEqual((overtime.affection, overtime.hunger, overtime.energy), (studied.affection, studied.hunger, studied.energy))

        events = care.recent_interactions()
        self.assertTrue(all(event["action"] == event["event_type"] for event in events))

    def test_configurable_cooldown_does_not_write_blocked_events(self) -> None:
        care = PetCareSystem(self.storage, "cat", cooldowns={"feed": 60}, clock=self.clock)
        first = care.feed()
        self.clock.advance(seconds=30)
        blocked = care.feed()

        self.assertFalse(care.last_action_applied)
        self.assertAlmostEqual(care.cooldown_remaining_seconds, 30)
        self.assertEqual(blocked, first)
        self.assertEqual(len(care.recent_interactions(event_type="feed")), 1)

        self.clock.advance(seconds=31)
        care.feed()
        self.assertTrue(care.last_action_applied)
        self.assertEqual(len(care.recent_interactions(event_type="feed")), 2)

    def test_actions_clamp_values_and_recent_query_honors_limit(self) -> None:
        care = PetCareSystem(self.storage, "cat", cooldowns={"pet_head": 0}, clock=self.clock)
        for _ in range(20):
            status = care.pet_head()
        self.assertEqual(status.mood, 100)
        self.assertEqual(status.affection, 70)
        self.assertTrue(all(0 <= getattr(status, name) <= 100 for name in ("mood", "affection", "hunger", "energy", "discipline")))
        self.assertEqual(len(care.recent_interactions(limit=3)), 3)

    def test_time_decay_keeps_fractional_elapsed_time_across_restart(self) -> None:
        care = PetCareSystem(self.storage, "cat", clock=self.clock)
        initial = care.get_status()
        self.clock.advance(minutes=90)
        after_first_hour = care.time_decay()
        self.assertEqual(after_first_hour.hunger, initial.hunger + 4)
        self.assertEqual(after_first_hour.energy, initial.energy + 2)
        self.assertEqual(after_first_hour.mood, initial.mood - 1)

        self.clock.advance(minutes=30)
        reopened = PetCareSystem(PetStorage(self.settings), "cat", clock=self.clock)
        after_second_hour = reopened.time_decay()
        self.assertEqual(after_second_hour.hunger, initial.hunger + 8)
        self.assertEqual(after_second_hour.energy, initial.energy + 4)
        self.assertEqual(len(reopened.recent_interactions(event_type="time_decay")), 2)

        self.clock.advance(hours=1)
        after_three_hours = reopened.time_decay()
        self.assertEqual(after_three_hours.mood, initial.mood - 3)
        self.assertGreaterEqual(after_three_hours.energy, after_second_hour.energy)

    def test_status_and_event_roll_back_together(self) -> None:
        care = PetCareSystem(self.storage, "cat", clock=self.clock)
        before = care.get_status()
        with self.storage.connection() as conn:
            conn.execute(
                """
                CREATE TRIGGER reject_gift_event
                BEFORE INSERT ON pet_interaction_events
                WHEN NEW.action = 'gift'
                BEGIN
                  SELECT RAISE(ABORT, 'test event failure');
                END;
                """
            )

        with self.assertRaises(sqlite3.IntegrityError):
            care.gift()
        self.assertEqual(care.get_status(), before)
        self.assertEqual(care.recent_interactions(), [])

    def test_new_tables_do_not_change_report_or_sync_tables(self) -> None:
        care = PetCareSystem(self.storage, "cat", clock=self.clock)
        care.play()
        report = self.storage.get_report_payload("2026-01-02")
        now = self.storage.utc_now()
        with self.storage.connection() as conn:
            conn.execute(
                """
                INSERT INTO sync_queue (date, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?);
                """,
                (report["date"], "{}", now, now),
            )

        self.assertEqual(report["totalComputerSeconds"], 0)
        self.assertEqual(len(self.storage.pending_sync_items()), 1)
        with self.storage.connection() as conn:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table';").fetchall()
            }
        self.assertTrue({"daily_summary", "sync_queue", "pet_status", "pet_interaction_events"}.issubset(tables))

    def test_legacy_event_type_schema_is_migrated_in_place(self) -> None:
        database = self.settings.database_path
        conn = sqlite3.connect(database)
        try:
            conn.execute("DROP TABLE pet_interaction_events;")
            conn.execute("DROP TABLE pet_status;")
            conn.execute(
                """
                CREATE TABLE pet_status (
                  character_id TEXT PRIMARY KEY, mood INTEGER, affection INTEGER, hunger INTEGER,
                  energy INTEGER, discipline INTEGER, created_at TEXT, updated_at TEXT,
                  last_decay_at TEXT
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE pet_interaction_events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, character_id TEXT, event_type TEXT,
                  mood_delta INTEGER, affection_delta INTEGER, hunger_delta INTEGER,
                  energy_delta INTEGER, discipline_delta INTEGER, mood INTEGER, affection INTEGER,
                  hunger INTEGER, energy INTEGER, discipline INTEGER, metadata_json TEXT, created_at TEXT
                );
                """
            )
            timestamp = "2026-01-01T00:00:00Z"
            conn.execute(
                "INSERT INTO pet_status VALUES ('cat', 65, 52, 0, 80, 50, ?, ?, ?);",
                (timestamp, timestamp, timestamp),
            )
            conn.execute(
                """
                INSERT INTO pet_interaction_events
                (character_id, event_type, mood_delta, affection_delta, hunger_delta, energy_delta,
                 discipline_delta, mood, affection, hunger, energy, discipline, metadata_json, created_at)
                VALUES ('cat', 'feed', 5, 2, -20, 0, 0, 65, 52, 0, 80, 50, '{}', ?);
                """,
                (timestamp,),
            )
            conn.commit()
        finally:
            conn.close()

        migrated = PetStorage(self.settings)
        status = migrated.get_pet_status("cat")
        event = migrated.get_recent_pet_interactions("cat")[0]
        self.assertEqual(status["last_fed_at"], timestamp)
        self.assertEqual(event["action"], "feed")
        with migrated.connection() as conn:
            status_columns = {row["name"] for row in conn.execute("PRAGMA table_info(pet_status);")}
            event_columns = {row["name"] for row in conn.execute("PRAGMA table_info(pet_interaction_events);")}
        self.assertTrue({"id", "last_fed_at", "last_played_at", "last_gift_at", "updated_at"}.issubset(status_columns))
        self.assertGreater(status["id"], 0)
        self.assertIn("action", event_columns)


if __name__ == "__main__":
    unittest.main()
