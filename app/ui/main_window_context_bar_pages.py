from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import QButtonGroup, QToolButton, QWidget

from ui.main_window_context_bar_page_factories import (
    bond_label_for_state,
    build_arrow_page,
    build_atom_page,
    build_bond_page,
    build_empty_page,
    build_ring_page,
    build_template_page,
)


@dataclass(frozen=True)
class ContextBarPages:
    pages: dict[str, QWidget]
    bond_group: QButtonGroup | None
    bond_buttons: dict[str, QToolButton]
    arrow_group: QButtonGroup | None
    arrow_buttons: dict[str, QToolButton]


class MainWindowContextBarPageBuilder:
    def __init__(
        self,
        *,
        insert_controller_for_window,
        tool_mode_controller_for_window,
        tool_state_service,
        activate_bond_style_for_window,
        set_bond_length_for_window,
    ) -> None:
        self._insert_controller_for_window = insert_controller_for_window
        self._tool_mode_controller_for_window = tool_mode_controller_for_window
        self._tool_state = tool_state_service
        self._activate_bond_style_for_window = activate_bond_style_for_window
        self._set_bond_length_for_window = set_bond_length_for_window

    def build(self, window) -> ContextBarPages:
        bond_page = build_bond_page(
            window,
            self._activate_bond_style_for_window,
            self._set_bond_length_for_window,
        )
        arrow_page = build_arrow_page(
            window,
            self._tool_mode_controller_for_window(window),
            self._tool_state,
        )
        pages = {
            "empty": build_empty_page(),
            "bond": bond_page.page,
            "template": build_template_page(window, self._insert_controller_for_window(window)),
            "arrow": arrow_page.page,
            "atom": build_atom_page(),
            "ring": build_ring_page(),
        }
        return ContextBarPages(
            pages=pages,
            bond_group=bond_page.group,
            bond_buttons=bond_page.buttons,
            arrow_group=arrow_page.group,
            arrow_buttons=arrow_page.buttons,
        )


__all__ = [
    "ContextBarPages",
    "MainWindowContextBarPageBuilder",
    "bond_label_for_state",
]
