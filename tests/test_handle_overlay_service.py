import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import QColor, QPainterPath, QPen
    from PyQt6.QtWidgets import QApplication, QGraphicsEllipseItem, QGraphicsScene
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from ui.handle_overlay_service import HandleOverlayService


class _FakeGraphicsItem:
    def __init__(self, rect: QRectF | None = None, *, data=None, pen: QPen | None = None) -> None:
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


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for handle overlay service tests")
class HandleOverlayServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _make_canvas(self, scene: QGraphicsScene, *, bond_length_px: float = 40.0):
        canvas = SimpleNamespace(
            scene=lambda: scene,
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=bond_length_px)),
            _active_handles=[],
            _handle_target=None,
            _clear_selection_highlight=mock.Mock(),
            _set_selection_highlight=mock.Mock(),
            _default_curved_control=mock.Mock(return_value=QPointF(5.0, 3.0)),
            _curved_midpoint=mock.Mock(side_effect=lambda start, control, end: QPointF(5.0, 4.0)),
            _update_curved_control=mock.Mock(),
        )
        return canvas

    def test_clear_handles_removes_items_and_resets_target(self) -> None:
        scene = QGraphicsScene()
        canvas = self._make_canvas(scene)
        handle_a = QGraphicsEllipseItem(0.0, 0.0, 4.0, 4.0)
        handle_b = QGraphicsEllipseItem(5.0, 0.0, 4.0, 4.0)
        scene.addItem(handle_a)
        scene.addItem(handle_b)
        canvas._active_handles = [handle_a, handle_b]
        canvas._handle_target = object()

        HandleOverlayService(canvas).clear_handles()

        self.assertEqual(canvas._active_handles, [])
        self.assertIsNone(canvas._handle_target)
        self.assertIsNone(handle_a.scene())
        self.assertIsNone(handle_b.scene())
        canvas._clear_selection_highlight.assert_called_once_with()

    def test_create_handle_adds_item_to_scene(self) -> None:
        scene = QGraphicsScene()
        canvas = self._make_canvas(scene)

        handle = HandleOverlayService(canvas).create_handle(QPointF(3.0, 4.0), "orbital_scale", "target")

        self.assertIs(handle.scene(), scene)
        self.assertEqual(handle.data(0), "handle")
        self.assertEqual(handle.data(1), "orbital_scale")
        self.assertEqual(handle.data(2), "target")

    def test_show_orbital_handles_highlights_target_and_uses_center_or_bounds(self) -> None:
        scene = QGraphicsScene()
        canvas = self._make_canvas(scene)
        service = HandleOverlayService(canvas)
        item = _FakeGraphicsItem(data={1: {"center": QPointF(10.0, 20.0), "base_handle_dist": 7.0}})

        service.show_orbital_handles(item)

        canvas._set_selection_highlight.assert_called_once_with([item])
        self.assertIs(canvas._handle_target, item)
        self.assertEqual(len(canvas._active_handles), 2)
        self.assertEqual(
            [(handle.rect().center().x(), handle.rect().center().y()) for handle in canvas._active_handles],
            [(17.0, 20.0), (10.0, 13.0)],
        )

        fallback = _FakeGraphicsItem(rect=QRectF(0.0, 0.0, 20.0, 10.0), data={1: {}})
        canvas._set_selection_highlight.reset_mock()
        service.show_orbital_handles(fallback)
        canvas._set_selection_highlight.assert_called_once_with([fallback])
        self.assertEqual(
            [(handle.rect().center().x(), handle.rect().center().y()) for handle in canvas._active_handles],
            [(42.0, 5.0), (10.0, -27.0)],
        )

    def test_show_curved_handles_uses_geometry_or_fallback_midpoint(self) -> None:
        scene = QGraphicsScene()
        canvas = self._make_canvas(scene)
        service = HandleOverlayService(canvas)
        item = _FakeGraphicsItem(data={2: {"start": QPointF(0.0, 0.0), "end": QPointF(10.0, 0.0)}})

        service.show_curved_handles(item)

        canvas._set_selection_highlight.assert_called_once_with([item])
        canvas._default_curved_control.assert_called_once_with(QPointF(0.0, 0.0), QPointF(10.0, 0.0))
        canvas._update_curved_control.assert_called_once_with(item, QPointF(5.0, 4.0))
        self.assertEqual(len(canvas._active_handles), 1)
        self.assertEqual((canvas._active_handles[0].rect().center().x(), canvas._active_handles[0].rect().center().y()), (5.0, 4.0))

        fallback = _FakeGraphicsItem(rect=QRectF(0.0, 0.0, 20.0, 20.0), data={2: {}})
        canvas._set_selection_highlight.reset_mock()
        canvas._update_curved_control.reset_mock()
        service.show_curved_handles(fallback)
        canvas._set_selection_highlight.assert_called_once_with([fallback])
        canvas._update_curved_control.assert_not_called()
        self.assertEqual((canvas._active_handles[0].rect().center().x(), canvas._active_handles[0].rect().center().y()), (10.0, 10.0))


if __name__ == "__main__":
    unittest.main()
