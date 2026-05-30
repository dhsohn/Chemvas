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
    from ui.canvas_note_controller import CanvasNoteController
    from ui.canvas_view import NoteItem
    from ui.selection_controller import SelectionController


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
            select_note=mock.Mock(side_effect=_select_note),
            scene=lambda: scene,
            setFocus=mock.Mock(),
        )
        controller = CanvasNoteController(canvas)

        controller.begin_note_edit(item)

        canvas.select_note.assert_called_once_with(item, additive=False)
        self.assertEqual(selected_notes, [item])
        canvas.setFocus.assert_called_once_with(Qt.FocusReason.MouseFocusReason)
        self.assertIs(scene.focusItem(), item)
        self.assertTrue(item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction)
        self.assertTrue(bool(item.flags() & item.GraphicsItemFlag.ItemIsFocusable))
        self.assertTrue(item.textCursor().hasSelection())

    def test_create_text_note_registers_scene_item_and_applies_style(self) -> None:
        scene = QGraphicsScene()
        item = QGraphicsTextItem()
        pos = QPointF(3.0, 4.0)

        def _attach(target) -> None:
            scene.addItem(target)
            canvas.note_items.append(target)
            canvas._make_selectable(target)

        attach_mock = mock.Mock(side_effect=_attach)
        canvas = SimpleNamespace(
            note_items=[],
            _scene_item_controller=SimpleNamespace(attach_scene_item=attach_mock),
            _new_note_item=mock.Mock(return_value=item),
            _make_selectable=mock.Mock(),
        )
        controller = CanvasNoteController(canvas)
        controller.apply_note_style = mock.Mock()

        created = controller.create_text_note(pos, "Mechanism")

        self.assertIs(created, item)
        self.assertEqual(item.toPlainText(), "Mechanism")
        self.assertEqual(item._last_text, "Mechanism")
        self.assertEqual(item.data(0), "note")
        self.assertEqual(item.pos(), pos)
        self.assertEqual(canvas.note_items, [item])
        self.assertIn(item, scene.items())
        attach_mock.assert_called_once_with(item)
        canvas._make_selectable.assert_called_once_with(item)
        controller.apply_note_style.assert_called_once_with(item)

    def test_apply_text_style_to_selected_and_update_text_note_refresh_note_box(self) -> None:
        scene = QGraphicsScene()
        item = QGraphicsTextItem("Mechanism")
        scene.addItem(item)

        canvas = SimpleNamespace(
            selected_notes=[item],
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
            _selection_color=QColor("#1f5eff"),
            _selection_stroke_delta=0.8,
            _update_note_selection_box=mock.Mock(),
        )
        controller = CanvasNoteController(canvas)

        controller.apply_text_style_to_selected()

        box = item.data(20)
        self.assertIsNotNone(box)
        self.assertTrue(box.isVisible())
        self.assertEqual(item.defaultTextColor().name(), "#334455")
        self.assertTrue(item.font().italic())
        self.assertEqual(item.font().pointSize(), 13)
        canvas._update_note_selection_box.assert_called_once_with(item)

        controller.update_text_note(item, "Updated")
        self.assertEqual(item.toPlainText(), "Updated")
        self.assertEqual(canvas._update_note_selection_box.call_count, 2)

    def test_update_note_box_hides_existing_box_when_disabled(self) -> None:
        scene = QGraphicsScene()
        item = QGraphicsTextItem("Mechanism")
        scene.addItem(item)
        canvas = SimpleNamespace(
            note_padding=6.0,
            note_box_enabled=True,
            note_border_enabled=True,
            note_box_color=QColor("#ffffff"),
            note_box_alpha=0.4,
            note_border_color=QColor("#111111"),
            note_border_width=1.2,
        )
        controller = CanvasNoteController(canvas)

        controller.update_note_box(item)
        box = item.data(20)
        self.assertIsNotNone(box)
        self.assertTrue(box.isVisible())

        canvas.note_box_enabled = False
        canvas.note_border_enabled = False
        controller.update_note_box(item)

        self.assertFalse(box.isVisible())

    def test_selection_controller_note_box_helper_round_trips_visibility(self) -> None:
        scene = QGraphicsScene()
        item = QGraphicsTextItem("Mechanism")
        scene.addItem(item)
        canvas = SimpleNamespace(
            selected_notes=[item],
            note_padding=6.0,
            _selection_color=QColor("#1f5eff"),
            _selection_stroke_delta=0.8,
        )
        controller = SelectionController(canvas)

        controller.update_note_selection_box(item)
        selection_box = item.data(21)
        self.assertIsNotNone(selection_box)
        self.assertTrue(selection_box.isVisible())

        canvas.selected_notes = []
        controller.update_note_selection_box(item)
        self.assertFalse(selection_box.isVisible())

    def test_handle_note_focus_out_adds_updates_and_deletes_commands(self) -> None:
        canvas = SimpleNamespace(
            commands=[],
            removed_items=[],
            selected_notes=[],
            updated_boxes=[],
        )

        def _note_state_dict(item) -> dict:
            return {
                "kind": "note",
                "text": item.toPlainText(),
                "x": item.pos().x(),
                "y": item.pos().y(),
            }

        canvas._note_state_dict = _note_state_dict
        canvas._push_command = canvas.commands.append
        canvas._scene_item_controller = SimpleNamespace(remove_scene_item=canvas.removed_items.append)
        canvas._update_note_selection_box = canvas.updated_boxes.append
        controller = CanvasNoteController(canvas)
        item = NoteItem(canvas)

        item.setPlainText("Mechanism")
        controller.handle_note_focus_out(item)
        self.assertEqual(type(canvas.commands[-1]).__name__, "AddSceneItemsCommand")
        self.assertEqual(item._last_text, "Mechanism")

        item.setPlainText("Mechanism 2")
        controller.handle_note_focus_out(item)
        self.assertEqual(type(canvas.commands[-1]).__name__, "UpdateSceneItemCommand")
        self.assertEqual(item._last_text, "Mechanism 2")

        item.setPlainText("")
        controller.handle_note_focus_out(item)
        self.assertEqual(type(canvas.commands[-1]).__name__, "DeleteSceneItemsCommand")
        self.assertEqual(canvas.removed_items[-1], item)
        self.assertEqual(item._last_text, "")

    def test_handle_note_focus_out_removes_empty_untracked_note_and_selection_box(self) -> None:
        canvas = SimpleNamespace(
            commands=[],
            removed_items=[],
            selected_notes=[],
            updated_boxes=[],
            _note_state_dict=lambda item: {},
        )
        canvas._push_command = canvas.commands.append
        canvas._scene_item_controller = SimpleNamespace(remove_scene_item=canvas.removed_items.append)
        canvas._update_note_selection_box = canvas.updated_boxes.append
        controller = CanvasNoteController(canvas)
        item = NoteItem(canvas)
        canvas.selected_notes.append(item)

        controller.handle_note_focus_out(item)

        self.assertNotIn(item, canvas.selected_notes)
        self.assertEqual(canvas.updated_boxes, [item])
        self.assertEqual(canvas.removed_items, [item])

    def test_handle_note_focus_out_prefers_scene_item_controller_for_removal(self) -> None:
        controller_remove = mock.Mock()
        canvas = SimpleNamespace(
            commands=[],
            removed_items=[],
            selected_notes=[],
            updated_boxes=[],
            _note_state_dict=lambda item: {},
            _scene_item_controller=SimpleNamespace(remove_scene_item=controller_remove),
        )
        canvas._push_command = canvas.commands.append
        canvas._update_note_selection_box = canvas.updated_boxes.append
        controller = CanvasNoteController(canvas)
        item = NoteItem(canvas)

        controller.handle_note_focus_out(item)

        controller_remove.assert_called_once_with(item)
        self.assertEqual(canvas.removed_items, [])

    def test_update_note_box_covers_no_brush_and_no_pen_fallbacks(self) -> None:
        scene = QGraphicsScene()
        item = QGraphicsTextItem("Mechanism")
        scene.addItem(item)
        canvas = SimpleNamespace(
            note_padding=6.0,
            note_box_enabled=False,
            note_border_enabled=True,
            note_box_color=QColor("#ffffff"),
            note_box_alpha=0.4,
            note_border_color=QColor("#111111"),
            note_border_width=1.2,
        )
        controller = CanvasNoteController(canvas)

        controller.update_note_box(item)
        box = item.data(20)
        self.assertEqual(box.brush().style(), Qt.BrushStyle.NoBrush)

        canvas.note_box_enabled = True
        canvas.note_border_enabled = False
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
        canvas = SimpleNamespace(
            text_font_family="Arial",
            text_font_size=13,
            text_font_weight=QFont.Weight.Bold,
            text_italic=False,
            text_color=QColor("#334455"),
            text_alignment=Qt.AlignmentFlag.AlignHCenter,
            text_line_spacing=1.25,
            _update_note_selection_box=mock.Mock(),
        )
        controller = CanvasNoteController(canvas)
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
        canvas._update_note_selection_box.assert_called_once_with(item)


if __name__ == "__main__":
    unittest.main()
