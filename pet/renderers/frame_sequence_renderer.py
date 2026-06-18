from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from PySide6.QtCore import QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget

from .static_renderer import StaticRenderer, _state_spec, _state_source


class FrameSequenceRenderer(StaticRenderer):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._frames: list[QPixmap] = []
        self._frame_index = 0
        self._loop = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_frame)

    def set_character(self, character: Any) -> None:
        super().set_character(character)
        self._load_state_frames()

    def set_state(self, state: str) -> str:
        resolved = super().set_state(state)
        self._load_state_frames()
        return resolved

    def set_frames(
        self,
        frames: Iterable[str | Path | QPixmap],
        *,
        fps: float = 12.0,
        loop: bool = True,
    ) -> None:
        loaded: list[QPixmap] = []
        for frame in frames:
            pixmap = QPixmap(frame) if isinstance(frame, QPixmap) else QPixmap(str(frame))
            if not pixmap.isNull():
                loaded.append(pixmap)
        self._frames = loaded
        self._frame_index = 0
        self._loop = bool(loop)
        self._timer.stop()
        if loaded:
            self.set_image(loaded[0])
        if len(loaded) > 1:
            interval = max(8, round(1000.0 / max(0.1, min(120.0, float(fps)))))
            self._timer.start(interval)

    def shutdown(self) -> None:
        self._timer.stop()

    def _load_state_frames(self) -> None:
        spec = _state_spec(self.character, self.state)
        frames = getattr(spec, "frames", ()) if spec is not None else ()
        fps = getattr(spec, "fps", 12.0) if spec is not None else 12.0
        loop = getattr(spec, "loop", True) if spec is not None else True
        if not frames:
            source = _state_source(self.character, self.state)
            frames = (source,) if source else ()
        self.set_frames(frames, fps=fps, loop=loop)

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
