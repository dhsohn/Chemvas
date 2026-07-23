from __future__ import annotations

from functools import partial

from PyQt6.QtCore import Qt

from chemvas.ui.bond_renderer_access import update_bond_geometry_for
from chemvas.ui.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas_scene_items_state import (
    append_scene_item_for,
    remove_scene_item_from_collection_for,
    remove_selected_note_for,
    selected_notes_for,
)
from chemvas.ui.handle_overlay_access import clear_handles_for
from chemvas.ui.handle_state import handle_target_for
from chemvas.ui.history_commands import (
    _restore_scene_runtime_snapshot,
    _run_rollback_step,
    _scene_runtime_snapshot,
    _SceneRuntimeSnapshot,
)
from chemvas.ui.mark_item_access import remove_mark_item_for
from chemvas.ui.note_selection_box import update_note_selection_box_for
from chemvas.ui.scene_item_access import (
    canvas_scene_for_item_operation,
    item_is_unavailable_for_scene_operation,
    remove_attached_item_from_canvas_scene,
)
from chemvas.ui.scene_item_state import ARROW_KINDS
from chemvas.ui.selection_service_access import refresh_selection_outline_for
from chemvas.ui.transactions.scene_item_attach import (
    SceneItemAttachPorts,
    SceneItemAttachSnapshot,
)


def _add_item_with_attach_ports(
    attach_ports: SceneItemAttachPorts,
    item: object,
) -> None:
    attach_ports.add_item(item)


class SceneItemLifecycleService:
    def __init__(self, canvas, *, graph_service) -> None:
        self.canvas = canvas
        self.graph_service = graph_service
        self.marks = mark_registry_for(canvas)

    def bond_ids_for_ring_item(self, item) -> set[int]:
        ring_atom_ids = item.data(2)
        if not isinstance(ring_atom_ids, list) or len(ring_atom_ids) < 2:
            return set()
        bond_ids: set[int] = set()
        for index, atom_a in enumerate(ring_atom_ids):
            atom_b = ring_atom_ids[(index + 1) % len(ring_atom_ids)]
            if not isinstance(atom_a, int) or not isinstance(atom_b, int):
                continue
            bond_id = self.graph_service.bond_id_between(atom_a, atom_b)
            if bond_id is not None:
                bond_ids.add(bond_id)
        return bond_ids

    def refresh_bond_geometry_for_ring_item(self, item) -> None:
        self._refresh_bond_geometry_for_bond_ids(self.bond_ids_for_ring_item(item))

    def _refresh_bond_geometry_for_bond_ids(self, bond_ids: set[int]) -> None:
        for bond_id in bond_ids:
            update_bond_geometry_for(self.canvas, bond_id)

    def _refresh_bond_geometry_best_effort(
        self,
        bond_ids: set[int],
        *,
        original_error: BaseException,
    ) -> None:
        for bond_id in bond_ids:
            _run_rollback_step(
                original_error,
                f"refreshing bond {bond_id} after a failed ring attach",
                partial(update_bond_geometry_for, self.canvas, bond_id),
            )

    def attach_scene_item(self, item) -> None:
        if item_is_unavailable_for_scene_operation(item):
            return
        scene = canvas_scene_for_item_operation(self.canvas)
        if scene is None:
            return
        attach_ports = SceneItemAttachPorts.capture(scene, item)
        if not attach_ports.item_can_be_added():
            return
        kind = attach_ports.item_kind_for_attach()
        attach_ports.validate_attachment_contract(
            require_text_interaction=kind == "note",
        )
        ring_runtime = (
            _scene_runtime_snapshot(
                self.canvas,
                strict=True,
                scene_override=scene,
            )
            if kind == "ring"
            else None
        )
        snapshot = SceneItemAttachSnapshot.capture(
            self.canvas,
            item,
            scene=scene,
            attach_ports=attach_ports,
        )
        ring_bond_ids: set[int] = set()
        try:
            if kind == "ring":
                ring_bond_ids = self.bond_ids_for_ring_item(item)
            if kind == "note":
                attach_ports.apply_text_interaction_flags(
                    Qt.TextInteractionFlag.NoTextInteraction
                )
            self._register_scene_item(
                item,
                kind,
                mark_atom_id=snapshot.mark_atom_id,
            )
            attach_ports.apply_selectable()
            _add_item_with_attach_ports(attach_ports, item)
            if kind == "ring":
                self._refresh_bond_geometry_for_bond_ids(ring_bond_ids)
            snapshot.release()
        except BaseException as original_error:
            self._rollback_failed_attach(
                item,
                kind,
                snapshot=snapshot,
                ring_runtime=ring_runtime,
                ring_bond_ids=ring_bond_ids,
                original_error=original_error,
            )
            raise

    def _register_scene_item(
        self,
        item,
        kind,
        *,
        mark_atom_id: int | None,
    ) -> None:
        if kind == "ring":
            append_scene_item_for(self.canvas, "ring_items", item)
        elif kind == "mark":
            append_scene_item_for(self.canvas, "mark_items", item)
            if mark_atom_id is not None:
                self.marks.add_for_atom(mark_atom_id, item)
        elif kind == "note":
            append_scene_item_for(self.canvas, "note_items", item)
        elif kind in ARROW_KINDS:
            append_scene_item_for(self.canvas, "arrow_items", item)
        elif kind == "ts_bracket":
            append_scene_item_for(self.canvas, "ts_bracket_items", item)
        elif kind == "shape":
            append_scene_item_for(self.canvas, "shape_items", item)
        elif kind == "orbital":
            append_scene_item_for(self.canvas, "orbital_items", item)

    def _rollback_failed_attach(
        self,
        item,
        kind,
        *,
        snapshot: SceneItemAttachSnapshot,
        ring_runtime: _SceneRuntimeSnapshot | None,
        ring_bond_ids: set[int],
        original_error: BaseException,
    ) -> None:
        attach_ports = snapshot.attach_ports
        if attach_ports is None:
            raise RuntimeError("scene-item attach snapshot has no bound ports")
        _run_rollback_step(
            original_error,
            "removing a partial scene-item registration",
            partial(
                self._remove_scene_item_registration,
                item,
                kind,
                mark_atom_id=snapshot.mark_atom_id,
            ),
        )
        _run_rollback_step(
            original_error,
            "detaching a partially attached scene item",
            partial(attach_ports.remove_item, item),
        )
        if ring_bond_ids:
            self._refresh_bond_geometry_best_effort(
                ring_bond_ids,
                original_error=original_error,
            )
        snapshot.restore(
            original_error,
            phase="a failed scene-item attach",
            restore_scene_rect=ring_runtime is None,
        )
        if ring_runtime is not None:
            _run_rollback_step(
                original_error,
                "restoring exact ring-attach scene/runtime state",
                partial(
                    _restore_scene_runtime_snapshot,
                    ring_runtime,
                    original_error=original_error,
                ),
            )
            # Raw bond primitives are the final geometric authority. Only
            # release/restore automatic scene bounds after those primitives
            # are exact again, otherwise a sceneRect observer can permanently
            # cache a transiently expanded line/path extent.
            snapshot.restore_scene_rect(
                original_error,
                phase="a failed ring attach",
            )

    def _remove_scene_item_registration(
        self,
        item,
        kind,
        *,
        mark_atom_id: int | None = None,
    ) -> None:
        if kind == "ring":
            remove_scene_item_from_collection_for(self.canvas, "ring_items", item)
        elif kind == "mark":
            remove_scene_item_from_collection_for(self.canvas, "mark_items", item)
            if mark_atom_id is not None:
                marks = self.marks.get_for_atom(mark_atom_id)
                if marks is not None and item in marks:
                    marks.remove(item)
                if not marks:
                    self.marks.by_atom.pop(mark_atom_id, None)
        elif kind == "note":
            remove_selected_note_for(self.canvas, item)
            remove_scene_item_from_collection_for(self.canvas, "note_items", item)
        elif kind in ARROW_KINDS:
            remove_scene_item_from_collection_for(self.canvas, "arrow_items", item)
        elif kind == "ts_bracket":
            remove_scene_item_from_collection_for(self.canvas, "ts_bracket_items", item)
        elif kind == "shape":
            remove_scene_item_from_collection_for(self.canvas, "shape_items", item)
        elif kind == "orbital":
            remove_scene_item_from_collection_for(self.canvas, "orbital_items", item)

    def restore_scene_item(self, item) -> None:
        self.attach_scene_item(item)

    def remove_scene_item(self, item) -> None:
        if item is None:
            return
        kind = item.data(0)
        if kind == "mark":
            data = item.data(1) or {}
            atom_id = data.get("atom_id") if isinstance(data, dict) else None
            remove_mark_item_for(self.canvas, item)
            if isinstance(atom_id, int) and not self.marks.get_for_atom(atom_id):
                self.marks.by_atom.pop(atom_id, None)
            return
        was_selected_note = kind == "note" and item in selected_notes_for(self.canvas)
        self._remove_scene_item_registration(item, kind)
        if kind == "note":
            update_note_selection_box_for(self.canvas, item)
        if kind in {
            "shape",
            "orbital",
            "curved_single",
            "curved_double",
        } and item is handle_target_for(self.canvas):
            clear_handles_for(self.canvas)
        removed = remove_attached_item_from_canvas_scene(self.canvas, item)
        if was_selected_note:
            # Scene items emit selectionChanged when a selected item is removed,
            # which redraws the outline; notes carry their own selection state,
            # so an erased selected note must refresh explicitly or a stale
            # group box would linger.
            refresh_selection_outline_for(self.canvas)
        if removed is None:
            return
        if kind == "ring":
            self.refresh_bond_geometry_for_ring_item(item)


__all__ = ["SceneItemLifecycleService"]
