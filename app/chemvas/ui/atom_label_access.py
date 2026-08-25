from __future__ import annotations

from chemvas.ui.canvas_atom_graphics_state import atom_items_for
from chemvas.ui.canvas_model_access import atom_for_id
from chemvas.ui.canvas_service_ports import atom_label_service_for_access


def atom_label_service(canvas):
    return atom_label_service_for_access(canvas)


def atom_item_for_id_for(canvas, atom_id: int):
    return atom_label_service_for_access(canvas).atom_item_for_id(atom_id)


def implicit_carbon_dot_brush_for(canvas):
    return atom_label_service_for_access(canvas).implicit_carbon_dot_brush()


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
    literal_label: bool | None = None,
    include_default_kwargs: bool = True,
) -> None:
    if include_default_kwargs:
        kwargs = {
            "clear_smiles": clear_smiles,
            "record": record,
            "allow_merge": allow_merge,
            "show_carbon": show_carbon,
        }
        if literal_label is not None:
            kwargs["literal_label"] = literal_label
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
        if literal_label is not None:
            kwargs["literal_label"] = literal_label
    atom_label_service(canvas).add_or_update_atom_label(atom_id, text, **kwargs)


def clear_atom_label_for(canvas, atom_id: int) -> None:
    if atom_for_id(canvas, atom_id) is None:
        return
    atom_label_service_for_access(canvas).add_or_update_atom_label(
        atom_id, "C", show_carbon=False
    )


def prompt_atom_label_for(canvas, atom_id: int) -> None:
    atom_label_service_for_access(canvas).prompt_atom_label(atom_id)


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
