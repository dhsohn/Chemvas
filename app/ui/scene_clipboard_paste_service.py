from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtWidgets import QGraphicsItem

from ui.atom_coords_access import atom_coords_3d_for
from ui.canvas_model_access import atom_for_id, bond_count_for, next_atom_id_for
from ui.canvas_rotation_state import rotation_state_for
from ui.canvas_smiles_input_state import last_smiles_input_for
from ui.history_canvas_access import (
    capture_history_transaction_for_history,
    release_history_transaction_for_history,
    restore_history_transaction_for_history,
)
from ui.history_recording_access import record_additions_for
from ui.insert_commit_rollback import rollback_insert_mutation
from ui.renderer_style_access import bond_length_px_for
from ui.scene_clipboard_access import (
    clipboard_paste_count_for,
    clipboard_paste_source_json_for,
    set_clipboard_paste_count_for,
    set_clipboard_paste_source_json_for,
)
from ui.scene_clipboard_selection import (
    capture_clipboard_selection_snapshot_for_canvas,
    restore_clipboard_selection_snapshot_for_canvas,
)
from ui.scene_clipboard_transaction_logic import (
    build_clipboard_paste_plan,
    clipboard_paste_offset,
    translated_scene_item_state,
)
from ui.scene_item_access import remove_scene_item
from ui.scene_paste_apply_logic import apply_paste_payload


@dataclass(frozen=True, slots=True)
class SceneClipboardPasteCallbacks:
    add_atom: Callable[[str, float, float], int]
    apply_atom_color: Callable[[int, str], None]
    set_atom_annotation: Callable[[int, dict[str, int] | None], None]
    add_or_update_atom_label: Callable[..., None]
    add_bond: Callable[[int, int, int], int]
    restore_bond_from_state: Callable[[int, dict], None]
    create_scene_item_from_state: Callable[[dict], object]
    select_pasted_content: Callable[[set[int], list[QGraphicsItem]], None]
    apply_perspective: Callable[
        [dict[int, tuple[float, float, float]], tuple[float, float, float] | None, tuple[float, float] | None],
        None,
    ]


def _add_clipboard_rollback_note(
    original_error: BaseException,
    cleanup_error: BaseException,
    *,
    phase: str,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if not callable(add_note):
            return
        add_note(f"Clipboard {phase} rollback also failed: {cleanup_error!r}")
    except BaseException:
        return


def paste_selection_from_clipboard_for_canvas(
    canvas,
    *,
    payload_provider: Callable[[], tuple[dict | None, str | None]],
    callbacks: SceneClipboardPasteCallbacks,
) -> bool:
    payload, payload_json = payload_provider()
    previous_source_json = clipboard_paste_source_json_for(canvas)
    previous_paste_count = clipboard_paste_count_for(canvas)
    plan = build_clipboard_paste_plan(
        payload=payload,
        payload_json=payload_json,
        previous_source_json=previous_source_json,
        previous_paste_count=previous_paste_count,
        bond_length_px=bond_length_px_for(canvas),
        clipboard_paste_offset=clipboard_paste_offset,
        before_next_atom_id=next_atom_id_for(canvas),
        before_bond_count=bond_count_for(canvas),
        before_smiles_input=last_smiles_input_for(canvas),
    )
    if plan is None:
        return False
    # Only advance the paste offset bookkeeping once we know the payload is
    # actually applicable; an empty/invalid payload must not perturb the
    # cascade offset for the next real paste.
    if not plan.has_payload_content():
        return False
    before_smiles_input = plan.before_smiles_input if isinstance(plan.before_smiles_input, str) else None
    selection_snapshot = capture_clipboard_selection_snapshot_for_canvas(canvas)
    services = getattr(canvas, "services", None)
    tracked_scene_items: list[object] = []

    def create_tracked_scene_item_from_state(state: dict) -> object:
        item = callbacks.create_scene_item_from_state(state)
        if item is not None:
            tracked_scene_items.append(item)
        return item

    exact_transaction = capture_history_transaction_for_history(
        canvas,
        history_service=getattr(services, "history_service", None),
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
            add_atom=callbacks.add_atom,
            apply_atom_color=callbacks.apply_atom_color,
            set_atom_annotation=callbacks.set_atom_annotation,
            add_or_update_atom_label=callbacks.add_or_update_atom_label,
            add_bond=callbacks.add_bond,
            restore_bond_from_state=callbacks.restore_bond_from_state,
            translated_scene_item_state=translated_scene_item_state,
            create_scene_item_from_state=create_tracked_scene_item_from_state,
            apply_perspective=callbacks.apply_perspective,
        )

        if not result.has_changes():
            release_history_transaction_for_history(canvas, exact_transaction)
            return False

        added_scene_items = [item for item in result.added_scene_items if isinstance(item, QGraphicsItem)]
        callbacks.select_pasted_content(result.new_atom_ids, added_scene_items)
        record_additions_for(
            canvas,
            plan.before_next_atom_id,
            plan.before_bond_count,
            before_smiles_input,
            added_scene_items=added_scene_items,
        )
        set_clipboard_paste_source_json_for(canvas, plan.paste_source_json)
        set_clipboard_paste_count_for(canvas, plan.paste_count)
        release_history_transaction_for_history(canvas, exact_transaction)
    except BaseException as error:
        for item in reversed(tracked_scene_items):
            try:
                remove_scene_item(canvas, item)
            except BaseException as cleanup_error:
                _add_clipboard_rollback_note(
                    error,
                    cleanup_error,
                    phase="scene cleanup",
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
        except BaseException as cleanup_error:
            _add_clipboard_rollback_note(
                error,
                cleanup_error,
                phase="mutation",
            )
        try:
            restore_clipboard_selection_snapshot_for_canvas(canvas, selection_snapshot)
        except BaseException as cleanup_error:
            _add_clipboard_rollback_note(
                error,
                cleanup_error,
                phase="selection",
            )
        try:
            set_clipboard_paste_source_json_for(canvas, previous_source_json)
        except BaseException as cleanup_error:
            _add_clipboard_rollback_note(
                error,
                cleanup_error,
                phase="source",
            )
        try:
            set_clipboard_paste_count_for(canvas, previous_paste_count)
        except BaseException as cleanup_error:
            _add_clipboard_rollback_note(
                error,
                cleanup_error,
                phase="count",
            )
        try:
            restore_result = restore_history_transaction_for_history(
                canvas,
                exact_transaction,
            )
            for exact_restore_error in restore_result.errors:
                _add_clipboard_rollback_note(
                    error,
                    exact_restore_error,
                    phase="exact",
                )
        except BaseException as cleanup_error:
            _add_clipboard_rollback_note(
                error,
                cleanup_error,
                phase="exact",
            )
        raise

    return True


def apply_pasted_perspective_for_canvas(
    canvas,
    coords_3d: dict[int, tuple[float, float, float]],
    projection_center_3d: tuple[float, float, float] | None,
    projection_anchor_2d: tuple[float, float] | None,
) -> None:
    rotation = rotation_state_for(canvas)
    target_center = rotation.projection_center_3d
    target_anchor = rotation.projection_anchor_2d
    stored_coords = atom_coords_3d_for(canvas)
    for atom_id, coords in coords_3d.items():
        atom = atom_for_id(canvas, atom_id)
        if atom is None:
            continue
        target_z = coords[2]
        if target_center is not None and projection_center_3d is not None:
            target_z = target_center[2] + (coords[2] - projection_center_3d[2])
        stored_coords[atom_id] = _coords_for_projection_frame(
            canvas,
            atom.x,
            atom.y,
            target_z,
            center_3d=target_center,
            anchor_2d=target_anchor,
        )


def _coords_for_projection_frame(
    canvas,
    screen_x: float,
    screen_y: float,
    z: float,
    *,
    center_3d: tuple[float, float, float] | None,
    anchor_2d: tuple[float, float] | None,
) -> tuple[float, float, float]:
    if center_3d is None:
        return screen_x, screen_y, z
    cx, cy, cz = center_3d
    anchor_x, anchor_y = anchor_2d or (cx, cy)
    focal = max(bond_length_px_for(canvas) * 8.0, 120.0)
    dz = max(min(z - cz, focal * 0.7), -focal * 0.8)
    denom = max(focal - dz, focal * 0.2)
    scale = focal / denom
    return (
        cx + (screen_x - anchor_x) / scale,
        cy + (screen_y - anchor_y) / scale,
        z,
    )


__all__ = [
    "SceneClipboardPasteCallbacks",
    "apply_pasted_perspective_for_canvas",
    "paste_selection_from_clipboard_for_canvas",
]
