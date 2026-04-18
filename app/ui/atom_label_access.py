from __future__ import annotations


def atom_label_service(canvas):
    return getattr(canvas, "_atom_label_service", None)


def add_or_update_atom_label(
    canvas,
    atom_id: int,
    text: str,
    *,
    clear_smiles: bool = True,
    record: bool = True,
    allow_merge: bool = True,
    show_carbon: bool = False,
) -> None:
    service = atom_label_service(canvas)
    if service is not None:
        service.add_or_update_atom_label(
            atom_id,
            text,
            clear_smiles=clear_smiles,
            record=record,
            allow_merge=allow_merge,
            show_carbon=show_carbon,
        )
        return
    canvas.add_or_update_atom_label(
        atom_id,
        text,
        clear_smiles=clear_smiles,
        record=record,
        allow_merge=allow_merge,
        show_carbon=show_carbon,
    )


__all__ = ["add_or_update_atom_label", "atom_label_service"]
