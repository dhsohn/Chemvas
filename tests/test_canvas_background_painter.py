from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QTransform

import chemvas.ui.canvas.canvas_background_painter as background_painter
from chemvas.ui.canvas.canvas_tool_settings_state import CanvasToolSettingsState


class _CountingToolSettings:
    """Tool settings whose grid flag counts how often the painter reads it."""

    def __init__(self, *, grid_snap_enabled: bool) -> None:
        self._grid_snap_enabled = grid_snap_enabled
        self.grid_snap_reads = 0

    @property
    def grid_snap_enabled(self) -> bool:
        self.grid_snap_reads += 1
        return self._grid_snap_enabled


def _canvas_with_grid(settings) -> SimpleNamespace:
    return SimpleNamespace(runtime_state=SimpleNamespace(tool_settings_state=settings))


def test_draw_canvas_background_paints_workspace_shadow_and_sheet(monkeypatch) -> None:
    settings = _CountingToolSettings(grid_snap_enabled=False)
    canvas = _canvas_with_grid(settings)
    painter = mock.Mock()
    viewport_rect = QRectF(-100.0, -80.0, 200.0, 160.0)
    sheet_rect = QRectF(-20.0, -10.0, 40.0, 20.0)
    monkeypatch.setattr(
        background_painter, "sheet_rect_for", mock.Mock(return_value=sheet_rect)
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
    # With the grid off the painter asks once and draws no lines.
    assert settings.grid_snap_reads == 1
    painter.drawLines.assert_not_called()


def test_draw_canvas_background_draws_square_grid_lines_when_the_grid_is_on(
    monkeypatch,
) -> None:
    canvas = _canvas_with_grid(CanvasToolSettingsState(grid_snap_enabled=True))
    painter = mock.Mock()
    painter.transform.return_value = QTransform()
    sheet_rect = QRectF(0.0, 0.0, 40.0, 30.0)
    monkeypatch.setattr(
        background_painter, "sheet_rect_for", mock.Mock(return_value=sheet_rect)
    )
    monkeypatch.setattr(
        background_painter, "grid_step_for", mock.Mock(return_value=10.0)
    )

    background_painter.draw_canvas_background_for(
        canvas, painter, QRectF(-100.0, -100.0, 400.0, 400.0)
    )

    lines = painter.drawLines.call_args.args[0]
    # 5 columns and 4 rows; intersections match the square snap coordinates.
    assert len(lines) == 9
    points = [point for line in lines for point in (line.p1(), line.p2())]
    assert all(
        sheet_rect.contains(point) or sheet_rect.intersects(QRectF(point, point))
        for point in points
    )
    assert min(point.x() for point in points) == 0.0
    assert max(point.x() for point in points) == 40.0


def test_draw_canvas_background_skips_a_grid_too_dense_to_read(monkeypatch) -> None:
    canvas = _canvas_with_grid(CanvasToolSettingsState(grid_snap_enabled=True))
    painter = mock.Mock()
    dense = (background_painter.MIN_GRID_SPACING_PX / 10.0) * 0.5
    painter.transform.return_value = QTransform().scale(dense, dense)
    monkeypatch.setattr(
        background_painter,
        "sheet_rect_for",
        mock.Mock(return_value=QRectF(0.0, 0.0, 400.0, 300.0)),
    )
    monkeypatch.setattr(
        background_painter, "grid_step_for", mock.Mock(return_value=10.0)
    )

    background_painter.draw_canvas_background_for(
        canvas, painter, QRectF(-100.0, -100.0, 900.0, 900.0)
    )

    painter.drawLines.assert_not_called()
