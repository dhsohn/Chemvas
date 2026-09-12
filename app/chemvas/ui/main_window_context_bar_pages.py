from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chemvas.ui.main_window_context_bar_page_factories import (
    bond_label_for_state,
    build_arrow_page,
    build_atom_page,
    build_bond_page,
    build_bracket_page,
    build_color_palette_page,
    build_empty_page,
    build_line_page,
    build_mark_page,
    build_orbital_page,
    build_select_page,
    build_shape_page,
    build_template_page,
    build_text_page,
)

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QButtonGroup, QLineEdit, QSlider, QToolButton, QWidget

    from chemvas.ui.main_window_context_bar_widgets import BondLengthSpinBox


@dataclass(frozen=True, kw_only=True)
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
    arrow_width_slider: QSlider
    arrow_head_slider: QSlider
    bracket_group: QButtonGroup | None
    bracket_buttons: dict[str, QToolButton]
    atom_input: QLineEdit | None
    bond_length_spin: BondLengthSpinBox | None


class MainWindowContextBarPageBuilder:
    def __init__(
        self,
        *,
        insert_controller_for_window,
        tool_mode_controller_for_window,
        tool_state_service,
        activate_bond_style_for_window,
        set_bond_length_value_for_window,
        bond_length_px_for_window,
        apply_color_preset_for_window,
        apply_ring_fill_preset_for_window,
        rotate_selection_for_window,
        flip_selection_for_window,
        align_selection_for_window,
        distribute_selection_for_window,
        note_controller_for_window,
    ) -> None:
        self._insert_controller_for_window = insert_controller_for_window
        self._tool_mode_controller_for_window = tool_mode_controller_for_window
        self._tool_state = tool_state_service
        self._activate_bond_style_for_window = activate_bond_style_for_window
        self._set_bond_length_value_for_window = set_bond_length_value_for_window
        self._bond_length_px_for_window = bond_length_px_for_window
        self._apply_color_preset_for_window = apply_color_preset_for_window
        self._apply_ring_fill_preset_for_window = apply_ring_fill_preset_for_window
        self._rotate_selection_for_window = rotate_selection_for_window
        self._flip_selection_for_window = flip_selection_for_window
        self._align_selection_for_window = align_selection_for_window
        self._distribute_selection_for_window = distribute_selection_for_window
        self._note_controller_for_window = note_controller_for_window

    def _note_command(self, window, method_name: str, *args) -> None:
        controller = self._note_controller_for_window(window)
        if controller is None:
            return
        if not controller.text_format_targets():
            window.statusBar().showMessage(
                "Select a note or edit its text to use Text formatting.", 6000
            )
            return
        getattr(controller, method_name)(*args)

    def build(self, window) -> ContextBarPages:
        tool_mode_controller = self._tool_mode_controller_for_window(window)
        bond_page = build_bond_page(
            window,
            self._activate_bond_style_for_window,
            self._set_bond_length_value_for_window,
            self._bond_length_px_for_window(window),
        )
        arrow_page = build_arrow_page(
            window,
            tool_mode_controller,
            self._tool_state,
        )
        bracket_page = build_bracket_page(window, self._tool_state)
        atom_page = build_atom_page(
            tool_mode_controller.get_atom_symbol(),
            lambda text: self._tool_mode_controller_for_window(window).set_atom_symbol(
                text
            ),
        )
        ring_page = build_template_page(
            window,
            lambda ring_size, *, style: self._insert_controller_for_window(
                window
            ).begin_ring_template_insert(
                ring_size,
                style=style,
            ),
            begin_smiles_insert=lambda text: self._insert_controller_for_window(
                window
            ).begin_smiles_insert(text),
        )
        mark_page = build_mark_page(window, self._tool_state)
        text_page = build_text_page(
            window,
            toggle_bold=lambda: self._note_command(window, "toggle_text_bold"),
            toggle_italic=lambda: self._note_command(window, "toggle_text_italic"),
            toggle_superscript=lambda: self._note_command(
                window, "toggle_text_superscript"
            ),
            toggle_subscript=lambda: self._note_command(
                window, "toggle_text_subscript"
            ),
            adjust_size=lambda delta: self._note_command(
                window, "adjust_text_size", delta
            ),
            set_alignment=lambda name: self._note_command(
                window, "set_text_alignment", name
            ),
        )
        pages = {
            "empty": build_empty_page(),
            "bond": bond_page.page,
            "arrow": arrow_page.page,
            "bracket": bracket_page.page,
            "atom": atom_page.page,
            "text": text_page,
            "ring": ring_page.page,
            "mark": mark_page.page,
            "select": build_select_page(
                window,
                flip_selection=self._flip_selection_for_window,
                rotate_selection=self._rotate_selection_for_window,
                align_selection=self._align_selection_for_window,
                distribute_selection=self._distribute_selection_for_window,
            ),
            "orbital": build_orbital_page(window, self._tool_state),
            "shape": build_shape_page(window, self._tool_state),
            "line": build_line_page(window, self._tool_state),
            "color": build_color_palette_page(
                tooltip_prefix="Color",
                apply_preset=lambda value: self._apply_color_preset_for_window(
                    window, value
                ),
            ),
            "ring_fill": build_color_palette_page(
                tooltip_prefix="Ring Fill",
                apply_preset=lambda value: self._apply_ring_fill_preset_for_window(
                    window, value
                ),
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
            arrow_width_slider=arrow_page.width_slider,
            arrow_head_slider=arrow_page.head_slider,
            bracket_group=bracket_page.group,
            bracket_buttons=bracket_page.buttons,
            atom_input=atom_page.atom_input,
            bond_length_spin=bond_page.length_spin,
        )


__all__ = [
    "ContextBarPages",
    "MainWindowContextBarPageBuilder",
    "bond_label_for_state",
]
