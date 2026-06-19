from __future__ import annotations

import sys
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

from PySide6.QtCore import QObject, QPoint, QRectF, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QContextMenuEvent, QFont, QIcon, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSpinBox,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .behavior import PetBehaviorScheduler
from .care import PetCareSystem
from .character import CharacterPackage
from .character_registry import CharacterRegistry
from .classifier import ActivityClassifier, Classification
from .dialogue import DialogueAgent
from .interaction_ui import CareStatusView, CharacterPanel, HoverQuickMenu, PetStatusDialog
from .monitor import ActivityMonitor, ActivitySnapshot
from .reminder import ReminderEngine
from .renderers import BaseRenderer, StaticRenderer, WebViewRenderer, create_renderer
from .renderers.webview_renderer import WebEngineUnavailableError
from .settings import PetSettings, RESOURCE_DIR, load_settings, save_character_id, save_settings
from .storage import PetStorage
from .sync import SyncClient


class SyncWorkerSignals(QObject):
    finished = Signal(bool, str)


class SyncWorker(QRunnable):
    def __init__(self, client: SyncClient):
        super().__init__()
        self.client = client
        self.signals = SyncWorkerSignals()

    def run(self) -> None:
        try:
            ok, message = self.client.sync_today()
        except Exception:
            ok, message = False, "同步失败，数据已保留在本地。"
        self.signals.finished.emit(ok, message)


class StrongReminderDialog(QDialog):
    def __init__(self, message: str, countdown_seconds: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.remaining = countdown_seconds
        self.setWindowTitle("开始学习")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setModal(False)
        self.setMinimumWidth(360)

        self.label = QLabel(message)
        self.label.setWordWrap(True)
        self.countdown = QLabel()
        self.primary = QPushButton("开始学习")
        self.secondary = QPushButton("稍后")
        self.primary.clicked.connect(self.accept)
        self.secondary.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addWidget(self.secondary)
        buttons.addWidget(self.primary)

        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.addWidget(self.countdown)
        layout.addLayout(buttons)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        self._render()

    def _tick(self) -> None:
        self.remaining = max(0, self.remaining - 1)
        self._render()
        if self.remaining == 0:
            self.primary.setFocus()

    def _render(self) -> None:
        self.countdown.setText(f"倒计时 {self.remaining} 秒，确认后进入学习。")


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: PetSettings,
        profiles: dict[str, CharacterPackage],
        *,
        care_status: object | None = None,
        invalid_packages: list[tuple[str, str]] | None = None,
        preview_callback: Callable[[str, str], None] | None = None,
        switch_callback: Callable[[str], None] | None = None,
        reload_callback: Callable[[], tuple[dict[str, CharacterPackage], list[tuple[str, str]]]] | None = None,
        initial_tab: int = 0,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.settings = settings
        self._reload_callback = reload_callback
        self.setWindowTitle("桌宠设置")
        self.setMinimumSize(620, 620)

        self.server_url = QLineEdit(settings.server_url)
        self.api_token = QLineEdit(settings.api_token)
        self.api_token.setEchoMode(QLineEdit.Password)
        self.target_study = self._spin(settings.target_study_minutes, 0, 1440, " 分钟")
        self.entertainment_limit = self._spin(settings.entertainment_limit_minutes, 1, 600, " 分钟")
        self.idle_threshold = self._spin(settings.idle_threshold_seconds, 30, 7200, " 秒")
        self.strong_mode = QCheckBox("启用弹窗、倒计时和确认按钮")
        self.strong_mode.setChecked(settings.strong_mode_enabled)
        self.reminder_tone = QComboBox()
        self.reminder_tone.addItem("严格", "strict")
        self.reminder_tone.addItem("温和", "gentle")
        tone_index = self.reminder_tone.findData(settings.reminder_tone)
        if tone_index >= 0:
            self.reminder_tone.setCurrentIndex(tone_index)
        self.study_domains = QLineEdit(", ".join(settings.study_domains))
        self.entertainment_domains = QLineEdit(", ".join(settings.entertainment_domains))
        self.study_keywords = QLineEdit(", ".join(settings.study_keywords))
        self.entertainment_keywords = QLineEdit(", ".join(settings.entertainment_keywords))

        general = QWidget(self)
        general_form = QFormLayout(general)
        general_form.addRow("网站地址", self.server_url)
        general_form.addRow("API Token", self.api_token)
        general_form.addRow("每日学习目标", self.target_study)
        general_form.addRow("娱乐提醒阈值", self.entertainment_limit)
        general_form.addRow("空闲判定", self.idle_threshold)
        general_form.addRow("强提醒模式", self.strong_mode)
        general_form.addRow("提醒语气", self.reminder_tone)
        general_form.addRow("学习网站", self.study_domains)
        general_form.addRow("娱乐网站", self.entertainment_domains)
        general_form.addRow("学习关键词", self.study_keywords)
        general_form.addRow("娱乐关键词", self.entertainment_keywords)

        self.care_enabled = QCheckBox("启用养成属性与互动事件")
        self.care_enabled.setChecked(settings.care_enabled)
        self.hover_menu_enabled = QCheckBox("鼠标悬停时显示快捷菜单")
        self.hover_menu_enabled.setChecked(settings.hover_menu_enabled)
        self.interaction_bubbles_enabled = QCheckBox("互动时显示气泡文案")
        self.interaction_bubbles_enabled.setChecked(settings.interaction_bubbles_enabled)
        self.feed_cooldown = self._spin(settings.feed_cooldown_minutes, 0, 1440, " 分钟")
        self.play_cooldown = self._spin(settings.play_cooldown_minutes, 0, 1440, " 分钟")
        self.gift_cooldown = self._spin(settings.gift_cooldown_minutes, 0, 10080, " 分钟")
        self.pause_minutes = self._spin(settings.emergency_pause_minutes, 1, 1440, " 分钟")
        self.random_idle_interval = self._spin(settings.random_idle_interval_seconds, 5, 600, " 秒")
        interaction = QWidget(self)
        interaction_form = QFormLayout(interaction)
        interaction_form.addRow("养成系统", self.care_enabled)
        interaction_form.addRow("悬停快捷菜单", self.hover_menu_enabled)
        interaction_form.addRow("互动气泡", self.interaction_bubbles_enabled)
        interaction_form.addRow("喂食冷却", self.feed_cooldown)
        interaction_form.addRow("玩耍冷却", self.play_cooldown)
        interaction_form.addRow("礼物冷却", self.gift_cooldown)
        interaction_form.addRow("暂停提醒时长", self.pause_minutes)
        interaction_form.addRow("随机待机间隔", self.random_idle_interval)
        self.care_status_view = CareStatusView(interaction)
        if care_status is not None:
            self.care_status_view.set_status(care_status)
        interaction_form.addRow("当前养成状态", self.care_status_view)

        self.character_panel = CharacterPanel(
            profiles,
            settings.character_id,
            invalid_packages,
            self,
        )
        if preview_callback:
            self.character_panel.preview_requested.connect(preview_callback)
        if switch_callback:
            self.character_panel.character_selected.connect(switch_callback)
        self.character_panel.reload_requested.connect(self._reload_characters)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(general, "基础与同步")
        self.tabs.addTab(interaction, "自律与互动")
        self.tabs.addTab(self.character_panel, "角色与动作")
        self.tabs.setCurrentIndex(max(0, min(self.tabs.count() - 1, int(initial_tab))))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(buttons)

    def _reload_characters(self) -> None:
        if not self._reload_callback:
            return
        profiles, invalid = self._reload_callback()
        self.character_panel.set_profiles(profiles, self.settings.character_id, invalid)

    def accept(self) -> None:
        self.settings.server_url = self.server_url.text().strip().rstrip("/")
        self.settings.api_token = self.api_token.text().strip()
        self.settings.character_id = self.character_panel.selected_character_id or "default_pet"
        self.settings.target_study_minutes = self.target_study.value()
        self.settings.entertainment_limit_minutes = self.entertainment_limit.value()
        self.settings.idle_threshold_seconds = self.idle_threshold.value()
        self.settings.strong_mode_enabled = self.strong_mode.isChecked()
        self.settings.care_enabled = self.care_enabled.isChecked()
        self.settings.hover_menu_enabled = self.hover_menu_enabled.isChecked()
        self.settings.interaction_bubbles_enabled = self.interaction_bubbles_enabled.isChecked()
        self.settings.feed_cooldown_minutes = self.feed_cooldown.value()
        self.settings.play_cooldown_minutes = self.play_cooldown.value()
        self.settings.gift_cooldown_minutes = self.gift_cooldown.value()
        self.settings.emergency_pause_minutes = self.pause_minutes.value()
        self.settings.random_idle_interval_seconds = self.random_idle_interval.value()
        self.settings.reminder_tone = str(self.reminder_tone.currentData() or "strict")
        self.settings.study_domains = self._items(self.study_domains.text())
        self.settings.entertainment_domains = self._items(self.entertainment_domains.text())
        self.settings.study_keywords = self._items(self.study_keywords.text())
        self.settings.entertainment_keywords = self._items(self.entertainment_keywords.text())
        save_settings(self.settings)
        super().accept()

    @staticmethod
    def _spin(value: int, minimum: int, maximum: int, suffix: str) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin

    @staticmethod
    def _items(value: str) -> list[str]:
        return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]


class PetWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.character_registry = CharacterRegistry(RESOURCE_DIR / "characters")
        self.character_profiles = self.character_registry.packages
        self.character = self.character_registry.require(self.settings.character_id)
        if self.character.character_id != self.settings.character_id:
            self.settings.character_id = self.character.character_id
            save_character_id(self.character.character_id)
        self.storage = PetStorage(self.settings)
        self.care = PetCareSystem(self.storage, self.character.character_id)
        idle_interval = float(self.settings.random_idle_interval_seconds)
        self.behavior = PetBehaviorScheduler(
            self.character.states,
            random_idle_interval=(idle_interval, idle_interval * 1.8),
        )
        self.dialogue = DialogueAgent(self.character)
        self.monitor = ActivityMonitor()
        self.classifier = ActivityClassifier(self.settings)
        self.reminder = ReminderEngine(self.settings)
        self.sync = SyncClient(self.settings, self.storage)
        self.thread_pool = QThreadPool.globalInstance()
        self.sync_busy = False
        self._dialogs: list[StrongReminderDialog] = []
        self._preview_generation = 0
        self._study_care_seconds = 0
        self._goal_completed_announced = bool(self.storage.get_report_payload()["studyGoal"]["completed"])
        self._was_idle = False

        self.drag_position: QPoint | None = None
        self.press_global_position: QPoint | None = None
        self.drag_moved = False
        self.pending_click_position: QPoint | None = None
        self.bubble_text = self.character.line("default", "我在这里，开始记录。")
        self.current_state = self.behavior.state
        self.last_snapshot: ActivitySnapshot | None = None
        self.last_classification = Classification("unknown", "startup", "")
        self.last_domain = ""
        self._state_before_pointer_action = "idle"
        self.renderer: BaseRenderer

        self.setWindowTitle("Exam Planner Desktop Pet")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(290, 440)
        self.move(100, 220)

        self.renderer = self._make_renderer(self.character)
        self.hover_menu = HoverQuickMenu(self)
        self.hover_menu.move(15, 88)
        self.hover_menu.action_requested.connect(self._handle_menu_action)

        self._setup_tray()

        self.sample_timer = QTimer(self)
        self.sample_timer.timeout.connect(self._sample)
        self.sample_timer.start(max(1, self.settings.sample_interval_seconds) * 1000)

        self.sync_timer = QTimer(self)
        self.sync_timer.timeout.connect(self.sync_now)
        self.sync_timer.start(max(15, self.settings.sync_interval_seconds) * 1000)

        self.behavior_timer = QTimer(self)
        self.behavior_timer.timeout.connect(self._tick_behavior)
        self.behavior_timer.start(200)

        self.care_timer = QTimer(self)
        self.care_timer.timeout.connect(self._apply_care_decay)
        self.care_timer.start(10 * 60 * 1000)

        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self._show_pending_click_menu)

        self.greeting_timer = QTimer(self)
        self.greeting_timer.setSingleShot(True)
        self.greeting_timer.timeout.connect(self._greet_for_current_time)
        self.greeting_timer.start(700)

        self.storage.ensure_day()

    def _invalid_character_packages(self) -> list[tuple[str, str]]:
        return [(item.path.name, item.reason) for item in self.character_registry.invalid_packages]

    def _make_renderer(self, character: CharacterPackage):
        try:
            renderer = create_renderer(character, self)
            if isinstance(renderer, WebViewRenderer):
                renderer.renderer_failed.connect(self._renderer_failed)
        except (WebEngineUnavailableError, RuntimeError) as exc:
            self.bubble_text = f"WebView 不可用，已切换静态显示：{exc}"
            renderer = StaticRenderer(self)
            renderer.set_character(character)
        renderer.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        renderer.setGeometry(10, 92, 270, 338)
        renderer.set_state(self.current_state)
        renderer.show()
        return renderer

    def _renderer_failed(self, message: str) -> None:
        QTimer.singleShot(0, lambda: self._fallback_to_static(message))

    def _fallback_to_static(self, message: str) -> None:
        if not isinstance(self.renderer, WebViewRenderer):
            return
        previous = self.renderer
        previous.shutdown()
        previous.hide()
        previous.deleteLater()
        self.renderer = StaticRenderer(self)
        self.renderer.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.renderer.setGeometry(10, 92, 270, 338)
        self.renderer.set_character(self.character)
        self.renderer.set_state(self.current_state)
        self.renderer.show()
        self.bubble_text = f"动画渲染已降级，功能继续运行：{message}"
        self.update()

    def _setup_tray(self) -> None:
        self.tray = QSystemTrayIcon(self._tray_icon(), self)
        menu = QMenu()
        study_action = QAction("开始学习模式", self)
        sync_action = QAction("立即同步", self)
        pause_action = QAction("紧急暂停提醒", self)
        status_action = QAction("今日统计与状态", self)
        settings_action = QAction("设置", self)
        show_action = QAction("显示桌宠", self)
        quit_action = QAction("退出", self)
        study_action.triggered.connect(self.start_study_mode)
        sync_action.triggered.connect(self.sync_now)
        pause_action.triggered.connect(lambda _checked=False: self.emergency_pause())
        status_action.triggered.connect(self.show_status)
        settings_action.triggered.connect(lambda _checked=False: self.open_settings())
        show_action.triggered.connect(self.showNormal)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(study_action)
        menu.addAction(sync_action)
        menu.addAction(pause_action)
        menu.addAction(status_action)
        menu.addAction(settings_action)
        if self.character_profiles:
            character_menu = menu.addMenu("切换角色")
            for character_id, profile in sorted(self.character_profiles.items(), key=lambda item: item[1].display_name):
                action = QAction(profile.display_name, self)
                action.setCheckable(True)
                action.setChecked(character_id == self.character.character_id)
                action.triggered.connect(lambda _checked=False, target=character_id: self.switch_character(target))
                character_menu.addAction(action)
        menu.addSeparator()
        menu.addAction(show_action)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("桌宠自律助手")
        self.tray.show()

    def _handle_menu_action(self, action: str) -> None:
        self.hover_menu.hide()
        if action == "settings":
            self._play_action("settings_open", 1.5)
            self.open_settings()
            return
        self.perform_interaction(action)

    def perform_interaction(self, action: str) -> None:
        if action in {"status_view", "check_progress"}:
            self._play_action("check_progress", 2.0)
            self.show_status()
            return
        if action in {"study", "study_together", "ask_study"}:
            self.start_study_mode()
            return
        if action == "study_check_in":
            if self.settings.care_enabled:
                self.care.study_tick(1)
            self._play_action("praise_study", 2.5)
            self.bubble_text = "学习打卡完成，下一段也一起坚持。"
            self.update()
            return
        if action == "dialogue":
            self._play_action("greet", 2.2)
            if self.settings.interaction_bubbles_enabled:
                self.bubble_text = self.dialogue.select("default")
            self.update()
            return

        care_actions = {"feed", "play", "gift", "pet_head"}
        if action in care_actions and self.settings.care_enabled:
            method = getattr(self.care, action)
            method()
            if not self.care.last_action_applied:
                minutes = max(1, int((self.care.cooldown_remaining_seconds + 59) // 60))
                self.bubble_text = f"这个互动还要等 {minutes} 分钟。"
                self._play_action("warning_soft", 1.8)
                self.update()
                return

        animation = {
            "feed": "feed",
            "play": "play",
            "gift": "gift",
            "pet_head": "pet_head",
        }.get(action, action)
        self._play_action(animation, 3.0)
        if self.settings.interaction_bubbles_enabled:
            self.bubble_text = self.dialogue.select(action)
        self.update()

    def show_status(self) -> None:
        dialog = PetStatusDialog(self.care.get_status(), self.storage.get_report_payload(), self)
        dialog.exec()

    def _interaction_menu(self) -> QMenu:
        menu = QMenu("互动", self)
        for label, action in (
            ("摸摸头", "pet_head"),
            ("陪我学习", "study_together"),
            ("学习打卡", "study_check_in"),
            ("玩一会儿", "play"),
            ("喂食", "feed"),
            ("送礼物", "gift"),
            ("聊一句", "dialogue"),
            ("查看状态", "status_view"),
        ):
            item = menu.addAction(label)
            item.triggered.connect(lambda _checked=False, target=action: self.perform_interaction(target))
        return menu

    def _full_menu(self) -> QMenu:
        menu = QMenu("桌宠", self)
        study = menu.addAction("开始学习模式")
        pause = menu.addAction("暂停提醒 15 分钟")
        status = menu.addAction("今日统计")
        study.triggered.connect(self.start_study_mode)
        pause.triggered.connect(lambda _checked=False: self.emergency_pause(15))
        status.triggered.connect(self.show_status)
        character_menu = menu.addMenu("角色切换")
        for character_id, profile in sorted(self.character_profiles.items(), key=lambda item: item[1].display_name):
            item = character_menu.addAction(profile.display_name)
            item.setCheckable(True)
            item.setChecked(character_id == self.character.character_id)
            item.triggered.connect(lambda _checked=False, target=character_id: self.switch_character(target))
        preview = menu.addAction("动作预览")
        settings = menu.addAction("设置")
        sync = menu.addAction("重新同步")
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        preview.triggered.connect(lambda _checked=False: self.open_settings(2))
        settings.triggered.connect(lambda _checked=False: self.open_settings())
        sync.triggered.connect(self.sync_now)
        quit_action.triggered.connect(QApplication.instance().quit)
        return menu

    def _show_pending_click_menu(self) -> None:
        position = self.pending_click_position
        self.pending_click_position = None
        if position is None:
            return
        self._play_action("click", 1.5)
        menu = self._interaction_menu()
        menu.exec(position)
        menu.deleteLater()

    def _tray_icon(self) -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#2563eb"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(8, 8, 48, 48)
        painter.setBrush(QColor("white"))
        painter.drawEllipse(22, 22, 8, 8)
        painter.drawEllipse(36, 22, 8, 8)
        painter.end()
        return QIcon(pixmap)

    def _render_action(self, action: str) -> str:
        resolved = self.renderer.set_state(action)
        self.current_state = resolved
        return resolved

    def _set_state(self, state: str) -> None:
        self._render_action(self.behavior.set_main_state(state))

    def _play_action(self, action: str, duration: float = 2.5) -> str:
        actual = self.behavior.play_temporary(action, duration)
        return self._render_action(actual)

    def _tick_behavior(self) -> None:
        action = self.behavior.tick()
        if action != self.current_state:
            self._render_action(action)

    def _apply_care_decay(self) -> None:
        if self.settings.care_enabled:
            self.care.time_decay()

    def _greet_for_current_time(self) -> None:
        hour = datetime.now(ZoneInfo("Asia/Shanghai")).hour
        if 5 <= hour < 12:
            action, message = "good_morning", "早上好，先完成今天最重要的一件事。"
        elif 12 <= hour < 18:
            action, message = "good_afternoon", "下午好，记得给专注留一点完整时间。"
        elif 18 <= hour < 23:
            action, message = "good_evening", "晚上好，收好今天的学习进度吧。"
        else:
            action, message = "late_night_warning", "已经很晚了，完成收尾后早点休息。"
        self._play_action(action, 3.0)
        self.bubble_text = message
        self.update()

    def _sample(self) -> None:
        snapshot = self.monitor.current()
        classification = self.classifier.classify(snapshot)
        duration = self.settings.sample_interval_seconds
        is_idle = snapshot.idle_seconds >= self.settings.idle_threshold_seconds
        returned_from_idle = self._was_idle and not is_idle
        self._was_idle = is_idle
        if is_idle:
            duration = 0
            deep_idle = max(10 * 60, self.settings.idle_threshold_seconds * 3)
            self._set_state("sleep" if snapshot.idle_seconds >= deep_idle else "nap")
        elif classification.category == "study":
            self._set_state("study_normal")
        elif classification.category == "tool":
            self._set_state("study_typing")
        elif classification.category != "entertainment":
            self._set_state("idle_normal")

        site_visit = bool(classification.domain and classification.domain != self.last_domain)
        self.storage.record_activity(snapshot, classification, duration, site_visit=site_visit)
        decision = self.reminder.update(classification, duration)
        if decision.trigger:
            ratio = self.reminder.entertainment_streak_seconds / max(1, self.settings.entertainment_limit_minutes * 60)
            self.behavior.set_main_state("angry_strong" if ratio >= 1.5 else "angry_soft")
            self._play_action("warning_strong", 3.5)
            self.bubble_text = self.dialogue.select("entertainment_timeout")
            self.storage.record_reminder(decision.event_type, decision.message)
            if self.settings.care_enabled:
                self.care.entertainment_overtime()
            if self.settings.strong_mode_enabled:
                self._show_strong_reminder(decision.message, decision.countdown_seconds)
        elif classification.category == "study":
            self.bubble_text = self.character.line("study", "学习状态很好，继续。")
            self._study_care_seconds += duration
            if self.settings.care_enabled and self._study_care_seconds >= 30 * 60:
                units, self._study_care_seconds = divmod(self._study_care_seconds, 30 * 60)
                self.care.study_tick(units)
            report = self.storage.get_report_payload()
            goal_completed = bool(report["studyGoal"]["completed"])
            if goal_completed and not self._goal_completed_announced:
                self._goal_completed_announced = True
                self._play_action("study_complete", 4.0)
                self.bubble_text = "今天的学习目标完成了，做得漂亮！"
        elif classification.category == "entertainment":
            limit = max(1, self.settings.entertainment_limit_minutes * 60)
            ratio = self.reminder.entertainment_streak_seconds / limit
            if ratio >= 1.5:
                self._set_state("angry_strong")
            elif ratio >= 1:
                self._set_state("angry_soft")
            elif ratio >= 0.8:
                self._set_state("warning_soft")
                self._play_action("warning_soft", 2.0)
            else:
                self._set_state("idle_bored")
            self.bubble_text = self.character.line("entertainment", "娱乐时间在增加，注意阈值。")
        else:
            self.bubble_text = self.character.line("default", "我在记录今天的节奏。")

        if returned_from_idle:
            self._play_action("wake_up", 2.5)
            self.bubble_text = "欢迎回来，我们继续。"

        self.last_snapshot = snapshot
        self.last_classification = classification
        self.last_domain = classification.domain

    def _show_strong_reminder(self, message: str, countdown_seconds: int) -> None:
        dialog = StrongReminderDialog(message, countdown_seconds, self)
        self._dialogs.append(dialog)
        dialog.accepted.connect(self.start_study_mode)
        dialog.finished.connect(lambda _result, target=dialog: self._dialogs.remove(target) if target in self._dialogs else None)
        dialog.show()
        dialog.raise_()

    def start_study_mode(self) -> None:
        self.behavior.set_main_state("study_focus", interrupt=True)
        self._play_action("forgive", 2.5)
        self.bubble_text = self.dialogue.select("study_together")
        self.update()

    def emergency_pause(self, minutes: int | None = None) -> None:
        duration = self.settings.emergency_pause_minutes if minutes is None else max(1, int(minutes))
        self.reminder.emergency_pause(duration)
        self._set_state("nap")
        self.bubble_text = f"已暂停提醒 {duration} 分钟。"
        self.update()

    def sync_now(self) -> None:
        if self.sync_busy:
            return
        self.sync_busy = True
        self._play_action("syncing", 8.0)
        self.bubble_text = "正在同步..."
        worker = SyncWorker(self.sync)
        worker.signals.finished.connect(self._sync_finished)
        self.thread_pool.start(worker)
        self.update()

    def _sync_finished(self, ok: bool, message: str) -> None:
        self.sync_busy = False
        self.bubble_text = message
        self._play_action("sync_success" if ok else "sync_error", 3.0)
        if ok and self.tray.supportsMessages():
            self.tray.showMessage("桌宠同步", message, QSystemTrayIcon.Information, 2500)
        self.update()

    def open_settings(self, initial_tab: int = 0) -> None:
        dialog = SettingsDialog(
            self.settings,
            self.character_profiles,
            care_status=self.care.get_status(),
            invalid_packages=self._invalid_character_packages(),
            preview_callback=self.preview_character_action,
            switch_callback=self.switch_character,
            reload_callback=self.reload_characters,
            initial_tab=initial_tab,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        self.classifier = ActivityClassifier(self.settings)
        self.reminder = ReminderEngine(self.settings)
        self.sync = SyncClient(self.settings, self.storage)
        self.care = PetCareSystem(self.storage, self.settings.character_id)
        idle_interval = float(self.settings.random_idle_interval_seconds)
        self.behavior.random_idle_interval = (idle_interval, idle_interval * 1.8)
        self.sample_timer.setInterval(max(1, self.settings.sample_interval_seconds) * 1000)
        self.sync_timer.setInterval(max(15, self.settings.sync_interval_seconds) * 1000)
        self.storage.ensure_day()
        self.switch_character(self.settings.character_id)
        if not self.settings.hover_menu_enabled:
            self.hover_menu.hide()
        self.bubble_text = "设置已保存。"
        self.update()

    def reload_characters(self) -> tuple[dict[str, CharacterPackage], list[tuple[str, str]]]:
        self.character_registry.reload()
        self.character_profiles = self.character_registry.packages
        if self.settings.character_id not in self.character_profiles:
            self.switch_character("default_pet")
        return self.character_profiles, self._invalid_character_packages()

    def preview_character_action(self, character_id: str, action: str) -> None:
        original_id = self.character.character_id
        self._preview_generation += 1
        generation = self._preview_generation
        if character_id != original_id:
            self.switch_character(character_id, persist=False)
        actual = self._play_action(action, 3.2)
        self.bubble_text = f"预览 {action}" if actual == action else f"{action} fallback 到 {actual}"
        self.update()
        if character_id != original_id:
            QTimer.singleShot(
                3400,
                lambda: self.switch_character(original_id, persist=False)
                if generation == self._preview_generation
                else None,
            )

    def switch_character(self, character_id: str, persist: bool = True) -> None:
        profile = self.character_registry.get(character_id)
        if profile is None:
            return
        if persist:
            self._preview_generation += 1
        self.character = profile
        if persist:
            self.settings.character_id = profile.character_id
            save_character_id(profile.character_id)
        self.care = PetCareSystem(self.storage, profile.character_id)
        idle_interval = float(self.settings.random_idle_interval_seconds)
        self.behavior = PetBehaviorScheduler(
            profile.states,
            random_idle_interval=(idle_interval, idle_interval * 1.8),
        )
        self.dialogue = DialogueAgent(profile)
        self.current_state = self.behavior.state
        previous = self.renderer
        previous.shutdown()
        previous.hide()
        previous.deleteLater()
        self.renderer = self._make_renderer(profile)
        self.bubble_text = profile.line("default", "角色已切换。")
        self._set_state("idle_normal")
        self.update()

    def shutdown(self) -> None:
        self.sample_timer.stop()
        self.sync_timer.stop()
        self.behavior_timer.stop()
        self.care_timer.stop()
        self.click_timer.stop()
        self.greeting_timer.stop()
        self.renderer.shutdown()
        for dialog in tuple(self._dialogs):
            dialog.close()
        self.tray.hide()
        self.close()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._state_before_pointer_action = self.behavior.main_state
            self.press_global_position = event.globalPosition().toPoint()
            self.drag_moved = False
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.drag_position and event.buttons() & Qt.LeftButton:
            current = event.globalPosition().toPoint()
            if self.press_global_position and (current - self.press_global_position).manhattanLength() >= 5:
                if not self.drag_moved:
                    self.drag_moved = True
                    self.behavior.set_main_state("dragging", interrupt=True)
                    self._play_action("drag_start", 0.5)
                else:
                    self._render_action(self.behavior.set_main_state("dragging", interrupt=True))
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            super().mouseReleaseEvent(event)
            return
        was_dragged = self.drag_moved
        self.drag_position = None
        self.press_global_position = None
        self.drag_moved = False
        self.behavior.set_main_state(self._state_before_pointer_action, interrupt=True)
        if was_dragged:
            self._play_action("drag_end", 1.2)
        else:
            self.pending_click_position = event.globalPosition().toPoint()
            self.click_timer.start(QApplication.doubleClickInterval())
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.click_timer.stop()
            self.pending_click_position = None
            self._play_action("double_click", 2.0)
            self.bubble_text = self.dialogue.select("pet_head")
            self.update()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self._play_action("menu_open", 1.5)
        menu = self._full_menu()
        menu.exec(event.globalPos())
        menu.deleteLater()
        event.accept()

    def enterEvent(self, event) -> None:
        if self.settings.hover_menu_enabled:
            self._play_action("menu_hover", 1.0)
            self.hover_menu.reveal()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self.settings.hover_menu_enabled:
            self.hover_menu.hide_later()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._paint_bubble(painter)
        painter.end()

    def _paint_bubble(self, painter: QPainter) -> None:
        bubble_rect = QRectF(10, 10, 270, 78)
        painter.setPen(QColor("#dbe3ef"))
        painter.setBrush(QColor(255, 255, 255, 235))
        painter.drawRoundedRect(bubble_rect, 12, 12)
        painter.setPen(QColor("#334155"))
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(bubble_rect.adjusted(12, 8, -12, -8), Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, self.bubble_text)

def run_app(*, smoke_test: bool = False) -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    icon_path = RESOURCE_DIR / "assets" / "app.ico"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = PetWindow()
    app.aboutToQuit.connect(window.shutdown)
    window.show()

    if smoke_test:
        outcome = {"ready": False}

        def mark_ready(_status: object) -> None:
            outcome["ready"] = True
            QTimer.singleShot(300, lambda: app.exit(0))

        if isinstance(window.renderer, WebViewRenderer):
            window.renderer.renderer_ready.connect(mark_ready)
        QTimer.singleShot(12_000, lambda: app.exit(0 if outcome["ready"] else 3))

    return app.exec()
