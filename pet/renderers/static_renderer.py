from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from .base import BaseRenderer


STATE_COLORS = {
    "idle": QColor("#2563eb"),
    "study": QColor("#16a34a"),
    "entertainment": QColor("#dc2626"),
    "warn": QColor("#f59e0b"),
    "strong": QColor("#ef4444"),
    "paused": QColor("#64748b"),
}


class StaticRenderer(BaseRenderer):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._pixmap = QPixmap()
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(96, 96)

    def set_character(self, character: Any) -> None:
        super().set_character(character)
        self._load_character_image()

    def set_state(self, state: str) -> str:
        resolved = super().set_state(state)
        self._load_character_image()
        return resolved

    def set_image(self, image: str | Path | QPixmap | None) -> None:
        if isinstance(image, QPixmap):
            self._pixmap = QPixmap(image)
        elif image:
            self._pixmap = QPixmap(str(image))
        else:
            self._pixmap = QPixmap()
        self.update()

    def _load_character_image(self) -> None:
        source = _state_source(self.character, self.state) or _character_skin(self.character)
        self.set_image(source)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self._pixmap.isNull():
            target = QRectF(self.rect()).adjusted(4, 4, -4, -4)
            size = self._pixmap.size()
            size.scale(target.size().toSize(), Qt.KeepAspectRatio)
            fitted = QRectF(0, 0, size.width(), size.height())
            fitted.moveCenter(target.center())
            painter.drawPixmap(fitted, self._pixmap, QRectF(self._pixmap.rect()))
        else:
            self._paint_fallback(painter)
        painter.end()

    def _paint_fallback(self, painter: QPainter) -> None:
        side = max(24.0, min(self.width(), self.height()) * 0.72)
        body = QRectF(0, 0, side, side)
        body.moveCenter(QRectF(self.rect()).center())
        color = STATE_COLORS.get(self.state, STATE_COLORS["idle"])

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 225))
        painter.drawEllipse(body.adjusted(-5, -5, 5, 5))
        painter.setBrush(color)
        painter.drawEllipse(body)

        eye_size = max(3.0, side * 0.08)
        eye_y = body.top() + side * 0.36
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QRectF(body.left() + side * 0.27, eye_y, eye_size, eye_size))
        painter.drawEllipse(QRectF(body.left() + side * 0.65, eye_y, eye_size, eye_size))

        mouth = QPainterPath()
        mouth.moveTo(body.left() + side * 0.35, body.top() + side * 0.66)
        mouth.quadTo(
            body.center().x(),
            body.top() + side * (0.78 if self.state != "strong" else 0.59),
            body.left() + side * 0.65,
            body.top() + side * 0.66,
        )
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("white"), max(2.0, side * 0.035)))
        painter.drawPath(mouth)


def _character_skin(character: Any) -> Path | str | None:
    if character is None:
        return None
    return getattr(character, "skin", None) or getattr(character, "asset", None)


def _state_spec(character: Any, state: str) -> Any:
    if character is None:
        return None
    getter = getattr(character, "state", None)
    if callable(getter):
        return getter(state)
    getter = getattr(character, "animation_for", None)
    if callable(getter):
        return getter(state)
    states = getattr(character, "states", None) or getattr(character, "animations", None) or {}
    return states.get(state) or states.get("idle")


def _state_source(character: Any, state: str) -> Path | str | None:
    spec = _state_spec(character, state)
    if spec is None:
        return None
    if isinstance(spec, (str, Path)):
        return spec
    return getattr(spec, "source", None) or getattr(spec, "asset", None)
