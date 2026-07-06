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
    from ui.canvas_note_controller import CanvasNoteController
    from ui.canvas_scene_items_state import selected_notes_for, set_selected_notes_for
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
