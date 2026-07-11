import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QFont
    from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsTextItem
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.document_state import _validate_note_states
    from PyQt6.QtGui import QTextCursor
    from ui.canvas_note_controller import CanvasNoteController, _EditingNoteSnapshot
    from ui.canvas_scene_items_state import (
        CanvasSceneItemsState,
        selected_notes_for,
        set_selected_notes_for,
    )
    from ui.canvas_text_style_state import CanvasTextStyleState, set_text_style_for
    from ui.history_commands import UpdateSceneItemCommand
    from ui.note_item import NoteItem
    from ui.note_item_access import committed_note_text_for
    from ui.scene_item_restore import create_note_item_from_state
    from ui.scene_item_state_serialization import note_state_dict
    from ui.selection_service_bundle import build_selection_services
    from ui.selection_style_state import SelectionStyleState


def _history_service(push=None):
    return SimpleNamespace(push=push if push is not None else mock.Mock())


def _attach_history_service(canvas):
    service = _history_service(getattr(canvas, "push_command", None))
    services = getattr(canvas, "services", None)
    if services is None:
        services = SimpleNamespace()
        canvas.services = services
    services.history_service = service
    return service


def _note_controller(canvas, **kwargs) -> CanvasNoteController:
    history_service = getattr(getattr(canvas, "services", None), "history_service", None)
    return CanvasNoteController(canvas, history_service=history_service, **kwargs)


def _selection_controller_for(canvas):
    graph_service = SimpleNamespace(
        expand_connected_atoms=mock.Mock(return_value=set()),
        connected_components=lambda atom_ids: [set(atom_ids)] if atom_ids else [],
    )
    return build_selection_services(canvas, graph_service=graph_service).selection_controller


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for note controller tests")
class CanvasNoteControllerUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_begin_note_edit_selects_note_and_focuses_editor(self) -> None:
        scene = QGraphicsScene()
        item = QGraphicsTextItem("Mechanism")
        scene.addItem(item)

        selected_notes = []

        def _select_note(target, additive: bool = False) -> None:
            self.assertIs(target, item)
            self.assertFalse(additive)
            selected_notes.clear()
            selected_notes.append(target)

        canvas = SimpleNamespace(
            selected_notes=selected_notes,
            services=SimpleNamespace(selection_controller=SimpleNamespace(select_note=mock.Mock(side_effect=_select_note))),
            scene=lambda: scene,
            setFocus=mock.Mock(),
        )
        _attach_history_service(canvas)
        controller = _note_controller(canvas)

        controller.begin_note_edit(item)

        canvas.services.selection_controller.select_note.assert_called_once_with(item, additive=False)
        self.assertEqual(selected_notes, [item])
        canvas.setFocus.assert_called_once_with(Qt.FocusReason.MouseFocusReason)
        self.assertIs(scene.focusItem(), item)
        self.assertTrue(item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction)
        self.assertTrue(bool(item.flags() & item.GraphicsItemFlag.ItemIsFocusable))
        self.assertTrue(item.textCursor().hasSelection())

    def test_create_text_note_registers_scene_item_and_applies_style(self) -> None:
        scene = QGraphicsScene()
        pos = QPointF(3.0, 4.0)

        def _attach(target) -> None:
            scene.addItem(target)
            canvas.note_items.append(target)
            canvas._make_selectable(target)

        attach_mock = mock.Mock(side_effect=_attach)
        canvas = SimpleNamespace(
            note_items=[],
            services=SimpleNamespace(
                scene_item_controller=SimpleNamespace(attach_scene_item=attach_mock),
            ),
            _make_selectable=mock.Mock(),
        )
        _attach_history_service(canvas)
        controller = _note_controller(canvas)
        controller.apply_note_style = mock.Mock()

        created = controller.create_text_note(pos, "Mechanism")

        self.assertIsInstance(created, NoteItem)
        self.assertEqual(created.toPlainText(), "Mechanism")
        self.assertEqual(committed_note_text_for(created), "Mechanism")
        self.assertEqual(created.data(0), "note")
        self.assertEqual(created.pos(), pos)
        self.assertEqual(canvas.note_items, [created])
        self.assertIn(created, scene.items())
        attach_mock.assert_called_once_with(created)
        canvas._make_selectable.assert_called_once_with(created)
        controller.apply_note_style.assert_called_once_with(created)

    def test_create_note_static_live_scene_descriptor_failure_precedes_apply_and_retries(
        self,
    ) -> None:
        scene = QGraphicsScene()
        note_items: list[QGraphicsTextItem] = []
        attach = mock.Mock(
            side_effect=lambda item: (
                scene.addItem(item),
                note_items.append(item),
            )
        )

        class FailOnceSceneCanvas:
            scene_calls = 0

            @property
            def scene(self):
                self.scene_calls += 1
                if self.scene_calls == 1:
                    raise AttributeError(
                        "live canvas scene descriptor failed internally"
                    )
                return lambda: scene

        canvas = FailOnceSceneCanvas()
        canvas.scene_items_state = CanvasSceneItemsState(note_items=note_items)
        canvas.services = SimpleNamespace(
            history_service=_history_service(),
            scene_item_controller=SimpleNamespace(attach_scene_item=attach),
        )
        controller = _note_controller(canvas)
        controller.apply_note_style = mock.Mock()

        with self.assertRaisesRegex(
            AttributeError,
            "live canvas scene descriptor failed internally",
        ):
            controller.create_text_note(QPointF(3.0, 4.0), "first")

        attach.assert_not_called()
        controller.apply_note_style.assert_not_called()
        self.assertEqual(note_items, [])
        tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
        self.assertTrue(tracker is None or tracker.depth == 0)

        created = controller.create_text_note(QPointF(5.0, 6.0), "retry")

        attach.assert_called_once_with(created)
        controller.apply_note_style.assert_called_once_with(created)
        self.assertEqual(note_items, [created])
        self.assertIs(created.scene(), scene)
        self.assertEqual(scene._chemvas_scene_rect_tracker.depth, 0)

    def test_create_text_note_removes_attached_item_if_style_application_raises(self) -> None:
        scene = QGraphicsScene()
        pos = QPointF(3.0, 4.0)
        removed = []

        def _attach(target) -> None:
            scene.addItem(target)
            canvas.note_items.append(target)

        def _remove(target) -> None:
            removed.append(target)
            if target in canvas.note_items:
                canvas.note_items.remove(target)
            scene.removeItem(target)

        canvas = SimpleNamespace(
            note_items=[],
            services=SimpleNamespace(
                scene_item_controller=SimpleNamespace(
                    attach_scene_item=mock.Mock(side_effect=_attach),
                    remove_scene_item=mock.Mock(side_effect=_remove),
                ),
            ),
        )
        _attach_history_service(canvas)
        controller = _note_controller(canvas)
        controller.apply_note_style = mock.Mock(side_effect=RuntimeError("style failed"))

        with self.assertRaisesRegex(RuntimeError, "style failed"):
            controller.create_text_note(pos, "Mechanism")

        self.assertEqual(canvas.note_items, [])
        self.assertEqual(len(removed), 1)
        self.assertNotIn(removed[0], scene.items())

    def test_create_text_note_focus_rollback_uses_captured_ports_and_retries(
        self,
    ) -> None:
        primary = RuntimeError("new note style failed")

        class FocusScene(QGraphicsScene):
            focus_getter_reads = 0
            focus_setter_reads = 0
            focus_setter_calls = 0
            fail_port_lookup = False
            fail_next_focus_set = False

            @property
            def focusItem(self):
                self.focus_getter_reads += 1
                if self.fail_port_lookup:
                    raise SystemExit("new-note focus getter was re-read")
                return lambda: QGraphicsScene.focusItem(self)

            @property
            def setFocusItem(self):
                self.focus_setter_reads += 1
                if self.fail_port_lookup:
                    raise SystemExit("new-note focus setter was re-read")
                return self._set_focus_item

            def _set_focus_item(self, item) -> None:
                self.focus_setter_calls += 1
                if self.fail_next_focus_set:
                    self.fail_next_focus_set = False
                    raise KeyboardInterrupt("new-note focus restore failed once")
                QGraphicsScene.setFocusItem(self, item)

        scene = FocusScene()
        original_focus = QGraphicsTextItem("original focus")
        original_focus.setFlag(
            original_focus.GraphicsItemFlag.ItemIsFocusable,
            True,
        )
        scene.addItem(original_focus)
        QGraphicsScene.setFocusItem(scene, original_focus)
        note_items: list[QGraphicsTextItem] = []
        created_items: list[QGraphicsTextItem] = []

        def attach(item) -> None:
            created_items.append(item)
            item.setFlag(item.GraphicsItemFlag.ItemIsFocusable, True)
            scene.addItem(item)
            note_items.append(item)
            QGraphicsScene.setFocusItem(scene, item)

        def remove(item) -> None:
            if item in note_items:
                note_items.remove(item)
            if item.scene() is scene:
                scene.removeItem(item)

        canvas = SimpleNamespace(
            scene=lambda: scene,
            scene_items_state=CanvasSceneItemsState(note_items=note_items),
            services=SimpleNamespace(
                scene_item_controller=SimpleNamespace(
                    attach_scene_item=attach,
                    remove_scene_item=remove,
                ),
            ),
        )
        _attach_history_service(canvas)
        controller = _note_controller(canvas)

        def style_then_fail(_item) -> None:
            scene.fail_port_lookup = True
            scene.fail_next_focus_set = True
            raise primary

        controller.apply_note_style = mock.Mock(side_effect=style_then_fail)

        with self.assertRaisesRegex(RuntimeError, "new note style failed") as caught:
            controller.create_text_note(QPointF(3.0, 4.0), "Mechanism")

        self.assertIs(caught.exception, primary)
        self.assertEqual(note_items, [])
        self.assertEqual(len(created_items), 1)
        self.assertIsNone(created_items[0].scene())
        self.assertIs(QGraphicsScene.focusItem(scene), original_focus)
        # Qt scene subclasses cannot interpose on the captured focus getter:
        # rollback authority is bound directly to QGraphicsScene.focusItem.
        self.assertEqual(scene.focus_getter_reads, 0)
        self.assertEqual(scene.focus_setter_reads, 1)
        self.assertEqual(scene.focus_setter_calls, 2)
        self.assertTrue(
            any(
                "new-note focus restore failed once" in note
                for note in getattr(primary, "__notes__", [])
            )
        )

    def test_bulk_note_creation_never_scans_existing_scene_items(self) -> None:
        scene = QGraphicsScene()
        note_items = []
        scene_items_state = CanvasSceneItemsState(note_items=note_items)

        def attach(item) -> None:
            scene.addItem(item)
            note_items.append(item)

        def remove(item) -> None:
            if item in note_items:
                note_items.remove(item)
            if item.scene() is scene:
                scene.removeItem(item)

        canvas = SimpleNamespace(
            scene=lambda: scene,
            scene_items_state=scene_items_state,
            services=SimpleNamespace(
                scene_item_controller=SimpleNamespace(
                    attach_scene_item=attach,
                    remove_scene_item=remove,
                ),
            ),
        )
        _attach_history_service(canvas)
        controller = _note_controller(canvas)
        controller.apply_note_style = mock.Mock()

        with (
            mock.patch(
                "ui.history_commands._scene_items_snapshot",
                side_effect=AssertionError("bulk note creation scanned the whole scene"),
            ) as scene_scan,
            mock.patch(
                "ui.canvas_note_controller._scene_runtime_snapshot",
                side_effect=AssertionError("note creation captured full runtime"),
            ) as runtime_scan,
        ):
            for index in range(100):
                controller.create_text_note(
                    QPointF(float(index), 0.0),
                    f"note {index}",
                )

        scene_scan.assert_not_called()
        runtime_scan.assert_not_called()
        self.assertEqual(len(note_items), 100)

    def test_far_note_system_exit_restores_auto_scene_rect_and_future_growth(self) -> None:
        scene = QGraphicsScene()
        scene.addRect(0.0, 0.0, 10.0, 10.0)
        original_rect = scene.sceneRect()
        note_items = []
        canvas = SimpleNamespace(
            scene=lambda: scene,
            scene_items_state=CanvasSceneItemsState(note_items=note_items),
        )

        def attach(item) -> None:
            scene.addItem(item)
            note_items.append(item)

        def remove(item) -> None:
            if item in note_items:
                note_items.remove(item)
            if item.scene() is scene:
                scene.removeItem(item)

        canvas.services = SimpleNamespace(
            scene_item_controller=SimpleNamespace(
                attach_scene_item=attach,
                remove_scene_item=remove,
            )
        )
        _attach_history_service(canvas)
        controller = _note_controller(canvas)

        def style_then_exit(_item) -> None:
            # The temporary guard keeps even an eager downstream sceneRect
            # read from poisoning Qt's grow-only automatic cache.
            self.assertEqual(scene.sceneRect(), original_rect)
            raise SystemExit("note style terminated")

        controller.apply_note_style = mock.Mock(side_effect=style_then_exit)

        with self.assertRaisesRegex(SystemExit, "note style terminated"):
            controller.create_text_note(QPointF(10_000.0, 0.0), "far")

        self.assertEqual(note_items, [])
        self.assertEqual(scene.sceneRect(), original_rect)
        future = scene.addRect(20_000.0, 0.0, 10.0, 10.0)
        self.assertGreater(scene.sceneRect().right(), 20_000.0)
        scene.removeItem(future)

    def test_note_metadata_capture_exit_precedes_auto_scene_rect_guard(self) -> None:
        scene = QGraphicsScene()
        scene.addRect(0.0, 0.0, 10.0, 10.0)
        canvas = SimpleNamespace(scene=lambda: scene)
        controller = CanvasNoteController(canvas)

        with mock.patch(
            "ui.canvas_note_controller.committed_note_text_for",
            side_effect=SystemExit("note metadata capture terminated"),
        ):
            with self.assertRaisesRegex(
                SystemExit,
                "note metadata capture terminated",
            ):
                controller.create_text_note(QPointF(10_000.0, 0.0), "far")

        tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
        self.assertTrue(tracker is None or tracker.depth == 0)
        future = scene.addRect(20_000.0, 0.0, 10.0, 10.0)
        self.assertGreater(scene.sceneRect().right(), 20_000.0)
        scene.removeItem(future)

    def _editing_note_controller(self, text: str):
        scene = QGraphicsScene()
        canvas = SimpleNamespace(scene=lambda: scene, text_style_state=CanvasTextStyleState())
        note = NoteItem(canvas)
        note.setData(0, "note")
        note.setPlainText(text)
        scene.addItem(note)
        scene.setFocusItem(note)
        cursor = note.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        note.setTextCursor(cursor)
        return CanvasNoteController(canvas), note

    def test_toggle_superscript_and_subscript_mark_selected_text(self) -> None:
        controller, note = self._editing_note_controller("2")

        controller.toggle_text_superscript()
        self.assertIn("vertical-align:super", note.toHtml())

        controller.toggle_text_superscript()
        self.assertNotIn("vertical-align:super", note.toHtml())

        controller.toggle_text_subscript()
        self.assertIn("vertical-align:sub", note.toHtml())

    def test_toggle_bold_italic_and_adjust_size_change_char_format(self) -> None:
        controller, note = self._editing_note_controller("label")

        controller.toggle_text_bold()
        controller.toggle_text_italic()
        controller.adjust_text_size(6)

        cursor = note.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        char_format = cursor.charFormat()
        self.assertGreater(char_format.fontWeight(), QFont.Weight.Normal)
        self.assertTrue(char_format.fontItalic())
        self.assertGreater(char_format.fontPointSize(), 0.0)

    def test_set_font_family_and_alignment_on_editing_note(self) -> None:
        controller, note = self._editing_note_controller("memo")

        controller.set_text_font_family("Courier New")
        controller.set_text_alignment("center")

        html = note.toHtml()
        self.assertIn("Courier New", html)
        cursor = note.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        self.assertEqual(cursor.blockFormat().alignment(), Qt.AlignmentFlag.AlignHCenter)

    def test_set_alignment_on_selected_note_records_history(self) -> None:
        scene = QGraphicsScene()
        push_command = mock.Mock()
        canvas = SimpleNamespace(
            scene=lambda: scene,
            text_style_state=CanvasTextStyleState(),
            services=SimpleNamespace(history_service=_history_service(push_command)),
        )
        note = NoteItem(canvas)
        note.setData(0, "note")
        note.setPlainText("memo")
        scene.addItem(note)
        set_selected_notes_for(canvas, [note])
        controller = _note_controller(canvas)

        controller.set_text_alignment("right")

        cursor = note.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        self.assertEqual(cursor.blockFormat().alignment(), Qt.AlignmentFlag.AlignRight)
        self.assertEqual(push_command.call_count, 1)
        self.assertIsInstance(push_command.call_args.args[0], UpdateSceneItemCommand)

    def test_selected_note_batch_serializes_every_item_before_first_mutation(self) -> None:
        scene = QGraphicsScene()
        canvas = SimpleNamespace(scene=lambda: scene)
        first = NoteItem(canvas)
        second = NoteItem(canvas)
        for item, text in ((first, "first"), (second, "second")):
            item.setData(0, "note")
            item.setPlainText(text)
            scene.addItem(item)
        set_selected_notes_for(canvas, [first, second])
        history = _attach_history_service(canvas)
        controller = _note_controller(canvas)
        mutate = mock.Mock()
        real_state = note_state_dict
        calls = 0

        def fail_second_snapshot(_canvas, item) -> dict:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise KeyboardInterrupt("second snapshot interrupted")
            return real_state(item)

        with mock.patch(
            "ui.canvas_note_controller.note_state_dict_for",
            side_effect=fail_second_snapshot,
        ):
            with self.assertRaisesRegex(KeyboardInterrupt, "second snapshot interrupted"):
                controller._apply_to_target_notes(mutate)

        mutate.assert_not_called()
        self.assertEqual(first.toPlainText(), "first")
        self.assertEqual(second.toPlainText(), "second")
        history.push.assert_not_called()

    def test_selected_note_batch_metadata_capture_failure_precedes_all_mutations(self) -> None:
        scene = QGraphicsScene()
        canvas = SimpleNamespace(scene=lambda: scene)
        first = NoteItem(canvas)
        second = NoteItem(canvas)
        for item, text in ((first, "first"), (second, "second")):
            item.setData(0, "note")
            item.setPlainText(text)
            scene.addItem(item)
        set_selected_notes_for(canvas, [first, second])
        history = _attach_history_service(canvas)
        controller = _note_controller(canvas)
        mutate = mock.Mock()
        metadata_calls = 0

        def fail_second_metadata(_item) -> str:
            nonlocal metadata_calls
            metadata_calls += 1
            if metadata_calls == 2:
                raise SystemExit("metadata capture terminated")
            return ""

        with mock.patch(
            "ui.canvas_note_controller.committed_note_html_for",
            side_effect=fail_second_metadata,
        ):
            with self.assertRaisesRegex(SystemExit, "metadata capture terminated"):
                controller._apply_to_target_notes(mutate)

        mutate.assert_not_called()
        self.assertEqual(first.toPlainText(), "first")
        self.assertEqual(second.toPlainText(), "second")
        history.push.assert_not_called()

    def test_selected_note_batch_rolls_back_only_attempted_items(self) -> None:
        scene = QGraphicsScene()
        canvas = SimpleNamespace(scene=lambda: scene)
        first = NoteItem(canvas)
        second = NoteItem(canvas)
        for item, text in ((first, "first"), (second, "second")):
            item.setData(0, "note")
            item.setPlainText(text)
            scene.addItem(item)
        second.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        second_flags = second.textInteractionFlags()
        second.set_committed_text("second-committed")
        set_selected_notes_for(canvas, [first, second])
        _attach_history_service(canvas)
        controller = _note_controller(canvas)

        def mutate_then_interrupt(item) -> None:
            item.setPlainText("changed")
            raise KeyboardInterrupt("first mutation interrupted")

        def apply_state(_canvas, item, state) -> None:
            if item is second:
                raise AssertionError("untouched second note was restored")
            item.setHtml(state["html"])

        with mock.patch(
            "ui.history_commands._apply_scene_item_state",
            side_effect=apply_state,
        ):
            with self.assertRaisesRegex(KeyboardInterrupt, "first mutation interrupted"):
                controller._apply_to_target_notes(mutate_then_interrupt)

        self.assertEqual(first.toPlainText(), "first")
        self.assertEqual(second.toPlainText(), "second")
        self.assertEqual(second.textInteractionFlags(), second_flags)
        self.assertEqual(committed_note_text_for(second), "second-committed")

    def test_selected_note_batch_persistent_interaction_lookup_does_not_block_earlier_note_restore_and_retries(
        self,
    ) -> None:
        class BrokenSystemExit(SystemExit):
            def __getattribute__(self, name: str):
                if name == "add_note":
                    raise KeyboardInterrupt("broken diagnostic lookup")
                return super().__getattribute__(name)

        class ToggleInteractionSetter:
            def __init__(self) -> None:
                self.fail = False

            def __get__(self, instance, owner):
                if instance is None:
                    return self
                if self.fail:
                    raise KeyboardInterrupt(
                        "persistent batch interaction lookup failure"
                    )
                return lambda flags: QGraphicsTextItem.setTextInteractionFlags(
                    instance,
                    flags,
                )

        interaction_setter = ToggleInteractionSetter()

        class FailingInteractionNote(NoteItem):
            setTextInteractionFlags = interaction_setter

        scene = QGraphicsScene()
        canvas = SimpleNamespace(scene=lambda: scene)
        first = NoteItem(canvas)
        second = FailingInteractionNote(canvas)
        for item, text in ((first, "first"), (second, "second")):
            item.setData(0, "note")
            item.setPlainText(text)
            scene.addItem(item)
        set_selected_notes_for(canvas, [first, second])
        _attach_history_service(canvas)
        controller = _note_controller(canvas)
        primary_error = BrokenSystemExit("second mutation terminated")

        def mutate_then_exit(item) -> None:
            item.setPlainText("changed")
            if item is second:
                interaction_setter.fail = True
                raise primary_error

        def apply_state(_canvas, item, state) -> None:
            QGraphicsTextItem.setHtml(item, state["html"])

        with (
            mock.patch(
                "ui.history_commands._apply_scene_item_state",
                side_effect=apply_state,
            ),
            mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        ):
            with self.assertRaises(BrokenSystemExit) as caught:
                controller._apply_to_target_notes(mutate_then_exit)

        self.assertIs(caught.exception, primary_error)
        self.assertEqual(first.toPlainText(), "first")
        self.assertEqual(second.toPlainText(), "second")

        interaction_setter.fail = False
        controller._apply_to_target_notes(
            lambda item: item.setPlainText("retry")
        )
        self.assertEqual(first.toPlainText(), "retry")
        self.assertEqual(second.toPlainText(), "retry")

    def test_selected_note_history_exit_restores_metadata_flags_and_stack_identity(
        self,
    ) -> None:
        scene = QGraphicsScene()
        canvas = SimpleNamespace(scene=lambda: scene)
        note = NoteItem(canvas)
        note.setData(0, "note")
        note.setPlainText("memo")
        note.set_committed_text("committed-before")
        note.set_committed_html("<p>committed-before</p>")
        note.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        scene.addItem(note)
        set_selected_notes_for(canvas, [note])

        before_html = note.toHtml()
        before_flags = note.textInteractionFlags()
        before_committed_text = note.committed_text()
        before_committed_html = note.committed_html()
        old_command = object()
        old_redo = object()
        undo_stack = [old_command]
        redo_stack = [old_redo]
        history_state = SimpleNamespace(history=undo_stack, redo_stack=redo_stack)

        def append_mutate_then_exit(command) -> None:
            history_state.history.append(command)
            history_state.redo_stack.clear()
            note.set_committed_text("push-mutated")
            note.set_committed_html("<p>push-mutated</p>")
            note.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            raise SystemExit("batch history terminated")

        history = SimpleNamespace(
            state=history_state,
            push=append_mutate_then_exit,
            notify_change=mock.Mock(),
        )
        canvas.services = SimpleNamespace(history_service=history)
        controller = _note_controller(canvas)

        def apply_state(_canvas, item, state) -> None:
            item.setHtml(state["html"])
            item.set_committed_text(item.toPlainText())
            item.set_committed_html(item.toHtml())
            item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        with (
            mock.patch(
                "ui.history_commands._apply_scene_item_state",
                side_effect=apply_state,
            ),
            mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        ):
            with self.assertRaisesRegex(SystemExit, "batch history terminated"):
                controller.set_text_alignment("right")

        self.assertEqual(note.toHtml(), before_html)
        self.assertEqual(note.committed_text(), before_committed_text)
        self.assertEqual(note.committed_html(), before_committed_html)
        self.assertEqual(note.textInteractionFlags(), before_flags)
        self.assertIs(history_state.history, undo_stack)
        self.assertIs(history_state.redo_stack, redo_stack)
        self.assertEqual(undo_stack, [old_command])
        self.assertEqual(redo_stack, [old_redo])

    def test_far_batch_note_append_then_raise_restores_auto_rect_last_with_retry(
        self,
    ) -> None:
        class FailOnceAutomaticRestoreScene(QGraphicsScene):
            fail_null_restores = 0

            def setSceneRect(self, *args) -> None:
                rect = args[0] if len(args) == 1 else None
                super().setSceneRect(*args)
                if (
                    rect is not None
                    and rect.isNull()
                    and self.fail_null_restores
                ):
                    self.fail_null_restores -= 1
                    raise SystemExit(
                        "note scene rect restore failed after mutation"
                    )

        scene = FailOnceAutomaticRestoreScene()
        scene.addRect(0.0, 0.0, 10.0, 10.0)
        canvas = SimpleNamespace(scene=lambda: scene)
        note = NoteItem(canvas)
        note.setData(0, "note")
        note.setPlainText("before")
        note.set_committed_text("before")
        note.set_committed_html(note.toHtml())
        note.setPos(20.0, 20.0)
        scene.addItem(note)
        set_selected_notes_for(canvas, [note])
        baseline_rect = scene.sceneRect()
        baseline_pos = note.pos()
        baseline_html = note.toHtml()
        baseline_committed_html = note.committed_html()
        history_list = [object()]
        redo_list = [object()]
        history_state = SimpleNamespace(
            history=history_list,
            redo_stack=redo_list,
        )
        primary = KeyboardInterrupt("note history append terminated")

        def append_then_interrupt(command) -> None:
            history_state.history.append(command)
            history_state.redo_stack.clear()
            self.assertEqual(scene.sceneRect(), baseline_rect)
            scene.fail_null_restores = 1
            raise primary

        history = SimpleNamespace(
            state=history_state,
            push=append_then_interrupt,
            notify_change=mock.Mock(),
        )
        canvas.services = SimpleNamespace(history_service=history)
        controller = CanvasNoteController(canvas, history_service=history)

        def apply_state(_canvas, item, state) -> None:
            item.setHtml(state["html"])
            item.setPos(float(state["x"]), float(state["y"]))

        def move_far(item) -> None:
            item.setPlainText("after")
            item.setPos(25_000.0, 0.0)

        with (
            mock.patch(
                "ui.history_commands._apply_scene_item_state",
                side_effect=apply_state,
            ),
            mock.patch(
                "ui.history_commands.refresh_selection_outline_for_canvas"
            ),
        ):
            with self.assertRaises(KeyboardInterrupt) as raised:
                controller._apply_to_target_notes(move_far)

        self.assertIs(raised.exception, primary)
        self.assertEqual(note.pos(), baseline_pos)
        self.assertEqual(note.toHtml(), baseline_html)
        self.assertEqual(note.committed_html(), baseline_committed_html)
        self.assertIs(history_state.history, history_list)
        self.assertIs(history_state.redo_stack, redo_list)
        self.assertEqual(len(history_list), 1)
        self.assertEqual(len(redo_list), 1)
        self.assertEqual(scene.sceneRect(), baseline_rect)
        self.assertTrue(scene._chemvas_scene_rect_automatic)
        self.assertEqual(scene._chemvas_scene_rect_tracker.depth, 0)
        self.assertTrue(
            any(
                "restoring the note-formatting scene rect" in note_text
                for note_text in getattr(primary, "__notes__", [])
            )
        )

        def append_successfully(command) -> None:
            history_state.history.append(command)
            history_state.redo_stack.clear()

        history.push = append_successfully
        controller._apply_to_target_notes(
            lambda item: item.setPos(30_000.0, 0.0)
        )
        self.assertGreater(scene.sceneRect().right(), 30_000.0)
        self.assertTrue(scene._chemvas_scene_rect_automatic)
        self.assertEqual(scene._chemvas_scene_rect_tracker.depth, 0)

        future = scene.addRect(50_000.0, 0.0, 10.0, 10.0)
        self.assertGreater(scene.sceneRect().right(), 50_000.0)
        scene.removeItem(future)

    def test_note_history_undo_lookup_failure_keeps_primary_and_runs_later_rollback(
        self,
    ) -> None:
        undo_lookup_error = SystemExit("persistent undo lookup failure")

        class BrokenUndoCommand:
            @property
            def undo(self):
                raise undo_lookup_error

        old_command = object()
        old_redo = object()
        undo_stack = [old_command]
        redo_stack = [old_redo]
        history_state = SimpleNamespace(
            history=undo_stack,
            redo_stack=redo_stack,
        )
        primary_error = KeyboardInterrupt("history push interrupted")

        def append_then_interrupt(command) -> None:
            history_state.history.append(command)
            history_state.redo_stack.clear()
            raise primary_error

        history = SimpleNamespace(
            state=history_state,
            push=append_then_interrupt,
            notify_change=mock.Mock(),
        )
        later_rollback = mock.Mock()
        controller = CanvasNoteController(
            SimpleNamespace(),
            history_service=history,
        )

        with self.assertRaises(KeyboardInterrupt) as caught:
            controller._push_history_or_rollback(
                BrokenUndoCommand(),
                rollback_steps=(("running a later note rollback", later_rollback),),
            )

        self.assertIs(caught.exception, primary_error)
        later_rollback.assert_called_once_with()
        self.assertIs(history_state.history, undo_stack)
        self.assertIs(history_state.redo_stack, redo_stack)
        self.assertEqual(undo_stack, [old_command])
        self.assertEqual(redo_stack, [old_redo])
        self.assertTrue(
            any(
                "persistent undo lookup failure" in note
                for note in getattr(primary_error, "__notes__", [])
            )
        )

    def test_editing_note_format_failure_restores_metadata_cursor_focus_without_scene_scan(
        self,
    ) -> None:
        controller, note = self._editing_note_controller("new text")
        note.set_committed_text("old text")
        note.set_committed_html("<p>old text</p>")
        before_html = note.toHtml()
        before_flags = note.textInteractionFlags()
        before_cursor = note.textCursor()
        before_anchor = before_cursor.anchor()
        before_position = before_cursor.position()
        document = note.document()
        assert document is not None
        original_block_signals = document.blockSignals
        block_calls = 0

        def block_once_then_exit(blocked: bool) -> bool:
            nonlocal block_calls
            block_calls += 1
            previous = original_block_signals(blocked)
            if block_calls == 1:
                raise SystemExit("signal blocking terminated")
            return previous

        scene = note.scene()
        assert scene is not None
        controller.update_note_box = mock.Mock(
            side_effect=KeyboardInterrupt("box refresh interrupted")
        )

        with (
            mock.patch(
                "ui.history_commands._scene_items_snapshot",
                side_effect=AssertionError("editing format scanned unrelated scene items"),
            ) as scene_scan,
            mock.patch.object(document, "blockSignals", side_effect=block_once_then_exit),
        ):
            with self.assertRaisesRegex(KeyboardInterrupt, "box refresh interrupted"):
                controller.set_text_alignment("right")

        scene_scan.assert_not_called()
        self.assertEqual(note.toHtml(), before_html)
        self.assertEqual(committed_note_text_for(note), "old text")
        self.assertEqual(note.committed_html(), "<p>old text</p>")
        self.assertEqual(note.textInteractionFlags(), before_flags)
        self.assertEqual(note.textCursor().anchor(), before_anchor)
        self.assertEqual(note.textCursor().position(), before_position)
        self.assertIs(scene.focusItem(), note)
        self.assertFalse(document.signalsBlocked())

    def test_editing_note_persistent_interaction_lookup_keeps_later_box_focus_cursor_exact_and_retries(
        self,
    ) -> None:
        class BrokenKeyboardInterrupt(KeyboardInterrupt):
            def __getattribute__(self, name: str):
                if name == "add_note":
                    raise SystemExit("broken diagnostic lookup")
                return super().__getattribute__(name)

        class PersistentInteractionLookup:
            def __get__(self, instance, owner):
                if instance is None:
                    return self
                raise SystemExit("persistent interaction setter lookup failure")

        scene = QGraphicsScene()
        canvas = SimpleNamespace(
            scene=lambda: scene,
            text_style_state=CanvasTextStyleState(
                note_box_enabled=True,
                note_border_enabled=True,
            ),
        )
        note = NoteItem(canvas)
        note.setData(0, "note")
        note.setPlainText("memo")
        scene.addItem(note)
        scene.setFocusItem(note)
        other_focus = QGraphicsTextItem("other")
        other_focus.setFlag(other_focus.GraphicsItemFlag.ItemIsFocusable, True)
        scene.addItem(other_focus)
        controller = CanvasNoteController(canvas)
        controller.update_note_box(note)
        box = note.data(20)
        self.assertIsNotNone(box)
        before_html = note.toHtml()
        before_rect = box.rect()
        before_pen = box.pen()
        before_brush = box.brush()
        before_visible = box.isVisible()
        before_cursor = note.textCursor()
        before_anchor = before_cursor.anchor()
        before_position = before_cursor.position()
        primary_error = BrokenKeyboardInterrupt("box refresh interrupted")

        def mutate_box_focus_cursor_then_interrupt(_item) -> None:
            box.setRect(0.0, 0.0, 999.0, 777.0)
            pen = box.pen()
            pen.setWidthF(pen.widthF() + 9.0)
            box.setPen(pen)
            brush = box.brush()
            brush.setColor(QColor("#ff1493"))
            box.setBrush(brush)
            box.setVisible(not before_visible)
            scene.setFocusItem(other_focus)
            cursor = note.textCursor()
            cursor.clearSelection()
            note.setTextCursor(cursor)
            raise primary_error

        with (
            mock.patch.object(
                NoteItem,
                "setTextInteractionFlags",
                PersistentInteractionLookup(),
            ),
            mock.patch.object(
                controller,
                "update_note_box",
                side_effect=mutate_box_focus_cursor_then_interrupt,
            ),
        ):
            with self.assertRaises(BrokenKeyboardInterrupt) as caught:
                controller.set_text_alignment("right")

        self.assertIs(caught.exception, primary_error)
        self.assertEqual(note.toHtml(), before_html)
        self.assertEqual(box.rect(), before_rect)
        self.assertEqual(box.pen(), before_pen)
        self.assertEqual(box.brush(), before_brush)
        self.assertEqual(box.isVisible(), before_visible)
        self.assertIs(scene.focusItem(), note)
        self.assertEqual(note.textCursor().anchor(), before_anchor)
        self.assertEqual(note.textCursor().position(), before_position)

        scene.setFocusItem(note)
        controller.set_text_alignment("right")
        self.assertEqual(
            note.textCursor().blockFormat().alignment(),
            Qt.AlignmentFlag.AlignRight,
        )

    def test_editing_note_static_focus_lookup_failure_is_recorded_and_cursor_restore_continues(
        self,
    ) -> None:
        class FailingFocusSetter:
            def __init__(self) -> None:
                self.fail = False
                self.calls = 0

            def __get__(self, instance, owner):
                if instance is None:
                    return self
                self.calls += 1
                if self.fail:
                    raise AttributeError(
                        "live focus setter descriptor failed internally"
                    )
                return lambda item: QGraphicsScene.setFocusItem(instance, item)

        focus_setter = FailingFocusSetter()

        class FailingFocusScene(QGraphicsScene):
            setFocusItem = focus_setter

        scene = FailingFocusScene()
        canvas = SimpleNamespace(
            scene=lambda: scene,
            text_style_state=CanvasTextStyleState(),
        )
        note = NoteItem(canvas)
        note.setData(0, "note")
        note.setPlainText("memo")
        scene.addItem(note)
        scene.setFocusItem(note)
        other_focus = QGraphicsTextItem("other")
        other_focus.setFlag(other_focus.GraphicsItemFlag.ItemIsFocusable, True)
        scene.addItem(other_focus)
        controller = CanvasNoteController(canvas)
        before_html = note.toHtml()
        before_cursor = note.textCursor()
        before_anchor = before_cursor.anchor()
        before_position = before_cursor.position()
        primary_error = KeyboardInterrupt("formatting interrupted")

        def move_focus_cursor_then_interrupt(_item) -> None:
            QGraphicsScene.setFocusItem(scene, other_focus)
            cursor = note.textCursor()
            cursor.clearSelection()
            note.setTextCursor(cursor)
            focus_setter.fail = True
            raise primary_error

        with mock.patch.object(
            controller,
            "update_note_box",
            side_effect=move_focus_cursor_then_interrupt,
        ):
            with self.assertRaises(KeyboardInterrupt) as caught:
                controller.set_text_alignment("right")

        self.assertIs(caught.exception, primary_error)
        self.assertEqual(note.toHtml(), before_html)
        self.assertIs(scene.focusItem(), other_focus)
        self.assertEqual(note.textCursor().anchor(), before_anchor)
        self.assertEqual(note.textCursor().position(), before_position)
        self.assertTrue(
            any(
                "restoring editing-note focus" in note_text
                for note_text in getattr(primary_error, "__notes__", [])
            )
        )
        self.assertEqual(focus_setter.calls, 2)

        focus_setter.fail = False
        scene.setFocusItem(note)
        controller.set_text_alignment("right")
        self.assertEqual(focus_setter.calls, 3)
        self.assertEqual(
            note.textCursor().blockFormat().alignment(),
            Qt.AlignmentFlag.AlignRight,
        )

    def test_editing_note_static_live_focus_descriptor_failure_precedes_mutation_and_retries(
        self,
    ) -> None:
        class FailSecondFocusScene(QGraphicsScene):
            focus_calls = 0

            @property
            def focusItem(self):
                self.focus_calls += 1
                if self.focus_calls == 2:
                    raise AttributeError(
                        "live editing focus descriptor failed internally"
                    )
                return lambda: QGraphicsScene.focusItem(self)

        scene = FailSecondFocusScene()
        canvas = SimpleNamespace(
            scene=lambda: scene,
            text_style_state=CanvasTextStyleState(),
        )
        note = NoteItem(canvas)
        note.setData(0, "note")
        note.setPlainText("memo")
        scene.addItem(note)
        scene.setFocusItem(note)
        controller = CanvasNoteController(canvas)
        controller.update_note_box = mock.Mock()
        mutate = mock.Mock()

        with mock.patch(
            "ui.canvas_note_controller.update_note_selection_box_for"
        ) as update_selection_box:
            with self.assertRaises(AttributeError):
                controller._apply_to_target_notes(mutate)

            mutate.assert_not_called()
            controller.update_note_box.assert_not_called()
            update_selection_box.assert_not_called()
            self.assertEqual(note.toPlainText(), "memo")

            controller._apply_to_target_notes(mutate)

        mutate.assert_called_once_with(note)
        controller.update_note_box.assert_called_once_with(note)
        update_selection_box.assert_called_once_with(canvas, note)

    def test_editing_note_snapshot_keeps_absent_scene_focus_fallback(self) -> None:
        canvas = SimpleNamespace()
        note = NoteItem(canvas)
        note.setData(0, "note")

        snapshot = _EditingNoteSnapshot.capture(note)

        self.assertIsNone(snapshot.scene)
        self.assertIsNone(snapshot.focus_item)

    def test_format_methods_noop_when_no_note_is_focused(self) -> None:
        scene = QGraphicsScene()
        canvas = SimpleNamespace(scene=lambda: scene, text_style_state=CanvasTextStyleState())
        controller = CanvasNoteController(canvas)
        # No focused note -> should not raise.
        controller.toggle_text_bold()
        controller.toggle_text_superscript()
        controller.adjust_text_size(2)

    def test_superscript_formatting_survives_serialize_restore(self) -> None:
        controller, note = self._editing_note_controller("2")
        controller.toggle_text_superscript()

        state = note_state_dict(note)
        snapshot = {key: state[key] for key in ("text", "html", "x", "y")}
        _validate_note_states([snapshot])

        restored = create_note_item_from_state(
            snapshot,
            note_item_factory=lambda: QGraphicsTextItem(),
            note_style_applier=lambda item: None,
        )
        self.assertEqual(restored.toPlainText(), "2")
        self.assertIn("vertical-align:super", restored.toHtml())

    def test_apply_text_style_to_selected_and_update_text_note_refresh_note_box(self) -> None:
        scene = QGraphicsScene()
        item = QGraphicsTextItem("Mechanism")
        scene.addItem(item)

        selection_controller = SimpleNamespace(update_note_selection_box=mock.Mock())
        canvas = SimpleNamespace(
            text_style_state=CanvasTextStyleState(
                text_font_family="Arial",
                text_font_size=13,
                text_font_weight=QFont.Weight.DemiBold,
                text_italic=True,
                text_color=QColor("#334455"),
                text_alignment=Qt.AlignmentFlag.AlignRight,
                text_line_spacing=1.25,
                note_padding=6.0,
                note_box_enabled=True,
                note_border_enabled=True,
                note_box_color=QColor("#ffffff"),
                note_box_alpha=0.4,
                note_border_color=QColor("#111111"),
                note_border_width=1.2,
            ),
            selection_style_state=SelectionStyleState(
                color=QColor("#1f5eff"),
                stroke_delta=0.8,
            ),
            services=SimpleNamespace(selection_controller=selection_controller),
        )
        set_selected_notes_for(canvas, [item])
        _attach_history_service(canvas)
        controller = _note_controller(canvas)

        controller.apply_text_style_to_selected()

        box = item.data(20)
        self.assertIsNotNone(box)
        self.assertTrue(box.isVisible())
        self.assertEqual(item.defaultTextColor().name(), "#334455")
        self.assertTrue(item.font().italic())
        self.assertEqual(item.font().pointSize(), 13)
        selection_controller.update_note_selection_box.assert_called_once_with(item)

        controller.update_text_note(item, "Updated")
        self.assertEqual(item.toPlainText(), "Updated")
        self.assertEqual(selection_controller.update_note_selection_box.call_count, 2)

    def test_update_note_box_hides_existing_box_when_disabled(self) -> None:
        scene = QGraphicsScene()
        item = QGraphicsTextItem("Mechanism")
        scene.addItem(item)
        canvas = SimpleNamespace(
            text_style_state=CanvasTextStyleState(
                note_padding=6.0,
                note_box_enabled=True,
                note_border_enabled=True,
                note_box_color=QColor("#ffffff"),
                note_box_alpha=0.4,
                note_border_color=QColor("#111111"),
                note_border_width=1.2,
            ),
        )
        _attach_history_service(canvas)
        controller = _note_controller(canvas)

        controller.update_note_box(item)
        box = item.data(20)
        self.assertIsNotNone(box)
        self.assertTrue(box.isVisible())

        set_text_style_for(canvas, "note_box_enabled", False)
        set_text_style_for(canvas, "note_border_enabled", False)
        controller.update_note_box(item)

        self.assertFalse(box.isVisible())

    def test_typing_resizes_note_box_live(self) -> None:
        scene = QGraphicsScene()
        canvas = SimpleNamespace(
            scene=lambda: scene,
            text_style_state=CanvasTextStyleState(note_padding=6.0, note_border_enabled=True),
        )
        _attach_history_service(canvas)
        note = NoteItem(canvas)
        note.setData(0, "note")
        note.setPlainText("D")
        scene.addItem(note)
        controller = _note_controller(canvas)

        controller._ensure_note_box_autoresize(note)
        controller.update_note_box(note)
        width_before = note.data(20).rect().width()

        cursor = note.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        note.setTextCursor(cursor)
        cursor.insertText("aehyup Sohn")

        # contentsChanged should have resized the box to follow the longer text.
        self.assertGreater(note.data(20).rect().width(), width_before)
        # Connecting again is idempotent (no duplicate signal hookup).
        controller._ensure_note_box_autoresize(note)
        self.assertTrue(note.data(22))

    def test_focus_out_ends_editing_and_clears_text_selection(self) -> None:
        scene = QGraphicsScene()
        canvas = SimpleNamespace(scene=lambda: scene, text_style_state=CanvasTextStyleState())
        _attach_history_service(canvas)
        canvas.services.selection_controller = SimpleNamespace(update_note_selection_box=mock.Mock())
        set_selected_notes_for(canvas, [])
        note = NoteItem(canvas)
        note.setData(0, "note")
        note.setPlainText("Hi there")
        scene.addItem(note)
        controller = _note_controller(canvas)

        cursor = note.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        note.setTextCursor(cursor)
        self.assertTrue(note.textCursor().hasSelection())

        controller.handle_note_focus_out(note)

        # The double-click highlight is dropped and the editor stops accepting input.
        self.assertFalse(note.textCursor().hasSelection())
        self.assertEqual(note.textInteractionFlags(), Qt.TextInteractionFlag.NoTextInteraction)

    def test_selection_controller_note_box_helper_round_trips_visibility(self) -> None:
        scene = QGraphicsScene()
        item = QGraphicsTextItem("Mechanism")
        scene.addItem(item)
        canvas = SimpleNamespace(
            text_style_state=CanvasTextStyleState(note_padding=6.0),
            selection_style_state=SelectionStyleState(
                color=QColor("#1f5eff"),
                stroke_delta=0.8,
            ),
        )
        set_selected_notes_for(canvas, [item])
        controller = _selection_controller_for(canvas)

        controller.update_note_selection_box(item)
        selection_box = item.data(21)
        self.assertIsNotNone(selection_box)
        self.assertTrue(selection_box.isVisible())

        set_selected_notes_for(canvas, [])
        controller.update_note_selection_box(item)
        self.assertFalse(selection_box.isVisible())

    def test_handle_note_focus_out_adds_updates_and_deletes_commands(self) -> None:
        canvas = SimpleNamespace(
            commands=[],
            removed_items=[],
            updated_boxes=[],
        )
        set_selected_notes_for(canvas, [])

        def _note_state_dict(item) -> dict:
            return {
                "kind": "note",
                "text": item.toPlainText(),
                "x": item.pos().x(),
                "y": item.pos().y(),
            }

        canvas._note_state_dict = _note_state_dict
        canvas.push_command = canvas.commands.append
        canvas.services = SimpleNamespace(
            scene_item_controller=SimpleNamespace(remove_scene_item=canvas.removed_items.append),
            selection_controller=SimpleNamespace(update_note_selection_box=canvas.updated_boxes.append),
        )
        _attach_history_service(canvas)
        controller = _note_controller(canvas)
        item = NoteItem(canvas)

        item.setPlainText("Mechanism")
        controller.handle_note_focus_out(item)
        self.assertEqual(type(canvas.commands[-1]).__name__, "AddSceneItemsCommand")
        self.assertEqual(committed_note_text_for(item), "Mechanism")

        item.setPlainText("Mechanism 2")
        controller.handle_note_focus_out(item)
        self.assertEqual(type(canvas.commands[-1]).__name__, "UpdateSceneItemCommand")
        self.assertEqual(committed_note_text_for(item), "Mechanism 2")

        item.setPlainText("")
        controller.handle_note_focus_out(item)
        self.assertEqual(type(canvas.commands[-1]).__name__, "DeleteSceneItemsCommand")
        self.assertEqual(canvas.removed_items[-1], item)
        self.assertEqual(committed_note_text_for(item), "")

    def test_handle_note_focus_out_rolls_back_new_note_when_add_history_push_fails(self) -> None:
        canvas = SimpleNamespace(
            removed_items=[],
            updated_boxes=[],
            _note_state_dict=lambda item: {
                "kind": "note",
                "text": item.toPlainText(),
                "x": item.pos().x(),
                "y": item.pos().y(),
            },
        )
        set_selected_notes_for(canvas, [])

        def fail_push(_command) -> None:
            raise RuntimeError("history")

        canvas.push_command = fail_push
        canvas.services = SimpleNamespace(
            scene_item_controller=SimpleNamespace(remove_scene_item=canvas.removed_items.append),
            selection_controller=SimpleNamespace(update_note_selection_box=canvas.updated_boxes.append),
        )
        _attach_history_service(canvas)
        controller = _note_controller(canvas)
        item = NoteItem(canvas)
        item.setPlainText("Mechanism")

        with self.assertRaisesRegex(RuntimeError, "history"):
            controller.handle_note_focus_out(item)

        self.assertEqual(canvas.removed_items, [item])
        self.assertEqual(committed_note_text_for(item), "")

    def test_handle_note_focus_out_restores_deleted_note_when_delete_history_push_fails(self) -> None:
        canvas = SimpleNamespace(
            commands=[],
            removed_items=[],
            restored_items=[],
            updated_boxes=[],
        )
        set_selected_notes_for(canvas, [])

        def _note_state_dict(item) -> dict:
            return {
                "kind": "note",
                "text": item.toPlainText(),
                "x": item.pos().x(),
                "y": item.pos().y(),
            }

        canvas._note_state_dict = _note_state_dict
        canvas.push_command = canvas.commands.append
        canvas.services = SimpleNamespace(
            scene_item_controller=SimpleNamespace(
                remove_scene_item=canvas.removed_items.append,
                restore_scene_item=canvas.restored_items.append,
            ),
            selection_controller=SimpleNamespace(update_note_selection_box=canvas.updated_boxes.append),
        )
        history = _attach_history_service(canvas)
        controller = _note_controller(canvas)
        item = NoteItem(canvas)
        item.setPlainText("Mechanism")
        controller.handle_note_focus_out(item)
        history.push = mock.Mock(side_effect=RuntimeError("history"))
        item.setPlainText("")

        with self.assertRaisesRegex(RuntimeError, "history"):
            controller.handle_note_focus_out(item)

        self.assertEqual(canvas.removed_items, [item])
        self.assertEqual(canvas.restored_items, [item])
        self.assertEqual(committed_note_text_for(item), "Mechanism")

    def test_new_note_system_exit_after_history_append_restores_stack_identity_and_removes_item(
        self,
    ) -> None:
        scene = QGraphicsScene()
        note_items = []
        scene_items_state = CanvasSceneItemsState(note_items=note_items)
        canvas = SimpleNamespace(
            scene=lambda: scene,
            scene_items_state=scene_items_state,
        )
        item = NoteItem(canvas)
        item.setData(0, "note")
        item.setPlainText("Mechanism")
        scene.addItem(item)
        note_items.append(item)

        def remove(target) -> None:
            if target in note_items:
                note_items.remove(target)
            if target.scene() is scene:
                scene.removeItem(target)

        def restore(target) -> None:
            if target not in note_items:
                note_items.append(target)
            if target.scene() is not scene:
                scene.addItem(target)

        old_command = object()
        old_redo = object()
        undo_stack = [old_command]
        redo_stack = [old_redo]
        history_state = SimpleNamespace(history=undo_stack, redo_stack=redo_stack)

        def append_then_exit(command) -> None:
            history_state.history.append(command)
            history_state.redo_stack.clear()
            raise SystemExit("note history terminated")

        history = SimpleNamespace(
            state=history_state,
            push=append_then_exit,
            notify_change=mock.Mock(),
        )
        canvas.services = SimpleNamespace(
            history_service=history,
            scene_item_controller=SimpleNamespace(
                remove_scene_item=remove,
                restore_scene_item=restore,
            ),
            selection_controller=SimpleNamespace(update_note_selection_box=mock.Mock()),
        )

        with self.assertRaisesRegex(SystemExit, "note history terminated"):
            _note_controller(canvas).handle_note_focus_out(item)

        self.assertIs(scene_items_state.note_items, note_items)
        self.assertEqual(note_items, [])
        self.assertIsNone(item.scene())
        self.assertEqual(committed_note_text_for(item), "")
        self.assertIs(history_state.history, undo_stack)
        self.assertIs(history_state.redo_stack, redo_stack)
        self.assertEqual(undo_stack, [old_command])
        self.assertEqual(redo_stack, [old_redo])

    def test_existing_note_keyboard_interrupt_after_history_append_restores_scene_selection_and_stacks(
        self,
    ) -> None:
        scene = QGraphicsScene()
        note_items = []
        selected_notes = []
        scene_items_state = CanvasSceneItemsState(
            note_items=note_items,
            selected_notes=selected_notes,
        )
        canvas = SimpleNamespace(
            scene=lambda: scene,
            scene_items_state=scene_items_state,
        )
        item = NoteItem(canvas)
        item.setData(0, "note")
        item.setPlainText("")
        item.set_committed_text("Mechanism")
        item.set_committed_html("<p>Mechanism</p>")
        scene.addItem(item)
        note_items.append(item)
        selected_notes.append(item)

        def remove(target) -> None:
            if target in note_items:
                note_items.remove(target)
            if target.scene() is scene:
                scene.removeItem(target)

        def restore(target) -> None:
            if target not in note_items:
                note_items.append(target)
            if target.scene() is not scene:
                scene.addItem(target)

        def toggle(target) -> None:
            selected_notes.remove(target)

        old_command = object()
        old_redo = object()
        undo_stack = [old_command]
        redo_stack = [old_redo]
        history_state = SimpleNamespace(history=undo_stack, redo_stack=redo_stack)

        def append_then_interrupt(command) -> None:
            history_state.history.append(command)
            history_state.redo_stack.clear()
            raise KeyboardInterrupt("note history interrupted")

        history = SimpleNamespace(
            state=history_state,
            push=append_then_interrupt,
            notify_change=mock.Mock(),
        )
        canvas.services = SimpleNamespace(
            history_service=history,
            scene_item_controller=SimpleNamespace(
                remove_scene_item=remove,
                restore_scene_item=restore,
            ),
            selection_controller=SimpleNamespace(
                toggle_note_selection=toggle,
                update_note_selection_box=mock.Mock(),
                update_selection_outline=mock.Mock(),
            ),
        )

        with self.assertRaisesRegex(KeyboardInterrupt, "note history interrupted"):
            _note_controller(canvas).handle_note_focus_out(item)

        self.assertIs(scene_items_state.note_items, note_items)
        self.assertIs(scene_items_state.selected_notes, selected_notes)
        self.assertEqual(note_items, [item])
        self.assertEqual(selected_notes, [item])
        self.assertIs(item.scene(), scene)
        self.assertEqual(committed_note_text_for(item), "Mechanism")
        self.assertIs(history_state.history, undo_stack)
        self.assertIs(history_state.redo_stack, redo_stack)
        self.assertEqual(undo_stack, [old_command])
        self.assertEqual(redo_stack, [old_redo])

    def test_existing_note_deselect_keyboard_interrupt_restores_selected_list_before_remove(
        self,
    ) -> None:
        scene = QGraphicsScene()
        note_items = []
        selected_notes = []
        scene_items_state = CanvasSceneItemsState(
            note_items=note_items,
            selected_notes=selected_notes,
        )
        canvas = SimpleNamespace(
            scene=lambda: scene,
            scene_items_state=scene_items_state,
        )
        item = NoteItem(canvas)
        item.setData(0, "note")
        item.setPlainText("")
        item.set_committed_text("Mechanism")
        item.set_committed_html("<p>Mechanism</p>")
        scene.addItem(item)
        note_items.append(item)
        selected_notes.append(item)

        def mutate_then_interrupt(target) -> None:
            selected_notes.remove(target)
            raise KeyboardInterrupt("deselect interrupted")

        history = SimpleNamespace(
            state=SimpleNamespace(history=[], redo_stack=[]),
            push=mock.Mock(),
        )
        remove = mock.Mock()
        canvas.services = SimpleNamespace(
            history_service=history,
            scene_item_controller=SimpleNamespace(remove_scene_item=remove),
            selection_controller=SimpleNamespace(
                toggle_note_selection=mutate_then_interrupt,
                update_note_selection_box=mock.Mock(),
                update_selection_outline=mock.Mock(),
            ),
        )

        with self.assertRaisesRegex(KeyboardInterrupt, "deselect interrupted"):
            _note_controller(canvas).handle_note_focus_out(item)

        self.assertIs(scene_items_state.selected_notes, selected_notes)
        self.assertEqual(selected_notes, [item])
        self.assertEqual(note_items, [item])
        self.assertIs(item.scene(), scene)
        remove.assert_not_called()
        history.push.assert_not_called()

    def test_delete_history_snapshot_system_exit_restores_removed_note_and_selection(self) -> None:
        scene = QGraphicsScene()
        note_items = []
        selected_notes = []
        scene_items_state = CanvasSceneItemsState(
            note_items=note_items,
            selected_notes=selected_notes,
        )
        canvas = SimpleNamespace(
            scene=lambda: scene,
            scene_items_state=scene_items_state,
        )
        item = NoteItem(canvas)
        item.setData(0, "note")
        item.setPlainText("")
        item.set_committed_text("Mechanism")
        item.set_committed_html("<p>Mechanism</p>")
        scene.addItem(item)
        note_items.append(item)
        selected_notes.append(item)

        def remove(target) -> None:
            if target in note_items:
                note_items.remove(target)
            if target.scene() is scene:
                scene.removeItem(target)

        def restore(target) -> None:
            if target not in note_items:
                note_items.append(target)
            if target.scene() is not scene:
                scene.addItem(target)

        history = SimpleNamespace(
            state=SimpleNamespace(history=[], redo_stack=[]),
            push=mock.Mock(),
        )
        canvas.services = SimpleNamespace(
            history_service=history,
            scene_item_controller=SimpleNamespace(
                remove_scene_item=remove,
                restore_scene_item=restore,
            ),
            selection_controller=SimpleNamespace(
                toggle_note_selection=lambda target: selected_notes.remove(target),
                update_note_selection_box=mock.Mock(),
                update_selection_outline=mock.Mock(),
            ),
        )

        with mock.patch(
            "ui.canvas_note_controller.HistoryStackSnapshot.capture",
            side_effect=SystemExit("history snapshot terminated"),
        ):
            with self.assertRaisesRegex(SystemExit, "history snapshot terminated"):
                _note_controller(canvas).handle_note_focus_out(item)

        self.assertEqual(note_items, [item])
        self.assertEqual(selected_notes, [item])
        self.assertIs(item.scene(), scene)
        self.assertEqual(committed_note_text_for(item), "Mechanism")
        history.push.assert_not_called()

    def test_handle_note_focus_out_routes_deselection_through_note_service(self) -> None:
        canvas = SimpleNamespace(
            commands=[],
            removed_items=[],
            updated_boxes=[],
            _note_state_dict=lambda item: {},
        )
        set_selected_notes_for(canvas, [])
        canvas.push_command = canvas.commands.append
        toggle_note_selection = mock.Mock()
        canvas.services = SimpleNamespace(
            scene_item_controller=SimpleNamespace(remove_scene_item=canvas.removed_items.append),
            selection_controller=SimpleNamespace(
                update_note_selection_box=canvas.updated_boxes.append,
                toggle_note_selection=toggle_note_selection,
            ),
        )
        _attach_history_service(canvas)
        controller = _note_controller(canvas)
        item = NoteItem(canvas)
        item.setPlainText("kept")
        item.set_committed_text("kept")
        item.set_committed_html(item.toHtml())
        selected_notes_for(canvas).append(item)

        controller.handle_note_focus_out(item)

        # The note-service toggle handles grouped companions and the outline
        # refresh; the controller must not strip the note from state directly.
        toggle_note_selection.assert_called_once_with(item)
        self.assertIn(item, selected_notes_for(canvas))

    def test_handle_note_focus_out_routes_emptied_note_deletion_through_note_service(self) -> None:
        canvas = SimpleNamespace(
            commands=[],
            removed_items=[],
            updated_boxes=[],
            _note_state_dict=lambda item: {},
        )
        set_selected_notes_for(canvas, [])
        canvas.push_command = canvas.commands.append
        toggle_note_selection = mock.Mock()
        update_selection_outline = mock.Mock()
        canvas.services = SimpleNamespace(
            scene_item_controller=SimpleNamespace(remove_scene_item=canvas.removed_items.append),
            selection_controller=SimpleNamespace(
                update_note_selection_box=canvas.updated_boxes.append,
                toggle_note_selection=toggle_note_selection,
                update_selection_outline=update_selection_outline,
            ),
        )
        _attach_history_service(canvas)
        controller = _note_controller(canvas)
        item = NoteItem(canvas)
        item.setPlainText("")
        item.set_committed_text("previous")
        item.set_committed_html("<p>previous</p>")
        selected_notes_for(canvas).append(item)

        # Editing an existing note down to empty deletes it; the deselection
        # must still route through the note service so grouped companions drop.
        controller.handle_note_focus_out(item)

        toggle_note_selection.assert_called_once_with(item)
        self.assertEqual(canvas.removed_items, [item])
        # A mixed group's box spans attached members, so the outline must be
        # refreshed again after the note leaves the scene.
        update_selection_outline.assert_called_once_with()

    def test_handle_note_focus_out_removes_empty_untracked_note_and_selection_box(self) -> None:
        canvas = SimpleNamespace(
            commands=[],
            removed_items=[],
            updated_boxes=[],
            _note_state_dict=lambda item: {},
        )
        set_selected_notes_for(canvas, [])
        canvas.push_command = canvas.commands.append
        canvas.services = SimpleNamespace(
            scene_item_controller=SimpleNamespace(remove_scene_item=canvas.removed_items.append),
            selection_controller=SimpleNamespace(update_note_selection_box=canvas.updated_boxes.append),
        )
        _attach_history_service(canvas)
        controller = _note_controller(canvas)
        item = NoteItem(canvas)
        selected_notes_for(canvas).append(item)

        controller.handle_note_focus_out(item)

        self.assertNotIn(item, selected_notes_for(canvas))
        self.assertEqual(canvas.updated_boxes, [item])
        self.assertEqual(canvas.removed_items, [item])

    def test_handle_note_focus_out_prefers_scene_item_controller_for_removal(self) -> None:
        controller_remove = mock.Mock()
        canvas = SimpleNamespace(
            commands=[],
            removed_items=[],
            updated_boxes=[],
            _note_state_dict=lambda item: {},
            services=SimpleNamespace(
                scene_item_controller=SimpleNamespace(remove_scene_item=controller_remove),
            ),
        )
        set_selected_notes_for(canvas, [])
        canvas.push_command = canvas.commands.append
        canvas.services.selection_controller = SimpleNamespace(update_note_selection_box=canvas.updated_boxes.append)
        _attach_history_service(canvas)
        controller = _note_controller(canvas)
        item = NoteItem(canvas)

        controller.handle_note_focus_out(item)

        controller_remove.assert_called_once_with(item)
        self.assertEqual(canvas.removed_items, [])

    def test_update_note_box_covers_no_brush_and_no_pen_fallbacks(self) -> None:
        scene = QGraphicsScene()
        item = QGraphicsTextItem("Mechanism")
        scene.addItem(item)
        canvas = SimpleNamespace(
            text_style_state=CanvasTextStyleState(
                note_padding=6.0,
                note_box_enabled=False,
                note_border_enabled=True,
                note_box_color=QColor("#ffffff"),
                note_box_alpha=0.4,
                note_border_color=QColor("#111111"),
                note_border_width=1.2,
            ),
        )
        _attach_history_service(canvas)
        controller = _note_controller(canvas)

        controller.update_note_box(item)
        box = item.data(20)
        self.assertEqual(box.brush().style(), Qt.BrushStyle.NoBrush)

        set_text_style_for(canvas, "note_box_enabled", True)
        set_text_style_for(canvas, "note_border_enabled", False)
        controller.update_note_box(item)
        self.assertEqual(box.pen().style(), Qt.PenStyle.NoPen)

    def test_apply_note_style_prefers_line_height_type_enum_when_available(self) -> None:
        class FakeOption:
            def __init__(self) -> None:
                self.alignment = None

            def setAlignment(self, value) -> None:
                self.alignment = value

        class FakeDocument:
            def __init__(self) -> None:
                self.option = FakeOption()
                self.saved_option = None

            def defaultTextOption(self):
                return self.option

            def setDefaultTextOption(self, option) -> None:
                self.saved_option = option

        class FakeBlockFormat:
            class LineHeightType:
                ProportionalHeight = "proportional"

            def __init__(self) -> None:
                self.height = None

            def setLineHeight(self, value, height_type) -> None:
                self.height = (value, height_type)

        class FakeCursor:
            SelectionType = SimpleNamespace(Document="document")
            last_instance = None

            def __init__(self, document) -> None:
                self.document = document
                self.selection = None
                self.block_format = None
                FakeCursor.last_instance = self

            def select(self, selection) -> None:
                self.selection = selection

            def mergeBlockFormat(self, block_format) -> None:
                self.block_format = block_format

        document = FakeDocument()
        item = SimpleNamespace(
            setFont=mock.Mock(),
            setDefaultTextColor=mock.Mock(),
            document=lambda: document,
        )
        selection_controller = SimpleNamespace(update_note_selection_box=mock.Mock())
        canvas = SimpleNamespace(
            text_style_state=CanvasTextStyleState(
                text_font_family="Arial",
                text_font_size=13,
                text_font_weight=QFont.Weight.Bold,
                text_italic=False,
                text_color=QColor("#334455"),
                text_alignment=Qt.AlignmentFlag.AlignHCenter,
                text_line_spacing=1.25,
            ),
            services=SimpleNamespace(selection_controller=selection_controller),
        )
        _attach_history_service(canvas)
        controller = _note_controller(canvas)
        controller.update_note_box = mock.Mock()

        with mock.patch("ui.canvas_note_controller.QTextBlockFormat", FakeBlockFormat), mock.patch(
            "ui.canvas_note_controller.QTextCursor",
            FakeCursor,
        ):
            controller.apply_note_style(item)

        self.assertEqual(document.option.alignment, Qt.AlignmentFlag.AlignHCenter)
        self.assertIs(document.saved_option, document.option)
        self.assertEqual(FakeCursor.last_instance.selection, FakeCursor.SelectionType.Document)
        self.assertEqual(
            FakeCursor.last_instance.block_format.height,
            (125, FakeBlockFormat.LineHeightType.ProportionalHeight),
        )
        controller.update_note_box.assert_called_once_with(item)
        selection_controller.update_note_selection_box.assert_called_once_with(item)


if __name__ == "__main__":
    unittest.main()
