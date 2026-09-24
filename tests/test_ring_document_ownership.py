"""Ring data survives projection loss and molecular editing transactions."""

from __future__ import annotations

import gc
import json
from unittest import mock

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QEvent, QPointF
from PyQt6.QtGui import QColor, QPolygonF

from chemvas.core.document_io import read_document
from chemvas.domain.document import CLIPBOARD_SELECTION_VERSION
from chemvas.ui.annotations.state import (
    atom_state_dict_for,
    bond_state_dict,
    ring_state_dict,
    scene_item_state_for,
)
from chemvas.ui.canvas.canvas_lifecycle import schedule_canvas_deletion_for
from chemvas.ui.molecule.structure_mutation_access import add_benzene_ring_for
from chemvas.ui.scene.scene_clipboard_access import (
    build_selection_clipboard_payload_for_canvas,
)
from tests.canvas_factory import build_canvas_view
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing
from tests.gui_workflow_support import qt_errors as qt_errors
from tests.gui_workflow_support import release, start_drag
from tests.test_ring_fill_precision import _load


@pytest.fixture
def canvas(qt_application):
    view = build_canvas_view()
    _load(view, 0.3000000001)
    yield view
    schedule_canvas_deletion_for(view)
    qt_application.sendPostedEvents(view, QEvent.Type.DeferredDelete)


def _lose(canvas, loss):
    ring = canvas.runtime_state.ring_items()[0]
    record_id = ring.record_id
    if loss == "destroy":
        sip.delete(ring)
    else:
        canvas.scene().removeItem(ring)
    if loss == "release":
        canvas.runtime_state.scene_items_state.ring_items.pop(record_id)
        canvas.services.history_service.clear()
        del ring
        gc.collect()
    return record_id


@pytest.mark.parametrize("loss", ["detach", "destroy", "release"])
def test_save_and_copy_keep_ring_without_projection(canvas, tmp_path, loss):
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    record_id = _lose(canvas, loss)
    assert session.snapshot_state() == before
    path = tmp_path / "ring.chemvas"
    assert session.save_to_file(str(path)) == []
    assert read_document(path).state["ring_fills"] == json.loads(
        json.dumps(before["ring_fills"])
    )
    payload = build_selection_clipboard_payload_for_canvas(
        canvas,
        selected_items=[],
        explicit_atom_ids=set(canvas.model.atoms),
        selected_bond_ids=set(),
        bonds=canvas.model.bonds,
        atom_state_getter=lambda atom_id: atom_state_dict_for(canvas, atom_id),
        bond_state_getter=bond_state_dict,
        scene_item_state_getter=lambda item: scene_item_state_for(canvas, item),
        version=CLIPBOARD_SELECTION_VERSION,
    )
    assert payload["rings"] == [{"kind": "ring", **before["ring_fills"][0]}]
    assert canvas.runtime_state.ring_state.order == [record_id]
    session.apply_state(read_document(path).state)
    assert session.snapshot_state() == before
    assert canvas.runtime_state.ring_items()[0].brush().color().name() == "#ffcc00"


def test_ring_record_ignores_all_qt_geometry_and_appearance(canvas):
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    ring = canvas.runtime_state.ring_items()[0]
    state = ring_state_dict(ring)
    ring.setBrush(QColor("magenta"))
    ring.setData(2, [99, 100, 101])
    ring.setData(9, {"kind": "ring", "atom_ids": [999], "alpha": 0.9})
    ring.setPolygon(QPolygonF([QPointF(999, 999)]))
    ring.setPos(1000, 1000)
    ring.setScale(3)
    assert session.snapshot_state() == before
    assert ring_state_dict(ring) == state
    assert ring.data(2) == list(canvas.model.atoms)


@pytest.mark.parametrize("loss", ["detach", "destroy", "release"])
@pytest.mark.parametrize("entity", ["atom", "bond"])
def test_missing_ring_is_deleted_with_cycle_and_recovers_on_undo(canvas, loss, entity):
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    record_id = _lose(canvas, loss)
    deletion = canvas.services.scene_delete_controller
    getattr(deletion, f"delete_{entity}")(0)
    after = session.snapshot_state()
    assert after["ring_fills"] == []
    assert canvas.runtime_state.ring_state.order == []
    history = canvas.services.history_service
    for _ in range(2):
        history.undo()
        assert session.snapshot_state() == before
        ring = canvas.runtime_state.ring_items()[0]
        assert ring.record_id == record_id
        assert [(p.x(), p.y()) for p in ring.polygon()] == before["ring_fills"][0][
            "points"
        ]
        history.redo()
        assert session.snapshot_state() == after
        assert canvas.runtime_state.ring_state.order == []


@pytest.mark.parametrize("loss", ["destroy", "release"])
def test_fill_recovers_existing_record_instead_of_duplicating_ring(canvas, loss):
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    record_id = _lose(canvas, loss)
    selected = [item for item in canvas.scene().items() if item.data(0) == "bond"]
    canvas.services.canvas_color_mutation_service.apply_ring_fill_color_to_items(
        selected, QColor("#123456")
    )
    assert canvas.runtime_state.ring_state.order == [record_id]
    assert len(session.snapshot_state()["ring_fills"]) == 1
    canvas.services.history_service.undo()
    assert session.snapshot_state() == before


@pytest.mark.parametrize("publication", ["raise", "false"])
def test_failed_cycle_delete_preserves_records_and_redo(canvas, publication):
    session = canvas.services.canvas_document_session_service
    history = canvas.services.history_service
    canvas.services.scene_decoration_service.add_arrow(
        QPointF(100, 100), QPointF(160, 100), "arrow"
    )
    history.undo()
    before = session.snapshot_state()
    ring = canvas.runtime_state.ring_items()[0]
    records = dict(canvas.runtime_state.ring_state.records)
    stacks = history.capture_stack_snapshot()
    behavior = (
        {"side_effect": RuntimeError("publish failed")}
        if publication == "raise"
        else {"return_value": False}
    )
    with mock.patch.object(history, "push", **behavior), pytest.raises(RuntimeError):
        canvas.services.scene_delete_controller.delete_atom(0)
    assert session.snapshot_state() == before
    assert canvas.runtime_state.ring_state.records == records
    assert canvas.runtime_state.ring_items() == [ring]
    assert ring.scene() is canvas.scene()
    history.verify_stack_snapshot(stacks)


def test_ring_geometry_uses_current_model_and_exact_opacity(canvas):
    ring = canvas.runtime_state.ring_items()[0]
    canvas.model.atoms[0].x += 12.125
    canvas.services.scene_item_controller.apply_scene_item_state(
        ring, {"kind": "ring", "color": "#ABCDEF", "alpha": 0.3000000002}
    )
    state = ring_state_dict(ring)
    assert state["points"][0] == (canvas.model.atoms[0].x, canvas.model.atoms[0].y)
    assert state["alpha"] == 0.3000000002
    assert state["color"] == "#abcdef"
    polygon = ring.polygon()
    assert polygon[0] == QPointF(*state["points"][0])


def test_reset_clears_ring_without_projection(canvas):
    _lose(canvas, "release")
    canvas.services.canvas_scene_reset_service.clear_scene()
    assert canvas.runtime_state.ring_state.order == []
    assert (
        canvas.services.canvas_document_session_service.snapshot_state()["ring_fills"]
        == []
    )


def test_delete_middle_ring_restores_original_order_and_exact_appearance(canvas):
    add_benzene_ring_for(canvas, QPointF(120, 0))
    add_benzene_ring_for(canvas, QPointF(240, 0))
    rings = canvas.runtime_state.ring_items()
    for index, ring in enumerate(rings):
        canvas.services.scene_item_controller.apply_scene_item_state(
            ring, {"kind": "ring", "color": "#112233", "alpha": 0.1 + index / 10}
        )
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    order = list(canvas.runtime_state.ring_state.order)
    canvas.services.scene_delete_controller.delete_ring(rings[1])
    after = session.snapshot_state()
    assert after["ring_fills"] == [before["ring_fills"][0], before["ring_fills"][2]]
    for _ in range(3):
        canvas.services.history_service.undo()
        assert session.snapshot_state() == before
        assert canvas.runtime_state.ring_state.order == order
        canvas.services.history_service.redo()
        assert session.snapshot_state() == after


@pytest.mark.parametrize("finish", ["commit", "cancel"])
def test_native_ring_drag_delete_history_and_reopen(
    drawing, qt_errors, tmp_path, finish
):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    _window, canvas = drawing
    _load(canvas, 0.3000000001)
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    end = start_drag(canvas, "select", QPointF(0, 0))
    if finish == "cancel":
        QTest.keyClick(canvas, Qt.Key.Key_Escape)
        release(canvas, end)
        assert session.snapshot_state() == before
    else:
        release(canvas, end)
        moved = session.snapshot_state()
        assert moved["model"] != before["model"]
        assert moved["ring_fills"][0]["alpha"] == before["ring_fills"][0]["alpha"]
        assert [
            (point.x(), point.y())
            for point in canvas.runtime_state.ring_items()[0].polygon()
        ] == moved["ring_fills"][0]["points"]
        history = canvas.services.history_service
        history.undo()
        assert session.snapshot_state() == before
        history.redo()
        assert session.snapshot_state() == moved
        QTest.keyClick(canvas, Qt.Key.Key_Delete)
        assert session.snapshot_state()["ring_fills"] == []
        history.undo()
        assert session.snapshot_state() == moved
        path = tmp_path / "native-ring.chemvas"
        assert session.save_to_file(str(path)) == []
        session.apply_state(read_document(path).state)
        assert session.snapshot_state() == moved
    assert not qt_errors


def test_ring_geometry_history_recreates_projection_by_id(canvas):
    from chemvas.core.model_commands import SetRingPolygonsCommand
    from chemvas.ui.annotations.projections import find_projection
    from tests.test_annotation_document_ownership import (
        _assert_history_has_no_live_graphics,
    )

    ring = canvas.runtime_state.ring_items()[0]
    key = ring.record_id
    points = [(p.x(), p.y()) for p in ring.polygon()]
    command = SetRingPolygonsCommand([key], [points], [points])
    history = canvas.services.history_service
    history.clear()
    history.push(command)
    _assert_history_has_no_live_graphics(history.state.history)
    sip.delete(ring)
    history.undo()
    restored = find_projection(canvas, key)
    assert restored is not ring
    assert restored.scene() is canvas.scene()
    assert [(p.x(), p.y()) for p in restored.polygon()] == points
    history.redo()
    assert restored.scene() is canvas.scene()
