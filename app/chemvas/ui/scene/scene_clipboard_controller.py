from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QApplication, QGraphicsItem, QMessageBox

from chemvas.domain.document import (
    validate_image_collection_budget,
    validate_image_states,
)
from chemvas.domain.transactions import add_recovery_error_note
from chemvas.features.selection import unproject_point_3d
from chemvas.ui.annotations.state import (
    atom_state_dict_for,
    bond_state_dict,
    scene_item_state_for,
)
from chemvas.ui.canvas.canvas_format_access import clipboard_selection_version_for
from chemvas.ui.canvas.canvas_group_state import register_group_for
from chemvas.ui.canvas.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id
from chemvas.ui.history.history_commands import GroupSceneItemsCommand
from chemvas.ui.insert.insert_commit_rollback import rollback_insert_mutation
from chemvas.ui.molecule.atom_label_access import add_or_update_atom_label
from chemvas.ui.molecule.structure_mutation_access import add_bond_for
from chemvas.ui.scene.image_actions import image_bytes_from_mime, insert_image_bytes
from chemvas.ui.scene.scene_clipboard_access import (
    build_selection_clipboard_payload_for_canvas,
)
from chemvas.ui.scene.scene_clipboard_copy_io import (
    CLIPBOARD_PDF_MIME,
    CLIPBOARD_SVG_MIME,
)
from chemvas.ui.scene.scene_clipboard_copy_service import (
    copy_selection_to_clipboard_for_canvas,
)
from chemvas.ui.scene.scene_clipboard_logic import (
    clipboard_payload_candidates,
    decode_clipboard_selection_payload,
)
from chemvas.ui.scene.scene_clipboard_selection import (
    capture_clipboard_selection_snapshot_for_canvas,
    restore_clipboard_selection_snapshot_for_canvas,
    select_pasted_content_for_canvas,
)
from chemvas.ui.scene.scene_clipboard_transaction_logic import (
    build_clipboard_paste_plan,
    clipboard_paste_offset,
    translated_scene_item_state,
)
from chemvas.ui.scene.scene_item_access import (
    create_scene_item_from_state as create_scene_item_from_state_helper,
)
from chemvas.ui.scene.scene_paste_apply_logic import apply_paste_payload
from chemvas.ui.selection.selection_queries import (
    selected_ids_for,
    selected_items_for_transform_for,
)
from chemvas.ui.transactions.document import DocumentSavepoint

if TYPE_CHECKING:
    from collections.abc import Callable


class SceneClipboardController:
    def __init__(
        self,
        canvas,
        *,
        selection_controller=None,
        bond_mutation_service=None,
    ) -> None:
        self.canvas = canvas
        self.selection_controller = selection_controller
        self.bond_mutation_service = bond_mutation_service
        self.marks = mark_registry_for(canvas)

    def _restore_bond(self, bond_id: int, bond_state: dict) -> None:
        if self.bond_mutation_service is None:
            raise RuntimeError(
                "SceneClipboardController requires bond_mutation_service"
            )
        self.bond_mutation_service.restore_bond_from_state(bond_id, bond_state)

    def _clear_note_selection(self) -> None:
        if self.selection_controller is not None:
            self.selection_controller.clear_note_selection()

    def _select_pasted_note(self, item) -> None:
        if self.selection_controller is not None:
            self.selection_controller.select_note(item, additive=True)

    def _clipboard(self):
        clipboard = QApplication.clipboard()
        if clipboard is None:
            msg = "QApplication clipboard is unavailable"
            raise RuntimeError(msg)
        return clipboard

    def selection_payload_for_clipboard(self) -> dict | None:
        selected_items = selected_items_for_transform_for(self.canvas)
        explicit_atom_ids, bond_ids = selected_ids_for(self.canvas)
        return build_selection_clipboard_payload_for_canvas(
            self.canvas,
            selected_items=selected_items,
            explicit_atom_ids=explicit_atom_ids,
            selected_bond_ids=bond_ids,
            bonds=self.canvas.model.bonds,
            atom_state_getter=partial(atom_state_dict_for, self.canvas),
            bond_state_getter=bond_state_dict,
            scene_item_state_getter=partial(scene_item_state_for, self.canvas),
            version=clipboard_selection_version_for(self.canvas),
        )

    def clipboard_selection_payload(self) -> tuple[dict | None, str | None]:
        mime_data = self._clipboard().mimeData()
        payload_candidates = clipboard_payload_candidates(
            mime_data,
            mime_type=str(self.canvas.CLIPBOARD_SELECTION_MIME),
        )
        return decode_clipboard_selection_payload(
            payload_candidates,
            version=clipboard_selection_version_for(self.canvas),
        )

    def select_pasted_content(
        self, atom_ids: set[int], scene_items: list[QGraphicsItem]
    ) -> None:
        select_pasted_content_for_canvas(
            self.canvas,
            atom_ids=atom_ids,
            scene_items=scene_items,
            clear_note_selection=self._clear_note_selection,
            select_note=self._select_pasted_note,
        )

    def copy_selection_to_clipboard(self, *, payload_provider=None) -> bool:
        provider = (
            payload_provider
            if callable(payload_provider)
            else self.selection_payload_for_clipboard
        )
        try:
            return copy_selection_to_clipboard_for_canvas(
                self.canvas,
                clipboard=self._clipboard(),
                payload_provider=provider,
            )
        except ValueError as error:
            if payload_provider is not None:
                raise
            QMessageBox.warning(self.canvas, "Copy", str(error))
            return False

    def paste_selection_from_clipboard(self, *, payload_provider=None) -> bool:
        if payload_provider is None:
            mime = self._clipboard().mimeData()
            if mime is not None and not mime.hasFormat(
                str(self.canvas.CLIPBOARD_SELECTION_MIME)
            ):
                try:
                    data = image_bytes_from_mime(mime)
                    if data is not None:
                        insert_image_bytes(self.canvas, data)
                        return True
                except ValueError as error:
                    QMessageBox.warning(self.canvas, "Paste Image", str(error))
                    return False
        provider = (
            payload_provider
            if callable(payload_provider)
            else self.clipboard_selection_payload
        )
        try:
            return self._paste_payload(provider)
        except ValueError as error:
            if payload_provider is not None:
                raise
            QMessageBox.warning(self.canvas, "Paste", str(error))
            return False

    def _paste_payload(
        self, payload_provider: Callable[[], tuple[dict | None, str | None]]
    ) -> bool:
        canvas = self.canvas
        payload, payload_json = payload_provider()
        previous_source_json = (
            canvas.runtime_state.scene_clipboard_state.paste_source_json
        )
        previous_paste_count = canvas.runtime_state.scene_clipboard_state.paste_count
        plan = build_clipboard_paste_plan(
            payload=payload,
            payload_json=payload_json,
            previous_source_json=previous_source_json,
            previous_paste_count=previous_paste_count,
            bond_length_px=canvas.renderer.style.bond_length_px,
            clipboard_paste_offset=clipboard_paste_offset,
            before_next_atom_id=int(canvas.model.next_atom_id),
            before_bond_count=len(canvas.model.bonds),
            before_smiles_input=canvas.runtime_state.smiles_input_state.last_smiles_input,
        )
        if plan is None:
            return False
        # Only advance the paste offset bookkeeping once we know the payload is
        # actually applicable; an empty/invalid payload must not perturb the
        # cascade offset for the next real paste.
        if not plan.has_payload_content():
            return False
        incoming_images = [
            state
            for state in plan.scene_items
            if isinstance(state, dict) and state.get("kind") == "image"
        ]
        if incoming_images:
            from chemvas.domain.document.images import image_to_state

            existing_images = canvas.runtime_state.image_state.snapshot(image_to_state)
            validate_image_collection_budget([*existing_images, *incoming_images])
            validate_image_states(incoming_images)
        before_smiles_input = (
            plan.before_smiles_input
            if isinstance(plan.before_smiles_input, str)
            else None
        )
        selection_snapshot = capture_clipboard_selection_snapshot_for_canvas(canvas)
        tracked_scene_items: list[object] = []

        def create_tracked_scene_item_from_state(state: dict) -> object:
            item = create_scene_item_from_state_helper(canvas, state)
            if item is not None:
                tracked_scene_items.append(item)
            return item

        exact_transaction = DocumentSavepoint.capture(
            canvas, history_service=canvas.services.history_service
        )
        try:
            result = apply_paste_payload(
                atoms=plan.atoms,
                bonds=plan.bonds,
                rings=plan.rings,
                marks=plan.marks,
                scene_items=plan.scene_items,
                perspective=plan.perspective,
                dx=plan.dx,
                dy=plan.dy,
                add_atom=canvas.services.canvas_atom_mutation_service.add_atom,
                apply_atom_color=canvas.services.history_service.operations.apply_atom_color_for_history,
                set_atom_annotation=canvas.model.set_atom_annotation,
                add_or_update_atom_label=partial(add_or_update_atom_label, canvas),
                add_bond=partial(add_bond_for, canvas),
                restore_bond_from_state=self._restore_bond,
                translated_scene_item_state=translated_scene_item_state,
                create_scene_item_from_state=create_tracked_scene_item_from_state,
                apply_perspective=self._apply_pasted_perspective,
            )

            if not result.has_changes():
                exact_transaction.release()
                return False

            added_scene_items = [
                item
                for item in result.added_scene_items
                if isinstance(item, QGraphicsItem)
            ]
            added_groups = []
            for group in plan.groups:
                atom_ids = {result.atom_id_map[atom_id] for atom_id in group["atoms"]}
                items = [result.scene_item_map[tuple(ref)] for ref in group["items"]]
                group_id = register_group_for(
                    canvas, atom_ids, [require_scene_record_id(item) for item in items]
                )
                added_groups.append(
                    GroupSceneItemsCommand(
                        atom_ids,
                        [require_scene_record_id(item) for item in items],
                        group_id=group_id,
                    )
                )
            self.select_pasted_content(result.new_atom_ids, added_scene_items)
            canvas.services.canvas_history_recording_service.record_additions(
                plan.before_next_atom_id,
                plan.before_bond_count,
                before_smiles_input,
                added_scene_items=added_scene_items,
                added_groups=added_groups,
            )
            canvas.runtime_state.scene_clipboard_state.record_paste_source(
                plan.paste_source_json, plan.paste_count
            )
            exact_transaction.release()
        except Exception as error:
            for item in reversed(tracked_scene_items):
                try:
                    canvas.services.scene_item_controller.remove_scene_item(item)
                except Exception as cleanup_error:
                    add_recovery_error_note(
                        error,
                        cleanup_error,
                        phase="removing the pasted scene items",
                    )
            try:
                rollback_insert_mutation(
                    canvas,
                    before_next_atom_id=plan.before_next_atom_id,
                    before_bond_count=plan.before_bond_count,
                    before_smiles_input=before_smiles_input,
                    exact_transaction=None,
                    original_error=error,
                )
            except Exception as cleanup_error:
                add_recovery_error_note(
                    error,
                    cleanup_error,
                    phase="rolling back the paste mutation",
                )
            try:
                restore_clipboard_selection_snapshot_for_canvas(
                    canvas, selection_snapshot
                )
            except Exception as cleanup_error:
                add_recovery_error_note(
                    error,
                    cleanup_error,
                    phase="restoring the selection from before the paste",
                )
            try:
                canvas.runtime_state.scene_clipboard_state.record_paste_source(
                    previous_source_json, previous_paste_count
                )
            except Exception as cleanup_error:
                add_recovery_error_note(
                    error,
                    cleanup_error,
                    phase="restoring the clipboard paste source and count",
                )
            try:
                restore_result = exact_transaction.restore()
                for exact_restore_error in restore_result.errors:
                    add_recovery_error_note(
                        error,
                        exact_restore_error,
                        phase="restoring the exact paste transaction",
                    )
            except Exception as cleanup_error:
                add_recovery_error_note(
                    error,
                    cleanup_error,
                    phase="restoring the exact paste transaction",
                )
            raise

        return True

    def _apply_pasted_perspective(
        self,
        coords_3d: dict[int, tuple[float, float, float]],
        projection_center_3d: tuple[float, float, float] | None,
        _source_anchor: tuple[float, float] | None,
    ) -> None:
        # The pure payload callback supplies the source anchor. Reprojection
        # uses the target canvas anchor, as it did before the transfer.
        canvas = self.canvas
        rotation = canvas.runtime_state.rotation_state
        target_center = rotation.projection_center_3d
        target_anchor = rotation.projection_anchor_2d
        stored_coords = canvas.runtime_state.atom_coords_3d_state.atom_coords_3d
        for atom_id, coords in coords_3d.items():
            atom = canvas.model.atom_for_id(atom_id)
            if atom is None:
                continue
            target_z = coords[2]
            if target_center is not None and projection_center_3d is not None:
                target_z = target_center[2] + (coords[2] - projection_center_3d[2])
            stored_coords[atom_id] = unproject_point_3d(
                (atom.x, atom.y),
                target_z,
                bond_length_px=canvas.renderer.style.bond_length_px,
                center_3d=target_center,
                anchor_2d=target_anchor,
            )


__all__ = [
    "CLIPBOARD_PDF_MIME",
    "CLIPBOARD_SVG_MIME",
    "SceneClipboardController",
]
