from unittest import mock

import pytest
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QImage, QPainter, QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDockWidget, QLineEdit, QToolButton

from chemvas.shell.icon_factory import MainWindowIconFactory
from chemvas.shell.palette import PALETTE
from chemvas.ui.canvas_document_state import snapshot_canvas_document_state
from chemvas.ui.canvas_feedback_renderer import draw_canvas_feedback_for
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.main_window_ports import (
    insert_controller_for_window,
    preview_for_window,
    select_all_for_window,
    services_for_window,
    set_grid_snap_for_window,
)
from chemvas.ui.preview_3d_state import preview_info_items
from chemvas.ui.structure_mutation_access import add_bond_between_points_for
from tests.gui_workflow_support import _click, _tool
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing


@pytest.mark.parametrize(
    "tool", ["bond", "benzene", "arrow", "select", "note", "delete"]
)
def test_quick_smiles_survives_tool_changes_in_compact_window(drawing, tool):
    window, _canvas = drawing
    window.resize(1000, 700)
    field = window.findChild(QLineEdit, "contextSmilesInput")
    field.setText("CCO")
    _tool(window, tool)
    QApplication.processEvents()
    assert field.isVisibleTo(window)
    assert field.text() == "CCO"
    controller = insert_controller_for_window(window)
    with mock.patch.object(controller, "begin_smiles_insert") as insert:
        field.setFocus()
        QTest.keyClick(field, Qt.Key.Key_Return)
        insert.assert_called_once_with("CCO")


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


def test_inspector_toggle_float_and_close_keep_one_preview(drawing):
    window, _canvas = drawing
    dock = window.findChild(QDockWidget, "inspectorDock")
    button = window.findChild(QToolButton, "inspectorToggleButton")
    preview = preview_for_window(window)
    assert not dock.isVisible()
    button.click()
    QApplication.processEvents()
    assert dock.isVisible() and button.isChecked()
    assert not preview._updates_paused
    dock.setFloating(True)
    QApplication.processEvents()
    assert dock.isFloating()
    assert preview.isVisible()
    dock.close()
    QApplication.processEvents()
    assert not button.isChecked() and preview._updates_paused
    button.click()
    dock.setFloating(False)
    assert window.findChildren(type(preview)) == [preview]


def test_grid_controls_cycle_and_preserve_the_document(drawing):
    window, canvas = drawing
    before = snapshot_canvas_document_state(canvas)
    button = window.findChild(QToolButton, "statusGridButton")
    settings = tool_settings_state_for(canvas)
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


def test_long_export_status_does_not_expand_the_inspector(drawing):
    window, _canvas = drawing
    window.findChild(QToolButton, "inspectorToggleButton").click()
    QApplication.processEvents()
    dock = window.findChild(QDockWidget, "inspectorDock")
    width = dock.width()
    dock.show_export_status(
        "Exported XYZ: /Users/researcher/projects/reaction-study-2026/"
        "exports/calculations/candidate-structure-final.xyz"
    )
    QApplication.processEvents()
    assert dock.width() == width


def test_grid_and_valence_controls_follow_the_active_canvas(drawing):
    window, first = drawing
    grid = window.findChild(QToolButton, "statusGridButton")
    valence = window.findChild(QAction, "valenceCheckingAction")
    grid.click()
    valence.trigger()
    second = services_for_window(window).canvas_document_service.new_canvas(window)
    QApplication.processEvents()
    assert grid.text() == "Grid: None"
    assert tool_settings_state_for(second).valence_checking
    set_grid_snap_for_window(window, True)
    assert grid.text() == "Grid: Square"
    window.tab_references.canvas_tabs.setCurrentIndex(0)
    QApplication.processEvents()
    assert grid.text() == "Grid: Hex"
    assert not tool_settings_state_for(first).valence_checking


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
    assert tool_settings_state_for(canvas).valence_checking
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


def test_smiles_enter_places_and_inspects_real_molecule_then_exports_xyz(
    drawing, tmp_path, monkeypatch
):
    pytest.importorskip("rdkit")
    window, canvas = drawing
    _tool(window, "arrow")
    field = window.findChild(QLineEdit, "contextSmilesInput")
    field.setText("CC(=O)Oc1ccccc1C(=O)O")
    field.setFocus()
    QTest.keyClick(field, Qt.Key.Key_Return)
    assert not canvas.model.atoms
    _click(canvas, QPointF(0, 0))
    assert len(canvas.model.atoms) == 13
    select_all_for_window(window)
    window.findChild(QToolButton, "inspectorToggleButton").click()
    preview = preview_for_window(window)
    for _ in range(300):
        QTest.qWait(50)
        if preview._scene is not None:
            break
    assert preview._scene is not None, preview._message
    assert preview_info_items(
        preview._formula_text, preview._mw_text, preview._scene
    ) == [
        ("FORMULA", "C9H8O4"),
        ("MW", "180.16"),
        ("ATOMS (incl. H)", "21"),
        ("INDEP. RINGS", "1"),
        ("STYLE", "ACS 1996"),
    ]
    before = preview.grab().toImage()
    orientation = (preview._rotation_x, preview._rotation_y)
    point = preview.rect().center()
    QTest.mousePress(preview, Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseMove(preview, point + QPoint(24, 16))
    QTest.mouseRelease(preview, Qt.MouseButton.LeftButton, pos=point + QPoint(24, 16))
    assert (preview._rotation_x, preview._rotation_y) != orientation
    QApplication.sendEvent(
        preview,
        QWheelEvent(
            QPointF(point),
            QPointF(preview.mapToGlobal(point)),
            QPoint(),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        ),
    )
    assert preview._zoom == pytest.approx(1.1)
    assert preview.grab().toImage() != before
    path = tmp_path / "aspirin.xyz"
    monkeypatch.setattr(
        "chemvas.ui.main_window_document_action_service.QFileDialog.getSaveFileName",
        lambda *_args: (str(path), "XYZ (*.xyz)"),
    )
    errors = []
    monkeypatch.setattr(
        "chemvas.ui.main_window_document_action_service.QMessageBox.warning",
        lambda *_args: errors.append(_args),
    )
    preview.export_xyz_button.click()
    for _ in range(300):
        QTest.qWait(50)
        if path.exists() or errors:
            break
    assert not errors
    lines = path.read_text().splitlines()
    assert lines[0].strip() == "21"
    assert len(lines[2:]) == 21
