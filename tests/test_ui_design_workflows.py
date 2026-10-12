from unittest import mock

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QImage, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QToolButton

from chemvas.shell.icon_factory import MainWindowIconFactory
from chemvas.shell.palette import PALETTE
from chemvas.ui.canvas.canvas_document_state import snapshot_canvas_document_state
from chemvas.ui.canvas.canvas_feedback_renderer import draw_canvas_feedback_for
from chemvas.ui.molecule.structure_mutation_access import add_bond_between_points_for
from chemvas.ui.window.main_window_ports import (
    set_grid_snap_for_window,
)
from tests.gui_workflow_support import _tool
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing


def test_checked_icon_uses_teal_without_changing_its_shape(app):
    icon = MainWindowIconFactory(object()).icon_bond()
    for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected):
        off = icon.pixmap(20, 20, mode, QIcon.State.Off).toImage()
        on = icon.pixmap(20, 20, mode, QIcon.State.On).toImage()
        colors = set()
        for y in range(on.height()):
            for x in range(on.width()):
                assert on.pixelColor(x, y).alpha() == off.pixelColor(x, y).alpha()
                if on.pixelColor(x, y).alpha() == 255:
                    colors.add(on.pixelColor(x, y).name())
        assert colors == {PALETTE["checked_text"]}


def test_grid_controls_cycle_and_preserve_the_document(drawing):
    window, canvas = drawing
    before = snapshot_canvas_document_state(canvas)
    button = window.findChild(QToolButton, "statusGridButton")
    settings = canvas.runtime_state.tool_settings_state
    for text, enabled, style in (
        ("Grid: Hex", True, "hex"),
        ("Grid: Square", True, "square"),
        ("Grid: None", False, "square"),
    ):
        button.click()
        assert button.text() == text
        assert (settings.grid_snap_enabled, settings.grid_style) == (enabled, style)
    next(a for a in button.menu().actions() if a.text() == "Strength 15%").trigger()
    assert settings.grid_opacity == 0.15
    assert snapshot_canvas_document_state(canvas) == before
    assert not canvas.services.history_service.can_undo()


def test_grid_and_valence_controls_follow_the_active_canvas(drawing):
    window, first = drawing
    grid = window.findChild(QToolButton, "statusGridButton")
    valence = window.findChild(QAction, "valenceCheckingAction")
    grid.click()
    valence.trigger()
    second = window.services.canvas_document_service.new_canvas(window)
    QApplication.processEvents()
    assert grid.text() == "Grid: None"
    assert second.runtime_state.tool_settings_state.valence_checking
    set_grid_snap_for_window(window, True)
    assert grid.text() == "Grid: Square"
    window.tab_references.canvas_tabs.setCurrentIndex(0)
    QApplication.processEvents()
    assert grid.text() == "Grid: Hex"
    assert not first.runtime_state.tool_settings_state.valence_checking


def _scene_image(canvas):
    image = QImage(600, 400, QImage.Format.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    canvas.scene().render(painter)
    painter.end()
    return image


def _red_pixels_near_origin(canvas):
    image = canvas.viewport().grab().toImage()
    center = canvas.mapFromScene(QPointF(0, 0))
    scale = image.devicePixelRatio()
    region = QRectF(center.x() - 30, center.y() - 20, 60, 40)
    return sum(
        color.red() > color.green() + 30 and color.red() > color.blue() + 30
        for y in range(round(region.top() * scale), round(region.bottom() * scale))
        for x in range(round(region.left() * scale), round(region.right() * scale))
        for color in (image.pixelColor(x, y),)
    )


def test_valence_overlay_is_visible_but_absent_from_document_and_scene_export(drawing):
    window, canvas = drawing
    for endpoint in (
        QPointF(30, 0),
        QPointF(-30, 0),
        QPointF(0, 30),
        QPointF(0, -30),
        QPointF(30, 30),
    ):
        add_bond_between_points_for(canvas, QPointF(0, 0), endpoint)
    before = snapshot_canvas_document_state(canvas)
    exported = _scene_image(canvas)
    QApplication.processEvents()
    flagged = canvas.viewport().grab().toImage()
    assert _red_pixels_near_origin(canvas) > 0
    action = window.findChild(QAction, "valenceCheckingAction")
    action.trigger()
    QApplication.processEvents()
    plain = canvas.viewport().grab().toImage()
    assert plain != flagged
    assert _red_pixels_near_origin(canvas) == 0
    assert _scene_image(canvas) == exported
    assert snapshot_canvas_document_state(canvas) == before
    action.trigger()
    assert canvas.runtime_state.tool_settings_state.valence_checking
    canvas.services.history_service.undo()
    QApplication.processEvents()
    assert _red_pixels_near_origin(canvas) == 0
    canvas.services.history_service.redo()
    QApplication.processEvents()
    assert _red_pixels_near_origin(canvas) > 0


def test_bond_angle_guide_clears_on_release_and_escape(drawing):
    window, canvas = drawing
    _tool(window, "bond")
    tool = canvas.services.tool_controller.active
    start = canvas.mapFromScene(QPointF(-60, -30))
    end = canvas.mapFromScene(QPointF(-70, -47.3205))
    for finish in ("release", "escape"):
        if finish == "escape":
            end = canvas.mapFromScene(QPointF(-50, -47.3205))
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(canvas.viewport(), end)
        QApplication.processEvents()
        assert tool.angle_guide is not None
        painter = mock.Mock()
        painter.worldTransform.return_value = canvas.viewportTransform()
        painter.font.return_value = canvas.font()
        draw_canvas_feedback_for(canvas, painter, canvas.sceneRect())
        assert painter.drawText.call_args.args[-1] == (
            "120°" if finish == "release" else "60°"
        )
        assert painter.drawText.call_args.args[0].size().width() == 38
        # The bond ghost is unchanged when the view-only guide is hidden.
        exported = _scene_image(canvas)
        with mock.patch.object(
            type(tool), "angle_guide", new_callable=mock.PropertyMock, return_value=None
        ):
            assert _scene_image(canvas) == exported
        if finish == "release":
            QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
        else:
            QTest.keyClick(canvas, Qt.Key.Key_Escape)
            QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
        assert tool.angle_guide is None
