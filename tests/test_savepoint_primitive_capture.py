from __future__ import annotations

from unittest import mock

import pytest
from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QApplication
from scripts.benchmark_editor import document_state

from chemvas.ui.transactions.document import DocumentSavepoint, MoveGestureScope
from chemvas.ui.transactions.scene_runtime import BondPrimitiveGraphicsSnapshot
from tests.canvas_factory import build_canvas_view


@pytest.fixture
def canvas():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    view = build_canvas_view()
    view.services.canvas_document_session_service.apply_state(document_state(10))
    yield view
    view.services.canvas_scene_reset_service.clear_scene()
    view.close()
    view.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("scoped", [False, True])
def test_savepoint_reads_each_primitive_once_without_reusing_later_values(
    canvas, scoped
):
    state = canvas.runtime_state
    bond = state.bond_graphics_state.bond_items[0][0]
    atom = state.atom_graphics_state.atom_dots[0]
    scope = (
        MoveGestureScope(
            atom_ids=frozenset({0}),
            bond_ids=frozenset({0}),
            scene_items=(bond, atom),
        )
        if scoped
        else None
    )
    with mock.patch.object(
        BondPrimitiveGraphicsSnapshot,
        "capture",
        wraps=BondPrimitiveGraphicsSnapshot.capture,
    ) as capture:
        first = DocumentSavepoint.capture(canvas, move_scope=scope)
    items = [call.args[0] for call in capture.call_args_list]
    assert len(items) == len({id(item) for item in items})
    exact = {
        id(snapshot.item): snapshot.primitive_graphics for snapshot in first.scene_items
    }
    for snapshot in (
        *first.scene_runtime.bond_primitive_graphics,
        *first.atom_primitive_graphics,
    ):
        assert snapshot is exact[id(snapshot.item)]
    original_pen = QPen(bond.pen())
    first.release()

    changed_pen = QPen(original_pen)
    changed_pen.setWidthF(original_pen.widthF() + 3)
    bond.setPen(changed_pen)
    second = DocumentSavepoint.capture(canvas, move_scope=scope)
    second_bond = next(
        snapshot for snapshot in second.scene_items if snapshot.item is bond
    )
    assert second_bond.primitive_graphics is not exact[id(bond)]
    assert dict(second_bond.primitive_graphics.properties)["setPen"] == changed_pen
    assert dict(exact[id(bond)].properties)["setPen"] == original_pen

    # A later mutation rolls back to the new capture, retaining Qt identities.
    bond.setPen(original_pen)
    result = second.restore()
    assert result.authoritative, result.errors
    assert not result.errors
    assert canvas.runtime_state.bond_graphics_state.bond_items[0][0] is bond
    assert bond.pen() == changed_pen
