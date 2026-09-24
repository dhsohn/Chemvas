from copy import deepcopy
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent

from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.domain.chemistry_types import (
    Molecule3DAtom,
    Molecule3DScene,
)
from chemvas.domain.document import MoleculeModel
from chemvas.ui.preview3d.preview_3d import Preview3D
from chemvas.ui.preview3d.preview_3d_state import preview_payload_signature
from tests.test_gui_preview_3d_recovery import AnnotatedIdentifierAdapter


def _translated(model, dx, dy):
    moved = deepcopy(model)
    for atom in moved.atoms.values():
        atom.x += dx
        atom.y += dy
    return moved


@pytest.mark.parametrize("offset", [(100, 100), (-123.456, 987.654), (0.001, -0.002)])
def test_translation_reuses_scene_identifiers_and_pending_request(
    qt_application, offset
):
    model = MoleculeModel()
    model.add_atom("C", 1.123456, -2.654321)
    model.add_atom("O", 21.5, 30.25)
    model.add_bond(0, 1)
    scene = Molecule3DScene((Molecule3DAtom("C", 0, 0, 0),), ())
    adapter = AnnotatedIdentifierAdapter([(scene, None)])
    preview = Preview3D(rdkit_adapter=adapter)
    try:
        preview._set_canvas_structure(model, None)
        preview._update_timer.stop()
        request = preview._preview_request_id
        # Translation while debounced must not invalidate the pending job.
        preview._set_canvas_structure(_translated(model, *offset), None)
        assert preview._preview_request_id == request
        preview._update_timer.stop()
        preview._rebuild_scene()
        assert preview._scene is scene
        with patch.object(preview._update_timer, "start") as start:
            preview._set_canvas_structure(
                _translated(model, -offset[0], -offset[1]), None
            )
        start.assert_not_called()
        assert preview._scene is scene
        assert len(adapter.calls) == 1
        assert len(adapter.identifier_annotations) == 1
        assert preview._formula_text == "charge=0;radical=0"
    finally:
        preview.close()
        preview.deleteLater()
        QCoreApplication.sendPostedEvents(preview, QEvent.Type.DeferredDelete)


def test_preview_key_keeps_geometry_and_effective_electronic_annotations():
    model = MoleculeModel()
    model.add_atom("C", 0, 0)
    model.add_atom("O", 20, 0)
    model.add_bond(0, 1)
    original = preview_payload_signature(model, None)
    model.atoms[1].y = 0.0001
    assert preview_payload_signature(model, None) != original
    model.atoms[1].y = 0
    model.atom_annotations[1] = {"formal_charge": -1}
    assert preview_payload_signature(model, None) != original
    # Explicit payload annotations replace the model annotations in conversion.
    assert preview_payload_signature(model, {}) == original


@pytest.mark.parametrize("smiles", ["N[C@@H](C)C(=O)O", "F[C@](Cl)(Br)I"])
def test_translated_stereo_matches_independent_smiles_oracle(smiles):
    pytest.importorskip("rdkit")
    from rdkit import Chem

    expected = Chem.MolToSmiles(Chem.MolFromSmiles(smiles), isomericSmiles=True)
    adapter = RDKitAdapter()
    model = adapter.smiles_to_2d(smiles)
    assert model is not None, adapter.last_error
    signature = preview_payload_signature(model, None)
    for dx, dy in [(0, 0), (100, 200), (-357.75, -202.5)]:
        translated = _translated(model, dx, dy)
        assert adapter.compute_identifiers(translated).smiles == expected
        assert preview_payload_signature(translated, None) == signature
    reflected = deepcopy(model)
    for atom in reflected.atoms.values():
        atom.x = -atom.x
    opposite = adapter.compute_identifiers(reflected).smiles
    assert opposite and opposite != expected
    assert preview_payload_signature(reflected, None) != signature
    wedge = next(
        b for b in model.bonds if b is not None and b.style in {"wedge", "hash"}
    )
    wedge.style = "hash" if wedge.style == "wedge" else "wedge"
    assert adapter.compute_identifiers(model).smiles == opposite
    assert preview_payload_signature(model, None) != signature


def test_preview_key_preserves_drawn_double_bond_stereo():
    pytest.importorskip("rdkit")
    from rdkit import Chem

    model = MoleculeModel()
    for x, y in [(0, 30), (30, 0), (60, 0), (90, -30)]:
        model.add_atom("C", x, y)
    for a, b, order in [(0, 1, 1), (1, 2, 2), (2, 3, 1)]:
        model.add_bond(a, b, order)
    adapter = RDKitAdapter()
    signature = preview_payload_signature(model, None)
    expected = Chem.MolToSmiles(Chem.MolFromSmiles("C/C=C/C"))
    assert adapter.compute_identifiers(model).smiles == expected
    moved = _translated(model, 77.25, -90.125)
    assert adapter.compute_identifiers(moved).smiles == expected
    assert preview_payload_signature(moved, None) == signature
    model.atoms[3].y = 30
    opposite = Chem.MolToSmiles(Chem.MolFromSmiles("C/C=C\\C"))
    assert adapter.compute_identifiers(model).smiles == opposite
    assert preview_payload_signature(model, None) != signature
