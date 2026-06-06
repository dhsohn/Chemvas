import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsTextItem
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.canvas_scene_items_state import selected_notes_for, set_selected_notes_for
    from ui.selection_note_service import SelectionNoteService
    from ui.selection_style_state import SelectionStyleState


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for selection note service tests")
class SelectionNoteServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_select_note_replaces_or_extends_note_selection_and_updates_boxes(self) -> None:
        scene = QGraphicsScene()
        note_a = QGraphicsTextItem("A")
        note_b = QGraphicsTextItem("B")
        scene.addItem(note_a)
        scene.addItem(note_b)
        canvas = SimpleNamespace(
            note_padding=6.0,
            selection_style_state=SelectionStyleState(color=QColor("#1f5eff"), stroke_delta=0.8),
        )
        set_selected_notes_for(canvas, [note_a])
        service = SelectionNoteService(canvas)

        service.select_note(note_b, additive=False)

        self.assertEqual(selected_notes_for(canvas), [note_b])
        self.assertTrue(note_a.data(21) is None or not note_a.data(21).isVisible())
        self.assertTrue(note_b.data(21).isVisible())

        service.select_note(note_a, additive=True)

        self.assertEqual(selected_notes_for(canvas), [note_b, note_a])
        self.assertTrue(note_a.data(21).isVisible())

    def test_toggle_note_selection_adds_or_removes_note_and_updates_box_visibility(self) -> None:
        scene = QGraphicsScene()
        note = QGraphicsTextItem("A")
        scene.addItem(note)
        canvas = SimpleNamespace(
            note_padding=6.0,
            selection_style_state=SelectionStyleState(color=QColor("#1f5eff"), stroke_delta=0.8),
        )
        set_selected_notes_for(canvas, [])
        service = SelectionNoteService(canvas)

        service.toggle_note_selection(note)
        self.assertEqual(selected_notes_for(canvas), [note])
        self.assertTrue(note.data(21).isVisible())

        service.toggle_note_selection(note)
        self.assertEqual(selected_notes_for(canvas), [])
        self.assertFalse(note.data(21).isVisible())

    def test_clear_note_selection_hides_existing_selection_boxes(self) -> None:
        scene = QGraphicsScene()
        note_a = QGraphicsTextItem("A")
        note_b = QGraphicsTextItem("B")
        scene.addItem(note_a)
        scene.addItem(note_b)
        canvas = SimpleNamespace(
            note_padding=6.0,
            selection_style_state=SelectionStyleState(color=QColor("#1f5eff"), stroke_delta=0.8),
        )
        set_selected_notes_for(canvas, [note_a, note_b])
        service = SelectionNoteService(canvas)
        service.update_note_selection_box(note_a)
        service.update_note_selection_box(note_b)

        service.clear_note_selection()

        self.assertEqual(selected_notes_for(canvas), [])
        self.assertFalse(note_a.data(21).isVisible())
        self.assertFalse(note_b.data(21).isVisible())
