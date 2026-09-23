from __future__ import annotations

import pytest
from PyQt6.QtGui import QColor

from chemvas.domain.document import MoleculeModel
from chemvas.features.insertion import Molecule3DAtom, Molecule3DBond, Molecule3DScene
from chemvas.shell.palette import PALETTE
from chemvas.ui.preview_3d_state import (
    is_empty_preview_message,
    preview_empty_state_text,
    preview_info_items,
    preview_metadata_summary,
    preview_payload_signature,
    preview_status_badge,
)


def test_preview_payload_signature_captures_atoms_bonds_and_annotations() -> None:
    model = MoleculeModel()
    atom_a = model.add_atom("C", 0.1234, 1.9876)
    atom_b = model.add_atom("O", 12.0, 0.0)
    model.add_bond(atom_a, atom_b, 2)

    signature = preview_payload_signature(
        model,
        {atom_b: {"formal_charge": -1, "radical_electrons": 1}},
    )

    assert signature == (
        ((atom_a, "C", 0.0, 0.0), (atom_b, "O", 11.8766, -1.9876)),
        ((atom_a, atom_b, 2, "single"),),
        ((atom_b, -1, 1),),
    )


def test_preview_info_text_helpers_skip_empty_fields() -> None:
    assert preview_info_items("C2H6O", "46.07") == [
        ("FORMULA", "C2H6O"),
        ("MW", "46.07"),
    ]
    assert preview_info_items("C2H6O", "") == [("FORMULA", "C2H6O")]
    assert preview_info_items("", "46.07") == [("MW", "46.07")]
    assert preview_info_items("", "") == []


@pytest.mark.parametrize(
    "atom_count,edges,expected_rings",
    [
        (1, [], 0),
        (5, [(0, 1), (1, 2), (2, 0), (3, 4)], 1),
        (4, [(0, 1), (1, 2), (2, 0), (1, 3), (3, 2)], 2),
    ],
)
def test_inspector_counts_independent_rings_in_disconnected_and_fused_graphs(
    atom_count, edges, expected_rings
):
    scene = Molecule3DScene(
        atoms=tuple(Molecule3DAtom("C", i, 0, 0) for i in range(atom_count)),
        bonds=tuple(Molecule3DBond(a, b, 1) for a, b in edges),
    )
    assert preview_info_items("", "", scene) == [
        ("ATOMS (incl. H)", str(atom_count)),
        ("INDEP. RINGS", str(expected_rings)),
        ("STYLE", "ACS 1996"),
    ]


def test_preview_status_text_helpers_cover_empty_building_issue_and_ready_states() -> (
    None
):
    scene = Molecule3DScene(
        atoms=(
            Molecule3DAtom("C", 0.0, 0.0, 0.0),
            Molecule3DAtom("O", 1.0, 0.0, 0.0),
        ),
        bonds=(Molecule3DBond(0, 1, 1),),
    )

    assert is_empty_preview_message("3D preview unavailable")
    assert is_empty_preview_message("No chemical structure selected")
    assert preview_metadata_summary(None, "3D preview unavailable") == ""
    assert preview_status_badge(None, "3D preview unavailable")[0] == "Empty"
    assert preview_status_badge(None, "3D preview unavailable")[1:] == (
        QColor(PALETTE["hover"]),
        QColor(PALETTE["border_strong"]),
        QColor(PALETTE["text_muted"]),
    )
    assert preview_empty_state_text("3D preview unavailable") == (
        "No molecule yet",
        "Draw or paste a structure to preview it in 3D.",
    )

    assert (
        preview_metadata_summary(None, "Updating 3D preview...")
        == "Preparing coordinates"
    )
    assert preview_status_badge(None, "Updating 3D preview...")[0] == "Building"
    assert preview_status_badge(None, "Updating 3D preview...")[1:] == (
        QColor(PALETTE["surface_context"]),
        QColor(PALETTE["border_strong"]),
        QColor(PALETTE["text_muted"]),
    )
    assert preview_empty_state_text("Updating 3D preview...") == (
        "Building preview",
        "Preparing coordinates",
    )

    assert preview_metadata_summary(None, "RDKit missing") == "Preview needs attention"
    assert preview_status_badge(None, "RDKit missing")[0] == "Issue"
    assert preview_status_badge(None, "RDKit missing")[1:] == (
        QColor(PALETTE["danger_bg"]),
        QColor(PALETTE["danger_border"]),
        QColor(PALETTE["danger_text"]),
    )
    assert preview_empty_state_text("RDKit missing") == (
        "Preview unavailable",
        "RDKit missing",
    )

    assert preview_metadata_summary(scene, "") == "2 atoms / 1 bond"
    assert preview_status_badge(scene, "")[0] == "Ready"
    assert preview_status_badge(scene, "")[1:] == (
        QColor(PALETTE["checked_bg"]),
        QColor(PALETTE["checked_border"]),
        QColor(PALETTE["checked_text"]),
    )
