from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QTransform

import chemvas.ui.canvas_background_painter as background_painter
from chemvas.ui.sheet_setup_state import SheetSetupState
from tests.runtime_state import canvas_runtime_state


def _canvas() -> SimpleNamespace:
    viewport = mock.Mock()
    return SimpleNamespace(
        runtime_state=canvas_runtime_state(sheet_setup_state=SheetSetupState()),
        viewport=mock.Mock(return_value=viewport),
    )


def test_draw_canvas_background_paints_workspace_shadow_and_sheet(monkeypatch) -> None:
    canvas = _canvas()
    monkeypatch.setattr(
        background_painter, "grid_snap_enabled_for", mock.Mock(return_value=False)
    )
    painter = mock.Mock()
    viewport_rect = QRectF(-100.0, -80.0, 200.0, 160.0)
    sheet_rect = QRectF(-20.0, -10.0, 40.0, 20.0)
    monkeypatch.setattr(
        background_painter, "sheet_rect_for", mock.Mock(return_value=sheet_rect)
    )
    monkeypatch.setattr(
        background_painter, "document_is_empty_for", mock.Mock(return_value=False)
    )

    background_painter.draw_canvas_background_for(canvas, painter, viewport_rect)

    painter.save.assert_called_once_with()
    painter.restore.assert_called_once_with()
    background_painter.sheet_rect_for.assert_called_once_with(canvas)
    # 1 workspace fill + 4 layered drop-shadow rects + 1 white sheet fill.
    assert painter.fillRect.call_count == 6
    assert painter.fillRect.call_args_list[0].args == (viewport_rect, QColor("#e7e7e4"))
    assert painter.fillRect.call_args_list[-1].args == (sheet_rect, QColor("#ffffff"))
    painter.setBrush.assert_called_once_with(Qt.BrushStyle.NoBrush)
    painter.drawRect.assert_called_once_with(sheet_rect)
    pen = painter.setPen.call_args.args[0]
    assert pen.color() == QColor("#dededa")
    assert pen.widthF() == 1.0
    # With the grid off the painter asks once and draws no points.
    background_painter.grid_snap_enabled_for.assert_called_once_with(canvas)
    painter.drawPoints.assert_not_called()


def test_draw_canvas_background_draws_grid_points_when_the_grid_is_on(
    monkeypatch,
) -> None:
    canvas = _canvas()
    painter = mock.Mock()
    painter.transform.return_value = QTransform()
    sheet_rect = QRectF(0.0, 0.0, 40.0, 30.0)
    monkeypatch.setattr(
        background_painter, "sheet_rect_for", mock.Mock(return_value=sheet_rect)
    )
    monkeypatch.setattr(
        background_painter, "document_is_empty_for", mock.Mock(return_value=False)
    )
    monkeypatch.setattr(
        background_painter, "grid_snap_enabled_for", mock.Mock(return_value=True)
    )
    monkeypatch.setattr(
        background_painter, "grid_step_for", mock.Mock(return_value=10.0)
    )

    background_painter.draw_canvas_background_for(
        canvas, painter, QRectF(-100.0, -100.0, 400.0, 400.0)
    )

    points = painter.drawPoints.call_args.args
    # 5 columns (0..40) x 4 rows (0..30) inside the sheet, and nothing outside.
    assert len(points) == 20
    assert all(
        sheet_rect.contains(point) or sheet_rect.intersects(QRectF(point, point))
        for point in points
    )
    assert min(point.x() for point in points) == 0.0
    assert max(point.x() for point in points) == 40.0


def test_draw_canvas_background_skips_a_grid_too_dense_to_read(monkeypatch) -> None:
    canvas = _canvas()
    painter = mock.Mock()
    monkeypatch.setattr(
        background_painter, "document_is_empty_for", mock.Mock(return_value=False)
    )
    dense = (background_painter.MIN_GRID_SPACING_PX / 10.0) * 0.5
    painter.transform.return_value = QTransform().scale(dense, dense)
    monkeypatch.setattr(
        background_painter,
        "sheet_rect_for",
        mock.Mock(return_value=QRectF(0.0, 0.0, 400.0, 300.0)),
    )
    monkeypatch.setattr(
        background_painter, "grid_snap_enabled_for", mock.Mock(return_value=True)
    )
    monkeypatch.setattr(
        background_painter, "grid_step_for", mock.Mock(return_value=10.0)
    )

    background_painter.draw_canvas_background_for(
        canvas, painter, QRectF(-100.0, -100.0, 900.0, 900.0)
    )

    painter.drawPoints.assert_not_called()


def test_draw_canvas_background_writes_the_hint_only_on_an_empty_sheet(
    monkeypatch,
) -> None:
    canvas = _canvas()
    painter = mock.Mock()
    painter.transform.return_value = QTransform().scale(2.0, 2.0)
    sheet_rect = QRectF(0.0, 0.0, 400.0, 300.0)
    monkeypatch.setattr(
        background_painter, "sheet_rect_for", mock.Mock(return_value=sheet_rect)
    )
    monkeypatch.setattr(
        background_painter, "grid_snap_enabled_for", mock.Mock(return_value=False)
    )
    monkeypatch.setattr(
        background_painter, "document_is_empty_for", mock.Mock(return_value=True)
    )

    background_painter.draw_canvas_background_for(
        canvas, painter, QRectF(-100.0, -100.0, 800.0, 600.0)
    )

    # The hint is laid out in device pixels around the sheet centre (400, 300
    # at 200 %) with the painter's transform reset first.
    painter.resetTransform.assert_called_once_with()
    box, alignment, text = painter.drawText.call_args.args
    assert text == background_painter.EMPTY_SHEET_HINT
    assert alignment == Qt.AlignmentFlag.AlignCenter
    assert box.center().x() == 400.0
    assert box.center().y() == 300.0

    painter.drawText.reset_mock()
    background_painter.document_is_empty_for.return_value = False
    background_painter.draw_canvas_background_for(
        canvas, painter, QRectF(-100.0, -100.0, 800.0, 600.0)
    )
    painter.drawText.assert_not_called()


def test_draw_canvas_background_repaints_the_whole_view_when_emptiness_flips(
    monkeypatch,
) -> None:
    canvas = _canvas()
    painter = mock.Mock()
    painter.transform.return_value = QTransform()
    monkeypatch.setattr(
        background_painter,
        "sheet_rect_for",
        mock.Mock(return_value=QRectF(0.0, 0.0, 400.0, 300.0)),
    )
    monkeypatch.setattr(
        background_painter, "grid_snap_enabled_for", mock.Mock(return_value=False)
    )
    monkeypatch.setattr(
        background_painter, "document_is_empty_for", mock.Mock(return_value=True)
    )
    rect = QRectF(10.0, 10.0, 20.0, 20.0)
    update = canvas.viewport().update

    # The first pass only records the state; repeating it asks for nothing.
    background_painter.draw_canvas_background_for(canvas, painter, rect)
    background_painter.draw_canvas_background_for(canvas, painter, rect)
    update.assert_not_called()

    # A partial pass that first sees an object on the sheet asks for one full
    # repaint, so the hint's pixels outside that pass are cleared too.
    background_painter.document_is_empty_for.return_value = False
    background_painter.draw_canvas_background_for(canvas, painter, rect)
    background_painter.draw_canvas_background_for(canvas, painter, rect)
    assert update.call_count == 1

    # And once more when the last object goes away.
    background_painter.document_is_empty_for.return_value = True
    background_painter.draw_canvas_background_for(canvas, painter, rect)
    assert update.call_count == 2
    assert canvas.runtime_state.sheet_setup_state.empty_hint_shown is True


def test_document_is_empty_for_reads_atoms_and_every_scene_registry() -> None:
    from chemvas.ui.canvas_scene_items_state import CanvasSceneItemsState

    def canvas_with(*, atoms, **registries):
        return SimpleNamespace(
            model=SimpleNamespace(atoms=atoms),
            runtime_state=canvas_runtime_state(
                scene_items_state=CanvasSceneItemsState(**registries)
            ),
        )

    assert background_painter.document_is_empty_for(canvas_with(atoms={}))
    assert not background_painter.document_is_empty_for(
        canvas_with(atoms={1: object()})
    )
    for name in (
        "ring_items",
        "note_items",
        "image_items",
        "mark_items",
        "arrow_items",
        "ts_bracket_items",
        "shape_items",
        "orbital_items",
    ):
        assert not background_painter.document_is_empty_for(
            canvas_with(atoms={}, **{name: [object()]})
        ), name
