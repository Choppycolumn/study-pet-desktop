from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "characters" / "default_pet"
REQUIRED_ACTIONS = {
    "idle_normal",
    "idle_blink",
    "study_normal",
    "warning_soft",
    "warning_strong",
    "angry_soft",
    "happy",
    "sleep",
    "click",
    "dragging",
}
EXTENDED_ACTIONS = {
    "feed",
    "play",
    "gift",
    "pet_head",
    "menu_open",
    "sync_error",
    "study_complete",
    "celebrate",
}


def load_json(name: str) -> dict:
    return json.loads((PACKAGE_ROOT / name).read_text(encoding="utf-8"))


class DefaultActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_json("character.json")
        cls.animations = load_json("animations.json")
        cls.rig = load_json("rig.json")

    def test_metadata_declares_default_character_capabilities(self) -> None:
        for field in (
            "version",
            "author",
            "description",
            "tags",
            "supportedStates",
            "fallbackProfile",
        ):
            self.assertIn(field, self.manifest)
            self.assertTrue(self.manifest[field])

        supported = set(self.manifest["supportedStates"])
        self.assertTrue(REQUIRED_ACTIONS | EXTENDED_ACTIONS <= supported)

    def test_required_and_extended_actions_are_native_clips(self) -> None:
        clips = self.animations["clips"]
        expected = REQUIRED_ACTIONS | EXTENDED_ACTIONS
        self.assertTrue(expected <= set(clips))
        self.assertEqual(self.animations["defaultState"], "idle_normal")
        self.assertGreater(self.animations["defaultFps"], 0)

        signatures = {
            action: json.dumps(clips[action]["tracks"], sort_keys=True)
            for action in REQUIRED_ACTIONS
        }
        self.assertEqual(len(signatures), len(set(signatures.values())))
        for action in expected:
            self.assertTrue(clips[action]["tracks"], action)
        for action, clip in clips.items():
            self.assertIn(clip["fallback"], clips, action)

    def test_fallbacks_and_state_map_resolve_to_existing_clips(self) -> None:
        clips = self.animations["clips"]
        for requested, fallback in self.animations["fallbacks"].items():
            self.assertIsInstance(requested, str)
            self.assertIn(fallback, clips)
        for state, action in self.manifest["stateMap"].items():
            self.assertIsInstance(state, str)
            self.assertIn(action, clips)
        for action, fallback in self.manifest["stateFallbacks"].items():
            self.assertIn(action, clips)
            self.assertIn(fallback, clips)

    def test_tracks_only_reference_rig_nodes_and_valid_keyframes(self) -> None:
        node_ids = {node["id"] for node in self.rig["nodes"]}
        for clip_name, clip in self.animations["clips"].items():
            duration = clip["duration"]
            self.assertGreater(duration, 0, clip_name)
            for track in clip["tracks"]:
                self.assertIn(track["target"], node_ids, clip_name)
                frames = track["keyframes"]
                self.assertTrue(frames, clip_name)
                times = [frame["time"] for frame in frames]
                self.assertEqual(times, sorted(times), clip_name)
                self.assertGreaterEqual(times[0], 0, clip_name)
                self.assertLessEqual(times[-1], duration, clip_name)


if __name__ == "__main__":
    unittest.main()
