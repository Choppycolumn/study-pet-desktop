from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import struct
from typing import Any, Mapping
import warnings as python_warnings

from .rig import Rig


RECOMMENDED_MAX_SKIN_SIZE = 4096
MAX_SKIN_SIZE = RECOMMENDED_MAX_SKIN_SIZE
DEFAULT_STATES = ("idle", "study", "entertainment", "warning", "angry", "sleep")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


class CharacterPackageWarning(UserWarning):
    pass


@dataclass(frozen=True)
class CharacterState:
    name: str
    source: Path | None = None
    frames: tuple[Path, ...] = ()
    fps: float = 12.0
    loop: bool = True
    frame_width: int = 0
    frame_height: int = 0
    columns: int = 0
    rows: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": str(self.source) if self.source else None,
            "frames": [str(frame) for frame in self.frames],
            "fps": self.fps,
            "loop": self.loop,
            "frameWidth": self.frame_width,
            "frameHeight": self.frame_height,
            "columns": self.columns,
            "rows": self.rows,
            **dict(self.metadata),
        }


@dataclass(frozen=True)
class CharacterPackage:
    character_id: str
    display_name: str
    root: Path
    renderer: str = "static"
    skin: Path | None = None
    preview: Path | None = None
    manifest: Path | None = None
    atlas: Path | None = None
    rig_path: Path | None = None
    animations_path: Path | None = None
    states: Mapping[str, CharacterState] = field(default_factory=dict)
    state_map: Mapping[str, str] = field(default_factory=dict)
    rig: Rig = field(default_factory=Rig)
    bubble_lines: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    version: str | int | float | None = None
    author: str = ""
    description: str = ""
    tags: tuple[str, ...] = ()
    supported_states: tuple[str, ...] = ()
    fallback_profile: Any = None

    @property
    def id(self) -> str:
        return self.character_id

    @property
    def name(self) -> str:
        return self.display_name

    @property
    def asset(self) -> Path | None:
        return self.preview or self.skin

    @property
    def display_metadata(self) -> dict[str, Any]:
        """Return manifest metadata in a stable, UI-friendly shape."""
        return {
            **dict(self.metadata),
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "tags": list(self.tags),
            "supportedStates": list(self.supported_states),
            "fallbackProfile": self.fallback_profile,
        }

    def metadata_summary(self) -> dict[str, Any]:
        return self.display_metadata

    def line(self, state: str, fallback: str) -> str:
        lines = self.bubble_lines.get(str(state or "default").strip().lower())
        return lines[0] if lines else fallback

    def state(self, name: str) -> CharacterState:
        normalized = str(name or "idle").strip().lower() or "idle"
        mapped = self.state_map.get(normalized, normalized)
        return (
            self.states.get(mapped)
            or self.states.get(normalized)
            or self.states.get("idle")
            or CharacterState(normalized, source=self.skin)
        )

    def animation_for(self, name: str) -> CharacterState:
        return self.state(name)

    def to_web_payload(self) -> dict[str, Any]:
        return {
            "id": self.character_id,
            "displayName": self.display_name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "tags": list(self.tags),
            "supportedStates": list(self.supported_states),
            "fallbackProfile": self.fallback_profile,
            "renderer": self.renderer,
            "packageUrl": _path_url(self.manifest or self.root),
            "manifestUrl": _path_url(self.manifest),
            "skin": _path_url(self.skin),
            "preview": _path_url(self.preview),
            "atlas": _path_url(self.atlas),
            "rigUrl": _path_url(self.rig_path),
            "animationsUrl": _path_url(self.animations_path),
            "states": {
                name: {
                    **state.to_dict(),
                    "source": _path_url(state.source),
                    "frames": [_path_url(frame) for frame in state.frames],
                }
                for name, state in self.states.items()
            },
            "stateMap": dict(self.state_map),
            "rig": self.rig.to_dict(),
            "metadata": self.display_metadata,
        }


class CharacterPackageLoader:
    def __init__(self, *, emit_warnings: bool = True):
        self.emit_warnings = emit_warnings
        self._messages: list[str] = []

    def load(self, package: str | Path) -> CharacterPackage:
        self._messages = []
        requested = Path(package).expanduser()
        looks_like_manifest = requested.name.lower() == "character.json" or requested.suffix.lower() == ".json"
        manifest = requested if looks_like_manifest else requested / "character.json"
        root = requested.parent if looks_like_manifest else requested
        data: Mapping[str, Any] = {}
        try:
            parsed = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(parsed, Mapping):
                data = parsed
            else:
                self._warn(f"{manifest}: manifest root must be an object; defaults were used")
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            self._warn(f"{manifest}: could not read character package ({exc}); defaults were used")

        fallback_id = root.name or "character"
        character_id = self._required_text(data, ("id", "characterId"), fallback_id, "id")
        display_name = self._required_text(
            data, ("displayName", "name"), character_id, "displayName"
        )
        version = self._version(data.get("version"))
        author = self._optional_text(data.get("author"))
        description = self._optional_text(data.get("description"))
        tags = self._string_tuple(data.get("tags"), "tags")
        renderer = self._renderer(data)
        skin = self._skin(root, data)
        preview = self._resolve_file(root, data.get("preview"), "preview", warn_missing=False)
        atlas = self._resolve_file(root, data.get("atlas"), "atlas")
        rig_path, rig = self._rig(root, data.get("rig"))
        animations_path, animation_names = self._animation_file(root, data.get("animations"))
        states = self._states(root, data, skin, animation_names)
        raw_map = data.get("stateMap", data.get("state_map"))
        state_map = {
            str(key).strip().lower(): str(value).strip().lower()
            for key, value in raw_map.items()
            if str(key).strip() and str(value).strip()
        } if isinstance(raw_map, Mapping) else {}
        metadata = data.get("metadata") if isinstance(data.get("metadata"), Mapping) else {}
        bubble_lines = self._bubble_lines(data.get("bubbleLines", data.get("bubble_lines")))
        raw_supported_states = data.get("supportedStates", data.get("supported_states"))
        supported_states = self._string_tuple(
            raw_supported_states, "supportedStates", normalize=True
        ) if raw_supported_states is not None else tuple(states)
        fallback_profile = data.get("fallbackProfile", data.get("fallback_profile"))
        if fallback_profile is not None and not isinstance(
            fallback_profile, (str, int, float, bool, Mapping, list, tuple)
        ):
            self._warn("fallbackProfile must be a JSON value; it was ignored")
            fallback_profile = None
        elif isinstance(fallback_profile, Mapping):
            fallback_profile = dict(fallback_profile)
        elif isinstance(fallback_profile, (list, tuple)):
            fallback_profile = list(fallback_profile)
        if renderer in {"webview", "webview_skin_rig"}:
            for label, path in (("skin", skin), ("atlas", atlas), ("rig", rig_path), ("animations", animations_path)):
                if path is None:
                    self._warn(f"webview character package is missing a usable {label} resource")
        return CharacterPackage(
            character_id=character_id,
            display_name=display_name,
            root=root.resolve(),
            version=version,
            author=author,
            description=description,
            tags=tags,
            supported_states=supported_states,
            fallback_profile=fallback_profile,
            renderer=renderer,
            skin=skin,
            preview=preview,
            manifest=manifest.resolve(),
            atlas=atlas,
            rig_path=rig_path,
            animations_path=animations_path,
            states=states,
            state_map=state_map,
            rig=rig,
            bubble_lines=bubble_lines,
            metadata=dict(metadata),
            warnings=tuple(self._messages),
        )

    def _version(self, raw: Any) -> str | int | float | None:
        if raw is None:
            return None
        if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
            self._warn("version must be a string or number; it was ignored")
            return None
        if isinstance(raw, str):
            return raw.strip() or None
        return raw

    @staticmethod
    def _optional_text(raw: Any) -> str:
        return str(raw).strip() if raw is not None else ""

    def _string_tuple(
        self,
        raw: Any,
        label: str,
        *,
        normalize: bool = False,
    ) -> tuple[str, ...]:
        if raw is None:
            return ()
        if isinstance(raw, str):
            values = [raw]
        elif isinstance(raw, (list, tuple, set)):
            values = raw
        else:
            self._warn(f"{label} must be a string or array; it was ignored")
            return ()
        result: list[str] = []
        for value in values:
            text = str(value).strip()
            if normalize:
                text = text.lower()
            if text and text not in result:
                result.append(text)
        return tuple(result)

    def _warn(self, message: str) -> None:
        self._messages.append(message)
        if self.emit_warnings:
            python_warnings.warn(message, CharacterPackageWarning, stacklevel=3)

    def _required_text(
        self,
        data: Mapping[str, Any],
        keys: tuple[str, ...],
        fallback: str,
        label: str,
    ) -> str:
        for key in keys:
            value = str(data.get(key) or "").strip()
            if value:
                return value
        self._warn(f"character package is missing {label}; using {fallback!r}")
        return fallback

    def _renderer(self, data: Mapping[str, Any]) -> str:
        if "renderer" not in data and "type" not in data:
            self._warn("character package is missing renderer; using 'static'")
        raw = data.get("renderer", data.get("type", "static"))
        if isinstance(raw, Mapping):
            raw = raw.get("type", raw.get("name", "static"))
        renderer = str(raw or "static").strip().lower().replace("-", "_")
        aliases = {"frames": "frame_sequence", "spritesheet": "sprite_sheet", "web": "webview"}
        return aliases.get(renderer, renderer or "static")

    def _skin(self, root: Path, data: Mapping[str, Any]) -> Path | None:
        raw = data.get("skin", data.get("asset"))
        if isinstance(raw, Mapping):
            raw = raw.get("source", raw.get("path", raw.get("file")))
        skin = self._resolve_file(root, raw, "skin")
        if skin is None:
            self._warn("character package has no usable skin; renderer fallback will be used")
            return None
        size = _image_size(skin)
        if size and max(size) > RECOMMENDED_MAX_SKIN_SIZE:
            self._warn(
                f"skin {skin.name} is {size[0]}x{size[1]}; the recommended maximum is "
                f"{RECOMMENDED_MAX_SKIN_SIZE}px per side"
            )
        return skin

    def _rig(self, root: Path, raw: Any) -> tuple[Path | None, Rig]:
        path: Path | None = None
        if isinstance(raw, str):
            path = self._resolve_file(root, raw, "rig")
            if path is None:
                return None, Rig()
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                self._warn(f"rig {path}: could not be read ({exc}); empty rig was used")
                return path, Rig()
        if raw is None:
            return path, Rig()
        if not isinstance(raw, Mapping):
            self._warn("rig must be an object or JSON file path; empty rig was used")
            return path, Rig()
        return path, Rig.from_dict(raw)

    def _animation_file(self, root: Path, raw: Any) -> tuple[Path | None, tuple[str, ...]]:
        if not isinstance(raw, str):
            return None, ()
        path = self._resolve_file(root, raw, "animations")
        if path is None:
            return None, ()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            self._warn(f"animations {path}: could not be read ({exc})")
            return path, ()
        if not isinstance(data, Mapping):
            self._warn(f"animations {path}: root must be an object")
            return path, ()
        clips = data.get("clips", data.get("animations", data.get("states")))
        if not isinstance(clips, Mapping):
            self._warn(f"animations {path}: no clips object was found")
            return path, ()
        return path, tuple(str(name).strip().lower() for name in clips if str(name).strip())

    def _states(
        self,
        root: Path,
        data: Mapping[str, Any],
        skin: Path | None,
        animation_names: tuple[str, ...] = (),
    ) -> dict[str, CharacterState]:
        raw_states = data.get("states", data.get("animations"))
        if not isinstance(raw_states, Mapping):
            raw_states = {}
        states: dict[str, CharacterState] = {}
        for raw_name, raw_spec in raw_states.items():
            name = str(raw_name or "").strip().lower()
            if not name:
                self._warn("a state with an empty name was ignored")
                continue
            states[name] = self._state(root, name, raw_spec, skin)
        for name in animation_names:
            states.setdefault(name, CharacterState(name=name, source=skin))
        if states:
            states.setdefault("idle", CharacterState(name="idle", source=skin))
        else:
            for name in DEFAULT_STATES:
                states[name] = CharacterState(name=name, source=skin)
        return states

    @staticmethod
    def _bubble_lines(raw: Any) -> dict[str, tuple[str, ...]]:
        if not isinstance(raw, Mapping):
            return {}
        result: dict[str, tuple[str, ...]] = {}
        for key, value in raw.items():
            items = value if isinstance(value, list) else [value]
            lines = tuple(str(item).strip() for item in items if str(item).strip())
            if lines:
                result[str(key).strip().lower()] = lines
        return result

    def _state(self, root: Path, name: str, raw: Any, skin: Path | None) -> CharacterState:
        if isinstance(raw, str):
            raw = {"source": raw}
        if not isinstance(raw, Mapping):
            self._warn(f"state {name!r} must be an object; defaults were used")
            raw = {}
        source = self._resolve_file(
            root,
            raw.get("source", raw.get("asset", raw.get("sheet", raw.get("image")))),
            f"state {name} source",
            warn_missing=False,
        ) or skin
        frames: list[Path] = []
        raw_frames = raw.get("frames")
        if isinstance(raw_frames, list):
            for frame in raw_frames:
                path = self._resolve_file(root, frame, f"state {name} frame", warn_missing=False)
                if path:
                    frames.append(path)
        elif source and source.is_dir():
            frames = sorted(path for path in source.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)
            source = frames[0] if frames else skin
        frame_size = raw.get("frameSize")
        width = _positive_int(raw.get("frameWidth"))
        height = _positive_int(raw.get("frameHeight"))
        if isinstance(frame_size, (list, tuple)) and len(frame_size) >= 2:
            width, height = _positive_int(frame_size[0]), _positive_int(frame_size[1])
        elif isinstance(frame_size, Mapping):
            width = _positive_int(frame_size.get("width"))
            height = _positive_int(frame_size.get("height"))
        known = {
            "source", "asset", "sheet", "image", "frames", "fps", "loop",
            "frameSize", "frameWidth", "frameHeight", "columns", "rows",
        }
        return CharacterState(
            name=name,
            source=source,
            frames=tuple(frames),
            fps=_bounded_float(raw.get("fps"), 12.0, 0.1, 120.0),
            loop=_boolean(raw.get("loop"), True),
            frame_width=width,
            frame_height=height,
            columns=_positive_int(raw.get("columns")),
            rows=_positive_int(raw.get("rows")),
            metadata={key: value for key, value in raw.items() if key not in known},
        )

    def _resolve_file(
        self,
        root: Path,
        raw: Any,
        label: str,
        *,
        warn_missing: bool = True,
    ) -> Path | None:
        text = str(raw or "").strip()
        if not text:
            return None
        path = Path(text).expanduser()
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
        if not path.exists():
            if warn_missing:
                self._warn(f"{label} does not exist: {path}")
            return None
        return path


CharacterLoader = CharacterPackageLoader
Character = CharacterPackage


def load_character_package(package: str | Path, *, emit_warnings: bool = True) -> CharacterPackage:
    return CharacterPackageLoader(emit_warnings=emit_warnings).load(package)


def load_character(package: str | Path, *, emit_warnings: bool = True) -> CharacterPackage:
    return load_character_package(package, emit_warnings=emit_warnings)


def validate_character_package(package: str | Path) -> tuple[str, ...]:
    return load_character_package(package, emit_warnings=False).warnings


def _path_url(path: Path | None) -> str | None:
    return path.resolve().as_uri() if path else None


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _bounded_float(value: Any, fallback: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, parsed))


def _boolean(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "on", "1"}:
            return True
        if normalized in {"false", "no", "off", "0"}:
            return False
    return fallback if value is None else bool(value)


def _image_size(path: Path) -> tuple[int, int] | None:
    try:
        from PySide6.QtGui import QImageReader

        size = QImageReader(str(path)).size()
        if size.isValid():
            return size.width(), size.height()
    except (ImportError, RuntimeError):
        pass
    if path.suffix.lower() == ".png":
        try:
            with path.open("rb") as stream:
                header = stream.read(24)
            if header[:8] == b"\x89PNG\r\n\x1a\n" and len(header) == 24:
                return struct.unpack(">II", header[16:24])
        except OSError:
            return None
    return None
