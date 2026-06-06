from types import SimpleNamespace
from unittest import mock

from PyQt6.QtCore import QRectF
from ui.sheet_setup_access import (
    set_sheet_setup_for,
    sheet_orientation_for,
    sheet_rect_for,
    sheet_setup_for,
    sheet_size_for,
)


class _Viewport:
    def __init__(self) -> None:
        self.update = mock.Mock()


def test_sheet_setup_accessors_return_current_sheet_values() -> None:
    canvas = SimpleNamespace(sheet_size="A4", sheet_orientation="landscape")

    assert sheet_setup_for(canvas) == ("A4", "landscape")
    assert sheet_size_for(canvas) == "A4"
    assert sheet_orientation_for(canvas) == "landscape"


def test_set_sheet_setup_updates_scene_rect_and_viewport() -> None:
    viewport = _Viewport()
    canvas = SimpleNamespace(
        sheet_size="A4",
        sheet_orientation="landscape",
        setSceneRect=mock.Mock(),
        viewport=lambda: viewport,
    )

    set_sheet_setup_for(canvas, "A4", "portrait")

    assert sheet_setup_for(canvas) == ("A4", "portrait")
    assert sheet_rect_for(canvas) == QRectF(-297.5, -421.0, 595.0, 842.0)
    canvas.setSceneRect.assert_called_once_with(QRectF(-377.5, -501.0, 755.0, 1002.0))
    viewport.update.assert_called_once_with()
