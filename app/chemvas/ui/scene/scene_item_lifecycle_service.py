from __future__ import annotations

from functools import partial

from PyQt6.QtCore import Qt

from chemvas.domain.transactions import run_rollback_step
from chemvas.ui.annotations.items import RingFillItem
from chemvas.ui.annotations.state import ARROW_KINDS
from chemvas.ui.canvas.canvas_mark_registry import mark_registry_for
from chemvas.ui.molecule.bond_renderer_access import update_bond_geometry_for
from chemvas.ui.scene.scene_item_access import (
    canvas_scene_for_item_operation,
    item_is_unavailable_for_scene_operation,
    remove_attached_item_from_canvas_scene,
)
from chemvas.ui.selection.selection_state import remove_selected_note_for
from chemvas.ui.transactions.scene_item_attach import (
    SceneItemAttachPorts,
    SceneItemAttachSnapshot,
)
from chemvas.ui.transactions.scene_runtime import (
    SceneRuntimeSnapshot,
    capture_scene_runtime,
)
from chemvas.ui.transactions.scene_runtime_restore import restore_scene_runtime

# Every kind that can own handles; deleting one must take its handles with it.
HANDLE_BEARING_KINDS = ARROW_KINDS | frozenset({"shape", "orbital"})


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
            run_rollback_step(
                original_error,
                f"refreshing bond {bond_id} after a failed ring attach",
                partial(update_bond_geometry_for, self.canvas, bond_id),
            )

    def attach_scene_item(self, item) -> bool:
        if item_is_unavailable_for_scene_operation(item):
            return False
        scene = canvas_scene_for_item_operation(self.canvas)
        if scene is None:
            return False
        attach_ports = SceneItemAttachPorts.capture(scene, item)
        if not attach_ports.item_can_be_added():
            return False
        kind = attach_ports.item_kind_for_attach()
        attach_ports.validate_attachment_contract(
            require_text_interaction=kind == "note",
        )
        ring_runtime = (
            capture_scene_runtime(
                self.canvas,
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
                if isinstance(item, RingFillItem):
                    item.render_geometry()
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
            return True
        except Exception as original_error:
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
            self.canvas.runtime_state.append_scene_item("ring_items", item)
        elif kind == "mark":
            self.canvas.runtime_state.append_scene_item("mark_items", item)
            if mark_atom_id is not None:
                self.marks.add_for_atom(mark_atom_id, item)
        elif kind == "note":
            self.canvas.runtime_state.append_scene_item("note_items", item)
        elif kind == "image":
            self.canvas.runtime_state.append_scene_item("image_items", item)
        elif kind in ARROW_KINDS:
            self.canvas.render_context.arrows.record(item)
            self.canvas.runtime_state.append_scene_item("arrow_items", item)
        elif kind == "ts_bracket":
            self.canvas.runtime_state.append_scene_item("ts_bracket_items", item)
        elif kind == "shape":
            self.canvas.runtime_state.append_scene_item("shape_items", item)
        elif kind == "orbital":
            self.canvas.runtime_state.append_scene_item("orbital_items", item)

    def _rollback_failed_attach(
        self,
        item,
        kind,
        *,
        snapshot: SceneItemAttachSnapshot,
        ring_runtime: SceneRuntimeSnapshot | None,
        ring_bond_ids: set[int],
        original_error: BaseException,
    ) -> None:
        attach_ports = snapshot.attach_ports
        if attach_ports is None:
            raise RuntimeError("scene-item attach snapshot has no bound ports")
        run_rollback_step(
            original_error,
            "removing a partial scene-item registration",
            partial(
                self._remove_scene_item_registration,
                item,
                kind,
                mark_atom_id=snapshot.mark_atom_id,
            ),
        )
        # ``attach_ports.remove_item`` is resolved inside the callable rather
        # than by ``partial``, which would look it up before the rollback step's
        # ``try`` and let a missing port method escape and mask the primary
        # error instead of becoming a note.
        run_rollback_step(
            original_error,
            "detaching a partially attached scene item",
            lambda: attach_ports.remove_item(item),
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
            run_rollback_step(
                original_error,
                "restoring exact ring-attach scene/runtime state",
                partial(
                    restore_scene_runtime,
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
            self.canvas.runtime_state.remove_scene_item("ring_items", item)
        elif kind == "mark":
            self.canvas.runtime_state.remove_scene_item("mark_items", item)
            if mark_atom_id is not None:
                marks = self.marks.get_for_atom(mark_atom_id)
                if marks is not None and item in marks:
                    marks.remove(item)
                if not marks:
                    self.marks.by_atom.pop(mark_atom_id, None)
        elif kind == "note":
            remove_selected_note_for(self.canvas, item)
            self.canvas.runtime_state.remove_scene_item("note_items", item)
        elif kind == "image":
            self.canvas.runtime_state.remove_scene_item("image_items", item)
        elif kind in ARROW_KINDS:
            self.canvas.runtime_state.remove_scene_item("arrow_items", item)
        elif kind == "ts_bracket":
            self.canvas.runtime_state.remove_scene_item("ts_bracket_items", item)
        elif kind == "shape":
            self.canvas.runtime_state.remove_scene_item("shape_items", item)
        elif kind == "orbital":
            self.canvas.runtime_state.remove_scene_item("orbital_items", item)

    def restore_scene_item(self, item) -> None:
        if not self.attach_scene_item(item):
            return
        if item_is_unavailable_for_scene_operation(item) or item.data(0) != "mark":
            return
        data = item.data(1)
        atom_id = data.get("atom_id") if isinstance(data, dict) else None
        if not isinstance(atom_id, int):
            return
        self.canvas.services.canvas_mark_scene_service.sync_marks_for_atom(atom_id)

    def remove_scene_item(self, item) -> None:
        if item is None:
            return
        kind = item.data(0)
        if kind == "mark":
            data = item.data(1) or {}
            atom_id = data.get("atom_id") if isinstance(data, dict) else None
            self.canvas.services.canvas_mark_scene_service.remove_mark_item(item)
            if isinstance(atom_id, int) and not self.marks.get_for_atom(atom_id):
                self.marks.by_atom.pop(atom_id, None)
            return
        was_selected_note = (
            kind == "note"
            and item in self.canvas.runtime_state.selection_state.selected_notes
        )
        self._remove_scene_item_registration(item, kind)
        if kind == "note":
            self.canvas.services.selection.update_note_selection_box(item)
        if (
            kind in HANDLE_BEARING_KINDS
            and item is self.canvas.runtime_state.handle_state.target
        ):
            self.canvas.services.handle_overlay_service.clear_handles()
        removed = remove_attached_item_from_canvas_scene(self.canvas, item)
        if was_selected_note:
            # Scene items emit selectionChanged when a selected item is removed,
            # which redraws the outline; notes carry their own selection state,
            # so an erased selected note must refresh explicitly or a stale
            # group box would linger.
            self.canvas.services.selection.update_selection_outline()
        if removed is None:
            return
        if kind == "ring":
            self.refresh_bond_geometry_for_ring_item(item)


__all__ = ["SceneItemLifecycleService"]
