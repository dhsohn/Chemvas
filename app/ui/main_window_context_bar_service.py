from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSlider,
    QStackedWidget,
    QToolBar,
    QToolButton,
    QWidget,
)

from ui.main_window_config import ARROW_MENU_SPECS
from ui.main_window_theme import TOOLBAR_BUTTON_STYLE
from ui.main_window_toolbar_logic import BOND_STYLE_BY_LABEL

# Maps the active canvas tool name to the context page key shown in the bar.
_TOOL_PAGE_KEYS = {
    "bond": "bond",
    "arrow": "arrow",
    "text": "atom",
    "benzene": "ring",
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

    def refresh(self, window, tool: str | None) -> None:
        if self._stack is None:
            return
        key = _TOOL_PAGE_KEYS.get(tool or "", "empty")
        page = self._pages.get(key, self._pages["empty"])
        self._stack.setCurrentWidget(page)
        if key == "bond":
            self.reflect_state(window)

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

    # -- page builders -------------------------------------------------

    @staticmethod
    def _new_page() -> tuple[QWidget, QHBoxLayout]:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(3)
        return page, layout

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("toolbarSectionLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

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

    def _build_empty_page(self) -> QWidget:
        page, layout = self._new_page()
        layout.addWidget(self._hint_label("Select a tool to see its options here"))
        layout.addStretch(1)
        return page

    def _build_bond_page(self, window) -> QWidget:
        page, layout = self._new_page()
        layout.addWidget(self._section_label("Bond"))

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

    def _build_arrow_page(self, window) -> QWidget:
        page, layout = self._new_page()
        layout.addWidget(self._section_label("Arrow"))
        combo = QComboBox()
        for label, _value in ARROW_MENU_SPECS:
            combo.addItem(label)
        combo.setToolTip("Arrow type")
        combo.setFixedWidth(140)
        combo.currentTextChanged.connect(window._set_arrow_type)
        layout.addWidget(combo)

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

        layout.addWidget(self._divider())
        more = self._icon_button(window._icon_factory.icon_arrow(), "Open arrow settings")
        more.clicked.connect(window._open_arrow_settings)
        layout.addWidget(more)
        layout.addStretch(1)
        return page

    def _build_atom_page(self, window) -> QWidget:
        page, layout = self._new_page()
        layout.addWidget(self._section_label("Atom"))
        layout.addWidget(
            self._hint_label("Element hotkeys: c n o s p f h · edit label Enter · charge +/-")
        )
        layout.addStretch(1)
        return page

    def _build_ring_page(self, window) -> QWidget:
        page, layout = self._new_page()
        layout.addWidget(self._section_label("Ring"))
        layout.addWidget(
            self._hint_label("Pick rings from the Templates menu above · J for benzene")
        )
        layout.addStretch(1)
        return page


__all__ = ["MainWindowContextBarService"]
