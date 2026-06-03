import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QRectF
    from PyQt6.QtWidgets import QApplication, QGraphicsItem, QGraphicsTextItem
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.history import CompositeCommand

    from tests.test_scene_ops_controller import (
        SceneOpsController,
        _FakeCanvas,
        _make_rect_item,
        _make_ring_item,
    )


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene ops controller tests")
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

    def test_delete_selected_items_ignores_invalid_bond_and_filtered_items(self) -> None:
        canvas = _FakeCanvas()
        invalid_bond = _make_rect_item("bond", data1=999)
        handle = _make_rect_item("handle")
        note_box = _make_rect_item("note_box")
        note_select = _make_rect_item("note_select")
        for item in (invalid_bond, handle, note_box, note_select):
            canvas.add_item(item, selected=True)

        controller = SceneOpsController(canvas)

        self.assertFalse(controller.delete_selected_items())
        self.assertEqual(canvas.delete_bond_calls, [])
        self.assertEqual(canvas.remove_bond_calls, [])
        self.assertEqual(canvas.clear_handles_calls, 0)
        self.assertEqual(canvas.removed_scene_items, [])
        self.assertEqual(canvas.pushed_commands, [])

    def test_flip_selected_items_updates_standalone_ring_and_mark_items(self) -> None:
        canvas = _FakeCanvas()
        ring_item = _make_ring_item()
        mark_item = _make_rect_item(
            "mark",
            data1={"atom_id": None},
            state={"kind": "mark", "atom_id": None, "x": 4.0, "y": 5.0},
            rect=QRectF(0.0, 0.0, 4.0, 4.0),
        )
        canvas.add_item(ring_item, selected=True)
        canvas.add_item(mark_item, selected=True)

        controller = SceneOpsController(canvas)
        controller.flip_selected_items(horizontal=True)

        self.assertEqual(len(canvas.pushed_commands), 1)
        self.assertIsInstance(canvas.pushed_commands[0], CompositeCommand)
        self.assertEqual(canvas.update_selection_outline_calls, 1)
        self.assertEqual(ring_item.data(9)["points"], [(12.0, 0.0), (0.0, 0.0), (6.0, 10.0)])
        self.assertEqual(mark_item.data(9)["x"], 0.0)
        self.assertEqual(mark_item.data(9)["y"], 5.0)

    def test_flip_selected_items_skips_centerless_items(self) -> None:
        canvas = _FakeCanvas()
        note_item = QGraphicsTextItem("")
        note_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        note_item.setData(0, "note")
        note_item.setData(9, {"kind": "note", "text": "skip", "x": 1.0, "y": 2.0})
        canvas.add_item(note_item, selected=True)

        controller = SceneOpsController(canvas)
        controller.flip_selected_items(horizontal=True)

        self.assertEqual(canvas.pushed_commands, [])
        self.assertEqual(canvas.update_selection_outline_calls, 0)
        self.assertEqual(note_item.data(9), {"kind": "note", "text": "skip", "x": 1.0, "y": 2.0})

    def test_flip_selected_items_skips_when_flipped_state_matches_original(self) -> None:
        canvas = _FakeCanvas()
        mark_item = _make_rect_item(
            "mark",
            data1={"atom_id": None},
            state={"kind": "mark", "atom_id": None, "x": 2.0, "y": 2.0},
            rect=QRectF(0.0, 0.0, 4.0, 4.0),
        )
        canvas.add_item(mark_item, selected=True)

        controller = SceneOpsController(canvas)
        controller.flip_selected_items(horizontal=True)

        self.assertEqual(canvas.pushed_commands, [])
        self.assertEqual(canvas.update_selection_outline_calls, 0)
        self.assertEqual(mark_item.data(9), {"kind": "mark", "atom_id": None, "x": 2.0, "y": 2.0})


if __name__ == "__main__":
    unittest.main()
