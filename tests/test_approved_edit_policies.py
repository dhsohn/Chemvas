"""Approved editing policies preserve chemistry and retire input-only metadata."""

import json

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.core.document_io import create_document, read_document
from chemvas.domain.document import build_document_payload
from chemvas.ui.canvas.canvas_document_metadata_state import (
    document_is_dirty_for,
    mark_document_clean_for,
)
from tests.canvas_factory import build_canvas_view


@pytest.fixture
def canvas(qt_application):
    view = build_canvas_view()
    view.services.structure_build_service.add_bond_between_points(
        QPointF(0, 0), QPointF(40, 0), style="double", order=2
    )
    view.services.history_service.clear()
    view.resize(800, 600)
    view.show()
    view.centerOn(20, 0)
    QApplication.processEvents()
    yield view
    sip.delete(view)


@pytest.mark.parametrize("version", [7, 8])
def test_legacy_smiles_input_does_not_create_dirty_state_or_noop_history(
    canvas, tmp_path, version
):
    session = canvas.services.canvas_document_session_service
    state = session.snapshot_state()
    state["last_smiles_input"] = "obsolete input"
    path = tmp_path / "legacy.chemvas"
    raw = json.dumps(build_document_payload(state, version)).encode()
    path.write_bytes(raw)
    document = read_document(path)
    assert document.state["last_smiles_input"] == "obsolete input"
    session.apply_state(document.state)
    before = session.snapshot_state()
    mark_document_clean_for(canvas, before)
    assert before["last_smiles_input"] is None
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(0, 0), QPointF(40, 0), style="double", order=2
    )
    assert session.snapshot_state() == before
    assert not document_is_dirty_for(canvas, before)
    history.verify_stack_snapshot(stacks)
    saved = create_document(document.state, 8)
    assert saved.state == {**document.state, "last_smiles_input": None}
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "style,order,expected",
    [
        ("single", 1, "bold_in"),
        ("bold_in", 1, "bold_out"),
        ("bold_out", 1, "bold_in"),
        ("double", 2, "bold_in"),
        ("double_center", 2, "bold_center"),
        ("double_outer", 2, "bold_out"),
        ("bold_center", 2, "bold_center"),
        ("triple", 3, "bold_in"),
        ("double_either", 2, "double_either"),
    ],
)
def test_bold_click_and_drag_share_order_position_and_undo(
    canvas, style, order, expected
):
    transform = canvas.services.scene_transform_controller
    transform.apply_bond_style(0, style, order)
    history = canvas.services.history_service
    history.clear()
    session = canvas.services.canvas_document_session_service
    settings = canvas.runtime_state.tool_settings_state
    settings.active_bond_style = "bold_in"
    settings.active_bond_order = 1
    canvas.services.tool_mode_controller.set_tool("bond")
    before = session.snapshot_state()
    for gesture in ("click", "drag"):
        viewport = canvas.viewport()
        if gesture == "click":
            QTest.mouseClick(
                viewport,
                Qt.MouseButton.LeftButton,
                pos=canvas.mapFromScene(QPointF(20, 0)),
            )
        else:
            QTest.mousePress(
                viewport,
                Qt.MouseButton.LeftButton,
                pos=canvas.mapFromScene(QPointF(0, 0)),
            )
            QTest.mouseMove(viewport, canvas.mapFromScene(QPointF(40, 0)))
            QTest.mouseRelease(
                viewport,
                Qt.MouseButton.LeftButton,
                pos=canvas.mapFromScene(QPointF(40, 0)),
            )
        QApplication.processEvents()
        bond = canvas.model.bond_for_id(0)
        assert (bond.style, bond.order) == (expected, order)
        after = session.snapshot_state()
        if before != after:
            assert len(history.state.history) == 1
            history.undo()
            assert session.snapshot_state() == before
            history.redo()
            assert session.snapshot_state() == after
            history.undo()
        else:
            assert not history.state.history
        history.clear()
