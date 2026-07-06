import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsItem,
        QGraphicsRectItem,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.canvas_atom_graphics_state import set_atom_item_for
    from ui.canvas_group_state import group_state_for
    from ui.canvas_model_access import model_for
    from ui.canvas_scene_items_state import append_scene_item_for, selected_notes_for
    from ui.canvas_view import CanvasView
    from ui.scene_group_operations import group_selection_for


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for grouped-note integration tests")
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

    def test_shift_click_group_member_selects_and_deselects_grouped_note(self) -> None:
        canvas = CanvasView()
        canvas.services.tools.set_active("select")
        _, atom_item_a = self._add_atom(canvas, 0.0)
        _, atom_item_b = self._add_atom(canvas, 80.0)
        note = canvas.services.note_controller.create_text_note(QPointF(40.0, 40.0), "label")
        append_scene_item_for(canvas, "note_items", note)

        atom_item_a.setSelected(True)
        atom_item_b.setSelected(True)
        canvas.services.selection_controller.select_note(note, additive=True)
        self.assertTrue(group_selection_for(canvas))
        self.assertEqual(len(group_state_for(canvas).groups), 1)

        canvas.services.selection_controller.clear_note_selection()
        canvas.scene().clearSelection()
        self.assertNotIn(note, selected_notes_for(canvas))

        # Shift-click routes through toggle_item_selection; the grouped note must
        # follow the group even though set_scene_items_selected_for blocks the
        # selectionChanged expansion hook.
        canvas.services.selection_controller.toggle_item_selection(atom_item_a)
        self.assertTrue(atom_item_a.isSelected())
        self.assertTrue(atom_item_b.isSelected())
        self.assertIn(note, selected_notes_for(canvas))

        canvas.services.selection_controller.toggle_item_selection(atom_item_a)
        self.assertFalse(atom_item_a.isSelected())
        self.assertFalse(atom_item_b.isSelected())
        self.assertNotIn(note, selected_notes_for(canvas))


if __name__ == "__main__":
    unittest.main()
