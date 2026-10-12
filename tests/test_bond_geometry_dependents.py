"""Adjacent paint follows existing move/rotation/history workflows."""

import json
import math
from unittest import mock

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsPolygonItem

from chemvas.bootstrap.document_cli_shared import offscreen_document_scene
from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION, Atom, Bond
from chemvas.features.export import ExportPlan
from chemvas.ui.export.export_render_service import (
    render_export_plan,
    resolve_export_plan,
)
from tests.canvas_factory import build_canvas_view
from tests.test_cdxml_export import _simple_state
from tests.test_perspective_move import _event_at, _select_atoms, _start_drag


@pytest.fixture
def canvas(qt_application):
    view = build_canvas_view()
    view.resize(800, 600)
    yield view
    view.services.canvas_scene_reset_service.clear_scene()
    view.close()
    qt_application.processEvents()


def _prepare(canvas, style):
    order = 2 if style.startswith("double") else 1
    state = _simple_state(
        atoms={
            0: Atom("C", 0, 40),
            1: Atom("C", 0, 0),
            2: Atom("C", 40, 0),
            3: Atom("C", 100, 80),
            4: Atom("C", 140, 80),
        },
        bonds=[
            Bond(0, 1, style="bold_in" if style == "bold_in" else "single"),
            Bond(1, 2, order, style),
            Bond(3, 4),
        ],
    )
    canvas.services.canvas_document_session_service.apply_state(state)
    canvas.services.history_service.clear()


def _paint(context):
    result = {}
    for bond_id, items in context.state.bond_graphics_state.bond_items.items():
        coordinates = []
        for item in items:
            if isinstance(item, QGraphicsLineItem):
                for p in [item.line().p1(), item.line().p2()]:
                    point = item.mapToScene(p)
                    coordinates.extend((point.x(), point.y()))
                polygon = item.stroke_polygon()
            elif isinstance(item, QGraphicsPolygonItem):
                polygon = item.polygon()
            else:
                raise AssertionError(type(item))
            if polygon is not None:
                for p in polygon:
                    point = item.mapToScene(p)
                    coordinates.extend((point.x(), point.y()))
        result[bond_id] = coordinates
    return result


def _same(a, b):
    assert a.keys() == b.keys()
    for key in a:
        assert a[key] == pytest.approx(b[key], abs=1e-9, rel=1e-12)


def _verify_reopen_export(canvas, tmp_path):
    docs = canvas.services.canvas_document_session_service
    state = docs.snapshot_state()
    path = tmp_path / "saved.chemvas"
    write_document(path, state, CANVAS_FILE_VERSION)
    loaded = read_document(path)
    assert json.loads(json.dumps(loaded.state["model"])) == json.loads(
        json.dumps(state["model"])
    )
    live = _paint(canvas.render_context)
    with offscreen_document_scene(loaded.state, command="neighbor-reopen") as fresh:
        _same(live, _paint(fresh))
        for name, context in [("live", canvas.render_context), ("reopened", fresh)]:
            items, _ = resolve_export_plan(context.scene, margin=3, target_width_pt=180)
            plan = ExportPlan(
                source_x=-20,
                source_y=-20,
                source_w=180,
                source_h=140,
                out_w_pt=180,
                out_h_pt=140,
            )
            render_export_plan(
                context.scene,
                str(tmp_path / (name + ".png")),
                items=items,
                plan=plan,
                fmt="png",
                dpi=144,
                background="white",
            )
        assert (tmp_path / "live.png").read_bytes() == (
            tmp_path / "reopened.png"
        ).read_bytes()
    return live


@pytest.mark.parametrize("style", ["single", "double", "double_outer", "bold_in"])
def test_pointer_release_undo_redo_and_export_match_reopen(canvas, tmp_path, style):
    _prepare(canvas, style)
    initial = _paint(canvas.render_context)
    unrelated = tuple(canvas.runtime_state.bond_graphics_state.bond_items[2])
    tool, start = _start_drag(canvas, {0})
    event = _event_at(canvas, start + QPointF(40, 0))
    assert tool.on_mouse_move(event)
    # The dependency refresh is required during the gesture, not just on release.
    _verify_reopen_export(canvas, tmp_path)
    assert tool.on_mouse_release(event)
    live = _verify_reopen_export(canvas, tmp_path)
    assert live[1] != initial[1]
    if style == "single":
        assert live[1][4] == pytest.approx(-0.75 * (1 + math.sqrt(2)))
    if style == "double":
        assert live[1][12] == pytest.approx(4.84 * (1 + math.sqrt(2)))
    assert tuple(canvas.runtime_state.bond_graphics_state.bond_items[2]) == unrelated
    _same({2: initial[2]}, {2: live[2]})
    history = canvas.services.history_service
    for _ in range(2):
        history.undo()
        _same(_paint(canvas.render_context), initial)
        _verify_reopen_export(canvas, tmp_path)
        history.redo()
        _same(_paint(canvas.render_context), live)
        _verify_reopen_export(canvas, tmp_path)


@pytest.mark.parametrize(
    "route", ["direct_atom", "direct_bond", "absolute", "optimized_internal"]
)
def test_move_routes_refresh_stationary_and_selected_neighbor_outlines(
    canvas, tmp_path, route
):
    _prepare(canvas, "single")
    move = canvas.services.move_controller
    if route == "direct_atom":
        item = canvas.runtime_state.atom_graphics_state.atom_dots[0]
        move.move_item(item, 40, 0)
    elif route == "direct_bond":
        move.move_item(
            canvas.runtime_state.bond_graphics_state.bond_items[0][0], 20, 10
        )
    elif route == "absolute":
        move.set_atom_positions({0: (40, 40)})
    else:
        # AB has both ends selected, but must be recomputed because BC is fixed.
        move.move_atoms({0, 1}, 20, 10, bond_ids={0}, redraw_bond_ids={1})
    _verify_reopen_export(canvas, tmp_path)


@pytest.mark.parametrize("mode", ["2d", "3d"])
def test_partial_rotation_undo_redo_refreshes_stationary_neighbor(
    canvas, tmp_path, mode
):
    _prepare(canvas, "double")
    initial = _paint(canvas.render_context)
    # Both B and C stay still: BC changes only through A's new incident angle.
    _select_atoms(canvas, {0, 3})
    if mode == "2d":
        canvas.services.scene_transform_controller.rotate_selected_items(45)
    else:
        rotation = canvas.services.selection_rotation_controller
        assert rotation.begin_selection_3d_rotation(press_pos=QPointF())
        rotation.update_selection_3d_rotation(60, 80)
        rotation.end_selection_3d_rotation()
    after = _verify_reopen_export(canvas, tmp_path)
    assert after[1] != initial[1]
    history = canvas.services.history_service
    history.undo()
    _same(_paint(canvas.render_context), initial)
    history.redo()
    _same(_paint(canvas.render_context), after)
    _verify_reopen_export(canvas, tmp_path)


@pytest.mark.parametrize(
    "finish", ["cancel", "failed_commit", "failed_commit_and_refresh"]
)
def test_partial_drag_rollback_restores_neighbor_and_unrelated_paint(canvas, finish):
    _prepare(canvas, "double")
    initial = _paint(canvas.render_context)
    tool, start = _start_drag(canvas, {0})
    event = _event_at(canvas, start + QPointF(40, 0))
    assert tool.on_mouse_move(event)
    if finish == "cancel":
        tool._cancel_selection_drag()
    elif finish == "failed_commit":
        with mock.patch.object(canvas.services.history_service.state, "enabled", False):
            with pytest.raises(RuntimeError):
                tool._commit_selection_drag()
    else:
        with (
            mock.patch.object(canvas.services.history_service.state, "enabled", False),
            mock.patch.object(
                canvas.bond_renderer,
                "update_bond_geometry",
                side_effect=RuntimeError("refresh failed"),
            ),
            pytest.raises(RuntimeError),
        ):
            tool._commit_selection_drag()
    _same(_paint(canvas.render_context), initial)


def test_whole_component_translation_preserves_item_translation_fast_path(canvas):
    _prepare(canvas, "single")
    items = tuple(canvas.runtime_state.bond_graphics_state.bond_items[0])
    polygon = [(p.x(), p.y()) for p in items[0].stroke_polygon()]
    canvas.services.move_controller.move_atoms(
        {0, 1, 2}, 20, 10, bond_ids={0, 1}, redraw_bond_ids=set()
    )
    assert tuple(canvas.runtime_state.bond_graphics_state.bond_items[0]) == items
    assert [(p.x(), p.y()) for p in items[0].stroke_polygon()] == polygon
    assert items[0].pos() == QPointF(20, 10)
