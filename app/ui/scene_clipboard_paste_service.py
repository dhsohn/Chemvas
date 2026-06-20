from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtWidgets import QGraphicsItem

from ui.canvas_model_access import bond_count_for, next_atom_id_for
from ui.canvas_smiles_input_state import last_smiles_input_for
from ui.history_recording_access import record_additions_for
from ui.renderer_style_access import bond_length_px_for
from ui.scene_clipboard_access import (
    clipboard_paste_count_for,
    clipboard_paste_source_json_for,
    set_clipboard_paste_count_for,
    set_clipboard_paste_source_json_for,
)
from ui.scene_clipboard_transaction_logic import (
    build_clipboard_paste_plan,
    clipboard_paste_offset,
    translated_scene_item_state,
)
from ui.scene_paste_apply_logic import apply_paste_payload


@dataclass(frozen=True, slots=True)
class SceneClipboardPasteCallbacks:
    add_atom: Callable[[str, float, float], int]
    apply_atom_color: Callable[[int, str], None]
    add_or_update_atom_label: Callable[..., None]
    add_bond: Callable[[int, int, int], int]
    restore_bond_from_state: Callable[[int, dict], None]
    create_scene_item_from_state: Callable[[dict], object]
    select_pasted_content: Callable[[set[int], list[QGraphicsItem]], None]


def paste_selection_from_clipboard_for_canvas(
    canvas,
    *,
    payload_provider: Callable[[], tuple[dict | None, str | None]],
    callbacks: SceneClipboardPasteCallbacks,
) -> bool:
    payload, payload_json = payload_provider()
    plan = build_clipboard_paste_plan(
        payload=payload,
        payload_json=payload_json,
        previous_source_json=clipboard_paste_source_json_for(canvas),
        previous_paste_count=clipboard_paste_count_for(canvas),
        bond_length_px=bond_length_px_for(canvas),
        clipboard_paste_offset=clipboard_paste_offset,
        before_next_atom_id=next_atom_id_for(canvas),
        before_bond_count=bond_count_for(canvas),
        before_smiles_input=last_smiles_input_for(canvas),
    )
    if plan is None:
        return False
    set_clipboard_paste_source_json_for(canvas, plan.paste_source_json)
    set_clipboard_paste_count_for(canvas, plan.paste_count)
    if not plan.has_payload_content():
        return False

    result = apply_paste_payload(
        atoms=plan.atoms,
        bonds=plan.bonds,
        rings=plan.rings,
        marks=plan.marks,
        scene_items=plan.scene_items,
        dx=plan.dx,
        dy=plan.dy,
        add_atom=callbacks.add_atom,
        apply_atom_color=callbacks.apply_atom_color,
        add_or_update_atom_label=callbacks.add_or_update_atom_label,
        add_bond=callbacks.add_bond,
        restore_bond_from_state=callbacks.restore_bond_from_state,
        translated_scene_item_state=translated_scene_item_state,
        create_scene_item_from_state=callbacks.create_scene_item_from_state,
    )

    if not result.has_changes():
        return False

    added_scene_items = [item for item in result.added_scene_items if isinstance(item, QGraphicsItem)]
    callbacks.select_pasted_content(result.new_atom_ids, added_scene_items)
    before_smiles_input = plan.before_smiles_input if isinstance(plan.before_smiles_input, str) else None
    record_additions_for(
        canvas,
        plan.before_next_atom_id,
        plan.before_bond_count,
        before_smiles_input,
        added_scene_items=added_scene_items,
    )
    return True


__all__ = [
    "SceneClipboardPasteCallbacks",
    "paste_selection_from_clipboard_for_canvas",
]
