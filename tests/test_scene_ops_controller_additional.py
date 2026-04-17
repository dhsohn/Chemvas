import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.history import CompositeCommand
    from core.model import Atom
    from tests.test_scene_ops_controller import (
        SceneOpsController,
        _FakeCanvas,
        _make_note_item,
        _make_rect_item,
        _make_ring_item,
    )


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene ops controller tests")
class SceneOpsControllerAdditionalTest(unittest.TestCase):
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

    def test_selected_atom_components_cache_is_reused_until_graph_version_changes(self) -> None:
        canvas = _FakeCanvas()
        controller = SceneOpsController(canvas)
        calls: list[set[int]] = []

        def connected_components(atom_ids: set[int]) -> list[set[int]]:
            calls.append(set(atom_ids))
            return [{1, 2}]

        canvas._connected_components = connected_components
        canvas._graph_version = 4

        first = controller._selected_atom_components_for_transform({1, 2})
        second = controller._selected_atom_components_for_transform({1, 2})
        canvas._graph_version = 5
        third = controller._selected_atom_components_for_transform({1, 2})

        self.assertEqual(first, [{1, 2}])
        self.assertEqual(second, [{1, 2}])
        self.assertEqual(third, [{1, 2}])
        self.assertEqual(calls, [{1, 2}, {1, 2}])

    def test_flip_center_and_bounds_helpers_cover_atom_and_ring_paths(self) -> None:
        canvas = _FakeCanvas()
        canvas.model.atoms = {
            1: Atom("C", 0.0, 0.0),
            2: Atom("O", 20.0, 10.0),
        }
        controller = SceneOpsController(canvas)
        ring_item = _make_ring_item()
        bogus_item = _make_rect_item("mystery")

        self.assertEqual(controller._center_for_flip_group({1, 2}, []), QPointF(10.0, 5.0))
        self.assertEqual(controller._flip_center_for_selection(set(), [ring_item]), QPointF(6.0, 5.0))
        self.assertEqual(controller._flip_bounds_for_item(ring_item), QRectF(0.0, 0.0, 12.0, 10.0))
        self.assertIsNone(controller._flip_bounds_for_item(bogus_item))

    def test_flip_selected_items_updates_group_and_standalone_items(self) -> None:
        canvas = _FakeCanvas()
        atom_1_id = canvas.add_atom("C", 0.0, 0.0)
        atom_2_id = canvas.add_atom("O", 20.0, 0.0)

        atom_1_item = canvas._atom_item_for_id(atom_1_id)
        atom_2_item = canvas._atom_item_for_id(atom_2_id)
        assert atom_1_item is not None
        assert atom_2_item is not None
        atom_1_item.setSelected(True)
        atom_2_item.setSelected(True)

        mark_item = _make_rect_item(
            "mark",
            data1={"atom_id": atom_1_id},
            state={"kind": "mark", "atom_id": atom_1_id, "x": 2.0, "y": 3.0, "dx": 2.0, "dy": 3.0},
        )
        ring_item = _make_ring_item()
        ring_item.setData(2, [atom_1_id, atom_2_id])
        note_item = _make_note_item("flip me", 40.0, 10.0)
        arrow_item = _make_rect_item(
            "arrow",
            state={"kind": "arrow", "start": (30.0, 10.0), "end": (50.0, 10.0), "control": (40.0, 20.0)},
        )
        orbital_item = _make_rect_item(
            "orbital",
            state={"kind": "orbital", "center": (60.0, 15.0), "rotation": 15.0},
        )

        for item in (mark_item, ring_item, note_item, arrow_item, orbital_item):
            canvas.add_item(item, selected=True)
        canvas._marks_by_atom[atom_1_id] = [mark_item]

        controller = SceneOpsController(canvas)
        controller.flip_selected_items(horizontal=True)

        self.assertEqual(len(canvas.pushed_commands), 1)
        self.assertIsInstance(canvas.pushed_commands[0], CompositeCommand)
        self.assertEqual(canvas.update_selection_outline_calls, 1)
        self.assertEqual((canvas.model.atoms[atom_1_id].x, canvas.model.atoms[atom_1_id].y), (20.0, 0.0))
        self.assertEqual((canvas.model.atoms[atom_2_id].x, canvas.model.atoms[atom_2_id].y), (0.0, 0.0))
        self.assertEqual(mark_item.data(9)["x"], 18.0)
        self.assertEqual(mark_item.data(9)["dx"], -2.0)
        self.assertEqual(ring_item.data(9)["points"][0], (20.0, 0.0))
        self.assertEqual(arrow_item.data(9)["start"], (50.0, 10.0))
        self.assertEqual(arrow_item.data(9)["end"], (30.0, 10.0))
        self.assertEqual(arrow_item.data(9)["control"], (40.0, 20.0))
        self.assertEqual(orbital_item.data(9)["rotation"], 165.0)

    def test_copy_selection_to_clipboard_without_payload_hides_and_restores_overlapping_items(self) -> None:
        canvas = _FakeCanvas()
        canvas.devicePixelRatioF = lambda: 2.0
        selected_item = _make_rect_item("handle", rect=QRectF(0.0, 0.0, 10.0, 10.0))
        overlapping_item = _make_rect_item("note", rect=QRectF(2.0, 2.0, 8.0, 8.0))
        canvas.add_item(selected_item, selected=True)
        canvas.add_item(overlapping_item, selected=False)
        controller = SceneOpsController(canvas)

        self.assertTrue(controller.copy_selection_to_clipboard())

        clipboard = QApplication.clipboard().mimeData()
        self.assertTrue(clipboard.hasImage())
        self.assertFalse(clipboard.hasFormat(canvas.CLIPBOARD_SELECTION_MIME))
        self.assertIsNone(canvas._clipboard_selection_payload_json)
        self.assertIsNone(canvas._clipboard_paste_source_json)
        self.assertEqual(canvas._clipboard_paste_count, 0)
        self.assertTrue(overlapping_item.isVisible())

    def test_paste_selection_from_clipboard_repeats_source_and_skips_bad_entries(self) -> None:
        canvas = _FakeCanvas()
        canvas._clipboard_paste_source_json = "payload-json"
        canvas._clipboard_paste_count = 3
        controller = SceneOpsController(canvas)
        payload = {
            "format": "lightdraw-selection",
            "version": 1,
            "atoms": [
                "bad-atom",
                {"id": 1, "element": "C", "x": 5.0, "y": 10.0, "color": "#ff0000", "explicit_label": True},
            ],
            "bonds": [
                "bad-bond",
                {"a": 1, "b": 99, "order": 2, "style": "double", "color": "#123456"},
            ],
            "rings": [],
            "marks": [],
            "scene_items": [
                "bad-item",
                {"kind": "note", "text": "copied", "x": 50.0, "y": 60.0},
                {"kind": "skip", "x": 1.0, "y": 2.0},
            ],
        }
        original_create_scene_item_from_state = canvas.create_scene_item_from_state

        def create_scene_item_from_state(state: dict):
            if state.get("kind") == "skip":
                return None
            return original_create_scene_item_from_state(state)

        canvas.create_scene_item_from_state = create_scene_item_from_state
        controller._clipboard_selection_payload = lambda: (payload, "payload-json")

        self.assertTrue(controller.paste_selection_from_clipboard())

        self.assertEqual(canvas._clipboard_paste_source_json, "payload-json")
        self.assertEqual(canvas._clipboard_paste_count, 4)
        self.assertEqual(set(canvas.model.atoms), {0})
        self.assertEqual(canvas.model.atoms[0].color, "#ff0000")
        self.assertTrue(canvas.model.atoms[0].explicit_label)
        self.assertEqual(
            canvas.created_scene_item_states,
            [{"kind": "note", "text": "copied", "x": 122.0, "y": 132.0}],
        )
        self.assertEqual(canvas.record_additions_calls, [(0, 0, None, canvas.created_items)])
        self.assertEqual(canvas.clear_note_selection_calls, 1)
        self.assertEqual(canvas.update_selection_outline_calls, 1)
        self.assertTrue(canvas._atom_item_for_id(0).isSelected())
        self.assertEqual(len(canvas.selected_notes), 1)


if __name__ == "__main__":
    unittest.main()
