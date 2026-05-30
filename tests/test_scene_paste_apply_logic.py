import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from tests.test_scene_ops_controller_paste_edges import _RecordingFakeCanvas

    try:
        from ui.scene_paste_apply_logic import apply_paste_payload
    except ImportError as exc:  # pragma: no cover - contract test for upcoming helper API
        apply_paste_payload = None
        IMPORT_ERROR = str(exc)
    else:  # pragma: no cover - trivial import branch
        IMPORT_ERROR = ""
else:
    apply_paste_payload = None
    IMPORT_ERROR = ""


class _RecordingPasteCanvas(_RecordingFakeCanvas):
    def __init__(self) -> None:
        super().__init__()
        self.add_atom_calls: list[tuple[str, float, float]] = []
        self.add_bond_calls: list[tuple[int, int, int]] = []
        self.translate_none_kinds: set[str] = set()
        self.translate_empty_kinds: set[str] = set()
        self.translate_calls: list[tuple[str | None, float, float, dict[int, int]]] = []

    def add_atom(self, element: str, x: float, y: float) -> int:
        self.add_atom_calls.append((element, x, y))
        return super().add_atom(element, x, y)

    def add_bond(self, atom_a: int, atom_b: int, order: int) -> int:
        self.add_bond_calls.append((atom_a, atom_b, order))
        return super().add_bond(atom_a, atom_b, order)

    def _translated_scene_item_state(
        self,
        state: dict,
        *,
        dx: float,
        dy: float,
        atom_id_map: dict[int, int],
    ) -> dict | None:
        kind = state.get("kind") if isinstance(state, dict) else None
        self.translate_calls.append((kind, dx, dy, dict(atom_id_map)))
        if isinstance(state, dict) and kind in self.translate_none_kinds:
            return None
        if isinstance(state, dict) and kind in self.translate_empty_kinds:
            return {}
        return super()._translated_scene_item_state(state, dx=dx, dy=dy, atom_id_map=atom_id_map)


@unittest.skipIf(
    QApplication is None or apply_paste_payload is None,
    f"PyQt6 or the paste apply helper is unavailable: {IMPORT_ERROR}",
)
class ScenePasteApplyLogicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_apply_paste_selection_routes_valid_atoms_bonds_and_translated_scene_items(self) -> None:
        canvas = _RecordingPasteCanvas()
        canvas.translate_none_kinds = {"skip-none"}
        canvas.translate_empty_kinds = {"skip-empty"}
        payload = {
            "format": "chemvas-selection",
            "version": 1,
            "atoms": [
                "bad",
                {"id": "bad", "element": "C", "x": 1.0, "y": 2.0},
                {"id": 10, "element": "C", "x": 5.0, "y": 7.0, "color": "#123456", "explicit_label": True},
                {"id": 11, "element": "O", "x": 15.0, "y": 17.0, "color": "#abcdef", "explicit_label": True},
                {"id": 12, "element": "C", "x": 21.0, "y": 22.0, "color": "#fedcba", "explicit_label": False},
            ],
            "bonds": [
                "bad-bond",
                {"a": 10, "b": 11, "order": 2, "style": "double", "color": "#999999"},
                {"a": 10, "b": "11", "order": 1, "style": "single", "color": "#000000"},
                {"a": 10, "b": 99, "order": 1, "style": "single", "color": "#000000"},
            ],
            "rings": [
                {"kind": "ring", "atom_ids": [10, 11], "points": [(0.0, 0.0), (12.0, 0.0), (6.0, 10.0)]},
                {"kind": "skip-none", "atom_ids": [10, 11], "points": [(1.0, 1.0), (2.0, 1.0), (1.5, 2.0)]},
            ],
            "marks": [
                {"kind": "mark", "atom_id": 10, "x": 1.0, "y": 2.0},
                {"kind": "skip-empty", "atom_id": 10, "x": 9.0, "y": 9.0},
            ],
            "scene_items": [
                {"kind": "note", "text": "keep", "x": 30.0, "y": 40.0},
                {"kind": "skip-none", "x": 1.0, "y": 2.0},
                {"kind": "skip-empty", "x": 3.0, "y": 4.0},
            ],
        }

        result = apply_paste_payload(
            atoms=payload["atoms"],
            bonds=payload["bonds"],
            rings=payload["rings"],
            marks=payload["marks"],
            scene_items=payload["scene_items"],
            dx=18.0,
            dy=22.0,
            add_atom=canvas.add_atom,
            apply_atom_color=canvas.apply_atom_color,
            add_or_update_atom_label=canvas.add_or_update_atom_label,
            add_bond=canvas.add_bond,
            restore_bond_from_state=canvas._restore_bond_from_state,
            translated_scene_item_state=canvas._translated_scene_item_state,
            create_scene_item_from_state=canvas.create_scene_item_from_state,
        )

        self.assertTrue(result.has_changes())
        self.assertEqual(
            canvas.add_atom_calls,
            [
                ("C", 23.0, 29.0),
                ("O", 33.0, 39.0),
                ("C", 39.0, 44.0),
            ],
        )
        self.assertEqual(
            canvas.atom_color_calls,
            [
                (0, "#123456"),
                (1, "#abcdef"),
                (2, "#fedcba"),
            ],
        )
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
        self.assertEqual(canvas.add_bond_calls, [(0, 1, 2)])
        self.assertEqual(
            canvas.restore_bond_calls,
            [
                (
                    0,
                    {
                        "a": 0,
                        "b": 1,
                        "order": 2,
                        "style": "double",
                        "color": "#999999",
                    },
                )
            ],
        )
        self.assertEqual(result.atom_id_map, {10: 0, 11: 1, 12: 2})
        self.assertEqual(result.new_atom_ids, {0, 1, 2})
        self.assertEqual(len(result.added_scene_items), 3)
        self.assertEqual(
            canvas.created_scene_item_states,
            [
                {"kind": "ring", "atom_ids": [10, 11], "points": [(0.0, 0.0), (12.0, 0.0), (6.0, 10.0)]},
                {"kind": "mark", "atom_id": 0, "x": 19.0, "y": 24.0},
                {"kind": "note", "text": "keep", "x": 48.0, "y": 62.0},
            ],
        )
        self.assertEqual(
            canvas.translate_calls,
            [
                ("ring", 18.0, 22.0, {10: 0, 11: 1, 12: 2}),
                ("skip-none", 18.0, 22.0, {10: 0, 11: 1, 12: 2}),
                ("mark", 18.0, 22.0, {10: 0, 11: 1, 12: 2}),
                ("skip-empty", 18.0, 22.0, {10: 0, 11: 1, 12: 2}),
                ("note", 18.0, 22.0, {10: 0, 11: 1, 12: 2}),
                ("skip-none", 18.0, 22.0, {10: 0, 11: 1, 12: 2}),
                ("skip-empty", 18.0, 22.0, {10: 0, 11: 1, 12: 2}),
            ],
        )

    def test_apply_paste_selection_returns_false_when_nothing_is_created(self) -> None:
        canvas = _RecordingPasteCanvas()
        canvas.translate_none_kinds = {"skip-none"}
        canvas.translate_empty_kinds = {"skip-empty"}
        payload = {
            "format": "chemvas-selection",
            "version": 1,
            "atoms": [
                "bad",
                {"id": "bad", "element": "C", "x": 1.0, "y": 2.0},
                {"id": 99, "element": "C", "x": "bad", "y": 3.0},
            ],
            "bonds": [
                {"a": 99, "b": 100, "order": 1, "style": "single", "color": "#000000"},
            ],
            "rings": [
                {"kind": "skip-none", "atom_ids": [99, 100], "points": [(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)]},
            ],
            "marks": [
                {"kind": "skip-empty", "atom_id": 99, "x": 1.0, "y": 2.0},
            ],
            "scene_items": [
                {"kind": "skip-none", "x": 3.0, "y": 4.0},
                {"kind": "skip-empty", "x": 5.0, "y": 6.0},
            ],
        }

        result = apply_paste_payload(
            atoms=payload["atoms"],
            bonds=payload["bonds"],
            rings=payload["rings"],
            marks=payload["marks"],
            scene_items=payload["scene_items"],
            dx=18.0,
            dy=22.0,
            add_atom=canvas.add_atom,
            apply_atom_color=canvas.apply_atom_color,
            add_or_update_atom_label=canvas.add_or_update_atom_label,
            add_bond=canvas.add_bond,
            restore_bond_from_state=canvas._restore_bond_from_state,
            translated_scene_item_state=canvas._translated_scene_item_state,
            create_scene_item_from_state=canvas.create_scene_item_from_state,
        )

        self.assertFalse(result.has_changes())
        self.assertEqual(result.atom_id_map, {})
        self.assertEqual(result.new_atom_ids, set())
        self.assertEqual(result.added_scene_items, [])
        self.assertEqual(canvas.add_atom_calls, [])
        self.assertEqual(canvas.atom_color_calls, [])
        self.assertEqual(canvas.atom_label_calls, [])
        self.assertEqual(canvas.add_bond_calls, [])
        self.assertEqual(canvas.restore_bond_calls, [])
        self.assertEqual(canvas.created_scene_item_states, [])


if __name__ == "__main__":
    unittest.main()
