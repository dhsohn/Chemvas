"""SMILES ghosts use logical widget bounds and physical image/pixmap bounds."""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from PyQt6.QtCore import QPointF, QRectF, QSize
from PyQt6.QtGui import QColor, QImage, QPainter, QPicture, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

from chemvas.domain.document import Atom, Bond, MoleculeModel
from chemvas.ui.canvas_insert_state import insert_state_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.preview_scene_renderer import PREVIEW_OPACITY, SmilesPreviewItem
from chemvas.ui.scene_decoration_access import add_arrow_for
from tests.canvas_factory import build_canvas_view


def _picture():
    picture = QPicture()
    painter = QPainter(picture)
    # Including the preview's one-unit slack, layer bounds land on the
    # physical pixel grid at every tested DPR. Fractional layer-origin
    # rounding is a separate pre-existing behavior, not this clipping fix.
    painter.fillRect(QRectF(-23, -15, 46, 30), QColor("black"))
    painter.end()
    return picture


class _PreviewWidget(QWidget):
    def __init__(self, picture):
        super().__init__()
        self.item = SmilesPreviewItem(picture)
        self.preview_pos = QPointF()
        self.device_was_widget = False
        self.resize(320, 240)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), QColor("white"))
            self.device_was_widget = isinstance(painter.device(), QWidget)
            painter.translate(self.preview_pos)
            self.item.paint(
                painter, SimpleNamespace(exposedRect=self.item.boundingRect()), self
            )
        finally:
            painter.end()


def _reference(size, ratio, picture, position):
    image = QImage(size, QImage.Format.Format_RGB32)
    image.setDevicePixelRatio(ratio)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setOpacity(PREVIEW_OPACITY)
    painter.drawPicture(position, picture)
    painter.end()
    return image


def _device_pixels(ratio):
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    picture = _picture()
    widget = _PreviewWidget(picture)
    widget.show()
    app.processEvents()
    assert widget.devicePixelRatioF() == ratio
    positions = [(64, 48), (160, 120), (256, 48), (64, 192), (256, 192)]
    counts = []
    try:
        for x, y in positions:
            position = QPointF(x, y)
            widget.preview_pos = position
            widget.update()
            app.processEvents()
            actual = widget.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)
            assert widget.device_was_widget
            expected = _reference(actual.size(), ratio, picture, position)
            changed = sum(
                actual.pixelColor(px, py).red() < 240
                for py in range(actual.height())
                for px in range(actual.width())
            )
            counts.append(changed)
            assert actual == expected, (ratio, "widget", (x, y), changed)
            for device_type in (QImage, QPixmap):
                size = QSize(round(320 * ratio), round(240 * ratio))
                device = (
                    QImage(size, QImage.Format.Format_RGB32)
                    if device_type is QImage
                    else QPixmap(size)
                )
                device.setDevicePixelRatio(ratio)
                device.fill(QColor("white"))
                painter = QPainter(device)
                painter.translate(position)
                widget.item.paint(
                    painter, SimpleNamespace(exposedRect=widget.item.boundingRect())
                )
                painter.end()
                actual_image = device if device_type is QImage else device.toImage()
                assert (
                    actual_image.convertToFormat(QImage.Format.Format_RGB32) == expected
                )
        assert len(set(counts)) == 1
    finally:
        widget.close()
        app.processEvents()
    return counts


def _bounded_image_layer(ratio):
    picture = QPicture()
    painter = QPainter(picture)
    painter.fillRect(QRectF(-999, -999, 1998, 1998), QColor("black"))
    painter.end()
    item = SmilesPreviewItem(picture)
    size = QSize(round(320 * ratio), round(240 * ratio))
    image = QImage(size, QImage.Format.Format_RGB32)
    image.setDevicePixelRatio(ratio)
    image.fill(QColor("white"))
    layers = []

    class SpyImage(QImage):
        def __init__(self, size, image_format):
            layers.append(QSize(size))
            super().__init__(size, image_format)

    painter = QPainter(image)
    try:
        with mock.patch("chemvas.ui.preview_scene_renderer.QImage", SpyImage):
            item.paint(painter, SimpleNamespace(exposedRect=item.boundingRect()))
    finally:
        painter.end()
    assert layers and all(
        layer.width() <= size.width() and layer.height() <= size.height()
        for layer in layers
    )
    assert image.pixelColor(image.width() - 1, image.height() - 1).red() < 240


def _canvas_insertion(ratio, *, real_smiles=False):
    app = QApplication.instance() or QApplication([])
    canvas = build_canvas_view()
    canvas.resize(640, 480)
    canvas.show()
    app.processEvents()
    try:
        assert canvas.viewport().devicePixelRatioF() == ratio
        controller = canvas.services.structure.insert_controller
        history = canvas.services.history_service
        add_arrow_for(canvas, QPointF(-80, -70), QPointF(-50, -70), "line")
        add_arrow_for(canvas, QPointF(-80, -50), QPointF(-50, -50), "line")
        history.undo()
        stacks = history.capture_stack_snapshot()
        before = snapshot_canvas_state_for(canvas)
        model = MoleculeModel(
            atoms={0: Atom("C", -12, 0), 1: Atom("O", 12, 0)},
            bonds=[Bond(0, 1)],
        )
        # Conversion is outside this rendering regression; the actual picture,
        # canvas painting, insertion transaction and history are exercised.
        if real_smiles:
            controller.begin_smiles_insert("c1ccccc1C(=O)O")
        else:
            with mock.patch(
                "chemvas.ui.insert_smiles_service.smiles_to_2d_for", return_value=model
            ):
                controller.begin_smiles_insert("CO")
        state = insert_state_for(canvas)
        assert state.smiles_active and len(state.smiles_preview_items) == 1
        model = state.smiles_preview_model
        center = QPointF(state.smiles_preview_center)
        item = state.smiles_preview_items[0]
        position = canvas.mapToScene(
            round(canvas.viewport().width() * 0.8),
            round(canvas.viewport().height() * 0.8),
        )
        controller.render_smiles_preview(position)
        app.processEvents()
        shown = canvas.viewport().grab().toImage()
        item.setVisible(False)
        hidden = canvas.viewport().grab().toImage()
        item.setVisible(True)
        assert shown != hidden, (ratio, "lower-right canvas ghost is invisible")
        assert snapshot_canvas_state_for(canvas) == before
        history.verify_stack_snapshot(stacks)
        controller.commit_smiles_insert(position)
        after = snapshot_canvas_state_for(canvas)
        assert not state.smiles_active
        assert len(canvas.model.atoms) == len(model.atoms)
        for source_id, atom in canvas.model.atoms.items():
            source = model.atoms[source_id]
            assert (atom.x, atom.y) == (
                source.x + (position.x() - center.x()),
                source.y + (position.y() - center.y()),
            )
        history.undo()
        assert snapshot_canvas_state_for(canvas) == before
        history.redo()
        assert snapshot_canvas_state_for(canvas) == after
        return shown
    finally:
        canvas.services.document.canvas_scene_reset_service.clear_scene()
        canvas.close()
        app.processEvents()


@pytest.mark.parametrize("ratio", [1.0, 1.25, 1.5, 2.0])
def test_smiles_preview_real_devices_and_insertion_at_high_dpi(tmp_path, ratio):
    environment = dict(
        os.environ,
        QT_QPA_PLATFORM="offscreen",
        QT_SCALE_FACTOR=str(ratio),
        QT_FONT_DPI="96",
        PYTHONPATH=str(Path(__file__).resolve().parents[1] / "app"),
        XDG_CONFIG_HOME=str(tmp_path / "config"),
        XDG_DATA_HOME=str(tmp_path / "data"),
        XDG_CACHE_HOME=str(tmp_path / "cache"),
    )
    for name in ("QT_SCREEN_SCALE_FACTORS", "QT_AUTO_SCREEN_SCALE_FACTOR"):
        environment.pop(name, None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from tests.test_smiles_preview_high_dpi import "
                "QApplication, _device_pixels, _canvas_insertion, _bounded_image_layer; "
                "app = QApplication([]); "
                f"print(_device_pixels({ratio})); _bounded_image_layer({ratio}); _canvas_insertion({ratio})"
            ),
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(json.loads(result.stdout.strip())) == 5
