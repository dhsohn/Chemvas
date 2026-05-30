import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QRectF
    from PyQt6.QtWidgets import QApplication, QGraphicsItem
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from tests.test_scene_ops_controller import SceneOpsController, _FakeCanvas, _make_note_item


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

    def _translated_scene_item_state(
        self,
        state: dict,
        *,
        dx: float,
        dy: float,
        atom_id_map: dict[int, int],
    ) -> dict | None:
        if isinstance(state, dict) and state.get("kind") in self.translate_empty_kinds:
            return {}
        return super()._translated_scene_item_state(state, dx=dx, dy=dy, atom_id_map=atom_id_map)


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
        controller = SceneOpsController(canvas)

        controller._clipboard_selection_payload = lambda: (None, None)
        self.assertFalse(controller.paste_selection_from_clipboard())

        controller._clipboard_selection_payload = lambda: (
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
        controller = SceneOpsController(canvas)

        controller._select_pasted_content({99}, [None, note_item])

        self.assertEqual(canvas.clear_note_selection_calls, 1)
        self.assertEqual(canvas.select_note_calls, [(note_item, True)])
        self.assertEqual(canvas.update_selection_outline_calls, 1)
        self.assertTrue(note_item.isSelected())

    def test_paste_selection_from_clipboard_filters_invalid_entries_and_returns_false_when_everything_is_dropped(self) -> None:
        canvas = _RecordingFakeCanvas()
        canvas._clipboard_paste_source_json = "old-source"
        canvas._clipboard_paste_count = 7
        canvas.translate_empty_kinds = {"skip"}
        controller = SceneOpsController(canvas)
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
        controller._clipboard_selection_payload = lambda: (payload, "new-source")

        self.assertFalse(controller.paste_selection_from_clipboard())
        self.assertEqual(canvas._clipboard_paste_source_json, "new-source")
        self.assertEqual(canvas._clipboard_paste_count, 1)
        self.assertEqual(canvas.atom_color_calls, [])
        self.assertEqual(canvas.atom_label_calls, [])
        self.assertEqual(canvas.created_scene_item_states, [])
        self.assertEqual(canvas.record_additions_calls, [])

    def test_paste_selection_from_clipboard_applies_explicit_carbon_and_additive_note_selection(self) -> None:
        canvas = _RecordingFakeCanvas()
        canvas.translate_empty_kinds = {"skip"}
        controller = SceneOpsController(canvas)
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
        controller._clipboard_selection_payload = lambda: (payload, "fresh-source")

        self.assertTrue(controller.paste_selection_from_clipboard())

        self.assertEqual(canvas._clipboard_paste_source_json, "fresh-source")
        self.assertEqual(canvas._clipboard_paste_count, 1)
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

    def test_copy_selection_to_clipboard_returns_false_for_invalid_bounds(self) -> None:
        canvas = _RecordingFakeCanvas()
        controller = SceneOpsController(canvas)
        item = _ZeroBoundsItem()
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        item.setData(0, "note")
        item.setData(9, {"kind": "note", "text": "flat", "x": 0.0, "y": 0.0})
        canvas.add_item(item, selected=True)
        controller._selection_payload_for_clipboard = lambda: {
            "format": "chemvas-selection",
            "version": 1,
            "scene_items": [{"kind": "note", "text": "flat", "x": 0.0, "y": 0.0}],
        }

        self.assertFalse(controller.copy_selection_to_clipboard())
        self.assertIsNone(canvas._clipboard_paste_source_json)
        self.assertEqual(canvas._clipboard_paste_count, 0)

    def test_copy_selection_to_clipboard_resets_paste_source_when_copy_has_no_selection_data(self) -> None:
        canvas = _RecordingFakeCanvas()
        canvas._clipboard_paste_source_json = "stale-source"
        canvas._clipboard_paste_count = 4
        controller = SceneOpsController(canvas)
        item = _make_note_item("copy", 12.0, 14.0)
        canvas.add_item(item, selected=True)
        controller._selection_payload_for_clipboard = lambda: None

        self.assertTrue(controller.copy_selection_to_clipboard())
        self.assertIsNone(canvas._clipboard_paste_source_json)
        self.assertEqual(canvas._clipboard_paste_count, 0)
        mime_data = QApplication.clipboard().mimeData()
        self.assertTrue(mime_data.hasImage())
        self.assertFalse(mime_data.hasFormat(canvas.CLIPBOARD_SELECTION_MIME))


if __name__ == "__main__":
    unittest.main()
