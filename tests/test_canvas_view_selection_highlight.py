import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
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
    from chemvas.ui.canvas_handle_controller import CanvasHandleController
    from chemvas.ui.canvas_tool_settings_state import CanvasToolSettingsState
    from chemvas.ui.curved_arrow_path_service import CurvedArrowPathService
    from chemvas.ui.handle_mutation_access import (
        update_curved_control_for,
        update_orbital_rotate_for,
        update_orbital_scale_for,
    )
    from chemvas.ui.handle_mutation_service import HandleMutationService
    from chemvas.ui.handle_overlay_access import (
        clear_handles_for,
        show_curved_handles_for,
        show_orbital_handles_for,
    )
    from chemvas.ui.handle_overlay_service import HandleOverlayService
    from chemvas.ui.handle_state import CanvasHandleState
    from chemvas.ui.selection_highlight_styler import SelectionHighlightStyler
    from chemvas.ui.selection_style_state import SelectionStyleState


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


def _attach_handle_services(view: SimpleNamespace) -> SimpleNamespace:
    services = getattr(view, "services", None)
    if services is None:
        services = SimpleNamespace()
        view.services = services
    if hasattr(view, "refresh_selection_outline") and not hasattr(
        services, "selection_controller"
    ):
        services.selection_controller = SimpleNamespace(
            update_selection_outline=view.refresh_selection_outline
        )
    services.selection_highlight_styler = SelectionHighlightStyler(view)
    services.handle_overlay_service = HandleOverlayService(view)
    services.curved_arrow_path_service = CurvedArrowPathService(view)
    services.handle_mutation_service = HandleMutationService(
        view,
        curved_arrow_path_service=services.curved_arrow_path_service,
    )
    services.handle_controller = CanvasHandleController(
        view,
        handle_overlay_service=services.handle_overlay_service,
        handle_mutation_service=services.handle_mutation_service,
    )
    return services


def _selection_style_state(
    color: str = "#1f5eff",
    stroke_delta: float = 0.6,
    selected_items: list | None = None,
) -> SelectionStyleState:
    return SelectionStyleState(
        selected_items=list(selected_items or []),
        color=QColor(color),
        stroke_delta=stroke_delta,
    )


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for canvas view tests"
)
class CanvasViewSelectionHighlightTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_apply_selection_style_handles_items_and_groups(self) -> None:
        view = SimpleNamespace(selection_style_state=_selection_style_state())
        services = _attach_handle_services(view)
        styler = services.selection_highlight_styler
        item = _path_item()

        styler.apply_selection_style(item, True)
        self.assertEqual(item.pen().color().name(), "#1f5eff")
        self.assertAlmostEqual(item.pen().widthF(), 2.1)
        self.assertIsInstance(item.data(6), QPen)

        styler.apply_selection_style(item, False)
        self.assertEqual(item.pen().color().name(), "#111111")
        self.assertAlmostEqual(item.pen().widthF(), 1.5)

        child = _path_item("#222222", 2.0)
        group = QGraphicsItemGroup()
        group.addToGroup(child)
        styler.apply_selection_style(group, True)
        self.assertEqual(child.pen().color().name(), "#1f5eff")
        styler.apply_selection_style(group, False)
        self.assertEqual(child.pen().color().name(), "#222222")
        self.assertAlmostEqual(child.pen().widthF(), 2.0)

    def test_selection_highlight_set_and_clear_round_trip_items(self) -> None:
        old_item = _path_item("#333333", 1.0)
        new_item = _path_item("#444444", 1.2)
        view = SimpleNamespace(
            selection_style_state=_selection_style_state("#ff0000", 0.5, [old_item]),
        )
        services = _attach_handle_services(view)
        styler = services.selection_highlight_styler

        styler.apply_selection_style(old_item, True)
        styler.set_selection_highlight([new_item])

        self.assertEqual(view.selection_style_state.selected_items, [new_item])
        self.assertEqual(old_item.pen().color().name(), "#333333")
        self.assertEqual(new_item.pen().color().name(), "#ff0000")

        styler.clear_selection_highlight()
        self.assertEqual(view.selection_style_state.selected_items, [])
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
            handle_state=CanvasHandleState(
                active_handles=[handle_a, handle_b], target=object()
            ),
            selection_style_state=_selection_style_state(
                selected_items=[selected_item]
            ),
        )
        services = _attach_handle_services(view)
        services.selection_highlight_styler.apply_selection_style(selected_item, True)

        clear_handles_for(view)

        self.assertEqual(view.handle_state.active_handles, [])
        self.assertIsNone(view.handle_state.target)
        self.assertIsNone(handle_a.scene())
        self.assertIsNone(handle_b.scene())
        self.assertEqual(view.selection_style_state.selected_items, [])
        self.assertEqual(selected_item.pen().color().name(), "#111111")

    def test_show_orbital_handles_creates_scale_and_rotate_handles(self) -> None:
        scene = QGraphicsScene()
        item = _path_item()
        item.setData(1, {"center": QPointF(10.0, 20.0), "base_handle_dist": 15.0})
        view = SimpleNamespace(
            scene=lambda: scene,
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            handle_state=CanvasHandleState(),
            selection_style_state=_selection_style_state(),
        )
        _attach_handle_services(view)
        view.clear_handles = lambda: clear_handles_for(view)

        show_orbital_handles_for(view, item)

        self.assertEqual(len(view.handle_state.active_handles), 2)
        self.assertEqual(
            {handle.data(1) for handle in view.handle_state.active_handles},
            {"orbital_scale", "orbital_rotate"},
        )
        self.assertTrue(
            all(handle.data(2) is item for handle in view.handle_state.active_handles)
        )
        self.assertIs(view.handle_state.target, item)
        self.assertEqual(item.pen().color().name(), "#1f5eff")

    def test_show_orbital_then_curved_handles_replaces_previous_handles_and_highlight(
        self,
    ) -> None:
        scene = QGraphicsScene()
        orbital = _path_item("#111111", 1.0)
        orbital.setData(1, {"center": QPointF(10.0, 20.0), "base_handle_dist": 15.0})
        curved = _path_item("#222222", 1.2)
        curved.setData(2, {"start": QPointF(0.0, 0.0), "end": QPointF(10.0, 0.0)})
        view = SimpleNamespace(
            scene=lambda: scene,
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            handle_state=CanvasHandleState(),
            selection_style_state=_selection_style_state(),
            services=SimpleNamespace(
                scene_decoration_build_service=SimpleNamespace(
                    add_arrow_head=mock.Mock()
                )
            ),
            refresh_selection_outline=mock.Mock(),
            tool_settings_state=CanvasToolSettingsState(curved_snap_step=2),
        )
        _attach_handle_services(view)
        view.clear_handles = lambda: clear_handles_for(view)

        show_orbital_handles_for(view, orbital)
        first_handles = list(view.handle_state.active_handles)

        show_curved_handles_for(view, curved)

        self.assertTrue(all(handle.scene() is None for handle in first_handles))
        self.assertEqual(
            [handle.data(1) for handle in view.handle_state.active_handles],
            ["curved_start", "curved_control", "curved_end"],
        )
        self.assertIs(view.handle_state.target, curved)
        self.assertEqual(orbital.pen().color().name(), "#111111")
        self.assertEqual(curved.pen().color().name(), "#1f5eff")

    def test_update_handle_drag_dispatches_to_expected_helper(self) -> None:
        target = object()
        mutation_service = SimpleNamespace(
            update_orbital_scale=mock.Mock(),
            update_orbital_rotate=mock.Mock(),
            update_curved_control=mock.Mock(),
            update_curved_endpoint=mock.Mock(),
        )
        overlay_service = SimpleNamespace(
            show_orbital_handles=mock.Mock(),
            show_curved_handles=mock.Mock(),
        )
        view = SimpleNamespace(
            services=SimpleNamespace(
                handle_mutation_service=mutation_service,
                handle_overlay_service=overlay_service,
            ),
        )
        view.services.handle_controller = CanvasHandleController(
            view,
            handle_overlay_service=overlay_service,
            handle_mutation_service=mutation_service,
        )

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

        controller = view.services.handle_controller

        controller.update_handle_drag(scale_handle, QPointF(10.0, 0.0))
        mutation_service.update_orbital_scale.assert_called_once_with(
            target, QPointF(10.0, 0.0)
        )
        overlay_service.show_orbital_handles.assert_called_once_with(target)

        controller.update_handle_drag(rotate_handle, QPointF(0.0, -10.0))
        mutation_service.update_orbital_rotate.assert_called_once_with(
            target, QPointF(0.0, -10.0)
        )
        self.assertEqual(overlay_service.show_orbital_handles.call_count, 2)

        controller.update_handle_drag(curved_handle, QPointF(3.0, 4.0))
        mutation_service.update_curved_control.assert_called_once_with(
            target, QPointF(3.0, 4.0)
        )
        overlay_service.show_curved_handles.assert_called_once_with(target)

        controller.update_handle_drag(curved_start_handle, QPointF(-1.0, 2.0))
        controller.update_handle_drag(curved_end_handle, QPointF(12.0, -3.0))
        mutation_service.update_curved_endpoint.assert_has_calls(
            [
                mock.call(target, QPointF(-1.0, 2.0), "start"),
                mock.call(target, QPointF(12.0, -3.0), "end"),
            ]
        )
        self.assertEqual(overlay_service.show_curved_handles.call_count, 3)

        controller.update_handle_drag(orphan_handle, QPointF(1.0, 1.0))
        self.assertEqual(mutation_service.update_orbital_scale.call_count, 1)

    def test_orbital_and_curved_update_helpers_apply_geometry_changes(self) -> None:
        orbital = _path_item()
        orbital.setData(1, {"center": QPointF(0.0, 0.0), "base_handle_dist": 10.0})
        orbital_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0))
        )
        _attach_handle_services(orbital_view)
        update_orbital_scale_for(orbital_view, orbital, QPointF(20.0, 0.0))
        self.assertAlmostEqual(orbital.scale(), 2.0)

        orbital_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            tool_settings_state=CanvasToolSettingsState(
                orbital_snap_enabled=True, orbital_snap_step=15
            ),
        )
        _attach_handle_services(orbital_view)
        update_orbital_rotate_for(orbital_view, orbital, QPointF(10.0, 10.0))
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
            services=SimpleNamespace(
                scene_decoration_build_service=SimpleNamespace(
                    add_arrow_head=mock.Mock()
                )
            ),
            refresh_selection_outline=mock.Mock(),
        )
        _attach_handle_services(curved_view)

        update_curved_control_for(curved_view, curved, QPointF(5.0, 4.0))

        data = curved.data(2)
        self.assertAlmostEqual(data["control"].x(), 5.0)
        self.assertAlmostEqual(data["control"].y(), 8.0)
        self.assertFalse(curved.path().isEmpty())
        curved_view.refresh_selection_outline.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
