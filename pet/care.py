from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Callable, Mapping

from .storage import PetStorage


_METRICS = ("mood", "affection", "hunger", "energy", "discipline")


@dataclass(frozen=True)
class PetStatus:
    id: int
    character_id: str
    mood: int
    affection: int
    hunger: int
    energy: int
    discipline: int
    created_at: str
    updated_at: str
    last_decay_at: str
    last_fed_at: str | None
    last_played_at: str | None
    last_gift_at: str | None

    def __post_init__(self) -> None:
        for name in _METRICS:
            value = int(getattr(self, name))
            if not 0 <= value <= 100:
                raise ValueError(f"{name} must be between 0 and 100")

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> PetStatus:
        return cls(
            id=int(value.get("id", 0)),
            character_id=str(value["character_id"]),
            mood=int(value["mood"]),
            affection=int(value["affection"]),
            hunger=int(value["hunger"]),
            energy=int(value["energy"]),
            discipline=int(value["discipline"]),
            created_at=str(value["created_at"]),
            updated_at=str(value["updated_at"]),
            last_decay_at=str(value["last_decay_at"]),
            last_fed_at=str(value["last_fed_at"]) if value["last_fed_at"] is not None else None,
            last_played_at=str(value["last_played_at"]) if value["last_played_at"] is not None else None,
            last_gift_at=str(value["last_gift_at"]) if value["last_gift_at"] is not None else None,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "character_id": self.character_id,
            "mood": self.mood,
            "affection": self.affection,
            "hunger": self.hunger,
            "energy": self.energy,
            "discipline": self.discipline,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_decay_at": self.last_decay_at,
            "last_fed_at": self.last_fed_at,
            "last_played_at": self.last_played_at,
            "last_gift_at": self.last_gift_at,
        }


class PetCareSystem:
    """Persistent, per-character pet care rules on top of PetStorage."""

    INITIAL_STATUS = {
        "mood": 60,
        "affection": 50,
        "hunger": 20,
        "energy": 80,
        "discipline": 50,
    }
    DEFAULT_COOLDOWNS = {
        "feed": 5 * 60,
        "play": 10 * 60,
        "gift": 30 * 60,
        "pet_head": 2,
        "study_tick": 0,
        "entertainment_overtime": 0,
        "time_decay": 0,
    }

    def __init__(
        self,
        storage: PetStorage,
        character_id: str | None = None,
        *,
        cooldowns: Mapping[str, float | timedelta] | None = None,
        clock: Callable[[], datetime | str] | None = None,
    ):
        self.storage = storage
        self.character_id = str(character_id or storage.settings.character_id).strip()
        if not self.character_id:
            raise ValueError("character_id must not be empty")
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        settings = storage.settings
        self.cooldowns = dict(self.DEFAULT_COOLDOWNS)
        self.cooldowns.update(
            {
                "feed": max(0, int(settings.feed_cooldown_minutes) * 60),
                "play": max(0, int(settings.play_cooldown_minutes) * 60),
                "gift": max(0, int(settings.gift_cooldown_minutes) * 60),
            }
        )
        if cooldowns:
            for event_type, duration in cooldowns.items():
                self.set_cooldown(event_type, duration)
        self.last_action_applied = True
        self.cooldown_remaining_seconds = 0.0
        self.storage.get_pet_status(self.character_id, self.INITIAL_STATUS, self._timestamp())

    @staticmethod
    def _as_datetime(value: datetime | str) -> datetime:
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        elif isinstance(value, datetime):
            parsed = value
        else:
            raise TypeError("timestamp must be a datetime or ISO-8601 string")
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _isoformat(cls, value: datetime | str) -> str:
        return cls._as_datetime(value).isoformat().replace("+00:00", "Z")

    def _timestamp(self, value: datetime | str | None = None) -> str:
        return self._isoformat(self._clock() if value is None else value)

    @staticmethod
    def _seconds(value: float | timedelta) -> float:
        seconds = value.total_seconds() if isinstance(value, timedelta) else float(value)
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("cooldown must be a finite non-negative duration")
        return seconds

    def set_cooldown(self, event_type: str, duration: float | timedelta) -> None:
        event_type = str(event_type).strip()
        if not event_type:
            raise ValueError("event_type must not be empty")
        self.cooldowns[event_type] = self._seconds(duration)

    def get_status(self) -> PetStatus:
        return PetStatus.from_dict(self.storage.get_pet_status(self.character_id, self.INITIAL_STATUS, self._timestamp()))

    @property
    def status(self) -> PetStatus:
        return self.get_status()

    def _apply(
        self,
        action: str,
        deltas: Mapping[str, int],
        *,
        now: datetime | str | None = None,
        metadata: dict | None = None,
        last_decay_at: str | None = None,
    ) -> PetStatus:
        row, applied, remaining = self.storage.apply_pet_interaction(
            self.character_id,
            action,
            dict(deltas),
            occurred_at=self._timestamp(now),
            cooldown_seconds=self.cooldowns.get(action, 0),
            metadata=metadata,
            last_decay_at=last_decay_at,
        )
        self.last_action_applied = applied
        self.cooldown_remaining_seconds = remaining
        return PetStatus.from_dict(row)

    def feed(self, *, now: datetime | str | None = None) -> PetStatus:
        return self._apply("feed", {"hunger": -20, "mood": 5, "affection": 2}, now=now)

    def play(self, *, now: datetime | str | None = None) -> PetStatus:
        return self._apply("play", {"mood": 8, "energy": -5, "affection": 3}, now=now)

    def gift(self, *, now: datetime | str | None = None) -> PetStatus:
        return self._apply("gift", {"affection": 5, "mood": 10}, now=now)

    def pet_head(self, *, now: datetime | str | None = None) -> PetStatus:
        return self._apply("pet_head", {"affection": 1, "mood": 2}, now=now)

    def study_tick(
        self,
        units: int = 1,
        *,
        now: datetime | str | None = None,
    ) -> PetStatus:
        if isinstance(units, bool) or int(units) != units or units <= 0:
            raise ValueError("study units must be a positive integer")
        units = int(units)
        return self._apply(
            "study_tick",
            {"discipline": units, "affection": units, "mood": units},
            now=now,
            metadata={"units": units},
        )

    def entertainment_overtime(
        self,
        *,
        now: datetime | str | None = None,
    ) -> PetStatus:
        return self._apply("entertainment_overtime", {"discipline": -2, "mood": -3}, now=now)

    def time_decay(
        self,
        *,
        now: datetime | str | None = None,
        hours: float | None = None,
        elapsed_seconds: float | None = None,
    ) -> PetStatus:
        if hours is not None and elapsed_seconds is not None:
            raise ValueError("provide hours or elapsed_seconds, not both")
        current = self._as_datetime(self._clock() if now is None else now)
        status = self.get_status()
        previous = self._as_datetime(status.last_decay_at)
        if hours is not None:
            elapsed = float(hours) * 3600
        elif elapsed_seconds is not None:
            elapsed = float(elapsed_seconds)
        else:
            elapsed = (current - previous).total_seconds()
        if not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("decay duration must be finite and non-negative")
        completed_hours = int(elapsed // 3600)
        if completed_hours == 0:
            self.last_action_applied = False
            self.cooldown_remaining_seconds = 0.0
            return status

        decay_at = previous + timedelta(hours=completed_hours)
        event_at = max(current, decay_at)
        return self._apply(
            "time_decay",
            {
                "mood": -completed_hours,
                "hunger": 4 * completed_hours,
                "energy": 2 * completed_hours,
            },
            now=event_at,
            metadata={"elapsed_hours": completed_hours},
            last_decay_at=self._isoformat(decay_at),
        )

    def recent_interactions(
        self,
        limit: int = 20,
        action: str | None = None,
        *,
        event_type: str | None = None,
    ) -> list[dict]:
        return self.storage.get_recent_pet_interactions(
            self.character_id,
            limit,
            action,
            event_type=event_type,
        )

    get_recent_interactions = recent_interactions
