from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QWidget

from .base import BaseRenderer
from .frame_sequence_renderer import FrameSequenceRenderer
from .sprite_sheet_renderer import SpriteSheetRenderer
from .static_renderer import StaticRenderer
from .webview_renderer import WebViewRenderer


_RENDERERS: dict[str, type[BaseRenderer]] = {
    "static": StaticRenderer,
    "frame_sequence": FrameSequenceRenderer,
    "sprite_sheet": SpriteSheetRenderer,
    "webview": WebViewRenderer,
    "webview_skin_rig": WebViewRenderer,
}


def register_renderer(name: str, renderer_class: type[BaseRenderer], *, replace: bool = False) -> None:
    key = str(name or "").strip().lower().replace("-", "_")
    if not key:
        raise ValueError("renderer name is required")
    if not issubclass(renderer_class, BaseRenderer):
        raise TypeError("renderer class must inherit BaseRenderer")
    if key in _RENDERERS and not replace:
        raise ValueError(f"renderer {key!r} is already registered")
    _RENDERERS[key] = renderer_class


def renderer_class(name: str) -> type[BaseRenderer]:
    key = str(name or "static").strip().lower().replace("-", "_")
    return _RENDERERS.get(key, StaticRenderer)


def create_renderer(character: Any, parent: QWidget | None = None) -> BaseRenderer:
    renderer = renderer_class(getattr(character, "renderer", "static"))(parent)
    renderer.set_character(character)
    return renderer
