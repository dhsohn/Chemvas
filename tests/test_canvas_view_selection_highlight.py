import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QColor, QPainterPath, QPen
    from PyQt6.QtWidgets import QApplication, QGraphicsEllipseItem, QGraphicsItemGroup, QGraphicsPathItem, QGraphicsScene
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.canvas_handle_controller import CanvasHandleController
    from ui.canvas_view import CanvasView
    from ui.curved_arrow_path_service import CurvedArrowPathService
    from ui.handle_mutation_service import HandleMutationService
    from ui.handle_overlay_service import HandleOverlayService
    from ui.selection_highlight_styler import SelectionHighlightStyler


def _path_item(color: str = "#111111", width: float = 1.5) -> QGraphicsPathItem:
    item = QGraphicsPathItem()
    path = QPainterPath()
    path.moveTo(0.0, 0.0)
    path.lineTo(10.0, 0.0)
    item.setPath(path)
    pen = QPen(QColor(color))
    pen.setWidthF(width)
    item.setPen(pen)
    return item


def _attach_handle_services(view: SimpleNamespace) -> None:
    view._selection_highlight_styler = SelectionHighlightStyler(view)
    view._handle_overlay_service = HandleOverlayService(view)
    view._handle_mutation_service = HandleMutationService(view)
    view._curved_arrow_path_service = CurvedArrowPathService(view)
    view._handle_controller = CanvasHandleController(view)


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewSelectionHighlightTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_apply_selection_style_handles_items_and_groups(self) -> None:
        view = SimpleNamespace(_selection_color=QColor("#1f5eff"), _selection_stroke_delta=0.6)
        _attach_handle_services(view)
        view._apply_selection_style = lambda item, selected: CanvasView._apply_selection_style(view, item, selected)
        item = _path_item()

        CanvasView._apply_selection_style(view, item, True)
        self.assertEqual(item.pen().color().name(), "#1f5eff")
        self.assertAlmostEqual(item.pen().widthF(), 2.1)
        self.assertIsInstance(item.data(6), QPen)

        CanvasView._apply_selection_style(view, item, False)
        self.assertEqual(item.pen().color().name(), "#111111")
        self.assertAlmostEqual(item.pen().widthF(), 1.5)

        child = _path_item("#222222", 2.0)
        group = QGraphicsItemGroup()
        group.addToGroup(child)
        CanvasView._apply_selection_style(view, group, True)
        self.assertEqual(child.pen().color().name(), "#1f5eff")
        CanvasView._apply_selection_style(view, group, False)
        self.assertEqual(child.pen().color().name(), "#222222")
        self.assertAlmostEqual(child.pen().widthF(), 2.0)

    def test_selection_highlight_set_and_clear_round_trip_items(self) -> None:
        old_item = _path_item("#333333", 1.0)
        new_item = _path_item("#444444", 1.2)
        view = SimpleNamespace(
            _selection_color=QColor("#ff0000"),
            _selection_stroke_delta=0.5,
            _selected_items=[old_item],
        )
        _attach_handle_services(view)
        view._apply_selection_style = lambda item, selected: CanvasView._apply_selection_style(view, item, selected)
        view._clear_selection_highlight = lambda: CanvasView._clear_selection_highlight(view)

        CanvasView._apply_selection_style(view, old_item, True)
        CanvasView._set_selection_highlight(view, [new_item])

        self.assertEqual(view._selected_items, [new_item])
        self.assertEqual(old_item.pen().color().name(), "#333333")
        self.assertEqual(new_item.pen().color().name(), "#ff0000")

        CanvasView._clear_selection_highlight(view)
        self.assertEqual(view._selected_items, [])
        self.assertEqual(new_item.pen().color().name(), "#444444")

    def test_clear_handles_removes_scene_items_and_selection_highlight(self) -> None:
        scene = QGraphicsScene()
        handle_a = QGraphicsEllipseItem(0.0, 0.0, 4.0, 4.0)
        handle_b = QGraphicsEllipseItem(5.0, 0.0, 4.0, 4.0)
        scene.addItem(handle_a)
        scene.addItem(handle_b)
        selected_item = _path_item()
        view = SimpleNamespace(
            scene=lambda: scene,
            _active_handles=[handle_a, handle_b],
            _handle_target=object(),
            _selection_color=QColor("#1f5eff"),
            _selection_stroke_delta=0.6,
            _selected_items=[selected_item],
        )
        _attach_handle_services(view)
        view._apply_selection_style = lambda item, selected: CanvasView._apply_selection_style(view, item, selected)
        view._clear_selection_highlight = lambda: CanvasView._clear_selection_highlight(view)
        CanvasView._apply_selection_style(view, selected_item, True)

        CanvasView.clear_handles(view)

        self.assertEqual(view._active_handles, [])
        self.assertIsNone(view._handle_target)
        self.assertIsNone(handle_a.scene())
        self.assertIsNone(handle_b.scene())
        self.assertEqual(view._selected_items, [])
        self.assertEqual(selected_item.pen().color().name(), "#111111")

    def test_show_orbital_handles_creates_scale_and_rotate_handles(self) -> None:
        scene = QGraphicsScene()
        item = _path_item()
        item.setData(1, {"center": QPointF(10.0, 20.0), "base_handle_dist": 15.0})
        view = SimpleNamespace(
            scene=lambda: scene,
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            _active_handles=[],
            _handle_target=None,
            _selection_color=QColor("#1f5eff"),
            _selection_stroke_delta=0.6,
            _selected_items=[],
        )
        _attach_handle_services(view)
        view._apply_selection_style = lambda target, selected: CanvasView._apply_selection_style(view, target, selected)
        view._clear_selection_highlight = lambda: CanvasView._clear_selection_highlight(view)
        view.clear_handles = lambda: CanvasView.clear_handles(view)
        view._set_selection_highlight = lambda items: CanvasView._set_selection_highlight(view, items)
        view._create_handle = lambda pos, handle_type, target: CanvasView._create_handle(view, pos, handle_type, target)

        CanvasView.show_orbital_handles(view, item)

        self.assertEqual(len(view._active_handles), 2)
        self.assertEqual({handle.data(1) for handle in view._active_handles}, {"orbital_scale", "orbital_rotate"})
        self.assertTrue(all(handle.data(2) is item for handle in view._active_handles))
        self.assertIs(view._handle_target, item)
        self.assertEqual(item.pen().color().name(), "#1f5eff")

    def test_show_orbital_then_curved_handles_replaces_previous_handles_and_highlight(self) -> None:
        scene = QGraphicsScene()
        orbital = _path_item("#111111", 1.0)
        orbital.setData(1, {"center": QPointF(10.0, 20.0), "base_handle_dist": 15.0})
        curved = _path_item("#222222", 1.2)
        curved.setData(2, {"start": QPointF(0.0, 0.0), "end": QPointF(10.0, 0.0)})
        view = SimpleNamespace(
            scene=lambda: scene,
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            _active_handles=[],
            _handle_target=None,
            _selection_color=QColor("#1f5eff"),
            _selection_stroke_delta=0.6,
            _selected_items=[],
            _add_arrow_head=mock.Mock(),
            _update_selection_outline=mock.Mock(),
            _orbital_snap_enabled=False,
            _orbital_snap_step=15,
            _curved_snap=False,
            _curved_snap_step=2,
        )
        _attach_handle_services(view)
        view._apply_selection_style = lambda target, selected: CanvasView._apply_selection_style(view, target, selected)
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

        CanvasView.show_orbital_handles(view, orbital)
        first_handles = list(view._active_handles)

        CanvasView.show_curved_handles(view, curved)

        self.assertTrue(all(handle.scene() is None for handle in first_handles))
        self.assertEqual([handle.data(1) for handle in view._active_handles], ["curved_start", "curved_control", "curved_end"])
        self.assertIs(view._handle_target, curved)
        self.assertEqual(orbital.pen().color().name(), "#111111")
        self.assertEqual(curved.pen().color().name(), "#1f5eff")

    def test_update_handle_drag_dispatches_to_expected_helper(self) -> None:
        target = object()
        view = SimpleNamespace(
            _update_orbital_scale=mock.Mock(),
            _update_orbital_rotate=mock.Mock(),
            _update_curved_control=mock.Mock(),
            _update_curved_endpoint=mock.Mock(),
            show_orbital_handles=mock.Mock(),
            show_curved_handles=mock.Mock(),
        )
        view._handle_controller = CanvasHandleController(view)

        scale_handle = QGraphicsEllipseItem(0.0, 0.0, 4.0, 4.0)
        scale_handle.setData(1, "orbital_scale")
        scale_handle.setData(2, target)
        rotate_handle = QGraphicsEllipseItem(0.0, 0.0, 4.0, 4.0)
        rotate_handle.setData(1, "orbital_rotate")
        rotate_handle.setData(2, target)
        curved_handle = QGraphicsEllipseItem(0.0, 0.0, 4.0, 4.0)
        curved_handle.setData(1, "curved_control")
        curved_handle.setData(2, target)
        curved_start_handle = QGraphicsEllipseItem(0.0, 0.0, 4.0, 4.0)
        curved_start_handle.setData(1, "curved_start")
        curved_start_handle.setData(2, target)
        curved_end_handle = QGraphicsEllipseItem(0.0, 0.0, 4.0, 4.0)
        curved_end_handle.setData(1, "curved_end")
        curved_end_handle.setData(2, target)
        orphan_handle = QGraphicsEllipseItem(0.0, 0.0, 4.0, 4.0)
        orphan_handle.setData(1, "orbital_scale")
        orphan_handle.setData(2, None)

        CanvasView.update_handle_drag(view, scale_handle, QPointF(10.0, 0.0))
        view._update_orbital_scale.assert_called_once_with(target, QPointF(10.0, 0.0))
        view.show_orbital_handles.assert_called_once_with(target)

        CanvasView.update_handle_drag(view, rotate_handle, QPointF(0.0, -10.0))
        view._update_orbital_rotate.assert_called_once_with(target, QPointF(0.0, -10.0))
        self.assertEqual(view.show_orbital_handles.call_count, 2)

        CanvasView.update_handle_drag(view, curved_handle, QPointF(3.0, 4.0))
        view._update_curved_control.assert_called_once_with(target, QPointF(3.0, 4.0))
        view.show_curved_handles.assert_called_once_with(target)

        CanvasView.update_handle_drag(view, curved_start_handle, QPointF(-1.0, 2.0))
        CanvasView.update_handle_drag(view, curved_end_handle, QPointF(12.0, -3.0))
        view._update_curved_endpoint.assert_has_calls(
            [mock.call(target, QPointF(-1.0, 2.0), "start"), mock.call(target, QPointF(12.0, -3.0), "end")]
        )
        self.assertEqual(view.show_curved_handles.call_count, 3)

        CanvasView.update_handle_drag(view, orphan_handle, QPointF(1.0, 1.0))
        self.assertEqual(view._update_orbital_scale.call_count, 1)

    def test_orbital_and_curved_update_helpers_apply_geometry_changes(self) -> None:
        orbital = _path_item()
        orbital.setData(1, {"center": QPointF(0.0, 0.0), "base_handle_dist": 10.0})
        orbital_view = SimpleNamespace(renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)))
        _attach_handle_services(orbital_view)
        CanvasView._update_orbital_scale(orbital_view, orbital, QPointF(20.0, 0.0))
        self.assertAlmostEqual(orbital.scale(), 2.0)

        orbital_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            _orbital_snap_enabled=True,
            _orbital_snap_step=15,
        )
        _attach_handle_services(orbital_view)
        CanvasView._update_orbital_rotate(orbital_view, orbital, QPointF(10.0, 10.0))
        self.assertAlmostEqual(orbital.rotation(), 45.0)

        curved = _path_item()
        curved.setData(
            2,
            {
                "start": QPointF(0.0, 0.0),
                "end": QPointF(10.0, 0.0),
                "control": QPointF(5.0, 3.0),
                "double": False,
            },
        )
        curved_view = SimpleNamespace(
            _clamp_curved_midpoint=mock.Mock(return_value=QPointF(5.0, 4.0)),
            _add_arrow_head=mock.Mock(),
            _update_selection_outline=mock.Mock(),
        )
        _attach_handle_services(curved_view)
        curved_view._control_from_midpoint = lambda start, end, mid: CanvasView._control_from_midpoint(
            curved_view, start, end, mid
        )

        CanvasView._update_curved_control(curved_view, curved, QPointF(6.0, 6.0))

        data = curved.data(2)
        self.assertAlmostEqual(data["control"].x(), 5.0)
        self.assertAlmostEqual(data["control"].y(), 8.0)
        self.assertFalse(curved.path().isEmpty())
        curved_view._update_selection_outline.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
