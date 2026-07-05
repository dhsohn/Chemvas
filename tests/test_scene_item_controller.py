import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

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

if QApplication is not None:
    from ui.canvas_mark_registry import CanvasMarkRegistry
    from ui.canvas_scene_items_state import (
        SCENE_ITEM_COLLECTION_ATTRS,
        scene_item_collection_for,
        set_scene_item_collection_for,
    )
    from ui.handle_state import CanvasHandleState
    from ui.scene_item_controller import SceneItemController


class _FakeCanvas:
    def __init__(self) -> None:
        self._scene = QGraphicsScene()
        self.renderer = SimpleNamespace(
            style=SimpleNamespace(bond_length_px=20.0, bond_color="#000000"),
            ring_fill_brush=lambda: QBrush(QColor("#AA4400")),
        )
        self.bond_renderer = SimpleNamespace(update_bond_geometry=self.update_bond_geometry)
        self.model = SimpleNamespace(atoms={})
        for name in SCENE_ITEM_COLLECTION_ATTRS:
            set_scene_item_collection_for(self, name, [])
        self.mark_registry = CanvasMarkRegistry()
        self.handle_state = CanvasHandleState()
        self.make_selectable_calls = []
        self.updated_bond_ids = []
        self.bond_lookup = {}
        self.removed_mark_items = []
        self.updated_note_boxes = []
        self.clear_handles_calls = 0
        self.applied_note_style_items = []
        self.mark_centers = {}
        self.built_mark_kinds = []
        self.built_arrow_calls = []
        self.curved_arrow_path_calls = []
        self.built_ts_bracket_rects = []
        self.built_orbital_calls = []
        self.services = SimpleNamespace(
            canvas_graph_service=SimpleNamespace(bond_id_between=self.bond_id_between),
            note_controller=SimpleNamespace(apply_note_style=self.record_note_style_applied),
            selection_controller=SimpleNamespace(update_note_selection_box=self.record_note_selection_box_updated),
            scene_decoration_build_service=SimpleNamespace(
                build_mark_item=self.record_build_mark_item,
                set_mark_center=self.record_set_mark_center,
                build_arrow_item=self.record_build_arrow_item,
                build_ts_bracket_item=self.record_build_ts_bracket_item,
                build_orbital_items=self.record_build_orbital_items,
                ts_bracket_path=self.record_ts_bracket_path,
            ),
            canvas_mark_scene_service=SimpleNamespace(remove_mark_item=self.record_remove_mark_item),
            handle_overlay_service=SimpleNamespace(clear_handles=self.clear_handles),
            curved_arrow_path_service=SimpleNamespace(set_curved_arrow_path=self.record_set_curved_arrow_path),
        )

    def scene(self):
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

    def _make_selectable(self, item) -> None:
        self.make_selectable_calls.append(item)

    def record_note_style_applied(self, item: QGraphicsTextItem) -> None:
        item._style_applied = True
        self.applied_note_style_items.append(item)

    def record_build_mark_item(self, kind: str):
        self.built_mark_kinds.append(kind)
        if kind == "missing":
            return None
        return QGraphicsTextItem(kind)

    def record_set_mark_center(self, item, center: QPointF) -> None:
        self.mark_centers[item] = QPointF(center)
        item.setPos(center)

    def record_build_arrow_item(self, start: QPointF, end: QPointF, kind: str) -> QGraphicsPathItem:
        item = QGraphicsPathItem(QPainterPath())
        self.built_arrow_calls.append((QPointF(start), QPointF(end), kind, item))
        return item

    def record_set_curved_arrow_path(
        self,
        item: QGraphicsPathItem,
        start: QPointF,
        end: QPointF,
        control: QPointF,
        double: bool,
    ) -> None:
        self.curved_arrow_path_calls.append((item, QPointF(start), QPointF(end), QPointF(control), double))

    def record_build_ts_bracket_item(self, rect) -> QGraphicsPathItem:
        item = QGraphicsPathItem(QPainterPath())
        item.setData(0, "ts_bracket")
        self.built_ts_bracket_rects.append(rect)
        return item

    def record_build_orbital_items(self, center: QPointF, kind: str):
        self.built_orbital_calls.append((QPointF(center), kind))
        if kind == "missing":
            return []
        return [QGraphicsTextItem(kind)]

    def record_ts_bracket_path(self, _rect):
        return QPainterPath()

    def bond_id_between(self, atom_a: int, atom_b: int):
        return self.bond_lookup.get((atom_a, atom_b))

    def update_bond_geometry(self, bond_id: int) -> None:
        self.updated_bond_ids.append(bond_id)

    def record_remove_mark_item(self, item) -> None:
        self.removed_mark_items.append(item)
        if item in self.mark_items:
            self.mark_items.remove(item)
        data = item.data(1) or {}
        atom_id = data.get("atom_id") if isinstance(data, dict) else None
        if isinstance(atom_id, int):
            marks = self.mark_registry.by_atom.get(atom_id)
            if marks and item in marks:
                marks.remove(item)
        self._scene.removeItem(item)

    def record_note_selection_box_updated(self, item) -> None:
        self.updated_note_boxes.append(item)

    def clear_handles(self) -> None:
        self.clear_handles_calls += 1
        self.handle_state.target = None


class _BrokenSceneItem:
    def __init__(self, kind: str, *, data1=None) -> None:
        self._kind = kind
        self._data1 = data1

    def data(self, role: int):
        if role == 0:
            return self._kind
        if role == 1:
            return self._data1
        return None

    def scene(self):
        raise RuntimeError("item deleted")

    def setTextInteractionFlags(self, _flags) -> None:
        pass


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene item controller tests")
class SceneItemControllerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.canvas = _FakeCanvas()
        self.controller = SceneItemController(
            self.canvas,
            graph_service=self.canvas.services.canvas_graph_service,
        )

    def test_attach_scene_item_updates_registries_without_duplicates(self) -> None:
        mark = QGraphicsTextItem("+")
        mark.setData(0, "mark")
        mark.setData(1, {"atom_id": 7})
        note = QGraphicsTextItem("Mechanism")
        note.setData(0, "note")

        self.controller.attach_scene_item(mark)
        self.controller.attach_scene_item(mark)
        self.controller.restore_scene_item(note)

        self.assertEqual(self.canvas.mark_items, [mark])
        self.assertEqual(self.canvas.mark_registry.by_atom, {7: [mark]})
        self.assertEqual(self.canvas.note_items, [note])
        self.assertEqual(note.textInteractionFlags(), Qt.TextInteractionFlag.NoTextInteraction)
        self.assertTrue(mark.flags() & mark.GraphicsItemFlag.ItemIsSelectable)
        self.assertTrue(note.flags() & note.GraphicsItemFlag.ItemIsSelectable)
        self.assertIs(mark.scene(), self.canvas.scene())
        self.assertIs(note.scene(), self.canvas.scene())

    def test_attach_scene_item_rolls_back_mark_registry_when_scene_add_fails(self) -> None:
        mark = QGraphicsTextItem("+")
        mark.setData(0, "mark")
        mark.setData(1, {"atom_id": 7})

        with patch("ui.scene_item_lifecycle_service.add_item_to_canvas_scene", side_effect=RuntimeError("boom")):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                self.controller.attach_scene_item(mark)

        self.assertEqual(self.canvas.mark_items, [])
        self.assertEqual(self.canvas.mark_registry.by_atom, {})
        self.assertIsNone(mark.scene())

    def test_attach_scene_item_removes_scene_item_when_ring_refresh_fails(self) -> None:
        ring = QGraphicsPolygonItem(QPolygonF([QPointF(0.0, 0.0), QPointF(4.0, 0.0), QPointF(2.0, 3.0)]))
        ring.setData(0, "ring")
        ring.setData(2, [1, 2, 3])
        self.canvas.bond_lookup = {(1, 2): 17}

        def fail_update(_bond_id: int) -> None:
            raise RuntimeError("refresh failed")

        self.canvas.bond_renderer.update_bond_geometry = fail_update

        with self.assertRaisesRegex(RuntimeError, "refresh failed"):
            self.controller.attach_scene_item(ring)

        self.assertEqual(self.canvas.ring_items, [])
        self.assertIsNone(ring.scene())

    def test_attach_scene_item_refreshes_ring_bonds_after_partial_refresh_failure(self) -> None:
        ring = QGraphicsPolygonItem(QPolygonF([QPointF(0.0, 0.0), QPointF(4.0, 0.0), QPointF(2.0, 3.0)]))
        ring.setData(0, "ring")
        ring.setData(2, [1, 2, 3])
        self.canvas.bond_lookup = {(1, 2): 17, (2, 3): 18, (3, 1): 19}
        calls = []

        def fail_second_update(bond_id: int) -> None:
            calls.append((bond_id, ring in self.canvas.ring_items, ring.scene() is self.canvas.scene()))
            if len(calls) == 2:
                raise RuntimeError("refresh failed")

        self.canvas.bond_renderer.update_bond_geometry = fail_second_update

        with self.assertRaisesRegex(RuntimeError, "refresh failed"):
            self.controller.attach_scene_item(ring)

        post_rollback_calls = [bond_id for bond_id, registered, in_scene in calls if not registered and not in_scene]
        self.assertEqual(self.canvas.ring_items, [])
        self.assertIsNone(ring.scene())
        self.assertCountEqual(post_rollback_calls, [17, 18, 19])

    def test_restore_scene_item_skips_already_attached_or_deleted_items(self) -> None:
        note = QGraphicsTextItem("Attached")
        note.setData(0, "note")
        self.canvas.scene().addItem(note)
        self.canvas.note_items.append(note)
        broken = _BrokenSceneItem("note")

        self.controller.restore_scene_item(note)
        self.controller.restore_scene_item(broken)

        self.assertEqual(self.canvas.note_items, [note])
        self.assertEqual(self.canvas.make_selectable_calls, [])

    def test_restore_scene_item_registers_arrow_ts_bracket_and_orbital_items(self) -> None:
        curved = QGraphicsPathItem(QPainterPath())
        curved.setData(0, "curved_double")
        ts_bracket = QGraphicsPathItem(QPainterPath())
        ts_bracket.setData(0, "ts_bracket")
        orbital = QGraphicsItemGroup()
        orbital.setData(0, "orbital")

        self.controller.restore_scene_item(curved)
        self.controller.restore_scene_item(ts_bracket)
        self.controller.restore_scene_item(orbital)

        self.assertEqual(self.canvas.arrow_items, [curved])
        self.assertEqual(self.canvas.ts_bracket_items, [ts_bracket])
        self.assertEqual(self.canvas.orbital_items, [orbital])
        self.assertTrue(curved.flags() & curved.GraphicsItemFlag.ItemIsSelectable)
        self.assertTrue(ts_bracket.flags() & ts_bracket.GraphicsItemFlag.ItemIsSelectable)
        self.assertTrue(orbital.flags() & orbital.GraphicsItemFlag.ItemIsSelectable)
        self.assertIs(curved.scene(), self.canvas.scene())
        self.assertIs(ts_bracket.scene(), self.canvas.scene())
        self.assertIs(orbital.scene(), self.canvas.scene())

    def test_restore_scene_item_reuses_existing_registries_for_offscene_items_without_duplicates(self) -> None:
        ring = QGraphicsPolygonItem(QPolygonF([QPointF(0.0, 0.0), QPointF(4.0, 0.0), QPointF(2.0, 3.0)]))
        ring.setData(0, "ring")
        ring.setData(2, [1, 2, 3])
        note = QGraphicsTextItem("Detached")
        note.setData(0, "note")
        free_mark = QGraphicsTextItem("free")
        free_mark.setData(0, "mark")
        free_mark.setData(1, {"atom_id": None})
        curved = QGraphicsPathItem(QPainterPath())
        curved.setData(0, "curved_single")
        ts_bracket = QGraphicsPathItem(QPainterPath())
        ts_bracket.setData(0, "ts_bracket")
        orbital = QGraphicsItemGroup()
        orbital.setData(0, "orbital")

        self.canvas.ring_items.append(ring)
        self.canvas.note_items.append(note)
        self.canvas.mark_items.append(free_mark)
        self.canvas.arrow_items.append(curved)
        self.canvas.ts_bracket_items.append(ts_bracket)
        self.canvas.orbital_items.append(orbital)

        for item in (ring, note, free_mark, curved, ts_bracket, orbital):
            self.controller.restore_scene_item(item)

        self.assertEqual(self.canvas.ring_items, [ring])
        self.assertEqual(self.canvas.note_items, [note])
        self.assertEqual(self.canvas.mark_items, [free_mark])
        self.assertEqual(self.canvas.arrow_items, [curved])
        self.assertEqual(self.canvas.ts_bracket_items, [ts_bracket])
        self.assertEqual(self.canvas.orbital_items, [orbital])
        self.assertEqual(self.canvas.mark_registry.by_atom, {})
        for item in (ring, note, free_mark, curved, ts_bracket, orbital):
            self.assertTrue(item.flags() & item.GraphicsItemFlag.ItemIsSelectable)
        self.assertIs(ring.scene(), self.canvas.scene())
        self.assertIs(note.scene(), self.canvas.scene())
        self.assertIs(free_mark.scene(), self.canvas.scene())
        self.assertIs(curved.scene(), self.canvas.scene())
        self.assertIs(ts_bracket.scene(), self.canvas.scene())
        self.assertIs(orbital.scene(), self.canvas.scene())

    def test_restore_helper_methods_create_and_register_supported_items(self) -> None:
        self.canvas.model.atoms[7] = SimpleNamespace(x=10.0, y=20.0)

        ring = self.controller.restore_ring_from_state(
            {"points": [(0.0, 0.0), (6.0, 0.0), (3.0, 4.0)], "atom_ids": [1, 2, 3]}
        )
        note = self.controller.restore_note_from_state({"text": "Mechanism", "x": 3.0, "y": -4.0})
        mark = self.controller.restore_mark_from_state(
            {"mark_kind": "plus", "atom_id": 7, "dx": 5.0, "dy": -2.0, "text": "m"}
        )
        arrow = self.controller.restore_arrow_from_state(
            {
                "kind": "curved_double",
                "start": (1.0, 2.0),
                "end": (7.0, 8.0),
                "control": (4.0, 9.0),
                "double": True,
            }
        )
        ts_bracket = self.controller.restore_ts_bracket_from_state(
            {"left": -5.0, "top": -2.0, "right": 8.0, "bottom": 6.0}
        )
        orbital = self.controller.restore_orbital_from_state(
            {"orbital_kind": "sp2", "center": (2.0, 3.0), "scale": 1.2, "rotation": 15.0}
        )

        self.assertIsNotNone(ring)
        self.assertIn(ring, self.canvas.ring_items)
        self.assertIsNotNone(note)
        self.assertIn(note, self.canvas.note_items)
        self.assertIn(note, self.canvas.applied_note_style_items)
        self.assertEqual(note.toPlainText(), "Mechanism")
        self.assertIsNotNone(mark)
        self.assertIn(mark, self.canvas.mark_items)
        self.assertIn(mark, self.canvas.mark_registry.by_atom[7])
        self.assertEqual(self.canvas.built_mark_kinds, ["plus"])
        self.assertAlmostEqual(self.canvas.mark_centers[mark].x(), 15.0)
        self.assertAlmostEqual(self.canvas.mark_centers[mark].y(), 18.0)
        self.assertIsNotNone(arrow)
        self.assertIn(arrow, self.canvas.arrow_items)
        self.assertEqual(len(self.canvas.built_arrow_calls), 1)
        self.assertEqual(len(self.canvas.curved_arrow_path_calls), 1)
        self.assertIsNotNone(ts_bracket)
        self.assertIn(ts_bracket, self.canvas.ts_bracket_items)
        self.assertEqual(len(self.canvas.built_ts_bracket_rects), 1)
        self.assertIsNotNone(orbital)
        self.assertIn(orbital, self.canvas.orbital_items)
        self.assertEqual(self.canvas.built_orbital_calls[0][1], "sp2")

    def test_restore_helper_methods_return_none_for_invalid_state(self) -> None:
        self.assertIsNone(self.controller.restore_ring_from_state({"points": [(0.0, 0.0), (1.0, 1.0)]}))
        self.assertIsNone(
            self.controller.restore_mark_from_state({"mark_kind": "plus", "atom_id": 99, "dx": 1.0, "dy": 2.0})
        )
        self.assertIsNone(
            self.controller.restore_arrow_from_state({"kind": "curved_double", "start": (1.0, 2.0)})
        )
        self.assertIsNone(self.controller.restore_ts_bracket_from_state({"left": 1.0, "top": 2.0}))
        self.assertIsNone(self.controller.restore_orbital_from_state({"orbital_kind": "p"}))
        self.assertEqual(self.canvas.make_selectable_calls, [])
        self.assertEqual(self.canvas.ring_items, [])
        self.assertEqual(self.canvas.mark_items, [])
        self.assertEqual(self.canvas.arrow_items, [])
        self.assertEqual(self.canvas.ts_bracket_items, [])
        self.assertEqual(self.canvas.orbital_items, [])

    def test_create_scene_item_from_state_registers_supported_item_and_skips_invalid_inputs(self) -> None:
        self.canvas.model.atoms[3] = SimpleNamespace(x=4.0, y=5.0)

        note = self.controller.create_scene_item_from_state({"kind": "note", "text": "A", "x": 1.0, "y": 2.0})
        mark = self.controller.create_scene_item_from_state(
            {"kind": "mark", "mark_kind": "plus", "atom_id": 3, "dx": 2.0, "dy": -1.0}
        )
        default_mark = self.controller.create_scene_item_from_state(
            {"kind": "mark", "mark_kind": None, "atom_id": None, "x": 6.0, "y": 7.0}
        )
        unknown = self.controller.create_scene_item_from_state({"kind": "mystery"})
        invalid_ring = self.controller.create_scene_item_from_state({"kind": "ring", "points": [(0.0, 0.0), (1.0, 1.0)]})
        invalid_arrow = self.controller.create_scene_item_from_state({"kind": "arrow", "start": (0.0, 0.0)})
        invalid_mark = self.controller.create_scene_item_from_state(
            {"kind": "mark", "mark_kind": "missing", "atom_id": 3, "dx": 2.0, "dy": 1.0}
        )
        invalid_orbital = self.controller.create_scene_item_from_state({"kind": "orbital", "orbital_kind": "missing"})

        self.assertIsNotNone(note)
        self.assertIn(note, self.canvas.note_items)
        self.assertIsNotNone(mark)
        self.assertIn(mark, self.canvas.mark_items)
        self.assertIsNotNone(default_mark)
        self.assertIn(default_mark, self.canvas.mark_items)
        self.assertEqual(self.canvas.built_mark_kinds[:2], ["plus", "plus"])
        self.assertIsNone(unknown)
        self.assertIsNone(invalid_ring)
        self.assertIsNone(invalid_arrow)
        self.assertIsNone(invalid_mark)
        self.assertIsNone(invalid_orbital)

    def test_bond_ids_for_ring_item_returns_empty_for_short_or_invalid_sequences(self) -> None:
        short_ring = QGraphicsPolygonItem()
        short_ring.setData(2, "bad")
        mixed_ring = QGraphicsPolygonItem()
        mixed_ring.setData(2, [1, "bad", 2])
        self.canvas.bond_lookup = {(2, 1): 17}

        self.assertEqual(self.controller.bond_ids_for_ring_item(short_ring), set())
        self.assertEqual(self.controller.bond_ids_for_ring_item(mixed_ring), {17})

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
        self.canvas.handle_state.target = curved

        self.controller.remove_scene_item(note)
        self.controller.remove_scene_item(curved)

        self.assertNotIn(note, self.canvas.selected_notes)
        self.assertEqual(self.canvas.updated_note_boxes, [note])
        self.assertNotIn(note, self.canvas.note_items)
        self.assertIsNone(note.scene())
        self.assertNotIn(curved, self.canvas.arrow_items)
        self.assertIsNone(curved.scene())
        self.assertEqual(self.canvas.clear_handles_calls, 1)
        self.assertIsNone(self.canvas.handle_state.target)

    def test_remove_scene_item_cleans_registries_even_if_scene_lookup_raises(self) -> None:
        broken_note = _BrokenSceneItem("note")
        self.canvas.note_items.append(broken_note)
        self.canvas.selected_notes.append(broken_note)

        self.controller.remove_scene_item(broken_note)

        self.assertNotIn(broken_note, self.canvas.note_items)
        self.assertNotIn(broken_note, self.canvas.selected_notes)
        self.assertEqual(self.canvas.updated_note_boxes, [broken_note])

    def test_remove_scene_item_handles_none_and_off_registry_variants(self) -> None:
        self.controller.remove_scene_item(None)

        note = QGraphicsTextItem("Loose")
        note.setData(0, "note")
        self.canvas.scene().addItem(note)
        curved = QGraphicsPathItem(QPainterPath())
        curved.setData(0, "curved_single")
        self.canvas.scene().addItem(curved)
        ts_bracket = QGraphicsPathItem(QPainterPath())
        ts_bracket.setData(0, "ts_bracket")
        self.canvas.scene().addItem(ts_bracket)
        self.canvas.ts_bracket_items.append(ts_bracket)
        orbital = QGraphicsItemGroup()
        orbital.setData(0, "orbital")
        self.canvas.scene().addItem(orbital)
        self.canvas.handle_state.target = orbital

        self.controller.remove_scene_item(note)
        self.controller.remove_scene_item(curved)
        self.controller.remove_scene_item(ts_bracket)
        self.controller.remove_scene_item(orbital)

        self.assertEqual(self.canvas.updated_note_boxes, [note])
        self.assertIsNone(note.scene())
        self.assertIsNone(curved.scene())
        self.assertIsNone(ts_bracket.scene())
        self.assertNotIn(ts_bracket, self.canvas.ts_bracket_items)
        self.assertEqual(self.canvas.clear_handles_calls, 1)
        self.assertIsNone(orbital.scene())

    def test_remove_scene_item_cleans_mark_registry_after_helper_removal(self) -> None:
        mark = QGraphicsTextItem("-")
        mark.setData(0, "mark")
        mark.setData(1, {"atom_id": 11})
        self.canvas.scene().addItem(mark)
        self.canvas.mark_items.append(mark)
        self.canvas.mark_registry.by_atom[11] = [mark]

        self.controller.remove_scene_item(mark)

        self.assertEqual(self.canvas.removed_mark_items, [mark])
        self.assertNotIn(mark, self.canvas.mark_items)
        self.assertNotIn(11, self.canvas.mark_registry.by_atom)
        self.assertIsNone(mark.scene())

    def test_remove_scene_item_keeps_atom_mark_registry_when_sibling_remains_and_refreshes_detached_ring(self) -> None:
        first_mark = QGraphicsTextItem("-")
        first_mark.setData(0, "mark")
        first_mark.setData(1, {"atom_id": 11})
        second_mark = QGraphicsTextItem("+")
        second_mark.setData(0, "mark")
        second_mark.setData(1, {"atom_id": 11})
        self.canvas.scene().addItem(first_mark)
        self.canvas.mark_items.extend([first_mark, second_mark])
        self.canvas.mark_registry.by_atom[11] = [first_mark, second_mark]

        ring = QGraphicsPolygonItem(QPolygonF([QPointF(0.0, 0.0), QPointF(4.0, 0.0), QPointF(2.0, 3.0)]))
        ring.setData(0, "ring")
        ring.setData(2, [1, 2, 3])
        self.canvas.bond_lookup = {
            (1, 2): 101,
            (2, 3): 102,
            (3, 1): 103,
        }

        self.controller.remove_scene_item(first_mark)
        self.controller.remove_scene_item(ring)

        self.assertEqual(self.canvas.mark_registry.by_atom[11], [second_mark])
        self.assertEqual(self.canvas.removed_mark_items, [first_mark])
        self.assertCountEqual(self.canvas.updated_bond_ids, [101, 102, 103])

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
        self.canvas.handle_state.target = orbital

        self.controller.remove_scene_item(orbital)

        self.assertEqual(self.canvas.clear_handles_calls, 1)
        self.assertNotIn(orbital, self.canvas.orbital_items)
        self.assertIsNone(orbital.scene())


if __name__ == "__main__":
    unittest.main()
