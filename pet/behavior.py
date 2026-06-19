from __future__ import annotations

import random as random_module
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .action_library import ALL_ACTIONS, ActionResolution, resolve_action


RANDOM_IDLE_ACTIONS = (
    "idle_blink",
    "idle_breathe",
    "idle_look_left",
    "idle_look_right",
    "idle_stretch",
    "idle_bored",
    "idle_random_01",
    "idle_random_02",
    "idle_random_03",
)

STUDY_LEVEL_ACTIONS = {
    "normal": "study_normal",
    "focus": "study_focus",
    "reading": "study_reading",
    "typing": "study_typing",
    "writing": "study_writing",
    "thinking": "study_thinking",
    "encourage": "study_encourage",
    "complete": "study_complete",
}

ENTERTAINMENT_LEVEL_ACTIONS = {
    "none": "idle_normal",
    "near_limit": "warning_soft",
    "at_limit": "warning_medium",
    "over_limit": "warning_strong",
    "continued": "angry_soft",
    "severe": "angry_strong",
    "stare": "stare",
    "disappointed": "disappointed",
}


class PetBehaviorScheduler:
    def __init__(
        self,
        available: Iterable[str] | Mapping[str, object] | None = None,
        *,
        available_actions: Iterable[str] | Mapping[str, object] | None = None,
        random: Any | None = None,
        random_source: Any | None = None,
        clock: Callable[[], float] | Any | None = None,
        random_idle_interval: tuple[float, float] | None = (20.0, 45.0),
        random_idle_duration: tuple[float, float] = (1.5, 4.0),
    ) -> None:
        if available is not None and available_actions is not None:
            raise TypeError("pass available or available_actions, not both")
        self._random = random_source if random_source is not None else random
        if self._random is None:
            self._random = random_module.Random()
        self._clock = self._clock_callable(clock)
        self.random_idle_interval = self._range(random_idle_interval, allow_none=True)
        self.random_idle_duration = self._range(random_idle_duration)
        source_actions = available_actions if available_actions is not None else available
        self.available_actions = self._available(source_actions)

        self.last_resolution = self._resolve("idle_normal")
        self.main_action = self.last_resolution.actual
        self.current_action = self.main_action
        self.requested_action = "idle_normal"
        self._temporary_until: float | None = None
        self._next_idle_at: float | None = None
        self._last_random_idle: str | None = None
        self._schedule_next_idle(self.now)

    @staticmethod
    def _clock_callable(clock: Callable[[], float] | Any | None) -> Callable[[], float]:
        if clock is None:
            return time.monotonic
        if callable(clock):
            return clock
        for name in ("monotonic", "time", "now"):
            method = getattr(clock, name, None)
            if callable(method):
                return method
        raise TypeError("clock must be callable or provide monotonic(), time(), or now()")

    @staticmethod
    def _range(
        value: tuple[float, float] | None,
        *,
        allow_none: bool = False,
    ) -> tuple[float, float] | None:
        if value is None and allow_none:
            return None
        if value is None or len(value) != 2:
            raise ValueError("range must contain two values")
        low, high = float(value[0]), float(value[1])
        if low < 0 or high < low:
            raise ValueError("range must satisfy 0 <= low <= high")
        return low, high

    @staticmethod
    def _available(available: Iterable[str] | Mapping[str, object] | None) -> frozenset[str]:
        if available is None:
            return frozenset(ALL_ACTIONS)
        values = available.keys() if isinstance(available, Mapping) else available
        return frozenset(
            "_".join(str(value).strip().lower().replace("-", " ").split())
            for value in values
            if str(value).strip()
        )

    @property
    def now(self) -> float:
        return float(self._clock())

    @property
    def state(self) -> str:
        return self.current_action

    @property
    def action(self) -> str:
        return self.current_action

    @property
    def main_state(self) -> str:
        return self.main_action

    @property
    def primary_action(self) -> str:
        return self.main_action

    @property
    def temporary_action(self) -> str | None:
        return self.current_action if self.is_temporary else None

    @property
    def temporary_until(self) -> float | None:
        return self._temporary_until

    expires_at = temporary_until

    @property
    def is_temporary(self) -> bool:
        return self._temporary_until is not None

    def _resolve(self, action: object) -> ActionResolution:
        return resolve_action(self.available_actions, action)

    def _activate(self, resolution: ActionResolution) -> None:
        self.last_resolution = resolution
        self.requested_action = resolution.requested
        self.current_action = resolution.actual

    def configure_actions(self, available: Iterable[str] | Mapping[str, object]) -> str:
        self.available_actions = self._available(available)
        self.main_action = self._resolve(self.main_action).actual
        self.current_action = self._resolve(self.current_action).actual
        return self.current_action

    def set_main_state(self, action: object, *, interrupt: bool = False) -> str:
        resolution = self._resolve(action)
        self.main_action = resolution.actual
        self.last_resolution = resolution
        if interrupt or not self.is_temporary:
            self._activate(resolution)
        self._schedule_next_idle(self.now)
        return resolution.actual

    set_main_action = set_main_state

    def play_temporary(self, action: object, duration: float) -> str:
        seconds = float(duration)
        if seconds <= 0:
            return self.cancel_temporary()
        resolution = self._resolve(action)
        self._activate(resolution)
        self._temporary_until = self.now + seconds
        return resolution.actual

    trigger = play_temporary
    schedule_temporary = play_temporary

    def cancel_temporary(self) -> str:
        self._temporary_until = None
        self._activate(self._resolve(self.main_action))
        self._schedule_next_idle(self.now)
        return self.current_action

    def tick(self) -> str:
        now = self.now
        if self._temporary_until is not None:
            if now < self._temporary_until:
                return self.current_action
            self._temporary_until = None
            self._activate(self._resolve(self.main_action))
            self._schedule_next_idle(now)

        if self._next_idle_at is not None and now >= self._next_idle_at and self.main_action == "idle_normal":
            return self.schedule_random_idle()
        return self.current_action

    update = tick

    def schedule_random_idle(self, duration: float | None = None) -> str:
        supported = [action for action in RANDOM_IDLE_ACTIONS if action in self.available_actions]
        if not supported:
            self._schedule_next_idle(self.now)
            return self.current_action
        if len(supported) > 1 and self._last_random_idle in supported:
            supported.remove(self._last_random_idle)
        action = self._choice(supported)
        self._last_random_idle = action
        seconds = self._uniform(self.random_idle_duration) if duration is None else float(duration)
        return self.play_temporary(action, seconds)

    random_idle = schedule_random_idle

    def schedule_study(self, level: object = "normal") -> str:
        key = self._study_level(level)
        action = STUDY_LEVEL_ACTIONS[key]
        if key == "complete":
            return self.play_temporary(action, 4.0)
        return self.set_main_state(action)

    study = schedule_study
    on_study = schedule_study

    def complete_study(self, duration: float = 4.0) -> str:
        return self.play_temporary("study_complete", duration)

    def start_study(self) -> str:
        self.play_temporary("forgive", 1.5)
        self.main_action = self._resolve("study_focus").actual
        return self.current_action

    def schedule_entertainment(self, level: object = "near_limit") -> str:
        key = self._entertainment_level(level)
        return self.set_main_state(ENTERTAINMENT_LEVEL_ACTIONS[key])

    entertainment = schedule_entertainment
    on_entertainment = schedule_entertainment

    def schedule_idle(self, idle_seconds: float = 0) -> str:
        seconds = max(0.0, float(idle_seconds))
        if seconds >= 600:
            return self.set_main_state("sleep")
        if seconds >= 180:
            return self.set_main_state("nap")
        return self.set_main_state("idle_normal")

    idle = schedule_idle
    on_idle = schedule_idle

    def schedule_sync(self, status: object = "syncing", duration: float | None = None) -> str:
        key = str(status or "syncing").strip().lower().replace("-", "_").replace(" ", "_")
        action = {
            "start": "syncing",
            "sync": "syncing",
            "success": "sync_success",
            "ok": "sync_success",
            "complete": "sync_success",
            "completed": "sync_success",
            "error": "sync_error",
            "failed": "sync_error",
            "failure": "sync_error",
            "network": "network_error",
        }.get(key, key)
        return self.play_temporary(action, 3.0 if duration is None else duration)

    sync = schedule_sync
    on_sync = schedule_sync

    def schedule_interaction(self, action: object = "click", duration: float = 2.0) -> str:
        return self.play_temporary(action, duration)

    interact = schedule_interaction
    on_interaction = schedule_interaction

    def schedule_care(self, action: object, duration: float = 3.0) -> str:
        return self.play_temporary(action, duration)

    care = schedule_care
    on_care = schedule_care

    def schedule_drag(self, phase: object, duration: float | None = None) -> str:
        key = str(phase).strip().lower().replace("-", "_").replace(" ", "_")
        action = {
            "start": "drag_start",
            "drag_start": "drag_start",
            "move": "dragging",
            "drag": "dragging",
            "dragging": "dragging",
            "end": "drag_end",
            "drop": "drag_end",
            "drag_end": "drag_end",
        }.get(key)
        if action is None:
            raise ValueError(f"unknown drag phase: {phase!r}")
        default = 0.5 if action != "dragging" else 30.0
        return self.play_temporary(action, default if duration is None else duration)

    def drag_start(self, duration: float = 0.5) -> str:
        return self.schedule_drag("start", duration)

    def dragging(self, duration: float = 30.0) -> str:
        return self.schedule_drag("dragging", duration)

    def drag_end(self, duration: float = 0.7) -> str:
        return self.schedule_drag("end", duration)

    on_drag_start = drag_start
    on_dragging = dragging
    on_drag_end = drag_end

    def _schedule_next_idle(self, now: float) -> None:
        if self.random_idle_interval is None or self.main_action != "idle_normal":
            self._next_idle_at = None
        else:
            self._next_idle_at = now + self._uniform(self.random_idle_interval)

    def _choice(self, values: list[str]) -> str:
        method = getattr(self._random, "choice", None)
        if callable(method):
            return str(method(values))
        value = self._random() if callable(self._random) else random_module.random()
        return values[min(len(values) - 1, int(float(value) * len(values)))]

    def _uniform(self, value_range: tuple[float, float]) -> float:
        low, high = value_range
        method = getattr(self._random, "uniform", None)
        if callable(method):
            return float(method(low, high))
        value = self._random() if callable(self._random) else random_module.random()
        return low + (high - low) * float(value)

    @staticmethod
    def _study_level(level: object) -> str:
        if isinstance(level, (int, float)):
            number = float(level)
            return "normal" if number <= 1 else "focus" if number <= 2 else "encourage"
        key = str(level or "normal").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {"focused": "focus", "read": "reading", "write": "writing", "done": "complete"}
        key = aliases.get(key, key)
        if key not in STUDY_LEVEL_ACTIONS:
            raise ValueError(f"unknown study level: {level!r}")
        return key

    @staticmethod
    def _entertainment_level(level: object) -> str:
        if isinstance(level, (int, float)):
            number = int(level)
            keys = ("none", "near_limit", "over_limit", "continued", "severe", "stare", "disappointed")
            return keys[max(0, min(number, len(keys) - 1))]
        key = str(level or "near_limit").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "soft": "near_limit",
            "warning": "near_limit",
            "medium": "at_limit",
            "strong": "over_limit",
            "over": "over_limit",
            "angry": "continued",
            "high": "severe",
            "critical": "severe",
        }
        key = aliases.get(key, key)
        if key not in ENTERTAINMENT_LEVEL_ACTIONS:
            raise ValueError(f"unknown entertainment level: {level!r}")
        return key


BehaviorScheduler = PetBehaviorScheduler


__all__ = [
    "BehaviorScheduler",
    "ENTERTAINMENT_LEVEL_ACTIONS",
    "PetBehaviorScheduler",
    "RANDOM_IDLE_ACTIONS",
    "STUDY_LEVEL_ACTIONS",
]
