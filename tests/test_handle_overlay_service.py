import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import QColor, QPainterPath, QPen
    from PyQt6.QtWidgets import QApplication, QGraphicsEllipseItem, QGraphicsScene
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.ui.handle_overlay_service import HandleOverlayService
    from chemvas.ui.handle_state import CanvasHandleState


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


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for handle overlay service tests"
)
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
            handle_state=CanvasHandleState(),
            services=canvas_runtime_services(
                selection_highlight_styler=mock.Mock(),
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
        canvas.handle_state.active_handles = [handle_a, handle_b]
        canvas.handle_state.target = object()

        HandleOverlayService(canvas).clear_handles()

        self.assertEqual(canvas.handle_state.active_handles, [])
        self.assertIsNone(canvas.handle_state.target)
        self.assertIsNone(handle_a.scene())
        self.assertIsNone(handle_b.scene())
        canvas.services.scene_view.selection_highlight_styler.clear_selection_highlight.assert_called_once_with()

    def test_clear_handles_uses_scene_access_helper_without_context_scene_facade(
        self,
    ) -> None:
        canvas = self._make_canvas(QGraphicsScene())
        canvas.scene = mock.Mock(
            side_effect=AssertionError("scene facade should not be used by service")
        )
        handle = object()
        canvas.handle_state.active_handles = [handle]

        with mock.patch(
            "chemvas.ui.handle_overlay_service.clear_handle_items_for_canvas",
            return_value=[],
        ) as clear_handles:
            HandleOverlayService(canvas).clear_handles()

        clear_handles.assert_called_once_with(canvas, [handle])
        canvas.scene.assert_not_called()
        self.assertEqual(canvas.handle_state.active_handles, [])

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

    def test_create_handle_uses_scene_access_helper_without_context_scene_facade(
        self,
    ) -> None:
        canvas = self._make_canvas(QGraphicsScene())
        canvas.scene = mock.Mock(
            side_effect=AssertionError("scene facade should not be used by service")
        )

        with mock.patch(
            "chemvas.ui.handle_overlay_service.add_handle_to_canvas_scene",
            side_effect=lambda _canvas, item: item,
        ) as add_handle:
            handle = HandleOverlayService(canvas).create_handle(
                QPointF(3.0, 4.0), "orbital_scale", "target"
            )

        add_handle.assert_called_once_with(canvas, handle)
        canvas.scene.assert_not_called()

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

        canvas.services.scene_view.selection_highlight_styler.set_selection_highlight.assert_called_once_with(
            [item]
        )
        self.assertIs(canvas.handle_state.target, item)
        self.assertEqual(len(canvas.handle_state.active_handles), 2)
        self.assertEqual(
            [
                (handle.rect().center().x(), handle.rect().center().y())
                for handle in canvas.handle_state.active_handles
            ],
            [(17.0, 20.0), (10.0, 13.0)],
        )

        fallback = _FakeGraphicsItem(rect=QRectF(0.0, 0.0, 20.0, 10.0), data={1: {}})
        canvas.services.scene_view.selection_highlight_styler.set_selection_highlight.reset_mock()
        service.show_orbital_handles(fallback)
        canvas.services.scene_view.selection_highlight_styler.set_selection_highlight.assert_called_once_with(
            [fallback]
        )
        self.assertEqual(
            [
                (handle.rect().center().x(), handle.rect().center().y())
                for handle in canvas.handle_state.active_handles
            ],
            [(42.0, 5.0), (10.0, -27.0)],
        )

    def test_show_curved_handles_uses_geometry_or_fallback_midpoint(self) -> None:
        scene = QGraphicsScene()
        canvas = self._make_canvas(scene)
        service = HandleOverlayService(canvas)
        item = _FakeGraphicsItem(
            data={2: {"start": QPointF(0.0, 0.0), "end": QPointF(10.0, 0.0)}}
        )

        service.show_curved_handles(item)

        canvas.services.scene_view.selection_highlight_styler.set_selection_highlight.assert_called_once_with(
            [item]
        )
        canvas.services.handles.handle_mutation_service.update_curved_control.assert_called_once_with(
            item, QPointF(5.0, 1.5)
        )
        self.assertEqual(len(canvas.handle_state.active_handles), 3)
        self.assertEqual(
            [
                (handle.data(1), handle.rect().center().x(), handle.rect().center().y())
                for handle in canvas.handle_state.active_handles
            ],
            [
                ("curved_start", 0.0, 0.0),
                ("curved_control", 5.0, 1.5),
                ("curved_end", 10.0, 0.0),
            ],
        )

        fallback = _FakeGraphicsItem(rect=QRectF(0.0, 0.0, 20.0, 20.0), data={2: {}})
        canvas.services.scene_view.selection_highlight_styler.set_selection_highlight.reset_mock()
        canvas.services.handles.handle_mutation_service.update_curved_control.reset_mock()
        service.show_curved_handles(fallback)
        canvas.services.scene_view.selection_highlight_styler.set_selection_highlight.assert_called_once_with(
            [fallback]
        )
        canvas.services.handles.handle_mutation_service.update_curved_control.assert_not_called()
        self.assertEqual(len(canvas.handle_state.active_handles), 1)
        self.assertEqual(
            (
                canvas.handle_state.active_handles[0].rect().center().x(),
                canvas.handle_state.active_handles[0].rect().center().y(),
            ),
            (10.0, 10.0),
        )

        controlled = _FakeGraphicsItem(
            data={
                2: {
                    "start": QPointF(1.0, 1.0),
                    "end": QPointF(9.0, 1.0),
                    "control": QPointF(5.0, 6.0),
                }
            }
        )
        canvas.services.handles.handle_mutation_service.update_curved_control.reset_mock()
        service.show_curved_handles(controlled)
        canvas.services.handles.handle_mutation_service.update_curved_control.assert_called_once_with(
            controlled,
            QPointF(5.0, 3.5),
        )
        self.assertEqual(
            [handle.data(1) for handle in canvas.handle_state.active_handles],
            ["curved_start", "curved_control", "curved_end"],
        )


if __name__ == "__main__":
    unittest.main()
