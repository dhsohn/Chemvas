import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import QPainterPath
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.ui.canvas_tool_settings_state import CanvasToolSettingsState
    from chemvas.ui.curved_arrow_path_service import CurvedArrowPathService
    from chemvas.ui.handle_mutation_service import HandleMutationService


class _FakeGraphicsItem:
    def __init__(self, rect: QRectF | None = None, *, data=None) -> None:
        self._data = dict(data or {})
        self._rect = QRectF(rect or QRectF(0.0, 0.0, 20.0, 10.0))
        self._path = QPainterPath()
        self._scale = 1.0
        self._rotation = 0.0
        self._pos = QPointF()

    def data(self, key):
        return self._data.get(key)

    def setData(self, key, value) -> None:
        self._data[key] = value

    def boundingRect(self) -> QRectF:
        return QRectF(self._rect)

    def setScale(self, scale: float) -> None:
        self._scale = float(scale)

    def setRotation(self, angle: float) -> None:
        self._rotation = float(angle)

    def setPath(self, path: QPainterPath) -> None:
        self._path = QPainterPath(path)

    def path(self) -> QPainterPath:
        return QPainterPath(self._path)

    def setPos(self, x, y=None) -> None:
        if isinstance(x, QPointF):
            self._pos = QPointF(x)
            return
        self._pos = QPointF(float(x), float(y))

    def pos(self) -> QPointF:
        return QPointF(self._pos)


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for handle mutation service tests"
)
class HandleMutationServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _make_canvas(self, *, bond_length_px: float = 40.0):
        build_service = SimpleNamespace(add_arrow_head=mock.Mock())
        canvas = SimpleNamespace(
            renderer=SimpleNamespace(
                style=SimpleNamespace(bond_length_px=bond_length_px)
            ),
            tool_settings_state=CanvasToolSettingsState(),
            refresh_selection_outline=mock.Mock(),
        )
        canvas.services = canvas_runtime_services(
            scene_decoration_build_service=build_service,
            selection_controller=SimpleNamespace(
                update_selection_outline=canvas.refresh_selection_outline
            ),
        )
        canvas.services.handles.curved_arrow_path_service = CurvedArrowPathService(
            canvas
        )
        return canvas

    def _service(self, canvas) -> HandleMutationService:
        return HandleMutationService(
            canvas,
            curved_arrow_path_service=canvas.services.handles.curved_arrow_path_service,
        )

    def test_update_orbital_scale_and_rotate_use_center_or_bounds(self) -> None:
        canvas = self._make_canvas(bond_length_px=40.0)
        service = self._service(canvas)

        centered_item = _FakeGraphicsItem(
            data={1: {"center": QPointF(10.0, 5.0), "base_handle_dist": 10.0}}
        )
        service.update_orbital_scale(centered_item, QPointF(15.0, 5.0))
        service.update_orbital_rotate(centered_item, QPointF(10.0, 15.0))
        self.assertAlmostEqual(centered_item._scale, 0.5)
        self.assertAlmostEqual(centered_item._rotation, 90.0)

        canvas.tool_settings_state.orbital_snap_enabled = True
        canvas.tool_settings_state.orbital_snap_step = 15
        fallback_item = _FakeGraphicsItem(
            rect=QRectF(0.0, 0.0, 20.0, 10.0), data={1: {}}
        )
        service.update_orbital_scale(fallback_item, QPointF(42.0, 5.0))
        service.update_orbital_rotate(fallback_item, QPointF(42.0, 5.0))
        self.assertAlmostEqual(fallback_item._scale, 1.0)
        self.assertAlmostEqual(fallback_item._rotation, 0.0)

    def test_update_curved_control_updates_path_and_handles_invalid_input(self) -> None:
        canvas = self._make_canvas()
        service = self._service(canvas)
        curved_item = _FakeGraphicsItem(
            data={
                2: {
                    "start": QPointF(0.0, 0.0),
                    "end": QPointF(10.0, 0.0),
                    "double": True,
                }
            }
        )
        curved_item.setPos(14.0, -6.0)

        service.update_curved_control(curved_item, QPointF(5.0, 4.0))

        self.assertFalse(curved_item.path().isEmpty())
        self.assertEqual(curved_item.data(2)["control"], QPointF(5.0, 8.0))
        self.assertEqual(curved_item.pos(), QPointF())
        add_arrow_head = canvas.services.scene_decoration.scene_decoration_build_service.add_arrow_head
        self.assertEqual(add_arrow_head.call_count, 2)
        canvas.refresh_selection_outline.assert_called_once_with()

        invalid_item = _FakeGraphicsItem(data={2: {"start": QPointF(0.0, 0.0)}})
        add_arrow_head.reset_mock()
        canvas.refresh_selection_outline.reset_mock()
        service.update_curved_control(invalid_item, QPointF(3.0, 3.0))
        self.assertTrue(invalid_item.path().isEmpty())
        add_arrow_head.assert_not_called()
        canvas.refresh_selection_outline.assert_not_called()

    def test_update_curved_endpoint_updates_path_and_preserves_existing_control(
        self,
    ) -> None:
        canvas = self._make_canvas()
        service = self._service(canvas)
        curved_item = _FakeGraphicsItem(
            data={
                2: {
                    "start": QPointF(0.0, 0.0),
                    "end": QPointF(10.0, 0.0),
                    "control": QPointF(5.0, 8.0),
                    "double": False,
                }
            }
        )
        curved_item.setPos(22.0, 9.0)

        service.update_curved_endpoint(curved_item, QPointF(-2.0, 1.0), "start")

        self.assertFalse(curved_item.path().isEmpty())
        self.assertEqual(curved_item.data(2)["start"], QPointF(-2.0, 1.0))
        self.assertEqual(curved_item.data(2)["end"], QPointF(10.0, 0.0))
        self.assertEqual(curved_item.data(2)["control"], QPointF(5.0, 8.0))
        self.assertEqual(curved_item.pos(), QPointF())
        canvas.refresh_selection_outline.assert_called_once_with()

        add_arrow_head = canvas.services.scene_decoration.scene_decoration_build_service.add_arrow_head
        add_arrow_head.reset_mock()
        canvas.refresh_selection_outline.reset_mock()
        fallback_item = _FakeGraphicsItem(
            data={
                2: {
                    "start": QPointF(0.0, 0.0),
                    "end": QPointF(10.0, 0.0),
                    "double": True,
                }
            }
        )
        service.update_curved_endpoint(fallback_item, QPointF(12.0, -1.0), "end")
        self.assertEqual(fallback_item.data(2)["end"], QPointF(12.0, -1.0))
        self.assertEqual(fallback_item.data(2)["control"], QPointF(6.3, 3.1))
        self.assertEqual(add_arrow_head.call_count, 2)
        canvas.refresh_selection_outline.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
