import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QGraphicsEllipseItem, QGraphicsScene

from chemvas.ui.canvas.canvas_scene_items_state import CanvasSceneItemsState
from chemvas.ui.tools.handle_overlay_service import HandleOverlayService
from chemvas.ui.tools.handle_state import CanvasHandleState


class _FakeGraphicsItem:
    def __init__(
        self, rect: QRectF | None = None, *, data=None, pen: QPen | None = None
    ) -> None:
        self._data = dict(data or {})
        self._rect = QRectF(rect or QRectF(0.0, 0.0, 20.0, 10.0))
        self._pen = QPen(pen or QPen(QColor("#444444")))
        self._path = QPainterPath()

    def data(self, key):
        return self._data.get(key)

    def setData(self, key, value) -> None:
        self._data[key] = value

    def boundingRect(self) -> QRectF:
        return QRectF(self._rect)

    def pen(self) -> QPen:
        return QPen(self._pen)

    def setPen(self, pen: QPen) -> None:
        self._pen = QPen(pen)

    def setPath(self, path: QPainterPath) -> None:
        self._path = QPainterPath(path)

    def path(self) -> QPainterPath:
        return QPainterPath(self._path)


class HandleOverlayServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _make_canvas(self, scene: QGraphicsScene, *, bond_length_px: float = 40.0):
        def update_curved_control(item, mid: QPointF) -> None:
            data = item.data(2) or {}
            start = data.get("start")
            end = data.get("end")
            if isinstance(start, QPointF) and isinstance(end, QPointF):
                data["control"] = QPointF(
                    2.0 * mid.x() - 0.5 * (start.x() + end.x()),
                    2.0 * mid.y() - 0.5 * (start.y() + end.y()),
                )
                item.setData(2, data)

        canvas = SimpleNamespace(
            scene=lambda: scene,
            renderer=SimpleNamespace(
                style=SimpleNamespace(bond_length_px=bond_length_px)
            ),
            runtime_state=canvas_runtime_state(
                handle_state=CanvasHandleState(),
                scene_items_state=CanvasSceneItemsState(),
            ),
            services=canvas_runtime_services(
                handle_mutation_service=SimpleNamespace(
                    update_curved_control=mock.Mock(side_effect=update_curved_control)
                ),
            ),
        )
        return canvas

    def test_clear_handles_removes_items_and_resets_target(self) -> None:
        scene = QGraphicsScene()
        canvas = self._make_canvas(scene)
        handle_a = QGraphicsEllipseItem(0.0, 0.0, 4.0, 4.0)
        handle_b = QGraphicsEllipseItem(5.0, 0.0, 4.0, 4.0)
        scene.addItem(handle_a)
        scene.addItem(handle_b)
        canvas.runtime_state.handle_state.active_handles = [handle_a, handle_b]
        canvas.runtime_state.handle_state.target = object()

        HandleOverlayService(canvas).clear_handles()

        self.assertEqual(canvas.runtime_state.handle_state.active_handles, [])
        self.assertIsNone(canvas.runtime_state.handle_state.target)
        self.assertIsNone(handle_a.scene())
        self.assertIsNone(handle_b.scene())

    def test_create_handle_adds_item_to_scene(self) -> None:
        scene = QGraphicsScene()
        canvas = self._make_canvas(scene)

        handle = HandleOverlayService(canvas).create_handle(
            QPointF(3.0, 4.0), "orbital_scale", "target"
        )

        self.assertIs(handle.scene(), scene)
        self.assertEqual(handle.data(0), "handle")
        self.assertEqual(handle.data(1), "orbital_scale")
        self.assertEqual(handle.data(2), "target")

    def test_show_orbital_handles_highlights_target_and_uses_center_or_bounds(
        self,
    ) -> None:
        scene = QGraphicsScene()
        canvas = self._make_canvas(scene)
        service = HandleOverlayService(canvas)
        item = _FakeGraphicsItem(
            data={1: {"center": QPointF(10.0, 20.0), "base_handle_dist": 7.0}}
        )

        service.show_orbital_handles(item)

        self.assertIs(canvas.runtime_state.handle_state.target, item)
        self.assertEqual(len(canvas.runtime_state.handle_state.active_handles), 2)
        self.assertEqual(
            [
                (handle.pos().x(), handle.pos().y())
                for handle in canvas.runtime_state.handle_state.active_handles
            ],
            [(17.0, 20.0), (10.0, 13.0)],
        )

        fallback = _FakeGraphicsItem(rect=QRectF(0.0, 0.0, 20.0, 10.0), data={1: {}})
        service.show_orbital_handles(fallback)
        self.assertEqual(
            [
                (handle.pos().x(), handle.pos().y())
                for handle in canvas.runtime_state.handle_state.active_handles
            ],
            [(42.0, 5.0), (10.0, -27.0)],
        )
