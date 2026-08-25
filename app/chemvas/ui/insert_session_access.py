from __future__ import annotations

from chemvas.ui.canvas_service_ports import insert_controller_for_access


def cancel_smiles_insert_for(canvas) -> None:
    insert_controller_for_access(canvas).cancel_smiles_insert()


def clear_smiles_preview_for(canvas) -> None:
    insert_controller_for_access(canvas).clear_smiles_preview()


def cancel_template_insert_for(canvas) -> None:
    insert_controller_for_access(canvas).cancel_template_insert()


def clear_template_preview_for(canvas) -> None:
    insert_controller_for_access(canvas).clear_template_preview()


def apply_insert_session_state_for(canvas, state) -> None:
    insert_controller_for_access(canvas).apply_insert_session_state(state)


__all__ = [
    "apply_insert_session_state_for",
    "cancel_smiles_insert_for",
    "cancel_template_insert_for",
    "clear_smiles_preview_for",
    "clear_template_preview_for",
]
