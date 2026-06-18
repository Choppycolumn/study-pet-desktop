from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRectF, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QMouseEvent, QPainter, QPixmap
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
    QVBoxLayout,
    QWidget,
)

from .character import CharacterPackage, CharacterPackageLoader
from .classifier import ActivityClassifier, Classification
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
    def __init__(self, settings: PetSettings, profiles: dict[str, CharacterPackage], parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("桌宠设置")
        self.setMinimumWidth(520)

        self.server_url = QLineEdit(settings.server_url)
        self.api_token = QLineEdit(settings.api_token)
        self.api_token.setEchoMode(QLineEdit.Password)
        self.character = QComboBox()
        for character_id, profile in sorted(profiles.items(), key=lambda item: item[1].display_name):
            self.character.addItem(profile.display_name, character_id)
        selected = self.character.findData(settings.character_id)
        if selected >= 0:
            self.character.setCurrentIndex(selected)

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

        form = QFormLayout()
        form.addRow("网站地址", self.server_url)
        form.addRow("API Token", self.api_token)
        form.addRow("角色", self.character)
        form.addRow("每日学习目标", self.target_study)
        form.addRow("娱乐提醒阈值", self.entertainment_limit)
        form.addRow("空闲判定", self.idle_threshold)
        form.addRow("强提醒模式", self.strong_mode)
        form.addRow("提醒语气", self.reminder_tone)
        form.addRow("学习网站", self.study_domains)
        form.addRow("娱乐网站", self.entertainment_domains)
        form.addRow("学习关键词", self.study_keywords)
        form.addRow("娱乐关键词", self.entertainment_keywords)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def accept(self) -> None:
        self.settings.server_url = self.server_url.text().strip().rstrip("/")
        self.settings.api_token = self.api_token.text().strip()
        self.settings.character_id = str(self.character.currentData() or "default_pet")
        self.settings.target_study_minutes = self.target_study.value()
        self.settings.entertainment_limit_minutes = self.entertainment_limit.value()
        self.settings.idle_threshold_seconds = self.idle_threshold.value()
        self.settings.strong_mode_enabled = self.strong_mode.isChecked()
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
        self.character_profiles = self._load_character_profiles()
        self.character = self.character_profiles.get(self.settings.character_id)
        if self.character is None:
            self.character = self.character_profiles.get("default_pet") or next(iter(self.character_profiles.values()))
            self.settings.character_id = self.character.character_id
        self.storage = PetStorage(self.settings)
        self.monitor = ActivityMonitor()
        self.classifier = ActivityClassifier(self.settings)
        self.reminder = ReminderEngine(self.settings)
        self.sync = SyncClient(self.settings, self.storage)
        self.thread_pool = QThreadPool.globalInstance()
        self.sync_busy = False
        self._dialogs: list[StrongReminderDialog] = []

        self.drag_position: QPoint | None = None
        self.bubble_text = self.character.line("default", "我在这里，开始记录。")
        self.current_state = "idle"
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

        self._setup_tray()

        self.sample_timer = QTimer(self)
        self.sample_timer.timeout.connect(self._sample)
        self.sample_timer.start(max(1, self.settings.sample_interval_seconds) * 1000)

        self.sync_timer = QTimer(self)
        self.sync_timer.timeout.connect(self.sync_now)
        self.sync_timer.start(max(15, self.settings.sync_interval_seconds) * 1000)

        self.storage.ensure_day()

    @staticmethod
    def _load_character_profiles() -> dict[str, CharacterPackage]:
        root = RESOURCE_DIR / "characters"
        loader = CharacterPackageLoader(emit_warnings=False)
        profiles: dict[str, CharacterPackage] = {}
        for manifest in sorted(root.glob("*/character.json")):
            package = loader.load(manifest)
            profiles[package.character_id] = package
        if not profiles:
            raise RuntimeError(f"No character packages were found in {root}")
        return profiles

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
        sync_action = QAction("立即同步", self)
        pause_action = QAction("紧急暂停提醒", self)
        settings_action = QAction("设置", self)
        show_action = QAction("显示桌宠", self)
        quit_action = QAction("退出", self)
        sync_action.triggered.connect(self.sync_now)
        pause_action.triggered.connect(self.emergency_pause)
        settings_action.triggered.connect(self.open_settings)
        show_action.triggered.connect(self.showNormal)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(sync_action)
        menu.addAction(pause_action)
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

    def _set_state(self, state: str) -> None:
        self.current_state = state
        self.renderer.set_state(state)

    def _sample(self) -> None:
        snapshot = self.monitor.current()
        classification = self.classifier.classify(snapshot)
        duration = self.settings.sample_interval_seconds
        if snapshot.idle_seconds >= self.settings.idle_threshold_seconds:
            duration = 0
            self._set_state("sleep")
        else:
            self._set_state(classification.category)

        site_visit = bool(classification.domain and classification.domain != self.last_domain)
        self.storage.record_activity(snapshot, classification, duration, site_visit=site_visit)
        decision = self.reminder.update(classification, duration)
        if decision.trigger:
            self._set_state("angry")
            self.bubble_text = self.character.line("strong", decision.message)
            self.storage.record_reminder(decision.event_type, decision.message)
            if self.settings.strong_mode_enabled:
                self._show_strong_reminder(decision.message, decision.countdown_seconds)
        elif classification.category == "study":
            self.bubble_text = self.character.line("study", "学习状态很好，继续。")
        elif classification.category == "entertainment":
            self.bubble_text = self.character.line("entertainment", "娱乐时间在增加，注意阈值。")
        else:
            self.bubble_text = self.character.line("default", "我在记录今天的节奏。")

        self.last_snapshot = snapshot
        self.last_classification = classification
        self.last_domain = classification.domain

    def _show_strong_reminder(self, message: str, countdown_seconds: int) -> None:
        dialog = StrongReminderDialog(message, countdown_seconds, self)
        self._dialogs.append(dialog)
        dialog.accepted.connect(lambda: self._set_state("study"))
        dialog.finished.connect(lambda _result, target=dialog: self._dialogs.remove(target) if target in self._dialogs else None)
        dialog.show()
        dialog.raise_()

    def emergency_pause(self) -> None:
        self.reminder.emergency_pause()
        self._set_state("sleep")
        self.bubble_text = f"已暂停提醒 {self.settings.emergency_pause_minutes} 分钟。"
        self.update()

    def sync_now(self) -> None:
        if self.sync_busy:
            return
        self.sync_busy = True
        self._set_state("syncing")
        self.bubble_text = "正在同步..."
        worker = SyncWorker(self.sync)
        worker.signals.finished.connect(self._sync_finished)
        self.thread_pool.start(worker)
        self.update()

    def _sync_finished(self, ok: bool, message: str) -> None:
        self.sync_busy = False
        self.bubble_text = message
        self._set_state("happy" if ok else "error")
        if ok and self.tray.supportsMessages():
            self.tray.showMessage("桌宠同步", message, QSystemTrayIcon.Information, 2500)
        self.update()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.character_profiles, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.classifier = ActivityClassifier(self.settings)
        self.reminder = ReminderEngine(self.settings)
        self.sync = SyncClient(self.settings, self.storage)
        self.sample_timer.setInterval(max(1, self.settings.sample_interval_seconds) * 1000)
        self.sync_timer.setInterval(max(15, self.settings.sync_interval_seconds) * 1000)
        self.storage.ensure_day()
        self.switch_character(self.settings.character_id)
        self.bubble_text = "设置已保存。"
        self.update()

    def switch_character(self, character_id: str) -> None:
        profile = self.character_profiles.get(character_id)
        if not profile:
            return
        self.character = profile
        self.settings.character_id = character_id
        save_character_id(character_id)
        previous = self.renderer
        previous.shutdown()
        previous.hide()
        previous.deleteLater()
        self.renderer = self._make_renderer(profile)
        self.bubble_text = profile.line("default", "角色已切换。")
        self._set_state("idle")
        self.update()

    def shutdown(self) -> None:
        self.sample_timer.stop()
        self.sync_timer.stop()
        self.renderer.shutdown()
        for dialog in tuple(self._dialogs):
            dialog.close()
        self.tray.hide()
        self.close()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._state_before_pointer_action = self.current_state
            self._set_state("drag")
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.drag_position and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.drag_position = None
        self._set_state("click")
        QTimer.singleShot(260, lambda: self._set_state(self._state_before_pointer_action))
        event.accept()

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
