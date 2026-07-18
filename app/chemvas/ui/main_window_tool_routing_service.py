from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QIcon, QPixmap

from chemvas.ui.main_window_config import (
    ARROW_MENU_SPECS,
    ARROW_PRESET_SPECS,
    COLOR_PALETTE_SPECS,
)
from chemvas.ui.main_window_toolbar_logic import build_template_entries


class MainWindowToolRoutingService:
    def __init__(
        self,
        *,
        insert_controller_for_window,
        tool_mode_controller_for_window,
        color_mutation_service_for_window,
        color_tool_for_window,
        selected_scene_items_for_window,
        icon_factory_for_window,
        tool_state_service,
        context_page_state_service,
    ) -> None:
        self._insert_controller_for_window = insert_controller_for_window
        self._tool_mode_controller_for_window = tool_mode_controller_for_window
        self._color_mutation_service_for_window = color_mutation_service_for_window
        self._color_tool_for_window = color_tool_for_window
        self._selected_scene_items_for_window = selected_scene_items_for_window
        self._icon_factory_for_window = icon_factory_for_window
        self._tool_state = tool_state_service
        self._context_page_state = context_page_state_service

    def _selected_scene_items(self, window):
        return self._selected_scene_items_for_window(window, excluded_kinds=set())

    def add_menu_action(
        self,
        menu,
        label: str,
        callback: Callable[..., None],
        icon: QIcon | None = None,
    ):
        action = (
            menu.addAction(icon, label) if icon is not None else menu.addAction(label)
        )
        action.triggered.connect(lambda checked=False, callback=callback: callback())
        return action

    def palette_icon(self, hex_value: str) -> QIcon:
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(hex_value))
        return QIcon(pixmap)

    def template_entries(self, window) -> list[tuple[str, Callable[[], None]]]:
        insert_controller = self._insert_controller_for_window(window)
        return build_template_entries(insert_controller.begin_ring_template_insert)

    def acs_color_palette(self) -> list[tuple[str, str]]:
        return list(COLOR_PALETTE_SPECS)

    def populate_template_menu(self, window, menu) -> None:
        icon_factory = self._icon_factory_for_window(window)
        for label, handler in self.template_entries(window):
            self.add_menu_action(
                menu, label, handler, icon_factory.icon_template_preview(label)
            )

    def populate_arrow_menu(self, window, menu) -> None:
        icon_factory = self._icon_factory_for_window(window)
        for label, kind in ARROW_MENU_SPECS:
            self.add_menu_action(
                menu,
                label,
                lambda value=label: self.activate_arrow_type_from_menu(window, value),
                icon_factory.icon_arrow_preview(kind),
            )
        preset_menu = menu.addMenu("Preset")
        for label in ARROW_PRESET_SPECS:
            self.add_menu_action(
                preset_menu,
                label,
                lambda value=label: self.activate_arrow_preset_from_menu(window, value),
            )

    def populate_palette_menu(
        self, window, menu, callback: Callable[[str], None]
    ) -> None:
        for label, hex_value in self.acs_color_palette():
            self.add_menu_action(
                menu,
                label,
                lambda value=hex_value: callback(value),
                self.palette_icon(hex_value),
            )

    def activate_arrow_type_from_menu(self, window, value: str) -> None:
        self._context_page_state.set_tool_with_status(window, "arrow")
        self._tool_state.set_arrow_type(window, value)

    def activate_arrow_preset_from_menu(self, window, value: str) -> None:
        self._context_page_state.set_tool_with_status(window, "arrow")
        self._tool_state.set_arrow_preset(window, value)

    def apply_color_preset(self, window, hex_value: str, *, qtimer=QTimer) -> None:
        color = QColor(hex_value)
        tool = self._color_tool_for_window(window)
        set_color = getattr(tool, "set_color", None)
        if callable(set_color):
            set_color(color)

        def apply_color() -> None:
            self._tool_mode_controller_for_window(window).set_tool("color")
            color_service = self._color_mutation_service_for_window(window)
            items = [
                item
                for item in self._selected_scene_items(window)
                if item.data(0) in {"bond", "atom", "ring", "note", "shape"}
            ]
            color_service.apply_color_to_items(items, color)

        qtimer.singleShot(0, apply_color)

    def apply_ring_fill_preset(self, window, hex_value: str, *, qtimer=QTimer) -> None:
        color = QColor(hex_value)

        def apply_fill() -> None:
            color_service = self._color_mutation_service_for_window(window)
            items = [
                item
                for item in self._selected_scene_items(window)
                if item.data(0) == "ring"
            ]
            color_service.apply_ring_fill_color_to_items(items, color)

        qtimer.singleShot(0, apply_fill)


__all__ = ["MainWindowToolRoutingService"]
