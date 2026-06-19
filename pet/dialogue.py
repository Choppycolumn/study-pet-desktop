from __future__ import annotations

import random as random_module
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any


BUBBLE_LINES: dict[str, tuple[str, ...]] = {
    "default": (
        "我在这里，慢慢来就好。",
        "今天也一起稳稳地向前走吧。",
        "需要我的时候，叫我一声就好。",
    ),
    "feed": (
        "好香，谢谢你！我补充好能量啦。",
        "吃饱啦，我会精神满满地陪着你。",
        "这一口正合心意，谢谢投喂！",
    ),
    "play": (
        "来活动一下吧，玩一会儿再继续努力。",
        "好耶，一起玩！休息好了更有精神。",
        "陪你玩一小会儿，快乐也要适量收藏。",
    ),
    "gift": (
        "这是给我的吗？我会好好珍惜！",
        "收到礼物啦，谢谢你惦记我。",
        "今天的惊喜被我接住啦！",
    ),
    "pet_head": (
        "摸摸收到，心情变好啦。",
        "嘿嘿，再轻轻摸一下也可以。",
        "你的手好暖，我会乖乖陪着你。",
    ),
    "study_together": (
        "好，我们一起专心学一会儿。",
        "我陪你开始，先完成眼前这一小步。",
        "并肩学习时间到，保持自己的节奏吧。",
    ),
    "check_progress": (
        "来看看进度，每一点积累都算数。",
        "已经走了这么远，接着完成下一步吧。",
        "先确认完成了什么，再决定接下来做什么。",
    ),
    "entertainment_timeout": (
        "休息时间有点久啦，回来完成一小段学习吧。",
        "娱乐先暂停一下，我们把注意力带回计划。",
        "该收心啦，先从五分钟的专注开始。",
    ),
    "status_view": (
        "状态已查看，我会继续陪着你。",
        "今天的状态一目了然，按自己的节奏继续吧。",
        "情况都在这里，挑一件最重要的事开始吧。",
    ),
}

DEFAULT_BUBBLE_LINES = BUBBLE_LINES

_ACTION_ALIASES = {
    "head_pet": "pet_head",
    "pethead": "pet_head",
    "touch_head": "pet_head",
    "摸头": "pet_head",
    "一起学习": "study_together",
    "陪伴学习": "study_together",
    "progress": "check_progress",
    "progress_check": "check_progress",
    "查看进度": "check_progress",
    "娱乐超时": "entertainment_timeout",
    "entertainment_overrun": "entertainment_timeout",
    "entertainment_limit": "entertainment_timeout",
    "timeout": "entertainment_timeout",
    "status": "status_view",
    "view_status": "status_view",
    "check_status": "status_view",
    "状态查看": "status_view",
    "查看状态": "status_view",
}

_SENSITIVE_TEXT = re.compile(
    r"(?:"
    r"api[_\s-]*token|access[_\s-]*token|refresh[_\s-]*token|"
    r"authorization|bearer\s+[a-z0-9._~+/=-]+|"
    r"password|passwd|client[_\s-]*secret|api[_\s-]*key|"
    r"密[码鑰钥]|口令|令牌|"
    r"\bsk-[a-z0-9_-]{8,}"
    r")",
    re.IGNORECASE,
)

RandomSource = Any


class DialogueAgent:
    """Select short pet bubbles without interpolating external or sensitive data."""

    def __init__(self, manifest: object | None = None, *, random: RandomSource = None):
        self._manifest = manifest
        self._random = random if random is not None else random_module

    def select(self, action: object, manifest: object | None = None) -> str:
        action_name = _normalize_action(action)
        custom_lines = _manifest_lines(self._manifest if manifest is None else manifest)
        candidates = (
            custom_lines.get(action_name)
            or BUBBLE_LINES.get(action_name)
            or custom_lines.get("default")
            or BUBBLE_LINES["default"]
        )
        return _choose(self._random, candidates)

    def line(self, action: object, manifest: object | None = None) -> str:
        return self.select(action, manifest)

    def get_line(self, action: object, manifest: object | None = None) -> str:
        return self.select(action, manifest)


def choose_bubble_line(
    action: object,
    manifest: object | None = None,
    *,
    random: RandomSource = None,
) -> str:
    return DialogueAgent(manifest, random=random).select(action)


def get_dialogue(
    action: object,
    manifest: object | None = None,
    *,
    random: RandomSource = None,
) -> str:
    return choose_bubble_line(action, manifest, random=random)


def _normalize_action(action: object) -> str:
    normalized = str(action or "default").strip().lower()
    normalized = re.sub(r"[-\s]+", "_", normalized).strip("_") or "default"
    return _ACTION_ALIASES.get(normalized, normalized)


def _manifest_lines(manifest: object | None) -> dict[str, tuple[str, ...]]:
    if manifest is None:
        return {}
    if isinstance(manifest, Mapping):
        raw = manifest.get("bubbleLines", manifest.get("bubble_lines"))
        if raw is None:
            raw = manifest
    else:
        raw = getattr(manifest, "bubble_lines", None)
        if raw is None:
            raw = getattr(manifest, "bubbleLines", None)
    if not isinstance(raw, Mapping):
        return {}

    result: dict[str, tuple[str, ...]] = {}
    for action, values in raw.items():
        key = _normalize_action(action)
        items = values if isinstance(values, (list, tuple)) else (values,)
        lines = tuple(
            text
            for item in items
            if isinstance(item, str)
            if (text := item.strip()) and not _SENSITIVE_TEXT.search(text)
        )
        if lines:
            result[key] = lines
    return result


def _choose(random_source: RandomSource, lines: Sequence[str]) -> str:
    chooser: Callable[[Sequence[str]], str] | None = getattr(random_source, "choice", None)
    if not callable(chooser) and callable(random_source):
        chooser = random_source
    if not callable(chooser):
        raise TypeError("random must be callable or provide choice()")
    selected = chooser(lines)
    if selected not in lines:
        raise ValueError("random source returned a value outside the dialogue pool")
    return selected


__all__ = [
    "BUBBLE_LINES",
    "DEFAULT_BUBBLE_LINES",
    "DialogueAgent",
    "choose_bubble_line",
    "get_dialogue",
]
