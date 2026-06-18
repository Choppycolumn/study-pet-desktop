from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..webview_bridge import WebViewBridge
from ..settings import RESOURCE_DIR
from .base import BaseRenderer, RendererUnavailableError


try:
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineCore import QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView

    _WEBENGINE_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - depends on the optional Qt component
    QWebChannel = None  # type: ignore[assignment]
    QWebEngineSettings = None  # type: ignore[assignment]
    QWebEngineView = None  # type: ignore[assignment]
    _WEBENGINE_IMPORT_ERROR = exc


class WebEngineUnavailableError(RendererUnavailableError):
    """Raised when Qt WebEngine cannot be imported or initialized."""


class WebViewRenderer(BaseRenderer):
    renderer_failed = Signal(str)
    renderer_ready = Signal(object)
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        index_path: str | Path | None = None,
        bridge: WebViewBridge | None = None,
    ):
        if QWebEngineView is None or QWebChannel is None or QWebEngineSettings is None:
            detail = f": {_WEBENGINE_IMPORT_ERROR}" if _WEBENGINE_IMPORT_ERROR else ""
            raise WebEngineUnavailableError(f"PySide6 QtWebEngine is unavailable{detail}")
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.bridge = bridge or WebViewBridge(self)
        self.web_view: Any = None
        self.channel: Any = None

        try:
            self.web_view = QWebEngineView(self)
            self.web_view.setAttribute(Qt.WA_TranslucentBackground, True)
            self.web_view.setStyleSheet("background: transparent;")
            self.web_view.page().setBackgroundColor(Qt.transparent)
            settings = self.web_view.settings()
            attribute = QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls
            settings.setAttribute(attribute, True)

            self.channel = QWebChannel(self.web_view.page())
            self.channel.registerObject("bridge", self.bridge)
            self.web_view.page().setWebChannel(self.channel)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addWidget(self.web_view)

            path = Path(index_path) if index_path else RESOURCE_DIR / "webview" / "index.html"
            path = path.expanduser().resolve()
            if not path.is_file():
                raise FileNotFoundError(f"WebView entry point does not exist: {path}")
            self.index_path = path
            self.web_view.loadFinished.connect(self._load_finished)
            self.bridge.event_received.connect(self._bridge_event)
            self.web_view.load(QUrl.fromLocalFile(str(path)))
        except Exception as exc:
            if self.web_view is not None:
                self.web_view.deleteLater()
            raise WebEngineUnavailableError(f"Qt WebEngine could not be initialized: {exc}") from exc

    @property
    def view(self) -> Any:
        return self.web_view

    def set_character(self, character: Any) -> None:
        super().set_character(character)
        self.bridge.set_character(_character_payload(character))
        self.bridge.set_state(self.state)

    def set_state(self, state: str, payload: Mapping[str, Any] | None = None) -> str:
        resolved = super().set_state(state)
        self.bridge.set_state(resolved, payload)
        return resolved

    def shutdown(self) -> None:
        if self.web_view is not None:
            self.web_view.stop()
            self.web_view.page().setWebChannel(None)
            self.web_view.close()

    def _load_finished(self, ok: bool) -> None:
        if not ok:
            self.renderer_failed.emit("WebView HTML failed to load")

    def _bridge_event(self, name: str, payload: Mapping[str, Any]) -> None:
        if name == "renderer-error":
            self.renderer_failed.emit(str(payload.get("message") or "WebView renderer error"))
        elif name == "renderer-ready":
            self.renderer_ready.emit(dict(payload))


def _character_payload(character: Any) -> dict[str, Any]:
    if character is None:
        return {}
    serializer = getattr(character, "to_web_payload", None)
    if callable(serializer):
        return dict(serializer())

    character_id = getattr(character, "character_id", None) or getattr(character, "id", "character")
    display_name = getattr(character, "display_name", None) or getattr(character, "name", character_id)
    skin = getattr(character, "skin", None) or getattr(character, "asset", None)
    states = getattr(character, "states", None) or getattr(character, "animations", None) or {}
    return {
        "id": str(character_id),
        "displayName": str(display_name),
        "skin": _url(skin),
        "states": {str(name): _state_payload(spec) for name, spec in states.items()},
    }


def _state_payload(spec: Any) -> dict[str, Any]:
    if isinstance(spec, Mapping):
        data = dict(spec)
        source = data.get("source", data.get("asset"))
        data["source"] = _url(source)
        return _json_safe(data)
    source = getattr(spec, "source", None) or getattr(spec, "asset", None)
    frames = getattr(spec, "frames", ())
    return {
        "source": _url(source),
        "frames": [_url(frame) for frame in frames],
        "fps": float(getattr(spec, "fps", 12.0)),
        "loop": bool(getattr(spec, "loop", True)),
    }


def _url(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value.resolve().as_uri()
    text = str(value).strip()
    if not text:
        return None
    path = Path(text).expanduser()
    return path.resolve().as_uri() if path.exists() else text


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return value.resolve().as_uri()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
