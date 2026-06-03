from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSlider,
    QStackedWidget,
    QToolBar,
    QToolButton,
    QWidget,
)

from ui.main_window_config import ARROW_MENU_SPECS, ARROW_PRESET_SPECS, TEMPLATE_ENTRY_SPECS
from ui.main_window_theme import TOOLBAR_BUTTON_STYLE
from ui.main_window_toolbar_logic import BOND_STYLE_BY_LABEL

# Maps the active canvas tool name to the context page key shown in the bar.
_TOOL_PAGE_KEYS = {
    "bond": "bond",
    "arrow": "arrow",
    "text": "atom",
    "benzene": "ring",
    "template": "template",
}

# Every entry sets a single active bond style, so they form one exclusive group.
_BOND_SEGMENTS = [
    ("Single", "icon_bond", "Single bond (1)"),
    ("Double", "icon_bond_double", "Double bond (2)"),
    ("Triple", "icon_bond_triple", "Triple bond (3)"),
    ("Bold", "icon_bond_bold", "Bold bond (B)"),
    ("Wedge", "icon_bond_wedge", "Wedge bond (W)"),
    ("Hash", "icon_bond_hash", "Hash bond (Shift+H)"),
    ("Dotted", "icon_bond_dotted", "Dotted bond"),
]

# (style, order) -> segment label, for reflecting the canvas state.
_LABEL_BY_STYLE = {value: label for label, value in BOND_STYLE_BY_LABEL.items()}

_ICON_SIZE = QSize(22, 22)


class MainWindowContextBarService:
    """Builds and updates the tool-sensitive options toolbar."""

    def __init__(self) -> None:
        self._stack: QStackedWidget | None = None
        self._pages: dict[str, QWidget] = {}
        self._bond_group: QButtonGroup | None = None
        self._bond_buttons: dict[str, QToolButton] = {}
        self._arrow_group: QButtonGroup | None = None
        self._arrow_buttons: dict[str, QToolButton] = {}

    def init_context_bar(self, window) -> QToolBar:
        bar = QToolBar("Options", window)
        bar.setObjectName("contextOptionsBar")
        bar.setMovable(False)
        bar.setFloatable(False)

        stack = QStackedWidget()
        self._stack = stack
        self._pages = {
            "empty": self._build_empty_page(),
            "bond": self._build_bond_page(window),
            "template": self._build_template_page(window),
            "arrow": self._build_arrow_page(window),
            "atom": self._build_atom_page(window),
            "ring": self._build_ring_page(window),
        }
        for page in self._pages.values():
            stack.addWidget(page)
        stack.setCurrentWidget(self._pages["empty"])
        bar.addWidget(stack)

        window.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
        window.addToolBar(Qt.ToolBarArea.TopToolBarArea, bar)
        return bar

    def refresh(self, window, tool: str | None, *, page_key: str | None = None) -> None:
        if self._stack is None:
            return
        key = page_key or _TOOL_PAGE_KEYS.get(tool or "", "empty")
        page = self._pages.get(key, self._pages["empty"])
        self._stack.setCurrentWidget(page)
        if key == "bond":
            self.reflect_state(window)
        elif key == "arrow":
            self.reflect_arrow_state(window)

    def reflect_state(self, window) -> None:
        if not self._bond_buttons or self._bond_group is None:
            return
        canvas = window._active_canvas_or_none()
        if canvas is None:
            return
        key = (
            canvas.active_bond_style,
            canvas.active_bond_order,
        )
        label = _LABEL_BY_STYLE.get(key)
        target = self._bond_buttons.get(label)
        self._bond_group.setExclusive(False)
        for button in self._bond_buttons.values():
            blocked = button.blockSignals(True)
            button.setChecked(button is target)
            button.blockSignals(blocked)
        self._bond_group.setExclusive(True)

    def reflect_arrow_state(self, window) -> None:
        if not self._arrow_buttons or self._arrow_group is None:
            return
        canvas = window._active_canvas_or_none()
        if canvas is None:
            return
        target = self._arrow_buttons.get(canvas.active_arrow_type)
        self._arrow_group.setExclusive(False)
        for button in self._arrow_buttons.values():
            blocked = button.blockSignals(True)
            button.setChecked(button is target)
            button.blockSignals(blocked)
        self._arrow_group.setExclusive(True)

    # -- page builders -------------------------------------------------

    @staticmethod
    def _new_page() -> tuple[QWidget, QHBoxLayout]:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(3)
        return page, layout

    @staticmethod
    def _hint_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("toolbarSectionLabel")
        return label

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFixedHeight(18)
        line.setStyleSheet("color: #e0e0dd;")
        return line

    @staticmethod
    def _icon_button(icon, tooltip: str, *, checkable: bool = False) -> QToolButton:
        button = QToolButton()
        button.setIcon(icon)
        button.setIconSize(_ICON_SIZE)
        button.setToolTip(tooltip)
        button.setAutoRaise(True)
        button.setCheckable(checkable)
        button.setStyleSheet(TOOLBAR_BUTTON_STYLE)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    @staticmethod
    def _text_button(text: str, tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setAutoRaise(True)
        button.setStyleSheet(TOOLBAR_BUTTON_STYLE)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _build_empty_page(self) -> QWidget:
        page, layout = self._new_page()
        layout.addWidget(self._hint_label("Select a tool to see its options here"))
        layout.addStretch(1)
        return page

    def _build_bond_page(self, window) -> QWidget:
        page, layout = self._new_page()

        group = QButtonGroup(page)
        group.setExclusive(True)
        self._bond_group = group
        self._bond_buttons = {}
        for label, icon_method, tip in _BOND_SEGMENTS:
            button = self._icon_button(getattr(window._icon_factory, icon_method)(), tip, checkable=True)
            button.clicked.connect(lambda _checked, v=label: window._activate_bond_style_tool(v))
            group.addButton(button)
            self._bond_buttons[label] = button
            layout.addWidget(button)

        layout.addWidget(self._divider())
        length_button = self._icon_button(window._icon_factory.icon_bond_length(), "Set the default bond length")
        length_button.clicked.connect(window._set_bond_length)
        layout.addWidget(length_button)
        layout.addStretch(1)
        return page

    def _build_template_page(self, window) -> QWidget:
        page, layout = self._new_page()
        for label, ring_size, style in TEMPLATE_ENTRY_SPECS:
            button = self._icon_button(window._icon_factory.icon_template_preview(label), label)
            button.clicked.connect(
                lambda _checked=False, n=ring_size, s=style: window.canvas.begin_ring_template_insert(
                    n,
                    style=s,
                )
            )
            layout.addWidget(button)
        layout.addStretch(1)
        return page

    def _build_arrow_page(self, window) -> QWidget:
        page, layout = self._new_page()

        group = QButtonGroup(page)
        group.setExclusive(True)
        self._arrow_group = group
        self._arrow_buttons = {}
        for label, value in ARROW_MENU_SPECS:
            button = self._icon_button(window._icon_factory.icon_arrow_preview(value), label, checkable=True)
            button.clicked.connect(lambda _checked, v=label: window._set_arrow_type(v))
            group.addButton(button)
            self._arrow_buttons[value] = button
            layout.addWidget(button)

        layout.addWidget(self._divider())
        layout.addWidget(self._hint_label("Preset"))
        for label in ARROW_PRESET_SPECS:
            button = self._text_button(label, f"{label} arrow preset")
            button.clicked.connect(lambda _checked=False, v=label: window._set_arrow_preset(v))
            layout.addWidget(button)

        layout.addWidget(self._divider())
        layout.addWidget(self._hint_label("Width"))
        width = QSlider(Qt.Orientation.Horizontal)
        width.setMinimum(1)
        width.setMaximum(6)
        width.setFixedWidth(84)
        width.setValue(int(window.canvas.get_arrow_line_width()))
        width.valueChanged.connect(lambda v: window.canvas.set_arrow_line_width(v))
        layout.addWidget(width)

        layout.addWidget(self._hint_label("Head"))
        head = QSlider(Qt.Orientation.Horizontal)
        head.setMinimum(10)
        head.setMaximum(60)
        head.setFixedWidth(84)
        head.setValue(int(window.canvas.get_arrow_head_scale() * 100))
        head.valueChanged.connect(lambda v: window.canvas.set_arrow_head_scale(v / 100.0))
        layout.addWidget(head)

        layout.addStretch(1)
        return page

    def _build_atom_page(self, window) -> QWidget:
        page, layout = self._new_page()
        layout.addWidget(
            self._hint_label("Element hotkeys: c n o s p f h · edit label Enter · charge +/-")
        )
        layout.addStretch(1)
        return page

    def _build_ring_page(self, window) -> QWidget:
        page, layout = self._new_page()
        layout.addWidget(self._hint_label("Benzene ring"))
        layout.addStretch(1)
        return page


__all__ = ["MainWindowContextBarService"]
