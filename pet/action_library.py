from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


ACTION_CATEGORIES: dict[str, tuple[str, ...]] = {
    "idle": (
        "idle_normal",
        "idle_blink",
        "idle_breathe",
        "idle_look_left",
        "idle_look_right",
        "idle_stretch",
        "idle_sit",
        "idle_lie",
        "idle_bored",
        "idle_random_01",
        "idle_random_02",
        "idle_random_03",
    ),
    "study": (
        "study_normal",
        "study_focus",
        "study_reading",
        "study_typing",
        "study_writing",
        "study_thinking",
        "study_encourage",
        "study_complete",
        "ask_study",
        "study_together",
        "check_progress",
        "praise_study",
    ),
    "discipline": (
        "warning_soft",
        "warning_medium",
        "warning_strong",
        "angry_soft",
        "angry_strong",
        "disappointed",
        "stare",
        "block_screen",
        "force_study",
        "forgive",
    ),
    "emotion": (
        "happy",
        "excited",
        "proud",
        "shy",
        "sad",
        "wronged",
        "angry",
        "surprised",
        "confused",
        "tired",
        "sleepy",
        "calm",
    ),
    "interaction": (
        "click",
        "double_click",
        "pet_head",
        "drag_start",
        "dragging",
        "drag_end",
        "greet",
        "wave",
        "nod",
        "shake_head",
        "poke",
        "hide",
        "return_back",
    ),
    "routine": (
        "wake_up",
        "sleep",
        "nap",
        "good_morning",
        "good_afternoon",
        "good_evening",
        "late_night_warning",
        "break_time",
        "back_to_work",
    ),
    "system": (
        "syncing",
        "sync_success",
        "sync_error",
        "network_error",
        "config_error",
        "loading",
        "update_available",
        "achievement",
    ),
    "easter_egg": (
        "dance",
        "cheer",
        "celebrate",
        "roll",
        "hide_and_peek",
        "special_01",
        "special_02",
        "special_03",
    ),
    "care": (
        "feed",
        "eating",
        "full",
        "hungry",
        "play",
        "playing",
        "gift",
        "love",
        "pet_head",
        "shy",
        "spoiled",
        "lonely",
        "want_attention",
    ),
    "menu": (
        "menu_open",
        "menu_hover",
        "menu_select",
        "settings_open",
    ),
}

STANDARD_ACTIONS = ACTION_CATEGORIES
ALL_ACTIONS = tuple(
    dict.fromkeys(action for actions in ACTION_CATEGORIES.values() for action in actions)
)
ALL_STANDARD_ACTIONS = ALL_ACTIONS


ACTION_ALIASES = {
    "default": "idle_normal",
    "idle": "idle_normal",
    "study": "study_normal",
    "focus": "study_focus",
    "reading": "study_reading",
    "typing": "study_typing",
    "writing": "study_writing",
    "thinking": "study_thinking",
    "encourage": "study_encourage",
    "complete": "study_complete",
    "warning": "warning_soft",
    "warn": "warning_soft",
    "strong": "warning_strong",
    "entertainment": "play",
    "entertain": "play",
    "head_pet": "pet_head",
    "touch_head": "pet_head",
    "tap": "click",
    "drag": "dragging",
    "wake": "wake_up",
    "sync": "syncing",
    "settings": "settings_open",
}

LEGACY_ACTION_TARGETS: dict[str, tuple[str, ...]] = {
    "idle_normal": ("idle",),
    "study_normal": ("study",),
    "study_focus": ("study",),
    "study_typing": ("study",),
    "warning_soft": ("warning", "warn"),
    "warning_medium": ("warning", "warn"),
    "warning_strong": ("strong", "warning", "warn"),
    "angry_soft": ("angry", "strong", "warning"),
    "angry_strong": ("angry", "strong", "warning"),
    "drag_start": ("drag",),
    "dragging": ("drag",),
    "drag_end": ("drag",),
    "nap": ("sleep", "paused"),
    "play": ("entertainment",),
    "sync_error": ("error",),
}


ACTION_FALLBACKS: dict[str, tuple[str, ...]] = {
    # Exact fallback examples from the mature action protocol.
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
    # Cultivation/menu protocol. These are intentionally linear, not recursive.
    "feed": ("happy", "idle_normal"),
    "eating": ("feed", "idle_normal"),
    "gift": ("happy", "idle_normal"),
    "play": ("excited", "happy", "idle_normal"),
    "hungry": ("sad", "idle_normal"),
    "want_attention": ("idle_bored", "idle_normal"),
    "menu_open": ("click", "idle_normal"),
}

# Complete coverage gives every standard action a stable path, while preserving
# the exact chains above verbatim.
for action in ACTION_CATEGORIES["idle"]:
    if action != "idle_normal":
        ACTION_FALLBACKS.setdefault(action, ("idle_normal",))
for action in ACTION_CATEGORIES["study"]:
    if action != "study_normal":
        ACTION_FALLBACKS.setdefault(action, ("study_normal", "idle_normal"))
for action in ("warning_soft", "warning_medium"):
    ACTION_FALLBACKS.setdefault(action, ("warning_soft", "idle_normal") if action != "warning_soft" else ("idle_normal",))
ACTION_FALLBACKS.update(
    {
        "angry_soft": ("warning_strong", "warning_soft", "idle_normal"),
        "stare": ("angry_strong", "warning_strong", "idle_normal"),
        "block_screen": ("stare", "warning_strong", "idle_normal"),
        "force_study": ("warning_strong", "warning_soft", "idle_normal"),
        "forgive": ("calm", "happy", "idle_normal"),
        "full": ("happy", "idle_normal"),
        "playing": ("play", "idle_normal"),
        "love": ("happy", "idle_normal"),
        "shy": ("happy", "idle_normal"),
        "spoiled": ("shy", "happy", "idle_normal"),
        "lonely": ("sad", "idle_normal"),
        "menu_hover": ("menu_open", "idle_normal"),
        "menu_select": ("click", "idle_normal"),
        "settings_open": ("menu_open", "idle_normal"),
    }
)
for action in ACTION_CATEGORIES["emotion"]:
    ACTION_FALLBACKS.setdefault(action, ("idle_normal",))
for action in ACTION_CATEGORIES["interaction"]:
    ACTION_FALLBACKS.setdefault(action, ("click", "idle_normal") if action != "click" else ("idle_normal",))
for action in ACTION_CATEGORIES["routine"]:
    ACTION_FALLBACKS.setdefault(action, ("idle_normal",))
for action in ACTION_CATEGORIES["system"]:
    ACTION_FALLBACKS.setdefault(action, ("warning_soft", "idle_normal"))
for action in ACTION_CATEGORIES["easter_egg"]:
    ACTION_FALLBACKS.setdefault(action, ("happy", "idle_normal"))

_ACTION_TO_CATEGORY: dict[str, str] = {}
for category, actions in ACTION_CATEGORIES.items():
    for action in actions:
        _ACTION_TO_CATEGORY[action] = category


def normalize_action(value: object) -> str:
    return "_".join(str(value or "").strip().lower().replace("-", " ").split())


def canonical_action(value: object) -> str:
    action = normalize_action(value)
    seen: set[str] = set()
    while action in ACTION_ALIASES and action not in seen:
        seen.add(action)
        action = ACTION_ALIASES[action]
    return action


def actions_for_category(category: object) -> tuple[str, ...]:
    return ACTION_CATEGORIES.get(normalize_action(category), ())


def get_action_category(action: object) -> str | None:
    return _ACTION_TO_CATEGORY.get(canonical_action(action))


action_category = get_action_category
category_actions = actions_for_category


@dataclass(frozen=True)
class ActionResolution:
    requested: str
    actual: str
    fallback_chain: tuple[str, ...]
    candidates: tuple[str, ...]

    @property
    def resolved(self) -> str:
        return self.actual

    @property
    def chain(self) -> tuple[str, ...]:
        return self.fallback_chain

    @property
    def used_fallback(self) -> bool:
        return self.actual != self.requested

    def as_dict(self) -> dict[str, object]:
        return {
            "requested": self.requested,
            "actual": self.actual,
            "fallback_chain": list(self.fallback_chain),
        }

    def __getitem__(self, key: str) -> object:
        return self.as_dict()[key]


def fallback_chain(requested: object) -> tuple[str, ...]:
    requested_name = normalize_action(requested) or "idle_normal"
    canonical = canonical_action(requested_name) or "idle_normal"
    chain = [requested_name]
    if canonical != requested_name:
        chain.append(canonical)
    chain.extend(ACTION_FALLBACKS.get(canonical, ("idle_normal",)))
    if "idle_normal" not in chain:
        chain.append("idle_normal")
    return tuple(dict.fromkeys(chain))


def resolve_action(
    available: Iterable[str] | Mapping[str, object] | None,
    requested: object,
) -> ActionResolution:
    requested_name = normalize_action(requested) or "idle_normal"
    names = available.keys() if isinstance(available, Mapping) else (available or ())
    supported = {normalize_action(action) for action in names if normalize_action(action)}
    candidates = fallback_chain(requested_name)
    attempted: list[str] = []
    actual = ""
    for candidate in candidates:
        attempted.append(candidate)
        if candidate in supported:
            actual = candidate
            break

    if not actual:
        for candidate in candidates:
            for legacy in LEGACY_ACTION_TARGETS.get(candidate, ()):
                if legacy in supported:
                    actual = legacy
                    break
            if actual:
                break

    if not actual:
        actual = "idle_normal"
        if "idle_normal" not in attempted:
            attempted.append("idle_normal")

    return ActionResolution(
        requested=requested_name,
        actual=actual,
        fallback_chain=tuple(attempted),
        candidates=candidates,
    )


__all__ = [
    "ACTION_ALIASES",
    "ACTION_CATEGORIES",
    "ACTION_FALLBACKS",
    "ALL_ACTIONS",
    "ALL_STANDARD_ACTIONS",
    "LEGACY_ACTION_TARGETS",
    "ActionResolution",
    "STANDARD_ACTIONS",
    "action_category",
    "actions_for_category",
    "canonical_action",
    "category_actions",
    "fallback_chain",
    "get_action_category",
    "normalize_action",
    "resolve_action",
]
