"""GUI movement and Graph Patch agree on their shared document-editing scope."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtTest import QTest

from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.domain.document.inspection import inspect_components
from chemvas.domain.document.perspective import project_point_3d, unproject_point_3d
from chemvas.features.document_composition import compose_document_state
from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas.canvas_scene_items_state import ring_items_for
from chemvas.ui.selection.selection_queries import selected_atom_ids_for_transform_for
from tests.canvas_factory import build_canvas_view
from tests.document_patch_workflow_support import run_patch
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing
from tests.gui_workflow_support import qt_errors as qt_errors


def _normalized(value):
    return json.loads(json.dumps(value))


def _marked_ring_state(depth):
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "settings": {"bond_length_px": 18.0},
            "atoms": [
                {"id": index, "element": element, "x": x, "y": y}
                for index, (element, x, y) in enumerate(
                    [
                        ("C", 120, 140),
                        ("C", 160, 140),
                        ("O", 140, 180),
                        ("C", 260, 230),
                        ("N", 300, 230),
                    ]
                )
            ],
            "bonds": [
                {"a": a, "b": b, "order": 1}
                for a, b in [(0, 1), (1, 2), (2, 0), (3, 4)]
            ],
            "ring_fills": [{"atom_ids": [0, 1, 2], "color": "#a4b5c6", "alpha": 0.375}],
            "notes": [
                {
                    "x": 230,
                    "y": 280,
                    "runs": [
                        {"text": "Untouched ", "style": {"font_weight": 700}},
                        {
                            "text": "한글 note",
                            "style": {"italic": True, "color": "#135790"},
                        },
                    ],
                }
            ],
        }
    )
    state["marks"] = [
        {
            "kind": kind,
            "text": None,
            "atom_id": atom_id,
            "dx": dx,
            "dy": dy,
            "x": x,
            "y": y,
            "color": color,
        }
        for kind, atom_id, dx, dy, x, y, color in [
            ("plus", 0, 6.0, -15.0, 126.0, 125.0, "#123456"),
            ("minus", 0, None, None, 104.0, 148.0, "#654321"),
            ("radical", 1, 4.0, -14.0, 164.0, 126.0, "#008844"),
            ("minus", None, None, None, 310.0, 150.0, "#8751fe"),
        ]
    ]
    state["model"]["atom_annotations"] = {
        0: {"formal_charge": 0},
        1: {"radical_electrons": 1},
    }
    state["groups"] = [{"atoms": [3, 4], "items": [["notes", 0], ["marks", 3]]}]
    if depth != "absent":
        center, anchor = (140.0, 160.0, 0.0), (140.0, 160.0)
        coordinates = {
            atom_id: unproject_point_3d(
                (
                    state["model"]["atoms"][atom_id]["x"],
                    state["model"]["atoms"][atom_id]["y"],
                ),
                z,
                bond_length_px=18.0,
                center_3d=center,
                anchor_2d=anchor,
            )
            for atom_id, z in enumerate((36.0, -24.0, 12.0))
        }
        if depth == "stale":
            x, y, z = coordinates[0]
            coordinates[0] = (x + 3.25, y, z)
        state["perspective"] = {
            "atom_coords_3d": coordinates,
            "projection_center_3d": center,
            "projection_anchor_2d": anchor,
        }
    return state


def _prepare(drawing, app, tool_name, scope, depth):
    _window, canvas = drawing
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(_marked_ring_state(depth))
    canvas.services.tool_mode_controller.set_tool(tool_name)
    canvas.centerOn(170, 175)
    canvas.scene().clearSelection()
    if scope == "atom":
        visible_atom_item_for(canvas, 0).setSelected(True)
        moving, press = {0}, QPointF(120, 140)
    else:
        canvas.runtime_state.bond_graphics_state.bond_items.get(0, [])[0].setSelected(
            True
        )
        moving, press = {0, 1}, QPointF(140, 140)
    app.processEvents()
    assert selected_atom_ids_for_transform_for(canvas) == moving
    canvas.services.history_service.clear()
    return canvas, documents, moving, canvas.mapFromScene(press)


def _live_graphics(canvas):
    marks = [item for item in canvas.scene().items() if item.data(0) == "mark"]

    def metadata(item):
        data = deepcopy(item.data(1))
        # Loading may omit these optional Qt keys; history explicitly sets
        # their equivalent None defaults. Keep every other key/value exact.
        for key in ("text", "dx", "dy"):
            data.setdefault(key, None)
        return data

    return {
        "marks": {
            item: (
                item.data(1)["atom_id"],
                (
                    canvas.services.scene_decoration_build_service.mark_center(
                        item
                    ).x(),
                    canvas.services.scene_decoration_build_service.mark_center(
                        item
                    ).y(),
                ),
                metadata(item),
            )
            for item in marks
        },
        "rings": {
            item: [(point.x(), point.y()) for point in item.mapToScene(item.polygon())]
            for item in ring_items_for(canvas)
        },
    }


def _assert_graphics_moved(canvas, before, moving, delta):
    after = _live_graphics(canvas)
    assert after["marks"].keys() == before["marks"].keys()
    for item, (atom_id, center, data) in before["marks"].items():
        expected = (
            (center[0] + delta.x(), center[1] + delta.y())
            if atom_id in moving
            else center
        )
        assert after["marks"][item][1] == pytest.approx(expected, rel=0, abs=1e-10)
        assert after["marks"][item][2] == data
    assert after["rings"].keys() == before["rings"].keys()
    for item, points in after["rings"].items():
        expected = [
            (canvas.model.atoms[atom_id].x, canvas.model.atoms[atom_id].y)
            for atom_id in item.data(2)
        ]
        assert len(points) == len(expected)
        for point, target in zip(points, expected, strict=True):
            assert point == pytest.approx(target, rel=0, abs=1e-10)


def _assert_reopened_graphics(canvas, state, moving):
    graphics = _live_graphics(canvas)
    expected_marks = {
        (mark["atom_id"], mark["kind"], mark["color"]): mark for mark in state["marks"]
    }
    actual_marks = {
        (atom_id, data["kind"], data["color"]): (center, data)
        for atom_id, center, data in graphics["marks"].values()
    }
    assert len(actual_marks) == len(graphics["marks"]) == len(state["marks"])
    assert actual_marks.keys() == expected_marks.keys()
    for key, (center, data) in actual_marks.items():
        expected = expected_marks[key]
        target = (expected["x"], expected["y"])
        if expected["atom_id"] in moving:
            assert center == pytest.approx(target, rel=0, abs=1e-10)
        else:
            assert center == target
        for field in ("text", "dx", "dy"):
            assert data[field] == expected[field]
    assert len(graphics["rings"]) == len(state["ring_fills"]) == 1
    ring, points = next(iter(graphics["rings"].items()))
    expected_ring = state["ring_fills"][0]
    assert ring.data(2) == expected_ring["atom_ids"]
    for atom_id, point, target in zip(
        ring.data(2), points, expected_ring["points"], strict=True
    ):
        if atom_id in moving:
            assert point == pytest.approx(target, rel=0, abs=1e-10)
        else:
            assert point == tuple(target)


def _moved_coordinate_paths(state, moving):
    paths = {
        ("model", "atoms", str(atom_id), axis)
        for atom_id in moving
        for axis in ("x", "y")
    }
    for index, mark in enumerate(state["marks"]):
        if mark["atom_id"] in moving:
            paths.update(("marks", index, axis) for axis in ("x", "y"))
    for index, ring in enumerate(state["ring_fills"]):
        for vertex, atom_id in enumerate(ring["atom_ids"]):
            if atom_id in moving:
                paths.update(
                    ("ring_fills", index, "points", vertex, axis) for axis in (0, 1)
                )
    for atom_id in state.get("perspective", {}).get("atom_coords_3d", {}):
        if int(atom_id) in moving:
            paths.update(
                ("perspective", "atom_coords_3d", atom_id, axis) for axis in (0, 1)
            )
    return paths


def _assert_complete_state(actual, expected, moved_paths=frozenset(), path=()):
    if isinstance(expected, dict):
        assert isinstance(actual, dict), path
        assert actual.keys() == expected.keys(), path
        for key, value in expected.items():
            _assert_complete_state(actual[key], value, moved_paths, (*path, key))
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), path
        for index, value in enumerate(expected):
            _assert_complete_state(actual[index], value, moved_paths, (*path, index))
    elif path in moved_paths:
        assert actual == pytest.approx(expected, rel=0, abs=1e-10), path
    else:
        assert actual == expected, path


@pytest.mark.parametrize("tool_name", ["select", "move"])
@pytest.mark.parametrize("scope", ["atom", "bond"])
@pytest.mark.parametrize("depth", ["absent", "nonzero", "stale"])
def test_pointer_move_matches_public_cli_and_exact_history(
    drawing, app, qt_errors, tmp_path, tool_name, scope, depth
):
    canvas, documents, moving, start = _prepare(drawing, app, tool_name, scope, depth)
    before = documents.snapshot_state()
    normalized_before = _normalized(before)
    source = tmp_path / "source.chemvas"
    write_document(source, before, CANVAS_FILE_VERSION)
    source_bytes = source.read_bytes()
    assert read_document(source).state == normalized_before
    graphics_before = _live_graphics(canvas)
    assert len(graphics_before["marks"]) == 4 and len(graphics_before["rings"]) == 1
    groups = dict(canvas.runtime_state.group_state.groups)
    raw_before = dict(canvas.runtime_state.atom_coords_3d_state.atom_coords_3d)
    rotation = canvas.runtime_state.rotation_state
    frame = (rotation.projection_center_3d, rotation.projection_anchor_2d)
    if depth == "stale":
        # Native snapshots intentionally omit stale cache entries. The CLI
        # receives that exact snapshot; raw GUI cache preservation is separate.
        assert 0 in raw_before
        assert set(normalized_before["perspective"]["atom_coords_3d"]) == {"1", "2"}
    elif depth == "nonzero":
        assert set(normalized_before["perspective"]["atom_coords_3d"]) == {
            "0",
            "1",
            "2",
        }
    else:
        assert raw_before == {} and "perspective" not in normalized_before
    if depth != "absent":
        assert set(raw_before) == {0, 1, 2}
    end = start + QPoint(36, -24)
    assert canvas.viewport().rect().contains(start)
    assert canvas.viewport().rect().contains(end)
    # Targets come from input-event coordinates, never from the resulting atoms.
    delta = canvas.mapToScene(end) - canvas.mapToScene(start)
    targets = {
        atom_id: (
            before["model"]["atoms"][atom_id]["x"] + delta.x(),
            before["model"]["atoms"][atom_id]["y"] + delta.y(),
        )
        for atom_id in moving
    }
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end)
    app.processEvents()
    for atom_id, target in targets.items():
        atom = canvas.model.atoms[atom_id]
        assert (atom.x, atom.y) == pytest.approx(target, rel=0, abs=1e-10)
    _assert_graphics_moved(canvas, graphics_before, moving, delta)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    app.processEvents()
    after = documents.snapshot_state()
    raw_after = dict(canvas.runtime_state.atom_coords_3d_state.atom_coords_3d)
    if depth == "nonzero" and scope == "atom":
        # Independent numeric oracle: 180% viewport, z=36, focal=144.
        # The inverse screen scale is exactly 3/4, not one world unit per pixel.
        assert (delta.x(), delta.y()) == pytest.approx(
            (20.0, -40.0 / 3), rel=0, abs=1e-10
        )
        assert raw_before[0] == (125.0, 145.0, 36.0)
        assert raw_after[0] == pytest.approx((140.0, 135.0, 36.0), rel=0, abs=1e-10)
    assert raw_after.keys() == raw_before.keys()
    assert (rotation.projection_center_3d, rotation.projection_anchor_2d) == frame
    for atom_id, original in raw_before.items():
        if atom_id not in moving:
            assert raw_after[atom_id] == original
            continue
        assert raw_after[atom_id][2] == original[2]
        projected_before = project_point_3d(
            original, bond_length_px=18.0, center_3d=frame[0], anchor_2d=frame[1]
        )
        projected_after = project_point_3d(
            raw_after[atom_id],
            bond_length_px=18.0,
            center_3d=frame[0],
            anchor_2d=frame[1],
        )
        assert projected_after == pytest.approx(
            (projected_before[0] + delta.x(), projected_before[1] + delta.y()),
            rel=0,
            abs=1e-10,
        )
    components = inspect_components(after)
    assert components[0].formal_charge == 0 and components[0].radical_electrons == 1
    _assert_graphics_moved(canvas, graphics_before, moving, delta)
    result, output = run_patch(
        tmp_path,
        source,
        [
            {"op": "move_atom", "atom_id": atom_id, "x": x, "y": y}
            for atom_id, (x, y) in sorted(targets.items())
        ],
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["candidate_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    _assert_complete_state(
        _normalized(after),
        read_document(output).state,
        _moved_coordinate_paths(normalized_before, moving),
    )
    history = canvas.services.history_service
    assert len(history.state.history) == 1
    graphics_after = _live_graphics(canvas)
    for _ in range(2):
        history.undo()
        assert documents.snapshot_state() == before
        assert canvas.runtime_state.atom_coords_3d_state.atom_coords_3d == raw_before
        assert _live_graphics(canvas) == graphics_before
        history.redo()
        assert documents.snapshot_state() == after
        assert canvas.runtime_state.atom_coords_3d_state.atom_coords_3d == raw_after
        assert _live_graphics(canvas) == graphics_after
        assert canvas.runtime_state.group_state.groups.keys() == groups.keys()
        assert all(
            canvas.runtime_state.group_state.groups[key] is group
            for key, group in groups.items()
        )
    saved = tmp_path / "gui-saved.chemvas"
    assert documents.save_to_file(str(saved)) == []
    _assert_complete_state(read_document(saved).state, _normalized(after))
    for path in (output, saved):
        stored = read_document(path).state
        documents.apply_state(stored)
        app.processEvents()
        _assert_reopened_graphics(canvas, stored, moving)
        _assert_complete_state(
            _normalized(documents.snapshot_state()),
            stored,
            _moved_coordinate_paths(stored, moving),
        )
        assert not qt_errors
    assert source.read_bytes() == source_bytes
    assert source_bytes != saved.read_bytes()
    assert not qt_errors


@pytest.mark.parametrize("route", ["select", "move", "transform"])
def test_move_after_document_replacement_is_confined_to_its_canvas(
    drawing, app, qt_errors, tmp_path, route
):
    tool_name = "select" if route == "transform" else route
    canvas, documents, _moving, _start = _prepare(
        drawing, app, tool_name, "atom", "nonzero"
    )
    retired_model = canvas.model
    retired_atoms = deepcopy(retired_model.atoms)

    # The controllers outlive a loaded document. Reuse them after the model,
    # graphics and 3D cache have been replaced, with overlapping atom ids.
    canvas, documents, moving, start = _prepare(
        drawing, app, tool_name, "atom", "absent"
    )
    assert canvas.model is not retired_model
    before = documents.snapshot_state()
    graphics_before = _live_graphics(canvas)
    other = build_canvas_view()
    try:
        other_documents = other.services.canvas_document_session_service
        other_documents.apply_state(_marked_ring_state("nonzero"))
        other_before = other_documents.snapshot_state()

        if route == "transform":
            delta = QPointF(20, -10)
            canvas.services.scene_transform_controller.translate_selected_items(
                delta.x(), delta.y()
            )
        else:
            end = start + QPoint(36, -24)
            delta = canvas.mapToScene(end) - canvas.mapToScene(start)
            QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
            QTest.mouseMove(canvas.viewport(), end)
            QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
            app.processEvents()

        after = documents.snapshot_state()
        assert after != before
        atom = canvas.model.atoms[0]
        assert (atom.x, atom.y) == pytest.approx(
            (
                before["model"]["atoms"][0]["x"] + delta.x(),
                before["model"]["atoms"][0]["y"] + delta.y(),
            ),
            rel=0,
            abs=1e-10,
        )
        _assert_graphics_moved(canvas, graphics_before, moving, delta)
        history = canvas.services.history_service
        assert len(history.state.history) == 1
        history.undo()
        assert documents.snapshot_state() == before
        history.redo()
        assert documents.snapshot_state() == after
        assert retired_model.atoms == retired_atoms
        assert other_documents.snapshot_state() == other_before
        assert not other.services.history_service.can_undo()
        assert not canvas.runtime_state.atom_coords_3d_state.atom_coords_3d

        saved = tmp_path / "replacement-moved.chemvas"
        assert documents.save_to_file(str(saved)) == []
        assert read_document(saved).state == _normalized(after)
        assert not qt_errors
    finally:
        other.close()
        other.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("finish", ["cancel", "no-op"])
def test_uncommitted_gui_move_keeps_history_while_cli_noop_is_rejected(
    drawing, app, qt_errors, tmp_path, finish
):
    canvas, documents, _moving, start = _prepare(
        drawing, app, "select", "atom", "nonzero"
    )
    before = documents.snapshot_state()
    raw_before = dict(canvas.runtime_state.atom_coords_3d_state.atom_coords_3d)
    graphics = _live_graphics(canvas)
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    source = tmp_path / "source.chemvas"
    write_document(source, before, CANVAS_FILE_VERSION)
    end = start + QPoint(36, -24) if finish == "cancel" else start
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end)
    if finish == "cancel":
        assert documents.snapshot_state() != before
        QTest.keyClick(canvas.viewport(), Qt.Key.Key_Escape)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    app.processEvents()
    assert documents.snapshot_state() == before
    assert canvas.runtime_state.atom_coords_3d_state.atom_coords_3d == raw_before
    assert _live_graphics(canvas) == graphics
    history.verify_stack_snapshot(stacks)
    atom = before["model"]["atoms"][0]
    result, output = run_patch(
        tmp_path,
        source,
        [
            {"op": "move_atom", "atom_id": 0, "x": atom["x"], "y": atom["y"]},
        ],
    )
    assert result.returncode != 0
    assert "move_atom must change the atom position" in result.stderr
    assert result.stdout == "" and not output.exists()
    assert not qt_errors
