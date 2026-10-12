from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6 import sip
from PyQt6.QtCore import QPointF, QRectF

from chemvas.core.history import (
    CompositeCommand,
    history_transaction_scope,
)
from chemvas.domain.document import unmarked_isolated_carbon_ids
from chemvas.domain.document.marks import mark_kinds_by_atom
from chemvas.features.insertion import (
    build_atom_annotations,
    opposite_charge_mark,
    plan_mark_rebind,
)
from chemvas.features.selection import choose_mark_atom
from chemvas.ui.annotations.state import mark_state_dict_for, scene_item_history_state
from chemvas.ui.canvas.canvas_geometry_logic import shortcut_mark_offset
from chemvas.ui.canvas.canvas_hit_testing_service import scene_items_in_rect_for_canvas
from chemvas.ui.canvas.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id
from chemvas.ui.canvas.graphics_items import AtomLabelItem
from chemvas.ui.history.history_commands import (
    AddSceneItemsCommand,
    ChangeAtomLabelCommand,
    DeleteSceneItemsCommand,
    RebindMarkCommand,
    SetAtomAnnotationCommand,
)
from chemvas.ui.molecule.atom_label_access import atom_has_visible_label_for
from chemvas.ui.scene.scene_item_access import remove_item_from_canvas_scene
from chemvas.ui.selection.selection_info_access import emit_selection_info_for
from chemvas.ui.transactions.document import document_transaction

if TYPE_CHECKING:
    from chemvas.core.history import HistoryCommand
    from chemvas.ui.canvas.canvas_history_service import CanvasHistoryService
    from chemvas.ui.canvas.canvas_view import CanvasView


class CanvasMarkSceneService:
    """Owns atom-bound charge and radical marks.

    Adding such a mark is a user edit that changes the atom's electronic
    state: it is recorded in history and the atom annotation is rebuilt from
    the marks the atom now carries. Removal and Undo restore reconcile the
    annotation through the same owner.
    """

    def __init__(
        self,
        canvas: CanvasView,
        *,
        scene_decoration_service=None,
        history_service: CanvasHistoryService,
    ) -> None:
        self.canvas = canvas
        self.marks = mark_registry_for(canvas)
        self.scene_decoration_service = scene_decoration_service
        self.history = history_service

    def change_charge_for_atom(self, atom_id: int, delta: int) -> None:
        """One shortcut changes charge by one, preserving other mark edits."""
        cancel = opposite_charge_mark(self.marks.get_for_atom(atom_id) or [], delta)
        atom = self.canvas.model.atom_for_id(atom_id)
        if atom is None:
            return
        before = self.canvas.model.atom_annotations.get(atom_id)
        before = dict(before) if before is not None else None
        with (
            document_transaction(self.canvas, history_service=self.history),
            history_transaction_scope(self.history.operations),
        ):
            command: HistoryCommand
            if cancel is not None:
                command = DeleteSceneItemsCommand.capture(
                    self.history.operations,
                    [mark_state_dict_for(self.canvas, cancel)],
                    [cancel],
                )
                command.redo(self.history.operations)
                labels = self.reveal_unmarked_isolated_carbons({atom_id})
                if labels:
                    command = CompositeCommand([command, *labels])
            else:
                item = self._add_mark_for_atom(
                    atom_id,
                    QPointF(atom.x, atom.y),
                    kind="plus" if delta > 0 else "minus",
                    record=False,
                )
                if item is None:
                    raise RuntimeError("Failed to create the charge mark.")
                self._place_shortcut_mark(atom_id, item)
                self.sync_marks_for_atom(atom_id)
                command = AddSceneItemsCommand.from_items(
                    item_states=[mark_state_dict_for(self.canvas, item)], items=[item]
                )
            self._push_atom_mark_edit(atom_id, before, command)

    def _push_atom_mark_edit(
        self,
        atom_id: int,
        before: dict[str, int] | None,
        command: HistoryCommand,
    ) -> None:
        after = self.canvas.model.atom_annotations.get(atom_id)
        # A loaded annotation need not have marks; mark replay alone would
        # rebuild it from the marks and lose that value on Undo.
        annotation = SetAtomAnnotationCommand(
            atom_id, before, dict(after) if after is not None else None
        )
        self.history.push(CompositeCommand([annotation, command]))

    def reveal_unmarked_isolated_carbons(
        self, atom_ids: set[int]
    ) -> list[ChangeAtomLabelCommand]:
        """Apply visibility for affected survivors of a user mark-removal edit.

        The caller owns the active transaction and appends these commands to
        its one history entry. Loading, low-level removal and Undo do not call
        this: existing invisible carbons and ordinary atom deletion stay intact.
        """
        candidates = unmarked_isolated_carbon_ids(
            atom_ids,
            atoms=self.canvas.model.atoms,
            bonds=self.canvas.model.bonds,
            has_visible_label=lambda atom_id: atom_has_visible_label_for(
                self.canvas, atom_id
            ),
            has_marks=lambda atom_id: bool(self.marks.get_for_atom(atom_id)),
        )
        if not candidates:
            return []
        commands = []
        with history_transaction_scope(self.history.operations):
            for atom_id in sorted(candidates):
                atom = self.canvas.model.atoms[atom_id]
                command = ChangeAtomLabelCommand(
                    atom_id=atom_id,
                    before_element=atom.element,
                    after_element=atom.element,
                    before_explicit_label=atom.explicit_label,
                    after_explicit_label=True,
                )
                command.redo(self.history.operations)
                commands.append(command)
        return commands

    @staticmethod
    def _mark_ink_rect(item) -> QRectF:
        if isinstance(item, AtomLabelItem):
            return item.mapToScene(item.glyph_path()).boundingRect()
        return item.sceneBoundingRect()

    def _place_shortcut_mark(self, atom_id: int, item) -> None:
        atom = self.canvas.model.atom_for_id(atom_id)
        if atom is None:
            return
        origin = QPointF(atom.x, atom.y)
        center = self.canvas.services.scene_decoration_build_service.mark_center(item)
        local_ink = self._mark_ink_rect(item).translated(-center)

        def bounds(rect):
            return rect.left(), rect.top(), rect.right(), rect.bottom()

        def tuple_offset(x, y):
            offset = self.mark_offset_from_click(
                atom_id, QPointF(x, y), kind=item.data(1)["kind"]
            )
            return offset.x(), offset.y()

        dx, dy = shortcut_mark_offset(
            (atom.x, atom.y),
            bounds(local_ink),
            [
                bounds(self._mark_ink_rect(other))
                for other in self.marks.get_for_atom(atom_id) or []
                if other is not item
            ],
            bond_length=self.canvas.renderer.style.bond_length_px,
            click_offset=tuple_offset,
        )
        offset = QPointF(dx, dy)
        center = origin + offset
        self.canvas.services.scene_decoration_build_service.set_mark_center(
            item, center
        )
        data = dict(item.data(1))
        data.update(dx=offset.x(), dy=offset.y())
        item.setData(1, data)

    def find_atom_for_mark(
        self, pos: QPointF, *, kind: str | None = None
    ) -> int | None:
        """Bind on a label or its own mark-placement corridor, not blank space."""
        base_radius = self.canvas.renderer.style.bond_length_px * 0.35
        tolerance = max(
            self.canvas.renderer.style.bond_length_px * 0.05,
            1.5 / float(self.canvas.runtime_state.input_view_state.zoom),
        )
        candidates = []
        for item in scene_items_in_rect_for_canvas(
            self.canvas,
            QRectF(
                pos.x() - base_radius,
                pos.y() - base_radius,
                base_radius * 2,
                base_radius * 2,
            ),
        ):
            if item.data(0) != "atom":
                continue
            atom_id = item.data(1)
            atom = self.canvas.model.atom_for_id(atom_id)
            if atom is None:
                continue
            distance = math.hypot(pos.x() - atom.x, pos.y() - atom.y)
            on_label = item.contains(item.mapFromScene(pos))
            offset = self.mark_offset_from_click(atom_id, pos, kind=kind)
            candidates.append(
                (atom_id, distance, on_label, math.hypot(offset.x(), offset.y()))
            )
        return choose_mark_atom(
            candidates, base_radius=base_radius, tolerance=tolerance
        )

    def add_mark_for_atom(
        self,
        atom_id: int,
        click_pos: QPointF,
        *,
        kind: str | None = None,
    ):
        if (
            self.canvas.model.atom_for_id(atom_id) is None
            or self.scene_decoration_service is None
        ):
            return None
        before = self.canvas.model.atom_annotations.get(atom_id)
        before = dict(before) if before is not None else None
        with (
            document_transaction(self.canvas, history_service=self.history),
            history_transaction_scope(self.history.operations),
        ):
            item = self._add_mark_for_atom(atom_id, click_pos, kind=kind, record=False)
            if item is None:
                return None
            self.sync_marks_for_atom(atom_id)
            self._push_atom_mark_edit(
                atom_id,
                before,
                AddSceneItemsCommand.from_items(
                    item_states=[mark_state_dict_for(self.canvas, item)], items=[item]
                ),
            )
        return item

    def _add_mark_for_atom(
        self,
        atom_id: int,
        click_pos: QPointF,
        *,
        kind: str | None,
        record: bool,
    ):
        atom = self.canvas.model.atom_for_id(atom_id)
        if atom is None:
            return None
        kind = kind or self.canvas.runtime_state.tool_settings_state.mark_kind
        offset = self.mark_offset_from_click(atom_id, click_pos, kind=kind)
        center = QPointF(atom.x + offset.x(), atom.y + offset.y())
        if self.scene_decoration_service is None:
            return None
        return self.scene_decoration_service.add_mark(
            center,
            kind=kind,
            atom_id=atom_id,
            offset=offset,
            record=record,
        )

    def sync_marks_for_atom(self, atom_id: int) -> None:
        """Make the atom annotation match its current marks.

        The marks also feed selection-derived window state, which changes here
        without a selection change, so it is refreshed in the same step.
        """
        model = self.canvas.model
        if model.atom_for_id(atom_id) is None:
            model.clear_atom_annotation(atom_id)
        else:
            annotations = build_atom_annotations(
                {atom_id},
                {atom_id: atom_id},
                mark_kinds_by_atom(self.canvas.runtime_state.mark_state),
            )
            model.set_atom_annotation(atom_id, annotations.get(atom_id))
        emit_selection_info_for(self.canvas)

    def rebind_mark(self, item, atom_id: int) -> bool:
        """Transfer only on an explicit user choice; ordinary moves never call this."""
        if (
            sip.isdeleted(item)
            or item.scene() is not self.canvas.scene()
            or item.data(0) != "mark"
        ):
            raise ValueError("The mark is no longer in this document.")
        plan = plan_mark_rebind(self.canvas.model, item, atom_id, self.marks.by_atom)
        if plan is None:
            return False
        atom = self.canvas.model.atoms[atom_id]
        before = scene_item_history_state(item, mark_state_dict_for(self.canvas, item))
        center = self.canvas.services.scene_decoration_build_service.mark_center(item)
        after = dict(
            before, atom_id=atom_id, dx=center.x() - atom.x, dy=center.y() - atom.y
        )
        command: HistoryCommand = RebindMarkCommand(
            require_scene_record_id(item),
            before,
            after,
            {
                key: tuple(require_scene_record_id(mark) for mark in marks)
                for key, marks in plan.before_marks.items()
            },
            {
                key: tuple(require_scene_record_id(mark) for mark in marks)
                for key, marks in plan.after_marks.items()
            },
            plan.before_annotations,
            plan.after_annotations,
        )
        with (
            document_transaction(self.canvas, history_service=self.history),
            history_transaction_scope(self.history.operations),
        ):
            command.redo(self.history.operations)
            labels = self.reveal_unmarked_isolated_carbons(
                {plan.old_id} if plan.old_id is not None else set()
            )
            if labels:
                command = CompositeCommand([command, *labels])
            self.history.push(command)
        return True

    def mark_offset_from_click(
        self, atom_id: int, click_pos: QPointF, *, kind: str | None = None
    ) -> QPointF:
        mark_kind = kind or self.canvas.runtime_state.tool_settings_state.mark_kind
        return self.canvas.render_context.geometry.mark_offset_from_click(
            atom_id, click_pos, kind=mark_kind
        )

    def remove_mark_item(self, item) -> None:
        self.canvas.runtime_state.remove_scene_item("mark_items", item)
        data = item.data(1) or {}
        atom_id = data.get("atom_id")
        if isinstance(atom_id, int):
            marks = self.marks.get_for_atom(atom_id)
            if marks is not None and item in marks:
                marks.remove(item)
            if marks is not None and not marks:
                self.marks.by_atom.pop(atom_id, None)
        remove_item_from_canvas_scene(self.canvas, item)
        if isinstance(atom_id, int):
            self.sync_marks_for_atom(atom_id)

    def remove_marks_for_atom(self, atom_id: int) -> None:
        marks = self.marks.pop_for_atom(atom_id)
        for item in list(marks):
            self.canvas.runtime_state.remove_scene_item("mark_items", item)
            remove_item_from_canvas_scene(self.canvas, item)
        if marks:
            self.sync_marks_for_atom(atom_id)

    def mark_center_for_pointer(
        self,
        pos: QPointF,
        atom_id: int | None = None,
        *,
        kind: str | None = None,
    ) -> QPointF:
        if atom_id is None:
            return QPointF(pos)
        atom = self.canvas.model.atom_for_id(atom_id)
        if atom is None:
            return QPointF(pos)
        offset = self.mark_offset_from_click(atom_id, pos, kind=kind)
        return QPointF(atom.x + offset.x(), atom.y + offset.y())


__all__ = ["CanvasMarkSceneService"]
