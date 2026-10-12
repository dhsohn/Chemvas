"""Check actual paint damage before grab() can hide a stale foreground overlay."""

import pytest
from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF
from PyQt6.QtGui import QRegion
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.features.rendering import overvalent_atom_ids
from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas.canvas_document_state import snapshot_canvas_document_state
from chemvas.ui.molecule.structure_mutation_access import add_bond_between_points_for
from chemvas.ui.scene.scene_decoration_access import add_mark_for_atom_for
from chemvas.ui.window.main_window_ports import (
    active_canvas_for_window,
    set_zoom_percent_for_window,
)
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing


def _drain():
    for _ in range(3):
        QApplication.processEvents()
        QTest.qWait(20)


class _PaintDamage(QObject):
    def __init__(self):
        super().__init__()
        self.region = QRegion()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Paint:
            self.region |= event.region()
        return False


def _red_pixels(canvas):
    # grab() repaints the widget: call only before the edit or after recording
    # its real paint events, never as the sole stale-pixel regression assertion.
    image = canvas.viewport().grab().toImage()
    ratio = image.devicePixelRatio()
    item = visible_atom_item_for(canvas, 0)
    bounds = item.sceneBoundingRect() if item is not None else QRectF(-3, -3, 6, 6)
    area = canvas.viewportTransform().mapRect(bounds).adjusted(-10, -10, 10, 12)
    points = set()
    for y in range(
        max(0, int(area.top() * ratio)),
        min(image.height(), round(area.bottom() * ratio)),
    ):
        for x in range(
            max(0, int(area.left() * ratio)),
            min(image.width(), round(area.right() * ratio)),
        ):
            color = image.pixelColor(x, y)
            if color.red() > color.green() + 30 and color.red() > color.blue() + 30:
                points.add((int(x / ratio), int(y / ratio)))
    return points


def _assert_feedback(canvas, expected):
    assert overvalent_atom_ids(canvas.model) == expected
    assert canvas.runtime_state.valence_warnings.warnings_for(canvas.model) == expected
    assert bool(_red_pixels(canvas)) == bool(expected)


def _repair(canvas, kind):
    if kind == "bond_order":
        canvas.services.scene_transform_controller.apply_bond_style(0, "single", 1)
    elif kind == "bond_delete":
        canvas.services.scene_delete_controller.delete_bond(0, record=True)
    elif kind == "element":
        canvas.services.atom_label_service.add_or_update_atom_label(
            0, "C", allow_merge=False
        )
    else:
        add_mark_for_atom_for(canvas, 0, QPointF(12, 12), kind="plus")


@pytest.mark.parametrize("zoom", [50, 180, 400])
@pytest.mark.parametrize("kind", ["bond_order", "bond_delete", "element", "charge"])
def test_repair_repaints_old_warning_and_tracks_history_and_reopen(
    drawing, tmp_path, zoom, kind
):
    window, canvas = drawing
    set_zoom_percent_for_window(window, zoom)
    canvas.centerOn(0, 0)
    # All bonds extend upward. Their dirty rectangles do not contain the wave
    # below the nitrogen label, even though the chemical warning changes.
    for end, order in (
        (QPointF(-40, -30), 2),
        (QPointF(40, -30), 1),
        (QPointF(0, -50), 1),
    ):
        add_bond_between_points_for(
            canvas, QPointF(), end, "double" if order == 2 else "single", order
        )
    canvas.services.atom_label_service.add_or_update_atom_label(
        0, "N", allow_merge=False
    )
    actions = window.services.document_action_service
    invalid_path = tmp_path / "invalid.chemvas"
    assert actions.save_canvas_to_path(window, str(invalid_path))
    invalid_bytes = invalid_path.read_bytes()
    canvas.centerOn(0, 0)
    _drain()
    _assert_feedback(canvas, {0})
    original = snapshot_canvas_document_state(canvas)
    history = canvas.services.history_service
    for operation in (lambda: _repair(canvas, kind), history.redo):
        old_warning = _red_pixels(canvas)
        assert old_warning
        _drain()
        damage = _PaintDamage()
        canvas.viewport().installEventFilter(damage)
        try:
            operation()
            _drain()
        finally:
            canvas.viewport().removeEventFilter(damage)
        assert overvalent_atom_ids(canvas.model) == set()
        uncovered = [
            point for point in old_warning if not damage.region.contains(QPoint(*point))
        ]
        assert not uncovered, (
            f"{len(uncovered)} old warning pixels were never repainted"
        )
        _assert_feedback(canvas, set())
        repaired = snapshot_canvas_document_state(canvas)
        history.undo()
        _drain()
        assert snapshot_canvas_document_state(canvas) == original
        _assert_feedback(canvas, {0})
    history.redo()
    _drain()
    assert snapshot_canvas_document_state(canvas) == repaired
    repaired_path = tmp_path / "repaired.chemvas"
    assert actions.save_canvas_to_path(window, str(repaired_path))
    repaired_bytes = repaired_path.read_bytes()
    for path, expected in ((invalid_path, {0}), (repaired_path, set())):
        assert actions.load_canvas_from_path(window, str(path))
        canvas = active_canvas_for_window(window)
        set_zoom_percent_for_window(window, zoom)
        canvas.centerOn(0, 0)
        _drain()
        _assert_feedback(canvas, expected)
    assert invalid_path.read_bytes() == invalid_bytes
    assert repaired_path.read_bytes() == repaired_bytes
