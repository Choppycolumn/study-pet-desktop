from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


def _number(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


@dataclass(frozen=True)
class RigPoint:
    x: float = 0.0
    y: float = 0.0

    @classmethod
    def from_value(cls, value: Any, fallback: "RigPoint | None" = None) -> "RigPoint":
        default = fallback or cls()
        if isinstance(value, Mapping):
            return cls(_number(value.get("x"), default.x), _number(value.get("y"), default.y))
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return cls(_number(value[0], default.x), _number(value[1], default.y))
        return default

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y}


@dataclass(frozen=True)
class RigBone:
    name: str
    parent: str | None = None
    position: RigPoint = field(default_factory=RigPoint)
    rotation: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    length: float = 0.0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], index: int = 0) -> "RigBone":
        position = RigPoint.from_value(
            data.get("position"),
            RigPoint(_number(data.get("x")), _number(data.get("y"))),
        )
        parent = _text(data.get("parent")) or None
        return cls(
            name=_text(data.get("name") or data.get("id"), f"bone_{index}"),
            parent=parent,
            position=position,
            rotation=_number(data.get("rotation")),
            scale_x=_number(data.get("scaleX", data.get("scale_x")), 1.0),
            scale_y=_number(data.get("scaleY", data.get("scale_y")), 1.0),
            length=max(0.0, _number(data.get("length"))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "parent": self.parent,
            "position": self.position.to_dict(),
            "rotation": self.rotation,
            "scaleX": self.scale_x,
            "scaleY": self.scale_y,
            "length": self.length,
        }


@dataclass(frozen=True)
class RigPart:
    name: str
    bone: str | None = None
    source: str | None = None
    position: RigPoint = field(default_factory=RigPoint)
    rotation: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    z_index: int = 0
    pivot: RigPoint = field(default_factory=lambda: RigPoint(0.5, 0.5))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], index: int = 0) -> "RigPart":
        position = RigPoint.from_value(
            data.get("position"),
            RigPoint(_number(data.get("x")), _number(data.get("y"))),
        )
        source = _text(data.get("source") or data.get("part") or data.get("image") or data.get("skin")) or None
        scale = data.get("scale") if isinstance(data.get("scale"), Mapping) else {}
        return cls(
            name=_text(data.get("name") or data.get("id"), f"part_{index}"),
            bone=_text(data.get("bone") or data.get("parent")) or None,
            source=source,
            position=position,
            rotation=_number(data.get("rotation")),
            scale_x=_number(data.get("scaleX", data.get("scale_x", scale.get("x"))), 1.0),
            scale_y=_number(data.get("scaleY", data.get("scale_y", scale.get("y"))), 1.0),
            z_index=int(_number(data.get("zIndex", data.get("z", data.get("layer"))), index)),
            pivot=RigPoint.from_value(data.get("pivot"), RigPoint(0.5, 0.5)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "bone": self.bone,
            "source": self.source,
            "position": self.position.to_dict(),
            "rotation": self.rotation,
            "scaleX": self.scale_x,
            "scaleY": self.scale_y,
            "zIndex": self.z_index,
            "pivot": self.pivot.to_dict(),
        }


@dataclass(frozen=True)
class Rig:
    width: float = 0.0
    height: float = 0.0
    origin: RigPoint = field(default_factory=lambda: RigPoint(0.5, 1.0))
    bones: tuple[RigBone, ...] = ()
    parts: tuple[RigPart, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "Rig":
        if not isinstance(data, Mapping):
            return cls()
        canvas = data.get("canvas") if isinstance(data.get("canvas"), Mapping) else {}
        raw_bones = data.get("bones") if isinstance(data.get("bones"), list) else []
        raw_parts = data.get("nodes", data.get("parts", data.get("slots")))
        if not isinstance(raw_parts, list):
            raw_parts = []
        bones = tuple(
            RigBone.from_dict(item, index)
            for index, item in enumerate(raw_bones)
            if isinstance(item, Mapping)
        )
        parts = tuple(
            RigPart.from_dict(item, index)
            for index, item in enumerate(raw_parts)
            if isinstance(item, Mapping)
        )
        metadata = data.get("metadata") if isinstance(data.get("metadata"), Mapping) else {}
        return cls(
            width=max(0.0, _number(data.get("width", canvas.get("width")))),
            height=max(0.0, _number(data.get("height", canvas.get("height")))),
            origin=RigPoint.from_value(data.get("origin", data.get("anchor", data.get("pivot"))), RigPoint(0.5, 1.0)),
            bones=bones,
            parts=parts,
            metadata=dict(metadata),
        )

    def bone(self, name: str) -> RigBone | None:
        return next((bone for bone in self.bones if bone.name == name), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "origin": self.origin.to_dict(),
            "bones": [bone.to_dict() for bone in self.bones],
            "parts": [part.to_dict() for part in self.parts],
            "metadata": dict(self.metadata),
        }


CharacterRig = Rig
