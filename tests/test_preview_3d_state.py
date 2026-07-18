from __future__ import annotations

from chemvas.domain.document import MoleculeModel
from chemvas.features.insertion import Molecule3DAtom, Molecule3DBond, Molecule3DScene
from chemvas.ui.main_window_palette import PALETTE
from chemvas.ui.preview_3d_state import (
    is_empty_preview_message,
    preview_empty_state_text,
    preview_info_items,
    preview_info_lines,
    preview_metadata_summary,
    preview_payload_signature,
    preview_status_badge,
)
from PyQt6.QtGui import QColor


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
        ((atom_a, "C", 0.123, 1.988), (atom_b, "O", 12.0, 0.0)),
        ((atom_a, atom_b, 2, "single"),),
        ((atom_b, -1, 1),),
    )


def test_preview_info_text_helpers_skip_empty_fields() -> None:
    assert preview_info_lines("C2H6O", "46.07") == ["Formula: C2H6O", "MW: 46.07"]
    assert preview_info_lines("", "46.07") == ["MW: 46.07"]
    assert preview_info_items("C2H6O", "46.07") == [
        ("FORMULA", "C2H6O"),
        ("MW", "46.07"),
    ]
    assert preview_info_items("C2H6O", "") == [("FORMULA", "C2H6O")]


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
