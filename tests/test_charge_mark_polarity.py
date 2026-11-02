"""Charge-mark polarity is owned by domain.document.marks."""

from __future__ import annotations

from itertools import combinations_with_replacement

import pytest

from chemvas.domain.document import (
    VALID_MARK_KINDS,
    MoleculeModel,
    serialize_model_state,
)
from chemvas.domain.document.inspection import document_annotations
from chemvas.domain.document.marks import annotation_totals
from chemvas.features.insertion.structure_payload import build_atom_annotations


def _mark_multisets() -> list[tuple[str, ...]]:
    kinds = tuple(sorted(VALID_MARK_KINDS))
    return [
        combo
        for size in range(4)
        for combo in combinations_with_replacement(kinds, size)
    ]


def _mark(kind: str, atom_id: int) -> dict[str, object]:
    return {
        "kind": kind,
        "text": None,
        "atom_id": atom_id,
        "dx": None,
        "dy": None,
        "x": 0.0,
        "y": 0.0,
    }


@pytest.mark.parametrize(
    "kinds",
    _mark_multisets(),
    ids=lambda kinds: "+".join(kinds) if kinds else "empty",
)
def test_inspection_and_build_atom_annotations_agree(
    kinds: tuple[str, ...],
) -> None:
    model = MoleculeModel()
    atom_id = model.add_atom("C", 0.0, 0.0)
    state = {
        "model": serialize_model_state(model),
        "marks": [_mark(kind, atom_id) for kind in kinds],
    }

    expected = annotation_totals(kinds)
    inspected = document_annotations(state, model).get(atom_id, {})
    built = build_atom_annotations(
        {atom_id},
        {atom_id: atom_id},
        {atom_id: kinds},
    ).get(atom_id, {})

    assert (
        inspected.get("formal_charge", 0),
        inspected.get("radical_electrons", 0),
    ) == expected
    assert (
        built.get("formal_charge", 0),
        built.get("radical_electrons", 0),
    ) == expected
