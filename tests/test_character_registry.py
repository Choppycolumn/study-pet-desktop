from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from pet.character import CharacterPackageLoader
from pet.character_registry import CharacterRegistry


def write_manifest(root: Path, directory: str, data: object) -> Path:
    package = root / directory
    package.mkdir(parents=True, exist_ok=True)
    (package / "character.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    return package


class CharacterPackageMetadataTests(unittest.TestCase):
    def test_manifest_metadata_is_exposed_in_package_and_web_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_root = write_manifest(
                root,
                "scholar",
                {
                    "id": "scholar",
                    "displayName": "Scholar",
                    "version": 2,
                    "author": "QA Team",
                    "description": "A focused study character.",
                    "tags": ["study", "quiet", "study"],
                    "supportedStates": ["IDLE", "study"],
                    "fallbackProfile": {"warning": "study"},
                    "metadata": {"license": "CC0"},
                    "states": {"idle": {}, "study": {}},
                },
            )
            package = CharacterPackageLoader(emit_warnings=False).load(package_root)

        self.assertEqual(package.version, 2)
        self.assertEqual(package.author, "QA Team")
        self.assertEqual(package.tags, ("study", "quiet"))
        self.assertEqual(package.supported_states, ("idle", "study"))
        self.assertEqual(package.fallback_profile, {"warning": "study"})
        self.assertEqual(package.display_metadata["license"], "CC0")
        payload = package.to_web_payload()
        self.assertEqual(payload["supportedStates"], ["idle", "study"])
        self.assertEqual(payload["metadata"]["author"], "QA Team")

    def test_old_manifest_infers_supported_states_and_uses_metadata_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package_root = write_manifest(
                Path(directory),
                "legacy",
                {
                    "id": "legacy",
                    "displayName": "Legacy",
                    "animations": {"idle": {}, "study": {}},
                },
            )
            package = CharacterPackageLoader(emit_warnings=False).load(package_root)

        self.assertIsNone(package.version)
        self.assertEqual(package.author, "")
        self.assertEqual(package.tags, ())
        self.assertEqual(package.supported_states, ("idle", "study"))


class CharacterRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_registry_lists_valid_and_invalid_packages_with_reasons(self) -> None:
        write_manifest(self.root, "default", {"id": "default", "displayName": "Default"})
        broken = self.root / "broken"
        broken.mkdir()
        (broken / "character.json").write_text("{not json", encoding="utf-8")
        (self.root / "missing").mkdir()

        registry = CharacterRegistry(self.root, default_character_id="default")

        self.assertEqual(registry.valid_ids, ("default",))
        self.assertEqual(set(registry.invalid_ids), {"broken", "missing"})
        self.assertIn("could not read", registry.error_for("broken") or "")
        self.assertEqual(registry.error_for("missing"), "missing character.json")

    def test_reload_duplicate_detection_and_default_fallback(self) -> None:
        write_manifest(self.root, "a", {"id": "shared", "displayName": "First"})
        write_manifest(self.root, "b", {"id": "shared", "displayName": "Second"})
        write_manifest(self.root, "default", {"id": "default", "displayName": "Default"})
        registry = CharacterRegistry(self.root, default_character_id="default")

        self.assertEqual(registry.get("unknown").character_id, "default")
        self.assertIn("duplicate", registry.error_for("b") or "")
        write_manifest(self.root, "new", {"id": "new", "displayName": "New"})
        self.assertNotIn("new", registry)
        self.assertIs(registry.reload(), registry)
        self.assertIn("new", registry)

    def test_action_report_separates_direct_missing_and_fallback_actions(self) -> None:
        write_manifest(
            self.root,
            "compact",
            {
                "id": "compact",
                "displayName": "Compact",
                "supportedStates": ["idle_normal", "study_normal"],
                "fallbackProfile": {"warning_soft": "study_normal"},
                "states": {"idle_normal": {}, "study_normal": {}},
            },
        )
        report = CharacterRegistry(
            self.root, default_character_id="compact"
        ).action_report("compact")

        self.assertIn("idle_normal", report["supported"])
        self.assertIn("study_normal", report["supported"])
        self.assertIn("warning_soft", report["missing"])
        self.assertEqual(report["fallbacks"].get("warning_soft"), "study_normal")
        self.assertEqual(report["missingActions"], report["missing"])


if __name__ == "__main__":
    unittest.main()
