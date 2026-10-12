"""Closing a third fused ring must reuse its coincident existing vertex."""

from copy import deepcopy
from itertools import combinations

import pytest
from PyQt6.QtCore import QPointF

from chemvas.core.document_io import read_document, write_document
from chemvas.features.rendering import overvalent_atom_ids
from chemvas.ui.molecule.structure_build_committer import StructureBuildCommitter
from tests.gui_workflow_support import _click, _tool
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing


def _two_rings(window, canvas):
    _tool(window, "benzene")
    _click(canvas, QPointF(0, 0))
    _click(canvas, QPointF(17.320508075688775, 0))
    assert len(canvas.model.atoms) == 10
    assert len([b for b in canvas.model.bonds if b is not None]) == 11
    assert overvalent_atom_ids(canvas.model) == set()


def _assert_unique_graph(canvas):
    points = [(atom.x, atom.y) for atom in canvas.model.atoms.values()]
    assert all(
        abs(a[0] - b[0]) > 1e-6 or abs(a[1] - b[1]) > 1e-6
        for a, b in combinations(points, 2)
    )
    pairs = [
        tuple(sorted((bond.a, bond.b)))
        for bond in canvas.model.bonds
        if bond is not None
    ]
    assert len(pairs) == len(set(pairs))


@pytest.mark.parametrize("side", [1, -1])
def test_third_benzene_delete_history_repeated_placement_and_reopen(
    drawing, tmp_path, side
):
    window, canvas = drawing
    _two_rings(window, canvas)
    original_atoms = deepcopy(canvas.model.atoms)
    original_bonds = deepcopy(canvas.model.bonds)
    document = canvas.services.canvas_document_session_service
    history = canvas.services.history_service
    # Both lower and upper closure touch a third vertex outside the clicked edge.
    anchor = QPointF(8.660254037844387, side * 15)
    for cycle in range(3):
        _tool(window, "benzene")
        _click(canvas, anchor)
        assert len(canvas.model.atoms) == 13
        assert len([b for b in canvas.model.bonds if b is not None]) == 15
        _assert_unique_graph(canvas)
        assert {
            key: canvas.model.atoms[key] for key in original_atoms
        } == original_atoms
        assert canvas.model.bonds[:11] == original_bonds
        third_state = document.snapshot_state()
        third_path = tmp_path / f"three-{side}-{cycle}.chemvas"
        write_document(third_path, third_state, canvas.FILE_FORMAT_VERSION)
        third_bytes = third_path.read_bytes()
        added = set(canvas.model.atoms) - original_atoms.keys()
        assert len(added) == 3
        _tool(window, "select")
        for item in canvas.scene().items():
            if item.data(0) == "atom" and item.data(1) in added:
                item.setSelected(True)
        assert canvas.services.scene_delete_controller.delete_selected_items()
        _assert_unique_graph(canvas)
        assert canvas.model.atoms == original_atoms
        assert [b for b in canvas.model.bonds if b is not None] == original_bonds
        assert overvalent_atom_ids(canvas.model) == set()
        assert canvas.runtime_state.valence_warnings.warnings_for(canvas.model) == set()
        repaired_state = document.snapshot_state()
        history.undo()
        assert document.snapshot_state() == third_state
        history.redo()
        assert document.snapshot_state() == repaired_state
        repaired_path = tmp_path / f"two-{side}-{cycle}.chemvas"
        write_document(repaired_path, repaired_state, canvas.FILE_FORMAT_VERSION)
        for path, expected in (
            (third_path, third_state),
            (repaired_path, repaired_state),
        ):
            document.restore_state(read_document(path).state)
            assert document.snapshot_state() == expected
            _assert_unique_graph(canvas)
        assert canvas.runtime_state.valence_warnings.warnings_for(canvas.model) == set()
        assert third_path.read_bytes() == third_bytes


def test_closure_preserves_existing_atom_identity_annotations_and_bonds(drawing):
    window, canvas = drawing
    _two_rings(window, canvas)
    atom = canvas.model.atoms[6]
    atom.element = "N"
    atom.color = "#123456"
    atom.explicit_label = True
    canvas.model.atom_annotations[6] = {"formal_charge": 1, "radical_electrons": 1}
    canvas.services.structure_build_service.render_model()
    original = deepcopy(atom)
    bonds = deepcopy(canvas.model.bonds)
    _click(canvas, QPointF(8.660254037844387, 15))
    assert len(canvas.model.atoms) == 13
    assert canvas.model.atoms[6] == original
    assert canvas.model.atom_annotations[6] == {
        "formal_charge": 1,
        "radical_electrons": 1,
    }
    assert canvas.model.bonds[:11] == bonds
    _assert_unique_graph(canvas)


def test_closure_does_not_absorb_an_unrelated_coincident_atom(drawing):
    window, canvas = drawing
    _two_rings(window, canvas)
    separate = canvas.services.canvas_atom_mutation_service.add_atom("O", 0, 40)
    canvas.services.structure_build_service.render_model()
    original = deepcopy(canvas.model.atoms[separate])
    _click(canvas, QPointF(8.660254037844387, 15))
    assert len(canvas.model.atoms) == 14
    assert canvas.model.atoms[separate] == original
    assert all(
        separate not in (bond.a, bond.b)
        for bond in canvas.model.bonds
        if bond is not None
    )


def test_closure_does_not_snap_a_nearby_existing_vertex(drawing):
    window, canvas = drawing
    _two_rings(window, canvas)
    canvas.model.atoms[6].x += 0.01
    canvas.services.structure_build_service.render_model()
    original = deepcopy(canvas.model.atoms[6])
    _click(canvas, QPointF(8.660254037844387, 15))
    assert len(canvas.model.atoms) == 14
    assert canvas.model.atoms[6] == original


def test_ambiguous_existing_overlap_is_not_silently_repaired(drawing):
    window, canvas = drawing
    _two_rings(window, canvas)
    atom = canvas.model.atoms[6]
    duplicate = canvas.model.add_atom("C", atom.x, atom.y)
    canvas.model.add_bond(1, duplicate)
    canvas.services.structure_build_service.render_model()
    document = canvas.services.canvas_document_session_service
    before = document.snapshot_state()
    history = canvas.services.history_service.capture_stack_snapshot()
    _click(canvas, QPointF(8.660254037844387, 15))
    assert document.snapshot_state() == before
    canvas.services.history_service.verify_stack_snapshot(history)


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("duplicate_index", [2, 3])
def test_closure_rechecks_ambiguity_after_both_paths_connect(
    drawing, side, duplicate_index
):
    _, canvas = drawing
    builder = canvas.services.structure_build_service
    canvas.model.add_atom("C", 0, 0)
    canvas.model.add_atom("C", 20, 0)
    canvas.model.add_bond(0, 1)
    center = QPointF(10, side * 20)
    points, _ = builder.regular_ring_points_for_bond(6, 0, center)
    for point in points[2:]:
        canvas.model.add_atom("C", point.x(), point.y())
    point = points[duplicate_index]
    duplicate = canvas.model.add_atom("N", point.x(), point.y())
    edges = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 0)]
    split_edge = (duplicate_index, duplicate_index + 1)
    for a, b in edges:
        if (a, b) == split_edge:
            a = duplicate if a == duplicate_index else a
            b = duplicate if b == duplicate_index else b
        canvas.model.add_bond(a, b)
    builder.render_model()
    document = canvas.services.canvas_document_session_service
    before = document.snapshot_state()
    history = canvas.services.history_service.capture_stack_snapshot()

    assert builder.add_benzene_ring(center, attach_bond_id=0) is None
    assert document.snapshot_state() == before
    canvas.services.history_service.verify_stack_snapshot(history)


def test_closure_recording_failure_restores_original_graph_and_history(
    drawing, monkeypatch
):
    window, canvas = drawing
    _two_rings(window, canvas)
    document = canvas.services.canvas_document_session_service
    before = document.snapshot_state()
    history = canvas.services.history_service.capture_stack_snapshot()

    def fail(*args, **kwargs):
        raise RuntimeError("injected closure recording failure")

    monkeypatch.setattr(StructureBuildCommitter, "record_additions", fail)
    with pytest.raises(RuntimeError, match="injected closure recording failure"):
        canvas.services.structure_build_service.add_benzene_ring(
            QPointF(8.660254037844387, 15), attach_bond_id=1
        )
    assert document.snapshot_state() == before
    canvas.services.history_service.verify_stack_snapshot(history)
    assert overvalent_atom_ids(canvas.model) == set()
