from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QIcon, QPixmap

from ui.main_window_config import ARROW_MENU_SPECS, ARROW_PRESET_SPECS, COLOR_PALETTE_SPECS
from ui.main_window_toolbar_logic import build_template_entries


class MainWindowToolRoutingService:
    def add_menu_action(
        self,
        menu,
        label: str,
        callback: Callable[[], None],
        icon: QIcon | None = None,
    ):
        action = menu.addAction(icon, label) if icon is not None else menu.addAction(label)
        action.triggered.connect(lambda checked=False, callback=callback: callback())
        return action

    def palette_icon(self, hex_value: str) -> QIcon:
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(hex_value))
        return QIcon(pixmap)

    def template_entries(self, window) -> list[tuple[str, Callable[[], None]]]:
        return build_template_entries(window.canvas.begin_ring_template_insert)

    def acs_color_palette(self) -> list[tuple[str, str]]:
        return list(COLOR_PALETTE_SPECS)

    def populate_template_menu(self, window, menu) -> None:
        for label, handler in window._template_entries():
            self.add_menu_action(menu, label, handler, window._icon_template_preview(label))

    def populate_arrow_menu(self, window, menu) -> None:
        for label, kind in ARROW_MENU_SPECS:
            self.add_menu_action(
                menu,
                label,
                lambda value=label: window._activate_arrow_type_from_menu(value),
                window._icon_arrow_preview(kind),
            )
        preset_menu = menu.addMenu("Preset")
        for label in ARROW_PRESET_SPECS:
            self.add_menu_action(
                preset_menu,
                label,
                lambda value=label: window._activate_arrow_preset_from_menu(value),
            )
        menu.addSeparator()
        self.add_menu_action(menu, "Settings...", window._open_arrow_settings)

    def populate_palette_menu(self, window, menu, callback: Callable[[str], None]) -> None:
        for label, hex_value in window._acs_color_palette():
            self.add_menu_action(
                menu,
                label,
                lambda value=hex_value: callback(value),
                self.palette_icon(hex_value),
            )

    def activate_arrow_type_from_menu(self, window, value: str) -> None:
        window._set_tool_with_status("arrow")
        window._set_arrow_type(value)

    def activate_arrow_preset_from_menu(self, window, value: str) -> None:
        window._set_tool_with_status("arrow")
        window._set_arrow_preset(value)

    def apply_color_preset(self, window, hex_value: str, *, qtimer=QTimer) -> None:
        color = QColor(hex_value)
        tool = window.canvas.tools.tools.get("color") if hasattr(window.canvas, "tools") else None
        if tool is not None:
            tool._last_color = color.name()

        def apply_color() -> None:
            window.canvas.set_tool("color")
            for item in window.canvas.scene().selectedItems():
                if item.data(0) in {"bond", "atom", "ring"}:
                    window.canvas.apply_color_to_item(item, color)

        qtimer.singleShot(0, apply_color)

    def apply_ring_fill_preset(self, window, hex_value: str, *, qtimer=QTimer) -> None:
        color = QColor(hex_value)

        def apply_fill() -> None:
            for item in window.canvas.scene().selectedItems():
                if item.data(0) == "ring":
                    window.canvas.apply_ring_fill_color(item, color)

        qtimer.singleShot(0, apply_fill)


__all__ = ["MainWindowToolRoutingService"]
