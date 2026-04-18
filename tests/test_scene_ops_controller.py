import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import QImage, QPolygonF
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsItem,
        QGraphicsPolygonItem,
        QGraphicsRectItem,
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
    from core.history import (
        CompositeCommand,
        DeleteAtomsCommand,
        DeleteBondCommand,
        DeleteSceneItemsCommand,
    )
    from core.model import Atom, Bond, MoleculeModel
    from ui.scene_clipboard_transaction_logic import build_clipboard_copy_plan
    from ui.scene_ops_controller import SceneOpsController


def _set_selectable(item: QGraphicsItem) -> QGraphicsItem:
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    return item


def _make_rect_item(
    kind: str,
    *,
    data1=None,
    state: dict | None = None,
    rect: QRectF | None = None,
) -> QGraphicsRectItem:
    item = _set_selectable(QGraphicsRectItem(rect or QRectF(0.0, 0.0, 10.0, 10.0)))
    item.setData(0, kind)
    if data1 is not None:
        item.setData(1, data1)
    if state is not None:
        item.setData(9, dict(state))
    return item


def _make_note_item(text: str, x: float, y: float) -> QGraphicsTextItem:
    item = _set_selectable(QGraphicsTextItem(text))
    item.setData(0, "note")
    item.setData(9, {"kind": "note", "text": text, "x": x, "y": y})
    item.setPos(x, y)
    return item


def _make_ring_item() -> QGraphicsPolygonItem:
    polygon = QPolygonF([QPointF(0.0, 0.0), QPointF(12.0, 0.0), QPointF(6.0, 10.0)])
    item = _set_selectable(QGraphicsPolygonItem(polygon))
    item.setData(0, "ring")
    item.setData(9, {"kind": "ring", "points": [(0.0, 0.0), (12.0, 0.0), (6.0, 10.0)]})
    return item


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene ops controller tests")
class SceneOpsControllerTest(unittest.TestCase):
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

    def test_delete_selected_items_returns_false_without_selection(self) -> None:
        canvas = _FakeCanvas()
        controller = SceneOpsController(canvas)

        self.assertFalse(controller.delete_selected_items())
        self.assertEqual(canvas.pushed_commands, [])

    def test_delete_selected_items_uses_single_bond_fast_path(self) -> None:
        canvas = _FakeCanvas()
        canvas.model.atoms = {
            1: Atom("C", 0.0, 0.0),
            2: Atom("O", 30.0, 0.0),
        }
        canvas.model.bonds = [Bond(1, 2, 1)]
        bond_item = _make_rect_item("bond", data1=0)
        canvas.add_item(bond_item, selected=True)

        controller = SceneOpsController(canvas)

        self.assertTrue(controller.delete_selected_items())
        self.assertEqual(canvas.delete_bond_calls, [])
        self.assertEqual(len(canvas.pushed_commands), 1)
        self.assertIsInstance(canvas.pushed_commands[0], DeleteBondCommand)
        self.assertEqual(canvas.remove_bond_calls, [0])
        self.assertEqual(sorted(canvas.redraw_connected_bonds_calls), [1, 2])

    def test_delete_selected_items_builds_composite_commands_for_mixed_selection(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("O", 20.0, 0.0),
            },
            bonds=[Bond(1, 2, 2)],
            next_atom_id=3,
        )
        atom_item = _make_rect_item("atom", data1=1)
        bond_item = _make_rect_item("bond", data1=0)
        ring_item = _make_ring_item()
        note_item = _make_note_item("Mechanism", 40.0, 10.0)
        linked_mark = _make_rect_item(
            "mark",
            data1={"atom_id": 1},
            state={"kind": "mark", "atom_id": 1, "x": 4.0, "y": -5.0},
        )
        sibling_mark = _make_rect_item(
            "mark",
            data1={"atom_id": 1},
            state={"kind": "mark", "atom_id": 1, "x": -2.0, "y": 7.0},
        )
        free_mark = _make_rect_item(
            "mark",
            data1={"atom_id": None},
            state={"kind": "mark", "atom_id": None, "x": 80.0, "y": 5.0},
        )
        arrow_item = _make_rect_item(
            "arrow",
            state={"kind": "arrow", "start": (0.0, 0.0), "end": (10.0, 5.0)},
        )
        ts_bracket_item = _make_rect_item(
            "ts_bracket",
            state={"kind": "ts_bracket", "left": 1.0, "top": 2.0, "right": 3.0, "bottom": 4.0},
        )
        orbital_item = _make_rect_item(
            "orbital",
            state={"kind": "orbital", "center": (12.0, 9.0), "rotation": 15.0},
        )
        other_item = _make_rect_item("weird", state={"kind": "weird", "value": 1})
        handle_item = _make_rect_item("handle", state={"kind": "handle"})

        for item in (
            atom_item,
            bond_item,
            ring_item,
            note_item,
            linked_mark,
            free_mark,
            arrow_item,
            ts_bracket_item,
            orbital_item,
            other_item,
            handle_item,
        ):
            canvas.add_item(item, selected=True)
        canvas.add_item(sibling_mark, selected=False)
        canvas._marks_by_atom[1] = [linked_mark, sibling_mark]

        controller = SceneOpsController(canvas)

        self.assertTrue(controller.delete_selected_items())
        self.assertEqual(len(canvas.pushed_commands), 1)
        command = canvas.pushed_commands[0]
        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual(canvas.clear_handles_calls, 1)
        self.assertEqual(canvas.last_smiles_input, None)
        self.assertEqual(canvas.remove_bond_calls, [0])
        self.assertEqual(sorted(canvas.redraw_connected_bonds_calls), [1, 2])
        self.assertEqual(canvas.remove_atom_calls, [(1, True)])

        delete_bond_commands = [child for child in command.commands if isinstance(child, DeleteBondCommand)]
        self.assertEqual(len(delete_bond_commands), 1)
        self.assertEqual(delete_bond_commands[0].bond_id, 0)
        self.assertEqual(delete_bond_commands[0].bond_state["order"], 2)

        delete_atom_commands = [child for child in command.commands if isinstance(child, DeleteAtomsCommand)]
        self.assertEqual(len(delete_atom_commands), 1)
        atom_delete = delete_atom_commands[0]
        self.assertEqual(set(atom_delete.atom_states), {1})
        self.assertEqual(
            atom_delete.mark_states,
            [
                {"kind": "mark", "atom_id": 1, "x": 4.0, "y": -5.0},
                {"kind": "mark", "atom_id": 1, "x": -2.0, "y": 7.0},
            ],
        )

        delete_scene_item_commands = [child for child in command.commands if isinstance(child, DeleteSceneItemsCommand)]
        self.assertEqual(len(delete_scene_item_commands), 1)
        scene_delete = delete_scene_item_commands[0]
        deleted_kinds = [state["kind"] for state in scene_delete.item_states]
        self.assertEqual(
            deleted_kinds,
            ["ring", "note", "mark", "arrow", "ts_bracket", "orbital", "weird"],
        )
        self.assertNotIn(linked_mark, scene_delete.items)
        self.assertIn(free_mark, scene_delete.items)
        self.assertNotIn(handle_item, scene_delete.items)

    def test_delete_selected_items_pushes_single_scene_item_command(self) -> None:
        canvas = _FakeCanvas()
        note_item = _make_note_item("Solo", 12.0, 14.0)
        canvas.add_item(note_item, selected=True)
        controller = SceneOpsController(canvas)

        self.assertTrue(controller.delete_selected_items())
        self.assertEqual(len(canvas.pushed_commands), 1)
        self.assertIsInstance(canvas.pushed_commands[0], DeleteSceneItemsCommand)
        self.assertEqual(canvas.removed_scene_items, [note_item])
        self.assertEqual(canvas.clear_handles_calls, 0)

    def test_delete_ring_prefers_scene_item_controller_when_available(self) -> None:
        canvas = _FakeCanvas()
        ring_item = _make_ring_item()
        controller_removed_items: list[object] = []
        canvas._ring_state_dict = lambda item: {"kind": "ring", "points": [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]}
        canvas._scene_item_controller = SimpleNamespace(remove_scene_item=controller_removed_items.append)
        controller = SceneOpsController(canvas)

        command = controller.delete_ring(ring_item, record=False)

        self.assertIsInstance(command, DeleteSceneItemsCommand)
        self.assertEqual(controller_removed_items, [ring_item])
        self.assertEqual(canvas.removed_scene_items, [])

    def test_clipboard_selection_payload_rejects_wrong_type_and_version(self) -> None:
        canvas = _FakeCanvas()
        controller = SceneOpsController(canvas)
        clipboard = QApplication.clipboard()

        for raw_payload in (
            b'{"format":"not-lightdraw-selection","version":1}',
            b'{"format":"lightdraw-selection","version":999}',
        ):
            mime_data = canvas.new_mime_data(raw_payload)
            clipboard.setMimeData(mime_data)
            payload, payload_json = controller._clipboard_selection_payload()
            self.assertIsNone(payload)
            self.assertIsNone(payload_json)

    def test_clipboard_selection_payload_uses_image_only_fallback_json(self) -> None:
        canvas = _FakeCanvas()
        controller = SceneOpsController(canvas)
        clipboard = QApplication.clipboard()
        payload_json = '{"format":"lightdraw-selection","version":1,"scene_items":[{"kind":"note"}]}'
        canvas._clipboard_selection_payload_json = payload_json
        mime_data = QImage(4, 4, QImage.Format.Format_ARGB32)
        image_mime = canvas.new_image_mime_data(mime_data)
        clipboard.setMimeData(image_mime)

        payload, returned_json = controller._clipboard_selection_payload()

        self.assertEqual(payload, {"format": "lightdraw-selection", "version": 1, "scene_items": [{"kind": "note"}]})
        self.assertEqual(returned_json, payload_json)

    def test_selection_payload_for_clipboard_includes_linked_items(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0, color="#111111", explicit_label=True),
                2: Atom("O", 20.0, 0.0, color="#222222"),
            },
            bonds=[Bond(1, 2, 2, style="double", color="#333333")],
        )
        atom_item = _make_rect_item("atom", data1=1, state={"kind": "atom"})
        bond_item = _make_rect_item("bond", data1=0, state={"kind": "bond"})
        note_item = _make_note_item("payload", 30.0, 40.0)
        free_mark = _make_rect_item(
            "mark",
            data1={"atom_id": None},
            state={"kind": "mark", "atom_id": None, "x": 50.0, "y": 60.0},
        )
        linked_mark = _make_rect_item(
            "mark",
            data1={"atom_id": 1},
            state={"kind": "mark", "atom_id": 1, "x": 2.0, "y": 3.0},
        )
        ring_item = _make_ring_item()
        ring_item.setData(2, [1, 2])
        canvas.ring_items.append(ring_item)
        canvas._marks_by_atom[1] = [linked_mark]
        for item in (atom_item, bond_item, note_item, free_mark, linked_mark):
            canvas.add_item(item, selected=True)
        canvas.add_item(ring_item, selected=False)
        controller = SceneOpsController(canvas)

        payload = controller._selection_payload_for_clipboard()

        assert payload is not None
        self.assertEqual(payload["format"], "lightdraw-selection")
        self.assertEqual(payload["version"], 1)
        self.assertEqual([atom["id"] for atom in payload["atoms"]], [1, 2])
        self.assertEqual(payload["bonds"], [{"a": 1, "b": 2, "order": 2, "style": "double", "color": "#333333"}])
        self.assertEqual(payload["rings"], [{"kind": "ring", "points": [(0.0, 0.0), (12.0, 0.0), (6.0, 10.0)]}])
        self.assertEqual(
            payload["marks"],
            [
                {"kind": "mark", "atom_id": 1, "x": 2.0, "y": 3.0},
                {"kind": "mark", "atom_id": None, "x": 50.0, "y": 60.0},
            ],
        )
        self.assertEqual(payload["scene_items"], [{"kind": "note", "text": "payload", "x": 30.0, "y": 40.0}])

    def test_selection_payload_for_clipboard_returns_none_for_empty_selection(self) -> None:
        canvas = _FakeCanvas()
        controller = SceneOpsController(canvas)

        self.assertIsNone(controller._selection_payload_for_clipboard())

    def test_clipboard_copy_plan_uses_union_of_valid_rects(self) -> None:
        first = _make_rect_item("note", rect=QRectF(0.0, 0.0, 10.0, 10.0))
        invalid = _make_rect_item("note", rect=QRectF())
        second = _make_rect_item("note", rect=QRectF(20.0, 10.0, 5.0, 5.0))

        plan = build_clipboard_copy_plan(
            [first, invalid, second],
            payload=None,
            bond_line_width=0.5,
            device_pixel_ratio=1.0,
        )

        assert plan is not None
        self.assertEqual(plan.source, QRectF(-2.5, -2.5, 30.0, 20.0))

    def test_copy_selection_to_clipboard_handles_empty_and_successful_copy(self) -> None:
        canvas = _FakeCanvas()
        controller = SceneOpsController(canvas)

        self.assertFalse(controller.copy_selection_to_clipboard())

        note_item = _make_note_item("copy", 10.0, 12.0)
        canvas.add_item(note_item, selected=True)
        self.assertTrue(controller.copy_selection_to_clipboard())
        self.assertIsNotNone(canvas._clipboard_selection_payload_json)
        self.assertEqual(canvas._clipboard_paste_count, 0)
        mime_data = QApplication.clipboard().mimeData()
        self.assertTrue(mime_data.hasImage())
        self.assertTrue(mime_data.hasFormat(canvas.CLIPBOARD_SELECTION_MIME))

    def test_paste_selection_remaps_atom_ids_and_restores_selection(self) -> None:
        canvas = _FakeCanvas()
        controller = SceneOpsController(canvas)

        stale_item = _make_rect_item("stale")
        canvas.add_item(stale_item, selected=True)

        payload = {
            "format": "lightdraw-selection",
            "version": 1,
            "atoms": [
                {"id": 10, "element": "C", "x": 5.0, "y": 10.0, "color": "#ff0000", "explicit_label": True},
                {"id": 11, "element": "O", "x": 25.0, "y": 30.0, "color": "#00ff00"},
            ],
            "bonds": [
                {"a": 10, "b": 11, "order": 2, "style": "double", "color": "#123456"},
            ],
            "rings": [],
            "marks": [
                {"kind": "mark", "atom_id": 10, "x": 8.0, "y": 12.0},
            ],
            "scene_items": [
                {"kind": "note", "text": "copied", "x": 50.0, "y": 60.0},
            ],
        }
        controller._clipboard_selection_payload = lambda: (payload, "payload-json")

        self.assertTrue(controller.paste_selection_from_clipboard())

        self.assertEqual(canvas._clipboard_paste_source_json, "payload-json")
        self.assertEqual(canvas._clipboard_paste_count, 1)
        self.assertEqual(set(canvas.model.atoms), {0, 1})
        self.assertEqual(canvas.model.atoms[0].color, "#ff0000")
        self.assertTrue(canvas.model.atoms[0].explicit_label)
        self.assertEqual(canvas.model.atoms[1].color, "#00ff00")
        self.assertEqual(len(canvas.model.bonds), 1)
        self.assertEqual((canvas.model.bonds[0].a, canvas.model.bonds[0].b), (0, 1))
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
                        "color": "#123456",
                    },
                )
            ],
        )
        self.assertEqual(
            canvas.created_scene_item_states,
            [
                {"kind": "mark", "atom_id": 0, "x": 26.0, "y": 30.0},
                {"kind": "note", "text": "copied", "x": 68.0, "y": 78.0},
            ],
        )
        self.assertFalse(stale_item.isSelected())
        self.assertTrue(canvas._atom_item_for_id(0).isSelected())
        self.assertTrue(canvas._atom_item_for_id(1).isSelected())
        self.assertTrue(canvas.created_items[0].isSelected())
        self.assertTrue(canvas.created_items[1].isSelected())
        self.assertEqual(canvas.selected_notes, [canvas.created_items[1]])
        self.assertEqual(canvas.clear_note_selection_calls, 1)
        self.assertEqual(canvas.update_selection_outline_calls, 1)
        self.assertEqual(
            canvas.record_additions_calls,
            [
                (0, 0, None, canvas.created_items),
            ],
        )

    def test_paste_selection_from_clipboard_rejects_missing_or_empty_payload(self) -> None:
        canvas = _FakeCanvas()
        controller = SceneOpsController(canvas)

        controller._clipboard_selection_payload = lambda: (None, None)
        self.assertFalse(controller.paste_selection_from_clipboard())

        controller._clipboard_selection_payload = lambda: (
            {"format": "lightdraw-selection", "version": 1, "atoms": [], "bonds": [], "rings": [], "marks": [], "scene_items": []},
            "payload-json",
        )
        self.assertFalse(controller.paste_selection_from_clipboard())

    def test_paste_selection_from_clipboard_accepts_scene_item_only_payload_and_resets_source(self) -> None:
        canvas = _FakeCanvas()
        canvas._clipboard_paste_source_json = "old-source"
        canvas._clipboard_paste_count = 5
        controller = SceneOpsController(canvas)
        payload = {
            "format": "lightdraw-selection",
            "version": 1,
            "atoms": [{"id": "bad"}],
            "bonds": [{"a": 1, "b": "bad"}],
            "rings": [],
            "marks": [],
            "scene_items": [{"kind": "note", "text": "solo", "x": 10.0, "y": 15.0}],
        }
        controller._clipboard_selection_payload = lambda: (payload, "new-source")

        self.assertTrue(controller.paste_selection_from_clipboard())
        self.assertEqual(canvas._clipboard_paste_source_json, "new-source")
        self.assertEqual(canvas._clipboard_paste_count, 1)
        self.assertEqual(canvas.created_scene_item_states, [{"kind": "note", "text": "solo", "x": 28.0, "y": 33.0}])
        self.assertEqual(canvas.record_additions_calls, [(0, 0, None, canvas.created_items)])

    def test_flip_selected_items_noop_paths(self) -> None:
        canvas = _FakeCanvas()
        controller = SceneOpsController(canvas)

        controller.flip_selected_items(horizontal=True)

        self.assertEqual(canvas.pushed_commands, [])


class _FakeCanvas:
    CLIPBOARD_SELECTION_MIME = "application/x-lightdraw-selection+json"
    CLIPBOARD_SELECTION_VERSION = 1

    def __init__(self) -> None:
        self._scene = QGraphicsScene()
        self.model = MoleculeModel()
        self.renderer = SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0, bond_line_width=1.0))
        self.last_smiles_input = None
        self._marks_by_atom: dict[int, list[QGraphicsItem]] = {}
        self.ring_items: list[QGraphicsItem] = []
        self._clipboard_selection_payload_json = None
        self._clipboard_paste_source_json = None
        self._clipboard_paste_count = 0
        self._clipboard_payload = None
        self._graph_version = 0
        self._selection_component_cache_signature = None
        self._selection_component_cache: list[set[int]] = []
        self.delete_bond_calls: list[tuple[int, bool]] = []
        self.remove_bond_calls: list[int] = []
        self.redraw_connected_bonds_calls: list[int] = []
        self.remove_atom_calls: list[tuple[int, bool]] = []
        self.removed_scene_items: list[QGraphicsItem] = []
        self.pushed_commands: list[object] = []
        self.clear_handles_calls = 0
        self.atom_items: dict[int, QGraphicsItem] = {}
        self.created_scene_item_states: list[dict] = []
        self.created_items: list[QGraphicsItem] = []
        self.restore_bond_calls: list[tuple[int, dict]] = []
        self.selected_notes: list[QGraphicsTextItem] = []
        self.clear_note_selection_calls = 0
        self.update_selection_outline_calls = 0
        self.record_additions_calls: list[tuple[int, int, str | None, list[QGraphicsItem]]] = []

    def scene(self) -> QGraphicsScene:
        return self._scene

    def add_item(self, item: QGraphicsItem, *, selected: bool = False) -> None:
        self._scene.addItem(item)
        if selected:
            item.setSelected(True)

    def delete_bond(self, bond_id: int, record: bool = True) -> None:
        self.delete_bond_calls.append((bond_id, record))
        if 0 <= bond_id < len(self.model.bonds):
            self.model.bonds[bond_id] = None

    def _bond_state_dict(self, bond: Bond) -> dict:
        return {
            "a": bond.a,
            "b": bond.b,
            "order": bond.order,
            "style": bond.style,
            "color": bond.color,
        }

    def _remove_bond_by_id(self, bond_id: int) -> None:
        self.remove_bond_calls.append(bond_id)
        self.model.bonds[bond_id] = None

    def _redraw_connected_bonds(self, atom_id: int) -> None:
        self.redraw_connected_bonds_calls.append(atom_id)

    def _mark_state_dict(self, mark: QGraphicsItem) -> dict:
        return self.scene_item_state(mark)

    def _atom_state_dict(self, atom_id: int) -> dict:
        atom = self.model.atoms[atom_id]
        return {
            "element": atom.element,
            "x": atom.x,
            "y": atom.y,
            "color": atom.color,
            "explicit_label": atom.explicit_label,
        }

    def _remove_atom_only(self, atom_id: int, remove_marks: bool = True) -> None:
        self.remove_atom_calls.append((atom_id, remove_marks))
        self.model.atoms.pop(atom_id, None)

    def scene_item_state(self, item: QGraphicsItem) -> dict:
        state = item.data(9)
        return dict(state) if isinstance(state, dict) else {}

    def remove_scene_item(self, item: QGraphicsItem) -> None:
        self.removed_scene_items.append(item)
        self._scene.removeItem(item)

    def clear_handles(self) -> None:
        self.clear_handles_calls += 1

    def _push_command(self, command) -> None:
        self.pushed_commands.append(command)

    def new_mime_data(self, payload: bytes):
        from PyQt6.QtCore import QMimeData

        mime_data = QMimeData()
        mime_data.setData(self.CLIPBOARD_SELECTION_MIME, payload)
        return mime_data

    @staticmethod
    def new_image_mime_data(image: QImage):
        from PyQt6.QtCore import QMimeData

        mime_data = QMimeData()
        mime_data.setImageData(image)
        return mime_data

    def _clipboard_selection_payload(self):
        return self._clipboard_payload

    def _selected_items_for_transform(self):
        return list(self._scene.selectedItems())

    def _selection_items_for_copy(self):
        return list(self._scene.selectedItems())

    def _selected_ids(self) -> tuple[set[int], set[int]]:
        atom_ids: set[int] = set()
        bond_ids: set[int] = set()
        for item in self._scene.selectedItems():
            kind = item.data(0)
            data = item.data(1)
            if kind == "atom" and isinstance(data, int):
                atom_ids.add(data)
            elif kind == "bond" and isinstance(data, int):
                bond_ids.add(data)
        return atom_ids, bond_ids

    def _selected_atom_ids_for_transform(self) -> set[int]:
        atom_ids, _ = self._selected_ids()
        return atom_ids

    def _connected_components(self, atom_ids: set[int]) -> list[set[int]]:
        return [set(atom_ids)] if atom_ids else []

    def _bounding_box_center_for_atoms(self, atom_ids: set[int]) -> QPointF | None:
        if not atom_ids:
            return None
        xs = [self.model.atoms[atom_id].x for atom_id in atom_ids if atom_id in self.model.atoms]
        ys = [self.model.atoms[atom_id].y for atom_id in atom_ids if atom_id in self.model.atoms]
        if not xs or not ys:
            return None
        return QPointF((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)

    def _clipboard_paste_offset(self, step: int, bond_length_px: float) -> tuple[float, float]:
        magnitude = max(18.0, bond_length_px * 0.35) * max(1, step)
        return magnitude, magnitude

    def add_atom(self, element: str, x: float, y: float) -> int:
        atom_id = self.model.add_atom(element, x, y)
        atom_item = _make_rect_item("atom", data1=atom_id)
        atom_item.setRect(QRectF(x - 2.0, y - 2.0, 4.0, 4.0))
        self.add_item(atom_item)
        self.atom_items[atom_id] = atom_item
        return atom_id

    def apply_atom_color(self, atom_id: int, color: str) -> None:
        self.model.atoms[atom_id].color = color

    def add_or_update_atom_label(
        self,
        atom_id: int,
        element: str,
        clear_smiles: bool = False,
        record: bool = False,
        allow_merge: bool = False,
        show_carbon: bool = False,
    ) -> None:
        self.model.atoms[atom_id].element = element
        self.model.atoms[atom_id].explicit_label = show_carbon

    def add_bond(self, atom_a: int, atom_b: int, order: int) -> int:
        self.model.bonds.append(Bond(atom_a, atom_b, order))
        return len(self.model.bonds) - 1

    def _restore_bond_from_state(self, bond_id: int, state: dict) -> None:
        self.restore_bond_calls.append((bond_id, dict(state)))
        self.model.bonds[bond_id] = Bond(
            state["a"],
            state["b"],
            state.get("order", 1),
            state.get("style", "single"),
            state.get("color", "#000000"),
        )

    def _translated_scene_item_state(
        self,
        state: dict,
        *,
        dx: float,
        dy: float,
        atom_id_map: dict[int, int],
    ) -> dict | None:
        if not isinstance(state, dict):
            return None
        translated = dict(state)
        kind = translated.get("kind")
        if kind == "mark":
            atom_id = translated.get("atom_id")
            translated["atom_id"] = atom_id_map.get(atom_id) if isinstance(atom_id, int) else None
            translated["x"] = float(translated["x"]) + dx
            translated["y"] = float(translated["y"]) + dy
            return translated
        if kind == "note":
            translated["x"] = float(translated["x"]) + dx
            translated["y"] = float(translated["y"]) + dy
            return translated
        return translated

    def create_scene_item_from_state(self, state: dict):
        self.created_scene_item_states.append(dict(state))
        kind = state.get("kind")
        if kind == "note":
            item = _make_note_item(str(state.get("text", "")), float(state.get("x", 0.0)), float(state.get("y", 0.0)))
        elif kind == "mark":
            item = _make_rect_item(
                "mark",
                data1={"atom_id": state.get("atom_id")},
                state=state,
                rect=QRectF(float(state.get("x", 0.0)), float(state.get("y", 0.0)), 6.0, 6.0),
            )
        else:
            item = _make_rect_item(kind or "item", state=state)
        self.created_items.append(item)
        self.add_item(item)
        return item

    def _atom_item_for_id(self, atom_id: int):
        return self.atom_items.get(atom_id)

    def clear_note_selection(self) -> None:
        self.clear_note_selection_calls += 1
        self.selected_notes.clear()

    def select_note(self, item: QGraphicsTextItem, additive: bool = True) -> None:
        self.selected_notes.append(item)

    def _update_selection_outline(self) -> None:
        self.update_selection_outline_calls += 1

    def _record_additions(
        self,
        before_next_atom_id: int,
        before_bond_count: int,
        before_smiles_input: str | None,
        added_scene_items: list | None = None,
    ) -> None:
        self.record_additions_calls.append(
            (
                before_next_atom_id,
                before_bond_count,
                before_smiles_input,
                added_scene_items if added_scene_items is not None else [],
            )
        )

    @staticmethod
    def _bounds_from_points(points: list[QPointF]) -> QRectF | None:
        if not points:
            return None
        xs = [point.x() for point in points]
        ys = [point.y() for point in points]
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    @staticmethod
    def _ts_bracket_rect_from_state(state: dict) -> QRectF | None:
        if not {"left", "top", "right", "bottom"} <= state.keys():
            return None
        return QRectF(
            float(state["left"]),
            float(state["top"]),
            float(state["right"]) - float(state["left"]),
            float(state["bottom"]) - float(state["top"]),
        )

    def set_atom_positions(self, positions: dict[int, tuple[float, float]], update_selection: bool = True) -> None:
        for atom_id, (x, y) in positions.items():
            if atom_id in self.model.atoms:
                self.model.atoms[atom_id].x = x
                self.model.atoms[atom_id].y = y

    def apply_scene_item_state(self, item: QGraphicsItem, state: dict) -> None:
        item.setData(9, dict(state))

    @staticmethod
    def _flip_point(point: QPointF, center: QPointF, horizontal: bool) -> QPointF:
        if horizontal:
            return QPointF(center.x() - (point.x() - center.x()), point.y())
        return QPointF(point.x(), center.y() - (point.y() - center.y()))


if __name__ == "__main__":
    unittest.main()
