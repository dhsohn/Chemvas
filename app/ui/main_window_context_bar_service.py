from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QStackedWidget,
    QToolBar,
    QToolButton,
    QWidget,
)

from ui.canvas_insert_state import insert_state_for
from ui.canvas_tool_settings_state import tool_settings_state_for
from ui.main_window_context_bar_pages import bond_label_for_state
from ui.main_window_theme import (
    CONTEXT_BAR_BUTTON_HEIGHT,
    CONTEXT_BAR_CONTENT_HEIGHT,
    SMILES_RENDER_BUTTON_STYLE,
    TOOLBAR_ICON_SIZE,
    TOOLBAR_THICKNESS,
)

# Maps the active canvas tool name to the context page key shown in the bar.
_TOOL_PAGE_KEYS = {
    "bond": "bond",
    "arrow": "arrow",
    "ts_bracket": "bracket",
    "text": "atom",
    "note": "text",
    "mark": "mark",
    "benzene": "ring",
    "color": "color",
    "orbital": "orbital",
    "shape": "shape",
}


class MainWindowContextBarService:
    """Builds and updates the tool-sensitive options toolbar."""

    def __init__(
        self,
        *,
        page_builder,
        active_tool_name_for_window,
        active_canvas_or_none_for_window,
        context_bar_page_override_for_window,
        insert_controller_for_window,
        set_atom_input_for_window,
        bond_length_px_for_window=None,
    ) -> None:
        self._page_builder = page_builder
        self._active_tool_name_for_window = active_tool_name_for_window
        self._active_canvas_or_none_for_window = active_canvas_or_none_for_window
        self._context_bar_page_override_for_window = context_bar_page_override_for_window
        self._insert_controller_for_window = insert_controller_for_window
        self._set_atom_input_for_window = set_atom_input_for_window
        self._bond_length_px_for_window = bond_length_px_for_window
        self._bond_length_spin = None
        self._stack: QStackedWidget | None = None
        self._pages: dict[str, QWidget] = {}
        self._bond_group: QButtonGroup | None = None
        self._bond_buttons: dict[str, QToolButton] = {}
        self._ring_group: QButtonGroup | None = None
        self._ring_buttons: dict[tuple[int, str], QToolButton] = {}
        self._mark_group: QButtonGroup | None = None
        self._mark_buttons: dict[str, QToolButton] = {}
        self._arrow_group: QButtonGroup | None = None
        self._arrow_buttons: dict[str, QToolButton] = {}
        self._bracket_group: QButtonGroup | None = None
        self._bracket_buttons: dict[str, QToolButton] = {}

    def init_context_bar(self, window) -> QToolBar:
        bar = QToolBar("Options", window)
        bar.setObjectName("contextOptionsBar")
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.setFixedHeight(TOOLBAR_THICKNESS)
        bar.setIconSize(QSize(TOOLBAR_ICON_SIZE, TOOLBAR_ICON_SIZE))

        stack = QStackedWidget()
        stack.setFixedHeight(CONTEXT_BAR_CONTENT_HEIGHT)
        stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._stack = stack
        context_pages = self._page_builder.build(window)
        self._pages = context_pages.pages
        self._bond_group = context_pages.bond_group
        self._bond_buttons = context_pages.bond_buttons
        self._ring_group = context_pages.ring_group
        self._ring_buttons = context_pages.ring_buttons
        self._mark_group = context_pages.mark_group
        self._mark_buttons = context_pages.mark_buttons
        self._arrow_group = context_pages.arrow_group
        self._arrow_buttons = context_pages.arrow_buttons
        self._bracket_group = context_pages.bracket_group
        self._bracket_buttons = context_pages.bracket_buttons
        self._bond_length_spin = context_pages.bond_length_spin
        self._set_atom_input_for_window(window, context_pages.atom_input)
        for page in self._pages.values():
            stack.addWidget(page)
        stack.setCurrentWidget(self._pages["empty"])
        bar.addWidget(stack)
        self._add_smiles_controls(bar, window)

        window.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
        window.addToolBar(Qt.ToolBarArea.TopToolBarArea, bar)
        return bar

    def _add_smiles_controls(self, bar: QToolBar, window) -> None:
        label = QLabel("SMILES")
        label.setObjectName("toolbarSectionLabel")
        bar.addWidget(label)
        smiles_input = QLineEdit()
        smiles_input.setObjectName("contextSmilesInput")
        smiles_input.setPlaceholderText("CC(=O)Oc1ccccc1C(=O)O")
        smiles_input.setFixedWidth(250)
        smiles_input.setFixedHeight(CONTEXT_BAR_BUTTON_HEIGHT)
        smiles_input.setToolTip("SMILES")
        smiles_input.setStatusTip("Type a SMILES string to insert")
        render_button = QToolButton()
        render_button.setObjectName("smiles_render_button")
        render_button.setText("Render")
        render_button.setToolTip("Insert SMILES")
        render_button.setStatusTip("Insert the typed SMILES structure")
        render_button.setFixedHeight(CONTEXT_BAR_BUTTON_HEIGHT)
        render_button.setStyleSheet(SMILES_RENDER_BUTTON_STYLE)
        render_button.setCursor(Qt.CursorShape.PointingHandCursor)
        render_button.clicked.connect(
            lambda _checked=False: self._insert_controller_for_window(window).begin_smiles_insert(smiles_input.text())
        )
        smiles_input.returnPressed.connect(
            lambda: self._insert_controller_for_window(window).begin_smiles_insert(smiles_input.text())
        )
        bar.addWidget(smiles_input)
        bar.addWidget(render_button)

    def refresh(self, window, tool: str | None, *, page_key: str | None = None) -> None:
        if self._stack is None:
            return
        key = page_key or _TOOL_PAGE_KEYS.get(tool or "", "empty")
        page = self._pages.get(key, self._pages["empty"])
        self._stack.setCurrentWidget(page)
        self.reflect_ring_state(window)
        if key == "bond":
            self.reflect_state(window)
            self.reflect_bond_length(window)
        elif key == "mark":
            self.reflect_mark_state(window)
        elif key == "arrow":
            self.reflect_arrow_state(window)
        elif key == "bracket":
            self.reflect_bracket_state(window)

    def refresh_window(self, window) -> None:
        self.refresh(
            window,
            self.active_tool_name(window),
            page_key=self._context_bar_page_override_for_window(window),
        )

    def active_tool_name(self, window) -> str | None:
        return self._active_tool_name_for_window(window)

    def reflect_state(self, window) -> None:
        if not self._bond_buttons or self._bond_group is None:
            return
        canvas = self._active_canvas_or_none_for_window(window)
        if canvas is None:
            return
        settings = tool_settings_state_for(canvas)
        key = (
            settings.active_bond_style,
            settings.active_bond_order,
        )
        label = bond_label_for_state(*key)
        target = self._bond_buttons.get(label) if label is not None else None
        self._bond_group.setExclusive(False)
        for button in self._bond_buttons.values():
            blocked = button.blockSignals(True)
            button.setChecked(button is target)
            button.blockSignals(blocked)
        self._bond_group.setExclusive(True)

    def reflect_bond_length(self, window) -> None:
        # The spin box copies the bond length once at build time, so re-sync it
        # from the active canvas here. Without this, switching canvases, loading
        # a document, or undoing a change can leave a stale value that the next
        # edit/stepper click would write back, rescaling the canvas unexpectedly.
        if self._bond_length_spin is None or self._bond_length_px_for_window is None:
            return
        canvas = self._active_canvas_or_none_for_window(window)
        if canvas is None:
            return
        # sync_value blocks signals and records the baseline, so a later
        # focus/blur won't commit this value and a fractional length is kept.
        self._bond_length_spin.sync_value(self._bond_length_px_for_window(window))

    def reflect_ring_state(self, window) -> None:
        if not self._ring_buttons or self._ring_group is None:
            return
        canvas = self._active_canvas_or_none_for_window(window)
        target = None
        if canvas is not None:
            insert_state = insert_state_for(canvas)
            if insert_state.template_active and insert_state.template_ring_size is not None:
                target = self._ring_buttons.get(
                    (
                        insert_state.template_ring_size,
                        insert_state.template_ring_style or "regular",
                    )
                )
        self._ring_group.setExclusive(False)
        for button in self._ring_buttons.values():
            blocked = button.blockSignals(True)
            button.setChecked(button is target)
            button.blockSignals(blocked)
        self._ring_group.setExclusive(True)

    def reflect_mark_state(self, window) -> None:
        if not self._mark_buttons or self._mark_group is None:
            return
        canvas = self._active_canvas_or_none_for_window(window)
        if canvas is None:
            return
        target = self._mark_buttons.get(tool_settings_state_for(canvas).mark_kind)
        self._mark_group.setExclusive(False)
        for button in self._mark_buttons.values():
            blocked = button.blockSignals(True)
            button.setChecked(button is target)
            button.blockSignals(blocked)
        self._mark_group.setExclusive(True)

    def reflect_arrow_state(self, window) -> None:
        if not self._arrow_buttons or self._arrow_group is None:
            return
        canvas = self._active_canvas_or_none_for_window(window)
        if canvas is None:
            return
        target = self._arrow_buttons.get(tool_settings_state_for(canvas).active_arrow_type)
        self._arrow_group.setExclusive(False)
        for button in self._arrow_buttons.values():
            blocked = button.blockSignals(True)
            button.setChecked(button is target)
            button.blockSignals(blocked)
        self._arrow_group.setExclusive(True)

    def reflect_bracket_state(self, window) -> None:
        if not self._bracket_buttons or self._bracket_group is None:
            return
        canvas = self._active_canvas_or_none_for_window(window)
        if canvas is None:
            return
        target = self._bracket_buttons.get(tool_settings_state_for(canvas).active_bracket_type)
        self._bracket_group.setExclusive(False)
        for button in self._bracket_buttons.values():
            blocked = button.blockSignals(True)
            button.setChecked(button is target)
            button.blockSignals(blocked)
        self._bracket_group.setExclusive(True)


__all__ = ["MainWindowContextBarService"]
