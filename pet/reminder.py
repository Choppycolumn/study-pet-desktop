from __future__ import annotations

from dataclasses import dataclass
import time

from .classifier import Classification
from .settings import PetSettings


@dataclass
class ReminderDecision:
    trigger: bool
    event_type: str = ""
    message: str = ""
    countdown_seconds: int = 60


class ReminderEngine:
    def __init__(self, settings: PetSettings):
        self.settings = settings
        self.entertainment_streak_seconds = 0
        self.last_strong_reminder_at = 0.0
        self.paused_until = 0.0

    def emergency_pause(self) -> None:
        self.paused_until = time.time() + self.settings.emergency_pause_minutes * 60

    def is_paused(self) -> bool:
        return time.time() < self.paused_until

    def update(self, classification: Classification, duration_seconds: int) -> ReminderDecision:
        if self.is_paused():
            return ReminderDecision(False)

        if classification.category == "entertainment":
            self.entertainment_streak_seconds += max(0, duration_seconds)
        else:
            self.entertainment_streak_seconds = 0

        limit_seconds = self.settings.entertainment_limit_minutes * 60
        cooldown_seconds = self.settings.reminder_cooldown_minutes * 60
        now = time.time()
        if (
            self.entertainment_streak_seconds >= limit_seconds
            and now - self.last_strong_reminder_at >= cooldown_seconds
        ):
            self.last_strong_reminder_at = now
            return ReminderDecision(
                True,
                "entertainment_overtime",
                "娱乐时间已经超过设定阈值，请确认开始学习。",
                countdown_seconds=60,
            )

        return ReminderDecision(False)
