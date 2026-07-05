import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QRectF
    from PyQt6.QtWidgets import QApplication, QGraphicsItem
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.atom_coords_access import atom_coords_3d_for
    from ui.bond_graphics_access import project_point_3d_for
    from ui.canvas_rotation_state import rotation_state_for

    from tests.test_scene_ops_controller import (
        _FakeCanvas,
        _make_note_item,
        scene_clipboard_controller_for,
    )


class _RecordingFakeCanvas(_FakeCanvas):
    def __init__(self) -> None:
        super().__init__()
        self.atom_color_calls: list[tuple[int, str]] = []
        self.atom_label_calls: list[dict] = []
        self.select_note_calls: list[tuple[QGraphicsItem, bool]] = []
        self.translate_empty_kinds: set[str] = set()

    def apply_atom_color(self, atom_id: int, color: str) -> None:
        self.atom_color_calls.append((atom_id, color))
        super().apply_atom_color(atom_id, color)

    def add_or_update_atom_label(
        self,
        atom_id: int,
        element: str,
        clear_smiles: bool = False,
        record: bool = False,
        allow_merge: bool = False,
        show_carbon: bool = False,
    ) -> None:
        self.atom_label_calls.append(
            {
                "atom_id": atom_id,
                "element": element,
                "clear_smiles": clear_smiles,
                "record": record,
                "allow_merge": allow_merge,
                "show_carbon": show_carbon,
            }
        )
        super().add_or_update_atom_label(
            atom_id,
            element,
            clear_smiles=clear_smiles,
            record=record,
            allow_merge=allow_merge,
            show_carbon=show_carbon,
        )

    def select_note(self, item, additive: bool = True) -> None:
        self.select_note_calls.append((item, additive))
        super().select_note(item, additive=additive)

    def create_scene_item_from_state(self, state: dict):
        if isinstance(state, dict) and state.get("kind") in self.translate_empty_kinds:
            return None
        return super().create_scene_item_from_state(state)


class _ZeroBoundsItem(QGraphicsItem):
    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(0.0, 0.0, 0.0, 0.0)

    def paint(self, painter, option, widget=None) -> None:  # type: ignore[override]
        return None


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene ops controller paste edge tests")
class SceneOpsControllerPasteEdgesTest(unittest.TestCase):
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

    def test_paste_selection_from_clipboard_rejects_missing_and_empty_payloads(self) -> None:
        canvas = _RecordingFakeCanvas()
        controller = scene_clipboard_controller_for(canvas)

        controller.clipboard_selection_payload = lambda: (None, None)
        self.assertFalse(controller.paste_selection_from_clipboard())

        controller.clipboard_selection_payload = lambda: (
            {
                "format": "chemvas-selection",
                "version": 1,
                "atoms": [],
                "bonds": [],
                "rings": [],
                "marks": [],
                "scene_items": [],
            },
            "payload-json",
        )
        self.assertFalse(controller.paste_selection_from_clipboard())

    def test_select_pasted_content_skips_missing_atoms_and_none_scene_items(self) -> None:
        canvas = _RecordingFakeCanvas()
        note_item = _make_note_item("note", 14.0, 16.0)
        canvas.add_item(note_item)
        controller = scene_clipboard_controller_for(canvas)

        controller.select_pasted_content({99}, [None, note_item])

        self.assertEqual(canvas.clear_note_selection_calls, 1)
        self.assertEqual(canvas.select_note_calls, [(note_item, True)])
        self.assertEqual(canvas.update_selection_outline_calls, 1)
        self.assertTrue(note_item.isSelected())

    def test_paste_selection_from_clipboard_keeps_paste_state_when_everything_is_dropped(self) -> None:
        canvas = _RecordingFakeCanvas()
        canvas.scene_clipboard_state.paste_source_json = "old-source"
        canvas.scene_clipboard_state.paste_count = 7
        canvas.translate_empty_kinds = {"skip"}
        controller = scene_clipboard_controller_for(canvas)
        payload = {
            "format": "chemvas-selection",
            "version": 1,
            "atoms": [
                "bad-atom",
                {"id": "bad"},
                {"id": 1, "element": "C", "x": "bad", "y": 2.0},
            ],
            "bonds": [
                "bad-bond",
                {"a": 1, "b": 2, "order": 1, "style": "single", "color": "#000000"},
            ],
            "rings": [],
            "marks": [],
            "scene_items": [
                {"kind": "skip", "x": 1.0, "y": 2.0},
            ],
        }
        controller.clipboard_selection_payload = lambda: (payload, "new-source")

        self.assertFalse(controller.paste_selection_from_clipboard())
        self.assertEqual(canvas.scene_clipboard_state.paste_source_json, "old-source")
        self.assertEqual(canvas.scene_clipboard_state.paste_count, 7)
        self.assertEqual(canvas.atom_color_calls, [])
        self.assertEqual(canvas.atom_label_calls, [])
        self.assertEqual(canvas.created_scene_item_states, [])
        self.assertEqual(canvas.record_additions_calls, [])

    def test_paste_selection_from_clipboard_applies_explicit_carbon_and_additive_note_selection(self) -> None:
        canvas = _RecordingFakeCanvas()
        canvas.translate_empty_kinds = {"skip"}
        controller = scene_clipboard_controller_for(canvas)
        payload = {
            "format": "chemvas-selection",
            "version": 1,
            "atoms": [
                {"id": 10, "element": "C", "x": 5.0, "y": 7.0, "color": "#123456", "explicit_label": True},
            ],
            "bonds": [
                {"a": 10, "b": 99, "order": 2, "style": "double", "color": "#abcdef"},
            ],
            "rings": [],
            "marks": [],
            "scene_items": [
                {"kind": "skip", "x": 1.0, "y": 2.0},
                {"kind": "note", "text": "copied", "x": 50.0, "y": 60.0},
            ],
        }
        controller.clipboard_selection_payload = lambda: (payload, "fresh-source")

        self.assertTrue(controller.paste_selection_from_clipboard())

        self.assertEqual(canvas.scene_clipboard_state.paste_source_json, "fresh-source")
        self.assertEqual(canvas.scene_clipboard_state.paste_count, 1)
        self.assertEqual(canvas.atom_color_calls, [(0, "#123456")])
        self.assertEqual(
            canvas.atom_label_calls,
            [
                {
                    "atom_id": 0,
                    "element": "C",
                    "clear_smiles": False,
                    "record": False,
                    "allow_merge": False,
                    "show_carbon": True,
                }
            ],
        )
        self.assertEqual(canvas.created_scene_item_states, [{"kind": "note", "text": "copied", "x": 68.0, "y": 78.0}])
        self.assertEqual(canvas.select_note_calls, [(canvas.created_items[0], True)])
        self.assertEqual(canvas.record_additions_calls, [(0, 0, None, canvas.created_items)])
        self.assertEqual(canvas.clear_note_selection_calls, 1)
        self.assertEqual(canvas.update_selection_outline_calls, 1)

    def test_paste_selection_from_clipboard_rolls_back_if_history_recording_raises(self) -> None:
        canvas = _RecordingFakeCanvas()
        canvas.scene_clipboard_state.paste_source_json = "old-source"
        canvas.scene_clipboard_state.paste_count = 3
        existing_note = _make_note_item("keep", 4.0, 6.0)
        canvas.add_item(existing_note, selected=True)
        canvas.selected_notes.append(existing_note)
        controller = scene_clipboard_controller_for(canvas)
        payload = {
            "format": "chemvas-selection",
            "version": 2,
            "atoms": [
                {"id": 10, "element": "C", "x": 5.0, "y": 7.0},
            ],
            "bonds": [],
            "rings": [],
            "marks": [],
            "scene_items": [
                {"kind": "note", "text": "copied", "x": 50.0, "y": 60.0},
            ],
            "perspective": {
                "atom_coords_3d": [{"atom_id": 10, "coords": [1.0, 2.0, 3.0]}],
                "projection_center_3d": [1.0, 2.0, 0.0],
                "projection_anchor_2d": [1.0, 2.0],
            },
        }
        controller.clipboard_selection_payload = lambda: (payload, "fresh-source")
        canvas.services.canvas_history_recording_service.record_additions = Mock(
            side_effect=RuntimeError("history failed")
        )

        with self.assertRaisesRegex(RuntimeError, "history failed"):
            controller.paste_selection_from_clipboard()

        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.model.bonds, [])
        self.assertEqual(atom_coords_3d_for(canvas), {})
        self.assertEqual(canvas.scene_clipboard_state.paste_source_json, "old-source")
        self.assertEqual(canvas.scene_clipboard_state.paste_count, 3)
        self.assertEqual(canvas.removed_scene_items, canvas.created_items)
        self.assertIsNone(canvas.created_items[0].scene())
        self.assertEqual(canvas.record_additions_calls, [])
        self.assertTrue(existing_note.isSelected())
        self.assertEqual(canvas.selected_notes, [existing_note])
        self.assertNotIn(canvas.created_items[0], canvas.selected_notes)

    def test_paste_selection_from_clipboard_remaps_perspective_state(self) -> None:
        canvas = _RecordingFakeCanvas()
        rotation = rotation_state_for(canvas)
        rotation.projection_center_3d = (100.0, 100.0, 0.0)
        rotation.projection_anchor_2d = (100.0, 100.0)
        controller = scene_clipboard_controller_for(canvas)
        payload = {
            "format": "chemvas-selection",
            "version": 2,
            "atoms": [
                {"id": 10, "element": "C", "x": 5.0, "y": 7.0},
                {"id": 11, "element": "N", "x": 25.0, "y": 7.0},
            ],
            "bonds": [{"a": 10, "b": 11, "order": 1, "style": "single", "color": "#000000"}],
            "rings": [],
            "marks": [],
            "scene_items": [],
            "perspective": {
                "atom_coords_3d": [
                    {"atom_id": 10, "coords": [1.0, 2.0, 3.0]},
                    {"atom_id": 11, "coords": [4.0, 5.0, 6.0]},
                ],
                "projection_center_3d": [7.0, 8.0, 9.0],
                "projection_anchor_2d": [10.0, 11.0],
            },
        }
        controller.clipboard_selection_payload = lambda: (payload, "perspective-source")

        self.assertTrue(controller.paste_selection_from_clipboard())

        coords_3d = atom_coords_3d_for(canvas)
        self.assertEqual(set(coords_3d), {0, 1})
        self.assertEqual(coords_3d[0][2], -6.0)
        self.assertEqual(coords_3d[1][2], -3.0)
        self.assertEqual(rotation.projection_center_3d, (100.0, 100.0, 0.0))
        self.assertEqual(rotation.projection_anchor_2d, (100.0, 100.0))
        for atom_id, coords in coords_3d.items():
            projected_x, projected_y = project_point_3d_for(canvas, coords)
            atom = canvas.model.atoms[atom_id]
            self.assertAlmostEqual(projected_x, atom.x)
            self.assertAlmostEqual(projected_y, atom.y)

    def test_copy_selection_to_clipboard_returns_false_for_invalid_bounds(self) -> None:
        canvas = _RecordingFakeCanvas()
        controller = scene_clipboard_controller_for(canvas)
        item = _ZeroBoundsItem()
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        item.setData(0, "note")
        item.setData(9, {"kind": "note", "text": "flat", "x": 0.0, "y": 0.0})
        canvas.add_item(item, selected=True)
        controller.selection_payload_for_clipboard = lambda: {
            "format": "chemvas-selection",
            "version": 1,
            "scene_items": [{"kind": "note", "text": "flat", "x": 0.0, "y": 0.0}],
        }

        self.assertFalse(controller.copy_selection_to_clipboard())
        self.assertIsNone(canvas.scene_clipboard_state.paste_source_json)
        self.assertEqual(canvas.scene_clipboard_state.paste_count, 0)

    def test_copy_selection_to_clipboard_resets_paste_source_when_copy_has_no_selection_data(self) -> None:
        canvas = _RecordingFakeCanvas()
        canvas.scene_clipboard_state.paste_source_json = "stale-source"
        canvas.scene_clipboard_state.paste_count = 4
        controller = scene_clipboard_controller_for(canvas)
        item = _make_note_item("copy", 12.0, 14.0)
        canvas.add_item(item, selected=True)
        controller.selection_payload_for_clipboard = lambda: None

        self.assertTrue(controller.copy_selection_to_clipboard())
        self.assertIsNone(canvas.scene_clipboard_state.paste_source_json)
        self.assertEqual(canvas.scene_clipboard_state.paste_count, 0)
        mime_data = QApplication.clipboard().mimeData()
        self.assertTrue(mime_data.hasImage())
        self.assertFalse(mime_data.hasFormat(canvas.CLIPBOARD_SELECTION_MIME))


if __name__ == "__main__":
    unittest.main()
