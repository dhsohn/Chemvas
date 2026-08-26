from __future__ import annotations

import time

from chemvas.features.insertion import model_with_atom_annotations
from chemvas.ui.canvas_rotation_state import rotation_state_for
from chemvas.ui.rdkit_adapter_access import (
    compute_props_for,
    preload_rdkit_for,
    rdkit_is_loaded_for,
    rdkit_is_unavailable_for,
)
from chemvas.ui.selection_info_state import (
    SelectionSignature,
    selection_info_state_for,
)


def _selection_ids_for_info(canvas) -> tuple[set[int], set[int]]:
    from chemvas.ui.selection_collection_access import selected_chemical_ids_for

    return selected_chemical_ids_for(canvas)


def _arm_rdkit_idle_timer(canvas) -> None:
    """Start the per-canvas idle warmup timer if one is attached and stopped.

    The timer self-stops once no warmup is pending, so it must be re-armed
    whenever a new selection needs RDKit properties.
    """
    timer = getattr(getattr(canvas, "runtime_state", None), "rdkit_idle_timer", None)
    if timer is not None and not timer.isActive():
        timer.start()


def _selection_signature(
    atom_ids: set[int],
    bond_ids: set[int],
    submodel,
    atom_annotations,
) -> SelectionSignature:
    # Fingerprint what the formula actually consumes, not just which ids are
    # selected: a mark or label edit on a held selection must miss the cache.
    return (
        frozenset(atom_ids),
        frozenset(bond_ids),
        tuple(
            (atom_id, atom.element) for atom_id, atom in sorted(submodel.atoms.items())
        ),
        tuple(
            (bond.a, bond.b, bond.order)
            for bond in submodel.bonds
            if bond is not None
        ),
        tuple(
            (atom_id, tuple(sorted(atom_annotations[atom_id].items())))
            for atom_id in sorted(atom_annotations)
        ),
    )


def _blank_selection_info(state, callback) -> None:
    state.signature = None
    state.pending_signature = None
    state.cache = ("", "")
    state.rdkit_warmup_pending = False
    callback("", "")


def emit_selection_info_for(canvas) -> None:
    state = selection_info_state_for(canvas)
    callback = state.callback
    if not callback:
        return
    rotation_selection_ids = rotation_state_for(canvas).selection_ids
    if rotation_selection_ids is not None:
        atom_ids, bond_ids = rotation_selection_ids
    else:
        atom_ids, bond_ids = _selection_ids_for_info(canvas)
    if not atom_ids and not bond_ids:
        _blank_selection_info(state, callback)
        return
    if rdkit_is_unavailable_for(canvas):
        _blank_selection_info(state, callback)
        return
    if not rdkit_is_loaded_for(canvas):
        pending_signature = (frozenset(atom_ids), frozenset(bond_ids))
        if pending_signature != state.pending_signature:
            state.pending_signature = pending_signature
            state.cache = ("", "")
            callback("", "")
        state.rdkit_warmup_pending = True
        _arm_rdkit_idle_timer(canvas)
        return
    from chemvas.ui.structure_payload_access import build_structure_payload_for

    # The bare submodel drops the mark layer, silently neutralizing charged
    # and radical selections; the payload builder is the same charge/radical
    # source that MOL/XYZ export and the 3D panel read.
    try:
        submodel, atom_annotations, _ = build_structure_payload_for(
            canvas, atom_ids, bond_ids
        )
    except ValueError:
        # A stale selection with no exportable structure has nothing to report.
        _blank_selection_info(state, callback)
        return
    signature = _selection_signature(atom_ids, bond_ids, submodel, atom_annotations)
    if signature == state.signature:
        formula_text, mw_text = state.cache
        callback(formula_text, mw_text)
        return
    if atom_annotations:
        submodel = model_with_atom_annotations(submodel, atom_annotations)
    formula, mw, _ = compute_props_for(canvas, submodel)
    formula_text = formula or ""
    mw_text = f"{mw:.2f}" if mw is not None else ""
    state.signature = signature
    state.pending_signature = None
    state.cache = (formula_text, mw_text)
    callback(formula_text, mw_text)


def maybe_warm_rdkit_for(canvas) -> None:
    state = selection_info_state_for(canvas)
    if not state.rdkit_warmup_pending:
        return
    if rdkit_is_unavailable_for(canvas):
        state.rdkit_warmup_pending = False
        state.pending_signature = None
        return
    if rdkit_is_loaded_for(canvas):
        state.rdkit_warmup_pending = False
        state.pending_signature = None
        emit_selection_info_for(canvas)
        return
    if time.monotonic() - state.last_interaction_time < state.rdkit_idle_threshold:
        return
    preload_rdkit_for(canvas)
    state.rdkit_warmup_pending = False
    state.pending_signature = None
    emit_selection_info_for(canvas)


__all__ = ["emit_selection_info_for", "maybe_warm_rdkit_for"]
