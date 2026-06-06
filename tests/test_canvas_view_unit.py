import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QColor, QFocusEvent, QPen
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.model import Atom, Bond
    from ui.atom_label_access import (
        atom_has_visible_label_for,
        implicit_carbon_dot_brush_for,
        uses_compact_label_hit_shape_for,
    )
    from ui.canvas_atom_graphics_state import set_atom_items_for
    from ui.canvas_history_state import CanvasHistoryState, history_state_for
    from ui.canvas_hit_testing_service import CanvasHitTestingService
    from ui.canvas_insert_state import CanvasInsertState, insert_state_for
    from ui.canvas_mark_registry import CanvasMarkRegistry
    from ui.canvas_note_controller import CanvasNoteController
    from ui.canvas_scene_items_state import (
        ring_items_for,
        selected_notes_for,
        set_scene_item_collection_for,
        set_selected_notes_for,
    )
    from ui.canvas_service_access import canvas_services_for
    from ui.canvas_tool_settings_state import tool_settings_state_for
    from ui.canvas_view import CanvasView
    from ui.history_commands import (
        AddSceneItemsCommand,
        DeleteSceneItemsCommand,
        UpdateSceneItemCommand,
    )
    from ui.input_view_access import (
        shortcut_modifiers_for,
    )
    from ui.note_item import NoteItem
    from ui.note_item_access import committed_note_text_for
    from ui.scene_clipboard_transaction_logic import (
        clipboard_paste_offset,
        translated_point_value,
        translated_scene_item_state,
    )
    from ui.scene_transform_logic import bounds_from_points, flip_point
    from ui.selection_collection_access import (
        selected_bond_atom_ids_for,
        selected_structure_ids_for,
        selection_signature_for,
        selection_snapshot_for,
        selection_target_item,
    )
    from ui.selection_service_access import (
        structure_item_is_selected_for,
    )
    from ui.selection_style_access import (
        selection_bond_overlay_width_for,
        selection_indicator_rect_for_atom_for,
    )
    from ui.sheet_setup_access import set_sheet_setup_for, sheet_rect_for
    from ui.structure_geometry_access import (
        atom_point_for,
        regular_ring_points_for_atom_for,
        regular_ring_points_for_bond_for,
        ring_polygon_points_for_bond_for,
        sprout_bond_endpoint_for,
        template_points_for_bond_for,
    )
    from ui.structure_payload_access import (
        build_3d_conversion_payload_for,
        build_selected_structure_payload_for,
        build_structure_payload_for,
    )
    from ui.structure_payload_logic import (
        build_atom_annotations,
        expand_atom_ids_for_structure,
    )


class _FakeNoteCanvas:
    def __init__(self) -> None:
        self.commands = []
        self.removed_items = []
        set_selected_notes_for(self, [])
        self.updated_boxes = []
        self.history_service = SimpleNamespace(push=self.push_command)
        self.services = SimpleNamespace(
            history_service=self.history_service,
            scene_item_controller=SimpleNamespace(remove_scene_item=self.removed_items.append),
            selection_controller=SimpleNamespace(update_note_selection_box=self.record_note_selection_box_updated),
        )
        self.services.note_controller = CanvasNoteController(
            self,
            history_service=self.services.history_service,
        )

    def _note_state_dict(self, item) -> dict:
        return {
            "kind": "note",
            "text": item.toPlainText(),
            "x": item.pos().x(),
            "y": item.pos().y(),
        }

    def push_command(self, command) -> None:
        self.commands.append(command)

    @property
    def selected_notes(self):
        return selected_notes_for(self)

    @selected_notes.setter
    def selected_notes(self, value) -> None:
        set_selected_notes_for(self, value)

    def remove_scene_item(self, item) -> None:
        self.removed_items.append(item)

    def record_note_selection_box_updated(self, item) -> None:
        self.updated_boxes.append(item)


class _FakeKeyEvent:
    def __init__(self, key, modifiers=Qt.KeyboardModifier.NoModifier, text: str = "") -> None:
        self._key = key
        self._modifiers = modifiers
        self._text = text

    def key(self):
        return self._key

    def modifiers(self):
        return self._modifiers

    def text(self):
        return self._text


class _FakeItem:
    def __init__(self, kind, data1=None, data2=None) -> None:
        self.kind = kind
        self.data1 = data1
        self.data2 = data2

    def data(self, key):
        if key == 0:
            return self.kind
        if key == 1:
            return self.data1
        if key == 2:
            return self.data2
        return None


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_canvas_background_defaults_to_workspace_gray(self) -> None:
        canvas = CanvasView()
        self.addCleanup(canvas.close)

        # Workspace is a soft gray so the white page reads as paper floating
        # above it (the page itself is painted white in drawBackground).
        self.assertEqual(canvas.backgroundBrush().color(), QColor("#e7e7e4"))

    def test_canvas_defaults_to_a4_landscape_sheet_and_can_switch_portrait(self) -> None:
        canvas = CanvasView()
        self.addCleanup(canvas.close)

        self.assertEqual(canvas.sheet_size, "A4")
        self.assertEqual(canvas.sheet_orientation, "landscape")
        self.assertAlmostEqual(sheet_rect_for(canvas).width(), 842.0)
        self.assertAlmostEqual(sheet_rect_for(canvas).height(), 595.0)
        self.assertAlmostEqual(canvas.sceneRect().width(), 1002.0)
        self.assertAlmostEqual(canvas.sceneRect().height(), 755.0)

        set_sheet_setup_for(canvas, "A4", "portrait")

        self.assertEqual(canvas.sheet_orientation, "portrait")
        self.assertAlmostEqual(sheet_rect_for(canvas).width(), 595.0)
        self.assertAlmostEqual(sheet_rect_for(canvas).height(), 842.0)
        self.assertAlmostEqual(canvas.sceneRect().width(), 755.0)
        self.assertAlmostEqual(canvas.sceneRect().height(), 1002.0)

    def test_history_fields_are_backed_by_state_holder(self) -> None:
        canvas = CanvasView()
        self.addCleanup(canvas.close)

        self.assertFalse(hasattr(canvas, "_history_state"))
        self.assertFalse(hasattr(canvas, "history_service"))
        self.assertFalse(hasattr(canvas, "contexts"))
        self.assertIsInstance(history_state_for(canvas), CanvasHistoryState)
        self.assertIs(history_state_for(canvas), canvas.runtime_state.history_state)

        history_state_for(canvas).history = ["undo"]
        history_state_for(canvas).redo_stack = ["redo"]
        history_state_for(canvas).enabled = False
        history_state_for(canvas).limit = 3
        callback = mock.Mock()
        history_state_for(canvas).change_callback = callback

        self.assertEqual(canvas.runtime_state.history_state.history, ["undo"])
        self.assertEqual(canvas.runtime_state.history_state.redo_stack, ["redo"])
        self.assertFalse(canvas.runtime_state.history_state.enabled)
        self.assertEqual(canvas.runtime_state.history_state.limit, 3)
        self.assertIs(canvas.runtime_state.history_state.change_callback, callback)

    def test_insert_fields_are_backed_by_state_holder(self) -> None:
        canvas = CanvasView()
        self.addCleanup(canvas.close)

        self.assertFalse(hasattr(canvas, "_insert_state"))
        self.assertIsInstance(insert_state_for(canvas), CanvasInsertState)
        self.assertIs(insert_state_for(canvas), canvas.runtime_state.insert_state)

        center = QPointF(1.0, 2.0)
        insert_state_for(canvas).smiles_active = True
        insert_state_for(canvas).smiles_preview_center = center
        insert_state_for(canvas).smiles_preview_smiles = "CCO"
        insert_state_for(canvas).template_active = True
        insert_state_for(canvas).template_ring_size = 6
        insert_state_for(canvas).template_ring_style = "chair"
        insert_state_for(canvas).template_preview_items = ["template"]

        self.assertTrue(canvas.runtime_state.insert_state.smiles_active)
        self.assertIs(canvas.runtime_state.insert_state.smiles_preview_center, center)
        self.assertEqual(canvas.runtime_state.insert_state.smiles_preview_smiles, "CCO")
        self.assertTrue(canvas.runtime_state.insert_state.template_active)
        self.assertEqual(canvas.runtime_state.insert_state.template_ring_size, 6)
        self.assertEqual(canvas.runtime_state.insert_state.template_ring_style, "chair")
        self.assertEqual(canvas.runtime_state.insert_state.template_preview_items, ["template"])

    def test_set_tool_and_mark_kind_cancel_pending_insert_modes(self) -> None:
        canvas = CanvasView()
        self.addCleanup(canvas.close)

        insert_state_for(canvas).template_active = True
        insert_state_for(canvas).template_ring_size = 5
        insert_state_for(canvas).template_ring_style = "regular"
        insert_state_for(canvas).smiles_active = True
        insert_state_for(canvas).smiles_preview_smiles = "CC"
        insert_state_for(canvas).smiles_preview_center = QPointF(1.0, 2.0)

        canvas_services_for(canvas).tool_mode_controller.set_tool("benzene")

        self.assertFalse(insert_state_for(canvas).template_active)
        self.assertIsNone(insert_state_for(canvas).template_ring_size)
        self.assertIsNone(insert_state_for(canvas).template_ring_style)
        self.assertFalse(insert_state_for(canvas).smiles_active)
        self.assertIsNone(insert_state_for(canvas).smiles_preview_smiles)
        self.assertIsNone(insert_state_for(canvas).smiles_preview_center)
        self.assertEqual(canvas.services.tools.active.name, "benzene")

        insert_state_for(canvas).template_active = True
        insert_state_for(canvas).template_ring_size = 6
        insert_state_for(canvas).template_ring_style = "benzene"

        canvas_services_for(canvas).tool_mode_controller.set_mark_kind("minus")

        self.assertFalse(insert_state_for(canvas).template_active)
        self.assertIsNone(insert_state_for(canvas).template_ring_size)
        self.assertIsNone(insert_state_for(canvas).template_ring_style)
        self.assertEqual(tool_settings_state_for(canvas).mark_kind, "minus")
        self.assertEqual(canvas.services.tools.active.name, "mark")

    def test_note_item_focus_out_adds_updates_and_deletes_commands(self) -> None:
        canvas = _FakeNoteCanvas()
        item = NoteItem(canvas)
        item.setPlainText("Mechanism")
        item.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))
        self.assertIsInstance(canvas.commands[-1], AddSceneItemsCommand)
        self.assertEqual(committed_note_text_for(item), "Mechanism")

        item.setPlainText("Mechanism 2")
        item.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))
        self.assertIsInstance(canvas.commands[-1], UpdateSceneItemCommand)
        self.assertEqual(committed_note_text_for(item), "Mechanism 2")

        item.setPlainText("")
        item.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))
        self.assertIsInstance(canvas.commands[-1], DeleteSceneItemsCommand)
        self.assertEqual(canvas.removed_items[-1], item)
        self.assertEqual(committed_note_text_for(item), "")

    def test_note_item_focus_out_removes_empty_untracked_note_and_selection_box(self) -> None:
        canvas = _FakeNoteCanvas()
        item = NoteItem(canvas)
        canvas.selected_notes.append(item)

        item.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))

        self.assertNotIn(item, canvas.selected_notes)
        self.assertEqual(canvas.updated_boxes, [item])
        self.assertEqual(canvas.removed_items, [item])

    def test_shortcut_modifiers_mask_meta_bits(self) -> None:
        mask_event = _FakeKeyEvent(
            Qt.Key.Key_H,
            Qt.KeyboardModifier.ShiftModifier
            | Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.MetaModifier,
        )
        self.assertEqual(
            shortcut_modifiers_for(mask_event),
            Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier,
        )

    def test_selection_helpers_and_geometry_helpers_cover_common_paths(self) -> None:
        self.assertTrue(selection_target_item(_FakeItem("atom")))
        self.assertFalse(selection_target_item(_FakeItem("handle")))

        fake_view = SimpleNamespace(model=SimpleNamespace(bonds=[Bond(0, 1, 1), None, Bond(1, 2, 2)]))
        self.assertEqual(selected_bond_atom_ids_for(fake_view, {0, 1, 2, 99}), ((0, 1), (1, 2)))

        scene = SimpleNamespace(selectedItems=lambda: (_FakeItem("atom", 1), _FakeItem("bond", 0), _FakeItem("handle"), _FakeItem("note")))
        snapshot_view = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(bonds=[Bond(1, 2, 1)]),
        )
        snapshot = selection_snapshot_for(snapshot_view)
        self.assertEqual(snapshot.selected_atom_ids, frozenset({1, 2}))
        self.assertEqual(len(snapshot.selection_items), 3)

        self.assertEqual((flip_point(QPointF(8.0, 4.0), QPointF(2.0, 1.0), True).x(), flip_point(QPointF(8.0, 4.0), QPointF(2.0, 1.0), True).y()), (-4.0, 4.0))
        self.assertEqual((flip_point(QPointF(8.0, 4.0), QPointF(2.0, 1.0), False).x(), flip_point(QPointF(8.0, 4.0), QPointF(2.0, 1.0), False).y()), (8.0, -2.0))
        self.assertIsNone(bounds_from_points([]))
        bounds = bounds_from_points([QPointF(-2.0, 3.0), QPointF(4.0, -1.0)])
        self.assertEqual((bounds.left(), bounds.top(), bounds.right(), bounds.bottom()), (-2.0, -1.0, 4.0, 3.0))

    def test_structure_selection_and_payload_helpers_cover_selected_and_empty_cases(self) -> None:
        selected_item = SimpleNamespace(isSelected=lambda: True)
        selection_controller = mock.Mock()
        selection_controller.structure_hit_from_item.side_effect = [
            (SimpleNamespace(kind="atom", id=1), None, ()),
            (SimpleNamespace(kind="bond", id=9), (1, 2), ()),
            (SimpleNamespace(kind="ring", id=5), None, (7, 8)),
            (SimpleNamespace(kind="other", id=None), None, ()),
            (None, None, ()),
        ]
        view = SimpleNamespace(services=SimpleNamespace(selection_controller=selection_controller))

        self.assertTrue(structure_item_is_selected_for(view, selected_item, {1}, set()))
        self.assertTrue(structure_item_is_selected_for(view, selected_item, {1}, set()))
        self.assertTrue(structure_item_is_selected_for(view, selected_item, {7}, set()))
        self.assertTrue(structure_item_is_selected_for(view, selected_item, set(), set()))
        self.assertFalse(structure_item_is_selected_for(view, None, set(), set()))

        selected_scene = SimpleNamespace(selectedItems=lambda: (_FakeItem("atom", 3), _FakeItem("bond", 4)))
        selected_ids_view = SimpleNamespace(scene=lambda: selected_scene)
        self.assertEqual(selected_structure_ids_for(selected_ids_view), ({3}, {4}))
        with self.assertRaisesRegex(ValueError, "Select a molecular structure"):
            selected_structure_ids_for(
                SimpleNamespace(),
                require_non_empty=True,
            )

        selected_payload_scene = SimpleNamespace(selectedItems=lambda: (_FakeItem("atom", 5), _FakeItem("bond", 6)))
        selected_payload_view = SimpleNamespace(
            scene=lambda: selected_payload_scene,
            model=SimpleNamespace(atoms={}, bonds=[]),
        )
        with mock.patch(
            "ui.structure_payload_access.build_structure_payload_state",
            return_value=("payload", {}, (0.0, 0.0, 1.0, 1.0)),
        ) as build_structure:
            self.assertEqual(
                build_selected_structure_payload_for(selected_payload_view),
                ("payload", {}, (0.0, 0.0, 1.0, 1.0)),
            )
        build_structure.assert_called_once()
        self.assertEqual(build_structure.call_args.args, (selected_payload_view.model, {5}, {6}, {}))

        payload_view = SimpleNamespace()
        with mock.patch(
            "ui.structure_payload_access.build_3d_conversion_payload_state",
            return_value=("export", {"a": 1}),
        ) as build_3d:
            payload_view.model = "model"
            payload_scene = SimpleNamespace(selectedItems=lambda: (_FakeItem("atom", 1), _FakeItem("bond", 2)))
            payload_view.scene = lambda: payload_scene
            self.assertEqual(build_3d_conversion_payload_for(payload_view), ("export", {"a": 1}))
        build_3d.assert_called_once()
        self.assertEqual(build_3d.call_args.args, ("model", {1}, {2}, {}))

        structure_payload_model = SimpleNamespace(
            atoms={9: Atom("C", 4.0, 5.0)},
            bounds=mock.Mock(return_value=(4.0, 5.0, 4.0, 5.0)),
        )
        structure_payload_view = SimpleNamespace(
            model=structure_payload_model,
            mark_registry=CanvasMarkRegistry({9: [_FakeItem("mark", {"kind": "minus"})]}),
        )
        with mock.patch(
            "ui.structure_payload_access.build_structure_payload_state",
            return_value=("export", {"b": 2}, (1.0, 2.0, 3.0, 4.0)),
        ) as build_structure:
            self.assertEqual(
                build_structure_payload_for(structure_payload_view, {9}, {10}),
                ("export", {"b": 2}, (1.0, 2.0, 3.0, 4.0)),
            )
        build_structure.assert_called_once()
        self.assertEqual(build_structure.call_args.args, (structure_payload_model, {9}, {10}, {9: ["minus"]}))
        bounds_getter = build_structure.call_args.kwargs["bounds_getter"]
        self.assertEqual(bounds_getter({9}, include_labels=True), (4.0, 5.0, 4.0, 5.0))

    def test_translation_helpers_compact_labels_and_selection_overlay_values(self) -> None:
        self.assertEqual(translated_point_value((1, 2), 3.0, -4.0), (4.0, -2.0))
        self.assertEqual(translated_point_value("bad", 3.0, -4.0), "bad")

        ring_state = translated_scene_item_state(
            {"kind": "ring", "atom_ids": [1, 2], "points": [(0.0, 0.0), (1.0, 2.0)]},
            dx=2.0,
            dy=3.0,
            atom_id_map={1: 10, 2: 20},
        )
        self.assertEqual(ring_state["atom_ids"], [10, 20])
        self.assertEqual(ring_state["points"], [(2.0, 3.0), (3.0, 5.0)])
        self.assertIsNone(
            translated_scene_item_state(
                {"kind": "ring", "atom_ids": [1, "bad"], "points": []},
                dx=0.0,
                dy=0.0,
                atom_id_map={1: 10},
            )
        )
        self.assertEqual(
            translated_scene_item_state(
                {"kind": "mark", "atom_id": 1, "x": 2.0, "y": 3.0},
                dx=4.0,
                dy=-1.0,
                atom_id_map={1: 9},
            ),
            {"kind": "mark", "atom_id": 9, "x": 6.0, "y": 2.0},
        )
        self.assertEqual(
            translated_scene_item_state(
                {"kind": "orbital", "center": (1.0, 2.0)},
                dx=5.0,
                dy=6.0,
                atom_id_map={},
            ),
            {"kind": "orbital", "center": (6.0, 8.0)},
        )
        self.assertEqual(
            translated_scene_item_state(
                {"kind": "ts_bracket", "left": 1.0, "right": 3.0, "top": 2.0, "bottom": 4.0},
                dx=2.0,
                dy=-1.0,
                atom_id_map={},
            ),
            {"kind": "ts_bracket", "left": 3.0, "right": 5.0, "top": 1.0, "bottom": 3.0},
        )
        self.assertIsNone(
            translated_scene_item_state(
                {"kind": "ring", "atom_ids": [], "points": []},
                dx=0.0,
                dy=0.0,
                atom_id_map={},
            )
        )
        self.assertEqual(
            translated_scene_item_state(
                {"kind": "ring", "atom_ids": [1], "points": ["bad", (1.0, 2.0)]},
                dx=2.0,
                dy=3.0,
                atom_id_map={1: 5},
            ),
            {"kind": "ring", "atom_ids": [5], "points": [(3.0, 5.0)]},
        )
        self.assertEqual(
            translated_scene_item_state(
                {"kind": "mark", "atom_id": 1, "x": 2.0},
                dx=4.0,
                dy=-1.0,
                atom_id_map={1: 9},
            ),
            {"kind": "mark", "atom_id": 9, "x": 6.0},
        )
        self.assertEqual(
            translated_scene_item_state(
                {"kind": "mark", "atom_id": 1, "y": 3.0},
                dx=4.0,
                dy=-1.0,
                atom_id_map={1: 9},
            ),
            {"kind": "mark", "atom_id": 9, "y": 2.0},
        )
        self.assertEqual(
            translated_scene_item_state(
                {"kind": "note", "x": 1.0, "y": 2.0},
                dx=5.0,
                dy=6.0,
                atom_id_map={},
            ),
            {"kind": "note", "x": 6.0, "y": 8.0},
        )
        self.assertEqual(
            translated_scene_item_state(
                {"kind": "ts_bracket", "left": "bad", "right": 3.0, "top": "bad", "bottom": 4.0},
                dx=2.0,
                dy=-1.0,
                atom_id_map={},
            ),
            {"kind": "ts_bracket", "left": "bad", "right": 5.0, "top": "bad", "bottom": 3.0},
        )
        self.assertEqual(
            translated_scene_item_state(
                {"kind": "other", "value": 1},
                dx=1.0,
                dy=1.0,
                atom_id_map={},
            ),
            {"kind": "other", "value": 1},
        )
        self.assertIsNone(translated_scene_item_state("bad", dx=0.0, dy=0.0, atom_id_map={}))

        self.assertTrue(uses_compact_label_hit_shape_for(SimpleNamespace(), "C"))
        self.assertTrue(uses_compact_label_hit_shape_for(SimpleNamespace(), "Cl"))
        self.assertFalse(uses_compact_label_hit_shape_for(SimpleNamespace(), "CH3"))
        self.assertEqual(implicit_carbon_dot_brush_for(SimpleNamespace()).alpha(), 0)
        self.assertEqual(clipboard_paste_offset(2, 20.0), (36.0, 36.0))
        self.assertEqual(selection_signature_for({1, 2}, {3}), (frozenset({1, 2}), frozenset({3})))

    def test_structure_payload_logic_helpers_cover_selection_expansion_and_annotations(self) -> None:
        model = SimpleNamespace(bonds=[Bond(1, 2, 1), None])
        self.assertEqual(expand_atom_ids_for_structure(model, {1}, {0, 99}), {1, 2})
        self.assertEqual(build_atom_annotations({5}, {5: 9}, {5: ["plus"]}), {9: {"formal_charge": 1}})

    def test_selection_indicator_overlay_width_and_segment_distance(self) -> None:
        fake_view = SimpleNamespace(
            renderer=SimpleNamespace(
                style=SimpleNamespace(bond_spacing_px=4.0, bond_line_width=1.0, bond_length_px=15.625)
            ),
            model=SimpleNamespace(atoms={1: Atom("C", 7.0, -2.0)}),
        )
        pen = QPen()
        pen.setWidthF(1.5)
        self.assertEqual(selection_bond_overlay_width_for(fake_view, pen), 5.7)

        rect = selection_indicator_rect_for_atom_for(fake_view, 1)
        self.assertEqual((rect.left(), rect.top(), rect.right(), rect.bottom()), (2.0, -7.0, 12.0, 3.0))
        self.assertIsNone(selection_indicator_rect_for_atom_for(fake_view, 99))

        self.assertAlmostEqual(
            CanvasHitTestingService.distance_point_to_segment(
                QPointF(5.0, 5.0),
                QPointF(0.0, 0.0),
                QPointF(10.0, 0.0),
            ),
            5.0,
        )
        self.assertAlmostEqual(
            CanvasHitTestingService.distance_point_to_segment(
                QPointF(5.0, 5.0),
                QPointF(0.0, 0.0),
                QPointF(0.0, 0.0),
            ),
            7.0710678118654755,
        )

    def test_bond_hotkey_visible_label_and_atom_point_helpers(self) -> None:
        fake_view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 1.0, 2.0),
                    2: Atom("O", 4.0, 5.0),
                },
                bonds=[Bond(1, 2, 1), None],
            ),
        )
        set_atom_items_for(fake_view, {1: object()})

        self.assertTrue(atom_has_visible_label_for(fake_view, 1))
        set_atom_items_for(fake_view, {})
        self.assertFalse(atom_has_visible_label_for(fake_view, 1))
        self.assertTrue(atom_has_visible_label_for(fake_view, 2))
        self.assertFalse(atom_has_visible_label_for(fake_view, 99))
        self.assertEqual((atom_point_for(fake_view, 2).x(), atom_point_for(fake_view, 2).y()), (4.0, 5.0))

    def test_sprout_bond_endpoint_handles_default_and_cyclic_cases(self) -> None:
        fake_view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 10.0, 0.0),
                    3: Atom("C", 0.0, 10.0),
                },
                bonds=[],
            ),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
        )

        self.assertIsNone(sprout_bond_endpoint_for(fake_view, 99))
        endpoint = sprout_bond_endpoint_for(fake_view, 1, cyclic=False)
        assert endpoint is not None
        self.assertEqual((endpoint.x(), endpoint.y()), (20.0, 0.0))

        fake_view.model.bonds = [Bond(1, 2, 1)]
        one_neighbor = sprout_bond_endpoint_for(fake_view, 1, cyclic=True)
        assert one_neighbor is not None
        self.assertAlmostEqual(one_neighbor.x(), -10.0)
        self.assertAlmostEqual(one_neighbor.y(), 17.320508075688775)

        fake_view.model.bonds = [Bond(1, 2, 1), Bond(1, 3, 1)]
        two_neighbors = sprout_bond_endpoint_for(fake_view, 1, cyclic=True)
        assert two_neighbors is not None
        self.assertAlmostEqual(two_neighbors.x(), -10.0)
        self.assertAlmostEqual(two_neighbors.y(), -17.32050807568877)

    def test_structure_geometry_wrappers_convert_pure_logic_results(self) -> None:
        fake_view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 10.0, 0.0),
                },
                bonds=[Bond(1, 2, 1)],
            ),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
        )

        with (
            mock.patch("ui.structure_geometry_access.compute_sprout_bond_endpoint", return_value=(7.0, 8.0)) as sprout,
            mock.patch(
                "ui.structure_geometry_access.ring_polygon_points_for_bond",
                return_value=[(0.0, 0.0), (1.0, 1.0)],
            ),
            mock.patch(
                "ui.structure_geometry_access.compute_regular_ring_points_for_atom",
                return_value=([(1.0, 2.0)], [(1, 0.0, 0.0)]),
            ) as atom_ring,
            mock.patch(
                "ui.structure_geometry_access.compute_regular_ring_points_for_bond",
                return_value=([(3.0, 4.0)], [(1, 0.0, 0.0), (2, 10.0, 0.0)]),
            ) as bond_ring,
            mock.patch(
                "ui.structure_geometry_access.compute_template_points_for_bond",
                return_value=([(5.0, 6.0)], [(1, 0.0, 0.0), (2, 10.0, 0.0)]),
            ) as template,
        ):
            endpoint = sprout_bond_endpoint_for(fake_view, 1, cyclic=False)
            atom_result = regular_ring_points_for_atom_for(fake_view, 6, 1)
            bond_result = regular_ring_points_for_bond_for(fake_view, 6, 0, QPointF(9.0, 10.0))
            template_result = template_points_for_bond_for(
                fake_view,
                [QPointF(1.0, 1.0), QPointF(2.0, 2.0)],
                0,
                QPointF(11.0, 12.0),
            )

        self.assertEqual((endpoint.x(), endpoint.y()), (7.0, 8.0))
        assert atom_result is not None
        assert bond_result is not None
        assert template_result is not None
        self.assertEqual((atom_result[0][0].x(), atom_result[0][0].y()), (1.0, 2.0))
        self.assertEqual((bond_result[0][0].x(), bond_result[0][0].y()), (3.0, 4.0))
        self.assertEqual((template_result[0][0].x(), template_result[0][0].y()), (5.0, 6.0))
        sprout.assert_called_once()
        self.assertEqual(sprout.call_args.args, (1,))
        self.assertIs(sprout.call_args.kwargs["atoms"], fake_view.model.atoms)
        self.assertIs(sprout.call_args.kwargs["bonds"], fake_view.model.bonds)
        self.assertEqual(sprout.call_args.kwargs["bond_length"], 20.0)
        self.assertFalse(sprout.call_args.kwargs["cyclic"])
        default_endpoint = sprout.call_args.kwargs["default_endpoint"]
        self.assertAlmostEqual(default_endpoint[0], -10.0)
        self.assertAlmostEqual(default_endpoint[1], -17.320508075688775)
        atom_ring.assert_called_once_with(
            6,
            1,
            atoms=fake_view.model.atoms,
            bonds=fake_view.model.bonds,
            bond_length=20.0,
        )
        bond_ring.assert_called_once_with(
            6,
            0,
            atoms=fake_view.model.atoms,
            bonds=fake_view.model.bonds,
            center_hint=(9.0, 10.0),
            occupied_polygon=[(0.0, 0.0), (1.0, 1.0)],
        )
        template.assert_called_once_with(
            [(1.0, 1.0), (2.0, 2.0)],
            0,
            atoms=fake_view.model.atoms,
            bonds=fake_view.model.bonds,
            center_hint=(11.0, 12.0),
            occupied_polygon=[(0.0, 0.0), (1.0, 1.0)],
        )

    def test_regular_ring_points_for_atom_wrapper_returns_none_when_logic_fails(self) -> None:
        fake_view = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0)}, bonds=[]),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
        )

        with mock.patch("ui.structure_geometry_access.compute_regular_ring_points_for_atom", return_value=None):
            self.assertIsNone(regular_ring_points_for_atom_for(fake_view, 6, 1))

    def test_ring_polygon_points_for_bond_wrapper_delegates_to_occupancy_helper(self) -> None:
        fake_view = SimpleNamespace(
            model=SimpleNamespace(bonds=[Bond(1, 2, 1)]),
        )
        set_scene_item_collection_for(fake_view, "ring_items", ["ring"])

        with mock.patch(
            "ui.structure_geometry_access.ring_polygon_points_for_bond",
            return_value=[(1.0, 2.0), (3.0, 4.0)],
        ) as occupancy:
            result = ring_polygon_points_for_bond_for(fake_view, 0)

        self.assertEqual(result, [(1.0, 2.0), (3.0, 4.0)])
        occupancy.assert_called_once_with(
            0,
            bonds=fake_view.model.bonds,
            ring_items=ring_items_for(fake_view),
        )


if __name__ == "__main__":
    unittest.main()
