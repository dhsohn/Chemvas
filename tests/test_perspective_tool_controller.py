import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
except ModuleNotFoundError:
    QPointF = None

if QPointF is not None:
    from ui.canvas_rotation_state import CanvasRotationState
    from ui.perspective_tool_controller import PerspectiveToolController
    from ui.tool_context import ToolContext
    from ui.tools import PerspectiveTool


class _Event:
    def __init__(
        self,
        pos: QPointF | None = None,
        *,
        button=Qt.MouseButton.LeftButton,
        modifiers=Qt.KeyboardModifier.NoModifier,
    ) -> None:
        self._pos = QPointF(pos or QPointF())
        self._button = button
        self._modifiers = modifiers

    def button(self):
        return self._button

    def modifiers(self):
        return self._modifiers

    def position(self):
        return QPointF(self._pos)


class _DataItem:
    def __init__(self, kind=None, item_id=None) -> None:
        self._data = {0: kind, 1: item_id}

    def data(self, key):
        return self._data.get(key)


class _PerspectiveCanvas:
    DragMode = SimpleNamespace(RubberBandDrag="rubber")

    def __init__(self) -> None:
        self.drag_mode = None
        self.item = None
        self.preferred_item = None
        self.selection_hit = False
        self.select_result = True
        self.begin_rotation_result = True
        self.selection_targets = []
        self.begin_calls = []
        self.clear_handles_calls = 0
        self.toggle_result = False
        self.rotation_state = CanvasRotationState(mode="rigid")
        self.services = SimpleNamespace(
            hit_testing_service=SimpleNamespace(
                scene_pos_from_event=lambda event: event.position(),
                item_at_event=lambda event: self.item,
                bond_id_from_event=lambda event: None,
            ),
            selection_controller=SimpleNamespace(
                toggle_item_selection=self.toggle_item_selection,
                preferred_structure_item_at_scene_pos=lambda pos: self.preferred_item,
                selection_hit_test=lambda pos, snapshot=None: self.selection_hit,
                select_structure_for_item=self._select_structure_for_item,
            ),
            handle_overlay_service=SimpleNamespace(clear_handles=self.clear_handles),
            selection_rotation_controller=SimpleNamespace(
                begin_selection_3d_rotation=self.begin_selection_3d_rotation,
                update_selection_3d_rotation=mock.Mock(),
                end_selection_3d_rotation=mock.Mock(),
            ),
        )

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def item_at_event(self, event):
        return self.item

    def toggle_item_selection(self, item):
        return self.toggle_result

    def clear_handles(self) -> None:
        self.clear_handles_calls += 1

    def scene_pos_from_event(self, event):
        return event.position()

    def preferred_structure_item_at_scene_pos(self, pos):
        return self.preferred_item

    def selection_hit_test(self, pos):
        return self.selection_hit

    def _select_structure_for_item(self, item):
        self.selection_targets.append(item)
        return self.select_result

    def select_structure_for_item(self, item):
        return self._select_structure_for_item(item)

    def begin_selection_3d_rotation(self, axis_hint=None, press_pos=None):
        self.begin_calls.append((axis_hint, QPointF(press_pos) if press_pos is not None else None))
        return self.begin_rotation_result


def _tool_context_for(canvas, *, hit_testing_service=None, selection_controller=None):
    return ToolContext(
        canvas,
        hit_testing_service=hit_testing_service or canvas.services.hit_testing_service,
        selection_controller=selection_controller or canvas.services.selection_controller,
        note_controller=getattr(
            canvas.services,
            "note_controller",
            SimpleNamespace(create_text_note=mock.Mock(), begin_note_edit=mock.Mock()),
        ),
        handle_controller=getattr(
            canvas.services,
            "handle_controller",
            SimpleNamespace(update_handle_drag=mock.Mock()),
        ),
        selection_rotation_controller=canvas.services.selection_rotation_controller,
        scene_transform_controller=getattr(
            canvas.services,
            "scene_transform_controller",
            SimpleNamespace(
                apply_bond_style=mock.Mock(),
                cycle_bond_style=mock.Mock(),
                flip_bond_direction=mock.Mock(),
            ),
        ),
        set_drag_mode=getattr(canvas, "setDragMode", None),
        rubber_band_drag_mode=getattr(getattr(canvas, "DragMode", None), "RubberBandDrag", None),
    )


@unittest.skipUnless(QPointF is not None, "PyQt6 is required for perspective controller tests")
class PerspectiveToolControllerTest(unittest.TestCase):
    def test_begin_selection_rotation_reselects_structure_and_uses_bond_axis_hint(self) -> None:
        canvas = _PerspectiveCanvas()
        bond_item = _DataItem("bond", 12)
        canvas.preferred_item = bond_item
        controller = PerspectiveToolController(canvas, context=_tool_context_for(canvas))

        rotating = controller.begin_selection_rotation(_Event(QPointF(2.0, 3.0)))

        self.assertTrue(rotating)
        self.assertEqual(canvas.clear_handles_calls, 1)
        self.assertEqual(canvas.selection_targets, [bond_item])
        self.assertEqual(canvas.begin_calls, [(12, QPointF(2.0, 3.0))])

    def test_begin_selection_rotation_returns_false_when_selection_cannot_be_established(self) -> None:
        canvas = _PerspectiveCanvas()
        atom_item = _DataItem("atom", 7)
        canvas.item = atom_item
        canvas.select_result = False
        controller = PerspectiveToolController(canvas, context=_tool_context_for(canvas))

        rotating = controller.begin_selection_rotation(_Event(QPointF(4.0, 5.0)))

        self.assertFalse(rotating)
        self.assertEqual(canvas.clear_handles_calls, 1)
        self.assertEqual(canvas.selection_targets, [atom_item])
        self.assertEqual(canvas.begin_calls, [])

    def test_begin_selection_rotation_skips_reselection_when_press_hits_selection(self) -> None:
        canvas = _PerspectiveCanvas()
        canvas.selection_hit = True
        canvas.preferred_item = _DataItem("bond", 9)
        controller = PerspectiveToolController(canvas, context=_tool_context_for(canvas))

        rotating = controller.begin_selection_rotation(_Event(QPointF(6.0, 7.0)))

        self.assertTrue(rotating)
        self.assertEqual(canvas.selection_targets, [])
        self.assertEqual(canvas.begin_calls, [(9, QPointF(6.0, 7.0))])

    def test_begin_selection_rotation_uses_context_services_when_available(self) -> None:
        canvas = _PerspectiveCanvas()
        service_bond = _DataItem("bond", 12)
        fallback_bond = _DataItem("bond", 99)
        canvas.item = fallback_bond
        canvas.preferred_item = fallback_bond
        press_pos = QPointF(8.0, 9.0)
        hit_testing_service = SimpleNamespace(
            scene_pos_from_event=mock.Mock(return_value=press_pos),
            item_at_event=mock.Mock(return_value=service_bond),
        )
        selection_controller = SimpleNamespace(
            preferred_structure_item_at_scene_pos=mock.Mock(side_effect=[None, service_bond]),
            selection_hit_test=mock.Mock(return_value=False),
            select_structure_for_item=mock.Mock(return_value=True),
        )
        canvas.services.hit_testing_service = SimpleNamespace(
            scene_pos_from_event=mock.Mock(side_effect=AssertionError("canvas service should not be used")),
            item_at_event=mock.Mock(side_effect=AssertionError("canvas service should not be used")),
        )
        canvas.services.selection_controller = SimpleNamespace(
            preferred_structure_item_at_scene_pos=mock.Mock(
                side_effect=AssertionError("canvas controller should not be used")
            ),
            selection_hit_test=mock.Mock(side_effect=AssertionError("canvas controller should not be used")),
            select_structure_for_item=mock.Mock(side_effect=AssertionError("canvas controller should not be used")),
        )
        canvas.scene_pos_from_event = mock.Mock(side_effect=AssertionError("canvas facade should not be used"))
        canvas.item_at_event = mock.Mock(side_effect=AssertionError("canvas facade should not be used"))
        canvas.preferred_structure_item_at_scene_pos = mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        )
        canvas.selection_hit_test = mock.Mock(side_effect=AssertionError("canvas facade should not be used"))
        canvas.select_structure_for_item = mock.Mock(side_effect=AssertionError("canvas facade should not be used"))
        controller = PerspectiveToolController(
            canvas,
            context=_tool_context_for(
                canvas,
                hit_testing_service=hit_testing_service,
                selection_controller=selection_controller,
            ),
        )

        rotating = controller.begin_selection_rotation(_Event(QPointF(1.0, 2.0)))

        self.assertTrue(rotating)
        hit_testing_service.scene_pos_from_event.assert_called_once()
        hit_testing_service.item_at_event.assert_called_once()
        selection_controller.selection_hit_test.assert_called_once_with(press_pos, snapshot=None)
        selection_controller.select_structure_for_item.assert_called_once_with(service_bond)
        canvas.scene_pos_from_event.assert_not_called()
        canvas.item_at_event.assert_not_called()
        canvas.preferred_structure_item_at_scene_pos.assert_not_called()
        canvas.selection_hit_test.assert_not_called()
        canvas.select_structure_for_item.assert_not_called()
        self.assertEqual(canvas.selection_targets, [])
        self.assertEqual(canvas.begin_calls, [(12, press_pos)])

    def test_axis_hint_for_item_only_accepts_integer_bond_ids(self) -> None:
        self.assertEqual(PerspectiveToolController.axis_hint_for_item(_DataItem("bond", 4)), 4)
        self.assertIsNone(PerspectiveToolController.axis_hint_for_item(_DataItem("bond", "4")))
        self.assertIsNone(PerspectiveToolController.axis_hint_for_item(_DataItem("atom", 4)))
        self.assertIsNone(PerspectiveToolController.axis_hint_for_item(None))


@unittest.skipUnless(QPointF is not None, "PyQt6 is required for perspective tool tests")
class PerspectiveToolWrapperContractTest(unittest.TestCase):
    def test_on_mouse_press_delegates_rotation_entry_and_tracks_local_state(self) -> None:
        canvas = _PerspectiveCanvas()
        fake_controller = mock.Mock()
        fake_controller.begin_selection_rotation.side_effect = [True, False]
        tool = PerspectiveTool(canvas, context=_tool_context_for(canvas))
        first_event = _Event(QPointF(8.0, 4.0))
        second_event = _Event(QPointF(3.0, 1.0))

        with mock.patch("ui.perspective_tool._perspective_tool_controller_for", return_value=fake_controller):
            self.assertTrue(tool.on_mouse_press(first_event))
            self.assertEqual(tool._last_pos, QPointF(8.0, 4.0))
            self.assertTrue(tool._rotating)

            self.assertFalse(tool.on_mouse_press(second_event))
            self.assertIsNone(tool._last_pos)
            self.assertFalse(tool._rotating)

        self.assertEqual(fake_controller.begin_selection_rotation.call_args_list, [mock.call(first_event), mock.call(second_event)])

    def test_on_mouse_press_short_circuits_shift_toggle_without_controller(self) -> None:
        canvas = _PerspectiveCanvas()
        canvas.toggle_result = True
        tool = PerspectiveTool(canvas, context=_tool_context_for(canvas))
        event = _Event(QPointF(1.0, 1.0), modifiers=Qt.KeyboardModifier.ShiftModifier)

        with mock.patch("ui.perspective_tool._perspective_tool_controller_for") as controller_for:
            self.assertTrue(tool.on_mouse_press(event))

        controller_for.assert_not_called()


if __name__ == "__main__":
    unittest.main()
