import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
)

from chemvas.ui.scene_clipboard_selection import select_pasted_content_for_canvas


class _FakeCanvas:
    def __init__(self, atom_item) -> None:
        self._scene = QGraphicsScene()
        self.selection_controller = SimpleNamespace(
            update_selection_outline=mock.Mock()
        )
        self.atom_label_service = SimpleNamespace(
            atom_item_for_id=mock.Mock(return_value=atom_item)
        )
        self.services = canvas_runtime_services(
            atom_label_service=self.atom_label_service,
            selection_controller=self.selection_controller,
        )

    def scene(self) -> QGraphicsScene:
        return self._scene


class SceneClipboardSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_select_pasted_content_selects_atoms_scene_items_notes_and_refreshes_outline(
        self,
    ) -> None:
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
        selection_changed = mock.Mock()
        canvas.scene().selectionChanged.connect(selection_changed)
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
        selection_changed.assert_not_called()
        self.assertFalse(canvas.scene().signalsBlocked())

    def test_paste_selection_restores_signal_block_state_after_note_failure(self):
        atom_item = QGraphicsRectItem(QRectF(0.0, 0.0, 4.0, 4.0))
        note_item = QGraphicsTextItem("note")
        note_item.setData(0, "note")
        canvas = _FakeCanvas(atom_item)
        canvas.scene().addItem(atom_item)
        canvas.scene().addItem(note_item)
        for blocked in (False, True):
            with self.subTest(blocked=blocked):
                canvas.scene().blockSignals(blocked)
                with self.assertRaisesRegex(RuntimeError, "note selection failed"):
                    select_pasted_content_for_canvas(
                        canvas,
                        atom_ids={7},
                        scene_items=[note_item],
                        clear_note_selection=mock.Mock(),
                        select_note=mock.Mock(
                            side_effect=RuntimeError("note selection failed")
                        ),
                    )
                self.assertEqual(canvas.scene().signalsBlocked(), blocked)
