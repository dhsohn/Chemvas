from __future__ import annotations

from typing import Any

from ui.canvas_service_ports import history_recording_service_for_access


def record_additions_for(
    canvas,
    before_next_atom_id: int,
    before_bond_count: int,
    before_smiles_input: str | None,
    *,
    added_scene_items: list | None = None,
) -> None:
    kwargs: dict[str, Any] = {
        "before_next_atom_id": before_next_atom_id,
        "before_bond_count": before_bond_count,
        "before_smiles_input": before_smiles_input,
    }
    if added_scene_items is not None:
        kwargs["added_scene_items"] = added_scene_items
    history_recording_service_for_access(canvas).record_additions(**kwargs)


def record_bond_update_for(canvas, *args) -> None:
    history_recording_service_for_access(canvas).record_bond_update(*args)


__all__ = ["record_additions_for", "record_bond_update_for"]
