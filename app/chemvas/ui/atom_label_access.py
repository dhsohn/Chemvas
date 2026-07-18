from __future__ import annotations

from PyQt6.QtGui import QColor

from chemvas.ui.canvas_atom_graphics_state import atom_items_for, visible_atom_item_for
from chemvas.ui.canvas_model_access import atom_for_id
from chemvas.ui.canvas_service_access import optional_canvas_service_method
from chemvas.ui.canvas_service_ports import atom_label_service_for_access


def atom_label_service(canvas):
    return atom_label_service_for_access(canvas)


def atom_item_for_id_for(canvas, atom_id: int):
    atom_item_for_id = optional_canvas_service_method(
        canvas, atom_label_service_for_access, "atom_item_for_id"
    )
    if atom_item_for_id is not None:
        return atom_item_for_id(atom_id)
    return visible_atom_item_for(canvas, atom_id)


def implicit_carbon_dot_brush_for(canvas):
    implicit_carbon_dot_brush = optional_canvas_service_method(
        canvas,
        atom_label_service_for_access,
        "implicit_carbon_dot_brush",
    )
    if implicit_carbon_dot_brush is not None:
        return implicit_carbon_dot_brush()
    return QColor(0, 0, 0, 0)


def atom_has_visible_label_for(canvas, atom_id: int) -> bool:
    atom = atom_for_id(canvas, atom_id)
    if atom is None:
        return False
    return (
        atom.element != "C" or atom.explicit_label or atom_id in atom_items_for(canvas)
    )


def uses_compact_label_hit_shape_for(canvas, text: str) -> bool:
    text = text.strip()
    if len(text) == 1:
        return text.isalpha() and text.upper() == text
    if len(text) == 2:
        return (
            text[0].isalpha()
            and text[0].upper() == text[0]
            and text[1].isalpha()
            and text[1].lower() == text[1]
        )
    return False


def add_or_update_atom_label(
    canvas,
    atom_id: int,
    text: str,
    *,
    clear_smiles: bool = True,
    record: bool = True,
    allow_merge: bool = True,
    show_carbon: bool = False,
    include_default_kwargs: bool = True,
) -> None:
    if include_default_kwargs:
        kwargs = {
            "clear_smiles": clear_smiles,
            "record": record,
            "allow_merge": allow_merge,
            "show_carbon": show_carbon,
        }
    else:
        kwargs = {}
        if not clear_smiles:
            kwargs["clear_smiles"] = False
        if not record:
            kwargs["record"] = False
        if not allow_merge:
            kwargs["allow_merge"] = False
        if show_carbon:
            kwargs["show_carbon"] = True
    atom_label_service(canvas).add_or_update_atom_label(atom_id, text, **kwargs)


def clear_atom_label_for(canvas, atom_id: int) -> None:
    if atom_for_id(canvas, atom_id) is None:
        return
    add_or_update = optional_canvas_service_method(
        canvas,
        atom_label_service_for_access,
        "add_or_update_atom_label",
    )
    if add_or_update is not None:
        add_or_update(atom_id, "C", show_carbon=False)


def prompt_atom_label_for(canvas, atom_id: int) -> None:
    prompt_atom_label = optional_canvas_service_method(
        canvas, atom_label_service_for_access, "prompt_atom_label"
    )
    if prompt_atom_label is not None:
        prompt_atom_label(atom_id)


__all__ = [
    "add_or_update_atom_label",
    "atom_has_visible_label_for",
    "atom_item_for_id_for",
    "atom_label_service",
    "clear_atom_label_for",
    "implicit_carbon_dot_brush_for",
    "prompt_atom_label_for",
    "uses_compact_label_hit_shape_for",
]
