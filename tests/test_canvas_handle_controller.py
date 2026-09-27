import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF

from chemvas.domain.document import arrow_from_state
from chemvas.ui.canvas.canvas_handle_controller import CanvasHandleController


class _Handle:
    def __init__(self, handle_type: str, target) -> None:
        self._data = {1: handle_type, 2: target}

    def data(self, key):
        return self._data.get(key)


class CanvasHandleControllerTest(unittest.TestCase):
    def test_overlay_and_selection_wrappers_delegate_to_services(self) -> None:
        overlay = SimpleNamespace(
            show_orbital_handles=mock.Mock(),
            show_curved_handles=mock.Mock(),
        )
        controller = CanvasHandleController(handle_overlay_service=overlay)
        controller.show_orbital_handles("orbital")
        controller.show_curved_handles("curved")

        overlay.show_orbital_handles.assert_called_once_with("orbital")
        overlay.show_curved_handles.assert_called_once_with("curved")

    def test_update_handle_drag_mutation_wrappers(self) -> None:
        mutation_service = SimpleNamespace(
            update_orbital_scale=mock.Mock(),
            update_orbital_rotate=mock.Mock(),
            update_curved_control=mock.Mock(),
            update_arrow_endpoint=mock.Mock(),
        )
        overlay_service = SimpleNamespace(
            show_orbital_handles=mock.Mock(),
            show_curved_handles=mock.Mock(),
        )
        controller = CanvasHandleController(
            handle_overlay_service=overlay_service,
            handle_mutation_service=mutation_service,
        )
        scene_pos = QPointF(4.0, 5.0)
        pressed = {"kind": "curved_single", "start": (0, 0), "end": (40, 0)}

        for handle_type, target in (
            ("orbital_scale", "orbital"),
            ("orbital_rotate", "orbital"),
            ("curved_control", "curve"),
            ("curved_start", "curve"),
            ("curved_end", "curve"),
            ("unknown", "mystery"),
            ("orbital_scale", None),
        ):
            controller.update_handle_drag(
                _Handle(handle_type, target), scene_pos, pressed
            )

        mutation_service.update_orbital_scale.assert_called_once_with(
            "orbital", scene_pos
        )
        mutation_service.update_orbital_rotate.assert_called_once_with(
            "orbital", scene_pos
        )
        mutation_service.update_curved_control.assert_called_once_with(
            "curve", scene_pos
        )
        mutation_service.update_arrow_endpoint.assert_has_calls(
            [
                mock.call(
                    "curve", scene_pos, "start", pressed=arrow_from_state(pressed)
                ),
                mock.call("curve", scene_pos, "end", pressed=arrow_from_state(pressed)),
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
            update_arrow_endpoint=mock.Mock(),
        )
        controller = CanvasHandleController(handle_mutation_service=mutation)
        controller.update_orbital_scale("item", QPointF(1.0, 1.0))
        controller.update_orbital_rotate("item", QPointF(2.0, 2.0))
        controller.update_curved_control("item", QPointF(3.0, 3.0))
        pressed = arrow_from_state({"kind": "line", "start": (0, 0), "end": (4, 0)})
        controller.update_arrow_endpoint(
            "item", QPointF(4.0, 4.0), "start", pressed=pressed
        )
        mutation.update_orbital_scale.assert_called_once_with("item", QPointF(1.0, 1.0))
        mutation.update_orbital_rotate.assert_called_once_with(
            "item", QPointF(2.0, 2.0)
        )
        mutation.update_curved_control.assert_called_once_with(
            "item", QPointF(3.0, 3.0)
        )
        mutation.update_arrow_endpoint.assert_called_once_with(
            "item", QPointF(4.0, 4.0), "start", pressed=pressed
        )
