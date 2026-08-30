from __future__ import annotations

from typing import TYPE_CHECKING, override

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPolygonF
from PyQt6.QtWidgets import QToolButton

from chemvas.shell.palette import PALETTE

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QCursor, QKeySequence, QMouseEvent, QPaintEvent
    from PyQt6.QtWidgets import QWidget


class ArrowButton(QToolButton):
    def __init__(self, direction: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._direction = direction
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    @override
    def paintEvent(self, event: QPaintEvent | None) -> None:
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
    @override
    def paintEvent(self, event: QPaintEvent | None) -> None:
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

    def _is_in_corner(self, pos: QPoint) -> bool:
        return (
            pos.x() >= self.width() - self._CORNER_ZONE
            and pos.y() >= self.height() - self._CORNER_ZONE
        )

    @override
    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if (
            event is not None
            and self.menu() is not None
            and self._is_in_corner(event.position().toPoint())
        ):
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
        shortcut: QKeySequence | QKeySequence.StandardKey | str | None = None,
        text: str | None = None,
        object_name: str | None = None,
        style_sheet: str | None = None,
        auto_raise: bool = True,
        cursor: QCursor | Qt.CursorShape | None = None,
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


__all__ = [
    "ArrowButton",
    "CornerMenuButton",
    "CornerMenuToolButton",
    "MainWindowToolbarButtonFactory",
]
