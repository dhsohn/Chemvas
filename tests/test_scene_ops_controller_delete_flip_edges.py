import os
import unittest

from tests.ring_support import make_ring

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QApplication, QGraphicsItem

from chemvas.ui.annotations.items import NoteItem
from chemvas.ui.history.history_commands import SetSceneGeometryCommand
from tests.scene_operation_support import (
    _FakeCanvas,
    _make_rect_item,
    scene_delete_controller_for,
    scene_transform_controller_for,
)


class SceneOpsControllerDeleteFlipEdgesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.clear(mode=clipboard.Mode.Clipboard)

    def tearDown(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.clear(mode=clipboard.Mode.Clipboard)

    def test_delete_selected_items_ignores_invalid_bond_and_filtered_items(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        invalid_bond = _make_rect_item("bond", data1=999)
        handle = _make_rect_item("handle")
        note_box = _make_rect_item("note_box")
        note_select = _make_rect_item("note_select")
        for item in (invalid_bond, handle, note_box, note_select):
            canvas.add_item(item, selected=True)

        controller = scene_delete_controller_for(canvas)

        self.assertFalse(controller.delete_selected_items())
        self.assertEqual(canvas.delete_bond_calls, [])
        self.assertEqual(canvas.remove_bond_calls, [])
        self.assertEqual(canvas.clear_handles_calls, 0)
        self.assertEqual(canvas.removed_scene_items, [])
        self.assertEqual(canvas.pushed_commands, [])

    def test_flip_selected_items_updates_standalone_ring_and_mark_items(self) -> None:
        canvas = _FakeCanvas()
        atom_ids = [
            canvas.add_atom("C", x, y)
            for x, y in [(0.0, 0.0), (12.0, 0.0), (6.0, 10.0)]
        ]
        ring_item = make_ring(canvas=canvas, atom_ids=atom_ids)
        for atom_id in atom_ids:
            canvas.atom_items[atom_id].setSelected(True)
        mark_item = _make_rect_item(
            "mark",
            data1={"atom_id": None},
            state={"kind": "mark", "atom_id": None, "x": 4.0, "y": 5.0},
            rect=QRectF(0.0, 0.0, 4.0, 4.0),
        )
        canvas.add_item(ring_item, selected=True)
        canvas.add_item(mark_item, selected=True)

        controller = scene_transform_controller_for(canvas)
        controller.flip_selected_items(horizontal=True)

        self.assertEqual(len(canvas.pushed_commands), 1)
        self.assertIsInstance(canvas.pushed_commands[0], SetSceneGeometryCommand)
        self.assertEqual(canvas.update_selection_outline_calls, 1)
        self.assertEqual(
            canvas.scene_item_state(ring_item)["points"],
            [(12.0, 0.0), (0.0, 0.0), (6.0, 10.0)],
        )
        self.assertEqual(canvas.scene_item_state(mark_item)["x"], 8.0)
        self.assertEqual(canvas.scene_item_state(mark_item)["y"], 5.0)

    def test_flip_selected_items_skips_centerless_items(self) -> None:
        canvas = _FakeCanvas()
        note_item = NoteItem(canvas.runtime_state.note_state)
        note_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        note_item.setData(0, "note")
        canvas.add_item(note_item, selected=True)
        note_item.boundingRect()
        before = canvas.scene_item_state(note_item)

        controller = scene_transform_controller_for(canvas)
        controller.flip_selected_items(horizontal=True)

        self.assertEqual(canvas.pushed_commands, [])
        self.assertEqual(canvas.update_selection_outline_calls, 0)
        self.assertEqual(canvas.scene_item_state(note_item), before)

    def test_flip_selected_items_skips_when_flipped_state_matches_original(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        mark_item = _make_rect_item(
            "mark",
            data1={"atom_id": None},
            state={"kind": "mark", "atom_id": None, "x": 2.0, "y": 2.0},
            rect=QRectF(-2.0, -2.0, 4.0, 4.0),
        )
        canvas.add_item(mark_item, selected=True)
        before = canvas.scene_item_state(mark_item)

        controller = scene_transform_controller_for(canvas)
        controller.flip_selected_items(horizontal=True)

        self.assertEqual(canvas.pushed_commands, [])
        self.assertEqual(canvas.update_selection_outline_calls, 0)
        self.assertEqual(canvas.scene_item_state(mark_item), before)
