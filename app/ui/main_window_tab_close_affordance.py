from __future__ import annotations

from PyQt6.QtCore import QEvent, QLineF, QObject, QRectF, Qt
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import QProxyStyle, QStyle, QStyleOption, QTabBar, QWidget

from ui.main_window_palette import PALETTE


def close_button_position(tab_bar: QTabBar) -> QTabBar.ButtonPosition:
    style = tab_bar.style()
    if style is None:
        return QTabBar.ButtonPosition.RightSide
    hint = style.styleHint(QStyle.StyleHint.SH_TabBar_CloseButtonPosition, None, tab_bar)
    return QTabBar.ButtonPosition(hint)


def visible_close_indices(*, count: int, current_index: int, hovered_index: int) -> set[int]:
    indices: set[int] = set()
    if 0 <= current_index < count:
        indices.add(current_index)
    if 0 <= hovered_index < count:
        indices.add(hovered_index)
    return indices


def apply_close_button_visibility(tab_bar: QTabBar, *, hovered_index: int) -> None:
    position = close_button_position(tab_bar)
    visible = visible_close_indices(
        count=tab_bar.count(),
        current_index=tab_bar.currentIndex(),
        hovered_index=hovered_index,
    )
    for index in range(tab_bar.count()):
        button = tab_bar.tabButton(index, position)
        if button is not None:
            button.setVisible(index in visible)


class CanvasTabCloseButtonStyle(QProxyStyle):
    """Draw the tab close affordance as a thin, calm glyph.

    The platform default renders a heavy boxed glyph (and an alarming red box
    on the active tab). Painting ``PE_IndicatorTabClose`` ourselves keeps the
    close button consistent with the app's icon set and warm-gray palette while
    leaving every other primitive to the base style.
    """

    _GLYPH = QColor(PALETTE["icon_muted"])
    _GLYPH_ACTIVE = QColor(PALETTE["icon"])
    _HOVER_BG = QColor(PALETTE["hover"])
    _PRESSED_BG = QColor(PALETTE["pressed"])

    def drawPrimitive(  # noqa: N802 - Qt override name
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption | None,
        painter: QPainter | None,
        widget: QWidget | None = None,
    ) -> None:
        if element == QStyle.PrimitiveElement.PE_IndicatorTabClose and option is not None and painter is not None:
            self._draw_close_indicator(option, painter)
            return
        super().drawPrimitive(element, option, painter, widget)

    def _draw_close_indicator(self, option: QStyleOption, painter: QPainter) -> None:
        rect = QRectF(option.rect)
        side = min(rect.width(), rect.height())
        if side <= 0:
            return
        state = option.state
        hovered = bool(state & QStyle.StateFlag.State_MouseOver)
        pressed = bool(state & QStyle.StateFlag.State_Sunken)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        center = rect.center()
        chip = QRectF(center.x() - side / 2, center.y() - side / 2, side, side)
        if pressed or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._PRESSED_BG if pressed else self._HOVER_BG)
            painter.drawRoundedRect(chip, 4.0, 4.0)

        inset = side * 0.32
        glyph = chip.adjusted(inset, inset, -inset, -inset)
        pen = QPen(self._GLYPH_ACTIVE if (hovered or pressed) else self._GLYPH)
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QLineF(glyph.topLeft(), glyph.bottomRight()))
        painter.drawLine(QLineF(glyph.bottomLeft(), glyph.topRight()))
        painter.restore()


class CanvasTabCloseAffordance(QObject):
    """Reveal a tab's close button only while it is current or hovered.

    The close-indicator slot is always reserved by the style, so toggling the
    button's visibility keeps tab widths stable while removing the persistent
    row of close glyphs that made the strip read as spreadsheet chrome. Each
    button is also restyled with :class:`CanvasTabCloseButtonStyle` so the glyph
    matches the app's icon set rather than the platform default.
    """

    def __init__(self, tab_bar: QTabBar) -> None:
        super().__init__(tab_bar)
        self._tab_bar = tab_bar
        self._hovered_index = -1
        self._close_style = CanvasTabCloseButtonStyle()
        self._close_style.setParent(self)
        tab_bar.setMouseTracking(True)
        tab_bar.installEventFilter(self)
        tab_bar.currentChanged.connect(self._on_current_changed)
        self.refresh()

    @property
    def hovered_index(self) -> int:
        return self._hovered_index

    def refresh(self) -> None:
        position = close_button_position(self._tab_bar)
        for index in range(self._tab_bar.count()):
            button = self._tab_bar.tabButton(index, position)
            if button is not None and not isinstance(button.style(), CanvasTabCloseButtonStyle):
                button.setStyle(self._close_style)
        apply_close_button_visibility(self._tab_bar, hovered_index=self._hovered_index)

    def _on_current_changed(self, _index: int) -> None:
        self.refresh()

    def _set_hovered_index(self, index: int) -> None:
        if index != self._hovered_index:
            self._hovered_index = index
            self.refresh()

    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:  # noqa: N802
        if a1 is None:
            return super().eventFilter(a0, a1)
        event_type = a1.type()
        if event_type == QEvent.Type.MouseMove and isinstance(a1, QMouseEvent):
            self._set_hovered_index(self._tab_bar.tabAt(a1.position().toPoint()))
        elif event_type == QEvent.Type.Leave:
            self._set_hovered_index(-1)
        elif event_type == QEvent.Type.ChildPolished:
            self.refresh()
        return super().eventFilter(a0, a1)


__all__ = [
    "CanvasTabCloseAffordance",
    "CanvasTabCloseButtonStyle",
    "apply_close_button_visibility",
    "close_button_position",
    "visible_close_indices",
]
