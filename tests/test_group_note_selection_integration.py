import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QCoreApplication, QEvent, QPointF
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsItem,
        QGraphicsRectItem,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.ui.canvas_atom_graphics_state import set_atom_item_for
    from chemvas.ui.canvas_group_state import group_state_for
    from chemvas.ui.canvas_lifecycle import schedule_canvas_deletion_for
    from chemvas.ui.canvas_model_access import model_for
    from chemvas.ui.canvas_scene_items_state import (
        append_scene_item_for,
        selected_notes_for,
    )
    from chemvas.ui.canvas_view import CanvasView
    from chemvas.ui.move_access import move_item_for
    from chemvas.ui.scene_group_operations import group_selection_for
    from chemvas.ui.selection_collection_access import selection_snapshot_for


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for grouped-note integration tests"
)
class GroupedNoteSelectionIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _add_atom(self, canvas, x: float):
        atom_id = model_for(canvas).add_atom("C", x, 0.0)
        item = QGraphicsRectItem(0.0, 0.0, 5.0, 5.0)
        item.setData(0, "atom")
        item.setData(1, atom_id)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        canvas.scene().addItem(item)
        set_atom_item_for(canvas, atom_id, item)
        return atom_id, item

    def _dispose_canvas(self, canvas) -> None:
        schedule_canvas_deletion_for(canvas)
        QCoreApplication.sendPostedEvents(canvas, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_grouped_note_follows_shift_click_and_drag(self) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        canvas.services.tooling.tools.set_active("select")
        _, atom_item_a = self._add_atom(canvas, 0.0)
        _, atom_item_b = self._add_atom(canvas, 80.0)
        note = canvas.services.interaction.note_controller.create_text_note(
            QPointF(40.0, 40.0), "label"
        )
        append_scene_item_for(canvas, "note_items", note)

        atom_item_a.setSelected(True)
        atom_item_b.setSelected(True)
        canvas.services.selection.selection_controller.select_note(note, additive=True)
        self.assertTrue(group_selection_for(canvas))
        self.assertEqual(len(group_state_for(canvas).groups), 1)

        canvas.services.selection.selection_controller.clear_note_selection()
        canvas.scene().clearSelection()
        self.assertNotIn(note, selected_notes_for(canvas))

        # Shift-click routes through toggle_item_selection, whose
        # set_scene_items_selected_for blocks the selectionChanged expansion hook,
        # so the grouped note must be toggled explicitly through the note service.
        canvas.services.selection.selection_controller.toggle_item_selection(
            atom_item_a
        )
        self.assertTrue(atom_item_a.isSelected())
        self.assertTrue(atom_item_b.isSelected())
        self.assertIn(note, selected_notes_for(canvas))

        # The selected note must ride along in the drag snapshot; the drag path
        # moves every snapshot selection item, so the note follows the group.
        snapshot = selection_snapshot_for(canvas)
        self.assertIn(note, snapshot.selection_items)
        before = note.pos()
        move_item_for(canvas, note, 25.0, 10.0, update_selection=False)
        self.assertEqual(note.pos().x() - before.x(), 25.0)
        self.assertEqual(note.pos().y() - before.y(), 10.0)

        # Toggling the same member again drops the whole group, note included.
        canvas.services.selection.selection_controller.toggle_item_selection(
            atom_item_a
        )
        self.assertFalse(atom_item_a.isSelected())
        self.assertFalse(atom_item_b.isSelected())
        self.assertNotIn(note, selected_notes_for(canvas))


if __name__ == "__main__":
    unittest.main()
