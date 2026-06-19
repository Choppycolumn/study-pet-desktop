from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager
import json
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .classifier import Classification
from .monitor import ActivitySnapshot
from .settings import PetSettings


class PetStorage:
    def __init__(self, settings: PetSettings):
        self.settings = settings
        self.path = settings.database_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    @contextmanager
    def connection(self):
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def utc_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def today(self) -> str:
        return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")

    def _init_db(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS daily_summary (
                  date TEXT PRIMARY KEY,
                  timezone TEXT NOT NULL,
                  device_id TEXT NOT NULL,
                  total_computer_seconds INTEGER NOT NULL DEFAULT 0,
                  study_seconds INTEGER NOT NULL DEFAULT 0,
                  entertainment_seconds INTEGER NOT NULL DEFAULT 0,
                  tool_seconds INTEGER NOT NULL DEFAULT 0,
                  social_seconds INTEGER NOT NULL DEFAULT 0,
                  unknown_seconds INTEGER NOT NULL DEFAULT 0,
                  entertainment_overtime_count INTEGER NOT NULL DEFAULT 0,
                  strong_reminder_count INTEGER NOT NULL DEFAULT 0,
                  target_study_seconds INTEGER NOT NULL DEFAULT 0,
                  goal_completed INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS site_usage_daily (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT NOT NULL,
                  device_id TEXT NOT NULL,
                  domain TEXT NOT NULL,
                  category TEXT NOT NULL,
                  seconds INTEGER NOT NULL DEFAULT 0,
                  visits INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE(date, device_id, domain)
                );
                CREATE TABLE IF NOT EXISTS app_usage_daily (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT NOT NULL,
                  device_id TEXT NOT NULL,
                  process_name TEXT NOT NULL,
                  category TEXT NOT NULL,
                  seconds INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE(date, device_id, process_name)
                );
                CREATE TABLE IF NOT EXISTS activity_samples (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  captured_at TEXT NOT NULL,
                  date TEXT NOT NULL,
                  process_name TEXT,
                  window_title TEXT,
                  domain TEXT,
                  category TEXT,
                  duration_seconds INTEGER NOT NULL DEFAULT 0,
                  idle_seconds INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS reminder_events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT NOT NULL,
                  event_type TEXT NOT NULL,
                  message TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sync_queue (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'pending',
                  attempt_count INTEGER NOT NULL DEFAULT 0,
                  last_error TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pet_status (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  character_id TEXT NOT NULL UNIQUE,
                  mood INTEGER NOT NULL DEFAULT 60 CHECK(mood BETWEEN 0 AND 100),
                  affection INTEGER NOT NULL DEFAULT 50 CHECK(affection BETWEEN 0 AND 100),
                  hunger INTEGER NOT NULL DEFAULT 20 CHECK(hunger BETWEEN 0 AND 100),
                  energy INTEGER NOT NULL DEFAULT 80 CHECK(energy BETWEEN 0 AND 100),
                  discipline INTEGER NOT NULL DEFAULT 50 CHECK(discipline BETWEEN 0 AND 100),
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  last_decay_at TEXT NOT NULL,
                  last_fed_at TEXT,
                  last_played_at TEXT,
                  last_gift_at TEXT
                );
                CREATE TABLE IF NOT EXISTS pet_interaction_events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  character_id TEXT NOT NULL,
                  action TEXT NOT NULL,
                  event_type TEXT,
                  mood_delta INTEGER NOT NULL DEFAULT 0,
                  affection_delta INTEGER NOT NULL DEFAULT 0,
                  hunger_delta INTEGER NOT NULL DEFAULT 0,
                  energy_delta INTEGER NOT NULL DEFAULT 0,
                  discipline_delta INTEGER NOT NULL DEFAULT 0,
                  mood INTEGER NOT NULL CHECK(mood BETWEEN 0 AND 100),
                  affection INTEGER NOT NULL CHECK(affection BETWEEN 0 AND 100),
                  hunger INTEGER NOT NULL CHECK(hunger BETWEEN 0 AND 100),
                  energy INTEGER NOT NULL CHECK(energy BETWEEN 0 AND 100),
                  discipline INTEGER NOT NULL CHECK(discipline BETWEEN 0 AND 100),
                  metadata_json TEXT NOT NULL DEFAULT '{}',
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(character_id) REFERENCES pet_status(character_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_pet_interaction_character_created
                  ON pet_interaction_events(character_id, created_at DESC, id DESC);
                """
            )
            self._migrate_pet_care_schema(conn)

    @staticmethod
    def _migrate_pet_care_schema(conn: sqlite3.Connection) -> None:
        """Add care columns to databases created by earlier application versions."""
        status_columns = {row["name"] for row in conn.execute("PRAGMA table_info(pet_status);")}
        if "id" not in status_columns:
            conn.execute("ALTER TABLE pet_status ADD COLUMN id INTEGER;")
            conn.execute("UPDATE pet_status SET id = rowid WHERE id IS NULL;")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pet_status_id ON pet_status(id);")
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_pet_status_fill_id
            AFTER INSERT ON pet_status
            WHEN NEW.id IS NULL
            BEGIN
              UPDATE pet_status SET id = NEW.rowid WHERE rowid = NEW.rowid;
            END;
            """
        )
        for name, declaration in (
            ("last_decay_at", "TEXT"),
            ("last_fed_at", "TEXT"),
            ("last_played_at", "TEXT"),
            ("last_gift_at", "TEXT"),
        ):
            if name not in status_columns:
                conn.execute(f"ALTER TABLE pet_status ADD COLUMN {name} {declaration};")

        event_columns = {row["name"] for row in conn.execute("PRAGMA table_info(pet_interaction_events);")}
        if "action" not in event_columns:
            conn.execute("ALTER TABLE pet_interaction_events ADD COLUMN action TEXT;")
        if "event_type" not in event_columns:
            conn.execute("ALTER TABLE pet_interaction_events ADD COLUMN event_type TEXT;")
        conn.execute(
            """
            UPDATE pet_interaction_events
            SET action = COALESCE(NULLIF(action, ''), event_type),
                event_type = COALESCE(NULLIF(event_type, ''), action);
            """
        )
        conn.execute("UPDATE pet_status SET last_decay_at = COALESCE(last_decay_at, updated_at, created_at);")
        for column, action in (
            ("last_fed_at", "feed"),
            ("last_played_at", "play"),
            ("last_gift_at", "gift"),
        ):
            conn.execute(
                f"""
                UPDATE pet_status
                SET {column} = COALESCE(
                  {column},
                  (SELECT MAX(created_at) FROM pet_interaction_events
                   WHERE pet_interaction_events.character_id = pet_status.character_id
                     AND action = ?)
                );
                """,
                (action,),
            )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pet_interaction_action_cooldown
            ON pet_interaction_events(character_id, action, created_at DESC, id DESC);
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pet_interaction_cooldown
            ON pet_interaction_events(character_id, event_type, created_at DESC, id DESC);
            """
        )

    @staticmethod
    def _pet_status_dict(row: sqlite3.Row) -> dict:
        return {
            "id": int(row["id"] or row["rowid"]) if "rowid" in row.keys() else int(row["id"] or 0),
            "character_id": str(row["character_id"]),
            "mood": int(row["mood"]),
            "affection": int(row["affection"]),
            "hunger": int(row["hunger"]),
            "energy": int(row["energy"]),
            "discipline": int(row["discipline"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "last_decay_at": str(row["last_decay_at"]),
            "last_fed_at": str(row["last_fed_at"]) if row["last_fed_at"] is not None else None,
            "last_played_at": str(row["last_played_at"]) if row["last_played_at"] is not None else None,
            "last_gift_at": str(row["last_gift_at"]) if row["last_gift_at"] is not None else None,
        }

    def get_pet_status(self, character_id: str, initial: dict | None = None, now: str | None = None) -> dict:
        """Load a character's status, creating its independent row when needed."""
        character_id = str(character_id).strip()
        if not character_id:
            raise ValueError("character_id must not be empty")
        values = {"mood": 60, "affection": 50, "hunger": 20, "energy": 80, "discipline": 50}
        if initial:
            values.update({key: max(0, min(100, int(initial[key]))) for key in values if key in initial})
        timestamp = now or self.utc_now()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO pet_status
                (character_id, mood, affection, hunger, energy, discipline, created_at, updated_at, last_decay_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    character_id,
                    values["mood"],
                    values["affection"],
                    values["hunger"],
                    values["energy"],
                    values["discipline"],
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute("SELECT * FROM pet_status WHERE character_id = ?;", (character_id,)).fetchone()
        if row is None:  # pragma: no cover - guarded by the insert above
            raise RuntimeError("failed to create pet status")
        return self._pet_status_dict(row)

    def apply_pet_interaction(
        self,
        character_id: str,
        action: str,
        deltas: dict[str, int],
        *,
        occurred_at: str,
        cooldown_seconds: float = 0,
        metadata: dict | None = None,
        last_decay_at: str | None = None,
    ) -> tuple[dict, bool, float]:
        """Atomically update status and append its event; return status, applied, cooldown left."""
        from datetime import datetime

        character_id = str(character_id).strip()
        action = str(action).strip()
        if not character_id or not action:
            raise ValueError("character_id and action must not be empty")
        metric_names = ("mood", "affection", "hunger", "energy", "discipline")
        normalized_deltas = {name: int(deltas.get(name, 0)) for name in metric_names}

        def parse_timestamp(value: str) -> datetime:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))

        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute(
                """
                INSERT OR IGNORE INTO pet_status
                (character_id, mood, affection, hunger, energy, discipline, created_at, updated_at, last_decay_at)
                VALUES (?, 60, 50, 20, 80, 50, ?, ?, ?);
                """,
                (character_id, occurred_at, occurred_at, occurred_at),
            )
            row = conn.execute("SELECT * FROM pet_status WHERE character_id = ?;", (character_id,)).fetchone()
            if row is None:  # pragma: no cover - guarded by the insert above
                raise RuntimeError("failed to load pet status")

            cooldown_left = 0.0
            if cooldown_seconds > 0:
                latest = conn.execute(
                    """
                    SELECT created_at FROM pet_interaction_events
                    WHERE character_id = ? AND action = ?
                    ORDER BY created_at DESC, id DESC LIMIT 1;
                    """,
                    (character_id, action),
                ).fetchone()
                if latest is not None:
                    elapsed = (parse_timestamp(occurred_at) - parse_timestamp(str(latest["created_at"]))).total_seconds()
                    cooldown_left = max(0.0, float(cooldown_seconds) - max(0.0, elapsed))
                    if cooldown_left > 0:
                        return self._pet_status_dict(row), False, cooldown_left

            updated = {
                name: max(0, min(100, int(row[name]) + normalized_deltas[name]))
                for name in metric_names
            }
            decay_timestamp = last_decay_at or str(row["last_decay_at"])
            conn.execute(
                """
                UPDATE pet_status
                SET mood = ?, affection = ?, hunger = ?, energy = ?, discipline = ?,
                    updated_at = ?, last_decay_at = ?,
                    last_fed_at = CASE WHEN ? = 'feed' THEN ? ELSE last_fed_at END,
                    last_played_at = CASE WHEN ? = 'play' THEN ? ELSE last_played_at END,
                    last_gift_at = CASE WHEN ? = 'gift' THEN ? ELSE last_gift_at END
                WHERE character_id = ?;
                """,
                (
                    updated["mood"],
                    updated["affection"],
                    updated["hunger"],
                    updated["energy"],
                    updated["discipline"],
                    occurred_at,
                    decay_timestamp,
                    action,
                    occurred_at,
                    action,
                    occurred_at,
                    action,
                    occurred_at,
                    character_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO pet_interaction_events
                (character_id, action, event_type, mood_delta, affection_delta, hunger_delta, energy_delta,
                 discipline_delta, mood, affection, hunger, energy, discipline, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    character_id,
                    action,
                    action,
                    normalized_deltas["mood"],
                    normalized_deltas["affection"],
                    normalized_deltas["hunger"],
                    normalized_deltas["energy"],
                    normalized_deltas["discipline"],
                    updated["mood"],
                    updated["affection"],
                    updated["hunger"],
                    updated["energy"],
                    updated["discipline"],
                    json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                    occurred_at,
                ),
            )
            updated_row = conn.execute("SELECT * FROM pet_status WHERE character_id = ?;", (character_id,)).fetchone()
        if updated_row is None:  # pragma: no cover - guarded by the transaction
            raise RuntimeError("failed to update pet status")
        return self._pet_status_dict(updated_row), True, 0.0

    def get_recent_pet_interactions(
        self,
        character_id: str | None = None,
        limit: int = 20,
        action: str | None = None,
        *,
        event_type: str | None = None,
    ) -> list[dict]:
        """Return newest interaction events as JSON-friendly dictionaries."""
        clauses: list[str] = []
        parameters: list[object] = []
        if character_id is not None:
            clauses.append("character_id = ?")
            parameters.append(str(character_id))
        selected_action = action if action is not None else event_type
        if selected_action is not None:
            clauses.append("action = ?")
            parameters.append(str(selected_action))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(max(0, int(limit)))
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM pet_interaction_events
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?;
                """,
                parameters,
            ).fetchall()
        events: list[dict] = []
        for row in rows:
            event = dict(row)
            try:
                event["metadata"] = json.loads(event.pop("metadata_json"))
            except (TypeError, json.JSONDecodeError):
                event["metadata"] = {}
                event.pop("metadata_json", None)
            events.append(event)
        return events

    recent_pet_interactions = get_recent_pet_interactions

    def ensure_day(self, date: str | None = None) -> None:
        date = date or self.today()
        now = self.utc_now()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO daily_summary
                (date, timezone, device_id, target_study_seconds, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                  timezone = excluded.timezone,
                  device_id = excluded.device_id,
                  target_study_seconds = excluded.target_study_seconds,
                  goal_completed = CASE
                    WHEN excluded.target_study_seconds > 0 AND study_seconds >= excluded.target_study_seconds THEN 1
                    ELSE 0
                  END,
                  updated_at = excluded.updated_at;
                """,
                (date, "Asia/Shanghai", self.settings.device_id, self.settings.target_study_minutes * 60, now, now),
            )

    def record_activity(
        self,
        snapshot: ActivitySnapshot,
        classification: Classification,
        duration_seconds: int,
        site_visit: bool = False,
    ) -> None:
        date = self.today()
        self.ensure_day(date)
        duration = max(0, int(duration_seconds))
        now = self.utc_now()
        column = f"{classification.category}_seconds" if classification.category in {"study", "entertainment", "tool", "social", "unknown"} else "unknown_seconds"
        title = snapshot.title[:240]
        process = (snapshot.process_name or "unknown").lower()

        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO activity_samples
                (captured_at, date, process_name, window_title, domain, category, duration_seconds, idle_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (now, date, process, title, classification.domain, classification.category, duration, snapshot.idle_seconds),
            )
            if duration > 0:
                conn.execute(
                    f"""
                    UPDATE daily_summary
                    SET total_computer_seconds = total_computer_seconds + ?,
                        {column} = {column} + ?,
                        goal_completed = CASE
                          WHEN target_study_seconds > 0 AND study_seconds + CASE WHEN ? = 'study_seconds' THEN ? ELSE 0 END >= target_study_seconds THEN 1
                          ELSE goal_completed
                        END,
                        updated_at = ?
                    WHERE date = ?;
                    """,
                    (duration, duration, column, duration, now, date),
                )
                conn.execute(
                    """
                    INSERT INTO app_usage_daily (date, device_id, process_name, category, seconds, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(date, device_id, process_name) DO UPDATE SET
                      category = excluded.category,
                      seconds = seconds + excluded.seconds,
                      updated_at = excluded.updated_at;
                    """,
                    (date, self.settings.device_id, process, classification.category, duration, now, now),
                )
                if classification.domain:
                    conn.execute(
                        """
                        INSERT INTO site_usage_daily (date, device_id, domain, category, seconds, visits, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(date, device_id, domain) DO UPDATE SET
                          category = excluded.category,
                          seconds = seconds + excluded.seconds,
                          visits = visits + excluded.visits,
                          updated_at = excluded.updated_at;
                        """,
                        (date, self.settings.device_id, classification.domain, classification.category, duration, 1 if site_visit else 0, now, now),
                    )

    def record_reminder(self, event_type: str, message: str) -> None:
        date = self.today()
        self.ensure_day(date)
        now = self.utc_now()
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO reminder_events (date, event_type, message, created_at) VALUES (?, ?, ?, ?);",
                (date, event_type, message, now),
            )
            conn.execute(
                """
                UPDATE daily_summary
                SET entertainment_overtime_count = entertainment_overtime_count + CASE WHEN ? = 'entertainment_overtime' THEN 1 ELSE 0 END,
                    strong_reminder_count = strong_reminder_count + 1,
                    updated_at = ?
                WHERE date = ?;
                """,
                (event_type, now, date),
            )

    def get_report_payload(self, date: str | None = None) -> dict:
        date = date or self.today()
        self.ensure_day(date)
        with self.connection() as conn:
            summary = conn.execute("SELECT * FROM daily_summary WHERE date = ?;", (date,)).fetchone()
            sites = conn.execute(
                """
                SELECT domain, category, seconds, visits
                FROM site_usage_daily
                WHERE date = ? AND device_id = ?
                ORDER BY seconds DESC;
                """,
                (date, self.settings.device_id),
            ).fetchall()

        target = int(summary["target_study_seconds"] or 0)
        return {
            "date": date,
            "timezone": "Asia/Shanghai",
            "deviceId": self.settings.device_id,
            "totalComputerSeconds": int(summary["total_computer_seconds"] or 0),
            "studySeconds": int(summary["study_seconds"] or 0),
            "entertainmentSeconds": int(summary["entertainment_seconds"] or 0),
            "toolSeconds": int(summary["tool_seconds"] or 0),
            "socialSeconds": int(summary["social_seconds"] or 0),
            "unknownSeconds": int(summary["unknown_seconds"] or 0),
            "sites": [
                {
                    "domain": row["domain"],
                    "category": row["category"],
                    "seconds": int(row["seconds"] or 0),
                    "visits": int(row["visits"] or 0),
                }
                for row in sites
            ],
            "entertainmentOvertimeCount": int(summary["entertainment_overtime_count"] or 0),
            "strongReminderCount": int(summary["strong_reminder_count"] or 0),
            "studyGoal": {
                "targetStudySeconds": target,
                "completed": bool(summary["goal_completed"]),
            },
        }

    def enqueue_sync(self, payload: dict, error: str = "") -> None:
        now = self.utc_now()
        with self.connection() as conn:
            conn.execute("DELETE FROM sync_queue WHERE date = ? AND status = 'pending';", (payload.get("date", self.today()),))
            conn.execute(
                """
                INSERT INTO sync_queue (date, payload_json, last_error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (payload.get("date", self.today()), json.dumps(payload, ensure_ascii=False), error[:500], now, now),
            )

    def pending_sync_items(self, limit: int = 5) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return list(
                conn.execute(
                    """
                    SELECT * FROM sync_queue
                    WHERE status = 'pending'
                    ORDER BY id ASC
                    LIMIT ?;
                    """,
                    (limit,),
                ).fetchall()
            )

    def mark_sync_done(self, item_id: int) -> None:
        now = self.utc_now()
        with self.connection() as conn:
            conn.execute("UPDATE sync_queue SET status = 'done', updated_at = ? WHERE id = ?;", (now, item_id))

    def mark_sync_failed(self, item_id: int, error: str) -> None:
        now = self.utc_now()
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE sync_queue
                SET attempt_count = attempt_count + 1,
                    last_error = ?,
                    updated_at = ?
                WHERE id = ?;
                """,
                (error[:500], now, item_id),
            )
