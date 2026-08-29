import os
from types import SimpleNamespace
from unittest import mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView

from chemvas.ui.sheet_setup_access import (
    scene_pos_in_sheet_for,
    set_sheet_setup_for,
    sheet_orientation_for,
    sheet_rect_for,
    sheet_setup_for,
    sheet_size_for,
)
from chemvas.ui.sheet_setup_state import SheetSetupState, sheet_setup_state_for
from chemvas.ui.transactions.scene_rect import (
    SceneRectSnapshot,
    scene_rect_is_automatic,
    view_scene_rect_is_explicit,
)
from tests.runtime_state import canvas_runtime_state

_APP = QApplication.instance() or QApplication([])
_APP.setQuitOnLastWindowClosed(False)


class _Viewport:
    def __init__(self) -> None:
        self.update = mock.Mock()


def _qt_sheet_canvas() -> tuple[QGraphicsView, QGraphicsScene]:
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    canvas = QGraphicsView(scene)
    canvas.runtime_state = canvas_runtime_state(sheet_setup_state=SheetSetupState())
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
    assert actual[3] == expected[3]
    assert actual[4:9] == expected[4:9]
    actual_tracker = actual[9]
    expected_tracker = expected[9]
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
    canvas = SimpleNamespace(
        runtime_state=canvas_runtime_state(
            sheet_setup_state=SheetSetupState(size_name="A4", orientation="landscape")
        )
    )

    assert sheet_setup_for(canvas) == ("A4", "landscape")
    assert sheet_size_for(canvas) == "A4"
    assert sheet_orientation_for(canvas) == "landscape"


def test_set_sheet_setup_updates_scene_rect_and_viewport() -> None:
    canvas, scene = _qt_sheet_canvas()

    set_sheet_setup_for(canvas, "A4", "portrait")

    assert sheet_setup_for(canvas) == ("A4", "portrait")
    assert sheet_rect_for(canvas) == QRectF(-297.5, -421.0, 595.0, 842.0)
    expected_scene_rect = QRectF(-377.5, -501.0, 755.0, 1002.0)
    assert scene.sceneRect() == expected_scene_rect
    assert canvas.sceneRect() == expected_scene_rect
    canvas.close()


def test_scene_pos_in_sheet_uses_configured_sheet_rect_and_allows_uninitialized_rect() -> (
    None
):
    canvas = SimpleNamespace(
        runtime_state=canvas_runtime_state(sheet_setup_state=SheetSetupState())
    )

    assert scene_pos_in_sheet_for(canvas, QPointF(999.0, 999.0))

    configured = SimpleNamespace(
        runtime_state=canvas_runtime_state(sheet_setup_state=SheetSetupState()),
        viewport=lambda: _Viewport(),
    )
    set_sheet_setup_for(configured, "A4", "landscape")

    assert scene_pos_in_sheet_for(configured, QPointF(0.0, 0.0))
    assert not scene_pos_in_sheet_for(configured, QPointF(999.0, 999.0))


def test_sheet_setup_viewport_failure_restores_state_rect_modes_and_tracker() -> None:
    canvas, scene = _qt_sheet_canvas()
    tracker_snapshot = SceneRectSnapshot.capture(scene)
    assert tracker_snapshot is not None
    tracker_snapshot.release()
    tracker = tracker_snapshot.tracker
    expansion_key = id(object())
    pending_expansions = tracker.pending_expansions
    pending_journal = tracker.pending_journal
    pending_expansions[expansion_key] = QRectF(1.0, 2.0, 3.0, 4.0)
    pending_journal.append((expansion_key, False, None))
    tracker.pending_rect = QRectF(-20.0, -30.0, 40.0, 60.0)
    before = _sheet_configuration(canvas, scene)
    primary = RuntimeError("sheet viewport update failed")
    expected_scene_rect = QRectF(-377.5, -501.0, 755.0, 1002.0)

    def fail_after_mutation() -> None:
        assert sheet_setup_for(canvas) == ("A4", "portrait")
        assert sheet_rect_for(canvas) == QRectF(-297.5, -421.0, 595.0, 842.0)
        assert scene.sceneRect() == expected_scene_rect
        assert canvas.sceneRect() == expected_scene_rect
        raise primary

    failing_viewport = SimpleNamespace(
        update=mock.Mock(side_effect=fail_after_mutation)
    )
    with (
        mock.patch.object(canvas, "viewport", return_value=failing_viewport),
        pytest.raises(RuntimeError, match=str(primary)) as raised,
    ):
        set_sheet_setup_for(canvas, "A4", "portrait")

    assert raised.value is primary
    _assert_sheet_configuration(canvas, scene, before)
    assert tracker.pending_expansions is pending_expansions
    assert tracker.pending_journal is pending_journal
    canvas.close()
