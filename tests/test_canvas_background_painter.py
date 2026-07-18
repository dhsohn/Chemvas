from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import chemvas.ui.canvas_background_painter as background_painter
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor


def test_draw_canvas_background_paints_workspace_shadow_and_sheet(monkeypatch) -> None:
    canvas = SimpleNamespace()
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
