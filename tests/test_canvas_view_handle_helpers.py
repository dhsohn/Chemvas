import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import QColor, QPainterPath, QPen
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsEllipseItem,
        QGraphicsItemGroup,
        QGraphicsPathItem,
        QGraphicsScene,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.canvas_handle_controller import CanvasHandleController
    from ui.canvas_tool_settings_state import CanvasToolSettingsState
    from ui.curved_arrow_path_service import CurvedArrowPathService
    from ui.handle_mutation_access import (
        curved_midpoint_for,
        update_curved_control_for,
        update_curved_endpoint_for,
        update_orbital_rotate_for,
        update_orbital_scale_for,
    )
    from ui.handle_mutation_service import HandleMutationService
    from ui.handle_overlay_access import (
        clear_handles_for,
        show_curved_handles_for,
        show_orbital_handles_for,
    )
    from ui.handle_overlay_service import HandleOverlayService
    from ui.handle_state import CanvasHandleState
    from ui.selection_highlight_styler import SelectionHighlightStyler
    from ui.selection_style_state import SelectionStyleState


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


def _make_proxy(scene: QGraphicsScene, *, bond_length_px: float = 40.0) -> SimpleNamespace:
    view = SimpleNamespace(
        scene=lambda: scene,
        renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=bond_length_px)),
        handle_state=CanvasHandleState(),
        selection_style_state=SelectionStyleState(
            color=QColor("#1f5eff"),
            stroke_delta=0.6,
        ),
        tool_settings_state=CanvasToolSettingsState(curved_snap_step=2),
        refresh_selection_outline=mock.Mock(),
        services=SimpleNamespace(
            scene_decoration_build_service=SimpleNamespace(add_arrow_head=mock.Mock()),
            selection_controller=SimpleNamespace(update_selection_outline=mock.Mock()),
        ),
    )
    view.services.selection_controller.update_selection_outline = view.refresh_selection_outline
    view.clear_handles = lambda: clear_handles_for(view)
    view.services.selection_highlight_styler = SelectionHighlightStyler(view)
    view.services.handle_overlay_service = HandleOverlayService(view)
    view.services.curved_arrow_path_service = CurvedArrowPathService(view)
    view.services.handle_mutation_service = HandleMutationService(
        view,
        curved_arrow_path_service=view.services.curved_arrow_path_service,
    )
    view.services.handle_controller = CanvasHandleController(
        view,
        handle_overlay_service=view.services.handle_overlay_service,
        handle_mutation_service=view.services.handle_mutation_service,
    )
    return view


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewHandleHelpersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_set_and_clear_selection_highlight_updates_group_children(self) -> None:
        scene = _RecordingScene()
        view = _make_proxy(scene)

        group = QGraphicsItemGroup()
        child = QGraphicsPathItem()
        original_pen = QPen(QColor("#444444"))
        original_pen.setWidthF(1.0)
        child.setPen(original_pen)
        group.addToGroup(child)

        view.services.selection_highlight_styler.set_selection_highlight([group])

        selected_pen = child.pen()
        stored_pen = child.data(6)
        self.assertIsInstance(stored_pen, QPen)
        self.assertEqual(stored_pen.color().name(), original_pen.color().name())
        self.assertAlmostEqual(stored_pen.widthF(), original_pen.widthF())
        self.assertEqual(selected_pen.color().name(), view.selection_style_state.color.name())
        self.assertAlmostEqual(selected_pen.widthF(), original_pen.widthF() + view.selection_style_state.stroke_delta)
        self.assertEqual(view.selection_style_state.selected_items, [group])

        view.services.selection_highlight_styler.clear_selection_highlight()

        restored_pen = child.pen()
        self.assertEqual(restored_pen.color().name(), original_pen.color().name())
        self.assertAlmostEqual(restored_pen.widthF(), original_pen.widthF())
        self.assertEqual(view.selection_style_state.selected_items, [])

    def test_clear_handles_removes_active_handles_and_clears_target(self) -> None:
        scene = _RecordingScene()
        view = _make_proxy(scene)
        view.services.selection_highlight_styler.clear_selection_highlight = mock.Mock()

        handle_one = QGraphicsEllipseItem(0.0, 0.0, 10.0, 10.0)
        handle_two = QGraphicsEllipseItem(10.0, 0.0, 10.0, 10.0)
        scene.addItem(handle_one)
        scene.addItem(handle_two)
        view.handle_state.active_handles = [handle_one, handle_two]
        view.handle_state.target = object()
        view.selection_style_state.selected_items = []

        clear_handles_for(view)

        self.assertEqual(scene.removed_items, [handle_one, handle_two])
        self.assertEqual(view.handle_state.active_handles, [])
        self.assertIsNone(view.handle_state.target)
        view.services.selection_highlight_styler.clear_selection_highlight.assert_called_once()

    def test_show_orbital_handles_creates_handles_from_center_and_bounds(self) -> None:
        scene = _RecordingScene()
        view = _make_proxy(scene, bond_length_px=40.0)

        center_item = _FakeGraphicsItem()
        center_item.setData(1, {"center": QPointF(10.0, 20.0), "base_handle_dist": 7.0})

        show_orbital_handles_for(view, center_item)

        self.assertEqual(len(view.handle_state.active_handles), 2)
        self.assertIs(view.handle_state.target, center_item)
        self.assertEqual(
            [_point_tuple(handle.rect().center()) for handle in view.handle_state.active_handles],
            [(17.0, 20.0), (10.0, 13.0)],
        )
        self.assertEqual(center_item.pen().color().name(), view.selection_style_state.color.name())
        self.assertIn(6, center_item._data)

        fallback_item = _FakeGraphicsItem(rect=QRectF(0.0, 0.0, 20.0, 10.0))
        fallback_item.setData(1, {})

        show_orbital_handles_for(view, fallback_item)

        self.assertEqual(
            [_point_tuple(handle.rect().center()) for handle in view.handle_state.active_handles],
            [(42.0, 5.0), (10.0, -27.0)],
        )
        self.assertEqual(fallback_item.pen().color().name(), view.selection_style_state.color.name())
        self.assertGreaterEqual(len(scene.removed_items), 2)

    def test_show_curved_handles_and_update_curved_control_cover_valid_and_fallback_paths(self) -> None:
        scene = _RecordingScene()
        view = _make_proxy(scene)

        curved_item = _FakeGraphicsItem()
        curved_item.setData(2, {"start": QPointF(0.0, 0.0), "end": QPointF(10.0, 0.0)})

        show_curved_handles_for(view, curved_item)

        self.assertEqual(len(view.handle_state.active_handles), 3)
        self.assertIs(view.handle_state.target, curved_item)
        self.assertFalse(curved_item.path().isEmpty())
        self.assertIn("control", curved_item.data(2))
        expected_mid = curved_midpoint_for(view, QPointF(0.0, 0.0), curved_item.data(2)["control"], QPointF(10.0, 0.0))
        self.assertEqual(
            [(handle.data(1), _point_tuple(handle.rect().center())) for handle in view.handle_state.active_handles],
            [("curved_start", (0.0, 0.0)), ("curved_control", _point_tuple(expected_mid)), ("curved_end", (10.0, 0.0))],
        )
        self.assertEqual(view.refresh_selection_outline.call_count, 1)

        fallback_item = _FakeGraphicsItem(rect=QRectF(0.0, 0.0, 20.0, 20.0))
        fallback_item.setData(2, {})

        show_curved_handles_for(view, fallback_item)

        self.assertEqual(_point_tuple(view.handle_state.active_handles[0].rect().center()), (10.0, 10.0))

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
        scale_handle = SimpleNamespace(data=lambda key: "orbital_scale" if key == 1 else target)
        rotate_handle = SimpleNamespace(data=lambda key: "orbital_rotate" if key == 1 else target)
        curved_handle = SimpleNamespace(data=lambda key: "curved_control" if key == 1 else target)
        curved_start_handle = SimpleNamespace(data=lambda key: "curved_start" if key == 1 else target)
        curved_end_handle = SimpleNamespace(data=lambda key: "curved_end" if key == 1 else target)
        unknown_handle = SimpleNamespace(data=lambda key: None)

        controller = view.services.handle_controller
        controller.update_handle_drag(scale_handle, QPointF(1.0, 2.0))
        controller.update_handle_drag(rotate_handle, QPointF(3.0, 4.0))
        controller.update_handle_drag(curved_handle, QPointF(5.0, 6.0))
        controller.update_handle_drag(curved_start_handle, QPointF(7.0, 8.0))
        controller.update_handle_drag(curved_end_handle, QPointF(9.0, 10.0))
        controller.update_handle_drag(unknown_handle, QPointF(7.0, 8.0))

        mutation_service.update_orbital_scale.assert_called_once_with(target, QPointF(1.0, 2.0))
        self.assertEqual(
            overlay_service.show_orbital_handles.call_args_list,
            [mock.call(target), mock.call(target)],
        )
        mutation_service.update_orbital_rotate.assert_called_once_with(target, QPointF(3.0, 4.0))
        mutation_service.update_curved_control.assert_called_once_with(target, QPointF(5.0, 6.0))
        mutation_service.update_curved_endpoint.assert_has_calls(
            [mock.call(target, QPointF(7.0, 8.0), "start"), mock.call(target, QPointF(9.0, 10.0), "end")]
        )
        self.assertEqual(overlay_service.show_curved_handles.call_count, 3)

    def test_update_curved_endpoint_updates_path_and_handles_invalid_input(self) -> None:
        scene = _RecordingScene()
        view = _make_proxy(scene)

        curved_item = _FakeGraphicsItem()
        curved_item.setData(2, {"start": QPointF(0.0, 0.0), "end": QPointF(10.0, 0.0), "control": QPointF(5.0, 8.0), "double": True})
        curved_item.setPos(-8.0, 6.0)

        update_curved_endpoint_for(view, curved_item, QPointF(-2.0, 1.0), "start")

        self.assertFalse(curved_item.path().isEmpty())
        self.assertEqual(curved_item.data(2)["start"], QPointF(-2.0, 1.0))
        self.assertEqual(curved_item.data(2)["control"], QPointF(5.0, 8.0))
        self.assertEqual(curved_item.pos(), QPointF())
        self.assertEqual(view.services.scene_decoration_build_service.add_arrow_head.call_count, 2)
        self.assertEqual(view.refresh_selection_outline.call_count, 1)

        invalid_item = _FakeGraphicsItem()
        invalid_item.setData(2, {"start": QPointF(0.0, 0.0)})
        update_curved_endpoint_for(view, invalid_item, QPointF(3.0, 3.0), "end")
        self.assertTrue(invalid_item.path().isEmpty())

    def test_update_orbital_scale_and_rotate_use_center_or_bounds(self) -> None:
        scene = _RecordingScene()
        view = _make_proxy(scene, bond_length_px=40.0)

        centered_item = _FakeGraphicsItem()
        centered_item.setData(1, {"center": QPointF(10.0, 5.0), "base_handle_dist": 10.0})

        update_orbital_scale_for(view, centered_item, QPointF(15.0, 5.0))
        update_orbital_rotate_for(view, centered_item, QPointF(10.0, 15.0))

        self.assertAlmostEqual(centered_item._scale, 0.5)
        self.assertAlmostEqual(centered_item._rotation, 90.0)

        fallback_item = _FakeGraphicsItem(rect=QRectF(0.0, 0.0, 20.0, 10.0))
        fallback_item.setData(1, {})

        update_orbital_scale_for(view, fallback_item, QPointF(42.0, 5.0))
        update_orbital_rotate_for(view, fallback_item, QPointF(42.0, 5.0))

        self.assertAlmostEqual(fallback_item._scale, 1.0)
        self.assertAlmostEqual(fallback_item._rotation, 0.0)

    def test_update_curved_control_updates_path_and_handles_invalid_input(self) -> None:
        scene = _RecordingScene()
        view = _make_proxy(scene)

        curved_item = _FakeGraphicsItem()
        curved_item.setData(2, {"start": QPointF(0.0, 0.0), "end": QPointF(10.0, 0.0), "double": True})
        curved_item.setPos(11.0, -3.0)

        update_curved_control_for(view, curved_item, QPointF(5.0, 4.0))

        self.assertFalse(curved_item.path().isEmpty())
        self.assertIn("control", curved_item.data(2))
        self.assertEqual(curved_item.pos(), QPointF())
        self.assertEqual(view.services.scene_decoration_build_service.add_arrow_head.call_count, 2)
        self.assertEqual(view.refresh_selection_outline.call_count, 1)

        invalid_item = _FakeGraphicsItem()
        invalid_item.setData(2, {"start": QPointF(0.0, 0.0)})
        update_curved_control_for(view, invalid_item, QPointF(3.0, 3.0))
        self.assertTrue(invalid_item.path().isEmpty())
