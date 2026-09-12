"""Actual pointer input, native file IO, agent patch, and continued editing."""

import hashlib
import json

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtTest import QTest

from chemvas.core.document_io import read_document
from chemvas.ui.atom_coords_access import atom_coords_3d_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from tests.test_document_patch_alias_repair import _cli, _operation, _patch, _state
from tests.test_native_geometry_backlog import app as app
from tests.test_native_geometry_backlog import canvas as canvas
from tests.test_perspective_components import _assert_live_depth, _chains, _select


@pytest.mark.parametrize("alias", ["OH", "NH2", "SH"])
def test_gui_save_agent_repair_reopen_and_user_edit(canvas, app, tmp_path, alias):
    documents = canvas.services.document.canvas_document_session_service
    state = _state(alias)
    state["model"]["atoms"][1]["element"] = "C"
    documents.apply_state(state)
    tools = canvas.services.input.tool_mode_controller
    tools.set_tool("text")
    tools.set_atom_symbol(alias)
    point = canvas.mapFromScene(QPointF(18, 0))
    QTest.mouseMove(canvas.viewport(), point)
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
    app.processEvents()
    assert canvas.model.atoms[1].element == alias

    source = tmp_path / "drawing.chemvas"
    documents.save_to_file(str(source))
    original = source.read_bytes()
    refused = _cli("inspect-document", source)
    assert refused.returncode == 2
    assert "exactly one single attachment" in refused.stderr
    patch = tmp_path / "repair.json"
    patch.write_text(
        json.dumps(_patch(hashlib.sha256(original).hexdigest(), _operation(alias)))
    )
    output = tmp_path / "repaired.chemvas"
    dry = _cli("apply-patch", source, patch, "--dry-run")
    assert dry.returncode == 0, dry.stderr
    repaired = _cli("apply-patch", source, patch, "--output", output)
    assert repaired.returncode == 0, repaired.stderr
    assert (
        json.loads(dry.stdout)["candidate_sha256"]
        == hashlib.sha256(output.read_bytes()).hexdigest()
    )
    assert source.read_bytes() == original
    documents.apply_state(read_document(output).state)
    expected = {"OH": "O", "NH2": "N", "SH": "S"}[alias]
    assert canvas.model.atoms[1].element == expected
    before = snapshot_canvas_state_for(canvas)

    # The repaired document is still a drawing the user can correct normally.
    tools.set_tool("arrow")
    start = canvas.mapFromScene(QPointF(80, 60))
    end = start + QPoint(70, 0)
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    after = snapshot_canvas_state_for(canvas)
    assert len(after["arrows"]) == len(before["arrows"]) + 1
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    canvas.services.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == after
    documents.save_to_file(str(tmp_path / "user-corrected.chemvas"))
    assert source.read_bytes() == original


def test_pointer_rotations_keep_both_components_in_saved_document(
    canvas, app, tmp_path
):
    first, second = _chains(canvas)
    canvas.services.input.tool_mode_controller.set_tool("perspective")

    def rotate(chain, pixels):
        _select(canvas, chain[0])
        atom = canvas.model.atoms[chain[0][2]]
        start = canvas.mapFromScene(QPointF(atom.x, atom.y))
        end = start + QPoint(pixels, 0)
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
        assert canvas.services.tool_controller.active.has_active_gesture
        QTest.mouseMove(canvas.viewport(), end)
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
        app.processEvents()

    rotate(first, 60)
    before = snapshot_canvas_state_for(canvas)
    assert any(abs(atom_coords_3d_for(canvas)[aid][2]) > 1 for aid in first[0])
    rotate(second, 40)
    after = snapshot_canvas_state_for(canvas)
    expected_ids = set(first[0] + second[0])
    assert set(after["perspective"]["atom_coords_3d"]) == expected_ids
    _assert_live_depth(canvas, expected_ids)
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    canvas.services.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == after
    output = tmp_path / "rotated-pair.chemvas"
    documents = canvas.services.document.canvas_document_session_service
    documents.save_to_file(str(output))
    documents.apply_state(read_document(output).state)
    assert snapshot_canvas_state_for(canvas) == after
    _assert_live_depth(canvas, expected_ids)
