"""Rigid movement must not flip the terminal double-bond side on reconstruction."""

import math

import pytest
from PyQt6.QtCore import QPointF

from chemvas.adapters.qt.renderer import Renderer
from chemvas.bootstrap.document_cli_shared import offscreen_document_scene
from chemvas.domain.document import CANVAS_FILE_VERSION, Atom, Bond
from chemvas.features.rendering import line_normal
from chemvas.ui.canvas.canvas_view import CanvasView
from chemvas.ui.export.figure_export_service import FigureExportService
from tests.document_file_helpers import read_document, write_document
from tests.test_cdxml_export import _simple_state

pytestmark = pytest.mark.usefixtures("qt_application")


def _geometry(context):
    label = context.state.atom_graphics_state.atom_items[1]
    center = label.mapToScene(label.label_position_center())
    lines = []
    for item in context.state.bond_graphics_state.bond_items[0]:
        for point in (item.line().p1(), item.line().p2()):
            point = item.mapToScene(point)
            lines.extend((point.x(), point.y()))
    return (center.x(), center.y()), lines


@pytest.mark.parametrize("angle", [0, 37, 90, 180, 223])
@pytest.mark.parametrize("style", ["double", "double_outer", "double_center"])
@pytest.mark.parametrize("scale", [0.1, 1, 10])
@pytest.mark.parametrize("delta", [(0.1, 0.2), (1000.1, -777.2)])
def test_drag_save_reopen_and_undo_redo_preserve_terminal_double_geometry(
    tmp_path, angle, style, scale, delta
):
    radians = math.radians(angle)

    def atom(element, x, y):
        return Atom(
            element,
            scale * (x * math.cos(radians) - y * math.sin(radians)),
            scale * (x * math.sin(radians) + y * math.cos(radians)),
        )

    canvas = CanvasView(renderer=Renderer())
    try:
        session = canvas.services.canvas_document_session_service
        session.apply_state(
            _simple_state(
                atoms={
                    0: atom("C", 0, 0),
                    1: atom("O", 40, 0),
                    2: atom("C", -30, 30),
                    3: atom("C", -30, -30),
                },
                bonds=[Bond(0, 1, order=2, style=style), Bond(0, 2), Bond(0, 3)],
            )
        )
        initial = _geometry(canvas.render_context)
        canvas.services.tool_mode_controller.set_tool("select")
        tool = canvas.services.tool_controller.active
        assert tool._begin_selection_drag({0, 1, 2, 3}, [], QPointF())
        tool._apply_drag_delta(QPointF(*delta))
        tool._commit_selection_drag()
        live = _geometry(canvas.render_context)
        assert live[0] == pytest.approx(
            tuple(a + d for a, d in zip(initial[0], delta, strict=True)), abs=1e-7
        )
        state = session.snapshot_state()
        path = tmp_path / "moved.cdxml"
        write_document(path, state, CANVAS_FILE_VERSION)
        before = path.read_bytes()
        with offscreen_document_scene(
            read_document(path).state, command="reopen"
        ) as ctx:
            reopened = _geometry(ctx)
            assert reopened[0] == pytest.approx(live[0], abs=1e-7)
            assert reopened[1] == pytest.approx(live[1], abs=1e-7)
            if (angle, style, scale, delta) == (0, "double", 1, (0.1, 0.2)):
                options = dict(
                    fmt="png",
                    scope="content",
                    dpi=150,
                    background="white",
                    sizing="custom",
                    target_width_mm=90,
                )
                direct, fresh = tmp_path / "live.png", tmp_path / "reopened.png"
                FigureExportService(canvas.render_context).export_figure(
                    str(direct), **options
                )
                FigureExportService(ctx).export_figure(str(fresh), **options)
                assert direct.read_bytes() == fresh.read_bytes()
        history = canvas.services.history_service
        history.undo()
        assert _geometry(canvas.render_context)[0] == pytest.approx(
            initial[0], abs=1e-7
        )
        history.redo()
        redone = _geometry(canvas.render_context)
        assert redone[0] == pytest.approx(live[0], abs=1e-7)
        assert redone[1] == pytest.approx(live[1], abs=1e-7)
        assert session.snapshot_state() == state
        assert path.read_bytes() == before
    finally:
        canvas.close()


@pytest.mark.parametrize("scale", [0.001, 1, 1000])
@pytest.mark.parametrize("offset", [(0, 0), (0.1, 0.2), (1000.1, -777.2)])
@pytest.mark.parametrize("side", [-1, 0, 1])
def test_shared_normal_ties_are_local_and_real_sides_remain_distinct(
    scale, offset, side
):
    x, y = offset
    normal = line_normal(
        x,
        y,
        x + 40 * scale,
        y,
        QPointF(x - 30 * scale, y + side * 0.01 * scale),
    )
    assert normal == (0, -1 if side < 0 else 1)
