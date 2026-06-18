from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


DEFAULT_STATE = "idle"
DEFAULT_STATE_ALIASES = {
    "default": "idle",
    "unknown": "idle",
    "focus": "study",
    "focused": "study",
    "learning": "study",
    "entertain": "entertainment",
    "play": "entertainment",
    "tool": "study",
    "reminder": "warning",
    "alert": "warning",
    "urgent": "angry",
    "strong": "angry",
    "pause": "sleep",
    "paused": "sleep",
    "syncing": "idle",
}

STATE_FALLBACKS = {
    "angry": ("warning", "warn", "strong", "idle"),
    "warning": ("warn", "idle"),
    "warn": ("warning", "idle"),
    "study": ("idle",),
    "tool": ("study", "idle"),
    "entertainment": ("idle",),
    "sleep": ("paused", "idle"),
    "paused": ("sleep", "idle"),
    "happy": ("idle",),
    "drag": ("idle",),
    "click": ("idle",),
    "error": ("warning", "warn", "idle"),
}


@dataclass(frozen=True)
class StateResolution:
    requested: str
    mapped: str
    resolved: str
    used_fallback: bool = False


class StateMachine:
    def __init__(
        self,
        states: Iterable[str] | Mapping[str, object] | None = None,
        mapping: Mapping[str, str] | None = None,
        fallback: str = DEFAULT_STATE,
    ):
        if states is not None and not isinstance(states, Mapping) and hasattr(states, "states"):
            character = states
            states = getattr(character, "states", {})
            if mapping is None:
                mapping = getattr(character, "state_map", {})
        state_names = states.keys() if isinstance(states, Mapping) else states
        self.available_states = {
            self._normalize(state) for state in (state_names or ()) if self._normalize(state)
        }
        self.fallback = self._normalize(fallback) or DEFAULT_STATE
        self.mapping = dict(DEFAULT_STATE_ALIASES)
        if mapping:
            self.mapping.update(
                {
                    self._normalize(source): self._normalize(target)
                    for source, target in mapping.items()
                    if self._normalize(source) and self._normalize(target)
                }
            )
        self.current_state = self._fallback_state()
        self.previous_state = self.current_state

    @classmethod
    def from_character(cls, character: object, fallback: str = DEFAULT_STATE) -> "StateMachine":
        return cls(
            getattr(character, "states", {}),
            getattr(character, "state_map", {}),
            fallback,
        )

    @property
    def state(self) -> str:
        return self.current_state

    def resolution(self, requested: str | None) -> StateResolution:
        normalized = self._normalize(requested) or self.fallback
        mapped = self.mapping.get(normalized, normalized)
        if not self.available_states:
            return StateResolution(normalized, mapped, mapped, mapped != normalized)
        candidates = [mapped, normalized]
        for source in (mapped, normalized):
            candidates.extend(STATE_FALLBACKS.get(source, ()))
        for candidate in candidates:
            if candidate in self.available_states:
                return StateResolution(normalized, mapped, candidate, candidate != normalized)
        resolved = self._fallback_state()
        return StateResolution(normalized, mapped, resolved, True)

    def resolve(self, requested: str | None) -> str:
        return self.resolution(requested).resolved

    def set_state(self, requested: str | None) -> str:
        resolved = self.resolve(requested)
        if resolved != self.current_state:
            self.previous_state = self.current_state
            self.current_state = resolved
        return self.current_state

    def transition(self, requested: str | None) -> StateResolution:
        result = self.resolution(requested)
        self.set_state(result.resolved)
        return result

    def configure(
        self,
        states: Iterable[str] | Mapping[str, object],
        mapping: Mapping[str, str] | None = None,
    ) -> str:
        state_names = states.keys() if isinstance(states, Mapping) else states
        self.available_states = {
            self._normalize(state) for state in state_names if self._normalize(state)
        }
        if mapping is not None:
            self.mapping = dict(DEFAULT_STATE_ALIASES)
            self.mapping.update(
                {
                    self._normalize(source): self._normalize(target)
                    for source, target in mapping.items()
                    if self._normalize(source) and self._normalize(target)
                }
            )
        self.current_state = self.resolve(self.current_state)
        self.previous_state = self.resolve(self.previous_state)
        return self.current_state

    def _fallback_state(self) -> str:
        if not self.available_states or self.fallback in self.available_states:
            return self.fallback
        if DEFAULT_STATE in self.available_states:
            return DEFAULT_STATE
        return sorted(self.available_states)[0]

    @staticmethod
    def _normalize(value: object) -> str:
        return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


CharacterStateMachine = StateMachine
