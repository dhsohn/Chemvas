"""Public edit paths must preserve native geometry in live and reopened scenes."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.canvas_factory import build_canvas_view
from tests.native_canvas_support import app as app
from tests.native_canvas_support import canvas as canvas


def test_headless_public_atom_move_needs_no_gui_packages():
    source = Path(__file__).resolve().parents[1] / "app"
    code = """
import copy, sys
sys.path.insert(0, sys.argv[1])
from chemvas.bootstrap.web_adapter import new_document, edit_document
document = edit_document({'document': new_document(), 'edit': {
    'kind': 'bond', 'start': [0, 0], 'end': [20, 0], 'style': 'single'
}})['document']
before = copy.deepcopy(document)
assert not any(n.split('.')[0] in {'PyQt6', 'PIL', 'rdkit'} for n in sys.modules)
result = edit_document({'document': document, 'edit': {
    'kind': 'move', 'selection': [{'target': 'atom', 'id': 0}], 'dx': 5, 'dy': 0
}})
assert result['document']['state']['model']['atoms'][0]['x'] == 5
assert result['document']['state']['model']['atoms'][1]['x'] == 20
assert document == before
assert result['drawing']['bonds']['0']
assert not any(n.split('.')[0] in {'PyQt6', 'PIL', 'rdkit'} for n in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", code, str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


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


@pytest.mark.parametrize("style", ["single", "double", "double_center", "double_outer"])
def test_browser_centerline_and_painted_outline_both_match_native(canvas, style):
    from chemvas.bootstrap.web_adapter import document_info, edit_document, new_document
    from chemvas.domain.document import extract_document_state

    result = edit_document(
        {
            "document": new_document(),
            "edit": {
                "kind": "bond",
                "start": [0, 0],
                "end": [20, 8],
                "style": "single",
            },
        }
    )
    result["document"]["state"]["model"]["bonds"][0].update(
        style=style, order=1 if style == "single" else 2
    )
    result = document_info(result["document"])
    canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(result["document"])
    )
    for bond_id, items in canvas.runtime_state.bond_graphics_state.bond_items.items():
        primitives = result["drawing"]["bonds"][str(bond_id)]
        assert len(primitives) == len(items)
        for item, primitive in zip(items, primitives, strict=True):
            line = item.line()
            assert primitive["line"] == pytest.approx(
                (line.x1(), line.y1(), line.x2(), line.y2())
            )
            polygon = item.stroke_polygon()
            assert polygon is not None
            assert len(primitive["polygon"]) == len(polygon)
            for actual, point in zip(primitive["polygon"], polygon, strict=True):
                assert actual == pytest.approx((point.x(), point.y()))
