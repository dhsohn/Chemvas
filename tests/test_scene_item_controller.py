import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPolygonF
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsItemGroup,
        QGraphicsPathItem,
        QGraphicsPolygonItem,
        QGraphicsScene,
        QGraphicsTextItem,
    )
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from ui.scene_item_controller import SceneItemController


class _FakeCanvas:
    def __init__(self) -> None:
        self._scene = QGraphicsScene()
        self.renderer = SimpleNamespace(
            style=SimpleNamespace(bond_length_px=20.0),
            ring_fill_brush=lambda: QBrush(QColor("#AA4400")),
        )
        self.model = SimpleNamespace(atoms={})
        self.ring_items = []
        self.mark_items = []
        self.note_items = []
        self.arrow_items = []
        self.ts_bracket_items = []
        self.orbital_items = []
        self.selected_notes = []
        self._marks_by_atom = {}
        self._handle_target = None
        self.make_selectable_calls = []
        self.updated_bond_ids = []
        self.bond_lookup = {}
        self.removed_mark_items = []
        self.updated_note_boxes = []
        self.clear_handles_calls = 0

    def scene(self):
        return self._scene

    def _make_selectable(self, item) -> None:
        self.make_selectable_calls.append(item)

    def _bond_id_between(self, atom_a: int, atom_b: int):
        return self.bond_lookup.get((atom_a, atom_b))

    def update_bond_geometry(self, bond_id: int) -> None:
        self.updated_bond_ids.append(bond_id)

    def _remove_mark_item(self, item) -> None:
        self.removed_mark_items.append(item)
        if item in self.mark_items:
            self.mark_items.remove(item)
        data = item.data(1) or {}
        atom_id = data.get("atom_id") if isinstance(data, dict) else None
        if isinstance(atom_id, int):
            marks = self._marks_by_atom.get(atom_id)
            if marks and item in marks:
                marks.remove(item)
        self._scene.removeItem(item)

    def _update_note_selection_box(self, item) -> None:
        self.updated_note_boxes.append(item)

    def clear_handles(self) -> None:
        self.clear_handles_calls += 1
        self._handle_target = None


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene item controller tests")
class SceneItemControllerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.canvas = _FakeCanvas()
        self.controller = SceneItemController(self.canvas)

    def test_restore_scene_item_updates_registries_without_duplicates(self) -> None:
        mark = QGraphicsTextItem("+")
        mark.setData(0, "mark")
        mark.setData(1, {"atom_id": 7})
        note = QGraphicsTextItem("Mechanism")
        note.setData(0, "note")

        self.controller.restore_scene_item(mark)
        self.controller.restore_scene_item(mark)
        self.controller.restore_scene_item(note)

        self.assertEqual(self.canvas.mark_items, [mark])
        self.assertEqual(self.canvas._marks_by_atom, {7: [mark]})
        self.assertEqual(self.canvas.note_items, [note])
        self.assertEqual(note.textInteractionFlags(), Qt.TextInteractionFlag.NoTextInteraction)
        self.assertEqual(self.canvas.make_selectable_calls, [mark, note])
        self.assertIs(mark.scene(), self.canvas.scene())
        self.assertIs(note.scene(), self.canvas.scene())

    def test_remove_scene_item_cleans_note_selection_and_handle_targets(self) -> None:
        note = QGraphicsTextItem("Label")
        note.setData(0, "note")
        curved = QGraphicsPathItem(QPainterPath())
        curved.setData(0, "curved_single")

        self.canvas.scene().addItem(note)
        self.canvas.note_items.append(note)
        self.canvas.selected_notes.append(note)
        self.canvas.scene().addItem(curved)
        self.canvas.arrow_items.append(curved)
        self.canvas._handle_target = curved

        self.controller.remove_scene_item(note)
        self.controller.remove_scene_item(curved)

        self.assertNotIn(note, self.canvas.selected_notes)
        self.assertEqual(self.canvas.updated_note_boxes, [note])
        self.assertNotIn(note, self.canvas.note_items)
        self.assertIsNone(note.scene())
        self.assertNotIn(curved, self.canvas.arrow_items)
        self.assertIsNone(curved.scene())
        self.assertEqual(self.canvas.clear_handles_calls, 1)
        self.assertIsNone(self.canvas._handle_target)

    def test_remove_scene_item_cleans_mark_registry_after_helper_removal(self) -> None:
        mark = QGraphicsTextItem("-")
        mark.setData(0, "mark")
        mark.setData(1, {"atom_id": 11})
        self.canvas.scene().addItem(mark)
        self.canvas.mark_items.append(mark)
        self.canvas._marks_by_atom[11] = [mark]

        self.controller.remove_scene_item(mark)

        self.assertEqual(self.canvas.removed_mark_items, [mark])
        self.assertNotIn(mark, self.canvas.mark_items)
        self.assertNotIn(11, self.canvas._marks_by_atom)
        self.assertIsNone(mark.scene())

    def test_ring_restore_and_removal_refresh_each_bond_geometry(self) -> None:
        ring = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(4.0, 0.0), QPointF(2.0, 3.0)])
        )
        ring.setData(0, "ring")
        ring.setData(2, [1, 2, 3])
        self.canvas.bond_lookup = {
            (1, 2): 101,
            (2, 3): 102,
            (3, 1): 103,
        }

        self.controller.restore_scene_item(ring)

        self.assertEqual(self.canvas.ring_items, [ring])
        self.assertIs(ring.scene(), self.canvas.scene())
        self.assertCountEqual(self.canvas.updated_bond_ids, [101, 102, 103])

        self.canvas.updated_bond_ids.clear()

        self.controller.remove_scene_item(ring)

        self.assertNotIn(ring, self.canvas.ring_items)
        self.assertIsNone(ring.scene())
        self.assertCountEqual(self.canvas.updated_bond_ids, [101, 102, 103])

    def test_remove_scene_item_clears_orbital_handle_target(self) -> None:
        orbital = QGraphicsItemGroup()
        orbital.setData(0, "orbital")
        self.canvas.scene().addItem(orbital)
        self.canvas.orbital_items.append(orbital)
        self.canvas._handle_target = orbital

        self.controller.remove_scene_item(orbital)

        self.assertEqual(self.canvas.clear_handles_calls, 1)
        self.assertNotIn(orbital, self.canvas.orbital_items)
        self.assertIsNone(orbital.scene())


if __name__ == "__main__":
    unittest.main()
