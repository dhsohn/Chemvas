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
    from chemvas.ui.canvas_rotation_state import CanvasRotationState
    from chemvas.ui.perspective_tool_controller import PerspectiveToolController
    from chemvas.ui.tool_context import ToolContext
    from chemvas.ui.tools import PerspectiveTool


class _Event:
    def __init__(
        self,
        pos: QPointF | None = None,
        *,
        button=Qt.MouseButton.LeftButton,
        buttons=Qt.MouseButton.LeftButton,
        modifiers=Qt.KeyboardModifier.NoModifier,
    ) -> None:
        self._pos = QPointF(pos or QPointF())
        self._button = button
        self._buttons = buttons
        self._modifiers = modifiers

    def button(self):
        return self._button

    def modifiers(self):
        return self._modifiers

    def buttons(self):
        return self._buttons

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
        self.begin_calls.append(
            (axis_hint, QPointF(press_pos) if press_pos is not None else None)
        )
        return self.begin_rotation_result


def _tool_context_for(canvas, *, hit_testing_service=None, selection_controller=None):
    return ToolContext(
        canvas,
        hit_testing_service=hit_testing_service or canvas.services.hit_testing_service,
        selection_controller=selection_controller
        or canvas.services.selection_controller,
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
        rubber_band_drag_mode=getattr(
            getattr(canvas, "DragMode", None), "RubberBandDrag", None
        ),
    )


@unittest.skipUnless(
    QPointF is not None, "PyQt6 is required for perspective controller tests"
)
class PerspectiveToolControllerTest(unittest.TestCase):
    def test_begin_selection_rotation_reselects_structure_and_uses_bond_axis_hint(
        self,
    ) -> None:
        canvas = _PerspectiveCanvas()
        bond_item = _DataItem("bond", 12)
        canvas.preferred_item = bond_item
        controller = PerspectiveToolController(
            canvas, context=_tool_context_for(canvas)
        )

        rotating = controller.begin_selection_rotation(_Event(QPointF(2.0, 3.0)))

        self.assertTrue(rotating)
        self.assertEqual(canvas.clear_handles_calls, 1)
        self.assertEqual(canvas.selection_targets, [bond_item])
        self.assertEqual(canvas.begin_calls, [(12, QPointF(2.0, 3.0))])

    def test_begin_selection_rotation_returns_false_when_selection_cannot_be_established(
        self,
    ) -> None:
        canvas = _PerspectiveCanvas()
        atom_item = _DataItem("atom", 7)
        canvas.item = atom_item
        canvas.select_result = False
        controller = PerspectiveToolController(
            canvas, context=_tool_context_for(canvas)
        )

        rotating = controller.begin_selection_rotation(_Event(QPointF(4.0, 5.0)))

        self.assertFalse(rotating)
        self.assertEqual(canvas.clear_handles_calls, 1)
        self.assertEqual(canvas.selection_targets, [atom_item])
        self.assertEqual(canvas.begin_calls, [])

    def test_begin_selection_rotation_skips_reselection_when_press_hits_selection(
        self,
    ) -> None:
        canvas = _PerspectiveCanvas()
        canvas.selection_hit = True
        canvas.preferred_item = _DataItem("bond", 9)
        controller = PerspectiveToolController(
            canvas, context=_tool_context_for(canvas)
        )

        rotating = controller.begin_selection_rotation(_Event(QPointF(6.0, 7.0)))

        self.assertTrue(rotating)
        self.assertEqual(canvas.selection_targets, [])
        self.assertEqual(canvas.begin_calls, [(9, QPointF(6.0, 7.0))])

    def test_begin_selection_rotation_uses_context_services_when_available(
        self,
    ) -> None:
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
            preferred_structure_item_at_scene_pos=mock.Mock(
                side_effect=[None, service_bond]
            ),
            selection_hit_test=mock.Mock(return_value=False),
            select_structure_for_item=mock.Mock(return_value=True),
        )
        canvas.services.hit_testing_service = SimpleNamespace(
            scene_pos_from_event=mock.Mock(
                side_effect=AssertionError("canvas service should not be used")
            ),
            item_at_event=mock.Mock(
                side_effect=AssertionError("canvas service should not be used")
            ),
        )
        canvas.services.selection_controller = SimpleNamespace(
            preferred_structure_item_at_scene_pos=mock.Mock(
                side_effect=AssertionError("canvas controller should not be used")
            ),
            selection_hit_test=mock.Mock(
                side_effect=AssertionError("canvas controller should not be used")
            ),
            select_structure_for_item=mock.Mock(
                side_effect=AssertionError("canvas controller should not be used")
            ),
        )
        canvas.scene_pos_from_event = mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        )
        canvas.item_at_event = mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        )
        canvas.preferred_structure_item_at_scene_pos = mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        )
        canvas.selection_hit_test = mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        )
        canvas.select_structure_for_item = mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        )
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
        selection_controller.selection_hit_test.assert_called_once_with(
            press_pos, snapshot=None
        )
        selection_controller.select_structure_for_item.assert_called_once_with(
            service_bond
        )
        canvas.scene_pos_from_event.assert_not_called()
        canvas.item_at_event.assert_not_called()
        canvas.preferred_structure_item_at_scene_pos.assert_not_called()
        canvas.selection_hit_test.assert_not_called()
        canvas.select_structure_for_item.assert_not_called()
        self.assertEqual(canvas.selection_targets, [])
        self.assertEqual(canvas.begin_calls, [(12, press_pos)])

    def test_axis_hint_for_item_only_accepts_integer_bond_ids(self) -> None:
        self.assertEqual(
            PerspectiveToolController.axis_hint_for_item(_DataItem("bond", 4)), 4
        )
        self.assertIsNone(
            PerspectiveToolController.axis_hint_for_item(_DataItem("bond", "4"))
        )
        self.assertIsNone(
            PerspectiveToolController.axis_hint_for_item(_DataItem("atom", 4))
        )
        self.assertIsNone(PerspectiveToolController.axis_hint_for_item(None))


@unittest.skipUnless(
    QPointF is not None, "PyQt6 is required for perspective tool tests"
)
class PerspectiveToolWrapperContractTest(unittest.TestCase):
    def test_on_mouse_press_delegates_rotation_entry_and_tracks_local_state(
        self,
    ) -> None:
        canvas = _PerspectiveCanvas()
        fake_controller = mock.Mock()
        fake_controller.begin_selection_rotation.side_effect = [True, False]
        tool = PerspectiveTool(canvas, context=_tool_context_for(canvas))
        first_event = _Event(QPointF(8.0, 4.0))
        second_event = _Event(QPointF(3.0, 1.0))

        with mock.patch(
            "chemvas.ui.perspective_tool._perspective_tool_controller_for",
            return_value=fake_controller,
        ):
            self.assertTrue(tool.on_mouse_press(first_event))
            self.assertEqual(tool._last_pos, QPointF(8.0, 4.0))
            self.assertTrue(tool._rotating)

            self.assertTrue(tool.on_mouse_release(first_event))

            self.assertFalse(tool.on_mouse_press(second_event))
            self.assertIsNone(tool._last_pos)
            self.assertFalse(tool._rotating)

        self.assertEqual(
            fake_controller.begin_selection_rotation.call_args_list,
            [mock.call(first_event), mock.call(second_event)],
        )

    def test_on_mouse_press_short_circuits_shift_toggle_without_controller(
        self,
    ) -> None:
        canvas = _PerspectiveCanvas()
        canvas.toggle_result = True
        tool = PerspectiveTool(canvas, context=_tool_context_for(canvas))
        event = _Event(QPointF(1.0, 1.0), modifiers=Qt.KeyboardModifier.ShiftModifier)

        with mock.patch(
            "chemvas.ui.perspective_tool._perspective_tool_controller_for"
        ) as controller_for:
            self.assertTrue(tool.on_mouse_press(event))

        controller_for.assert_not_called()

    def test_deactivate_commits_active_rotation_before_tool_switch(self) -> None:
        canvas = _PerspectiveCanvas()
        canvas.selection_hit = True
        controller = canvas.services.selection_rotation_controller
        session = {"active": False}
        coordinates = [0.0, 0.0]
        history = []
        selection_info = []

        def begin_rotation(*, axis_hint=None, press_pos=None) -> bool:
            del axis_hint, press_pos
            session["active"] = True
            return True

        def update_rotation(delta_x, delta_y) -> None:
            coordinates[0] += delta_x
            coordinates[1] += delta_y

        def end_rotation() -> None:
            session["active"] = False
            history.append(tuple(coordinates))
            selection_info.append(tuple(coordinates))

        controller.begin_selection_3d_rotation = mock.Mock(side_effect=begin_rotation)
        controller.update_selection_3d_rotation = mock.Mock(side_effect=update_rotation)
        controller.end_selection_3d_rotation = mock.Mock(side_effect=end_rotation)
        tool = PerspectiveTool(canvas, context=_tool_context_for(canvas))

        self.assertTrue(tool.on_mouse_press(_Event(QPointF(2.0, 3.0))))
        self.assertTrue(
            tool.on_mouse_move(
                _Event(
                    QPointF(8.0, 4.0),
                    modifiers=Qt.KeyboardModifier.ShiftModifier,
                )
            )
        )
        self.assertTrue(session["active"])
        self.assertEqual(tool._axis_lock, "x")

        # ToolController switches tools by deactivating the current one. The
        # in-flight drag must use the same commit path as a mouse release.
        tool.deactivate()

        self.assertFalse(session["active"])
        self.assertEqual(history, [(6.0, 0.0)])
        self.assertEqual(selection_info, [(6.0, 0.0)])
        self.assertIsNone(tool._last_pos)
        self.assertIsNone(tool._axis_lock)
        self.assertFalse(tool._rotating)
        controller.end_selection_3d_rotation.assert_called_once_with()

        # A delayed release from the old drag must not create a second command.
        tool.on_mouse_release(_Event(QPointF(8.0, 4.0)))
        controller.end_selection_3d_rotation.assert_called_once_with()

    def test_failed_deactivate_keeps_rotation_session_for_release_retry(self) -> None:
        canvas = _PerspectiveCanvas()
        controller = canvas.services.selection_rotation_controller
        controller.end_selection_3d_rotation = mock.Mock(
            side_effect=[RuntimeError("injected commit failure"), None]
        )
        tool = PerspectiveTool(canvas, context=_tool_context_for(canvas))
        tool._rotating = True
        tool._last_pos = QPointF(8.0, 4.0)
        tool._axis_lock = "x"

        with self.assertRaisesRegex(RuntimeError, "commit failure"):
            tool.deactivate()

        self.assertTrue(tool._rotating)
        self.assertEqual(tool._last_pos, QPointF(8.0, 4.0))
        self.assertEqual(tool._axis_lock, "x")

        # The delayed release retries the same finalization instead of silently
        # abandoning an external rotation session that never committed.
        tool.on_mouse_release(_Event(QPointF(8.0, 4.0)))

        self.assertEqual(controller.end_selection_3d_rotation.call_count, 2)
        self.assertFalse(tool._rotating)
        self.assertIsNone(tool._last_pos)
        self.assertIsNone(tool._axis_lock)

    def test_failed_move_retries_delta_and_axis_lock_before_publishing_locals(
        self,
    ) -> None:
        canvas = _PerspectiveCanvas()
        controller = canvas.services.selection_rotation_controller
        controller.update_selection_3d_rotation = mock.Mock(
            side_effect=[KeyboardInterrupt("injected preview failure"), None]
        )
        tool = PerspectiveTool(canvas, context=_tool_context_for(canvas))
        previous_position = QPointF(2.0, 3.0)
        current_position = QPointF(8.0, 4.0)
        tool._rotating = True
        tool._last_pos = previous_position

        move_event = _Event(
            current_position,
            modifiers=Qt.KeyboardModifier.ShiftModifier,
        )
        with self.assertRaisesRegex(KeyboardInterrupt, "preview failure"):
            tool.on_mouse_move(move_event)

        self.assertEqual(tool._last_pos, previous_position)
        self.assertIsNone(tool._axis_lock)
        self.assertTrue(tool._rotating)

        self.assertTrue(tool.on_mouse_move(move_event))

        self.assertEqual(
            controller.update_selection_3d_rotation.call_args_list,
            [mock.call(6.0, 0.0), mock.call(6.0, 0.0)],
        )
        self.assertEqual(tool._last_pos, current_position)
        self.assertEqual(tool._axis_lock, "x")
        self.assertTrue(tool._rotating)

    def test_move_without_left_button_does_not_continue_stranded_rotation(self) -> None:
        canvas = _PerspectiveCanvas()
        controller = canvas.services.selection_rotation_controller
        tool = PerspectiveTool(canvas, context=_tool_context_for(canvas))
        old_position = QPointF(8.0, 4.0)
        tool._rotating = True
        tool._last_pos = old_position
        tool._axis_lock = "x"

        handled = tool.on_mouse_move(
            _Event(
                QPointF(20.0, 12.0),
                buttons=Qt.MouseButton.NoButton,
            )
        )

        self.assertFalse(handled)
        controller.update_selection_3d_rotation.assert_not_called()
        self.assertTrue(tool._rotating)
        self.assertEqual(tool._last_pos, old_position)
        self.assertEqual(tool._axis_lock, "x")

    def test_new_press_retries_failed_release_without_restarting_rotation(self) -> None:
        canvas = _PerspectiveCanvas()
        controller = canvas.services.selection_rotation_controller
        controller.end_selection_3d_rotation = mock.Mock(
            side_effect=[
                RuntimeError("release commit failure"),
                RuntimeError("press retry failure"),
                None,
            ]
        )
        next_controller = mock.Mock()
        next_controller.begin_selection_rotation.return_value = True
        tool = PerspectiveTool(canvas, context=_tool_context_for(canvas))
        old_position = QPointF(8.0, 4.0)
        tool._rotating = True
        tool._last_pos = old_position
        tool._axis_lock = "x"

        with self.assertRaisesRegex(RuntimeError, "release commit failure"):
            tool.on_mouse_release(_Event(old_position))

        new_event = _Event(QPointF(20.0, 12.0))
        with (
            mock.patch(
                "chemvas.ui.perspective_tool._perspective_tool_controller_for",
                return_value=next_controller,
            ),
            self.assertRaisesRegex(RuntimeError, "press retry failure"),
        ):
            tool.on_mouse_press(new_event)

        next_controller.begin_selection_rotation.assert_not_called()
        self.assertTrue(tool._rotating)
        self.assertEqual(tool._last_pos, old_position)
        self.assertEqual(tool._axis_lock, "x")

        with mock.patch(
            "chemvas.ui.perspective_tool._perspective_tool_controller_for",
            return_value=next_controller,
        ):
            self.assertTrue(tool.on_mouse_press(new_event))

        self.assertEqual(controller.end_selection_3d_rotation.call_count, 3)
        next_controller.begin_selection_rotation.assert_not_called()
        self.assertFalse(tool._rotating)
        self.assertIsNone(tool._last_pos)
        self.assertIsNone(tool._axis_lock)

        # Moving after the consumed commit click must not keep rotating the
        # structure, even though the structure itself remains selected.
        self.assertFalse(tool.on_mouse_move(_Event(QPointF(30.0, 20.0))))
        controller.update_selection_3d_rotation.assert_not_called()

        # The commit click is consumed. Only a later click may start another
        # rotation session from the still-selected structure.
        with mock.patch(
            "chemvas.ui.perspective_tool._perspective_tool_controller_for",
            return_value=next_controller,
        ):
            self.assertTrue(tool.on_mouse_press(new_event))

        next_controller.begin_selection_rotation.assert_called_once_with(new_event)
        self.assertTrue(tool._rotating)
        self.assertEqual(tool._last_pos, new_event.position())
        self.assertIsNone(tool._axis_lock)


if __name__ == "__main__":
    unittest.main()
