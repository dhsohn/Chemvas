"""The actual length field keeps a marked drawing ready to export and reopen."""

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QImage, QKeySequence
from PyQt6.QtTest import QTest

from chemvas.ui.scene.scene_decoration_access import add_mark_for_atom_for
from chemvas.ui.window.main_window_context_bar_widgets import BondLengthSpinBox
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing


@pytest.mark.parametrize("with_arrow", [False, True])
def test_length_change_without_atoms_is_published_and_undoable(drawing, with_arrow):
    window, canvas = drawing
    if with_arrow:
        canvas.services.scene_decoration_service.add_arrow(
            QPointF(0, 0), QPointF(80, 0), "reaction"
        )
    documents = window.services.canvas_document_service
    documents.mark_clean(canvas)
    history = canvas.services.history_service
    count = len(history.state.history)
    old_length = canvas.renderer.style.bond_length_px

    canvas.services.geometry_controller.set_bond_length(old_length * 2)

    assert len(history.state.history) == count + 1
    assert documents.is_dirty(canvas)
    history.undo()
    assert canvas.renderer.style.bond_length_px == old_length
    assert not documents.is_dirty(canvas)
    history.redo()
    assert canvas.renderer.style.bond_length_px == old_length * 2


def test_empty_length_change_rolls_back_when_history_rejects_it(drawing, monkeypatch):
    window, canvas = drawing
    documents = window.services.canvas_document_service
    documents.mark_clean(canvas)
    history = canvas.services.history_service
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    stacks = history.capture_stack_snapshot()
    monkeypatch.setattr(history, "push", lambda command: False)

    with pytest.raises(RuntimeError, match="did not commit"):
        canvas.services.geometry_controller.set_bond_length(60)

    assert session.snapshot_state() == before
    history.verify_stack_snapshot(stacks)
    assert not documents.is_dirty(canvas)


def test_empty_length_change_publishes_when_history_is_disabled(drawing):
    window, canvas = drawing
    documents = window.services.canvas_document_service
    documents.mark_clean(canvas)
    history = canvas.services.history_service
    history.state.enabled = False

    canvas.services.geometry_controller.set_bond_length(60)

    assert not history.state.history
    assert documents.is_dirty(canvas)
    assert window.isWindowModified()


@pytest.mark.parametrize("kind", ["plus", "radical", "circled_minus"])
def test_length_field_export_and_reopen_keep_marked_scheme_geometry(
    drawing, tmp_path, kind
):
    window, canvas = drawing
    builder = canvas.services.structure_build_service
    builder.add_benzene_ring(QPointF(100, 100))
    builder.add_benzene_ring(QPointF(300, 100))
    atom = canvas.model.atoms[0]
    add_mark_for_atom_for(canvas, 0, QPointF(atom.x + 7, atom.y - 9), kind=kind)
    canvas.services.scene_decoration_service.add_arrow(
        QPointF(170, 100), QPointF(230, 100), "reaction"
    )
    canvas.services.scene_item_controller.create_scene_item_from_state(
        {"kind": "note", "text": "Synthetic scheme", "x": 140, "y": 150}
    )
    before = canvas.services.canvas_document_session_service.snapshot_state()
    window.ui_references.tool_action_for_key("bond").trigger()
    spin = window.findChild(BondLengthSpinBox, "bondLengthInput")
    assert spin is not None and spin.isVisible()
    spin.setFocus()
    spin.selectAll()
    QTest.keyClicks(spin, "60")
    QTest.keyClick(spin, Qt.Key.Key_Return)
    after = canvas.services.canvas_document_session_service.snapshot_state()
    assert after["settings"]["bond_length_px"] == 60
    assert after["marks"][0]["dx"] == before["marks"][0]["dx"] * 3
    assert after["marks"][0]["dy"] == before["marks"][0]["dy"] * 3
    assert after["arrows"] == before["arrows"]
    assert after["notes"] == before["notes"]
    canvas.setFocus()
    QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.Undo))
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.Redo))
    assert canvas.services.canvas_document_session_service.snapshot_state() == after
    session = canvas.services.canvas_document_session_service
    first, second = tmp_path / "live.png", tmp_path / "reopened.png"
    session.export_figure(str(first), fmt="png")
    actions = window.services.document_action_service
    document = tmp_path / "marked.chemvas"
    assert actions.save_canvas_to_path(window, str(document))
    assert actions.load_canvas_from_path(window, str(document))
    assert canvas.services.canvas_document_session_service.snapshot_state() == after
    session.export_figure(str(second), fmt="png")
    live, reopened = QImage(str(first)), QImage(str(second))
    assert not live.isNull()
    assert live == reopened
