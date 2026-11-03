"""Ring edits must leave the same bond geometry as reopening the document."""

from __future__ import annotations

import pytest

from tests.canvas_factory import build_canvas_view
from tests.native_canvas_support import app as app
from tests.native_canvas_support import canvas as canvas


def _bond_paths(view):
    result = {}
    for bond_id, items in view.runtime_state.bond_graphics_state.bond_items.items():
        paths = []
        for item in items:
            path = item.mapToScene(item.shape())
            paths.append(
                [
                    (
                        path.elementAt(i).type.value,
                        path.elementAt(i).x,
                        path.elementAt(i).y,
                    )
                    for i in range(path.elementCount())
                ]
            )
        result[bond_id] = paths
    return result


@pytest.mark.parametrize("ring_size", [5, 6])
def test_ring_insertion_undo_redo_has_the_reopened_bond_outlines(canvas, ring_size):
    for x in [0, 40, 80]:
        canvas.model.add_atom("C", x, 0)
    canvas.model.add_bond(0, 1, 1)
    canvas.model.add_bond(1, 2, 1)
    service = canvas.services.structure_build_service
    service.render_model()
    history = canvas.services.history_service
    reopened = build_canvas_view()
    try:
        actions = [
            lambda: service.sprout_regular_ring_from_atom(0, ring_size),
            lambda: service.sprout_regular_ring_from_atom(2, 6),
            history.undo,
            history.redo,
            history.undo,
            history.undo,
            history.redo,
        ]
        for action in actions:
            action()
            state = canvas.services.canvas_document_session_service.snapshot_state()
            live = _bond_paths(canvas)
            reopened.services.canvas_document_session_service.apply_state(state)
            fresh = _bond_paths(reopened)
            assert fresh.keys() == live.keys()
            for bond_id in live:
                assert len(live[bond_id]) == len(fresh[bond_id])
                for actual, expected in zip(live[bond_id], fresh[bond_id], strict=True):
                    assert len(actual) == len(expected)
                    for actual_point, expected_point in zip(
                        actual, expected, strict=True
                    ):
                        assert actual_point == pytest.approx(expected_point, abs=1e-9)
            assert (
                canvas.services.canvas_document_session_service.snapshot_state()
                == state
            )
    finally:
        reopened.services.canvas_scene_reset_service.clear_scene()
        reopened.close()
