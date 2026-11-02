import os
import unittest
from types import SimpleNamespace
from unittest import mock

from chemvas.ui.canvas.canvas_atom_graphics_state import CanvasAtomGraphicsState
from chemvas.ui.canvas.canvas_group_state import CanvasGroupState, register_group_for
from chemvas.ui.canvas.canvas_scene_items_state import (
    CanvasSceneItemsState,
    require_scene_record_id,
)
from tests.note_support import register_note_double
from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state
from tests.selection_support import build_selection_controller

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)

from chemvas.adapters.qt.renderer import Renderer
from chemvas.domain.document import MoleculeModel
from chemvas.ui.canvas.canvas_mark_registry import CanvasMarkRegistry
from chemvas.ui.scene.scene_item_lifecycle_service import SceneItemLifecycleService


class _Canvas(QGraphicsView):
    def __init__(self) -> None:
        super().__init__(QGraphicsScene())
        self.renderer = Renderer()
        self.model = MoleculeModel()
        self.runtime_state = canvas_runtime_state(
            atom_graphics_state=CanvasAtomGraphicsState(),
            group_state=CanvasGroupState(),
            mark_registry=CanvasMarkRegistry(),
            scene_items_state=CanvasSceneItemsState(),
        )
        self.selection_controller = SimpleNamespace(
            discard_removed_note=mock.Mock(return_value=False),
            update_selection_outline=mock.Mock(),
            update_note_selection_box=mock.Mock(),
        )
        self.services = canvas_runtime_services(selection=self.selection_controller)

    def add_note(self, *, selected: bool) -> QGraphicsTextItem:
        note = QGraphicsTextItem("note")
        note.setData(0, "note")
        self.scene().addItem(note)
        register_note_double(self, note)
        if selected:
            self.runtime_state.selection_state.add_selected_note(note)
        return note


class SceneItemLifecycleNoteRemovalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_removing_selected_note_routes_through_selection_controller(self) -> None:
        canvas = _Canvas()
        note = canvas.add_note(selected=True)
        canvas.selection_controller.discard_removed_note.return_value = True
        service = SceneItemLifecycleService(
            canvas,
            graph_service=SimpleNamespace(),
            selection_controller=canvas.selection_controller,
        )

        # The DeleteTool erase path removes notes directly; discard drops the
        # selection write, then the outline refreshes after scene removal.
        service.remove_scene_item(note)

        canvas.selection_controller.discard_removed_note.assert_called_once_with(note)
        canvas.selection_controller.update_selection_outline.assert_called_once_with()
        self.assertIsNone(note.scene())
        self.assertNotIn(note, canvas.runtime_state.scene_items("note_items"))

    def test_removing_unselected_note_still_routes_through_controller(self) -> None:
        canvas = _Canvas()
        note = canvas.add_note(selected=False)
        service = SceneItemLifecycleService(
            canvas,
            graph_service=SimpleNamespace(),
            selection_controller=canvas.selection_controller,
        )

        service.remove_scene_item(note)

        canvas.selection_controller.discard_removed_note.assert_called_once_with(note)
        canvas.selection_controller.update_selection_outline.assert_not_called()
        self.assertIsNone(note.scene())

    def test_selected_note_outline_refreshes_after_scene_removal(self) -> None:
        canvas = _Canvas()
        selected = canvas.add_note(selected=True)
        unselected = canvas.add_note(selected=False)
        events: list[tuple[str, bool]] = []

        def discard(item):
            events.append(("discard", item.scene() is not None))
            canvas.runtime_state.selection_state.remove_selected_note(item)
            return item is selected

        def refresh_outline():
            events.append(("outline", selected.scene() is not None))

        canvas.selection_controller.discard_removed_note = mock.Mock(
            side_effect=discard
        )
        canvas.selection_controller.update_selection_outline = mock.Mock(
            side_effect=refresh_outline
        )
        service = SceneItemLifecycleService(
            canvas,
            graph_service=SimpleNamespace(),
            selection_controller=canvas.selection_controller,
        )

        service.remove_scene_item(selected)
        service.remove_scene_item(unselected)

        self.assertEqual(
            events,
            [
                ("discard", True),
                ("outline", False),
                ("discard", True),
            ],
        )
        canvas.selection_controller.update_selection_outline.assert_called_once_with()

    def test_erasing_selected_mixed_group_note_leaves_molecule_selection(
        self,
    ) -> None:
        canvas = QGraphicsView(QGraphicsScene())
        canvas.renderer = Renderer()
        canvas.model = MoleculeModel()
        canvas.runtime_state = canvas_runtime_state(
            atom_graphics_state=CanvasAtomGraphicsState(),
            group_state=CanvasGroupState(),
            mark_registry=CanvasMarkRegistry(),
            scene_items_state=CanvasSceneItemsState(),
        )
        selection = build_selection_controller(canvas, render=False)
        outline_refresh = selection.outline_service.update_selection_outline
        canvas.services = canvas_runtime_services(selection=selection)
        atom_id = canvas.model.add_atom("C", 0.0, 0.0)
        atom_item = QGraphicsRectItem(0.0, 0.0, 5.0, 5.0)
        atom_item.setData(0, "atom")
        atom_item.setData(1, atom_id)
        atom_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        canvas.scene().addItem(atom_item)
        canvas.runtime_state.atom_graphics_state.atom_items[atom_id] = atom_item
        atom_item.setSelected(True)
        note = QGraphicsTextItem("note")
        note.setData(0, "note")
        canvas.scene().addItem(note)
        register_note_double(canvas, note)
        canvas.runtime_state.selection_state.add_selected_note(note)
        register_group_for(canvas, {atom_id}, [require_scene_record_id(note)])
        service = SceneItemLifecycleService(
            canvas,
            graph_service=SimpleNamespace(),
            selection_controller=selection,
        )

        # Erase must not apply set_note_selected(False) group semantics: the
        # molecule stays selected when only the note leaves the scene.
        service.remove_scene_item(note)

        self.assertTrue(atom_item.isSelected())
        self.assertNotIn(note, canvas.runtime_state.selection_state.selected_notes)
        self.assertIsNone(note.scene())
        outline_refresh.assert_called_once_with()
