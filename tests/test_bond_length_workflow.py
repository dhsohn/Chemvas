"""The actual length field keeps a marked drawing ready to export and reopen."""

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QImage, QKeySequence
from PyQt6.QtTest import QTest

from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.main_window_context_bar_widgets import BondLengthSpinBox
from chemvas.ui.main_window_ports import services_for_window, tool_action_for_window
from chemvas.ui.scene_decoration_access import add_arrow_for, add_mark_for_atom_for
from chemvas.ui.scene_item_access import create_scene_item_from_state
from tests.test_note_editing_workflows import app as app
from tests.test_note_editing_workflows import drawing as drawing


@pytest.mark.parametrize("kind", ["plus", "radical", "circled_minus"])
def test_length_field_export_and_reopen_keep_marked_scheme_geometry(
    drawing, tmp_path, kind
):
    window, canvas = drawing
    builder = canvas.services.structure.structure_build_service
    builder.add_benzene_ring(QPointF(100, 100))
    builder.add_benzene_ring(QPointF(300, 100))
    atom = canvas.model.atoms[0]
    add_mark_for_atom_for(canvas, 0, QPointF(atom.x + 7, atom.y - 9), kind=kind)
    add_arrow_for(canvas, QPointF(170, 100), QPointF(230, 100), "reaction")
    create_scene_item_from_state(
        canvas, {"kind": "note", "text": "Synthetic scheme", "x": 140, "y": 150}
    )
    before = snapshot_canvas_state_for(canvas)
    tool_action_for_window(window, "bond").trigger()
    spin = window.findChild(BondLengthSpinBox, "bondLengthInput")
    assert spin is not None and spin.isVisible()
    spin.setFocus()
    spin.selectAll()
    QTest.keyClicks(spin, "60")
    QTest.keyClick(spin, Qt.Key.Key_Return)
    after = snapshot_canvas_state_for(canvas)
    assert after["settings"]["bond_length_px"] == 60
    assert after["marks"][0]["dx"] == before["marks"][0]["dx"] * 3
    assert after["marks"][0]["dy"] == before["marks"][0]["dy"] * 3
    assert after["arrows"] == before["arrows"]
    assert after["notes"] == before["notes"]
    canvas.setFocus()
    QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.Undo))
    assert snapshot_canvas_state_for(canvas) == before
    QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.Redo))
    assert snapshot_canvas_state_for(canvas) == after
    session = canvas.services.document.canvas_document_session_service
    first, second = tmp_path / "live.png", tmp_path / "reopened.png"
    session.export_figure(str(first), fmt="png")
    actions = services_for_window(window).document_action_service
    document = tmp_path / "marked.chemvas"
    assert actions.save_canvas_to_path(window, str(document))
    assert actions.load_canvas_from_path(window, str(document))
    assert snapshot_canvas_state_for(canvas) == after
    session.export_figure(str(second), fmt="png")
    live, reopened = QImage(str(first)), QImage(str(second))
    assert not live.isNull()
    assert live == reopened
