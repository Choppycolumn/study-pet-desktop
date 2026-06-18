from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget

from .static_renderer import StaticRenderer, _state_spec, _state_source


class SpriteSheetRenderer(StaticRenderer):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._sheet = QPixmap()
        self._frames: list[QPixmap] = []
        self._frame_index = 0
        self._loop = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_frame)

    def set_character(self, character: Any) -> None:
        super().set_character(character)
        self._load_state_sheet()

    def set_state(self, state: str) -> str:
        resolved = super().set_state(state)
        self._load_state_sheet()
        return resolved

    def set_sprite_sheet(
        self,
        source: str | Path | QPixmap | None,
        *,
        frame_width: int = 0,
        frame_height: int = 0,
        columns: int = 0,
        rows: int = 0,
        fps: float = 12.0,
        loop: bool = True,
    ) -> None:
        self._sheet = QPixmap(source) if isinstance(source, QPixmap) else QPixmap(str(source or ""))
        self._frames = []
        self._timer.stop()
        if self._sheet.isNull():
            self.update()
            return

        columns = max(0, int(columns))
        rows = max(0, int(rows))
        frame_width = max(0, int(frame_width))
        frame_height = max(0, int(frame_height))
        if not frame_width and columns:
            frame_width = self._sheet.width() // columns
        if not frame_height and rows:
            frame_height = self._sheet.height() // rows
        if not frame_width:
            frame_width = self._sheet.width()
        if not frame_height:
            frame_height = self._sheet.height()
        columns = columns or max(1, self._sheet.width() // frame_width)
        rows = rows or max(1, self._sheet.height() // frame_height)

        for row in range(rows):
            for column in range(columns):
                x, y = column * frame_width, row * frame_height
                if x + frame_width <= self._sheet.width() and y + frame_height <= self._sheet.height():
                    self._frames.append(self._sheet.copy(x, y, frame_width, frame_height))
        self._frame_index = 0
        self._loop = bool(loop)
        if self._frames:
            self.set_image(self._frames[0])
        if len(self._frames) > 1:
            interval = max(8, round(1000.0 / max(0.1, min(120.0, float(fps)))))
            self._timer.start(interval)

    def shutdown(self) -> None:
        self._timer.stop()

    def _load_state_sheet(self) -> None:
        spec = _state_spec(self.character, self.state)
        self.set_sprite_sheet(
            _state_source(self.character, self.state),
            frame_width=getattr(spec, "frame_width", 0),
            frame_height=getattr(spec, "frame_height", 0),
            columns=getattr(spec, "columns", 0),
            rows=getattr(spec, "rows", 0),
            fps=getattr(spec, "fps", 12.0),
            loop=getattr(spec, "loop", True),
        )

    def _next_frame(self) -> None:
        if len(self._frames) < 2:
            self._timer.stop()
            return
        next_index = self._frame_index + 1
        if next_index >= len(self._frames):
            if not self._loop:
                self._timer.stop()
                return
            next_index = 0
        self._frame_index = next_index
        self.set_image(self._frames[self._frame_index])
