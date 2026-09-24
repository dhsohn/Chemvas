from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QInputDialog

from chemvas.ui.canvas.canvas_model_access import (
    atom_for_id,
    required_atom_for,
)
from chemvas.ui.canvas.canvas_smiles_input_state import (
    clear_last_smiles_input_for,
    last_smiles_input_for,
)
from chemvas.ui.molecule.atom_label_history_recorder import AtomLabelHistoryRecorder
from chemvas.ui.molecule.atom_label_merge_service import AtomLabelMergeService
from chemvas.ui.scene.scene_group_operations import group_connection_allowed_for

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from chemvas.ui.canvas.canvas_view import CanvasView


class AtomLabelService:
    def __init__(
        self,
        canvas: CanvasView,
        *,
        move_controller=None,
        graph_service,
        history_service=None,
        hover_refresh: Callable[[], None] | None = None,
    ) -> None:
        self.canvas = canvas
        self.history = history_service
        self.move_controller = move_controller
        self.graph_service = graph_service
        self._hover_refresh = hover_refresh or (lambda: None)
        self.drawing = canvas.render_context.atom_labels
        self._history_recorder = AtomLabelHistoryRecorder(
            canvas,
            history_service=history_service,
        )
        self.merge_service = AtomLabelMergeService(
            canvas,
            graph_service=graph_service,
        )

    def atom_item_for_id(self, atom_id: int):
        return self.drawing.atom_item_for_id(atom_id)

    def implicit_carbon_dot_brush(self):
        return self.drawing.implicit_carbon_dot_brush()

    def ensure_carbon_dot(self, atom_id: int) -> None:
        self.drawing.ensure_carbon_dot(atom_id)

    def remove_carbon_dot(self, atom_id: int) -> None:
        self.drawing.remove_carbon_dot(atom_id)

    def position_label(self, item, x: float, y: float) -> None:
        self.drawing.position_label(item, x, y)

    def relayout_atom_label(self, atom_id: int) -> bool:
        return self.drawing.relayout_atom_label(atom_id)

    def relayout_atom_labels(
        self, atom_ids: Iterable[int], *, skip_bond_ids: Iterable[int] = ()
    ) -> None:
        self.drawing.relayout_atom_labels(atom_ids, skip_bond_ids=skip_bond_ids)

    def restore_atom_item_interaction(
        self,
        atom_id: int,
        previous_item,
        *,
        was_selected: bool,
        refresh_hover: bool,
    ) -> None:
        replacement_item = self.atom_item_for_id(atom_id)
        if (
            was_selected
            and replacement_item is not None
            and replacement_item is not previous_item
        ):
            replacement_item.setSelected(True)
        if refresh_hover:
            self._hover_refresh()

    def record_label_change(
        self,
        atom_id: int,
        before_element: str,
        before_explicit_label: bool,
        before_smiles_input: str | None,
        merge_ids: list[int],
        merge_info: dict,
    ) -> None:
        atom = atom_for_id(self.canvas, atom_id)
        after_element = atom.element if atom is not None else before_element
        after_explicit_label = (
            atom.explicit_label if atom is not None else before_explicit_label
        )
        self._history_recorder.record_label_change(
            atom_id,
            before_element=before_element,
            after_element=after_element,
            before_explicit_label=before_explicit_label,
            after_explicit_label=after_explicit_label,
            before_smiles_input=before_smiles_input,
            merge_ids=merge_ids,
            merge_info=merge_info,
        )

    def merge_overlapping_atoms(self, atom_id: int) -> tuple[list[int], dict]:
        return self.merge_service.merge_overlapping_atoms(atom_id)

    def add_or_update_atom_label(
        self,
        atom_id: int,
        text: str,
        clear_smiles: bool = True,
        record: bool = True,
        allow_merge: bool = True,
        show_carbon: bool = False,
        literal_label: bool | None = None,
    ) -> None:
        text = text.strip()
        show_carbon = bool(show_carbon)
        atom = required_atom_for(self.canvas, atom_id)
        if allow_merge and text and (text.upper() != "C" or show_carbon):
            merge_ids = self.merge_service._overlapping_atom_ids(atom_id)
            if merge_ids and not group_connection_allowed_for(
                self.canvas, {atom_id, *merge_ids}
            ):
                return
        before_element = atom.element
        before_explicit_label = atom.explicit_label
        before_smiles_input = last_smiles_input_for(self.canvas)
        previous_atom_item = self.atom_item_for_id(atom_id)
        was_selected = bool(
            previous_atom_item is not None and previous_atom_item.isSelected()
        )
        refresh_hover = self.canvas.runtime_state.hover_preview_state.atom_id == atom_id
        if text:
            atom.element = text
            if clear_smiles:
                clear_last_smiles_input_for(self.canvas)
        show_label = bool(text)
        explicit_label = (
            bool(before_explicit_label and text == before_element)
            if literal_label is None
            else bool(literal_label)
        )
        if atom.element.upper() == "C":
            if show_carbon and show_label:
                explicit_label = True
            else:
                # A hidden carbon is an implicit carbon. Keeping the explicit
                # flag here left a label-less atom that orphan cleanup treated
                # as visible, so deleting its last bond stranded it invisibly.
                show_label = False
                explicit_label = False
        atom.explicit_label = explicit_label
        if not show_label:
            text = ""

        if not text:
            self.drawing.draw_atom(atom_id, visible=False)
            if self.move_controller is not None:
                self.move_controller.redraw_connected_bonds(atom_id)
            self.restore_atom_item_interaction(
                atom_id,
                previous_atom_item,
                was_selected=was_selected,
                refresh_hover=refresh_hover,
            )
            if record:
                self.record_label_change(
                    atom_id,
                    before_element,
                    before_explicit_label,
                    before_smiles_input,
                    [],
                    {},
                )
            return

        self.drawing.draw_atom(atom_id, visible=True)
        merge_ids, merge_info = (
            self.merge_overlapping_atoms(atom_id) if allow_merge else ([], {})
        )
        if merge_ids:
            # Merging can retarget or remove the last incident bond. Re-derive
            # the presentation even when there is no surviving bond for the
            # renderer-driven refresh below to visit.
            self.relayout_atom_label(atom_id)
        if self.move_controller is not None:
            self.move_controller.redraw_connected_bonds(atom_id)
        self.restore_atom_item_interaction(
            atom_id,
            previous_atom_item,
            was_selected=was_selected,
            refresh_hover=refresh_hover,
        )
        if record:
            self.record_label_change(
                atom_id,
                before_element,
                before_explicit_label,
                before_smiles_input,
                merge_ids,
                merge_info,
            )

    def prompt_atom_label(self, atom_id: int) -> None:
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return
        initial = (
            ""
            if atom.element.upper() == "C" and not atom.explicit_label
            else atom.element
        )
        text, ok = QInputDialog.getText(
            self.canvas,
            "Atom Label",
            "Enter atom symbol:",
            text=initial,
        )
        if not ok:
            return
        text = text.strip()
        if not text:
            self.add_or_update_atom_label(atom_id, "C", show_carbon=False)
            return
        self.add_or_update_atom_label(atom_id, text, show_carbon=True)


__all__ = ["AtomLabelService"]
