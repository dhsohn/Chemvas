from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6 import sip
from PyQt6.QtCore import QPointF, QRectF

from chemvas.core.history import history_transaction_scope
from chemvas.features.insertion import build_atom_annotations
from chemvas.ui.canvas_geometry_access import mark_target_distance_for_atom_for
from chemvas.ui.canvas_hit_testing_scene_access import scene_items_in_rect_for_canvas
from chemvas.ui.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas_model_access import (
    atom_annotations_for,
    atom_for_id,
    sync_atom_annotation_from_marks_for,
)
from chemvas.ui.canvas_scene_items_state import remove_scene_item_from_collection_for
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.graphics_items import AtomLabelItem
from chemvas.ui.history_commands import (
    AddSceneItemsCommand,
    DeleteSceneItemsCommand,
    RebindMarkCommand,
)
from chemvas.ui.input_view_access import zoom_factor_for
from chemvas.ui.mark_item_access import mark_center_for, set_mark_center_for
from chemvas.ui.renderer_style_access import bond_length_px_for
from chemvas.ui.scene_item_access import remove_item_from_canvas_scene
from chemvas.ui.scene_item_state import mark_state_dict_for
from chemvas.ui.selection_info_access import emit_selection_info_for
from chemvas.ui.transactions.document import document_transaction

if TYPE_CHECKING:
    from chemvas.core.history import HistoryCommand


class CanvasMarkSceneService:
    """Owns atom-bound charge and radical marks.

    Two distinct operations add such a mark. A user edit changes the atom's
    electronic state: it is recorded in history and the atom annotation is
    rebuilt from the marks the atom now carries. Materializing a mark only
    shows an annotation the model already holds (document restore, SMILES
    insertion) and must not touch the model or history. Removal and Undo
    restore reconcile the annotation through the same owner.
    """

    def __init__(
        self, canvas, *, scene_decoration_service=None, history_service=None
    ) -> None:
        self.canvas = canvas
        self.marks = mark_registry_for(canvas)
        self.scene_decoration_service = scene_decoration_service
        self.history = history_service

    def change_charge_for_atom(self, atom_id: int, delta: int) -> None:
        """One shortcut changes charge by one, preserving other mark edits."""
        if delta not in {-1, 1}:
            raise ValueError("Charge shortcuts require a change of +1 or -1.")
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return
        opposite = {"minus", "circled_minus"} if delta > 0 else {"plus", "circled_plus"}
        cancel = next(
            (
                item
                for item in reversed(self.marks.get_for_atom(atom_id) or [])
                if (item.data(1) or {}).get("kind") in opposite
            ),
            None,
        )
        with document_transaction(self.canvas, history_service=self.history):
            command: HistoryCommand
            if cancel is not None:
                command = DeleteSceneItemsCommand.capture(
                    self.canvas, [mark_state_dict_for(self.canvas, cancel)], [cancel]
                )
                command.redo(self.canvas)
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
                command = AddSceneItemsCommand(
                    item_states=[mark_state_dict_for(self.canvas, item)], items=[item]
                )
            if self.history.push(command) is False:
                raise RuntimeError("Failed to record charge change in history.")

    @staticmethod
    def _mark_ink_rect(item) -> QRectF:
        if isinstance(item, AtomLabelItem):
            return item.mapToScene(item.glyph_path()).boundingRect()
        return item.sceneBoundingRect()

    def _place_shortcut_mark(self, atom_id: int, item) -> None:
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return
        gap = max(0.5, bond_length_px_for(self.canvas) * 0.04)
        obstacles = [
            self._mark_ink_rect(other).adjusted(-gap, -gap, gap, gap)
            for other in self.marks.get_for_atom(atom_id) or []
            if other is not item
        ]
        origin = QPointF(atom.x, atom.y)
        ink = self._mark_ink_rect(item)
        local_ink = ink.translated(-mark_center_for(self.canvas, item))
        kind = item.data(1)["kind"]
        directions = (
            (1, -1),
            (-1, -1),
            (1, 1),
            (-1, 1),
            (0, -1),
            (0, 1),
            (1, 0),
            (-1, 0),
        )
        for x, y in directions:
            offset = self.mark_offset_from_click(
                atom_id, origin + QPointF(x, y), kind=kind
            )
            center = origin + offset
            if not any(
                local_ink.translated(center).intersects(rect) for rect in obstacles
            ):
                break
        else:
            # An occupied compass is not a four-direction cycle: place the
            # next symbol outside existing ink, without moving saved marks.
            extent = max(
                (
                    math.hypot(point.x() - atom.x, point.y() - atom.y)
                    for rect in obstacles
                    for point in (
                        rect.topLeft(),
                        rect.topRight(),
                        rect.bottomLeft(),
                        rect.bottomRight(),
                    )
                ),
                default=0.0,
            )
            radius = extent + math.hypot(local_ink.width(), local_ink.height()) + gap
            offset = QPointF(radius / math.sqrt(2), -radius / math.sqrt(2))
            center = origin + offset
        set_mark_center_for(self.canvas, item, center)
        data = dict(item.data(1))
        data.update(dx=offset.x(), dy=offset.y())
        item.setData(1, data)

    def find_atom_for_mark(
        self, pos: QPointF, *, kind: str | None = None
    ) -> int | None:
        """Bind on a label or its own mark-placement corridor, not blank space."""
        base_radius = bond_length_px_for(self.canvas) * 0.35
        tolerance = max(
            bond_length_px_for(self.canvas) * 0.05, 1.5 / zoom_factor_for(self.canvas)
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
            atom = atom_for_id(self.canvas, atom_id)
            if atom is None:
                continue
            distance = math.hypot(pos.x() - atom.x, pos.y() - atom.y)
            on_label = item.contains(item.mapFromScene(pos))
            offset = self.mark_offset_from_click(atom_id, pos, kind=kind)
            radius = max(base_radius, math.hypot(offset.x(), offset.y()) + tolerance)
            if on_label or distance <= radius:
                candidates.append((not on_label, distance, atom_id))
        return min(candidates)[2] if candidates else None

    def add_mark_for_atom(
        self,
        atom_id: int,
        click_pos: QPointF,
        *,
        kind: str | None = None,
    ):
        item = self._add_mark_for_atom(atom_id, click_pos, kind=kind, record=True)
        if item is not None:
            self.sync_marks_for_atom(atom_id)
        return item

    def materialize_mark_for_atom(
        self,
        atom_id: int,
        click_pos: QPointF,
        *,
        kind: str | None,
    ):
        return self._add_mark_for_atom(atom_id, click_pos, kind=kind, record=False)

    def _add_mark_for_atom(
        self,
        atom_id: int,
        click_pos: QPointF,
        *,
        kind: str | None,
        record: bool,
    ):
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return None
        kind = kind or tool_settings_state_for(self.canvas).mark_kind
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

        The marks also feed the selection formula readout, which changes here
        without a selection change, so it is refreshed in the same step.
        """
        sync_atom_annotation_from_marks_for(
            self.canvas,
            atom_id,
            self.marks.get_for_atom(atom_id) or (),
        )
        emit_selection_info_for(self.canvas)

    def rebind_mark(self, item, atom_id: int) -> bool:
        """Transfer only on an explicit user choice; ordinary moves never call this."""
        if (
            sip.isdeleted(item)
            or item.scene() is not self.canvas.scene()
            or item.data(0) != "mark"
        ):
            raise ValueError("The mark is no longer in this document.")
        atom = atom_for_id(self.canvas, atom_id)
        if type(atom_id) is not int or atom is None:
            raise ValueError("Choose an existing atom in this document.")
        old_id = (item.data(1) or {}).get("atom_id")
        if atom_id == old_id:
            return False
        if old_id is not None and atom_for_id(self.canvas, old_id) is None:
            raise ValueError("The mark's original atom no longer exists.")
        affected_ids = {atom_id} | ({old_id} if old_id is not None else set())
        before_marks = {
            key: tuple(self.marks.get_for_atom(key) or ()) for key in affected_ids
        }
        if old_id is not None and item not in before_marks[old_id]:
            raise ValueError(
                "The mark's binding is inconsistent; reload the document before reassigning."
            )
        annotations = atom_annotations_for(self.canvas)
        before_annotations = {
            key: dict(annotations[key]) for key in affected_ids if key in annotations
        }
        expected = build_atom_annotations(
            affected_ids,
            {key: key for key in affected_ids},
            {
                key: [(mark.data(1) or {})["kind"] for mark in items]
                for key, items in before_marks.items()
            },
        )
        normalized = {
            key: {k: v for k, v in value.items() if v}
            for key, value in before_annotations.items()
        }
        normalized = {key: value for key, value in normalized.items() if value}
        if normalized != expected:
            raise ValueError(
                "Atom annotations and marks disagree; resolve them before reassigning a mark."
            )
        after_marks = dict(before_marks)
        if old_id is not None:
            after_marks[old_id] = tuple(
                mark for mark in before_marks[old_id] if mark is not item
            )
        after_marks[atom_id] = (*before_marks[atom_id], item)
        after_annotations = build_atom_annotations(
            affected_ids,
            {key: key for key in affected_ids},
            {
                key: [(mark.data(1) or {})["kind"] for mark in items]
                for key, items in after_marks.items()
            },
        )
        before = mark_state_dict_for(self.canvas, item)
        pos = item.pos()
        before["item_pos"] = (pos.x(), pos.y())
        center = mark_center_for(self.canvas, item)
        after = dict(
            before, atom_id=atom_id, dx=center.x() - atom.x, dy=center.y() - atom.y
        )
        command = RebindMarkCommand(
            item,
            before,
            after,
            before_marks,
            after_marks,
            before_annotations,
            after_annotations,
        )
        with (
            document_transaction(self.canvas, history_service=self.history),
            history_transaction_scope(self.canvas),
        ):
            command.redo(self.canvas)
            if self.history.push(command) is False:
                raise RuntimeError(
                    "Mark reassignment could not be recorded in Undo history."
                )
        return True

    def mark_offset_from_click(
        self, atom_id: int, click_pos: QPointF, *, kind: str | None = None
    ) -> QPointF:
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return QPointF(0.0, 0.0)
        dx = click_pos.x() - atom.x
        dy = click_pos.y() - atom.y
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            dx = 1.0
            dy = -1.0
            length = math.hypot(dx, dy)
        direction_x = dx / length
        direction_y = dy / length
        target = bond_length_px_for(self.canvas) * 0.2
        mark_kind = kind or tool_settings_state_for(self.canvas).mark_kind
        label_target = mark_target_distance_for_atom_for(
            self.canvas, atom_id, direction_x, direction_y, mark_kind
        )
        if label_target > target:
            target += (label_target - target) * 0.25
        return QPointF(direction_x * target, direction_y * target)

    def remove_mark_item(self, item) -> None:
        remove_scene_item_from_collection_for(self.canvas, "mark_items", item)
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
            remove_scene_item_from_collection_for(self.canvas, "mark_items", item)
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
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return QPointF(pos)
        offset = self.mark_offset_from_click(atom_id, pos, kind=kind)
        return QPointF(atom.x + offset.x(), atom.y + offset.y())


__all__ = ["CanvasMarkSceneService"]
