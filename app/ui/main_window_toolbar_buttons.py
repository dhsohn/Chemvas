from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPolygonF
from PyQt6.QtWidgets import QMenu, QToolButton

from ui.main_window_palette import PALETTE
from ui.main_window_theme import TOOLBAR_MENU_BUTTON_STYLE


class ArrowButton(QToolButton):
    def __init__(self, direction: str, parent=None) -> None:
        super().__init__(parent)
        self._direction = direction
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PALETTE["text_muted"]))
        rect = self.rect().adjusted(6, 4, -6, -4)
        if rect.width() <= 0 or rect.height() <= 0:
            return
        if self._direction == "up":
            points = [
                QPointF(rect.center().x(), rect.top()),
                QPointF(rect.right(), rect.bottom()),
                QPointF(rect.left(), rect.bottom()),
            ]
        else:
            points = [
                QPointF(rect.left(), rect.top()),
                QPointF(rect.right(), rect.top()),
                QPointF(rect.center().x(), rect.bottom()),
            ]
        painter.drawPolygon(QPolygonF(points))


class CornerMenuButton(QToolButton):
    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PALETTE["text_faint"]))
        rect = self.rect()
        size = 6
        right = rect.right() - 2
        bottom = rect.bottom() - 2
        left = right - size
        top = bottom - size
        points = [
            QPointF(right, bottom),
            QPointF(left, bottom),
            QPointF(right, top),
        ]
        painter.drawPolygon(QPolygonF(points))


class CornerMenuToolButton(CornerMenuButton):
    """A corner-chevron button where only the bottom-right chevron opens the menu;
    clicking anywhere else triggers the default action (e.g. selecting the tool)."""

    _CORNER_ZONE = 14

    def _is_in_corner(self, pos) -> bool:
        return pos.x() >= self.width() - self._CORNER_ZONE and pos.y() >= self.height() - self._CORNER_ZONE

    def mousePressEvent(self, event) -> None:
        if self.menu() is not None and self._is_in_corner(event.position().toPoint()):
            self.showMenu()
            event.accept()
            return
        super().mousePressEvent(event)


class MainWindowToolbarButtonFactory:
    def create_toolbar_button(
        self,
        *,
        icon: QIcon | None = None,
        tooltip: str | None = None,
        status_tip: str | None = None,
        callback: Callable[[], None] | None = None,
        shortcut=None,
        text: str | None = None,
        object_name: str | None = None,
        style_sheet: str | None = None,
        auto_raise: bool = True,
        cursor=None,
    ) -> QToolButton:
        button = QToolButton()
        if icon is not None:
            button.setIcon(icon)
        if tooltip is not None:
            button.setToolTip(tooltip)
        resolved_status_tip = status_tip if status_tip is not None else tooltip
        if resolved_status_tip is not None:
            button.setStatusTip(resolved_status_tip)
        if shortcut is not None:
            button.setShortcut(shortcut)
        if text is not None:
            button.setText(text)
        if object_name is not None:
            button.setObjectName(object_name)
        if style_sheet is not None:
            button.setStyleSheet(style_sheet)
        button.setAutoRaise(auto_raise)
        if cursor is not None:
            button.setCursor(cursor)
        if callback is not None:
            button.clicked.connect(callback)
        return button

    def create_corner_menu_button(
        self,
        *,
        icon: QIcon | None = None,
        tooltip: str | None = None,
        status_tip: str | None = None,
        style_sheet: str,
        popup_mode: QToolButton.ToolButtonPopupMode,
        menu_builder: Callable[[QMenu], None],
        default_action: QAction | None = None,
    ) -> CornerMenuButton:
        button = CornerMenuButton()
        if default_action is not None:
            button.setDefaultAction(default_action)
        elif icon is not None:
            button.setIcon(icon)
        if tooltip is not None:
            button.setToolTip(tooltip)
        resolved_status_tip = status_tip if status_tip is not None else tooltip
        if resolved_status_tip is not None:
            button.setStatusTip(resolved_status_tip)
        button.setPopupMode(popup_mode)
        button.setStyleSheet(style_sheet)
        menu = QMenu(button)
        menu_builder(menu)
        button.setMenu(menu)
        return button

    def create_save_menu_button(self, save_action: QAction, save_as_action: QAction) -> CornerMenuButton:
        return self.create_corner_menu_button(
            tooltip=save_action.toolTip(),
            status_tip=save_action.statusTip() or save_action.toolTip(),
            style_sheet=TOOLBAR_MENU_BUTTON_STYLE,
            popup_mode=QToolButton.ToolButtonPopupMode.MenuButtonPopup,
            menu_builder=lambda menu: menu.addAction(save_as_action),
            default_action=save_action,
        )

    def create_file_project_menu_button(
        self,
        save_action: QAction,
        load_action: QAction,
        save_as_action: QAction,
        *export_actions: QAction,
    ) -> CornerMenuButton:
        def build_menu(menu: QMenu) -> None:
            menu.addAction(load_action)
            menu.addAction(save_action)
            menu.addAction(save_as_action)
            if export_actions:
                menu.addSeparator()
                for export_action in export_actions:
                    menu.addAction(export_action)

        return self.create_corner_menu_button(
            tooltip="File",
            status_tip="Save, load, export, or save as the current file",
            style_sheet=TOOLBAR_MENU_BUTTON_STYLE,
            popup_mode=QToolButton.ToolButtonPopupMode.MenuButtonPopup,
            menu_builder=build_menu,
            default_action=save_action,
        )


__all__ = [
    "ArrowButton",
    "CornerMenuButton",
    "CornerMenuToolButton",
    "MainWindowToolbarButtonFactory",
]
