from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QMovie, QPixmap

from .characters import AnimationSpec, CharacterProfile


@dataclass
class RenderFrame:
    pixmap: QPixmap | None
    previous_pixmap: QPixmap | None
    transition: float
    scale: float
    bob_y: float
    shake_x: float
    tint: QColor | None


class CharacterAnimator(QObject):
    frame_changed = Signal()

    def __init__(self, profile: CharacterProfile, transition_ms: int = 240):
        super().__init__()
        self.profile = profile
        self.transition_ms = max(80, transition_ms)
        self.state = "idle"
        self.previous_state = "idle"
        self.phase = 0.0
        self._transition_started = time.monotonic()
        self._movies: dict[Path, QMovie] = {}
        self._pixmaps: dict[Path, QPixmap] = {}
        self._ensure_asset(self.profile.animation_for("idle").asset or self.profile.asset)

    def set_profile(self, profile: CharacterProfile) -> None:
        self._stop_movies()
        self.profile = profile
        self.previous_state = self.state
        self.state = "idle"
        self.phase = 0.0
        self._transition_started = time.monotonic()
        self._ensure_asset(self.profile.animation_for("idle").asset or self.profile.asset)
        self.frame_changed.emit()

    def set_state(self, state: str) -> None:
        normalized = str(state or "idle").strip().lower() or "idle"
        if normalized == self.state:
            return
        self.previous_state = self.state
        self.state = normalized
        self._transition_started = time.monotonic()
        self._ensure_asset(self._asset_for(self.previous_state))
        self._ensure_asset(self._asset_for(self.state))
        self.frame_changed.emit()

    def tick(self, delta_seconds: float) -> None:
        current = self.profile.animation_for(self.state)
        speed = max(0.35, min(2.5, current.fps / 12.0))
        self.phase = (self.phase + max(0.0, delta_seconds) * speed * math.tau) % (math.tau * 1000)
        self.frame_changed.emit()

    def render_frame(self) -> RenderFrame:
        previous = self.profile.animation_for(self.previous_state)
        current = self.profile.animation_for(self.state)
        transition = self._transition_value()
        spec = self._interpolate_spec(previous, current, transition)
        pulse = math.sin(self.phase)
        bob_y = pulse * spec.bob
        scale = spec.scale * (1.0 + math.sin(self.phase * 1.7) * spec.breath)
        shake_x = math.sin(self.phase * 7.0) * spec.shake
        return RenderFrame(
            pixmap=self._pixmap_for(self.state),
            previous_pixmap=self._pixmap_for(self.previous_state) if transition < 1.0 else None,
            transition=transition,
            scale=scale,
            bob_y=bob_y,
            shake_x=shake_x,
            tint=_parse_tint(spec.tint),
        )

    def _transition_value(self) -> float:
        elapsed_ms = (time.monotonic() - self._transition_started) * 1000
        raw = max(0.0, min(1.0, elapsed_ms / self.transition_ms))
        return raw * raw * (3.0 - 2.0 * raw)

    def _interpolate_spec(self, previous: AnimationSpec, current: AnimationSpec, amount: float) -> AnimationSpec:
        lerp = lambda left, right: left + (right - left) * amount
        return AnimationSpec(
            state=current.state,
            asset=current.asset,
            fps=round(lerp(previous.fps, current.fps)),
            loop=current.loop,
            scale=lerp(previous.scale, current.scale),
            bob=lerp(previous.bob, current.bob),
            breath=lerp(previous.breath, current.breath),
            shake=lerp(previous.shake, current.shake),
            tint=current.tint if amount >= 0.5 else previous.tint,
        )

    def _asset_for(self, state: str) -> Path | None:
        return self.profile.animation_for(state).asset or self.profile.asset

    def _ensure_asset(self, path: Path | None) -> None:
        if not path or path in self._movies or path in self._pixmaps:
            return
        suffix = path.suffix.lower()
        if suffix in {".gif", ".webp", ".mng"}:
            movie = QMovie(str(path))
            if movie.isValid():
                spec = self.profile.animation_for(self.state)
                movie.setSpeed(max(10, round(spec.fps / 12 * 100)))
                movie.frameChanged.connect(lambda _frame: self.frame_changed.emit())
                movie.start()
                self._movies[path] = movie
                return
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            self._pixmaps[path] = pixmap

    def _pixmap_for(self, state: str) -> QPixmap | None:
        path = self._asset_for(state)
        self._ensure_asset(path)
        if not path:
            return None
        movie = self._movies.get(path)
        if movie:
            frame = movie.currentPixmap()
            return frame if not frame.isNull() else None
        pixmap = self._pixmaps.get(path)
        return pixmap if pixmap and not pixmap.isNull() else None

    def _stop_movies(self) -> None:
        for movie in self._movies.values():
            movie.stop()
        self._movies.clear()
        self._pixmaps.clear()


def _parse_tint(value: str | None) -> QColor | None:
    text = str(value or "").strip()
    if len(text) == 9 and text.startswith("#"):
        try:
            red = int(text[1:3], 16)
            green = int(text[3:5], 16)
            blue = int(text[5:7], 16)
            alpha = int(text[7:9], 16)
            return QColor(red, green, blue, alpha)
        except ValueError:
            return None
    color = QColor(text)
    return color if text and color.isValid() else None
