#!/usr/bin/env python3
"""Create the Windows application icon from the bundled pet preview."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "characters" / "default_pet" / "preview.png"
OUTPUT = ROOT / "assets" / "app.ico"


def main() -> int:
    image = Image.open(SOURCE).convert("RGBA")
    alpha = image.getchannel("A")
    bounds = alpha.getbbox()
    if bounds:
        image = image.crop(bounds)

    side = max(image.size)
    padding = max(16, side // 12)
    canvas = Image.new("RGBA", (side + padding * 2, side + padding * 2), (0, 0, 0, 0))
    canvas.alpha_composite(image, ((canvas.width - image.width) // 2, (canvas.height - image.height) // 2))
    canvas.thumbnail((256, 256), Image.Resampling.LANCZOS)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUTPUT, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
