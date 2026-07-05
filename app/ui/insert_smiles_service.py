from __future__ import annotations

import contextlib
from collections.abc import Callable

from core.document_state import deserialize_model_state
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QMessageBox

from ui.benzene_preview_access import clear_benzene_preview_for
from ui.bond_graphics_access import parallel_bond_segments_for
from ui.canvas_atom_graphics_state import clear_atom_graphics_for
from ui.canvas_bond_graphics_state import clear_bond_graphics_for
from ui.canvas_document_state import (
    restore_document_post_model_items,
    restore_document_pre_model_items,
    restore_document_projection_state,
    snapshot_canvas_document_state,
)
from ui.canvas_insert_state import CanvasInsertState
from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_model_access import next_atom_id_for, set_model_for
from ui.canvas_scene_items_state import clear_scene_item_collections_for
from ui.canvas_scene_reset_access import clear_scene_for
from ui.canvas_smiles_input_state import set_last_smiles_input_for
from ui.canvas_window_access import notify_error_for
from ui.input_view_access import viewport_center_scene_pos_for
from ui.insert_commit_service import InsertCommitService
from ui.insert_mode_logic import InsertSessionState
from ui.insert_mode_logic import begin_smiles_insert as begin_smiles_insert_state
from ui.insert_mode_logic import cancel_smiles_insert as cancel_smiles_insert_state
from ui.insert_smiles_transaction import SmilesLoadTransactionBuilder
from ui.preview_scene_access import (
    apply_smiles_preview_geometry_for as apply_smiles_preview_geometry_helper,
)
from ui.preview_scene_access import (
    clear_smiles_preview_for as clear_smiles_preview_helper,
)
from ui.preview_scene_renderer import (
    smiles_preview_snapshot as smiles_preview_snapshot_helper,
)
from ui.rdkit_adapter_access import rdkit_last_error_for, smiles_to_2d_for
from ui.renderer_style_access import (
    bond_length_px_for,
    bond_line_width_for,
    bond_pen_for,
)
from ui.scene_decoration_access import add_mark_for_atom_for
from ui.scene_item_access import clear_canvas_scene, remove_scene_item
from ui.smiles_insert_logic import (
    SmilesPreviewResolvers,
    annotation_mark_direction,
    annotation_mark_kinds,
    normalized_atom_annotation,
    plan_smiles_commit,
    plan_smiles_preview_update,
    smiles_preview_center,
)

MAX_SMILES_INPUT_LENGTH = 1024


class InsertSmilesService:
    def __init__(
        self,
        canvas,
        *,
        insert_state: CanvasInsertState,
        insert_commit_service: InsertCommitService,
        graph_service,
        structure_build_service,
        history_service,
        session_state: Callable[[], InsertSessionState],
        apply_session_state: Callable[[InsertSessionState], None],
        cancel_template_insert: Callable[[], None],
        cancel_smiles_insert=None,
        clear_smiles_preview=None,
        render_smiles_preview=None,
    ) -> None:
        self.canvas = canvas
        self.insert_state = insert_state
        self.insert_commit_service = insert_commit_service
        self.graph_service = graph_service
        self.structure_build_service = structure_build_service
        self.history = history_service
        self._session_state = session_state
        self._apply_session_state = apply_session_state
        self._cancel_template_insert = cancel_template_insert
        self._cancel_smiles_insert_callback = cancel_smiles_insert
        self._clear_smiles_preview_callback = clear_smiles_preview
        self._render_smiles_preview_callback = render_smiles_preview
        self.transaction_builder = SmilesLoadTransactionBuilder(canvas)

    def _warn_smiles_error(self, message: str) -> None:
        if not notify_error_for(self.canvas, f"SMILES: {message}"):
            QMessageBox.warning(self.canvas, "SMILES Error", message)

    def _reject_oversized_smiles(self, smiles: str) -> bool:
        if len(smiles) <= MAX_SMILES_INPUT_LENGTH:
            return False
        self._warn_smiles_error(f"SMILES input is too long (maximum {MAX_SMILES_INPUT_LENGTH} characters).")
        return True

    def load_smiles(self, smiles: str) -> None:
        smiles = smiles.strip()
        if not smiles:
            return
        if self._reject_oversized_smiles(smiles):
            return
        model = smiles_to_2d_for(self.canvas, smiles, scale=bond_length_px_for(self.canvas))
        if model is None:
            self._warn_smiles_error(rdkit_last_error_for(self.canvas) or "Failed to render SMILES.")
            return
        if self.structure_build_service is None:
            raise RuntimeError("structure_build_service is required to load SMILES")
        document_snapshot = snapshot_canvas_document_state(self.canvas)
        snapshot = self.transaction_builder.capture()
        after_clear_next_atom_id = next_atom_id_for(self.canvas)
        added_scene_items: list[object] = []
        command = None
        mutated = False

        def build_load_command():
            if added_scene_items:
                return self.transaction_builder.build_command(
                    snapshot,
                    after_clear_next_atom_id=after_clear_next_atom_id,
                    after_smiles_input=smiles,
                    added_scene_items=added_scene_items,
                )
            return self.transaction_builder.build_command(
                snapshot,
                after_clear_next_atom_id=after_clear_next_atom_id,
                after_smiles_input=smiles,
            )

        try:
            mutated = True
            clear_scene_for(self.canvas)
            after_clear_next_atom_id = next_atom_id_for(self.canvas)
            set_model_for(self.canvas, model)
            self.graph_service.rebuild_bond_adjacency()
            set_last_smiles_input_for(self.canvas, smiles)
            self.structure_build_service.render_model()
            self._add_annotation_marks(model, added_scene_items)
            command = build_load_command()
            if command is not None:
                self.history.push(command)
        except Exception:
            if mutated:
                self._restore_document_state_after_failed_load(document_snapshot, added_scene_items)
            raise

    def begin_smiles_insert(self, smiles: str) -> None:
        if self.insert_state.template_active:
            self._cancel_template_insert()
        clear_benzene_preview_for(self.canvas)
        smiles = smiles.strip()
        if not smiles:
            return
        if self._reject_oversized_smiles(smiles):
            return
        model = smiles_to_2d_for(self.canvas, smiles, scale=bond_length_px_for(self.canvas))
        if model is None:
            self._warn_smiles_error(rdkit_last_error_for(self.canvas) or "Failed to render SMILES.")
            return
        self.insert_state.smiles_preview_model = model
        center_xy = smiles_preview_center(model)
        if center_xy is None:
            self.insert_state.smiles_preview_model = None
            return
        next_state = begin_smiles_insert_state(self._session_state(), smiles, center_xy)
        if next_state is None:
            self.insert_state.smiles_preview_model = None
            return
        self._apply_session_state(next_state)
        self._render_smiles_preview(viewport_center_scene_pos_for(self.canvas))

    def _render_smiles_preview(self, pos: QPointF) -> None:
        if self._render_smiles_preview_callback is not None:
            self._render_smiles_preview_callback(pos)
            return
        self.render_smiles_preview(pos)

    def cancel_smiles_insert(self) -> None:
        self.insert_state.smiles_preview_model = None
        next_state = cancel_smiles_insert_state(self._session_state())
        self._apply_session_state(next_state)

    def commit_smiles_insert(self, pos: QPointF) -> None:
        plan = plan_smiles_commit(
            self.insert_state.smiles_preview_model,
            None
            if self.insert_state.smiles_preview_center is None
            else (self.insert_state.smiles_preview_center.x(), self.insert_state.smiles_preview_center.y()),
            (pos.x(), pos.y()),
        )
        if plan is None:
            self._cancel_smiles_insert()
            return
        if not self.insert_commit_service.apply_smiles_commit(
            plan,
            after_smiles_input=self.insert_state.smiles_preview_smiles,
        ):
            self._cancel_smiles_insert()
            return
        self._cancel_smiles_insert()

    def _cancel_smiles_insert(self) -> None:
        if self._cancel_smiles_insert_callback is not None:
            self._cancel_smiles_insert_callback()
            return
        self.cancel_smiles_insert()

    def clear_smiles_preview(self) -> None:
        (
            self.insert_state.smiles_preview_items,
            self.insert_state.smiles_preview_bond_items,
            self.insert_state.smiles_preview_atom_items,
        ) = clear_smiles_preview_helper(self.canvas, self.insert_state.smiles_preview_items)

    def smiles_preview_snapshot(self):
        return smiles_preview_snapshot_helper(
            self.insert_state.smiles_preview_bond_items,
            self.insert_state.smiles_preview_atom_items,
        )

    def render_smiles_preview(self, pos: QPointF) -> None:
        atom_radius = max(0.6, bond_line_width_for(self.canvas) * 0.6)
        preview_plan = plan_smiles_preview_update(
            self.insert_state.smiles_preview_model,
            None
            if self.insert_state.smiles_preview_center is None
            else (self.insert_state.smiles_preview_center.x(), self.insert_state.smiles_preview_center.y()),
            (pos.x(), pos.y()),
            atom_radius,
            self.smiles_preview_snapshot(),
            SmilesPreviewResolvers(
                parallel_bond_segments=lambda *args: parallel_bond_segments_for(self.canvas, *args)
            ),
        )
        if preview_plan.action == "clear" or preview_plan.geometry is None:
            self._clear_smiles_preview()
            return
        (
            self.insert_state.smiles_preview_items,
            self.insert_state.smiles_preview_bond_items,
            self.insert_state.smiles_preview_atom_items,
        ) = apply_smiles_preview_geometry_helper(
            self.canvas,
            preview_plan.geometry,
            base_pen=bond_pen_for(self.canvas),
            existing_items=self.insert_state.smiles_preview_items,
            existing_bond_items=self.insert_state.smiles_preview_bond_items,
            existing_atom_items=self.insert_state.smiles_preview_atom_items,
            action=preview_plan.action,
        )

    def _clear_smiles_preview(self) -> None:
        if self._clear_smiles_preview_callback is not None:
            self._clear_smiles_preview_callback()
            return
        self.clear_smiles_preview()

    def _add_annotation_marks(self, model, added: list[object] | None = None) -> list[object]:
        if added is None:
            added = []
        atom_annotations = getattr(model, "atom_annotations", {})
        for atom_id, annotation in atom_annotations.items():
            atom = model.atoms.get(atom_id)
            if atom is None:
                continue
            annotation_values = normalized_atom_annotation(annotation)
            for index, kind in enumerate(annotation_mark_kinds(annotation_values)):
                direction_x, direction_y = annotation_mark_direction(index)
                item = add_mark_for_atom_for(
                    self.canvas,
                    atom_id,
                    QPointF(atom.x + direction_x, atom.y + direction_y),
                    kind=kind,
                    record=False,
                )
                if item is not None:
                    added.append(item)
        return added

    def _restore_document_state_after_failed_load(self, state: dict, added_scene_items: list[object]) -> None:
        for item in reversed(added_scene_items):
            with contextlib.suppress(Exception):
                remove_scene_item(self.canvas, item)
        with contextlib.suppress(Exception):
            clear_scene_for(self.canvas)
        with contextlib.suppress(Exception):
            clear_canvas_scene(self.canvas)
        with contextlib.suppress(Exception):
            clear_scene_item_collections_for(self.canvas)
        with contextlib.suppress(Exception):
            mark_registry_for(self.canvas).clear()
        with contextlib.suppress(Exception):
            clear_atom_graphics_for(self.canvas)
        with contextlib.suppress(Exception):
            clear_bond_graphics_for(self.canvas)
        with contextlib.suppress(Exception):
            set_model_for(self.canvas, deserialize_model_state(state["model"]))
        with contextlib.suppress(Exception):
            set_last_smiles_input_for(self.canvas, state.get("last_smiles_input"))
        with contextlib.suppress(Exception):
            self.graph_service.rebuild_bond_adjacency()
        with contextlib.suppress(Exception):
            restore_document_pre_model_items(self.canvas, state)
        with contextlib.suppress(Exception):
            restore_document_projection_state(self.canvas, state)
        with contextlib.suppress(Exception):
            self.structure_build_service.render_model()
        with contextlib.suppress(Exception):
            restore_document_post_model_items(self.canvas, state)


__all__ = ["MAX_SMILES_INPUT_LENGTH", "InsertSmilesService"]
