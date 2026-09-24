from __future__ import annotations

from chemvas.domain.document import atom_shows_itself
from chemvas.ui.molecule.atom_label_renderer import uses_compact_label_hit_shape


def atom_has_visible_label_for(canvas, atom_id: int) -> bool:
    atom = canvas.model.atom_for_id(atom_id)
    if atom is None:
        return False
    return (
        atom_shows_itself(atom)
        or atom_id in canvas.runtime_state.atom_graphics_state.atom_items
    )


def uses_compact_label_hit_shape_for(canvas, text: str) -> bool:
    return uses_compact_label_hit_shape(text)


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
    canvas.services.atom_label_service.add_or_update_atom_label(atom_id, text, **kwargs)


def clear_atom_label_for(canvas, atom_id: int) -> None:
    if canvas.model.atom_for_id(atom_id) is None:
        return
    canvas.services.atom_label_service.add_or_update_atom_label(
        atom_id, "C", show_carbon=False
    )


__all__ = [
    "add_or_update_atom_label",
    "atom_has_visible_label_for",
    "clear_atom_label_for",
    "uses_compact_label_hit_shape_for",
]
