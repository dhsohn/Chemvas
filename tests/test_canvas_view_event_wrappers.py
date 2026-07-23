import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent, QTransform
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QGraphicsView
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.ui.canvas_hover_state import hover_state_for
    from chemvas.ui.canvas_insert_state import insert_state_for
    from chemvas.ui.canvas_pointer_controller import CanvasPointerController
    from chemvas.ui.canvas_view import CanvasView
    from chemvas.ui.canvas_window_access import set_error_callback_for
    from chemvas.ui.input_view_access import input_view_state_for


class _FakeEvent:
    def __init__(
        self,
        event_type=None,
        *,
        button=Qt.MouseButton.NoButton,
        buttons=Qt.MouseButton.NoButton,
        modifiers=Qt.KeyboardModifier.NoModifier,
        key=Qt.Key.Key_unknown,
        text="",
        gesture_type=None,
    ) -> None:
        self._event_type = event_type
        self._button = button
        self._buttons = buttons
        self._modifiers = modifiers
        self._key = key
        self._text = text
        self._gesture_type = gesture_type
        self.accept = mock.Mock()

    def type(self):
        return self._event_type

    def button(self):
        return self._button

    def buttons(self):
        return self._buttons

    def modifiers(self):
        return self._modifiers

    def key(self):
        return self._key

    def text(self):
        return self._text

    def gestureType(self):
        return self._gesture_type


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for canvas view tests"
)
class CanvasViewEventWrapperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _new_view(self, *, tool_active=None):
        view = CanvasView()
        hover_controller = SimpleNamespace(
            clear_hover_highlight=mock.Mock(),
            update_hover_highlight=mock.Mock(),
            refresh=mock.Mock(),
        )
        view.services.hover = hover_controller
        view.services.input.input_controller.hover = hover_controller
        insert_controller = SimpleNamespace(
            render_template_preview=mock.Mock(),
            render_smiles_preview=mock.Mock(),
            commit_template_insert=mock.Mock(),
            commit_smiles_insert=mock.Mock(),
            clear_template_preview=mock.Mock(),
            clear_smiles_preview=mock.Mock(),
        )
        view.services.structure.insert_controller = insert_controller
        input_view_state_for(view).base_transform = QTransform().translate(3.0, 4.0)
        view.setTransform(QTransform().scale(2.0, 2.0))
        hit_testing_service = SimpleNamespace(
            scene_pos_from_event=mock.Mock(return_value=QPointF(4.0, 5.0)),
            item_at_event=mock.Mock(return_value=None),
            bond_id_from_event=mock.Mock(return_value=None),
        )
        view.services.selection.hit_testing_service = hit_testing_service
        tool_controller = SimpleNamespace(active=tool_active)
        view.services.tool_controller = tool_controller
        scene_transform_controller = SimpleNamespace(apply_bond_style=mock.Mock())
        view.services.scene_operations.scene_transform_controller = (
            scene_transform_controller
        )
        view.services.input.pointer_controller = CanvasPointerController(
            view,
            hit_testing_service=hit_testing_service,
            insert_controller=insert_controller,
            hover_controller=hover_controller,
            tool_controller=tool_controller,
            scene_transform_controller=scene_transform_controller,
        )
        return view

    def test_mouse_press_event_handles_template_smiles_and_tool_branches(self) -> None:
        press_event = _FakeEvent(button=Qt.MouseButton.LeftButton)

        template_view = self._new_view(
            tool_active=SimpleNamespace(
                on_mouse_press=mock.Mock(
                    side_effect=AssertionError("tool should not run")
                )
            )
        )
        insert_state_for(template_view).template_active = True
        CanvasView.mousePressEvent(template_view, press_event)
        self.assertEqual(
            template_view.services.structure.insert_controller.commit_template_insert.call_count,
            1,
        )
        self.assertEqual(
            template_view.services.hover.clear_hover_highlight.call_count,
            1,
        )
        self.assertEqual(
            template_view.services.tool_controller.active.on_mouse_press.call_count, 0
        )

        smiles_view = self._new_view(
            tool_active=SimpleNamespace(
                on_mouse_press=mock.Mock(
                    side_effect=AssertionError("tool should not run")
                )
            )
        )
        insert_state_for(smiles_view).smiles_active = True
        CanvasView.mousePressEvent(smiles_view, press_event)
        self.assertEqual(
            smiles_view.services.structure.insert_controller.commit_smiles_insert.call_count,
            1,
        )
        self.assertEqual(smiles_view.services.hover.clear_hover_highlight.call_count, 1)
        self.assertEqual(
            smiles_view.services.tool_controller.active.on_mouse_press.call_count, 0
        )

        tool = SimpleNamespace(
            on_mouse_press=mock.Mock(return_value=True),
        )
        tool_view = self._new_view(tool_active=tool)
        CanvasView.mousePressEvent(tool_view, press_event)
        tool.on_mouse_press.assert_called_once_with(press_event)
        self.assertEqual(tool_view.services.hover.clear_hover_highlight.call_count, 1)
        self.assertEqual(
            tool_view.services.structure.insert_controller.commit_template_insert.call_count,
            0,
        )
        self.assertEqual(
            tool_view.services.structure.insert_controller.commit_smiles_insert.call_count,
            0,
        )

    def test_mouse_press_event_blocks_insert_and_drawing_tools_outside_sheet(
        self,
    ) -> None:
        press_event = _FakeEvent(button=Qt.MouseButton.LeftButton)
        outside_pos = QPointF(999.0, 999.0)

        template_tool = SimpleNamespace(
            name="bond",
            on_mouse_press=mock.Mock(
                side_effect=AssertionError("tool should not run outside sheet")
            ),
        )
        template_view = self._new_view(tool_active=template_tool)
        template_view.services.selection.hit_testing_service.scene_pos_from_event.return_value = outside_pos
        insert_state_for(template_view).template_active = True

        CanvasView.mousePressEvent(template_view, press_event)

        template_view.services.structure.insert_controller.commit_template_insert.assert_not_called()
        template_view.services.structure.insert_controller.clear_template_preview.assert_called_once_with()
        template_tool.on_mouse_press.assert_not_called()
        template_view.services.hover.clear_hover_highlight.assert_called_once_with()
        press_event.accept.assert_called_once_with()

        tool_event = _FakeEvent(button=Qt.MouseButton.LeftButton)
        drawing_tool = SimpleNamespace(
            name="mark",
            on_mouse_press=mock.Mock(
                side_effect=AssertionError("drawing tool should not run outside sheet")
            ),
        )
        tool_view = self._new_view(tool_active=drawing_tool)
        tool_view.services.selection.hit_testing_service.scene_pos_from_event.return_value = outside_pos

        CanvasView.mousePressEvent(tool_view, tool_event)

        drawing_tool.on_mouse_press.assert_not_called()
        tool_view.services.hover.clear_hover_highlight.assert_called_once_with()
        tool_event.accept.assert_called_once_with()

    def test_mouse_move_event_handles_preview_hover_and_tool_branches(self) -> None:
        move_event = _FakeEvent(buttons=Qt.MouseButton.NoButton)

        template_view = self._new_view()
        insert_state_for(template_view).template_active = True
        CanvasView.mouseMoveEvent(template_view, move_event)
        template_view.services.structure.insert_controller.render_template_preview.assert_called_once_with(
            QPointF(4.0, 5.0)
        )
        template_view.services.structure.insert_controller.render_smiles_preview.assert_not_called()
        template_view.services.hover.update_hover_highlight.assert_not_called()

        smiles_view = self._new_view()
        insert_state_for(smiles_view).smiles_active = True
        CanvasView.mouseMoveEvent(smiles_view, move_event)
        smiles_view.services.structure.insert_controller.render_smiles_preview.assert_called_once_with(
            QPointF(4.0, 5.0)
        )
        smiles_view.services.structure.insert_controller.render_template_preview.assert_not_called()
        smiles_view.services.hover.update_hover_highlight.assert_not_called()

        hover_view = self._new_view()
        hover_event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(4.0, 5.0),
            QPointF(4.0, 5.0),
            QPointF(4.0, 5.0),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        CanvasView.mouseMoveEvent(hover_view, hover_event)
        hover_view.services.hover.update_hover_highlight.assert_called_once_with(
            QPointF(4.0, 5.0)
        )
        hover_view.services.hover.clear_hover_highlight.assert_not_called()

        tool = SimpleNamespace(on_mouse_move=mock.Mock(return_value=True))
        tool_view = self._new_view(tool_active=tool)
        drag_event = _FakeEvent(buttons=Qt.MouseButton.LeftButton)
        CanvasView.mouseMoveEvent(tool_view, drag_event)
        tool.on_mouse_move.assert_called_once_with(drag_event)
        self.assertEqual(tool_view.services.hover.clear_hover_highlight.call_count, 1)
        tool_view.services.hover.update_hover_highlight.assert_not_called()

    def test_mouse_move_event_clears_previews_and_hover_outside_sheet(self) -> None:
        outside_pos = QPointF(999.0, 999.0)
        move_event = _FakeEvent(buttons=Qt.MouseButton.NoButton)

        template_view = self._new_view()
        template_view.services.selection.hit_testing_service.scene_pos_from_event.return_value = outside_pos
        insert_state_for(template_view).template_active = True
        CanvasView.mouseMoveEvent(template_view, move_event)

        template_view.services.structure.insert_controller.render_template_preview.assert_not_called()
        template_view.services.structure.insert_controller.clear_template_preview.assert_called_once_with()
        template_view.services.hover.clear_hover_highlight.assert_called_once_with()

        hover_view = self._new_view()
        hover_view.services.selection.hit_testing_service.scene_pos_from_event.return_value = outside_pos
        CanvasView.mouseMoveEvent(hover_view, move_event)

        hover_view.services.hover.update_hover_highlight.assert_not_called()
        hover_view.services.hover.clear_hover_highlight.assert_called_once_with()

    def test_mouse_release_event_refreshes_hover_after_tool_handler(self) -> None:
        tool = SimpleNamespace(on_mouse_release=mock.Mock(return_value=True))
        view = self._new_view(tool_active=tool)
        release_event = _FakeEvent(
            button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.NoButton
        )

        CanvasView.mouseReleaseEvent(view, release_event)

        tool.on_mouse_release.assert_called_once_with(release_event)
        view.services.hover.refresh.assert_called_once_with()
        view.services.hover.update_hover_highlight.assert_not_called()

    def test_mouse_release_event_contains_perspective_finalization_errors_at_qt_boundary(
        self,
    ) -> None:
        error_callback = mock.Mock()
        tool = SimpleNamespace(
            name="perspective",
            on_mouse_release=mock.Mock(
                side_effect=RuntimeError("injected rotation finalization failure")
            ),
        )
        view = self._new_view(tool_active=tool)
        set_error_callback_for(view, error_callback)
        release_event = _FakeEvent(
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.NoButton,
        )

        with mock.patch("chemvas.ui.canvas_view.logger.exception") as log_exception:
            CanvasView.mouseReleaseEvent(view, release_event)

        tool.on_mouse_release.assert_called_once_with(release_event)
        log_exception.assert_called_once_with(
            "Canvas mouse-%s handling failed",
            "release",
        )
        error_callback.assert_called_once_with(
            "The current interaction could not be completed. Try again."
        )
        release_event.accept.assert_called_once_with()
        view.services.hover.refresh.assert_not_called()

    def test_mouse_release_event_contains_error_callback_failures_too(self) -> None:
        tool = SimpleNamespace(
            name="perspective",
            on_mouse_release=mock.Mock(
                side_effect=KeyboardInterrupt("release failure")
            ),
        )
        view = self._new_view(tool_active=tool)
        set_error_callback_for(
            view,
            mock.Mock(side_effect=RuntimeError("notification failure")),
        )
        release_event = _FakeEvent(
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.NoButton,
        )

        with mock.patch("chemvas.ui.canvas_view.logger.exception") as log_exception:
            CanvasView.mouseReleaseEvent(view, release_event)

        self.assertEqual(
            log_exception.call_args_list,
            [
                mock.call("Canvas mouse-%s handling failed", "release"),
                mock.call("Canvas mouse-event error notification failed"),
            ],
        )
        release_event.accept.assert_called_once_with()

    def test_qt_mouse_release_callback_contains_perspective_finalization_error(
        self,
    ) -> None:
        error_callback = mock.Mock()
        tool = SimpleNamespace(
            name="perspective",
            on_mouse_press=mock.Mock(return_value=True),
            on_mouse_release=mock.Mock(
                side_effect=BaseExceptionGroup(
                    "rotation finalization failed",
                    [RuntimeError("release failure")],
                )
            ),
        )
        view = self._new_view(tool_active=tool)
        set_error_callback_for(view, error_callback)
        view.resize(240, 180)
        view.show()
        self.app.processEvents()
        position = view.viewport().rect().center()

        with mock.patch("chemvas.ui.canvas_view.logger.exception"):
            QTest.mousePress(
                view.viewport(),
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                position,
            )
            QTest.mouseRelease(
                view.viewport(),
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                position,
            )
            self.app.processEvents()

        error_callback.assert_called_once_with(
            "The current interaction could not be completed. Try again."
        )
        view.close()

    def test_qt_mouse_press_callback_contains_perspective_retry_error(self) -> None:
        error_callback = mock.Mock()
        tool = SimpleNamespace(
            name="perspective",
            on_mouse_press=mock.Mock(
                side_effect=BaseExceptionGroup(
                    "rotation retry failed",
                    [RuntimeError("press retry failure")],
                )
            ),
            on_mouse_release=mock.Mock(return_value=True),
        )
        view = self._new_view(tool_active=tool)
        set_error_callback_for(view, error_callback)
        view.resize(240, 180)
        view.show()
        self.app.processEvents()
        position = view.viewport().rect().center()

        with mock.patch("chemvas.ui.canvas_view.logger.exception"):
            QTest.mousePress(
                view.viewport(),
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                position,
            )
            QTest.mouseRelease(
                view.viewport(),
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                position,
            )
            self.app.processEvents()

        tool.on_mouse_press.assert_called_once()
        error_callback.assert_called_once_with(
            "The current interaction could not be completed. Try again."
        )
        view.close()

    def test_qt_mouse_double_click_callback_contains_perspective_retry_error(
        self,
    ) -> None:
        error_callback = mock.Mock()
        tool = SimpleNamespace(
            name="perspective",
            on_mouse_press=mock.Mock(
                side_effect=BaseExceptionGroup(
                    "rotation double-click retry failed",
                    [RuntimeError("double-click retry failure")],
                )
            ),
        )
        view = self._new_view(tool_active=tool)
        set_error_callback_for(view, error_callback)
        view.resize(240, 180)
        view.show()
        self.app.processEvents()
        position = view.viewport().rect().center()

        with mock.patch("chemvas.ui.canvas_view.logger.exception"):
            QTest.mouseDClick(
                view.viewport(),
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                position,
            )
            self.app.processEvents()

        tool.on_mouse_press.assert_called_once()
        error_callback.assert_called_once_with(
            "The current interaction could not be completed. Try again."
        )
        view.close()

    def test_qt_mouse_move_callback_contains_perspective_preview_error(self) -> None:
        error_callback = mock.Mock()
        tool = SimpleNamespace(
            name="perspective",
            on_mouse_press=mock.Mock(return_value=True),
            on_mouse_move=mock.Mock(side_effect=KeyboardInterrupt("preview failure")),
            on_mouse_release=mock.Mock(return_value=True),
        )
        view = self._new_view(tool_active=tool)
        set_error_callback_for(view, error_callback)
        view.resize(240, 180)
        view.show()
        self.app.processEvents()
        start = view.viewport().rect().center()
        end = start + QPointF(20.0, 10.0).toPoint()

        with mock.patch("chemvas.ui.canvas_view.logger.exception"):
            QTest.mousePress(
                view.viewport(),
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                start,
            )
            QTest.mouseMove(view.viewport(), end)
            QTest.mouseRelease(
                view.viewport(),
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                end,
            )
            self.app.processEvents()

        tool.on_mouse_move.assert_called_once()
        error_callback.assert_called_once_with(
            "The current interaction could not be completed. Try again."
        )
        view.close()

    def test_mouse_release_event_cancels_drawing_tool_outside_sheet(self) -> None:
        tool = SimpleNamespace(
            name="arrow",
            deactivate=mock.Mock(),
            activate=mock.Mock(),
            on_mouse_release=mock.Mock(
                side_effect=AssertionError("release should not commit outside sheet")
            ),
        )
        view = self._new_view(tool_active=tool)
        view.services.selection.hit_testing_service.scene_pos_from_event.return_value = QPointF(
            999.0, 999.0
        )
        release_event = _FakeEvent(
            button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.NoButton
        )

        CanvasView.mouseReleaseEvent(view, release_event)

        tool.deactivate.assert_called_once_with()
        tool.activate.assert_called_once_with()
        tool.on_mouse_release.assert_not_called()
        view.services.hover.clear_hover_highlight.assert_called_once_with()
        view.services.hover.refresh.assert_called_once_with()
        release_event.accept.assert_called_once_with()

    def test_viewport_event_clears_or_refreshes_hover_on_enter_leave_and_hide(
        self,
    ) -> None:
        with (
            mock.patch(
                "chemvas.ui.canvas_view_event_router.QTimer.singleShot"
            ) as single_shot,
            mock.patch.object(
                QGraphicsView,
                "viewportEvent",
                new=mock.Mock(return_value=False),
            ) as base_event,
        ):
            enter_view = self._new_view()
            base_event.reset_mock()
            enter_event = _FakeEvent(QEvent.Type.Enter)
            self.assertFalse(CanvasView.viewportEvent(enter_view, enter_event))
            single_shot.assert_called_once()
            delay, callback = single_shot.call_args.args
            self.assertEqual(delay, 0)
            enter_view.services.hover.update_hover_highlight.assert_not_called()
            callback()
            enter_view.services.hover.refresh.assert_called_once_with()
            enter_view.services.hover.update_hover_highlight.assert_not_called()
            self.assertEqual(
                enter_view.services.hover.clear_hover_highlight.call_count,
                0,
            )
            self.assertEqual(base_event.call_count, 1)

            for event_type in (QEvent.Type.Leave, QEvent.Type.Hide):
                sub_view = self._new_view()
                base_event.reset_mock()
                sub_event = _FakeEvent(event_type)
                self.assertFalse(CanvasView.viewportEvent(sub_view, sub_event))
                sub_view.services.hover.clear_hover_highlight.assert_called_once_with()
                self.assertEqual(base_event.call_count, 1)

    def test_viewport_event_mouse_move_routes_preview_and_hover_updates(self) -> None:
        with mock.patch.object(
            QGraphicsView,
            "viewportEvent",
            new=mock.Mock(return_value=False),
        ) as base_event:
            template_view = self._new_view()
            base_event.reset_mock()
            insert_state_for(template_view).template_active = True
            template_event = _FakeEvent(
                QEvent.Type.MouseMove, buttons=Qt.MouseButton.NoButton
            )
            self.assertFalse(CanvasView.viewportEvent(template_view, template_event))
            template_view.services.structure.insert_controller.render_template_preview.assert_called_once_with(
                QPointF(4.0, 5.0)
            )
            self.assertEqual(base_event.call_count, 1)

            smiles_view = self._new_view()
            base_event.reset_mock()
            insert_state_for(smiles_view).smiles_active = True
            smiles_event = _FakeEvent(
                QEvent.Type.MouseMove, buttons=Qt.MouseButton.NoButton
            )
            self.assertFalse(CanvasView.viewportEvent(smiles_view, smiles_event))
            smiles_view.services.structure.insert_controller.render_smiles_preview.assert_called_once_with(
                QPointF(4.0, 5.0)
            )
            self.assertEqual(base_event.call_count, 1)

            hover_view = self._new_view()
            base_event.reset_mock()
            hover_event = _FakeEvent(
                QEvent.Type.MouseMove, buttons=Qt.MouseButton.NoButton
            )
            self.assertFalse(CanvasView.viewportEvent(hover_view, hover_event))
            hover_view.services.hover.update_hover_highlight.assert_called_once_with(
                QPointF(4.0, 5.0)
            )
            self.assertEqual(base_event.call_count, 1)

            drag_view = self._new_view()
            base_event.reset_mock()
            drag_event = _FakeEvent(
                QEvent.Type.MouseMove, buttons=Qt.MouseButton.LeftButton
            )
            self.assertFalse(CanvasView.viewportEvent(drag_view, drag_event))
            drag_view.services.hover.clear_hover_highlight.assert_called_once_with()
            self.assertEqual(base_event.call_count, 1)

    def test_event_accepts_shortcut_override_and_native_gesture(self) -> None:
        with mock.patch.object(
            QGraphicsView, "event", new=mock.Mock(return_value=False)
        ) as base_event:
            shortcut_view = self._new_view()
            base_event.reset_mock()
            hover_state_for(shortcut_view).atom_id = 7
            shortcut_event = _FakeEvent(
                QEvent.Type.ShortcutOverride,
                modifiers=Qt.KeyboardModifier.NoModifier,
                key=Qt.Key.Key_Return,
                text="",
            )
            self.assertTrue(CanvasView.event(shortcut_view, shortcut_event))
            shortcut_event.accept.assert_called_once_with()
            shortcut_view.services.hover.refresh.assert_called_once_with()
            self.assertEqual(base_event.call_count, 0)

            class _FakeNativeGestureEvent(_FakeEvent):
                pass

            native_view = self._new_view()
            base_event.reset_mock()
            native_event = _FakeNativeGestureEvent(
                QEvent.Type.NativeGesture,
                gesture_type=Qt.NativeGestureType.PanNativeGesture,
            )
            with mock.patch(
                "chemvas.ui.canvas_view_event_router.QNativeGestureEvent",
                _FakeNativeGestureEvent,
            ):
                self.assertTrue(CanvasView.event(native_view, native_event))
            native_event.accept.assert_called_once_with()
            self.assertTrue(
                input_view_state_for(native_view).base_transform.isIdentity()
            )
            self.assertTrue(native_view.transform().isIdentity())
            self.assertEqual(base_event.call_count, 0)

    def test_scroll_contents_by_resets_transform_and_clears_hover(self) -> None:
        with mock.patch.object(
            QGraphicsView,
            "scrollContentsBy",
            new=mock.Mock(return_value=None),
        ) as base_scroll:
            view = self._new_view()
            base_scroll.reset_mock()
            CanvasView.scrollContentsBy(view, 12, -4)

            base_scroll.assert_called_once_with(12, -4)
            self.assertTrue(input_view_state_for(view).base_transform.isIdentity())
            self.assertTrue(view.transform().isIdentity())
            view.services.hover.clear_hover_highlight.assert_called_once_with()
            view.services.hover.refresh.assert_not_called()
            view.services.hover.update_hover_highlight.assert_not_called()
