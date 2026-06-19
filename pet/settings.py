from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any


SOURCE_DIR = Path(__file__).resolve().parents[1]
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", SOURCE_DIR)).resolve()
APP_DIR = RESOURCE_DIR


def user_data_dir() -> Path:
    override = os.environ.get("EXAM_PLANNER_PET_HOME")
    if override:
        return Path(override).expanduser()
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "ExamPlannerPet"
    return Path.home() / ".exam-planner-pet"


def settings_path() -> Path:
    override = os.environ.get("EXAM_PLANNER_PET_CONFIG")
    if override:
        return Path(override).expanduser()
    return user_data_dir() / "config.json"


def ensure_settings_file(config_path: Path | None = None) -> Path:
    path = config_path or settings_path()
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    example = RESOURCE_DIR / "config.example.json"
    if example.is_file():
        shutil.copyfile(example, path)
    return path


@dataclass
class PetSettings:
    timezone: str = "Asia/Shanghai"
    device_id: str = "windows-main"
    server_url: str = "http://127.0.0.1:8080"
    api_token: str = "change-me"
    character_id: str = "default_pet"
    target_study_minutes: int = 180
    entertainment_limit_minutes: int = 30
    idle_threshold_seconds: int = 180
    sample_interval_seconds: int = 2
    sync_interval_seconds: int = 60
    reminder_cooldown_minutes: int = 20
    emergency_pause_minutes: int = 30
    strong_mode_enabled: bool = True
    care_enabled: bool = True
    hover_menu_enabled: bool = True
    interaction_bubbles_enabled: bool = True
    feed_cooldown_minutes: int = 5
    play_cooldown_minutes: int = 10
    gift_cooldown_minutes: int = 30
    random_idle_interval_seconds: int = 25
    reminder_tone: str = "strict"
    study_domains: list[str] = field(default_factory=lambda: ["chat.openai.com", "github.com", "wikipedia.org"])
    entertainment_domains: list[str] = field(default_factory=lambda: ["bilibili.com", "youtube.com", "douyin.com"])
    social_domains: list[str] = field(default_factory=lambda: ["weibo.com", "x.com", "twitter.com"])
    study_keywords: list[str] = field(default_factory=lambda: ["课程", "学习", "作业", "lecture", "tutorial", "PPT", "PDF"])
    entertainment_keywords: list[str] = field(default_factory=lambda: ["游戏", "番剧", "直播", "短视频"])
    tool_processes: list[str] = field(default_factory=lambda: ["code.exe", "pycharm64.exe", "idea64.exe", "word.exe", "excel.exe", "powerpnt.exe"])
    entertainment_processes: list[str] = field(default_factory=lambda: ["steam.exe", "epicgameslauncher.exe", "cloudmusic.exe", "qqgame.exe"])

    @property
    def database_path(self) -> Path:
        return user_data_dir() / "pet.sqlite"


def _list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    return [str(item).strip() for item in value if str(item).strip()]


def _int(value: Any, fallback: int, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, parsed)


def _bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return fallback if value is None else bool(value)


def load_settings(config_path: Path | None = None) -> PetSettings:
    config_path = ensure_settings_file(config_path)
    settings = PetSettings()
    if not config_path.exists():
        return settings

    try:
        with config_path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return settings

    settings.timezone = str(raw.get("timezone", settings.timezone)) or "Asia/Shanghai"
    if settings.timezone != "Asia/Shanghai":
        settings.timezone = "Asia/Shanghai"
    settings.device_id = str(raw.get("deviceId", settings.device_id)).strip() or settings.device_id
    settings.server_url = str(raw.get("serverUrl", settings.server_url)).strip().rstrip("/") or settings.server_url
    settings.api_token = str(raw.get("apiToken", settings.api_token)).strip()
    settings.character_id = str(raw.get("characterId", settings.character_id)).strip() or settings.character_id
    settings.target_study_minutes = _int(raw.get("targetStudyMinutes"), settings.target_study_minutes, 0)
    settings.entertainment_limit_minutes = _int(raw.get("entertainmentLimitMinutes"), settings.entertainment_limit_minutes)
    settings.idle_threshold_seconds = _int(raw.get("idleThresholdSeconds"), settings.idle_threshold_seconds)
    settings.sample_interval_seconds = _int(raw.get("sampleIntervalSeconds"), settings.sample_interval_seconds)
    settings.sync_interval_seconds = _int(raw.get("syncIntervalSeconds"), settings.sync_interval_seconds)
    settings.reminder_cooldown_minutes = _int(raw.get("reminderCooldownMinutes"), settings.reminder_cooldown_minutes)
    settings.emergency_pause_minutes = _int(raw.get("emergencyPauseMinutes"), settings.emergency_pause_minutes)
    settings.strong_mode_enabled = _bool(raw.get("strongModeEnabled"), settings.strong_mode_enabled)
    settings.care_enabled = _bool(raw.get("careEnabled"), settings.care_enabled)
    settings.hover_menu_enabled = _bool(raw.get("hoverMenuEnabled"), settings.hover_menu_enabled)
    settings.interaction_bubbles_enabled = _bool(
        raw.get("interactionBubblesEnabled"), settings.interaction_bubbles_enabled
    )
    settings.feed_cooldown_minutes = _int(raw.get("feedCooldownMinutes"), settings.feed_cooldown_minutes, 0)
    settings.play_cooldown_minutes = _int(raw.get("playCooldownMinutes"), settings.play_cooldown_minutes, 0)
    settings.gift_cooldown_minutes = _int(raw.get("giftCooldownMinutes"), settings.gift_cooldown_minutes, 0)
    settings.random_idle_interval_seconds = _int(
        raw.get("randomIdleIntervalSeconds"), settings.random_idle_interval_seconds, 5
    )
    settings.reminder_tone = str(raw.get("reminderTone", settings.reminder_tone)).strip() or settings.reminder_tone
    settings.study_domains = _list(raw.get("studyDomains"), settings.study_domains)
    settings.entertainment_domains = _list(raw.get("entertainmentDomains"), settings.entertainment_domains)
    settings.social_domains = _list(raw.get("socialDomains"), settings.social_domains)
    settings.study_keywords = _list(raw.get("studyKeywords"), settings.study_keywords)
    settings.entertainment_keywords = _list(raw.get("entertainmentKeywords"), settings.entertainment_keywords)
    settings.tool_processes = [item.lower() for item in _list(raw.get("toolProcesses"), settings.tool_processes)]
    settings.entertainment_processes = [item.lower() for item in _list(raw.get("entertainmentProcesses"), settings.entertainment_processes)]
    return settings


def save_character_id(character_id: str, config_path: Path | None = None) -> None:
    config_path = ensure_settings_file(config_path)
    raw: dict[str, Any] = {}
    if config_path.exists():
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
    raw["characterId"] = str(character_id).strip() or "default_pet"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_settings(settings: PetSettings, config_path: Path | None = None) -> None:
    config_path = config_path or settings_path()
    payload = {
        "timezone": "Asia/Shanghai",
        "deviceId": settings.device_id,
        "serverUrl": settings.server_url,
        "apiToken": settings.api_token,
        "characterId": settings.character_id,
        "targetStudyMinutes": settings.target_study_minutes,
        "entertainmentLimitMinutes": settings.entertainment_limit_minutes,
        "idleThresholdSeconds": settings.idle_threshold_seconds,
        "sampleIntervalSeconds": settings.sample_interval_seconds,
        "syncIntervalSeconds": settings.sync_interval_seconds,
        "reminderCooldownMinutes": settings.reminder_cooldown_minutes,
        "emergencyPauseMinutes": settings.emergency_pause_minutes,
        "strongModeEnabled": settings.strong_mode_enabled,
        "careEnabled": settings.care_enabled,
        "hoverMenuEnabled": settings.hover_menu_enabled,
        "interactionBubblesEnabled": settings.interaction_bubbles_enabled,
        "feedCooldownMinutes": settings.feed_cooldown_minutes,
        "playCooldownMinutes": settings.play_cooldown_minutes,
        "giftCooldownMinutes": settings.gift_cooldown_minutes,
        "randomIdleIntervalSeconds": settings.random_idle_interval_seconds,
        "reminderTone": settings.reminder_tone,
        "studyDomains": settings.study_domains,
        "entertainmentDomains": settings.entertainment_domains,
        "socialDomains": settings.social_domains,
        "studyKeywords": settings.study_keywords,
        "entertainmentKeywords": settings.entertainment_keywords,
        "toolProcesses": settings.tool_processes,
        "entertainmentProcesses": settings.entertainment_processes,
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
