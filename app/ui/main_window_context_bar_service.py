from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QStackedWidget,
    QToolBar,
    QToolButton,
    QWidget,
)

from ui.canvas_tool_settings_state import tool_settings_state_for
from ui.main_window_context_bar_pages import bond_label_for_state

# Maps the active canvas tool name to the context page key shown in the bar.
_TOOL_PAGE_KEYS = {
    "bond": "bond",
    "arrow": "arrow",
    "text": "atom",
    "benzene": "ring",
    "template": "template",
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
    ) -> None:
        self._page_builder = page_builder
        self._active_tool_name_for_window = active_tool_name_for_window
        self._active_canvas_or_none_for_window = active_canvas_or_none_for_window
        self._context_bar_page_override_for_window = context_bar_page_override_for_window
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
        context_pages = self._page_builder.build(window)
        self._pages = context_pages.pages
        self._bond_group = context_pages.bond_group
        self._bond_buttons = context_pages.bond_buttons
        self._arrow_group = context_pages.arrow_group
        self._arrow_buttons = context_pages.arrow_buttons
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


__all__ = ["MainWindowContextBarService"]
