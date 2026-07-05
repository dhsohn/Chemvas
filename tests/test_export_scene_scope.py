from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QRectF
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsItemGroup,
        QGraphicsRectItem,
        QGraphicsScene,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.export_scene_scope import (
        collect_export_items,
        content_bounds,
        export_item_closure,
        exported_scene,
        item_export_bounds,
        set_label_outline_mode,
    )


class _OutlineRectItem(QGraphicsRectItem):
    def __init__(self, rect: QRectF) -> None:
        super().__init__(rect)
        self.outline_modes: list[bool] = []

    def set_outline_mode(self, enabled: bool) -> None:
        self.outline_modes.append(enabled)


class _ExportBoundsRectItem(QGraphicsRectItem):
    def export_scene_bounding_rect(self) -> QRectF:
        return QRectF(2.0, 3.0, 4.0, 5.0)


def test_export_scene_scope_filters_visible_content_and_bounds() -> None:
    app = QApplication.instance() or QApplication([])
    scene = QGraphicsScene()
    content = QGraphicsRectItem(0.0, 0.0, 10.0, 10.0)
    content.setData(0, "atom")
    hidden = QGraphicsRectItem(20.0, 0.0, 10.0, 10.0)
    hidden.setData(0, "bond")
    hidden.setVisible(False)
    overlay = QGraphicsRectItem(0.0, 0.0, 5.0, 5.0)
    overlay.setData(0, "selection_outline")
    scene.addItem(content)
    scene.addItem(hidden)
    scene.addItem(overlay)

    assert collect_export_items(scene) == [content]
    assert content_bounds([content]) == content.sceneBoundingRect()
    assert app is not None


def test_export_scene_scope_prefers_custom_export_bounds() -> None:
    item = _ExportBoundsRectItem(0.0, 0.0, 100.0, 100.0)

    assert item_export_bounds(item) == QRectF(2.0, 3.0, 4.0, 5.0)


def test_exported_scene_hides_non_export_items_and_restores_outline_mode() -> None:
    app = QApplication.instance() or QApplication([])
    scene = QGraphicsScene()
    export_item = _OutlineRectItem(QRectF(0.0, 0.0, 10.0, 10.0))
    hidden_item = QGraphicsRectItem(20.0, 0.0, 10.0, 10.0)
    scene.addItem(export_item)
    scene.addItem(hidden_item)

    assert set_label_outline_mode([hidden_item], True) == []

    with exported_scene(scene, [export_item]):
        assert export_item.isVisible()
        assert not hidden_item.isVisible()
        assert export_item.outline_modes == [True]

    assert hidden_item.isVisible()
    assert export_item.outline_modes == [True, False]
    assert app is not None


def test_exported_scene_keeps_export_item_descendants_visible() -> None:
    app = QApplication.instance() or QApplication([])
    scene = QGraphicsScene()
    group = QGraphicsItemGroup()
    group.setData(0, "orbital")
    child = QGraphicsRectItem(0.0, 0.0, 10.0, 10.0)
    group.addToGroup(child)
    unrelated = QGraphicsRectItem(20.0, 0.0, 10.0, 10.0)
    scene.addItem(group)
    scene.addItem(unrelated)

    assert export_item_closure([group]) == [group, child]

    with exported_scene(scene, [group]):
        assert group.isVisible()
        assert child.isVisible()
        assert not unrelated.isVisible()

    assert unrelated.isVisible()
    assert app is not None
