#!/usr/bin/env python3
"""Validate a high-resolution skin/atlas/rig/animation character package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pet.character import CharacterPackageLoader  # noqa: E402


def _object(path: Path) -> Mapping[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def _png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path.name} is not a valid PNG")
    return struct.unpack(">II", header[16:24])


def validate(package_root: Path) -> dict[str, Any]:
    package_root = package_root.resolve()
    required = ("character.json", "skin.png", "atlas.json", "rig.json", "animations.json")
    missing = [name for name in required if not (package_root / name).is_file()]
    if missing:
        raise ValueError(f"missing required files: {', '.join(missing)}")

    package = CharacterPackageLoader(emit_warnings=False).load(package_root)
    if package.warnings:
        raise ValueError("; ".join(package.warnings))
    width, height = _png_size(package_root / "skin.png")
    if max(width, height) > 4096:
        raise ValueError(f"skin.png is {width}x{height}; maximum supported size is 4096x4096")

    atlas = _object(package_root / "atlas.json")
    raw_parts = atlas.get("parts", atlas.get("sprites", atlas.get("frames")))
    if not isinstance(raw_parts, Mapping) or not raw_parts:
        raise ValueError("atlas.json must define parts, sprites, or frames")
    part_names: set[str] = set()
    for name, raw in raw_parts.items():
        if not isinstance(raw, Mapping):
            raise ValueError(f"atlas part {name!r} must be an object")
        frame = raw.get("frame") if isinstance(raw.get("frame"), Mapping) else raw
        x = int(frame.get("x", -1))
        y = int(frame.get("y", -1))
        part_width = int(frame.get("w", frame.get("width", 0)))
        part_height = int(frame.get("h", frame.get("height", 0)))
        if x < 0 or y < 0 or part_width <= 0 or part_height <= 0:
            raise ValueError(f"atlas part {name!r} has an invalid rectangle")
        if x + part_width > width or y + part_height > height:
            raise ValueError(f"atlas part {name!r} exceeds skin.png bounds")
        part_names.add(str(name))

    rig = _object(package_root / "rig.json")
    raw_nodes = rig.get("nodes", rig.get("parts"))
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("rig.json must define a non-empty nodes array")
    node_ids = {str(node.get("id", node.get("name", ""))) for node in raw_nodes if isinstance(node, Mapping)}
    for node in raw_nodes:
        if not isinstance(node, Mapping):
            raise ValueError("every rig node must be an object")
        node_id = str(node.get("id", node.get("name", "")))
        part = node.get("part", node.get("sprite"))
        parent = node.get("parent")
        if not node_id:
            raise ValueError("every rig node needs an id")
        if part and str(part) not in part_names:
            raise ValueError(f"rig node {node_id!r} references missing atlas part {part!r}")
        if parent and str(parent) not in node_ids:
            raise ValueError(f"rig node {node_id!r} references missing parent {parent!r}")

    animations = _object(package_root / "animations.json")
    clips = animations.get("clips", animations.get("animations"))
    if not isinstance(clips, Mapping) or "idle" not in clips:
        raise ValueError("animations.json must define an idle clip")
    animated_targets: set[str] = set()
    for clip_name, clip in clips.items():
        if not isinstance(clip, Mapping):
            raise ValueError(f"clip {clip_name!r} must be an object")
        tracks = clip.get("tracks", {})
        if isinstance(tracks, list):
            for track in tracks:
                if not isinstance(track, Mapping):
                    raise ValueError(f"clip {clip_name!r} contains a malformed track")
                target = str(track.get("target", track.get("node", "")))
                if target not in node_ids:
                    raise ValueError(f"clip {clip_name!r} targets unknown node {target!r}")
                animated_targets.add(target)
        elif isinstance(tracks, Mapping):
            unknown = {str(name) for name in tracks} - node_ids
            if unknown:
                raise ValueError(f"clip {clip_name!r} targets unknown nodes: {', '.join(sorted(unknown))}")
            animated_targets.update(str(name) for name in tracks)
        else:
            raise ValueError(f"clip {clip_name!r} tracks must be an object or array")

    expressive = {name for name in animated_targets if any(token in name for token in ("eye", "mouth", "arm"))}
    if not expressive:
        raise ValueError("at least one eye, mouth, or arm node must be animated")
    return {
        "id": package.character_id,
        "renderer": package.renderer,
        "skin": f"{width}x{height}",
        "parts": len(part_names),
        "nodes": len(node_ids),
        "clips": sorted(str(name) for name in clips),
        "expressiveTargets": sorted(expressive),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", nargs="?", type=Path, default=ROOT / "characters" / "default_pet")
    args = parser.parse_args()
    try:
        result = validate(args.package)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
