import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtWidgets import QApplication, QGraphicsView
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.canvas_insert_state import insert_state_for
    from ui.canvas_pointer_controller import CanvasPointerController
    from ui.canvas_view import CanvasView


class _FakeEvent:
    def __init__(
        self,
        event_type=None,
        *,
        button=Qt.MouseButton.NoButton,
        buttons=Qt.MouseButton.NoButton,
        pos=None,
        global_pos=None,
        modifiers=Qt.KeyboardModifier.NoModifier,
        key=Qt.Key.Key_unknown,
        text="",
    ) -> None:
        self._event_type = event_type
        self._button = button
        self._buttons = buttons
        self._pos = QPointF(0.0, 0.0) if pos is None else pos
        self._global_pos = QPointF(10.0, 20.0) if global_pos is None else global_pos
        self._modifiers = modifiers
        self._key = key
        self._text = text
        self.accept = mock.Mock()

    def type(self):
        return self._event_type

    def button(self):
        return self._button

    def buttons(self):
        return self._buttons

    def position(self):
        return self._pos

    def globalPosition(self):
        return self._global_pos

    def modifiers(self):
        return self._modifiers

    def key(self):
        return self._key

    def text(self):
        return self._text


class _FakeAction:
    def __init__(self, label: str) -> None:
        self.label = label
        self.checkable = False
        self.checked = False
        self._callback = None
        self.triggered = SimpleNamespace(connect=self._connect)

    def setCheckable(self, value: bool) -> None:
        self.checkable = value

    def setChecked(self, value: bool) -> None:
        self.checked = value

    def _connect(self, callback) -> None:
        self._callback = callback

    def trigger(self) -> None:
        self._callback(False)


class _FakeMenu:
    instances = []

    def __init__(self, parent=None) -> None:
        self.parent = parent
        self.actions = []
        self.exec_pos = None
        _FakeMenu.instances.append(self)

    def addAction(self, label: str):
        action = _FakeAction(label)
        self.actions.append(action)
        return action

    def exec(self, pos) -> None:
        self.exec_pos = pos


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewEventFallthroughTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _new_view(self, *, tool_active=None):
        view = CanvasView()
        hover_scene_service = SimpleNamespace(clear_hover_highlight=mock.Mock())
        view.services.hover_scene_service = hover_scene_service
        insert_controller = SimpleNamespace(
            render_template_preview=mock.Mock(),
            render_smiles_preview=mock.Mock(),
            commit_template_insert=mock.Mock(),
            commit_smiles_insert=mock.Mock(),
        )
        view.services.insert_controller = insert_controller
        hover_interaction_service = SimpleNamespace(update_hover_highlight=mock.Mock())
        view.services.hover_interaction_service = hover_interaction_service
        hover_refresh = mock.Mock()
        view.hover_refresh = hover_refresh
        hit_testing_service = SimpleNamespace(
            scene_pos_from_event=mock.Mock(return_value=QPointF(4.0, 5.0)),
            item_at_event=mock.Mock(return_value=None),
            bond_id_from_event=mock.Mock(return_value=None),
        )
        view.services.hit_testing_service = hit_testing_service
        tool_controller = SimpleNamespace(active=tool_active)
        view.services.tools = tool_controller
        scene_transform_controller = SimpleNamespace(apply_bond_style=mock.Mock())
        view.services.scene_transform_controller = scene_transform_controller
        view.services.pointer_controller = CanvasPointerController(
            view,
            hit_testing_service=hit_testing_service,
            insert_controller=insert_controller,
            hover_interaction_service=hover_interaction_service,
            tool_controller=tool_controller,
            scene_transform_controller=scene_transform_controller,
            hover_refresh=hover_refresh,
        )
        return view

    def test_mouse_press_event_right_click_and_tool_false_fall_through_to_super(self) -> None:
        with mock.patch.object(QGraphicsView, "mousePressEvent", new=mock.Mock(return_value=None)) as base_press:
            template_view = self._new_view()
            insert_state_for(template_view).template_active = True
            template_view.model.bonds = []

            CanvasView.mousePressEvent(template_view, _FakeEvent(button=Qt.MouseButton.RightButton))

            template_view.services.insert_controller.commit_template_insert.assert_not_called()
            base_press.assert_called_once()
            template_view.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()

            tool = SimpleNamespace(on_mouse_press=mock.Mock(return_value=False))
            tool_view = self._new_view(tool_active=tool)
            base_press.reset_mock()

            CanvasView.mousePressEvent(tool_view, _FakeEvent(button=Qt.MouseButton.LeftButton))

            tool.on_mouse_press.assert_called_once()
            base_press.assert_called_once()
            tool_view.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()

    def test_mouse_press_clears_hover_before_perspective_captures_scene(self) -> None:
        tool = SimpleNamespace(
            name="perspective",
            on_mouse_press=mock.Mock(return_value=True),
        )
        view = self._new_view(tool_active=tool)
        event = _FakeEvent(button=Qt.MouseButton.LeftButton)
        calls = mock.Mock()
        calls.attach_mock(
            view.services.hover_scene_service.clear_hover_highlight,
            "clear_hover",
        )
        calls.attach_mock(tool.on_mouse_press, "begin_rotation")

        CanvasView.mousePressEvent(view, event)

        self.assertEqual(
            calls.mock_calls,
            [mock.call.clear_hover(), mock.call.begin_rotation(event)],
        )

    def test_mouse_press_preserves_hover_until_non_perspective_tool_handles_target(self) -> None:
        tool = SimpleNamespace(
            name="bond",
            on_mouse_press=mock.Mock(return_value=True),
        )
        view = self._new_view(tool_active=tool)
        event = _FakeEvent(button=Qt.MouseButton.LeftButton)
        calls = mock.Mock()
        calls.attach_mock(tool.on_mouse_press, "handle_target")
        calls.attach_mock(
            view.services.hover_scene_service.clear_hover_highlight,
            "clear_hover",
        )

        CanvasView.mousePressEvent(view, event)

        self.assertEqual(
            calls.mock_calls,
            [mock.call.handle_target(event), mock.call.clear_hover()],
        )

    def test_mouse_press_event_right_click_on_double_bond_shows_variant_menu(self) -> None:
        from core.model import Atom, Bond
        view = self._new_view()
        view.model.atoms = {
            1: Atom("C", 0.0, 0.0),
            2: Atom("C", 20.0, 0.0),
        }
        view.model.bonds = [Bond(1, 2, 2, style="double_center")]
        view.services.hit_testing_service.item_at_event.return_value = None
        view.services.hit_testing_service.bond_id_from_event.return_value = 0
        view.apply_bond_style = mock.Mock(side_effect=AssertionError("canvas bond style wrapper should not run"))
        scene_transform_controller = SimpleNamespace(apply_bond_style=mock.Mock())
        view.services.scene_transform_controller = scene_transform_controller
        _FakeMenu.instances = []

        controller = CanvasPointerController(
            view,
            hit_testing_service=view.services.hit_testing_service,
            insert_controller=view.services.insert_controller,
            hover_interaction_service=view.services.hover_interaction_service,
            tool_controller=view.services.tools,
            scene_transform_controller=scene_transform_controller,
        )
        handled = controller._show_double_bond_context_menu(
            _FakeEvent(button=Qt.MouseButton.RightButton, global_pos=QPointF(30.0, 40.0)),
            menu_factory=_FakeMenu,
        )

        self.assertTrue(handled)
        menu = _FakeMenu.instances[-1]
        self.assertEqual([action.label for action in menu.actions], ["Inward", "Centered", "Outward"])
        self.assertEqual([action.checked for action in menu.actions], [False, True, False])
        self.assertEqual(menu.exec_pos, QPointF(30.0, 40.0).toPoint())

        menu.actions[2].trigger()

        scene_transform_controller.apply_bond_style.assert_called_once_with(0, "double_outer", 2)
        view.apply_bond_style.assert_not_called()

    def test_right_click_on_bold_double_preserves_bold_family_for_all_positions(self) -> None:
        from core.model import Atom, Bond

        cases = (
            ("bold_in", [True, False, False]),
            ("bold_center", [False, True, False]),
            ("bold_out", [False, False, True]),
            ("bold", [True, False, False]),
        )
        for current_style, checked in cases:
            with self.subTest(current_style=current_style):
                view = self._new_view()
                view.model.atoms = {
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 20.0, 0.0),
                }
                view.model.bonds = [Bond(1, 2, 2, style=current_style)]
                view.services.hit_testing_service.item_at_event.return_value = None
                view.services.hit_testing_service.bond_id_from_event.return_value = 0
                scene_transform_controller = SimpleNamespace(apply_bond_style=mock.Mock())
                controller = CanvasPointerController(
                    view,
                    hit_testing_service=view.services.hit_testing_service,
                    insert_controller=view.services.insert_controller,
                    hover_interaction_service=view.services.hover_interaction_service,
                    tool_controller=view.services.tools,
                    scene_transform_controller=scene_transform_controller,
                )
                _FakeMenu.instances = []

                handled = controller._show_double_bond_context_menu(
                    _FakeEvent(button=Qt.MouseButton.RightButton, global_pos=QPointF(30.0, 40.0)),
                    menu_factory=_FakeMenu,
                )

                self.assertTrue(handled)
                menu = _FakeMenu.instances[-1]
                self.assertEqual([action.label for action in menu.actions], ["Inward", "Centered", "Outward"])
                self.assertEqual([action.checked for action in menu.actions], checked)
                for action in menu.actions:
                    action.trigger()
                self.assertEqual(
                    scene_transform_controller.apply_bond_style.call_args_list,
                    [
                        mock.call(0, "bold_in", 2),
                        mock.call(0, "bold_center", 2),
                        mock.call(0, "bold_out", 2),
                    ],
                )

    def test_mouse_double_click_event_routes_non_select_tools_and_select_tool_falls_through(self) -> None:
        with mock.patch.object(
            QGraphicsView,
            "mouseDoubleClickEvent",
            new=mock.Mock(return_value=None),
        ) as base_double:
            tool = SimpleNamespace(name="bond", on_mouse_press=mock.Mock(return_value=True))
            tool_view = self._new_view(tool_active=tool)

            CanvasView.mouseDoubleClickEvent(tool_view, _FakeEvent(button=Qt.MouseButton.LeftButton))

            tool.on_mouse_press.assert_called_once()
            base_double.assert_not_called()
            tool_view.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()

            select_tool = SimpleNamespace(name="select", on_mouse_press=mock.Mock(return_value=True))
            select_view = self._new_view(tool_active=select_tool)
            base_double.reset_mock()

            CanvasView.mouseDoubleClickEvent(select_view, _FakeEvent(button=Qt.MouseButton.LeftButton))

            select_tool.on_mouse_press.assert_not_called()
            base_double.assert_called_once()
            select_view.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()

    def test_mouse_move_event_fallthrough_calls_super_for_hover_and_drag_paths(self) -> None:
        with mock.patch.object(QGraphicsView, "mouseMoveEvent", new=mock.Mock(return_value=None)) as base_move:
            hover_tool = SimpleNamespace(on_mouse_move=mock.Mock(return_value=False))
            hover_view = self._new_view(tool_active=hover_tool)

            CanvasView.mouseMoveEvent(hover_view, _FakeEvent(buttons=Qt.MouseButton.NoButton))

            hover_view.services.hover_interaction_service.update_hover_highlight.assert_called_once_with(
                QPointF(4.0, 5.0)
            )
            hover_view.services.hover_scene_service.clear_hover_highlight.assert_not_called()
            base_move.assert_called_once()

            drag_tool = SimpleNamespace(on_mouse_move=mock.Mock(return_value=False))
            drag_view = self._new_view(tool_active=drag_tool)
            base_move.reset_mock()

            CanvasView.mouseMoveEvent(drag_view, _FakeEvent(buttons=Qt.MouseButton.LeftButton))

            drag_view.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()
            drag_view.services.hover_interaction_service.update_hover_highlight.assert_not_called()
            base_move.assert_called_once()

    def test_mouse_release_event_tool_false_path_calls_super_and_refresh(self) -> None:
        tool = SimpleNamespace(on_mouse_release=mock.Mock(return_value=False))
        view = self._new_view(tool_active=tool)

        with (
            mock.patch.object(QGraphicsView, "mouseReleaseEvent", new=mock.Mock(return_value=None)) as base_release,
        ):
            CanvasView.mouseReleaseEvent(view, _FakeEvent(button=Qt.MouseButton.LeftButton))

        tool.on_mouse_release.assert_called_once()
        base_release.assert_called_once()
        view.hover_refresh.assert_called_once_with()
        view.services.hover_scene_service.clear_hover_highlight.assert_not_called()

    def test_viewport_event_generic_passthrough_and_event_false_paths_use_super(self) -> None:
        with mock.patch.object(QGraphicsView, "viewportEvent", new=mock.Mock(return_value=True)) as base_viewport:
            view = self._new_view()
            base_viewport.reset_mock()
            self.assertTrue(CanvasView.viewportEvent(view, _FakeEvent(QEvent.Type.FocusIn)))
            base_viewport.assert_called_once()
            view.services.hover_scene_service.clear_hover_highlight.assert_not_called()
            view.services.hover_interaction_service.update_hover_highlight.assert_not_called()

        with mock.patch.object(QGraphicsView, "event", new=mock.Mock(return_value=False)) as base_event:
            view = self._new_view()
            base_event.reset_mock()
            with mock.patch("ui.hover_service_bundle.refresh_hover_from_cursor_for") as refresh_hover:
                self.assertFalse(CanvasView.event(view, _FakeEvent(QEvent.Type.ShortcutOverride)))
            base_event.assert_called_once()
            refresh_hover.assert_called_once()
            self.assertIs(refresh_hover.call_args.args[0], view)
            self.assertIn("update_hover_highlight", refresh_hover.call_args.kwargs)
            self.assertIn("clear_hover_highlight", refresh_hover.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
