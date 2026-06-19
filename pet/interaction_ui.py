from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .action_library import ACTION_CATEGORIES, ALL_ACTIONS, resolve_action


QUICK_ACTIONS = (
    ("pet_head", "摸头", "♥"),
    ("play", "玩耍", "▶"),
    ("feed", "喂食", "+"),
    ("study_together", "学习", "✓"),
    ("settings", "设置", "⚙"),
)


class HoverQuickMenu(QFrame):
    action_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("hoverQuickMenu")
        self.setFixedSize(260, 48)
        self.setStyleSheet(
            "#hoverQuickMenu { background: rgba(255,255,255,235); border: 1px solid #cbd5e1; border-radius: 8px; }"
            "QToolButton { border: 0; color: #334155; font-size: 16px; padding: 0; }"
            "QToolButton:hover { background: #e2e8f0; border-radius: 6px; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)
        for action, label, symbol in QUICK_ACTIONS:
            button = QToolButton(self)
            button.setText(symbol)
            button.setToolTip(label)
            button.setFixedSize(QSize(46, 38))
            button.clicked.connect(lambda _checked=False, name=action: self.action_requested.emit(name))
            layout.addWidget(button)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self.hide()

    def reveal(self) -> None:
        self._hide_timer.stop()
        self.show()
        self.raise_()

    def hide_later(self, delay_ms: int = 900) -> None:
        self._hide_timer.start(max(100, int(delay_ms)))

    def enterEvent(self, event) -> None:
        self._hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.hide_later()
        super().leaveEvent(event)


class CareStatusView(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._bars: dict[str, QProgressBar] = {}
        labels = {
            "mood": "心情",
            "affection": "亲密度",
            "hunger": "饥饿度",
            "energy": "精力",
            "discipline": "自律值",
        }
        form = QFormLayout(self)
        for key, label in labels.items():
            bar = QProgressBar(self)
            bar.setRange(0, 100)
            bar.setFormat("%v / 100")
            bar.setFixedHeight(18)
            self._bars[key] = bar
            form.addRow(label, bar)

    def set_status(self, status: Any) -> None:
        for key, bar in self._bars.items():
            value = status.get(key, 0) if isinstance(status, Mapping) else getattr(status, key, 0)
            bar.setValue(max(0, min(100, int(value or 0))))


class PetStatusDialog(QDialog):
    def __init__(self, status: Any, report: Mapping[str, Any], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("桌宠状态")
        self.setMinimumWidth(420)
        care = CareStatusView(self)
        care.set_status(status)
        study = int(report.get("studySeconds", 0))
        entertainment = int(report.get("entertainmentSeconds", 0))
        summary = QLabel(
            f"今日学习 {_duration(study)}　娱乐 {_duration(entertainment)}\n"
            f"强提醒 {int(report.get('strongReminderCount', 0))} 次",
            self,
        )
        summary.setWordWrap(True)
        close_button = QPushButton("关闭", self)
        close_button.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(care)
        layout.addWidget(summary)
        layout.addWidget(close_button, alignment=Qt.AlignRight)


class CharacterPanel(QWidget):
    character_selected = Signal(str)
    preview_requested = Signal(str, str)
    reload_requested = Signal()

    def __init__(
        self,
        profiles: Mapping[str, Any],
        current_id: str,
        invalid_packages: list[tuple[str, str]] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.profiles = dict(profiles)
        self.invalid_packages = list(invalid_packages or [])
        self.preview = QLabel(self)
        self.preview.setFixedSize(128, 128)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("border: 1px solid #cbd5e1; background: #f8fafc;")
        self.character_list = QListWidget(self)
        self.character_list.setMinimumHeight(120)
        self.character_list.currentRowChanged.connect(self._render_character)
        self.metadata = QLabel(self)
        self.metadata.setWordWrap(True)
        self.action_category = QComboBox(self)
        for category in ACTION_CATEGORIES:
            self.action_category.addItem(category, category)
        self.action_name = QComboBox(self)
        self.action_category.currentIndexChanged.connect(self._load_actions)
        self.fallback = QLabel(self)
        self.fallback.setWordWrap(True)

        apply_button = QPushButton("应用角色", self)
        preview_button = QPushButton("预览动作", self)
        reload_button = QPushButton("重载角色", self)
        import_button = QPushButton("导入说明", self)
        apply_button.clicked.connect(self._apply)
        preview_button.clicked.connect(self._preview_action)
        reload_button.clicked.connect(self.reload_requested)
        import_button.clicked.connect(self._show_import_help)

        top = QHBoxLayout()
        top.addWidget(self.preview)
        top.addWidget(self.metadata, 1)
        actions = QHBoxLayout()
        actions.addWidget(self.action_category)
        actions.addWidget(self.action_name, 1)
        actions.addWidget(preview_button)
        buttons = QHBoxLayout()
        buttons.addWidget(apply_button)
        buttons.addWidget(reload_button)
        buttons.addWidget(import_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(QLabel("角色列表"))
        layout.addWidget(self.character_list)
        layout.addLayout(actions)
        layout.addWidget(self.fallback)
        layout.addLayout(buttons)
        self.set_profiles(self.profiles, current_id, self.invalid_packages)

    @property
    def selected_character_id(self) -> str:
        item = self.character_list.currentItem()
        return str(item.data(Qt.UserRole) or "") if item else ""

    def set_profiles(
        self,
        profiles: Mapping[str, Any],
        current_id: str,
        invalid_packages: list[tuple[str, str]] | None = None,
    ) -> None:
        self.profiles = dict(profiles)
        self.invalid_packages = list(invalid_packages or [])
        self.character_list.clear()
        selected_row = 0
        for row, (character_id, profile) in enumerate(
            sorted(self.profiles.items(), key=lambda item: item[1].display_name)
        ):
            self.character_list.addItem(profile.display_name)
            item = self.character_list.item(row)
            item.setData(Qt.UserRole, character_id)
            if character_id == current_id:
                selected_row = row
        offset = self.character_list.count()
        for index, (path, error) in enumerate(self.invalid_packages):
            self.character_list.addItem(f"无效：{path}")
            item = self.character_list.item(offset + index)
            item.setData(Qt.UserRole, "")
            item.setToolTip(error)
            item.setForeground(QColor("#dc2626"))
        if self.character_list.count():
            self.character_list.setCurrentRow(selected_row)
        self._load_actions()

    def _selected_profile(self) -> Any | None:
        return self.profiles.get(self.selected_character_id)

    def _render_character(self, _row: int) -> None:
        profile = self._selected_profile()
        if profile is None:
            item = self.character_list.currentItem()
            self.preview.clear()
            self.metadata.setText(item.toolTip() if item else "角色包无效")
            self.fallback.clear()
            return
        image_path = getattr(profile, "preview", None) or getattr(profile, "skin", None)
        pixmap = QPixmap(str(image_path)) if image_path else QPixmap()
        if pixmap.isNull():
            self.preview.setText("无预览图")
        else:
            self.preview.setPixmap(pixmap.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        supported = set(getattr(profile, "supported_states", ()) or getattr(profile, "states", {}).keys())
        missing = max(0, len(set(ALL_ACTIONS) - supported))
        self.metadata.setText(
            f"{profile.display_name}\n"
            f"Renderer：{profile.renderer}　版本：{getattr(profile, 'version', '1.0.0')}\n"
            f"作者：{getattr(profile, 'author', 'unknown')}\n"
            f"支持动作：{len(supported)}　缺失动作：{missing}\n"
            f"{getattr(profile, 'description', '')}"
        )
        self._describe_fallback()

    def _load_actions(self) -> None:
        category = str(self.action_category.currentData() or "idle")
        self.action_name.clear()
        for action in ACTION_CATEGORIES.get(category, ()):
            self.action_name.addItem(action, action)
        self._describe_fallback()

    def _describe_fallback(self) -> None:
        profile = self._selected_profile()
        action = str(self.action_name.currentData() or "")
        if not profile or not action:
            self.fallback.clear()
            return
        resolution = resolve_action(getattr(profile, "states", {}).keys(), action)
        actual = getattr(resolution, "resolved", getattr(resolution, "actual", action))
        if actual == action:
            self.fallback.setText(f"该角色原生支持：{action}")
        else:
            self.fallback.setText(f"预览时将 fallback：{action} → {actual}")

    def _apply(self) -> None:
        if self.selected_character_id:
            self.character_selected.emit(self.selected_character_id)

    def _preview_action(self) -> None:
        character_id = self.selected_character_id
        action = str(self.action_name.currentData() or "")
        if character_id and action:
            self.preview_requested.emit(character_id, action)
            self._describe_fallback()

    def _show_import_help(self) -> None:
        QMessageBox.information(
            self,
            "导入角色包",
            "把完整角色目录放入 characters/<角色ID>/ 后点击“重载角色”。\n\n"
            "基础文件：character.json、preview.png。\n"
            "Skin Rig 角色还需要 skin.png、atlas.json、rig.json、animations.json。\n"
            "打包版目录位于 StudyPet/_internal/characters/。请只使用你有权使用的素材。",
        )


def _duration(seconds: int) -> str:
    hours, rest = divmod(max(0, int(seconds)), 3600)
    minutes = rest // 60
    return f"{hours}小时{minutes}分钟" if hours else f"{minutes}分钟"
