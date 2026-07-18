import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
except ModuleNotFoundError:
    QPointF = None

if QPointF is not None:
    from chemvas.ui.canvas_handle_controller import CanvasHandleController
    from chemvas.ui.canvas_tool_settings_state import CanvasToolSettingsState


class _Handle:
    def __init__(self, handle_type: str, target) -> None:
        self._data = {1: handle_type, 2: target}

    def data(self, key):
        return self._data.get(key)


@unittest.skipUnless(
    QPointF is not None, "PyQt6 is required for canvas handle controller tests"
)
class CanvasHandleControllerTest(unittest.TestCase):
    def test_overlay_and_selection_wrappers_delegate_to_services(self) -> None:
        canvas = SimpleNamespace(
            tool_settings_state=CanvasToolSettingsState(curved_snap_step=0.25),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
        )
        overlay = SimpleNamespace(
            clear_handles=mock.Mock(),
            show_orbital_handles=mock.Mock(),
            show_curved_handles=mock.Mock(),
            create_handle=mock.Mock(return_value="handle"),
        )
        styler = SimpleNamespace(
            set_selection_highlight=mock.Mock(),
            clear_selection_highlight=mock.Mock(),
            apply_selection_style=mock.Mock(),
        )

        with mock.patch(
            "chemvas.ui.canvas_handle_controller.selection_highlight_styler_for",
            return_value=styler,
        ) as styler_for:
            controller = CanvasHandleController(canvas, handle_overlay_service=overlay)
            controller.clear_handles()
            controller.show_orbital_handles("orbital")
            controller.show_curved_handles("curved")
            self.assertEqual(
                controller.create_handle(QPointF(1.0, 2.0), "orbital_scale", "target"),
                "handle",
            )
            controller.set_selection_highlight(["item"])
            controller.clear_selection_highlight()
            controller.apply_selection_style("item", True)

        overlay.clear_handles.assert_called_once_with()
        overlay.show_orbital_handles.assert_called_once_with("orbital")
        overlay.show_curved_handles.assert_called_once_with("curved")
        overlay.create_handle.assert_called_once_with(
            QPointF(1.0, 2.0), "orbital_scale", "target"
        )
        self.assertEqual(styler_for.call_count, 3)
        styler.set_selection_highlight.assert_called_once_with(["item"])
        styler.clear_selection_highlight.assert_called_once_with()
        styler.apply_selection_style.assert_called_once_with("item", True)

    def test_update_handle_drag_mutation_wrappers_and_snap_distance(self) -> None:
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
        canvas = SimpleNamespace(
            tool_settings_state=CanvasToolSettingsState(
                curved_snap=True, curved_snap_step=0.25
            ),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
        )
        controller = CanvasHandleController(
            canvas,
            handle_overlay_service=overlay_service,
            handle_mutation_service=mutation_service,
        )
        scene_pos = QPointF(4.0, 5.0)

        controller.update_handle_drag(_Handle("orbital_scale", "orbital"), scene_pos)
        controller.update_handle_drag(_Handle("orbital_rotate", "orbital"), scene_pos)
        controller.update_handle_drag(_Handle("curved_control", "curve"), scene_pos)
        controller.update_handle_drag(_Handle("curved_start", "curve"), scene_pos)
        controller.update_handle_drag(_Handle("curved_end", "curve"), scene_pos)
        controller.update_handle_drag(_Handle("unknown", "mystery"), scene_pos)
        controller.update_handle_drag(_Handle("orbital_scale", None), scene_pos)

        mutation_service.update_orbital_scale.assert_called_once_with(
            "orbital", scene_pos
        )
        mutation_service.update_orbital_rotate.assert_called_once_with(
            "orbital", scene_pos
        )
        mutation_service.update_curved_control.assert_called_once_with(
            "curve", scene_pos
        )
        mutation_service.update_curved_endpoint.assert_has_calls(
            [
                mock.call("curve", scene_pos, "start"),
                mock.call("curve", scene_pos, "end"),
            ]
        )
        self.assertEqual(overlay_service.show_orbital_handles.call_count, 2)
        overlay_service.show_orbital_handles.assert_has_calls(
            [mock.call("orbital"), mock.call("orbital")]
        )
        self.assertEqual(overlay_service.show_curved_handles.call_count, 3)
        overlay_service.show_curved_handles.assert_has_calls(
            [mock.call("curve"), mock.call("curve"), mock.call("curve")]
        )

        mutation = SimpleNamespace(
            update_orbital_scale=mock.Mock(),
            update_orbital_rotate=mock.Mock(),
            update_curved_control=mock.Mock(),
            update_curved_endpoint=mock.Mock(),
        )
        controller = CanvasHandleController(canvas, handle_mutation_service=mutation)
        controller.update_orbital_scale("item", QPointF(1.0, 1.0))
        controller.update_orbital_rotate("item", QPointF(2.0, 2.0))
        controller.update_curved_control("item", QPointF(3.0, 3.0))
        controller.update_curved_endpoint("item", QPointF(4.0, 4.0), "start")
        mutation.update_orbital_scale.assert_called_once_with("item", QPointF(1.0, 1.0))
        mutation.update_orbital_rotate.assert_called_once_with(
            "item", QPointF(2.0, 2.0)
        )
        mutation.update_curved_control.assert_called_once_with(
            "item", QPointF(3.0, 3.0)
        )
        mutation.update_curved_endpoint.assert_called_once_with(
            "item", QPointF(4.0, 4.0), "start"
        )

        with mock.patch(
            "chemvas.ui.canvas_handle_controller.clamp_curved_midpoint_helper",
            return_value=QPointF(9.0, 9.0),
        ) as clamp_helper:
            result = controller.clamp_curved_midpoint(
                QPointF(), QPointF(10.0, 0.0), QPointF(5.0, 5.0)
            )
        self.assertEqual(result, QPointF(9.0, 9.0))
        clamp_helper.assert_called_once_with(
            QPointF(),
            QPointF(10.0, 0.0),
            QPointF(5.0, 5.0),
            snap_enabled=True,
            snap_distance=5.0,
        )


if __name__ == "__main__":
    unittest.main()
