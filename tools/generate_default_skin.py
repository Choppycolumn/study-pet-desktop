#!/usr/bin/env python3
"""Generate the procedural RGBA skin atlas for the bundled default pet."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import struct
import zlib


Color = tuple[int, int, int, int]
Point = tuple[float, float]

REQUIRED_SPRITES = {
    "head",
    "face_base",
    "hair_back",
    "hair_front",
    "torso",
    "left_upper_arm",
    "left_lower_arm",
    "left_hand",
    "right_upper_arm",
    "right_lower_arm",
    "right_hand",
    "left_upper_leg",
    "left_lower_leg",
    "left_foot",
    "right_upper_leg",
    "right_lower_leg",
    "right_foot",
    "eyes_open",
    "eyes_closed",
    "mouth_normal",
    "mouth_smile",
    "mouth_angry",
    "mouth_sleep",
    "prop_book",
    "prop_laptop",
    "effect_warning",
    "effect_heart",
}

INK = (43, 50, 65, 255)
HAIR = (45, 59, 86, 255)
HAIR_LIGHT = (76, 96, 132, 255)
SKIN = (255, 220, 193, 255)
SKIN_SHADOW = (239, 178, 157, 255)
TEAL = (51, 163, 155, 255)
TEAL_DARK = (34, 112, 113, 255)
CORAL = (242, 107, 103, 255)
GOLD = (246, 190, 72, 255)
PANTS = (65, 78, 105, 255)
WHITE = (250, 252, 255, 255)


class Canvas:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.pixels = bytearray(width * height * 4)

    def pixel(self, x: int, y: int, color: Color) -> None:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return
        offset = (y * self.width + x) * 4
        alpha = color[3]
        if alpha == 255:
            self.pixels[offset : offset + 4] = bytes(color)
            return
        if alpha == 0:
            return
        inverse = 255 - alpha
        destination_alpha = self.pixels[offset + 3]
        out_alpha = alpha + (destination_alpha * inverse + 127) // 255
        for channel in range(3):
            source = color[channel] * alpha
            destination = self.pixels[offset + channel] * destination_alpha * inverse // 255
            self.pixels[offset + channel] = (source + destination) // max(1, out_alpha)
        self.pixels[offset + 3] = out_alpha

    def ellipse(self, bounds: tuple[int, int, int, int], color: Color) -> None:
        left, top, right, bottom = bounds
        radius_x = max(0.5, (right - left) / 2)
        radius_y = max(0.5, (bottom - top) / 2)
        center_x = (left + right) / 2
        center_y = (top + bottom) / 2
        for y in range(max(0, top), min(self.height, bottom)):
            normalized_y = ((y + 0.5 - center_y) / radius_y) ** 2
            if normalized_y > 1:
                continue
            span = radius_x * math.sqrt(1 - normalized_y)
            start = max(0, math.ceil(center_x - span))
            end = min(self.width, math.floor(center_x + span) + 1)
            for x in range(start, end):
                self.pixel(x, y, color)

    def rect(self, bounds: tuple[int, int, int, int], color: Color) -> None:
        left, top, right, bottom = bounds
        for y in range(max(0, top), min(self.height, bottom)):
            for x in range(max(0, left), min(self.width, right)):
                self.pixel(x, y, color)

    def polygon(self, points: list[tuple[int, int]], color: Color) -> None:
        minimum_y = max(0, min(point[1] for point in points))
        maximum_y = min(self.height - 1, max(point[1] for point in points))
        for y in range(minimum_y, maximum_y + 1):
            intersections: list[float] = []
            previous = points[-1]
            for current in points:
                if (current[1] > y) != (previous[1] > y):
                    ratio = (y - current[1]) / (previous[1] - current[1])
                    intersections.append(current[0] + ratio * (previous[0] - current[0]))
                previous = current
            intersections.sort()
            for index in range(0, len(intersections) - 1, 2):
                start = max(0, math.ceil(intersections[index]))
                end = min(self.width, math.floor(intersections[index + 1]) + 1)
                for x in range(start, end):
                    self.pixel(x, y, color)

    def line(self, start: tuple[int, int], end: tuple[int, int], width: int, color: Color) -> None:
        delta_x = end[0] - start[0]
        delta_y = end[1] - start[1]
        steps = max(abs(delta_x), abs(delta_y), 1)
        radius = max(1, width // 2)
        for step in range(steps + 1):
            amount = step / steps
            x = round(start[0] + delta_x * amount)
            y = round(start[1] + delta_y * amount)
            self.ellipse((x - radius, y - radius, x + radius + 1, y + radius + 1), color)


class RegionDraw:
    def __init__(self, canvas: Canvas, frame: dict[str, int]):
        self.canvas = canvas
        self.x = frame["x"]
        self.y = frame["y"]
        self.width = frame["width"]
        self.height = frame["height"]

    def point(self, point: Point) -> tuple[int, int]:
        return (round(self.x + point[0] * self.width), round(self.y + point[1] * self.height))

    def bounds(self, left: float, top: float, right: float, bottom: float) -> tuple[int, int, int, int]:
        return (*self.point((left, top)), *self.point((right, bottom)))

    def ellipse(self, bounds: tuple[float, float, float, float], color: Color) -> None:
        self.canvas.ellipse(self.bounds(*bounds), color)

    def rect(self, bounds: tuple[float, float, float, float], color: Color) -> None:
        self.canvas.rect(self.bounds(*bounds), color)

    def polygon(self, points: list[Point], color: Color) -> None:
        self.canvas.polygon([self.point(point) for point in points], color)

    def line(self, start: Point, end: Point, width: float, color: Color) -> None:
        self.canvas.line(self.point(start), self.point(end), max(1, round(width * min(self.width, self.height))), color)

    def arc(self, bounds: tuple[float, float, float, float], start: float, end: float, width: float, color: Color) -> None:
        left, top, right, bottom = bounds
        center_x = (left + right) / 2
        center_y = (top + bottom) / 2
        radius_x = (right - left) / 2
        radius_y = (bottom - top) / 2
        points = []
        for index in range(25):
            angle = start + (end - start) * index / 24
            points.append((center_x + math.cos(angle) * radius_x, center_y + math.sin(angle) * radius_y))
        for first, second in zip(points, points[1:]):
            self.line(first, second, width, color)


def draw_hair_back(draw: RegionDraw) -> None:
    draw.ellipse((0.08, 0.04, 0.92, 0.96), HAIR)
    for center_x in (0.2, 0.35, 0.5, 0.65, 0.8):
        draw.ellipse((center_x - 0.13, 0.69, center_x + 0.13, 1.0), HAIR_LIGHT)


def draw_head(draw: RegionDraw) -> None:
    draw.ellipse((0.08, 0.04, 0.92, 0.96), SKIN_SHADOW)
    draw.ellipse((0.13, 0.08, 0.87, 0.9), SKIN)


def draw_face(draw: RegionDraw) -> None:
    draw.ellipse((0.05, 0.03, 0.95, 0.97), SKIN)
    draw.ellipse((0.08, 0.55, 0.28, 0.73), (246, 141, 151, 105))
    draw.ellipse((0.72, 0.55, 0.92, 0.73), (246, 141, 151, 105))
    draw.line((0.5, 0.47), (0.47, 0.58), 0.015, SKIN_SHADOW)


def draw_hair_front(draw: RegionDraw) -> None:
    draw.ellipse((0.08, 0.0, 0.92, 0.62), HAIR)
    draw.polygon([(0.08, 0.28), (0.32, 0.2), (0.25, 0.82), (0.48, 0.34), (0.52, 0.82), (0.72, 0.25), (0.92, 0.32), (0.84, 0.62), (0.12, 0.62)], HAIR)
    draw.arc((0.2, 0.08, 0.78, 0.5), 3.6, 5.8, 0.018, HAIR_LIGHT)


def draw_torso(draw: RegionDraw) -> None:
    draw.ellipse((0.12, 0.0, 0.88, 0.45), TEAL_DARK)
    draw.rect((0.1, 0.2, 0.9, 0.82), TEAL)
    draw.ellipse((0.1, 0.67, 0.9, 0.98), TEAL)
    draw.ellipse((0.29, 0.12, 0.71, 0.42), WHITE)
    draw.ellipse((0.36, 0.17, 0.64, 0.38), (230, 246, 244, 255))
    draw.line((0.43, 0.32), (0.43, 0.62), 0.014, TEAL_DARK)
    draw.line((0.57, 0.32), (0.57, 0.62), 0.014, TEAL_DARK)
    draw.ellipse((0.28, 0.6, 0.72, 0.79), TEAL_DARK)
    draw.ellipse((0.31, 0.61, 0.69, 0.75), (77, 183, 174, 255))


def draw_arm(draw: RegionDraw, upper: bool, right: bool) -> None:
    color = TEAL if upper else SKIN
    shadow = TEAL_DARK if upper else SKIN_SHADOW
    draw.ellipse((0.18, 0.02, 0.82, 0.98), shadow)
    inset = 0.25 if right else 0.18
    draw.ellipse((inset, 0.04, inset + 0.56, 0.91), color)
    if upper:
        draw.rect((0.16, 0.06, 0.84, 0.2), TEAL_DARK)


def draw_hand(draw: RegionDraw, right: bool) -> None:
    draw.ellipse((0.12, 0.12, 0.88, 0.9), SKIN)
    finger_x = 0.76 if right else 0.24
    draw.ellipse((finger_x - 0.12, 0.25, finger_x + 0.12, 0.82), SKIN_SHADOW)


def draw_leg(draw: RegionDraw, upper: bool, right: bool) -> None:
    color = PANTS if upper else (86, 102, 132, 255)
    shadow = (44, 54, 75, 255)
    draw.ellipse((0.16, 0.02, 0.84, 0.98), shadow)
    offset = 0.22 if right else 0.16
    draw.ellipse((offset, 0.03, offset + 0.62, 0.92), color)
    if upper:
        draw.rect((0.14, 0.05, 0.86, 0.17), (52, 64, 88, 255))


def draw_foot(draw: RegionDraw, right: bool) -> None:
    if right:
        draw.ellipse((0.08, 0.16, 0.93, 0.88), INK)
        draw.ellipse((0.13, 0.19, 0.88, 0.69), WHITE)
    else:
        draw.ellipse((0.07, 0.16, 0.92, 0.88), INK)
        draw.ellipse((0.12, 0.19, 0.87, 0.69), WHITE)
    draw.rect((0.18, 0.68, 0.9, 0.83), CORAL)


def draw_eyes(draw: RegionDraw, closed: bool) -> None:
    if closed:
        draw.arc((0.12, 0.24, 0.43, 0.76), 0.15, math.pi - 0.15, 0.055, INK)
        draw.arc((0.57, 0.24, 0.88, 0.76), 0.15, math.pi - 0.15, 0.055, INK)
        return
    for left, right in ((0.13, 0.42), (0.58, 0.87)):
        draw.ellipse((left, 0.08, right, 0.92), WHITE)
        draw.ellipse((left + 0.07, 0.18, right - 0.05, 0.88), INK)
        draw.ellipse((left + 0.11, 0.24, left + 0.17, 0.43), WHITE)


def draw_mouth(draw: RegionDraw, mood: str) -> None:
    if mood == "normal":
        draw.line((0.32, 0.53), (0.68, 0.53), 0.045, INK)
    elif mood == "smile":
        draw.arc((0.22, 0.18, 0.78, 0.77), 0.1, math.pi - 0.1, 0.05, INK)
        draw.ellipse((0.42, 0.54, 0.58, 0.71), CORAL)
    elif mood == "angry":
        draw.arc((0.22, 0.42, 0.78, 0.93), math.pi + 0.1, math.tau - 0.1, 0.055, INK)
    else:
        draw.ellipse((0.36, 0.23, 0.64, 0.79), INK)
        draw.ellipse((0.41, 0.31, 0.59, 0.67), (126, 55, 66, 255))


def draw_book(draw: RegionDraw) -> None:
    draw.polygon([(0.04, 0.18), (0.48, 0.27), (0.48, 0.9), (0.04, 0.76)], (44, 118, 140, 255))
    draw.polygon([(0.52, 0.27), (0.96, 0.18), (0.96, 0.76), (0.52, 0.9)], (54, 139, 156, 255))
    draw.polygon([(0.09, 0.23), (0.46, 0.31), (0.46, 0.82), (0.09, 0.71)], WHITE)
    draw.polygon([(0.54, 0.31), (0.91, 0.23), (0.91, 0.71), (0.54, 0.82)], WHITE)
    draw.line((0.5, 0.26), (0.5, 0.91), 0.014, INK)
    for y in (0.39, 0.5, 0.61):
        draw.line((0.16, y), (0.4, y + 0.05), 0.009, (116, 135, 151, 255))
        draw.line((0.6, y + 0.05), (0.84, y), 0.009, (116, 135, 151, 255))


def draw_laptop(draw: RegionDraw) -> None:
    draw.polygon([(0.15, 0.08), (0.85, 0.08), (0.78, 0.68), (0.22, 0.68)], INK)
    draw.polygon([(0.2, 0.14), (0.8, 0.14), (0.74, 0.61), (0.26, 0.61)], (107, 207, 207, 255))
    draw.ellipse((0.45, 0.28, 0.55, 0.44), WHITE)
    draw.polygon([(0.21, 0.68), (0.79, 0.68), (0.96, 0.89), (0.04, 0.89)], (90, 103, 125, 255))
    draw.line((0.04, 0.89), (0.96, 0.89), 0.025, INK)


def draw_warning(draw: RegionDraw) -> None:
    draw.polygon([(0.5, 0.05), (0.95, 0.9), (0.05, 0.9)], INK)
    draw.polygon([(0.5, 0.14), (0.84, 0.82), (0.16, 0.82)], GOLD)
    draw.rect((0.46, 0.34, 0.54, 0.62), INK)
    draw.ellipse((0.45, 0.68, 0.55, 0.79), INK)


def draw_heart(draw: RegionDraw) -> None:
    draw.ellipse((0.08, 0.12, 0.55, 0.58), CORAL)
    draw.ellipse((0.45, 0.12, 0.92, 0.58), CORAL)
    draw.polygon([(0.1, 0.38), (0.9, 0.38), (0.5, 0.94)], CORAL)
    draw.arc((0.2, 0.2, 0.48, 0.5), 3.5, 5.0, 0.035, (255, 183, 174, 255))


def validate_atlas(atlas: dict) -> tuple[int, int, dict[str, dict[str, int]]]:
    size = atlas.get("size", {})
    width = int(size.get("width", 0))
    height = int(size.get("height", 0))
    if (width, height) != (2048, 2048):
        raise ValueError("atlas size must be exactly 2048x2048")
    sprites = atlas.get("sprites")
    if not isinstance(sprites, dict):
        raise ValueError("atlas.sprites must be an object")
    missing = sorted(REQUIRED_SPRITES - sprites.keys())
    if missing:
        raise ValueError(f"atlas is missing sprites: {', '.join(missing)}")
    occupied: list[tuple[str, int, int, int, int]] = []
    for name, frame in sprites.items():
        values = [int(frame.get(key, -1)) for key in ("x", "y", "width", "height")]
        x, y, frame_width, frame_height = values
        if x < 0 or y < 0 or frame_width <= 0 or frame_height <= 0 or x + frame_width > width or y + frame_height > height:
            raise ValueError(f"sprite {name!r} is outside the atlas")
        for other_name, other_x, other_y, other_width, other_height in occupied:
            overlaps = x < other_x + other_width and x + frame_width > other_x and y < other_y + other_height and y + frame_height > other_y
            if overlaps:
                raise ValueError(f"sprites {name!r} and {other_name!r} overlap")
        occupied.append((name, x, y, frame_width, frame_height))
    return width, height, sprites


def render(atlas: dict) -> Canvas:
    width, height, sprites = validate_atlas(atlas)
    canvas = Canvas(width, height)
    drawers = {name: RegionDraw(canvas, frame) for name, frame in sprites.items()}
    draw_hair_back(drawers["hair_back"])
    draw_head(drawers["head"])
    draw_face(drawers["face_base"])
    draw_hair_front(drawers["hair_front"])
    draw_torso(drawers["torso"])
    for side in ("left", "right"):
        right = side == "right"
        draw_arm(drawers[f"{side}_upper_arm"], upper=True, right=right)
        draw_arm(drawers[f"{side}_lower_arm"], upper=False, right=right)
        draw_hand(drawers[f"{side}_hand"], right=right)
        draw_leg(drawers[f"{side}_upper_leg"], upper=True, right=right)
        draw_leg(drawers[f"{side}_lower_leg"], upper=False, right=right)
        draw_foot(drawers[f"{side}_foot"], right=right)
    draw_eyes(drawers["eyes_open"], closed=False)
    draw_eyes(drawers["eyes_closed"], closed=True)
    for mood in ("normal", "smile", "angry", "sleep"):
        draw_mouth(drawers[f"mouth_{mood}"], mood)
    draw_book(drawers["prop_book"])
    draw_laptop(drawers["prop_laptop"])
    draw_warning(drawers["effect_warning"])
    draw_heart(drawers["effect_heart"])
    return canvas


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def encode_png(canvas: Canvas) -> bytes:
    stride = canvas.width * 4
    scanlines = bytearray()
    for y in range(canvas.height):
        scanlines.append(0)
        start = y * stride
        scanlines.extend(canvas.pixels[start : start + stride])
    header = struct.pack(">IIBBBBB", canvas.width, canvas.height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header) + png_chunk(b"IDAT", zlib.compress(scanlines, 9)) + png_chunk(b"IEND", b"")


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    default_atlas = script_dir.parent / "characters" / "default_pet" / "atlas.json"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas", type=Path, default=default_atlas, help="Path to atlas.json")
    parser.add_argument("--output", type=Path, help="Output PNG path (defaults to atlas image beside atlas.json)")
    parser.add_argument("--check", action="store_true", help="Render and encode in memory without writing a file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    atlas_path = args.atlas.resolve()
    atlas = json.loads(atlas_path.read_text(encoding="utf-8"))
    canvas = render(atlas)
    png = encode_png(canvas)
    if len(png) < 1000 or not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("generated PNG failed its integrity check")
    if args.check:
        print(f"OK: {canvas.width}x{canvas.height}, {len(atlas['sprites'])} sprites, {len(png)} PNG bytes")
        return 0
    output = (args.output or atlas_path.parent / str(atlas.get("image", "skin.png"))).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(png)
    print(f"Wrote {output} ({len(png)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
