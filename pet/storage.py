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
                """
            )

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
