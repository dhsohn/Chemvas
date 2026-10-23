import os
import xml.etree.ElementTree as ET
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGraphicsItem,
    QGraphicsRectItem,
    QLabel,
    QPushButton,
)

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.export.figure_export_service import FigureExportService
from chemvas.ui.window.main_window_document_dialogs import prompt_export_options
from chemvas.ui.window.main_window_ports import active_canvas_for_window


@pytest.fixture
def drawing():
    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    canvas = active_canvas_for_window(window)
    scene = canvas.render_context.scene
    items = []
    for x, color in ((0, "red"), (200, "blue")):
        item = QGraphicsRectItem(x, 0, 100, 50)
        item.setData(0, "shape")
        item.setBrush(QColor(color))
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        scene.addItem(item)
        items.append(item)
    yield window, canvas, items
    window.services.canvas_document_service.mark_clean(canvas)
    window.close()
    app.processEvents()


def test_preview_uses_export_scope_and_restores_scene(drawing, tmp_path):
    _, canvas, items = drawing
    service = FigureExportService(canvas.render_context)
    items[0].setSelected(True)
    before = [(item.isVisible(), item.isSelected()) for item in items]
    preview, plan = service.preview_figure_export(
        scope="selection", selection=[items[0]], sizing="col1", background="white"
    )
    assert preview.width() <= 720 and preview.height() <= 480
    assert [(item.isVisible(), item.isSelected()) for item in items] == before
    assert preview.pixelColor(preview.width() // 2, preview.height() // 2).red() > 240
    assert preview.pixelColor(preview.width() // 2, preview.height() // 2).blue() < 20
    path = tmp_path / "selection.png"
    exported = service.export_figure(
        str(path),
        fmt="png",
        scope="selection",
        selection=[items[0]],
        sizing="col1",
        background="white",
    )
    assert exported == plan
    assert not QImage(str(path)).isNull()
    transparent, _ = service.preview_figure_export(
        scope="selection", selection=[items[0]]
    )
    assert transparent.pixelColor(0, 0).alpha() == 0


def test_preview_size_matches_written_svg_and_raster(drawing, tmp_path):
    window, canvas, _ = drawing
    service = FigureExportService(canvas.render_context)

    def drive(dialog):
        fmt = dialog.findChild(QComboBox, "exportFormatCombo")
        size = dialog.findChild(QComboBox, "exportSizeCombo")
        dimensions = dialog.findChild(QLabel, "exportDimensions")
        size.setCurrentIndex(size.findData("col1"))
        svg = tmp_path / "figure.svg"
        service.export_figure(str(svg), sizing="col1")
        attrs = ET.parse(svg).getroot().attrib
        width = float(attrs["width"].removesuffix("mm"))
        height = float(attrs["height"].removesuffix("mm"))
        assert f"{width:.2f} × {height:.2f} mm" in dimensions.text()
        fmt.setCurrentIndex(fmt.findData("png"))
        png = tmp_path / "figure.png"
        service.export_figure(str(png), fmt="png", sizing="col1", dpi=300)
        image = QImage(str(png))
        assert f"{image.width()} × {image.height()} px" in dimensions.text()
        assert dialog.findChild(QLabel, "exportPreview").pixmap() is not None
        return QDialog.DialogCode.Rejected

    with patch.object(QDialog, "exec", drive):
        assert prompt_export_options(window) is None
    assert window.runtime_state.last_export_options is None


def test_visible_limits_and_empty_selection_prevent_invalid_export(drawing):
    window, _, _ = drawing

    def drive(dialog):
        assert dialog.findChild(QCheckBox, "exportMaxHeightCheck").isHidden() is False
        assert dialog.findChild(QCheckBox, "exportMinFontCheck").isHidden() is False
        export = next(
            b for b in dialog.findChildren(QPushButton) if b.text() == "Export"
        )
        assert export.isEnabled()
        scope = dialog.findChild(QComboBox, "exportScopeCombo")
        scope.setCurrentIndex(scope.findData("selection"))
        assert not export.isEnabled()
        assert "Select something" in dialog.findChild(QLabel, "exportPreview").text()
        assert dialog.findChild(QLabel, "exportDimensions").text() == ""
        scope.setCurrentIndex(scope.findData("sheet"))
        assert export.isEnabled()
        dialog.findChild(QDoubleSpinBox, "exportMaxHeightSpin").setValue(0.01)
        dialog.findChild(QCheckBox, "exportMaxHeightCheck").setChecked(True)
        assert not export.isEnabled()
        dialog.findChild(QCheckBox, "exportMaxHeightCheck").setChecked(False)
        assert export.isEnabled()
        return QDialog.DialogCode.Rejected

    with patch.object(QDialog, "exec", drive):
        prompt_export_options(window)


def test_blank_canvas_shows_empty_state():
    app = QApplication.instance() or QApplication([])
    window = build_main_window()

    def drive(dialog):
        assert "nothing to export" in dialog.findChild(QLabel, "exportPreview").text()
        export = next(
            b for b in dialog.findChildren(QPushButton) if b.text() == "Export"
        )
        assert not export.isEnabled()
        return QDialog.DialogCode.Rejected

    with patch.object(QDialog, "exec", drive):
        prompt_export_options(window)
    window.close()
    app.processEvents()
