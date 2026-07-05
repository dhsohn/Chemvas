import os
import re
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import QFont, QImage, QPolygonF
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

if QApplication is not None:
    from core.history import (
        CompositeCommand,
        DeleteAtomsCommand,
        DeleteBondCommand,
    )
    from core.model import Atom, Bond, MoleculeModel
    from ui.atom_coords_access import atom_coords_3d_for
    from ui.canvas_atom_graphics_state import (
        atom_dots_for,
        atom_items_for,
        set_atom_dots_for,
        set_atom_items_for,
    )
    from ui.canvas_bond_graphics_state import bond_items_for, set_bond_items_for
    from ui.canvas_graph_state import CanvasGraphState
    from ui.canvas_mark_registry import CanvasMarkRegistry
    from ui.canvas_scene_items_state import (
        SCENE_ITEM_COLLECTION_ATTRS,
        scene_item_collection_for,
        set_scene_item_collection_for,
    )
    from ui.canvas_smiles_input_state import (
        last_smiles_input_for,
        set_last_smiles_input_for,
    )
    from ui.graphics_items import AtomLabelItem
    from ui.history_commands import DeleteSceneItemsCommand
    from ui.scene_clipboard_controller import (
        CLIPBOARD_PDF_MIME,
        CLIPBOARD_SVG_MIME,
        SceneClipboardController,
    )
    from ui.scene_clipboard_state import SceneClipboardState
    from ui.scene_clipboard_transaction_logic import build_clipboard_copy_plan
    from ui.scene_delete_controller import SceneDeleteController
    from ui.scene_transform_controller import SceneTransformController


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
        if kind == "mark":
            mark_data = dict(data1) if isinstance(data1, dict) else {}
            for key in ("atom_id", "dx", "dy", "text"):
                if key in state and key not in mark_data:
                    mark_data[key] = state.get(key)
            if "mark_kind" in state and "kind" not in mark_data:
                mark_data["kind"] = state.get("mark_kind")
            item.setData(1, mark_data)
            item.setPos(float(state.get("x", 0.0)), float(state.get("y", 0.0)))
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


def scene_clipboard_controller_for(canvas) -> SceneClipboardController:
    return SceneClipboardController(
        canvas,
        selection_controller=canvas.services.selection_controller,
        bond_mutation_service=canvas.services.canvas_bond_mutation_service,
    )


def scene_delete_controller_for(canvas) -> SceneDeleteController:
    return SceneDeleteController(
        canvas,
        move_controller=canvas.services.move_controller,
        atom_mutation_service=canvas.services.canvas_atom_mutation_service,
        bond_mutation_service=canvas.services.canvas_bond_mutation_service,
        style_controller=canvas.services.style_controller,
        history_service=canvas.history_service,
    )


def scene_transform_controller_for(canvas) -> SceneTransformController:
    return SceneTransformController(
        canvas,
        move_controller=canvas.services.move_controller,
        graph_service=canvas.services.canvas_graph_service,
        history_service=canvas.history_service,
    )


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
        controller = scene_delete_controller_for(canvas)

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

        controller = scene_delete_controller_for(canvas)

        self.assertTrue(controller.delete_selected_items())
        self.assertEqual(canvas.delete_bond_calls, [])
        self.assertEqual(len(canvas.pushed_commands), 1)
        self.assertIsInstance(canvas.pushed_commands[0], DeleteBondCommand)
        self.assertEqual(canvas.remove_bond_calls, [0])
        self.assertEqual(sorted(canvas.redraw_connected_bonds_calls), [1, 2])
        self.assertEqual(canvas.suspend_selection_outline_calls, [True, False])
        self.assertEqual(canvas.update_selection_outline_calls, 1)

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
        canvas.mark_registry.by_atom[1] = [linked_mark, sibling_mark]

        controller = scene_delete_controller_for(canvas)

        self.assertTrue(controller.delete_selected_items())
        self.assertEqual(len(canvas.pushed_commands), 1)
        command = canvas.pushed_commands[0]
        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual(canvas.clear_handles_calls, 1)
        self.assertIsNone(last_smiles_input_for(canvas))
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
        self.assertEqual(canvas.suspend_selection_outline_calls, [True, False])
        self.assertEqual(canvas.update_selection_outline_calls, 1)

    def test_delete_selected_items_pushes_single_scene_item_command(self) -> None:
        canvas = _FakeCanvas()
        note_item = _make_note_item("Solo", 12.0, 14.0)
        canvas.add_item(note_item, selected=True)
        controller = scene_delete_controller_for(canvas)

        self.assertTrue(controller.delete_selected_items())
        self.assertEqual(len(canvas.pushed_commands), 1)
        self.assertIsInstance(canvas.pushed_commands[0], DeleteSceneItemsCommand)
        self.assertEqual(canvas.removed_scene_items, [note_item])
        self.assertEqual(canvas.clear_handles_calls, 0)
        self.assertEqual(canvas.suspend_selection_outline_calls, [True, False])
        self.assertEqual(canvas.update_selection_outline_calls, 1)

    def test_delete_selected_items_includes_note_selection_registry(self) -> None:
        canvas = _FakeCanvas()
        note_item = _make_note_item("Registry", 12.0, 14.0)
        canvas.add_item(note_item, selected=False)
        canvas.selected_notes = [note_item]
        controller = scene_delete_controller_for(canvas)

        self.assertTrue(controller.delete_selected_items())
        self.assertEqual(len(canvas.pushed_commands), 1)
        self.assertIsInstance(canvas.pushed_commands[0], DeleteSceneItemsCommand)
        self.assertEqual(canvas.removed_scene_items, [note_item])

    def test_delete_ring_prefers_scene_item_controller_when_available(self) -> None:
        canvas = _FakeCanvas()
        ring_item = _make_ring_item()
        controller_removed_items: list[object] = []
        canvas.services.scene_item_controller = SimpleNamespace(remove_scene_item=controller_removed_items.append)
        controller = scene_delete_controller_for(canvas)

        command = controller.delete_ring(ring_item, record=False)

        self.assertIsInstance(command, DeleteSceneItemsCommand)
        self.assertEqual(controller_removed_items, [ring_item])
        self.assertEqual(canvas.removed_scene_items, [])

    def test_delete_ring_records_command_when_enabled(self) -> None:
        canvas = _FakeCanvas()
        ring_item = _make_ring_item()
        controller = scene_delete_controller_for(canvas)

        command = controller.delete_ring(ring_item, record=True)

        self.assertIsInstance(command, DeleteSceneItemsCommand)
        self.assertEqual(canvas.removed_scene_items, [ring_item])
        self.assertEqual(canvas.pushed_commands, [command])

    def test_clipboard_selection_payload_rejects_wrong_type_and_version(self) -> None:
        canvas = _FakeCanvas()
        controller = scene_clipboard_controller_for(canvas)
        clipboard = QApplication.clipboard()

        for raw_payload in (
            b'{"format":"not-chemvas-selection","version":1}',
            b'{"format":"chemvas-selection","version":999}',
        ):
            mime_data = canvas.new_mime_data(raw_payload)
            clipboard.setMimeData(mime_data)
            payload, payload_json = controller.clipboard_selection_payload()
            self.assertIsNone(payload)
            self.assertIsNone(payload_json)

    def test_clipboard_selection_payload_rejects_image_only_clipboard(self) -> None:
        canvas = _FakeCanvas()
        controller = scene_clipboard_controller_for(canvas)
        clipboard = QApplication.clipboard()
        mime_data = QImage(4, 4, QImage.Format.Format_ARGB32)
        image_mime = canvas.new_image_mime_data(mime_data)
        clipboard.setMimeData(image_mime)

        self.assertEqual(controller.clipboard_selection_payload(), (None, None))

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
        free_mark.setPos(50.0, 60.0)
        linked_mark = _make_rect_item(
            "mark",
            data1={"atom_id": 1, "dx": 2.0, "dy": 3.0},
            state={"kind": "mark", "atom_id": 1, "x": 2.0, "y": 3.0},
        )
        linked_mark.setPos(2.0, 3.0)
        ring_item = _make_ring_item()
        ring_item.setData(2, [1, 2])
        canvas.ring_items.append(ring_item)
        canvas.mark_registry.by_atom[1] = [linked_mark]
        for item in (atom_item, bond_item, note_item, free_mark, linked_mark):
            canvas.add_item(item, selected=True)
        canvas.add_item(ring_item, selected=False)
        controller = scene_clipboard_controller_for(canvas)

        payload = controller.selection_payload_for_clipboard()

        assert payload is not None
        self.assertEqual(payload["format"], "chemvas-selection")
        self.assertEqual(payload["version"], 1)
        self.assertEqual([atom["id"] for atom in payload["atoms"]], [1, 2])
        self.assertEqual(payload["bonds"], [{"a": 1, "b": 2, "order": 2, "style": "double", "color": "#333333"}])
        self.assertEqual(
            payload["rings"],
            [
                {
                    "kind": "ring",
                    "points": [(0.0, 0.0), (12.0, 0.0), (6.0, 10.0)],
                    "atom_ids": [1, 2],
                    "color": None,
                    "alpha": 0.0,
                }
            ],
        )
        self.assertEqual(
            payload["marks"],
            [
                {
                    "kind": "mark",
                    "mark_kind": None,
                    "text": None,
                    "atom_id": 1,
                    "dx": 2.0,
                    "dy": 3.0,
                    "x": 2.0,
                    "y": 3.0,
                },
                {
                    "kind": "mark",
                    "mark_kind": None,
                    "text": None,
                    "atom_id": None,
                    "dx": None,
                    "dy": None,
                    "x": 50.0,
                    "y": 60.0,
                },
            ],
        )
        self.assertEqual(len(payload["scene_items"]), 1)
        note_state = payload["scene_items"][0]
        self.assertEqual(
            {key: note_state[key] for key in ("kind", "text", "x", "y")},
            {"kind": "note", "text": "payload", "x": 30.0, "y": 40.0},
        )

    def test_selection_payload_for_clipboard_returns_none_for_empty_selection(self) -> None:
        canvas = _FakeCanvas()
        controller = scene_clipboard_controller_for(canvas)

        self.assertIsNone(controller.selection_payload_for_clipboard())

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
        controller = scene_clipboard_controller_for(canvas)

        self.assertFalse(controller.copy_selection_to_clipboard())

        note_item = _make_note_item("copy", 10.0, 12.0)
        canvas.add_item(note_item, selected=True)
        self.assertTrue(controller.copy_selection_to_clipboard())
        self.assertIsNotNone(canvas.scene_clipboard_state.paste_source_json)
        self.assertEqual(canvas.scene_clipboard_state.paste_count, 0)
        mime_data = QApplication.clipboard().mimeData()
        self.assertTrue(mime_data.hasImage())
        self.assertTrue(mime_data.hasFormat(CLIPBOARD_SVG_MIME))
        self.assertTrue(mime_data.hasFormat(CLIPBOARD_PDF_MIME))
        self.assertIn(b"<svg", bytes(mime_data.data(CLIPBOARD_SVG_MIME)))
        self.assertTrue(bytes(mime_data.data(CLIPBOARD_PDF_MIME)).startswith(b"%PDF-"))
        self.assertTrue(mime_data.hasFormat(canvas.CLIPBOARD_SELECTION_MIME))

    def test_vector_clipboard_uses_label_ink_bounds_not_hit_bounds(self) -> None:
        canvas = _FakeCanvas()
        controller = scene_clipboard_controller_for(canvas)
        label = _set_selectable(AtomLabelItem("N", hit_radius=80.0))
        label.setFont(QFont("Arial", 12))
        label.setData(0, "note")
        label.setData(9, {"kind": "note", "text": "N", "x": 10.0, "y": 12.0})
        label.setPos(10.0, 12.0)
        canvas.add_item(label, selected=True)

        self.assertTrue(controller.copy_selection_to_clipboard())
        svg_data = bytes(QApplication.clipboard().mimeData().data(CLIPBOARD_SVG_MIME))
        match = re.search(rb'viewBox="0 0 ([0-9.]+) ([0-9.]+)"', svg_data)

        self.assertIsNotNone(match)
        assert match is not None
        vector_width = float(match.group(1))
        self.assertLess(vector_width, label.sceneBoundingRect().width())

    def test_paste_selection_remaps_atom_ids_and_restores_selection(self) -> None:
        canvas = _FakeCanvas()
        controller = scene_clipboard_controller_for(canvas)

        stale_item = _make_rect_item("stale")
        canvas.add_item(stale_item, selected=True)

        payload = {
            "format": "chemvas-selection",
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
        controller.clipboard_selection_payload = lambda: (payload, "payload-json")

        self.assertTrue(controller.paste_selection_from_clipboard())

        self.assertEqual(canvas.scene_clipboard_state.paste_source_json, "payload-json")
        self.assertEqual(canvas.scene_clipboard_state.paste_count, 1)
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
        controller = scene_clipboard_controller_for(canvas)

        controller.clipboard_selection_payload = lambda: (None, None)
        self.assertFalse(controller.paste_selection_from_clipboard())

        controller.clipboard_selection_payload = lambda: (
            {"format": "chemvas-selection", "version": 1, "atoms": [], "bonds": [], "rings": [], "marks": [], "scene_items": []},
            "payload-json",
        )
        self.assertFalse(controller.paste_selection_from_clipboard())

    def test_paste_selection_from_clipboard_accepts_scene_item_only_payload_and_resets_source(self) -> None:
        canvas = _FakeCanvas()
        canvas.scene_clipboard_state.paste_source_json = "old-source"
        canvas.scene_clipboard_state.paste_count = 5
        controller = scene_clipboard_controller_for(canvas)
        payload = {
            "format": "chemvas-selection",
            "version": 1,
            "atoms": [{"id": "bad"}],
            "bonds": [{"a": 1, "b": "bad"}],
            "rings": [],
            "marks": [],
            "scene_items": [{"kind": "note", "text": "solo", "x": 10.0, "y": 15.0}],
        }
        controller.clipboard_selection_payload = lambda: (payload, "new-source")

        self.assertTrue(controller.paste_selection_from_clipboard())
        self.assertEqual(canvas.scene_clipboard_state.paste_source_json, "new-source")
        self.assertEqual(canvas.scene_clipboard_state.paste_count, 1)
        self.assertEqual(canvas.created_scene_item_states, [{"kind": "note", "text": "solo", "x": 28.0, "y": 33.0}])
        self.assertEqual(canvas.record_additions_calls, [(0, 0, None, canvas.created_items)])

    def test_flip_selected_items_noop_paths(self) -> None:
        canvas = _FakeCanvas()
        controller = scene_transform_controller_for(canvas)

        controller.flip_selected_items(horizontal=True)

        self.assertEqual(canvas.pushed_commands, [])

    def test_flip_selected_items_skips_atom_component_without_center(self) -> None:
        canvas = _FakeCanvas()
        missing_atom_item = _make_rect_item("atom", data1=99)
        canvas.add_item(missing_atom_item, selected=True)
        controller = scene_transform_controller_for(canvas)

        controller.flip_selected_items(horizontal=True)

        self.assertEqual(canvas.pushed_commands, [])
        self.assertEqual(canvas.update_selection_outline_calls, 0)


class _FakeSceneItemController:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def remove_scene_item(self, item: QGraphicsItem) -> None:
        self.canvas.remove_scene_item(item)

    def create_scene_item_from_state(self, state: dict):
        return self.canvas.create_scene_item_from_state(state)

    def apply_scene_item_state(self, item: QGraphicsItem, state: dict) -> None:
        self.canvas.apply_scene_item_state(item, state)

    def attach_scene_item(self, item: QGraphicsItem) -> None:
        self.canvas.attach_scene_item(item)

    def restore_scene_item(self, item: QGraphicsItem) -> None:
        self.canvas.restore_scene_item(item)


class _FakeCanvas:
    CLIPBOARD_SELECTION_MIME = "application/x-chemvas-selection+json"
    CLIPBOARD_SELECTION_VERSION = 1

    def __init__(self) -> None:
        self._scene = QGraphicsScene()
        self.model = MoleculeModel()
        self.renderer = SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0, bond_line_width=1.0))
        set_last_smiles_input_for(self, None)
        self.mark_registry = CanvasMarkRegistry()
        for name in SCENE_ITEM_COLLECTION_ATTRS:
            set_scene_item_collection_for(self, name, [])
        self.scene_clipboard_state = SceneClipboardState()
        self.scene_clipboard_state.paste_source_json = None
        self.scene_clipboard_state.paste_count = 0
        self._clipboard_payload = None
        self.graph_state = CanvasGraphState()
        self.delete_bond_calls: list[tuple[int, bool]] = []
        self.remove_bond_calls: list[int] = []
        self.redraw_connected_bonds_calls: list[int] = []
        self.remove_atom_calls: list[tuple[int, bool]] = []
        self.removed_scene_items: list[QGraphicsItem] = []
        self.pushed_commands: list[object] = []
        self.history_service = SimpleNamespace(push=self.push_command)
        self.clear_handles_calls = 0
        set_atom_items_for(self, {})
        set_atom_dots_for(self, {})
        set_bond_items_for(self, {})
        self.created_scene_item_states: list[dict] = []
        self.created_items: list[QGraphicsItem] = []
        self.restore_bond_calls: list[tuple[int, dict]] = []
        self.selected_notes: list[QGraphicsTextItem] = []
        self.clear_note_selection_calls = 0
        self.update_selection_outline_calls = 0
        self.suspend_selection_outline_calls: list[bool] = []
        self.record_additions_calls: list[tuple[int, int, str | None, list[QGraphicsItem]]] = []
        self.services = SimpleNamespace(
            history_service=self.history_service,
            scene_item_controller=_FakeSceneItemController(self),
            canvas_graph_service=SimpleNamespace(connected_components=self.connected_components),
            atom_label_service=SimpleNamespace(
                add_or_update_atom_label=self.add_or_update_atom_label,
                position_label=self.position_label,
            ),
            canvas_atom_mutation_service=SimpleNamespace(
                add_atom=self.add_atom,
                remove_atom_only=self._remove_atom_only,
                restore_atom_from_state=self.restore_atom_from_state,
                apply_atom_color=self.apply_atom_color,
            ),
            canvas_bond_mutation_service=SimpleNamespace(
                add_bond=self.add_bond,
                restore_bond_from_state=self._restore_bond_from_state,
                remove_bond_by_id=self._remove_bond_by_id,
                trim_bonds_to_length=self._trim_bonds_to_length,
            ),
            scene_decoration_build_service=SimpleNamespace(set_mark_center=self.set_mark_center),
            hit_testing_service=SimpleNamespace(mark_spatial_index_dirty=self.mark_spatial_index_dirty),
            canvas_ring_fill_scene_service=SimpleNamespace(update_ring_fills_for_atoms=lambda atom_ids: None),
            handle_overlay_service=SimpleNamespace(clear_handles=self.clear_handles),
            canvas_history_recording_service=SimpleNamespace(record_additions=self._record_additions),
            selection_controller=SimpleNamespace(
                clear_note_selection=self.clear_note_selection,
                select_note=self.select_note,
                update_selection_outline=self.refresh_selection_outline,
            ),
            style_controller=SimpleNamespace(suspend_selection_outline=self.suspend_selection_outline),
            move_controller=SimpleNamespace(
                redraw_connected_bonds=self.redraw_connected_bonds,
                redraw_bonds_for_atoms=self.redraw_bonds_for_atoms,
            ),
        )

    def devicePixelRatioF(self) -> float:
        return 1.0

    def scene(self) -> QGraphicsScene:
        return self._scene

    def _scene_items(self, name: str):
        return scene_item_collection_for(self, name)

    def _set_scene_items(self, name: str, value) -> None:
        set_scene_item_collection_for(self, name, value)

    selected_notes = property(lambda self: self._scene_items("selected_notes"), lambda self, value: self._set_scene_items("selected_notes", value))
    ring_items = property(lambda self: self._scene_items("ring_items"), lambda self, value: self._set_scene_items("ring_items", value))
    note_items = property(lambda self: self._scene_items("note_items"), lambda self, value: self._set_scene_items("note_items", value))
    mark_items = property(lambda self: self._scene_items("mark_items"), lambda self, value: self._set_scene_items("mark_items", value))
    arrow_items = property(lambda self: self._scene_items("arrow_items"), lambda self, value: self._set_scene_items("arrow_items", value))
    ts_bracket_items = property(lambda self: self._scene_items("ts_bracket_items"), lambda self, value: self._set_scene_items("ts_bracket_items", value))
    orbital_items = property(lambda self: self._scene_items("orbital_items"), lambda self, value: self._set_scene_items("orbital_items", value))

    @property
    def atom_items(self):
        return atom_items_for(self)

    @atom_items.setter
    def atom_items(self, value) -> None:
        set_atom_items_for(self, value)

    @property
    def atom_dots(self):
        return atom_dots_for(self)

    @atom_dots.setter
    def atom_dots(self, value) -> None:
        set_atom_dots_for(self, value)

    @property
    def bond_items(self):
        return bond_items_for(self)

    @bond_items.setter
    def bond_items(self, value) -> None:
        set_bond_items_for(self, value)

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

    def _trim_bonds_to_length(self, length: int) -> None:
        del self.model.bonds[length:]

    def redraw_connected_bonds(self, atom_id: int, skip_bond_id: int | None = None) -> None:
        self.redraw_connected_bonds_calls.append(atom_id)

    def redraw_bonds_for_atoms(self, atom_ids: set[int]) -> None:
        for atom_id in atom_ids:
            self.redraw_connected_bonds(atom_id)

    def mark_spatial_index_dirty(self) -> None:
        return None

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
        atom_coords_3d_for(self).pop(atom_id, None)

    def scene_item_state(self, item: QGraphicsItem) -> dict:
        state = item.data(9)
        return dict(state) if isinstance(state, dict) else {}

    def remove_scene_item(self, item: QGraphicsItem) -> None:
        self.removed_scene_items.append(item)
        self._scene.removeItem(item)

    def attach_scene_item(self, item: QGraphicsItem) -> None:
        self.add_item(item)

    def restore_scene_item(self, item: QGraphicsItem) -> None:
        self.add_item(item)

    def clear_handles(self) -> None:
        self.clear_handles_calls += 1

    def suspend_selection_outline(self, suspended: bool) -> None:
        self.suspend_selection_outline_calls.append(bool(suspended))

    def refresh_selection_outline(self) -> None:
        self.update_selection_outline_calls += 1

    def push_command(self, command) -> None:
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

    def _selected_atom_ids_for_transform(self) -> set[int]:
        atom_ids: set[int] = set()
        for item in self._scene.selectedItems():
            if item.data(0) == "atom" and isinstance(item.data(1), int):
                atom_ids.add(item.data(1))
        return atom_ids

    def connected_components(self, atom_ids: set[int]) -> list[set[int]]:
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

    def restore_atom_from_state(self, atom_id: int, state: dict) -> None:
        self.model.atoms[atom_id] = Atom(
            state.get("element", "C"),
            float(state.get("x", 0.0)),
            float(state.get("y", 0.0)),
            color=state.get("color", "#000000"),
            explicit_label=bool(state.get("explicit_label", False)),
        )

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

    def position_label(self, item: QGraphicsItem, x: float, y: float) -> None:
        set_rect = getattr(item, "setRect", None)
        if callable(set_rect):
            set_rect(QRectF(x - 2.0, y - 2.0, 4.0, 4.0))
            return
        item.setPos(x, y)

    def set_mark_center(self, item: QGraphicsItem, center: QPointF) -> None:
        item.setPos(center)
        state = item.data(9)
        if isinstance(state, dict):
            state = dict(state)
            state["x"] = center.x()
            state["y"] = center.y()
            item.setData(9, state)

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
