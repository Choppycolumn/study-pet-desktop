from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterator, Mapping

from . import action_library
from .character import CharacterPackage, CharacterPackageLoader


@dataclass(frozen=True)
class InvalidCharacterPackage:
    path: Path
    reason: str
    package_id: str = ""

    @property
    def id(self) -> str:
        return self.package_id or self.path.name

    @property
    def manifest(self) -> Path:
        return self.path / "character.json"

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "path": str(self.path),
            "reason": self.reason,
        }


class CharacterRegistry:
    """Discover character packages and retain useful diagnostics for rejected ones."""

    def __init__(
        self,
        characters_dir: str | Path | None = None,
        *,
        default_character_id: str = "default_pet",
        loader: CharacterPackageLoader | None = None,
        auto_reload: bool = True,
    ) -> None:
        default_dir = Path(__file__).resolve().parents[1] / "characters"
        self.characters_dir = Path(characters_dir or default_dir).expanduser().resolve()
        self.default_character_id = str(default_character_id or "default_pet").strip()
        self.loader = loader or CharacterPackageLoader(emit_warnings=False)
        self._packages: dict[str, CharacterPackage] = {}
        self._invalid: list[InvalidCharacterPackage] = []
        self.scan_error = ""
        if auto_reload:
            self.reload()

    @property
    def packages(self) -> dict[str, CharacterPackage]:
        return dict(self._packages)

    @property
    def characters(self) -> dict[str, CharacterPackage]:
        return self.packages

    @property
    def valid_characters(self) -> tuple[CharacterPackage, ...]:
        return tuple(self._packages.values())

    @property
    def valid_packages(self) -> tuple[CharacterPackage, ...]:
        return self.valid_characters

    @property
    def valid(self) -> tuple[CharacterPackage, ...]:
        return self.valid_characters

    @property
    def valid_ids(self) -> tuple[str, ...]:
        return tuple(self._packages)

    @property
    def invalid_characters(self) -> tuple[InvalidCharacterPackage, ...]:
        return tuple(self._invalid)

    @property
    def invalid_packages(self) -> tuple[InvalidCharacterPackage, ...]:
        return self.invalid_characters

    @property
    def invalid(self) -> tuple[InvalidCharacterPackage, ...]:
        return self.invalid_characters

    @property
    def invalid_ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self._invalid)

    @property
    def errors(self) -> dict[str, str]:
        return {item.id: item.reason for item in self._invalid}

    @property
    def default_character(self) -> CharacterPackage | None:
        return self._fallback_package()

    def __len__(self) -> int:
        return len(self._packages)

    def __iter__(self) -> Iterator[CharacterPackage]:
        return iter(self._packages.values())

    def __contains__(self, character_id: object) -> bool:
        return str(character_id) in self._packages

    def reload(self) -> CharacterRegistry:
        packages: dict[str, CharacterPackage] = {}
        invalid: list[InvalidCharacterPackage] = []
        self.scan_error = ""
        if not self.characters_dir.exists():
            self.scan_error = f"characters directory does not exist: {self.characters_dir}"
        elif not self.characters_dir.is_dir():
            self.scan_error = f"characters path is not a directory: {self.characters_dir}"
        else:
            for root in sorted(
                (path for path in self.characters_dir.iterdir() if path.is_dir()),
                key=lambda path: path.name.lower(),
            ):
                package, problem = self._load_directory(root)
                if problem is not None:
                    invalid.append(problem)
                    continue
                assert package is not None
                if package.character_id in packages:
                    invalid.append(
                        InvalidCharacterPackage(
                            root,
                            f"duplicate character id {package.character_id!r}",
                            package.character_id,
                        )
                    )
                    continue
                packages[package.character_id] = package
        self._packages = packages
        self._invalid = invalid
        return self

    scan = reload

    def list_valid(self) -> list[CharacterPackage]:
        return list(self.valid_characters)

    def list_invalid(self) -> list[InvalidCharacterPackage]:
        return list(self.invalid_characters)

    def _load_directory(
        self, root: Path
    ) -> tuple[CharacterPackage | None, InvalidCharacterPackage | None]:
        manifest = root / "character.json"
        if not manifest.is_file():
            return None, InvalidCharacterPackage(root, "missing character.json")
        package_id = root.name
        try:
            parsed = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return None, InvalidCharacterPackage(
                root, f"could not read character.json: {exc}", package_id
            )
        if not isinstance(parsed, Mapping):
            return None, InvalidCharacterPackage(
                root, "character.json root must be an object", package_id
            )
        declared_id = parsed.get("id", parsed.get("characterId"))
        if declared_id is not None and not str(declared_id).strip():
            return None, InvalidCharacterPackage(
                root, "character id must not be empty", package_id
            )
        try:
            package = self.loader.load(manifest)
        except Exception as exc:
            return None, InvalidCharacterPackage(
                root, f"failed to load character package: {exc}", package_id
            )
        return package, None

    def get(
        self,
        character_id: str | None = None,
        *,
        fallback: bool = True,
    ) -> CharacterPackage | None:
        requested = str(character_id or "").strip()
        if requested and requested in self._packages:
            return self._packages[requested]
        return self._fallback_package() if fallback else None

    resolve = get

    def require(self, character_id: str | None = None) -> CharacterPackage:
        package = self.get(character_id)
        if package is None:
            raise LookupError(f"no valid character packages in {self.characters_dir}")
        return package

    def error_for(self, package_id: str) -> str | None:
        requested = str(package_id).strip()
        for item in self._invalid:
            if item.id == requested or item.path.name == requested:
                return item.reason
        return None

    def metadata_for(self, character_id: str | None = None) -> dict[str, Any]:
        package = self.get(character_id)
        return package.display_metadata if package is not None else {}

    def action_report(self, character: str | CharacterPackage | None = None) -> dict[str, Any]:
        package = character if isinstance(character, CharacterPackage) else self.get(character)
        if package is None:
            raise LookupError(f"no valid character packages in {self.characters_dir}")

        actions = tuple(action_library.ALL_ACTIONS)
        supported_states = tuple(dict.fromkeys(
            str(state).strip().lower()
            for state in (package.supported_states or tuple(package.states))
            if str(state).strip()
        ))
        supported_set = set(supported_states)
        available_actions = supported_set | {
            action
            for action, state in package.state_map.items()
            if state in supported_set
        }
        directly_supported: list[str] = []
        missing: list[str] = []
        fallbacks: dict[str, str] = {}
        unresolved: list[str] = []

        for action in actions:
            mapped_state = package.state_map.get(action, action)
            if action in supported_set or mapped_state in supported_set:
                directly_supported.append(action)
                continue
            missing.append(action)
            profile_state = _profile_fallback(package.fallback_profile, action)
            if profile_state in supported_set:
                fallbacks[action] = profile_state
                continue
            resolution = action_library.resolve_action(available_actions, action)
            actual = resolution.actual
            resolved_state = package.state_map.get(actual, actual)
            if actual in available_actions and resolved_state in supported_set:
                fallbacks[action] = actual
            else:
                unresolved.append(action)

        category_report = {
            category: {
                "supported": [action for action in category_actions if action in directly_supported],
                "missing": [action for action in category_actions if action in missing],
            }
            for category, category_actions in _action_categories().items()
        }
        report = {
            "characterId": package.character_id,
            "supportedStates": list(supported_states),
            "supported": directly_supported,
            "missing": missing,
            "fallbacks": fallbacks,
            "unresolved": unresolved,
            "categories": category_report,
        }
        report["supportedActions"] = report["supported"]
        report["missingActions"] = report["missing"]
        report["fallbackActions"] = report["fallbacks"]
        return report

    action_support_report = action_report
    report_actions = action_report

    def _fallback_package(self) -> CharacterPackage | None:
        preferred = self._packages.get(self.default_character_id)
        if preferred is not None:
            return preferred
        for package in self._packages.values():
            if package.fallback_profile is True or package.fallback_profile == "default":
                return package
        return next(iter(self._packages.values()), None)


def _action_categories() -> dict[str, tuple[str, ...]]:
    return {
        str(category): tuple(actions)
        for category, actions in action_library.ACTION_CATEGORIES.items()
    }


def _profile_fallback(profile: Any, action: str) -> str | None:
    if not isinstance(profile, Mapping):
        return None
    candidate = str(profile.get(action, "")).strip().lower()
    return candidate or None
