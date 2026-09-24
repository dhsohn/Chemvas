import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.orbital_support import make_orbital
from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state
from tests.scene_render_context import attach_scene_render_context

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsEllipseItem,
    QGraphicsScene,
)

from chemvas.ui.annotations.arrows import ArrowRenderer
from chemvas.ui.canvas.canvas_handle_controller import CanvasHandleController
from chemvas.ui.canvas.canvas_scene_items_state import CanvasSceneItemsState
from chemvas.ui.canvas.canvas_tool_settings_state import CanvasToolSettingsState
from chemvas.ui.selection.selection_state import SelectionState
from chemvas.ui.tools.handle_mutation_access import (
    update_orbital_rotate_for,
    update_orbital_scale_for,
)
from chemvas.ui.tools.handle_mutation_service import HandleMutationService
from chemvas.ui.tools.handle_overlay_service import HandleOverlayService
from chemvas.ui.tools.handle_state import CanvasHandleState


class _RecordingScene(QGraphicsScene):
    def __init__(self) -> None:
        super().__init__()
        self.added_items = []
        self.removed_items = []

    def addItem(self, item) -> None:  # type: ignore[override]
        self.added_items.append(item)
        super().addItem(item)

    def removeItem(self, item) -> None:  # type: ignore[override]
        self.removed_items.append(item)
        super().removeItem(item)


class _FakeGraphicsItem:
    def __init__(self, rect: QRectF | None = None, *, pen: QPen | None = None) -> None:
        self._data = {}
        self._pen = QPen(pen or QPen(QColor("#444444")))
        self._rect = QRectF(rect or QRectF(0.0, 0.0, 20.0, 10.0))
        self._path = QPainterPath()
        self._scale = 1.0
        self._rotation = 0.0
        self._pos = QPointF()

    def pen(self) -> QPen:
        return QPen(self._pen)

    def setPen(self, pen: QPen) -> None:
        self._pen = QPen(pen)

    def data(self, key):
        return self._data.get(key)

    def setData(self, key, value) -> None:
        self._data[key] = value

    def childItems(self):
        return []

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


def _point_tuple(point: QPointF) -> tuple[float, float]:
    return (point.x(), point.y())


def _make_proxy(
    scene: QGraphicsScene, *, bond_length_px: float = 40.0
) -> SimpleNamespace:
    view = SimpleNamespace(
        scene=lambda: scene,
        renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=bond_length_px)),
        runtime_state=canvas_runtime_state(
            handle_state=CanvasHandleState(),
            scene_items_state=CanvasSceneItemsState(),
            selection_state=SelectionState(color=QColor("#1f5eff")),
            tool_settings_state=CanvasToolSettingsState(curved_snap_step=2),
        ),
        refresh_selection_outline=mock.Mock(),
        services=canvas_runtime_services(
            selection=SimpleNamespace(update_selection_outline=mock.Mock()),
        ),
    )
    arrow_builder = ArrowRenderer(attach_scene_render_context(view))
    arrow_builder.add_arrow_head = mock.Mock(wraps=arrow_builder.add_arrow_head)
    view.services.arrow_build_service = arrow_builder
    view.services.selection.update_selection_outline = view.refresh_selection_outline
    view.clear_handles = lambda: view.services.handle_overlay_service.clear_handles()
    view.services.handle_overlay_service = HandleOverlayService(view)
    view.services.handle_mutation_service = HandleMutationService(
        view,
    )
    view.services.handle_controller = CanvasHandleController(
        view,
        handle_overlay_service=view.services.handle_overlay_service,
        handle_mutation_service=view.services.handle_mutation_service,
    )
    return view


class CanvasViewHandleHelpersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_clear_handles_removes_active_handles_and_clears_target(self) -> None:
        scene = _RecordingScene()
        view = _make_proxy(scene)

        handle_one = QGraphicsEllipseItem(0.0, 0.0, 10.0, 10.0)
        handle_two = QGraphicsEllipseItem(10.0, 0.0, 10.0, 10.0)
        scene.addItem(handle_one)
        scene.addItem(handle_two)
        view.runtime_state.handle_state.active_handles = [handle_one, handle_two]
        view.runtime_state.handle_state.target = object()

        view.services.handle_overlay_service.clear_handles()

        self.assertEqual(scene.removed_items, [handle_one, handle_two])
        self.assertEqual(view.runtime_state.handle_state.active_handles, [])
        self.assertIsNone(view.runtime_state.handle_state.target)

    def test_show_orbital_handles_creates_handles_from_center_and_bounds(self) -> None:
        scene = _RecordingScene()
        view = _make_proxy(scene, bond_length_px=40.0)

        center_item = _FakeGraphicsItem()
        center_item.setData(1, {"center": QPointF(10.0, 20.0), "base_handle_dist": 7.0})

        view.services.handle_overlay_service.show_orbital_handles(center_item)

        self.assertEqual(len(view.runtime_state.handle_state.active_handles), 2)
        self.assertIs(view.runtime_state.handle_state.target, center_item)
        self.assertEqual(
            [
                _point_tuple(handle.pos())
                for handle in view.runtime_state.handle_state.active_handles
            ],
            [(17.0, 20.0), (10.0, 13.0)],
        )

        fallback_item = _FakeGraphicsItem(rect=QRectF(0.0, 0.0, 20.0, 10.0))
        fallback_item.setData(1, {})

        view.services.handle_overlay_service.show_orbital_handles(fallback_item)

        self.assertEqual(
            [
                _point_tuple(handle.pos())
                for handle in view.runtime_state.handle_state.active_handles
            ],
            [(42.0, 5.0), (10.0, -27.0)],
        )
        self.assertGreaterEqual(len(scene.removed_items), 2)

    def test_update_handle_drag_dispatches_by_handle_type(self) -> None:
        scene = _RecordingScene()
        view = _make_proxy(scene)
        mutation_service = mock.Mock()
        overlay_service = mock.Mock()
        view.services.handle_mutation_service = mutation_service
        view.services.handle_overlay_service = overlay_service
        view.services.handle_controller = CanvasHandleController(
            view,
            handle_overlay_service=overlay_service,
            handle_mutation_service=mutation_service,
        )

        target = object()
        scale_handle = SimpleNamespace(
            data=lambda key: "orbital_scale" if key == 1 else target
        )
        rotate_handle = SimpleNamespace(
            data=lambda key: "orbital_rotate" if key == 1 else target
        )
        curved_handle = SimpleNamespace(
            data=lambda key: "curved_control" if key == 1 else target
        )
        curved_start_handle = SimpleNamespace(
            data=lambda key: "curved_start" if key == 1 else target
        )
        curved_end_handle = SimpleNamespace(
            data=lambda key: "curved_end" if key == 1 else target
        )
        unknown_handle = SimpleNamespace(data=lambda key: None)

        controller = view.services.handle_controller
        controller.update_handle_drag(scale_handle, QPointF(1.0, 2.0))
        controller.update_handle_drag(rotate_handle, QPointF(3.0, 4.0))
        controller.update_handle_drag(curved_handle, QPointF(5.0, 6.0))
        controller.update_handle_drag(curved_start_handle, QPointF(7.0, 8.0))
        controller.update_handle_drag(curved_end_handle, QPointF(9.0, 10.0))
        controller.update_handle_drag(unknown_handle, QPointF(7.0, 8.0))

        mutation_service.update_orbital_scale.assert_called_once_with(
            target, QPointF(1.0, 2.0)
        )
        self.assertEqual(
            overlay_service.show_orbital_handles.call_args_list,
            [mock.call(target), mock.call(target)],
        )
        mutation_service.update_orbital_rotate.assert_called_once_with(
            target, QPointF(3.0, 4.0)
        )
        mutation_service.update_curved_control.assert_called_once_with(
            target, QPointF(5.0, 6.0)
        )
        mutation_service.update_arrow_endpoint.assert_has_calls(
            [
                mock.call(target, QPointF(7.0, 8.0), "start"),
                mock.call(target, QPointF(9.0, 10.0), "end"),
            ]
        )
        self.assertEqual(overlay_service.show_curved_handles.call_count, 3)

    def test_update_orbital_scale_and_rotate_use_document_geometry(self) -> None:
        scene = _RecordingScene()
        view = _make_proxy(scene, bond_length_px=40.0)

        centered_item = make_orbital(center=(10.0, 5.0), base_handle_dist=10.0)

        update_orbital_scale_for(view, centered_item, QPointF(15.0, 5.0))
        update_orbital_rotate_for(view, centered_item, QPointF(10.0, 15.0))

        self.assertAlmostEqual(centered_item.scale(), 0.5)
        self.assertAlmostEqual(centered_item.rotation(), 90.0)

        fallback_item = make_orbital(center=(10.0, 5.0), base_handle_dist=32.0)

        update_orbital_scale_for(view, fallback_item, QPointF(42.0, 5.0))
        update_orbital_rotate_for(view, fallback_item, QPointF(42.0, 5.0))

        self.assertAlmostEqual(fallback_item.scale(), 1.0)
        self.assertAlmostEqual(fallback_item.rotation(), 0.0)
