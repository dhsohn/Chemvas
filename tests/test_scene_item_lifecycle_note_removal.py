import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsScene,
        QGraphicsTextItem,
        QGraphicsView,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.ui.canvas_scene_items_state import (
        add_selected_note_for,
        append_scene_item_for,
        selected_notes_for,
    )
    from chemvas.ui.scene_item_lifecycle_service import SceneItemLifecycleService


if QApplication is not None:

    class _Canvas(QGraphicsView):
        def __init__(self) -> None:
            super().__init__(QGraphicsScene())
            self.selection_controller = SimpleNamespace(
                update_selection_outline=mock.Mock()
            )
            self.services = canvas_runtime_services(
                selection_controller=self.selection_controller
            )

        def add_note(self, *, selected: bool) -> QGraphicsTextItem:
            note = QGraphicsTextItem("note")
            note.setData(0, "note")
            self.scene().addItem(note)
            append_scene_item_for(self, "note_items", note)
            if selected:
                add_selected_note_for(self, note)
            return note


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for lifecycle note removal tests"
)
class SceneItemLifecycleNoteRemovalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_removing_selected_note_refreshes_selection_outline(self) -> None:
        canvas = _Canvas()
        note = canvas.add_note(selected=True)
        service = SceneItemLifecycleService(canvas, graph_service=SimpleNamespace())

        # The DeleteTool erase path removes notes directly; the outline must be
        # redrawn or a notes-only group box would linger over the erased note.
        service.remove_scene_item(note)

        self.assertNotIn(note, selected_notes_for(canvas))
        self.assertIsNone(note.scene())
        canvas.selection_controller.update_selection_outline.assert_called_once_with()

    def test_removing_unselected_note_skips_outline_refresh(self) -> None:
        canvas = _Canvas()
        note = canvas.add_note(selected=False)
        service = SceneItemLifecycleService(canvas, graph_service=SimpleNamespace())

        service.remove_scene_item(note)

        self.assertIsNone(note.scene())
        canvas.selection_controller.update_selection_outline.assert_not_called()
