from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, Protocol

from chemvas.core.history import history_transaction_scope
from chemvas.ui.molecule.atom_label_merge_service import AtomLabelMergeService

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from chemvas.domain.document import MoleculeModel
    from chemvas.ui.canvas.canvas_view import CanvasView


class AtomLabelDrawing(Protocol):
    """The label presentation a label edit refreshes."""

    def atom_item_for_id(self, atom_id: int) -> Any: ...
    def implicit_carbon_dot_brush(self) -> Any: ...
    def ensure_carbon_dot(self, atom_id: int) -> None: ...
    def remove_carbon_dot(self, atom_id: int) -> None: ...
    def position_label(self, item: Any, x: float, y: float) -> None: ...
    def relayout_atom_label(self, atom_id: int) -> bool: ...
    def relayout_atom_labels(
        self, atom_ids: Iterable[int], *, skip_bond_ids: Iterable[int] = ()
    ) -> None: ...
    def draw_atom(self, atom_id: int, *, visible: bool | None = None) -> None: ...


@dataclass(frozen=True, kw_only=True)
class AtomLabelPorts:
    """What an unrecorded label edit reads and writes, named instead of a canvas."""

    model: Callable[[], MoleculeModel]
    drawing: AtomLabelDrawing
    # Reselect the replacement item when a relabel swaps a selected item.
    select_items: Callable[[list[Any]], object]
    hovered_atom_id: Callable[[], int | None]
    add_atom: Callable[[str, float, float], int]

    @classmethod
    def for_canvas(cls, canvas: CanvasView) -> AtomLabelPorts:
        return cls(
            model=lambda: canvas.model,
            drawing=canvas.render_context.atom_labels,
            select_items=lambda items: canvas.services.selection.set_items_selected(
                items, True, block_signals=False
            ),
            hovered_atom_id=lambda: canvas.runtime_state.hover_preview_state.atom_id,
            add_atom=lambda element, x, y: (
                canvas.services.canvas_atom_mutation_service.add_atom(element, x, y)
            ),
        )


class AtomLabelService:
    """Label edits through explicit ports, plus desktop history and prompting.

    Only recorded edits, their history and the label prompt need the canvas;
    an editor that records whole-document changes builds one without it.
    """

    def __init__(
        self,
        ports: AtomLabelPorts,
        *,
        canvas: CanvasView | None = None,
        move_controller=None,
        graph_service,
        history_service=None,
        hover_refresh: Callable[[], None] | None = None,
        merge_service=None,
        connection_allowed=None,
    ) -> None:
        self.ports = ports
        self._canvas = canvas
        self.history = history_service
        self.move_controller = move_controller
        self.graph_service = graph_service
        self._hover_refresh = hover_refresh or (lambda: None)
        self.drawing = ports.drawing
        if merge_service is None:
            merge_service = AtomLabelMergeService(
                self.canvas, graph_service=graph_service
            )
        self.merge_service = merge_service
        if connection_allowed is None:
            canvas = self.canvas
            from chemvas.ui.scene.scene_group_operations import (
                group_connection_allowed_for,
            )

            def connection_allowed(ids):
                return group_connection_allowed_for(canvas, ids)

        self.connection_allowed = connection_allowed

    @classmethod
    def for_canvas(cls, canvas: CanvasView, **kwargs: Any) -> AtomLabelService:
        return cls(AtomLabelPorts.for_canvas(canvas), canvas=canvas, **kwargs)

    @property
    def canvas(self) -> CanvasView:
        """The recording canvas; unrecorded label edits never read it."""
        if self._canvas is None:
            raise RuntimeError(
                "This label service records no desktop history and shows no prompt."
            )
        return self._canvas

    @cached_property
    def _history_recorder(self):
        from chemvas.ui.molecule.atom_label_history_recorder import (
            AtomLabelHistoryRecorder,
        )

        return AtomLabelHistoryRecorder(self.canvas, history_service=self.history)

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
            self.ports.select_items([replacement_item])
        if refresh_hover:
            self._hover_refresh()

    def record_label_change(
        self,
        atom_id: int,
        before_element: str,
        before_explicit_label: bool,
        merge_ids: list[int],
        merge_info: dict,
    ) -> None:
        atom = self.ports.model().atom_for_id(atom_id)
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
            merge_ids=merge_ids,
            merge_info=merge_info,
        )

    def merge_overlapping_atoms(self, atom_id: int) -> tuple[list[int], dict]:
        return self.merge_service.merge_overlapping_atoms(atom_id)

    def add_or_update_atom_label(
        self,
        atom_id: int,
        text: str,
        record: bool = True,
        allow_merge: bool = True,
        show_carbon: bool = False,
        literal_label: bool | None = None,
    ) -> None:
        """Apply a label; a recorded edit is one document transaction.

        The model changes before the merge, redraw and history record that
        follow it, so a failure in any of them restores the whole edit.
        Unrecorded calls come from history replay, insertion and paste, whose
        command or build transaction owns the rollback.
        """
        if not record:
            self._apply_atom_label(
                atom_id,
                text,
                record=False,
                allow_merge=allow_merge,
                show_carbon=show_carbon,
                literal_label=literal_label,
            )
            return
        from chemvas.ui.transactions.document import document_transaction

        with (
            document_transaction(self.canvas, history_service=self.history),
            history_transaction_scope(self.history.operations),
        ):
            self._apply_atom_label(
                atom_id,
                text,
                record=True,
                allow_merge=allow_merge,
                show_carbon=show_carbon,
                literal_label=literal_label,
            )

    def add_labelled_atom(
        self, text: str, x: float, y: float, *, record: bool = True
    ) -> int:
        """Add a labelled atom; an unrecorded caller owns the candidate transaction."""
        if not record:
            atom_id = self.ports.add_atom(text, x, y)
            self.add_or_update_atom_label(atom_id, text, record=False, show_carbon=True)
            return atom_id
        from chemvas.ui.transactions.document import document_transaction

        with (
            document_transaction(self.canvas, history_service=self.history),
            history_transaction_scope(self.history.operations),
        ):
            before_next_atom_id = int(self.ports.model().next_atom_id)
            atom_id = self.add_labelled_atom(text, x, y, record=False)
            self._history_recorder.record_added_atom(
                atom_id, before_next_atom_id=before_next_atom_id
            )
        return atom_id

    def _apply_atom_label(
        self,
        atom_id: int,
        text: str,
        *,
        record: bool,
        allow_merge: bool,
        show_carbon: bool,
        literal_label: bool | None,
    ) -> None:
        text = text.strip()
        show_carbon = bool(show_carbon)
        atom = self.ports.model().atoms[atom_id]
        if allow_merge and text and (text.upper() != "C" or show_carbon):
            merge_ids = self.merge_service._overlapping_atom_ids(atom_id)
            if merge_ids and not self.connection_allowed({atom_id, *merge_ids}):
                return
        before_element = atom.element
        before_explicit_label = atom.explicit_label
        previous_atom_item = self.atom_item_for_id(atom_id)
        was_selected = bool(
            previous_atom_item is not None and previous_atom_item.isSelected()
        )
        refresh_hover = self.ports.hovered_atom_id() == atom_id
        if text:
            atom.element = text
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
                merge_ids,
                merge_info,
            )

    def atom_label_prompt_initial(self, atom_id: int) -> str | None:
        atom = self.ports.model().atom_for_id(atom_id)
        if atom is None:
            return None
        return (
            ""
            if atom.element.upper() == "C" and not atom.explicit_label
            else atom.element
        )

    def apply_atom_label_prompt(
        self, atom_id: int, text: str, *, record: bool = True
    ) -> None:
        text = text.strip()
        self.add_or_update_atom_label(
            atom_id, text or "C", record=record, show_carbon=bool(text)
        )

    def prompt_atom_label(self, atom_id: int) -> None:
        from PyQt6.QtWidgets import QInputDialog

        initial = self.atom_label_prompt_initial(atom_id)
        if initial is None:
            return
        text, ok = QInputDialog.getText(
            self.canvas,
            "Atom Label",
            "Enter atom symbol:",
            text=initial,
        )
        if ok:
            self.apply_atom_label_prompt(atom_id, text)


__all__ = ["AtomLabelDrawing", "AtomLabelPorts", "AtomLabelService"]
