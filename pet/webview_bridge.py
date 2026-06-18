from __future__ import annotations

from typing import Any, Mapping

from PySide6.QtCore import QObject, Signal, Slot


class WebViewBridge(QObject):
    stateChanged = Signal(str, "QVariantMap")
    characterChanged = Signal("QVariantMap")
    readyChanged = Signal(bool)
    eventReceived = Signal(str, "QVariantMap")

    state_changed = Signal(str, object)
    character_changed = Signal(object)
    ready_changed = Signal(bool)
    event_received = Signal(str, object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._state = "idle"
        self._state_payload: dict[str, Any] = {}
        self._character: dict[str, Any] = {}
        self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    def set_state(self, state: str, payload: Mapping[str, Any] | None = None) -> None:
        self._state = str(state or "idle").strip().lower() or "idle"
        self._state_payload = dict(payload or {})
        self.stateChanged.emit(self._state, self._state_payload)
        self.state_changed.emit(self._state, self._state_payload)

    def set_character(self, character: Mapping[str, Any] | None) -> None:
        self._character = dict(character or {})
        self.characterChanged.emit(self._character)
        self.character_changed.emit(self._character)

    @Slot(result="QVariantMap")
    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self._state,
            "statePayload": dict(self._state_payload),
            "character": dict(self._character),
        }

    @Slot()
    def ready(self) -> None:
        if not self._ready:
            self._ready = True
            self.readyChanged.emit(True)
            self.ready_changed.emit(True)

    @Slot(str, "QVariantMap")
    def sendEvent(self, name: str, payload: Mapping[str, Any] | None = None) -> None:
        normalized = str(name or "").strip()
        data = dict(payload or {})
        self.eventReceived.emit(normalized, data)
        self.event_received.emit(normalized, data)

    @Slot(str, "QVariantMap")
    def send_event(self, name: str, payload: Mapping[str, Any] | None = None) -> None:
        self.sendEvent(name, payload)


Bridge = WebViewBridge
