from __future__ import annotations

from typing import TYPE_CHECKING, Any

from chemvas.core.history import (
    capture_history_transaction_for_command,
    release_history_transaction_for_command,
    restore_history_transaction_for_command,
)
from chemvas.domain.transactions import add_recovery_error_note
from chemvas.ui.atom_coords_access import atom_coords_3d_for_id, pop_atom_coords_3d_for
from chemvas.ui.atom_label_access import add_or_update_atom_label
from chemvas.ui.canvas_calculation_plan_state import set_calculation_plan_for
from chemvas.ui.canvas_callback_state import run_scene_selection_group_callback_for
from chemvas.ui.canvas_color_mutation_service import apply_bond_color_in_place
from chemvas.ui.canvas_group_state import (
    CanvasGroupState,
    CanvasSceneGroup,
    group_state_for,
    register_group_for,
    remove_group_for,
    restore_group_for,
)
from chemvas.ui.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas_model_access import (
    atom_annotations_for,
    atom_for_id,
    set_next_atom_id_for,
)
from chemvas.ui.canvas_scene_items_state import scene_item_collection_for
from chemvas.ui.canvas_service_ports import (
    structure_mutation_atom_service,
    structure_mutation_bond_service,
)
from chemvas.ui.canvas_smiles_input_state import set_last_smiles_input_for
from chemvas.ui.handle_overlay_access import clear_handles_for
from chemvas.ui.history_canvas_access import (
    apply_atom_color_for_history,
    capture_history_transaction_for_history,
    release_history_transaction_for_history,
    remove_atom_for_history,
    restore_bond_length_for_history,
    restore_history_transaction_for_history,
    restore_projection_state_for_history,
    set_atom_positions_for_history,
    set_ring_polygons_for_history,
    trim_bonds_for_history,
)
from chemvas.ui.move_access import move_atoms_for, refresh_selection_outline_for_canvas
from chemvas.ui.scene_item_access import (
    apply_scene_item_state,
    remove_scene_item,
    restore_mark_from_state,
    restore_scene_item,
)
from chemvas.ui.scene_signal_blocking import blocked_scene_signals
from chemvas.ui.transactions.scene_runtime import (
    capture_scene_runtime,
    create_scene_items_atomically,
    mutate_existing_scene_items_atomically,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from chemvas.domain.transactions import RestoreOutcome
    from chemvas.ui.transactions.document import DocumentSavepoint, MoveGestureScope
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
        return capture_history_transaction_for_history(
            self.__canvas,
            history_service=history_service,
            guard_scene_rect=guard_scene_rect,
            move_scope=move_scope,
        )

    def restore_history_transaction_for_history(
        self, snapshot: DocumentSavepoint
    ) -> RestoreOutcome:
        return restore_history_transaction_for_history(self.__canvas, snapshot)

    def release_history_transaction_for_history(
        self, snapshot: DocumentSavepoint
    ) -> None:
        release_history_transaction_for_history(self.__canvas, snapshot)

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
                atom = atom_for_id(self.__canvas, atom_id)
                if atom is None:
                    continue
                before_positions[atom_id] = (atom.x, atom.y)
                coords_3d = atom_coords_3d_for_id(self.__canvas, atom_id)
                if coords_3d is not None:
                    before_coords_3d[atom_id] = coords_3d
            move_atoms_for(
                self.__canvas,
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
        restore_projection_state_for_history(
            self.__canvas, projection_center_3d, projection_anchor_2d
        )

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
        self, ring_items: list, polygons: list[list[tuple[float, float]]]
    ) -> None:
        set_ring_polygons_for_history(self.__canvas, ring_items, polygons)

    def set_last_smiles_input_for_history(self, value: str | None) -> None:
        set_last_smiles_input_for(self.__canvas, value)

    def set_next_atom_id_for_history(self, atom_id: int) -> None:
        set_next_atom_id_for(self.__canvas, atom_id)

    def restore_bond_length_for_history(self, length_px: float) -> None:
        restore_bond_length_for_history(self.__canvas, length_px)

    def remove_atom_for_history(
        self, atom_id: int, *, remove_marks: bool = True
    ) -> None:
        remove_atom_for_history(self.__canvas, atom_id, remove_marks=remove_marks)

    def restore_atom_from_state_for_history(self, atom_id: int, state: dict) -> None:
        structure_mutation_atom_service(self.__canvas).restore_atom_from_state(
            atom_id, state
        )

    def apply_atom_color_for_history(self, atom_id: int, color) -> None:
        apply_atom_color_for_history(self.__canvas, atom_id, color)

    def restore_mark_from_state_for_history(self, mark_state: dict):
        return restore_mark_from_state(self.__canvas, mark_state)

    def restore_bond_from_state_for_history(
        self, bond_id: int, bond_state: dict
    ) -> None:
        structure_mutation_bond_service(self.__canvas).restore_bond_from_state(
            bond_id, bond_state
        )

    def remove_bond_for_history(self, bond_id: int) -> None:
        structure_mutation_bond_service(self.__canvas).remove_bond_by_id(bond_id)

    def trim_bonds_for_history(self, length: int) -> None:
        trim_bonds_for_history(self.__canvas, length)

    def apply_scene_item_state(self, item: object, state: dict) -> None:
        apply_scene_item_state(self.__canvas, item, state)

    def clear_handles_for_target(self, item: object) -> None:
        """Drop handles placed from the geometry this command replaced.

        A lightweight canvas without a runtime container has no handles.
        """
        runtime_state = getattr(self.__canvas, "runtime_state", None)
        handle_state = getattr(runtime_state, "handle_state", None)
        if handle_state is None or getattr(handle_state, "target", None) is not item:
            return
        clear_handles_for(self.__canvas)

    def refresh_selection_outline(self) -> None:
        refresh_selection_outline_for_canvas(self.__canvas)

    def capture_scene_runtime(self) -> SceneRuntimeSnapshot:
        return capture_scene_runtime(self.__canvas)

    def blocked_scene_signals(self) -> AbstractContextManager[None]:
        return blocked_scene_signals(self.__canvas.scene())

    def pop_atom_coords_3d(self, atom_id: int) -> tuple[float, float, float] | None:
        return pop_atom_coords_3d_for(self.__canvas, atom_id)

    def scene_item_collection(self, name: str) -> list[Any]:
        return scene_item_collection_for(self.__canvas, name)

    def group_state(self) -> CanvasGroupState:
        return group_state_for(self.__canvas)

    def remove_group(self, group_id: int) -> CanvasSceneGroup | None:
        return remove_group_for(self.__canvas, group_id)

    def register_group(self, atom_ids: set[int], items: list) -> int:
        return register_group_for(self.__canvas, atom_ids, items)

    def restore_group(self, group_id: int, group: CanvasSceneGroup) -> None:
        restore_group_for(self.__canvas, group_id, group)

    def route_scene_selection_group_changed(self) -> None:
        run_scene_selection_group_callback_for(self.__canvas)

    def restore_mark_ownership(
        self,
        marks: dict[int, tuple[object, ...]],
        annotations: dict[int, dict[str, int]],
    ) -> None:
        registry = mark_registry_for(self.__canvas)
        model_annotations = atom_annotations_for(self.__canvas)
        for atom_id, items in marks.items():
            if items:
                registry.by_atom.setdefault(atom_id, [])[:] = items
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

    def create_scene_items(self, states: list[dict], items: list) -> None:
        create_scene_items_atomically(self.__canvas, states, items)

    def restore_scene_items(
        self, items: list, *, after_mutation: Callable[[], None] | None = None
    ) -> None:
        mutate_existing_scene_items_atomically(
            self.__canvas,
            items,
            restore_scene_item,
            unknown_was_attached=False,
            after_mutation=after_mutation,
        )

    def remove_scene_items(self, items: list) -> None:
        mutate_existing_scene_items_atomically(
            self.__canvas,
            items,
            remove_scene_item,
            unknown_was_attached=True,
        )

    def apply_bond_color(self, bond_id: int, color) -> None:
        apply_bond_color_in_place(self.__canvas, bond_id, color)


__all__ = ["CanvasHistoryOperations"]
