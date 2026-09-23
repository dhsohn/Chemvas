import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state
from tests.scene_render_context import attach_scene_render_context

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath
from PyQt6.QtWidgets import QApplication

from chemvas.ui.canvas_arrow_build_service import CanvasArrowBuildService
from chemvas.ui.canvas_scene_items_state import CanvasSceneItemsState
from chemvas.ui.canvas_tool_settings_state import CanvasToolSettingsState
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


class HandleMutationServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _make_canvas(self, *, bond_length_px: float = 40.0):
        canvas = SimpleNamespace(
            renderer=SimpleNamespace(
                style=SimpleNamespace(bond_length_px=bond_length_px)
            ),
            runtime_state=canvas_runtime_state(
                scene_items_state=CanvasSceneItemsState(),
                tool_settings_state=CanvasToolSettingsState(),
            ),
            refresh_selection_outline=mock.Mock(),
        )
        build_service = CanvasArrowBuildService(attach_scene_render_context(canvas))
        build_service.add_arrow_head = mock.Mock(wraps=build_service.add_arrow_head)
        canvas.services = canvas_runtime_services(
            arrow_build_service=build_service,
            selection=SimpleNamespace(
                update_selection_outline=canvas.refresh_selection_outline
            ),
        )
        return canvas

    def _service(self, canvas) -> HandleMutationService:
        return HandleMutationService(
            canvas,
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

        canvas.runtime_state.tool_settings_state.orbital_snap_enabled = True
        canvas.runtime_state.tool_settings_state.orbital_snap_step = 15
        fallback_item = _FakeGraphicsItem(
            rect=QRectF(0.0, 0.0, 20.0, 10.0), data={1: {}}
        )
        service.update_orbital_scale(fallback_item, QPointF(42.0, 5.0))
        service.update_orbital_rotate(fallback_item, QPointF(42.0, 5.0))
        self.assertAlmostEqual(fallback_item._scale, 1.0)
        self.assertAlmostEqual(fallback_item._rotation, 0.0)
