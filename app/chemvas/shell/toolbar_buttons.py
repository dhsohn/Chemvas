from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, override

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter
from PyQt6.QtWidgets import QToolButton

if TYPE_CHECKING:
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QMouseEvent, QPaintEvent
    from PyQt6.QtWidgets import QWidget


def _chevron_icon(direction: str) -> QIcon:
    icons = Path(__file__).resolve().parents[1] / "assets" / "icon"
    icon = QIcon(str(icons / f"chevron-{direction}.svg"))
    icon.addFile(
        str(icons / f"chevron-{direction}-disabled.svg"), QSize(), QIcon.Mode.Disabled
    )
    return icon


class ActionToolButton(QToolButton):
    """QToolButton whose default QAction triggers when accessibility checks it.

    Qt's accessibility toggle calls ``toggle()``/``setChecked()`` and syncs through
    ``checkStateSet`` without emitting ``QAction::triggered``. A mouse click uses
    ``nextCheckState()`` which does trigger the action.
    """

    @override
    def checkStateSet(self) -> None:
        action = self.defaultAction()
        if (
            self.isChecked()
            and action is not None
            and action.isCheckable()
            and not action.isChecked()
        ):
            action.trigger()
            return
        super().checkStateSet()


class CheckableOptionToolButton(ActionToolButton):
    """Checkable toolbar option without a default QAction (context bar)."""

    @override
    def toggle(self) -> None:
        if self.signalsBlocked():
            super().toggle()
            return
        if not self.isChecked():
            self.click()
            return
        super().toggle()


class ArrowButton(QToolButton):
    def __init__(self, direction: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(_chevron_icon(direction))
        self.setIconSize(QSize(12, 12))


class CornerMenuButton(ActionToolButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._menu_chevron = _chevron_icon("down")

    @override
    def paintEvent(self, event: QPaintEvent | None) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        self._menu_chevron.paint(
            painter,
            QRect(self.width() - 11, self.height() - 10, 10, 10),
            Qt.AlignmentFlag.AlignCenter,
            QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled,
        )


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
            and (
                event.button() == Qt.MouseButton.RightButton
                or self._is_in_corner(event.position().toPoint())
            )
        ):
            self.showMenu()
            event.accept()
            return
        super().mousePressEvent(event)


__all__ = [
    "ActionToolButton",
    "ArrowButton",
    "CheckableOptionToolButton",
    "CornerMenuButton",
    "CornerMenuToolButton",
]
