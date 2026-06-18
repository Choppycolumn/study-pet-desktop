from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .settings import APP_DIR, PetSettings


ANIMATION_STATES = ("idle", "study", "entertainment", "warn", "strong", "paused")

_STATE_DEFAULTS: dict[str, dict[str, object]] = {
    "idle": {"fps": 12, "loop": True, "scale": 1.0, "bob": 5.0, "breath": 0.025, "shake": 0.0, "tint": ""},
    "study": {"fps": 12, "loop": True, "scale": 1.0, "bob": 3.0, "breath": 0.018, "shake": 0.0, "tint": "#16a34a22"},
    "entertainment": {"fps": 12, "loop": True, "scale": 1.0, "bob": 6.0, "breath": 0.03, "shake": 1.0, "tint": "#f9731622"},
    "warn": {"fps": 16, "loop": True, "scale": 1.02, "bob": 7.0, "breath": 0.035, "shake": 3.0, "tint": "#f59e0b33"},
    "strong": {"fps": 18, "loop": True, "scale": 1.04, "bob": 5.0, "breath": 0.04, "shake": 6.0, "tint": "#ef444444"},
    "paused": {"fps": 8, "loop": True, "scale": 0.96, "bob": 1.5, "breath": 0.012, "shake": 0.0, "tint": "#64748b33"},
}


@dataclass
class AnimationSpec:
    state: str
    asset: Path | None = None
    fps: int = 12
    loop: bool = True
    scale: float = 1.0
    bob: float = 5.0
    breath: float = 0.025
    shake: float = 0.0
    tint: str | None = None


@dataclass
class CharacterProfile:
    character_id: str
    display_name: str
    tone: str = "gentle"
    asset: Path | None = None
    animations: dict[str, AnimationSpec] = field(default_factory=dict)
    bubble_lines: dict[str, list[str]] = field(default_factory=dict)
    notes: str = ""

    def line(self, mood: str, fallback: str) -> str:
        lines = self.bubble_lines.get(mood) or self.bubble_lines.get("default") or []
        return lines[0] if lines else fallback

    def animation_for(self, state: str) -> AnimationSpec:
        key = str(state or "idle").strip().lower()
        return self.animations.get(key) or self.animations.get("idle") or default_animation_spec(key)


class CharacterManager:
    def __init__(self, settings: PetSettings):
        self.settings = settings
        self.characters_dir = APP_DIR / "characters"

    def load(self) -> CharacterProfile:
        profiles = self.available_profiles()
        return profiles.get(self.settings.character_id) or profiles.get("catgirl") or self._fallback()

    def available_profiles(self) -> dict[str, CharacterProfile]:
        profiles: dict[str, CharacterProfile] = {}
        if not self.characters_dir.exists():
            return profiles
        for manifest in self.characters_dir.glob("*/character.json"):
            try:
                profile = self._read_manifest(manifest)
                profiles[profile.character_id] = profile
            except Exception:
                continue
        return profiles

    def _read_manifest(self, manifest: Path) -> CharacterProfile:
        data: dict[str, Any] = json.loads(manifest.read_text(encoding="utf-8"))
        character_id = str(data.get("id") or manifest.parent.name)
        asset = _resolve_asset(manifest.parent, data.get("asset"))
        animations = self._read_animations(manifest.parent, data.get("animations"))
        for state in ANIMATION_STATES:
            animations.setdefault(state, default_animation_spec(state))
        bubble_lines = data.get("bubbleLines") if isinstance(data.get("bubbleLines"), dict) else {}
        normalized_lines = {
            str(key): [str(item) for item in value if str(item).strip()]
            for key, value in bubble_lines.items()
            if isinstance(value, list)
        }
        return CharacterProfile(
            character_id=character_id,
            display_name=str(data.get("displayName") or character_id),
            tone=str(data.get("tone") or "gentle"),
            asset=asset,
            animations=animations,
            bubble_lines=normalized_lines,
            notes=str(data.get("notes") or ""),
        )

    def _read_animations(self, base_dir: Path, raw: Any) -> dict[str, AnimationSpec]:
        if not isinstance(raw, dict):
            return {}
        specs: dict[str, AnimationSpec] = {}
        for state, value in raw.items():
            if not isinstance(value, dict):
                continue
            state_name = str(state or "").strip().lower()
            if not state_name:
                continue
            defaults = _state_defaults(state_name)
            asset = _resolve_asset(base_dir, value.get("asset"))
            try:
                fps = max(1, min(60, int(value.get("fps", defaults["fps"]))))
            except (TypeError, ValueError):
                fps = int(defaults["fps"])
            specs[state_name] = AnimationSpec(
                state=state_name,
                asset=asset,
                fps=fps,
                loop=_bool(value.get("loop"), bool(defaults["loop"])),
                scale=_float(value.get("scale"), float(defaults["scale"]), 0.2, 3.0),
                bob=_float(value.get("bob"), float(defaults["bob"]), 0.0, 40.0),
                breath=_float(value.get("breath"), float(defaults["breath"]), 0.0, 0.25),
                shake=_float(value.get("shake"), float(defaults["shake"]), 0.0, 30.0),
                tint=_text(value.get("tint"), str(defaults["tint"] or "")),
            )
        return specs

    def _fallback(self) -> CharacterProfile:
        return CharacterProfile(
            character_id="fallback",
            display_name="桌宠",
            bubble_lines={"default": ["我在这里，先从下一分钟开始。"]},
        )


def default_animation_spec(state: str) -> AnimationSpec:
    state_name = str(state or "idle").strip().lower() or "idle"
    defaults = _state_defaults(state_name)
    return AnimationSpec(
        state=state_name,
        fps=int(defaults["fps"]),
        loop=bool(defaults["loop"]),
        scale=float(defaults["scale"]),
        bob=float(defaults["bob"]),
        breath=float(defaults["breath"]),
        shake=float(defaults["shake"]),
        tint=str(defaults["tint"] or "") or None,
    )


def _state_defaults(state: str) -> dict[str, object]:
    return _STATE_DEFAULTS.get(state, _STATE_DEFAULTS["idle"])


def _resolve_asset(base_dir: Path, raw: Any) -> Path | None:
    asset_name = str(raw or "").strip()
    if not asset_name:
        return None
    path = Path(asset_name).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    path = path.resolve()
    return path if path.exists() and path.is_file() else None


def _bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    if value is None:
        return fallback
    return bool(value)


def _float(value: Any, fallback: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, parsed))


def _text(value: Any, fallback: str = "") -> str | None:
    if value is None:
        value = fallback
    text = str(value).strip()
    return text or None
