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
    from ui.canvas_view import CanvasView
    from ui.curved_arrow_path_service import CurvedArrowPathService
    from ui.handle_mutation_service import HandleMutationService
    from ui.handle_overlay_service import HandleOverlayService
    from ui.selection_highlight_styler import SelectionHighlightStyler


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
        _selected_items=[],
        _active_handles=[],
        _handle_target=None,
        _selection_color=QColor("#1f5eff"),
        _selection_stroke_delta=0.6,
        _orbital_snap_enabled=False,
        _orbital_snap_step=15,
        _curved_snap=False,
        _curved_snap_step=2,
        _update_selection_outline=mock.Mock(),
        _add_arrow_head=mock.Mock(),
    )
    view._apply_selection_style = lambda item, selected: CanvasView._apply_selection_style(view, item, selected)
    view._clear_selection_highlight = lambda: CanvasView._clear_selection_highlight(view)
    view._set_selection_highlight = lambda items: CanvasView._set_selection_highlight(view, items)
    view.clear_handles = lambda: CanvasView.clear_handles(view)
    view._create_handle = lambda pos, handle_type, target: CanvasView._create_handle(view, pos, handle_type, target)
    view._default_curved_control = lambda start, end: CanvasView._default_curved_control(view, start, end)
    view._curved_midpoint = lambda start, control, end: CanvasView._curved_midpoint(view, start, control, end)
    view._clamp_curved_midpoint = lambda start, end, mid: CanvasView._clamp_curved_midpoint(view, start, end, mid)
    view._control_from_midpoint = lambda start, end, mid: CanvasView._control_from_midpoint(view, start, end, mid)
    view._update_curved_control = lambda item, pos: CanvasView._update_curved_control(view, item, pos)
    view._update_curved_endpoint = lambda item, pos, endpoint: CanvasView._update_curved_endpoint(view, item, pos, endpoint)
    view._selection_highlight_styler = SelectionHighlightStyler(view)
    view._handle_overlay_service = HandleOverlayService(view)
    view._handle_mutation_service = HandleMutationService(view)
    view._curved_arrow_path_service = CurvedArrowPathService(view)
    view._handle_controller = CanvasHandleController(view)
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

        CanvasView._set_selection_highlight(view, [group])

        selected_pen = child.pen()
        stored_pen = child.data(6)
        self.assertIsInstance(stored_pen, QPen)
        self.assertEqual(stored_pen.color().name(), original_pen.color().name())
        self.assertAlmostEqual(stored_pen.widthF(), original_pen.widthF())
        self.assertEqual(selected_pen.color().name(), view._selection_color.name())
        self.assertAlmostEqual(selected_pen.widthF(), original_pen.widthF() + view._selection_stroke_delta)
        self.assertEqual(view._selected_items, [group])

        CanvasView._clear_selection_highlight(view)

        restored_pen = child.pen()
        self.assertEqual(restored_pen.color().name(), original_pen.color().name())
        self.assertAlmostEqual(restored_pen.widthF(), original_pen.widthF())
        self.assertEqual(view._selected_items, [])

    def test_clear_handles_removes_active_handles_and_clears_target(self) -> None:
        scene = _RecordingScene()
        view = _make_proxy(scene)
        view._clear_selection_highlight = mock.Mock()

        handle_one = QGraphicsEllipseItem(0.0, 0.0, 10.0, 10.0)
        handle_two = QGraphicsEllipseItem(10.0, 0.0, 10.0, 10.0)
        scene.addItem(handle_one)
        scene.addItem(handle_two)
        view._active_handles = [handle_one, handle_two]
        view._handle_target = object()
        view._selected_items = []

        CanvasView.clear_handles(view)

        self.assertEqual(scene.removed_items, [handle_one, handle_two])
        self.assertEqual(view._active_handles, [])
        self.assertIsNone(view._handle_target)
        view._clear_selection_highlight.assert_called_once()

    def test_show_orbital_handles_creates_handles_from_center_and_bounds(self) -> None:
        scene = _RecordingScene()
        view = _make_proxy(scene, bond_length_px=40.0)

        center_item = _FakeGraphicsItem()
        center_item.setData(1, {"center": QPointF(10.0, 20.0), "base_handle_dist": 7.0})

        CanvasView.show_orbital_handles(view, center_item)

        self.assertEqual(len(view._active_handles), 2)
        self.assertIs(view._handle_target, center_item)
        self.assertEqual([_point_tuple(handle.rect().center()) for handle in view._active_handles], [(17.0, 20.0), (10.0, 13.0)])
        self.assertEqual(center_item.pen().color().name(), view._selection_color.name())
        self.assertIn(6, center_item._data)

        fallback_item = _FakeGraphicsItem(rect=QRectF(0.0, 0.0, 20.0, 10.0))
        fallback_item.setData(1, {})

        CanvasView.show_orbital_handles(view, fallback_item)

        self.assertEqual([_point_tuple(handle.rect().center()) for handle in view._active_handles], [(42.0, 5.0), (10.0, -27.0)])
        self.assertEqual(fallback_item.pen().color().name(), view._selection_color.name())
        self.assertGreaterEqual(len(scene.removed_items), 2)

    def test_show_curved_handles_and_update_curved_control_cover_valid_and_fallback_paths(self) -> None:
        scene = _RecordingScene()
        view = _make_proxy(scene)

        curved_item = _FakeGraphicsItem()
        curved_item.setData(2, {"start": QPointF(0.0, 0.0), "end": QPointF(10.0, 0.0)})

        CanvasView.show_curved_handles(view, curved_item)

        self.assertEqual(len(view._active_handles), 3)
        self.assertIs(view._handle_target, curved_item)
        self.assertFalse(curved_item.path().isEmpty())
        self.assertIn("control", curved_item.data(2))
        expected_mid = CanvasView._curved_midpoint(view, QPointF(0.0, 0.0), curved_item.data(2)["control"], QPointF(10.0, 0.0))
        self.assertEqual(
            [(handle.data(1), _point_tuple(handle.rect().center())) for handle in view._active_handles],
            [("curved_start", (0.0, 0.0)), ("curved_control", _point_tuple(expected_mid)), ("curved_end", (10.0, 0.0))],
        )
        self.assertEqual(view._update_selection_outline.call_count, 1)

        fallback_item = _FakeGraphicsItem(rect=QRectF(0.0, 0.0, 20.0, 20.0))
        fallback_item.setData(2, {})

        CanvasView.show_curved_handles(view, fallback_item)

        self.assertEqual(_point_tuple(view._active_handles[0].rect().center()), (10.0, 10.0))

    def test_update_handle_drag_dispatches_by_handle_type(self) -> None:
        scene = _RecordingScene()
        view = _make_proxy(scene)
        view._update_orbital_scale = mock.Mock()
        view._update_orbital_rotate = mock.Mock()
        view._update_curved_control = mock.Mock()
        view._update_curved_endpoint = mock.Mock()
        view.show_orbital_handles = mock.Mock()
        view.show_curved_handles = mock.Mock()

        target = object()
        scale_handle = SimpleNamespace(data=lambda key: "orbital_scale" if key == 1 else target)
        rotate_handle = SimpleNamespace(data=lambda key: "orbital_rotate" if key == 1 else target)
        curved_handle = SimpleNamespace(data=lambda key: "curved_control" if key == 1 else target)
        curved_start_handle = SimpleNamespace(data=lambda key: "curved_start" if key == 1 else target)
        curved_end_handle = SimpleNamespace(data=lambda key: "curved_end" if key == 1 else target)
        unknown_handle = SimpleNamespace(data=lambda key: None)

        CanvasView.update_handle_drag(view, scale_handle, QPointF(1.0, 2.0))
        CanvasView.update_handle_drag(view, rotate_handle, QPointF(3.0, 4.0))
        CanvasView.update_handle_drag(view, curved_handle, QPointF(5.0, 6.0))
        CanvasView.update_handle_drag(view, curved_start_handle, QPointF(7.0, 8.0))
        CanvasView.update_handle_drag(view, curved_end_handle, QPointF(9.0, 10.0))
        CanvasView.update_handle_drag(view, unknown_handle, QPointF(7.0, 8.0))

        view._update_orbital_scale.assert_called_once_with(target, QPointF(1.0, 2.0))
        self.assertEqual(view.show_orbital_handles.call_args_list, [mock.call(target), mock.call(target)])
        view._update_orbital_rotate.assert_called_once_with(target, QPointF(3.0, 4.0))
        view._update_curved_control.assert_called_once_with(target, QPointF(5.0, 6.0))
        view._update_curved_endpoint.assert_has_calls(
            [mock.call(target, QPointF(7.0, 8.0), "start"), mock.call(target, QPointF(9.0, 10.0), "end")]
        )
        self.assertEqual(view.show_curved_handles.call_count, 3)

    def test_update_curved_endpoint_updates_path_and_handles_invalid_input(self) -> None:
        scene = _RecordingScene()
        view = _make_proxy(scene)

        curved_item = _FakeGraphicsItem()
        curved_item.setData(2, {"start": QPointF(0.0, 0.0), "end": QPointF(10.0, 0.0), "control": QPointF(5.0, 8.0), "double": True})
        curved_item.setPos(-8.0, 6.0)

        CanvasView._update_curved_endpoint(view, curved_item, QPointF(-2.0, 1.0), "start")

        self.assertFalse(curved_item.path().isEmpty())
        self.assertEqual(curved_item.data(2)["start"], QPointF(-2.0, 1.0))
        self.assertEqual(curved_item.data(2)["control"], QPointF(5.0, 8.0))
        self.assertEqual(curved_item.pos(), QPointF())
        self.assertEqual(view._add_arrow_head.call_count, 2)
        self.assertEqual(view._update_selection_outline.call_count, 1)

        invalid_item = _FakeGraphicsItem()
        invalid_item.setData(2, {"start": QPointF(0.0, 0.0)})
        CanvasView._update_curved_endpoint(view, invalid_item, QPointF(3.0, 3.0), "end")
        self.assertTrue(invalid_item.path().isEmpty())

    def test_update_orbital_scale_and_rotate_use_center_or_bounds(self) -> None:
        scene = _RecordingScene()
        view = _make_proxy(scene, bond_length_px=40.0)

        centered_item = _FakeGraphicsItem()
        centered_item.setData(1, {"center": QPointF(10.0, 5.0), "base_handle_dist": 10.0})

        CanvasView._update_orbital_scale(view, centered_item, QPointF(15.0, 5.0))
        CanvasView._update_orbital_rotate(view, centered_item, QPointF(10.0, 15.0))

        self.assertAlmostEqual(centered_item._scale, 0.5)
        self.assertAlmostEqual(centered_item._rotation, 90.0)

        fallback_item = _FakeGraphicsItem(rect=QRectF(0.0, 0.0, 20.0, 10.0))
        fallback_item.setData(1, {})

        CanvasView._update_orbital_scale(view, fallback_item, QPointF(42.0, 5.0))
        CanvasView._update_orbital_rotate(view, fallback_item, QPointF(42.0, 5.0))

        self.assertAlmostEqual(fallback_item._scale, 1.0)
        self.assertAlmostEqual(fallback_item._rotation, 0.0)

    def test_update_curved_control_updates_path_and_handles_invalid_input(self) -> None:
        scene = _RecordingScene()
        view = _make_proxy(scene)

        curved_item = _FakeGraphicsItem()
        curved_item.setData(2, {"start": QPointF(0.0, 0.0), "end": QPointF(10.0, 0.0), "double": True})
        curved_item.setPos(11.0, -3.0)

        CanvasView._update_curved_control(view, curved_item, QPointF(5.0, 4.0))

        self.assertFalse(curved_item.path().isEmpty())
        self.assertIn("control", curved_item.data(2))
        self.assertEqual(curved_item.pos(), QPointF())
        self.assertEqual(view._add_arrow_head.call_count, 2)
        self.assertEqual(view._update_selection_outline.call_count, 1)

        invalid_item = _FakeGraphicsItem()
        invalid_item.setData(2, {"start": QPointF(0.0, 0.0)})
        CanvasView._update_curved_control(view, invalid_item, QPointF(3.0, 3.0))
        self.assertTrue(invalid_item.path().isEmpty())
