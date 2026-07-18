import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsTextItem
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.ui.canvas_group_state import register_group_for
    from chemvas.ui.canvas_scene_items_state import (
        selected_notes_for,
        set_selected_notes_for,
    )
    from chemvas.ui.selection_note_service import SelectionNoteService
    from chemvas.ui.selection_style_state import SelectionStyleState


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for selection note service tests"
)
class SelectionNoteServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_select_note_replaces_or_extends_note_selection_and_updates_boxes(
        self,
    ) -> None:
        scene = QGraphicsScene()
        note_a = QGraphicsTextItem("A")
        note_b = QGraphicsTextItem("B")
        scene.addItem(note_a)
        scene.addItem(note_b)
        canvas = SimpleNamespace(
            note_padding=6.0,
            selection_style_state=SelectionStyleState(
                color=QColor("#1f5eff"), stroke_delta=0.8
            ),
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

    def test_toggle_note_selection_adds_or_removes_note_and_updates_box_visibility(
        self,
    ) -> None:
        scene = QGraphicsScene()
        note = QGraphicsTextItem("A")
        scene.addItem(note)
        canvas = SimpleNamespace(
            note_padding=6.0,
            selection_style_state=SelectionStyleState(
                color=QColor("#1f5eff"), stroke_delta=0.8
            ),
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
            selection_style_state=SelectionStyleState(
                color=QColor("#1f5eff"), stroke_delta=0.8
            ),
        )
        set_selected_notes_for(canvas, [note_a, note_b])
        service = SelectionNoteService(canvas)
        service.update_note_selection_box(note_a)
        service.update_note_selection_box(note_b)

        service.clear_note_selection()

        self.assertEqual(selected_notes_for(canvas), [])
        self.assertFalse(note_a.data(21).isVisible())
        self.assertFalse(note_b.data(21).isVisible())

    def _note_canvas(self):
        return SimpleNamespace(
            note_padding=6.0,
            selection_style_state=SelectionStyleState(
                color=QColor("#1f5eff"), stroke_delta=0.8
            ),
        )

    def test_toggle_note_selection_deselects_notes_only_group_as_unit(self) -> None:
        scene = QGraphicsScene()
        note_a = QGraphicsTextItem("A")
        note_b = QGraphicsTextItem("B")
        note_a.setData(0, "note")
        note_b.setData(0, "note")
        scene.addItem(note_a)
        scene.addItem(note_b)
        canvas = self._note_canvas()
        canvas.scene = lambda: scene
        set_selected_notes_for(canvas, [note_a, note_b])
        register_group_for(canvas, set(), [note_a, note_b])
        service = SelectionNoteService(canvas)

        # Ctrl-clicking one member must drop the whole notes-only group, not
        # leave a partial selection behind.
        service.toggle_note_selection(note_a)

        self.assertEqual(selected_notes_for(canvas), [])

    def test_note_selection_changes_refresh_selection_outline(self) -> None:
        scene = QGraphicsScene()
        note = QGraphicsTextItem("A")
        scene.addItem(note)
        canvas = self._note_canvas()
        outline_refresh = mock.Mock()
        canvas.services = SimpleNamespace(
            selection_controller=SimpleNamespace(
                update_selection_outline=outline_refresh
            )
        )
        set_selected_notes_for(canvas, [])
        service = SelectionNoteService(canvas)

        # No-op paths must not redraw.
        service.clear_note_selection()
        service.set_note_selected(note, False)
        outline_refresh.assert_not_called()

        # Real changes must redraw so notes-only group boxes track note selection.
        service.select_note(note, additive=True)
        self.assertEqual(outline_refresh.call_count, 1)
        service.set_note_selected(note, True)
        self.assertEqual(outline_refresh.call_count, 1)
        service.toggle_note_selection(note)
        self.assertEqual(outline_refresh.call_count, 2)
        service.select_note(note, additive=True)
        service.clear_note_selection()
        self.assertEqual(outline_refresh.call_count, 4)

    def test_set_note_selected_is_idempotent_in_both_directions(self) -> None:
        scene = QGraphicsScene()
        note = QGraphicsTextItem("A")
        scene.addItem(note)
        canvas = self._note_canvas()
        set_selected_notes_for(canvas, [])
        service = SelectionNoteService(canvas)

        service.set_note_selected(note, False)
        self.assertEqual(selected_notes_for(canvas), [])

        service.set_note_selected(note, True)
        service.set_note_selected(note, True)
        self.assertEqual(selected_notes_for(canvas), [note])
        self.assertTrue(note.data(21).isVisible())

        service.set_note_selected(note, False)
        self.assertEqual(selected_notes_for(canvas), [])
        self.assertFalse(note.data(21).isVisible())

    def test_apply_group_note_toggle_directions_and_autodecide(self) -> None:
        scene = QGraphicsScene()
        note_a = QGraphicsTextItem("A")
        note_b = QGraphicsTextItem("B")
        scene.addItem(note_a)
        scene.addItem(note_b)
        canvas = self._note_canvas()
        set_selected_notes_for(canvas, [])
        service = SelectionNoteService(canvas)

        # Explicit select, then explicit deselect.
        service.apply_group_note_toggle([note_a, note_b], True)
        self.assertEqual(selected_notes_for(canvas), [note_a, note_b])
        service.apply_group_note_toggle([note_a, note_b], False)
        self.assertEqual(selected_notes_for(canvas), [])

        # selected=None decides from current state: none selected -> select all.
        service.apply_group_note_toggle([note_a, note_b], None)
        self.assertEqual(selected_notes_for(canvas), [note_a, note_b])
        # All selected -> None deselects all.
        service.apply_group_note_toggle([note_a, note_b], None)
        self.assertEqual(selected_notes_for(canvas), [])

        # Empty list is a no-op.
        service.apply_group_note_toggle([], True)
        self.assertEqual(selected_notes_for(canvas), [])
