"""Bond history must retain the live selection consumed by chemistry exports."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QCursor, QKeySequence, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id
from chemvas.ui.canvas_hover_state import hover_state_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.select_all_access import select_all_scene_items_for
from chemvas.ui.selection_collection_access import selected_ids_for
from chemvas.ui.structure_payload_access import build_selected_3d_conversion_payload_for
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    view.resize(850, 600)
    view.show()
    assert QTest.qWaitForWindowExposed(view)
    view.services.structure.structure_build_service.add_benzene_ring(QPointF(200, 150))
    view.centerOn(200, 150)
    view.setFocus()
    app.processEvents()
    QTest.qWait(20)
    yield view
    view.services.document.canvas_scene_reset_service.clear_scene()
    view.close()
    app.processEvents()


@pytest.mark.parametrize(
    "key", [Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_3, Qt.Key.Key_W]
)
def test_bond_hotkey_undo_redo_retains_ring_selection_and_export(
    canvas, tmp_path, monkeypatch, key
):
    assert select_all_scene_items_for(canvas)
    before_selection = selected_ids_for(canvas)
    assert before_selection == (set(range(6)), set(range(6)))
    before = snapshot_canvas_state_for(canvas)
    session = canvas.services.document.canvas_document_session_service
    path = tmp_path / "benzene.mol"
    session.export_mol(str(path))
    original_mol = path.read_bytes()
    # A single ring edge makes each key an effective edit (including "2",
    # whose explicit style differs from the template's ring-aware style).
    bond_id = next(i for i, bond in enumerate(canvas.model.bonds) if bond.order == 1)
    if key == Qt.Key.Key_1:
        bond_id = next(
            i for i, bond in enumerate(canvas.model.bonds) if bond.order == 2
        )
    bond = canvas.model.bonds[bond_id]
    a, b = canvas.model.atoms[bond.a], canvas.model.atoms[bond.b]
    position = canvas.mapFromScene(QPointF((a.x + b.x) / 2, (a.y + b.y) / 2))
    global_position = canvas.viewport().mapToGlobal(position)
    # Send a normal viewport event: Wayland may reject QTest's cursor warp.
    # Keyboard hover refresh must observe the same simulated pointer location.
    monkeypatch.setattr(QCursor, "pos", staticmethod(lambda: global_position))
    QApplication.sendEvent(
        canvas.viewport(),
        QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(position),
            QPointF(global_position),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    QApplication.processEvents()
    assert hover_state_for(canvas).bond_id == bond_id
    QTest.keyClick(canvas, key)
    after = snapshot_canvas_state_for(canvas)
    assert after != before
    assert selected_ids_for(canvas) == before_selection
    for _ in range(2):
        QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.Undo))
        assert snapshot_canvas_state_for(canvas) == before
        assert selected_ids_for(canvas) == before_selection
        for selected_only in (False, True):
            session.export_mol(str(path), selected_only=selected_only)
            assert path.read_bytes() == original_mol
        model, annotations = build_selected_3d_conversion_payload_for(canvas)
        assert len(model.atoms) == 6
        assert len(model.bonds) == 6
        assert sorted(bond.order for bond in model.bonds) == [1, 1, 1, 2, 2, 2]
        assert not annotations
        QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.Redo))
        assert snapshot_canvas_state_for(canvas) == after
        assert selected_ids_for(canvas) == before_selection


@pytest.mark.parametrize("selection", ["none", "edited", "other"])
def test_bond_history_preserves_current_partial_selection(canvas, selection):
    controller = canvas.services.scene_operations.scene_transform_controller
    controller.apply_bond_style(0, "triple", 3)
    canvas.scene().clearSelection()
    if selection != "none":
        for item in bond_items_for_id(canvas, 0 if selection == "edited" else 1):
            item.setSelected(True)
    expected = selected_ids_for(canvas)
    history = canvas.services.history_service
    history.undo()
    assert selected_ids_for(canvas) == expected
    history.redo()
    assert selected_ids_for(canvas) == expected


@pytest.mark.parametrize("operation", ["undo", "redo"])
def test_failed_bond_replay_restores_selection_and_document(
    canvas, monkeypatch, operation
):
    assert select_all_scene_items_for(canvas)
    canvas.services.scene_operations.scene_transform_controller.apply_bond_style(
        0, "triple", 3
    )
    history = canvas.services.history_service
    if operation == "redo":
        history.undo()
    state = snapshot_canvas_state_for(canvas)
    selection = selected_ids_for(canvas)
    stacks = history.capture_stack_snapshot()
    redraw = canvas.bond_renderer.redraw_bond

    def fail_after_redraw(bond_id):
        redraw(bond_id)
        raise RuntimeError("injected post-redraw failure")

    monkeypatch.setattr(canvas.bond_renderer, "redraw_bond", fail_after_redraw)
    with pytest.raises(RuntimeError, match="injected post-redraw"):
        getattr(history, operation)()
    assert snapshot_canvas_state_for(canvas) == state
    assert selected_ids_for(canvas) == selection
    history.verify_stack_snapshot(stacks)


def test_undo_keeps_benzene_in_exported_mol_and_selected_identifiers(canvas, tmp_path):
    pytest.importorskip("rdkit")
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors

    assert select_all_scene_items_for(canvas)
    canvas.services.scene_operations.scene_transform_controller.apply_bond_style(
        0, "triple", 3
    )
    canvas.services.history_service.undo()
    path = tmp_path / "benzene.mol"
    canvas.services.document.canvas_document_session_service.export_mol(str(path))
    molecule = Chem.MolFromMolBlock(path.read_text())
    assert molecule is not None
    assert rdMolDescriptors.CalcMolFormula(molecule) == "C6H6"
    assert Chem.MolToSmiles(molecule) == "c1ccccc1"
    assert Chem.AddHs(molecule).GetNumAtoms() == 12
