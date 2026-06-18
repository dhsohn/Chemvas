from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import QButtonGroup, QLineEdit, QToolButton, QWidget

from ui.main_window_context_bar_page_factories import (
    bond_label_for_state,
    build_arrow_page,
    build_atom_page,
    build_bond_page,
    build_color_palette_page,
    build_empty_page,
    build_mark_page,
    build_template_page,
)


@dataclass(frozen=True)
class ContextBarPages:
    pages: dict[str, QWidget]
    bond_group: QButtonGroup | None
    bond_buttons: dict[str, QToolButton]
    ring_group: QButtonGroup | None
    ring_buttons: dict[tuple[int, str], QToolButton]
    mark_group: QButtonGroup | None
    mark_buttons: dict[str, QToolButton]
    arrow_group: QButtonGroup | None
    arrow_buttons: dict[str, QToolButton]
    atom_input: QLineEdit | None


class MainWindowContextBarPageBuilder:
    def __init__(
        self,
        *,
        insert_controller_for_window,
        tool_mode_controller_for_window,
        tool_state_service,
        activate_bond_style_for_window,
        set_bond_length_for_window,
        apply_color_preset_for_window,
        apply_ring_fill_preset_for_window,
    ) -> None:
        self._insert_controller_for_window = insert_controller_for_window
        self._tool_mode_controller_for_window = tool_mode_controller_for_window
        self._tool_state = tool_state_service
        self._activate_bond_style_for_window = activate_bond_style_for_window
        self._set_bond_length_for_window = set_bond_length_for_window
        self._apply_color_preset_for_window = apply_color_preset_for_window
        self._apply_ring_fill_preset_for_window = apply_ring_fill_preset_for_window

    def build(self, window) -> ContextBarPages:
        tool_mode_controller = self._tool_mode_controller_for_window(window)
        bond_page = build_bond_page(
            window,
            self._activate_bond_style_for_window,
            self._set_bond_length_for_window,
        )
        arrow_page = build_arrow_page(
            window,
            tool_mode_controller,
            self._tool_state,
        )
        atom_page = build_atom_page(
            tool_mode_controller.get_atom_symbol(),
            lambda text: self._tool_mode_controller_for_window(window).set_atom_symbol(text),
        )
        ring_page = build_template_page(window, self._insert_controller_for_window(window))
        mark_page = build_mark_page(window, self._tool_state)
        pages = {
            "empty": build_empty_page(),
            "bond": bond_page.page,
            "arrow": arrow_page.page,
            "atom": atom_page.page,
            "ring": ring_page.page,
            "mark": mark_page.page,
            "color": build_color_palette_page(
                tooltip_prefix="Color",
                apply_preset=lambda value: self._apply_color_preset_for_window(window, value),
            ),
            "ring_fill": build_color_palette_page(
                tooltip_prefix="Ring Fill",
                apply_preset=lambda value: self._apply_ring_fill_preset_for_window(window, value),
            ),
        }
        return ContextBarPages(
            pages=pages,
            bond_group=bond_page.group,
            bond_buttons=bond_page.buttons,
            ring_group=ring_page.group,
            ring_buttons=ring_page.buttons,
            mark_group=mark_page.group,
            mark_buttons=mark_page.buttons,
            arrow_group=arrow_page.group,
            arrow_buttons=arrow_page.buttons,
            atom_input=atom_page.atom_input,
        )


__all__ = [
    "ContextBarPages",
    "MainWindowContextBarPageBuilder",
    "bond_label_for_state",
]
