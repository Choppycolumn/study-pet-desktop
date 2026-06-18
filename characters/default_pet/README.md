# Default Pet Character Package

This package is an original, procedural character for the `webview_skin_rig`
renderer. It contains no third-party artwork.

## Files

- `character.json` selects the renderer and maps application states to clips.
- `atlas.json` defines the pixel rectangles in the 2048x2048 RGBA skin.
- `rig.json` defines node parents, local positions, pivots, scales, and layers.
- `animations.json` contains millisecond keyframes for all bundled clips.
- `skin.png` is generated output and should not be edited by hand.

The atlas has 27 independent sprites: the head and face layers, front and back
hair, torso, articulated limbs, open and closed eyes, four mouths, two props,
and two effects. Rig positions use the 512x768 logical canvas. Pivot values are
in source-sprite pixels; positions are local logical-canvas pixels. Rotations in
the animation file are degrees.

Animation tracks use this shape:

```json
{
  "target": "head",
  "property": "rotation",
  "keyframes": [
    { "time": 0, "value": -2 },
    { "time": 500, "value": 2 }
  ]
}
```

`visible` tracks are discrete. Numeric tracks interpolate with the file's
default easing unless a keyframe supplies its own `easing`. A renderer should
restore the rig pose before entering a clip with `resetPose: true`, and use the
clip's `fallback` after a non-looping clip ends.

## Generate the skin

From the `desktop-pet` directory:

```powershell
python tools/generate_default_skin.py --check
python tools/generate_default_skin.py
```

`--check` validates every required region, checks atlas bounds and overlap, then
renders and PNG-encodes entirely in memory. The second command writes the image
named by `atlas.json` (`skin.png` by default). The generator uses only the
Python standard library.
