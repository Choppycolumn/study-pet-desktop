from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from ..state_machine import StateMachine


class RendererError(RuntimeError):
    """Base error raised by desktop-pet renderers."""


class RendererUnavailableError(RendererError):
    """Raised when an optional renderer backend is not installed."""


class BaseRenderer(QWidget):
    state_changed = Signal(str)
    character_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._character: Any = None
        self._state_machine = StateMachine()

    @property
    def character(self) -> Any:
        return self._character

    @property
    def state(self) -> str:
        return self._state_machine.state

    def set_character(self, character: Any) -> None:
        self._character = character
        states = getattr(character, "states", None) or getattr(character, "animations", None) or {}
        state_map = getattr(character, "state_map", None) or {}
        self._state_machine.configure(states, state_map)
        self.character_changed.emit(character)
        self.update()

    def set_state(self, state: str) -> str:
        previous = self.state
        resolved = self._state_machine.set_state(state)
        if resolved != previous:
            self.state_changed.emit(resolved)
            self.update()
        return resolved

    def shutdown(self) -> None:
        """Release backend resources before the widget is destroyed."""


Renderer = BaseRenderer
