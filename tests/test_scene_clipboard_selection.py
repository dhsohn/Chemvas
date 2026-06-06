import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QRectF
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsTextItem,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.scene_clipboard_selection import select_pasted_content_for_canvas

    class _FakeCanvas:
        def __init__(self, atom_item) -> None:
            self._scene = QGraphicsScene()
            self.selection_controller = SimpleNamespace(update_selection_outline=mock.Mock())
            self.atom_label_service = SimpleNamespace(atom_item_for_id=mock.Mock(return_value=atom_item))
            self.services = SimpleNamespace(
                atom_label_service=self.atom_label_service,
                selection_controller=self.selection_controller,
            )

        def scene(self) -> QGraphicsScene:
            return self._scene


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene clipboard selection tests")
class SceneClipboardSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_select_pasted_content_selects_atoms_scene_items_notes_and_refreshes_outline(self) -> None:
        atom_item = QGraphicsRectItem(QRectF(0.0, 0.0, 4.0, 4.0))
        stale_item = QGraphicsRectItem(QRectF(10.0, 0.0, 4.0, 4.0))
        pasted_item = QGraphicsRectItem(QRectF(20.0, 0.0, 4.0, 4.0))
        note_item = QGraphicsTextItem("note")
        note_item.setData(0, "note")
        for item in (atom_item, stale_item, pasted_item, note_item):
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        canvas = _FakeCanvas(atom_item)
        for item in (atom_item, stale_item, pasted_item, note_item):
            canvas.scene().addItem(item)
        stale_item.setSelected(True)
        clear_note_selection = mock.Mock()
        select_note = mock.Mock()

        select_pasted_content_for_canvas(
            canvas,
            atom_ids={7},
            scene_items=[None, pasted_item, note_item],
            clear_note_selection=clear_note_selection,
            select_note=select_note,
        )

        self.assertFalse(stale_item.isSelected())
        self.assertTrue(atom_item.isSelected())
        self.assertTrue(pasted_item.isSelected())
        self.assertTrue(note_item.isSelected())
        canvas.atom_label_service.atom_item_for_id.assert_called_once_with(7)
        clear_note_selection.assert_called_once_with()
        select_note.assert_called_once_with(note_item)
        canvas.selection_controller.update_selection_outline.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
