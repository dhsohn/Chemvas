from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPolygonF
from PyQt6.QtWidgets import QGraphicsItem

from chemvas.core.history import (
    capture_history_transaction_for_command,
    release_history_transaction_for_command,
    restore_history_transaction_for_command,
)
from chemvas.domain.transactions import add_recovery_error_note
from chemvas.ui.annotations.projections import (
    find_projection,
    resolve_projection,
    restore_active_projection,
)
from chemvas.ui.canvas.canvas_calculation_plan_state import set_calculation_plan_for
from chemvas.ui.canvas.canvas_callback_state import (
    run_scene_selection_group_callback_for,
)
from chemvas.ui.canvas.canvas_color_mutation_service import apply_bond_color_in_place
from chemvas.ui.canvas.canvas_group_state import (
    CanvasGroupState,
    register_group_for,
    restore_group_for,
)
from chemvas.ui.canvas.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas.canvas_scene_items_state import (
    SCENE_ITEM_COLLECTION_ATTRS,
    document_collection_for,
    require_scene_record_id,
)
from chemvas.ui.canvas.canvas_smiles_input_state import set_last_smiles_input_for
from chemvas.ui.canvas.sheet_setup_access import set_sheet_setup_for
from chemvas.ui.history.history_atom_position_restore import (
    set_atom_positions_for_history,
)
from chemvas.ui.history.history_commands import DeletedSceneItemOrder
from chemvas.ui.molecule.atom_coords_access import pop_atom_coords_3d_for
from chemvas.ui.molecule.atom_label_access import add_or_update_atom_label
from chemvas.ui.molecule.bond_length_graphics_refresh import (
    refresh_bond_length_graphics_for,
)
from chemvas.ui.scene.annotation_style_service import apply_annotation_style_for
from chemvas.ui.scene.scene_item_access import (
    remove_scene_item,
    restore_scene_item,
)
from chemvas.ui.scene.scene_signal_blocking import blocked_scene_signals
from chemvas.ui.transactions.document import DocumentSavepoint
from chemvas.ui.transactions.scene_runtime import capture_scene_runtime
from chemvas.ui.transactions.scene_runtime_restore import (
    create_scene_items_atomically,
    mutate_existing_scene_items_atomically,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from chemvas.domain.document.groups import SceneGroup
    from chemvas.domain.transactions import RestoreOutcome
    from chemvas.ui.transactions.document import MoveGestureScope
    from chemvas.ui.transactions.scene_runtime import SceneRuntimeSnapshot


class CanvasHistoryOperations:
    """Bind canonical UI mutation and transaction ports once for a canvas.

    Commands receive only these named operations. The canvas stays private to
    this adapter; document savepoints and history still own rollback policy.
    """

    __slots__ = ("__canvas",)

    def __init__(self, canvas) -> None:
        self.__canvas = canvas

    def capture_history_transaction_for_history(
        self,
        *,
        history_service=None,
        guard_scene_rect: bool = True,
        move_scope: MoveGestureScope | None = None,
    ) -> DocumentSavepoint:
        return DocumentSavepoint.capture(
            self.__canvas,
            history_service=history_service,
            guard_scene_rect=guard_scene_rect,
            move_scope=move_scope,
        )

    def restore_history_transaction_for_history(
        self, snapshot: DocumentSavepoint
    ) -> RestoreOutcome:
        return snapshot.restore()

    def release_history_transaction_for_history(
        self, snapshot: DocumentSavepoint
    ) -> None:
        snapshot.release()

    def move_atoms_for_history(
        self,
        atom_ids: set[int],
        dx: float,
        dy: float,
        *,
        bond_ids: set[int] | None = None,
        redraw_bond_ids: set[int] | None = None,
        update_selection: bool = True,
    ) -> None:
        transaction = capture_history_transaction_for_command(self)
        before_positions: dict[int, tuple[float, float]] = {}
        before_coords_3d: dict[int, tuple[float, float, float]] = {}
        try:
            # Position and 3D-coordinate properties are live preflight ports. They
            # belong to the same exact transaction as the move so a fail-before
            # descriptor still publishes authoritative rollback to history stacks.
            for atom_id in atom_ids:
                atom = self.__canvas.model.atom_for_id(atom_id)
                if atom is None:
                    continue
                before_positions[atom_id] = (atom.x, atom.y)
                coords_3d = (
                    self.__canvas.runtime_state.atom_coords_3d_state.atom_coords_3d.get(
                        atom_id
                    )
                )
                if coords_3d is not None:
                    before_coords_3d[atom_id] = coords_3d
            self.__canvas.services.move_controller.move_atoms(
                atom_ids,
                dx,
                dy,
                bond_ids=bond_ids,
                redraw_bond_ids=redraw_bond_ids,
                update_selection=update_selection,
                # History replay is a one-shot application: a boundary bond whose
                # length change altered its derived hash-mark count must rebuild
                # rather than keep the frozen mid-gesture count.
                rebuild_stale_bond_topology=True,
            )
            release_history_transaction_for_command(self, transaction)
        except Exception as original_error:
            # The move controller mutates atoms one at a time before redrawing
            # dependent graphics. Restore absolute positions instead of applying
            # the inverse delta to every requested atom: some atoms may not have
            # been reached when the original call failed.
            try:
                set_atom_positions_for_history(
                    self.__canvas,
                    before_positions,
                    update_selection=update_selection,
                    coords_3d=before_coords_3d or None,
                )
            except Exception as rollback_error:
                add_recovery_error_note(
                    original_error,
                    rollback_error,
                    phase="restoring the atom positions from before the move",
                )
            # The canonical setter is itself a multi-atom operation and can stop
            # after restoring only an early atom. The exact transaction snapshot
            # restores all model/3D/graphics/selection state independently of that
            # partial compensation while retaining the primary exception.
            restore_result = restore_history_transaction_for_command(
                self,
                transaction,
                original_error,
            )
            for exact_restore_error in restore_result.errors:
                add_recovery_error_note(
                    original_error,
                    exact_restore_error,
                    phase="restoring the exact move transaction",
                )
            raise

    def restore_projection_state_for_history(
        self,
        projection_center_3d: tuple[float, float, float] | None,
        projection_anchor_2d: tuple[float, float] | None,
    ) -> None:
        state = self.__canvas.runtime_state.rotation_state
        state.projection_center_3d = projection_center_3d
        state.projection_anchor_2d = projection_anchor_2d

    def set_atom_positions_for_history(
        self,
        positions: dict[int, tuple[float, float]],
        *,
        update_selection: bool = True,
        coords_3d: dict[int, tuple[float, float, float]] | None = None,
    ) -> None:
        set_atom_positions_for_history(
            self.__canvas,
            positions,
            update_selection=update_selection,
            coords_3d=coords_3d,
        )

    def set_ring_polygons_for_history(
        self, ring_ids: list[int], polygons: list[list[tuple[float, float]]]
    ) -> None:
        for record_id, points in zip(ring_ids, polygons, strict=True):
            ring = restore_active_projection(self.__canvas, record_id)
            ring.setPolygon(QPolygonF([QPointF(x, y) for x, y in points]))

    def set_last_smiles_input_for_history(self, value: str | None) -> None:
        set_last_smiles_input_for(self.__canvas, value)

    def set_next_atom_id_for_history(self, atom_id: int) -> None:
        self.__canvas.model.next_atom_id = atom_id

    def restore_bond_length_for_history(self, length_px: float) -> None:
        self.__canvas.renderer.set_bond_length(length_px)
        refresh_bond_length_graphics_for(self.__canvas)
        self.__canvas.services.hit_testing_service.mark_spatial_index_dirty()

    def remove_atom_for_history(
        self, atom_id: int, *, remove_marks: bool = True
    ) -> None:
        self.__canvas.services.canvas_atom_mutation_service.remove_atom_only(
            atom_id, remove_marks=remove_marks
        )

    def restore_atom_from_state_for_history(self, atom_id: int, state: dict) -> None:
        self.__canvas.services.canvas_atom_mutation_service.restore_atom_from_state(
            atom_id, state
        )

    def apply_atom_color_for_history(self, atom_id: int, color) -> None:
        self.__canvas.services.canvas_atom_mutation_service.apply_atom_color(
            atom_id, color
        )

    def restore_mark_from_state_for_history(self, mark_state: dict):
        return (
            self.__canvas.services.scene_item_controller.create_scene_item_from_state(
                {**mark_state, "kind": "mark"}
            )
        )

    def restore_bond_from_state_for_history(
        self, bond_id: int, bond_state: dict
    ) -> None:
        self.__canvas.services.canvas_bond_mutation_service.restore_bond_from_state(
            bond_id, bond_state
        )

    def remove_bond_for_history(self, bond_id: int) -> None:
        self.__canvas.services.canvas_bond_mutation_service.remove_bond_by_id(bond_id)

    def trim_bonds_for_history(self, length: int) -> None:
        self.__canvas.services.canvas_bond_mutation_service.trim_bonds_to_length(length)

    def apply_scene_item_state(self, item_id: int, state: dict) -> None:
        item = restore_active_projection(self.__canvas, item_id, state)
        self.__canvas.services.scene_item_controller.apply_scene_item_state(item, state)

    def clear_handles_for_target(self, item_id: int) -> None:
        """Drop handles placed from the geometry this command replaced.

        A lightweight canvas without a runtime container has no handles.
        """
        runtime_state = getattr(self.__canvas, "runtime_state", None)
        handle_state = getattr(runtime_state, "handle_state", None)
        if handle_state is None or getattr(
            handle_state, "target", None
        ) is not find_projection(self.__canvas, item_id):
            return
        self.__canvas.services.handle_overlay_service.clear_handles()

    def refresh_selection_outline(self) -> None:
        self.__canvas.services.selection.update_selection_outline()

    def capture_scene_runtime(self) -> SceneRuntimeSnapshot:
        return capture_scene_runtime(self.__canvas)

    def blocked_scene_signals(self) -> AbstractContextManager[None]:
        return blocked_scene_signals(self.__canvas.scene())

    def pop_atom_coords_3d(self, atom_id: int) -> tuple[float, float, float] | None:
        return pop_atom_coords_3d_for(self.__canvas, atom_id)

    def capture_scene_item_order(self, item_ids: list[int]) -> DeletedSceneItemOrder:
        ids = set(item_ids)
        runtime = self.__canvas.runtime_state
        collections = {
            name: [
                (index, key)
                for index, key in enumerate(
                    document_collection_for(runtime, name).order
                )
                if key in ids
            ]
            for name in SCENE_ITEM_COLLECTION_ATTRS
        }
        items = [find_projection(self.__canvas, key) for key in item_ids]
        cohorts = {
            (item.parentItem(), item.zValue())
            for item in items
            if item is not None and item.scene() is not None
        }
        references = {
            id(item): ("annotation", key, 0)
            for name in SCENE_ITEM_COLLECTION_ATTRS
            for key, item in getattr(runtime.scene_items_state, name).items()
        }
        for kind, entries in self._structure_stacking_items():
            for key, parts in entries.items():
                for part, item in enumerate(parts):
                    references[id(item)] = (kind, key, part)
        siblings = [
            [
                references[id(item)]
                for item in self.__canvas.scene().items(Qt.SortOrder.AscendingOrder)
                if item.parentItem() is parent
                and item.zValue() == z
                and id(item) in references
            ]
            for parent, z in cohorts
        ]
        return DeletedSceneItemOrder(collections, siblings)

    def _structure_stacking_items(self):
        runtime = self.__canvas.runtime_state
        return (
            (
                "atom",
                {
                    key: [item]
                    for key, item in runtime.atom_graphics_state.atom_items.items()
                },
            ),
            (
                "dot",
                {
                    key: [item]
                    for key, item in runtime.atom_graphics_state.atom_dots.items()
                },
            ),
            ("bond", runtime.bond_graphics_state.bond_items),
        )

    def restore_scene_item_order(self, order: DeletedSceneItemOrder) -> None:
        for name, entries in order.collections.items():
            document = document_collection_for(self.__canvas.runtime_state, name)
            ids = list(document.order)
            for _, key in entries:
                ids.remove(key)
            for index, key in entries:
                ids.insert(index, key)
            document.reorder(ids)
        structure = dict(self._structure_stacking_items())
        for siblings in order.siblings:
            resolved = []
            for kind, key, part in siblings:
                if kind == "annotation":
                    item = find_projection(self.__canvas, key)
                else:
                    parts = structure[kind].get(key, ())
                    item = parts[part] if part < len(parts) else None
                resolved.append(item)
            attached = [
                item
                for item in resolved
                if item is not None and item.scene() is not None
            ]
            for index in range(len(attached) - 2, -1, -1):
                attached[index].stackBefore(attached[index + 1])

    def group_state(self) -> CanvasGroupState:
        return self.__canvas.runtime_state.group_state

    def remove_group(self, group_id: int) -> SceneGroup | None:
        return self.__canvas.runtime_state.group_state.groups.pop(group_id, None)

    def register_group(self, atom_ids: set[int], items: list) -> int:
        return register_group_for(self.__canvas, atom_ids, items)

    def restore_group(self, group_id: int, group: SceneGroup) -> None:
        restore_group_for(self.__canvas, group_id, group)

    def route_scene_selection_group_changed(self) -> None:
        run_scene_selection_group_callback_for(self.__canvas)

    def restore_mark_ownership(
        self,
        marks: dict[int, tuple[int, ...]],
        annotations: dict[int, dict[str, int]],
    ) -> None:
        registry = mark_registry_for(self.__canvas)
        model_annotations = self.__canvas.model.atom_annotations
        for atom_id, items in marks.items():
            if items:
                registry.by_atom.setdefault(atom_id, [])[:] = [
                    resolve_projection(self.__canvas, key) for key in items
                ]
            else:
                registry.by_atom.pop(atom_id, None)
            if atom_id in annotations:
                model_annotations[atom_id] = dict(annotations[atom_id])
            else:
                model_annotations.pop(atom_id, None)

    def set_calculation_plan(self, state: dict[str, object] | None) -> None:
        set_calculation_plan_for(self.__canvas, state)

    def restore_atom_label(
        self, atom_id: int, element: str, explicit_label: bool
    ) -> None:
        add_or_update_atom_label(
            self.__canvas,
            atom_id,
            element,
            clear_smiles=False,
            record=False,
            allow_merge=False,
            show_carbon=explicit_label,
            literal_label=explicit_label,
        )

    def create_scene_items(self, states: list[dict]) -> list[int]:
        items: list = []
        create_scene_items_atomically(
            self.__canvas,
            [
                {key: value for key, value in state.items() if not key.startswith("_")}
                for state in states
            ],
            items,
        )
        return [require_scene_record_id(item) for item in items]

    def restore_scene_items(
        self,
        item_ids: list[int],
        states: list[dict],
        *,
        after_mutation: Callable[[], None] | None = None,
    ) -> None:
        items = [
            resolve_projection(self.__canvas, key, state)
            for key, state in zip(item_ids, states, strict=True)
        ]
        for item, state in zip(items, states, strict=True):
            if "_z_value" in state:
                item.setZValue(state["_z_value"])

        def restore_runtime() -> None:
            for item, state in zip(items, states, strict=True):
                if "_selected" in state:
                    item.setSelected(state["_selected"])
            if after_mutation is not None:
                after_mutation()

        mutate_existing_scene_items_atomically(
            self.__canvas,
            items,
            restore_scene_item,
            unknown_was_attached=False,
            after_mutation=restore_runtime,
        )

    def remove_scene_items(self, item_ids: list[int], states: list[dict]) -> None:
        items = [
            resolve_projection(self.__canvas, key, state)
            for key, state in zip(item_ids, states, strict=True)
        ]
        selection = [
            item.isSelected() if isinstance(item, QGraphicsItem) else None
            for item in items
        ]
        mutate_existing_scene_items_atomically(
            self.__canvas,
            items,
            remove_scene_item,
            unknown_was_attached=True,
        )
        for state, selected in zip(states, selection, strict=True):
            if selected is not None:
                state["_selected"] = selected

    def apply_annotation_style(self, target: str, state, item_id: int | None) -> None:
        if target == "note":
            if item_id is None:
                raise ValueError("note text history requires a document ID")
            state.apply(restore_active_projection(self.__canvas, item_id))
        elif target == "text":
            self.__canvas.services.style_controller.restore_text_style(state)
        elif target == "annotation":
            apply_annotation_style_for(self.__canvas, state)
        else:
            raise ValueError(f"Unknown annotation style target: {target}")

    def apply_sheet_setup(self, size_name: str, orientation: str) -> None:
        set_sheet_setup_for(self.__canvas, size_name, orientation)

    def apply_bond_color(self, bond_id: int, color) -> None:
        apply_bond_color_in_place(self.__canvas, bond_id, color)


__all__ = ["CanvasHistoryOperations"]
