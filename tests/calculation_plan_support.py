"""Synthetic document and calculation-plan builders shared by focused tests."""

from __future__ import annotations

from chemvas.domain.document import (
    Atom,
    Bond,
    MoleculeModel,
    serialize_model_state,
    serialize_settings,
)


def _document_state() -> dict[str, object]:
    model = MoleculeModel(
        atoms={
            0: Atom("C", 0.0, 0.0),
            1: Atom("O", 1.0, 0.0),
            2: Atom("C", 4.0, 0.0),
            3: Atom("O", 5.0, 0.0),
            4: Atom("Pt", 2.5, 3.0),
            5: Atom("Cl", 2.5, -3.0),
        },
        bonds=[Bond(0, 1, order=2), Bond(2, 3, order=1)],
    )
    return {
        "model": serialize_model_state(model),
        "ring_fills": [],
        "notes": [],
        "marks": [],
        "arrows": [],
        "ts_brackets": [],
        "shapes": [],
        "orbitals": [],
        "settings": serialize_settings(
            bond_length_px=18.0,
            arrow_line_width=1.5,
            arrow_head_scale=0.4,
            orbital_phase_enabled=True,
            text_font_size=13,
            text_font_weight=600,
            text_italic=False,
            sheet_size="A4",
            sheet_orientation="portrait",
        ),
        "last_smiles_input": None,
    }


def _plan(*, complete_mapping: bool = True) -> dict[str, object]:
    correspondence = [
        {"reactant_atom_id": 0, "product_atom_id": 2},
        {"reactant_atom_id": 1, "product_atom_id": 3},
        {"reactant_atom_id": 4, "product_atom_id": 4},
    ]
    if not complete_mapping:
        correspondence.pop()
    return {
        "format": "chemvas-calculation-plan",
        "version": 2,
        "states": [
            {
                "id": "R01",
                "charge": 0,
                "multiplicity": 1,
                "members": [
                    {"component_atom_ids": [0, 1], "inclusion": "included"},
                    {"component_atom_ids": [4], "inclusion": "included"},
                    {"component_atom_ids": [5], "inclusion": "context_only"},
                ],
            },
            {
                "id": "P01",
                "charge": 0,
                "multiplicity": 1,
                "members": [
                    {"component_atom_ids": [2, 3], "inclusion": "included"},
                    {"component_atom_ids": [4], "inclusion": "included"},
                    {"component_atom_ids": [5], "inclusion": "context_only"},
                ],
            },
        ],
        "steps": [
            {
                "id": "S01",
                "reactant": {
                    "state_id": "R01",
                    "roles": [
                        {"component_atom_ids": [0, 1], "role": "reactant"},
                        {"component_atom_ids": [4], "role": "catalyst"},
                        {"component_atom_ids": [5], "role": "spectator"},
                    ],
                    "precomplex": {"kind": "none"},
                },
                "product": {
                    "state_id": "P01",
                    "roles": [
                        {"component_atom_ids": [2, 3], "role": "product"},
                        {"component_atom_ids": [4], "role": "catalyst"},
                        {"component_atom_ids": [5], "role": "spectator"},
                    ],
                    "precomplex": {"kind": "none"},
                },
                "atom_correspondence": correspondence,
            }
        ],
    }
