import os
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chemvas.ui.sheet_setup_access import (
    scene_pos_in_sheet_for,
    set_sheet_setup_for,
    sheet_orientation_for,
    sheet_rect_for,
    sheet_setup_for,
    sheet_size_for,
)
from chemvas.ui.sheet_setup_state import sheet_setup_state_for
from chemvas.ui.transactions.scene_rect import (
    scene_rect_is_automatic,
    view_scene_rect_is_explicit,
)
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView

_APP = QApplication.instance() or QApplication([])
_APP.setQuitOnLastWindowClosed(False)


class _Viewport:
    def __init__(self) -> None:
        self.update = mock.Mock()


def _qt_sheet_canvas() -> tuple[QGraphicsView, QGraphicsScene]:
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    canvas = QGraphicsView(scene)
    set_sheet_setup_for(canvas, "A4", "landscape")
    return canvas, scene


def _tracker_signature(scene: QGraphicsScene):
    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    if tracker is None:
        return None
    return (
        tracker,
        QRectF(tracker.known_rect),
        QRectF(tracker.baseline_rect),
        QRectF(tracker.pending_rect),
        tracker.pending_expansions,
        tuple((key, QRectF(rect)) for key, rect in tracker.pending_expansions.items()),
        tracker.pending_journal,
        tuple(
            (
                key,
                existed,
                QRectF(previous) if previous is not None else None,
            )
            for key, existed, previous in tracker.pending_journal
        ),
        tracker.depth,
        tracker.internal_change,
    )


def _sheet_configuration(canvas: QGraphicsView, scene: QGraphicsScene):
    state = sheet_setup_state_for(canvas)
    return (
        state,
        state.size_name,
        state.orientation,
        state.rect,
        QRectF(state.rect),
        canvas.sheet_size,
        canvas.sheet_orientation,
        QRectF(canvas.sceneRect()),
        view_scene_rect_is_explicit(canvas),
        QRectF(scene.sceneRect()),
        scene_rect_is_automatic(scene),
        _tracker_signature(scene),
    )


def _assert_sheet_configuration(
    canvas: QGraphicsView,
    scene: QGraphicsScene,
    expected,
) -> None:
    actual = _sheet_configuration(canvas, scene)
    assert actual[0] is expected[0]
    assert actual[1:3] == expected[1:3]
    assert actual[3] is expected[3]
    assert actual[4:11] == expected[4:11]
    actual_tracker = actual[11]
    expected_tracker = expected[11]
    if expected_tracker is None:
        assert actual_tracker is None
        return
    assert actual_tracker is not None
    assert actual_tracker[0] is expected_tracker[0]
    assert actual_tracker[1:4] == expected_tracker[1:4]
    assert actual_tracker[4] is expected_tracker[4]
    assert actual_tracker[5] == expected_tracker[5]
    assert actual_tracker[6] is expected_tracker[6]
    assert actual_tracker[7:] == expected_tracker[7:]


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


def test_scene_pos_in_sheet_uses_configured_sheet_rect_and_allows_uninitialized_rect() -> (
    None
):
    canvas = SimpleNamespace(sheet_size="A4", sheet_orientation="landscape")

    assert scene_pos_in_sheet_for(canvas, QPointF(999.0, 999.0))

    configured = SimpleNamespace(
        sheet_size="A4",
        sheet_orientation="landscape",
        setSceneRect=mock.Mock(),
        viewport=lambda: _Viewport(),
    )
    set_sheet_setup_for(configured, "A4", "landscape")

    assert scene_pos_in_sheet_for(configured, QPointF(0.0, 0.0))
    assert not scene_pos_in_sheet_for(configured, QPointF(999.0, 999.0))
