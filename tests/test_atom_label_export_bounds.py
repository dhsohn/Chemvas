from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter
from PyQt6.QtWidgets import QApplication, QGraphicsRectItem, QGraphicsScene

from chemvas.features.export import content_bounds, item_export_bounds
from chemvas.ui.canvas_geometry_controller import CanvasGeometryController
from chemvas.ui.graphics_items import AtomDotItem, AtomLabelItem


@pytest.fixture(scope="module", autouse=True)
def application() -> QApplication:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    return app


def _label(text: str, *, stacked: bool = False, hit_radius=None) -> AtomLabelItem:
    item = AtomLabelItem(hit_radius=hit_radius)
    item.setData(0, "atom")
    item.setFont(QFont("DejaVu Sans", 12))
    item.setPlainText(text)
    if stacked:
        item.set_stack_anchor("N", hydrogens_below=True)
    item.setPos(17.25, -28.75)
    return item


@pytest.mark.parametrize(
    "text,stacked",
    [("O", False), ("CF3", False), ("CO2Me", False), ("NH4+", False), ("NH", True)],
)
@pytest.mark.parametrize("angle", [0, 37, 90, 180])
def test_atom_export_bounds_follow_all_painted_runs_without_changing_layout(
    text, stacked, angle
):
    label = _label(text, stacked=stacked, hit_radius=40)
    layout_control = _label(text, stacked=stacked)
    for item in (label, layout_control):
        item.setRotation(angle)
        item.setScale(1.25)
    scene = QGraphicsScene()
    scene.addItem(label)
    before = (
        label.boundingRect(),
        label.shape(),
        label.anchor_center(),
        label.toHtml(),
    )
    expected = label.mapToScene(label.glyph_path()).boundingRect()
    assert item_export_bounds(label) == expected
    assert content_bounds([label]) == expected
    # Existing mark clearance deliberately uses layout geometry, not tighter
    # output bounds. A no-hit-halo item is the independent old layout control.
    assert (
        CanvasGeometryController.visible_text_rect(label)
        == layout_control.sceneBoundingRect()
    )
    assert (
        label.boundingRect(),
        label.shape(),
        label.anchor_center(),
        label.toHtml(),
    ) == before


@pytest.mark.parametrize(
    "hidden,opacity,color",
    [(True, 1, "black"), (False, 0, "black"), (False, 1, "transparent")],
)
def test_atom_label_without_paint_has_no_export_extent(hidden, opacity, color):
    label = _label("O")
    label.setVisible(not hidden)
    label.setOpacity(opacity)
    label.setDefaultTextColor(QColor(color))
    assert item_export_bounds(label).isNull()
    assert content_bounds([label]) is None


@pytest.mark.parametrize("opacity", [0.25, 1])
def test_translucent_colored_atom_retains_its_full_geometry(opacity):
    label = _label("O")
    color = QColor("#4488cc")
    color.setAlphaF(opacity)
    label.setDefaultTextColor(color)
    assert (
        item_export_bounds(label) == label.mapToScene(label.glyph_path()).boundingRect()
    )


def test_parent_opacity_and_empty_label_cannot_enlarge_output():
    label = _label("O")
    parent = QGraphicsRectItem()
    label.setParentItem(parent)
    parent.setOpacity(0)
    assert item_export_bounds(label).isNull()
    parent.setOpacity(1)
    label.setPlainText("")
    assert item_export_bounds(label).isNull()


@pytest.mark.parametrize("kind", ["stacked", "dot"])
def test_calculation_number_keeps_existing_layout_clearance(monkeypatch, kind):
    from chemvas.ui import calculation_mapping_highlight as module

    scene = QGraphicsScene()
    if kind == "stacked":
        label = _label("NH", stacked=True)
        old_bounds = label.sceneBoundingRect()
    else:
        label = AtomDotItem(-2, -2, 4, 4)
        label.setBrush(QColor("black"))
        old_bounds = label.export_scene_bounding_rect()
    scene.addItem(label)
    center = label.sceneBoundingRect().center()
    monkeypatch.setattr(module, "atom_center_point_for", lambda *_: center)
    monkeypatch.setattr(module, "atom_pick_radius_for", lambda *_: 6)
    monkeypatch.setattr(module, "visible_atom_item_for", lambda *_: label)
    highlighter = module.CalculationMappingHighlighter(
        SimpleNamespace(scene=lambda: scene)
    )
    highlighter.show_atom_labels({0}, set())
    number = next(
        item for item in scene.items() if item.data(0) == "calculation_atom_id_label"
    )
    assert (
        number.sceneBoundingRect().bottom()
        == min(center.y() - 6, old_bounds.top()) - 2.5
    )
    highlighter.clear_all()


@pytest.mark.parametrize("text,stacked", [("O", False), ("CO2Me", False), ("NH", True)])
def test_tight_atom_bounds_enclose_native_outlined_ink(text, stacked):
    label = _label(text, stacked=stacked)
    label.setRotation(37)
    scene = QGraphicsScene()
    scene.addItem(label)
    source = label.sceneBoundingRect().adjusted(-10, -10, 10, 10)
    scale = 8
    image = QImage(
        round(source.width() * scale),
        round(source.height() * scale),
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.fill(Qt.GlobalColor.transparent)
    label.set_outline_mode(True)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(-source.x() * scale, -source.y() * scale)
    painter.scale(scale, scale)
    scene.render(painter, source, source)
    painter.end()
    label.set_outline_mode(False)
    bounds = item_export_bounds(label)
    assert bounds.width() < label.sceneBoundingRect().width()
    # Raster antialiasing can touch one neighboring physical pixel.
    tolerance = 1 / scale
    painted_bounds = bounds.adjusted(-tolerance, -tolerance, tolerance, tolerance)
    ink = 0
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha():
                ink += 1
                assert painted_bounds.contains(
                    QPointF(source.x() + x / scale, source.y() + y / scale)
                )
    assert ink > 0
