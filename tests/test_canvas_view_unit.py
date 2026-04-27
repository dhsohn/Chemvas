import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QColor, QFocusEvent, QPen
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.history import AddSceneItemsCommand, DeleteSceneItemsCommand, UpdateSceneItemCommand
    from core.model import Atom, Bond
    from ui.canvas_rotation_preview_controller import CanvasRotationPreviewController
    from ui.canvas_view import CanvasView, NoteItem, _rotation_preview_controller_for, _selection_controller_for
    from ui.selection_controller import SelectionController


class _FakeNoteCanvas:
    def __init__(self) -> None:
        self.commands = []
        self.removed_items = []
        self.selected_notes = []
        self.updated_boxes = []

    def _note_state_dict(self, item) -> dict:
        return {
            "kind": "note",
            "text": item.toPlainText(),
            "x": item.pos().x(),
            "y": item.pos().y(),
        }

    def _push_command(self, command) -> None:
        self.commands.append(command)

    def remove_scene_item(self, item) -> None:
        self.removed_items.append(item)

    def _update_note_selection_box(self, item) -> None:
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
    def __init__(self, kind) -> None:
        self.kind = kind

    def data(self, key):
        if key == 0:
            return self.kind
        return None


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_canvas_background_defaults_to_white(self) -> None:
        canvas = CanvasView()
        self.addCleanup(canvas.close)

        self.assertEqual(canvas.backgroundBrush().color(), QColor("#ffffff"))

    def test_canvas_defaults_to_a4_landscape_sheet_and_can_switch_portrait(self) -> None:
        canvas = CanvasView()
        self.addCleanup(canvas.close)

        self.assertEqual(canvas.sheet_size, "A4")
        self.assertEqual(canvas.sheet_orientation, "landscape")
        self.assertAlmostEqual(canvas.sheet_rect().width(), 842.0)
        self.assertAlmostEqual(canvas.sheet_rect().height(), 595.0)
        self.assertAlmostEqual(canvas.sceneRect().width(), 1002.0)
        self.assertAlmostEqual(canvas.sceneRect().height(), 755.0)

        canvas.set_sheet_setup("A4", "portrait")

        self.assertEqual(canvas.sheet_orientation, "portrait")
        self.assertAlmostEqual(canvas.sheet_rect().width(), 595.0)
        self.assertAlmostEqual(canvas.sheet_rect().height(), 842.0)
        self.assertAlmostEqual(canvas.sceneRect().width(), 755.0)
        self.assertAlmostEqual(canvas.sceneRect().height(), 1002.0)

    def test_note_item_focus_out_adds_updates_and_deletes_commands(self) -> None:
        canvas = _FakeNoteCanvas()
        item = NoteItem(canvas)
        item.setPlainText("Mechanism")
        item.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))
        self.assertIsInstance(canvas.commands[-1], AddSceneItemsCommand)
        self.assertEqual(item._last_text, "Mechanism")

        item.setPlainText("Mechanism 2")
        item.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))
        self.assertIsInstance(canvas.commands[-1], UpdateSceneItemCommand)
        self.assertEqual(item._last_text, "Mechanism 2")

        item.setPlainText("")
        item.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))
        self.assertIsInstance(canvas.commands[-1], DeleteSceneItemsCommand)
        self.assertEqual(canvas.removed_items[-1], item)
        self.assertEqual(item._last_text, "")

    def test_note_item_focus_out_removes_empty_untracked_note_and_selection_box(self) -> None:
        canvas = _FakeNoteCanvas()
        item = NoteItem(canvas)
        canvas.selected_notes.append(item)

        item.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))

        self.assertNotIn(item, canvas.selected_notes)
        self.assertEqual(canvas.updated_boxes, [item])
        self.assertEqual(canvas.removed_items, [item])

    def test_controller_helper_wrappers_reuse_matching_instances_and_recreate_foreign_bound_ones(self) -> None:
        canvas = SimpleNamespace()

        same_selection_controller = SelectionController(canvas)
        canvas._selection_controller = same_selection_controller
        self.assertIs(_selection_controller_for(canvas), same_selection_controller)

        foreign_selection_controller = SelectionController(SimpleNamespace())
        canvas._selection_controller = foreign_selection_controller
        rebound_selection_controller = _selection_controller_for(canvas)
        self.assertIsInstance(rebound_selection_controller, SelectionController)
        self.assertIsNot(rebound_selection_controller, foreign_selection_controller)
        self.assertIs(rebound_selection_controller.canvas, canvas)

        passthrough_controller = object()
        canvas._selection_controller = passthrough_controller
        self.assertIs(_selection_controller_for(canvas), passthrough_controller)

        same_rotation_controller = CanvasRotationPreviewController(canvas)
        canvas._rotation_preview_controller = same_rotation_controller
        self.assertIs(_rotation_preview_controller_for(canvas), same_rotation_controller)

        foreign_rotation_controller = CanvasRotationPreviewController(SimpleNamespace())
        canvas._rotation_preview_controller = foreign_rotation_controller
        rebound_rotation_controller = _rotation_preview_controller_for(canvas)
        self.assertIsInstance(rebound_rotation_controller, CanvasRotationPreviewController)
        self.assertIsNot(rebound_rotation_controller, foreign_rotation_controller)
        self.assertIs(rebound_rotation_controller.canvas, canvas)

    def test_shortcut_modifiers_mask_meta_bits(self) -> None:
        mask_event = _FakeKeyEvent(
            Qt.Key.Key_H,
            Qt.KeyboardModifier.ShiftModifier
            | Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.MetaModifier,
        )
        self.assertEqual(
            CanvasView._shortcut_modifiers(mask_event),
            Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier,
        )

    def test_chemdraw_shortcut_wrappers_delegate_to_service(self) -> None:
        service = mock.Mock()
        view = SimpleNamespace(_chemdraw_shortcut_service=service)
        event = _FakeKeyEvent(Qt.Key.Key_C, text="c")

        service.handle_shortcut.return_value = True
        service.handle_object_shortcut.return_value = True
        service.handle_generic_hotkey.return_value = True
        service.handle_atom_hotkey.return_value = True
        service.handle_bond_hotkey.return_value = True

        self.assertTrue(CanvasView._handle_chemdraw_shortcut(view, event))
        self.assertTrue(CanvasView._handle_chemdraw_object_shortcut(view, event))
        self.assertTrue(CanvasView._handle_chemdraw_generic_hotkey(view, event))
        self.assertTrue(CanvasView._handle_chemdraw_atom_hotkey(view, event, 4))
        self.assertTrue(CanvasView._handle_chemdraw_bond_hotkey(view, event, 7))

        service.handle_shortcut.assert_called_once_with(event)
        service.handle_object_shortcut.assert_called_once_with(event)
        service.handle_generic_hotkey.assert_called_once_with(event)
        service.handle_atom_hotkey.assert_called_once_with(event, 4)
        service.handle_bond_hotkey.assert_called_once_with(event, 7)

    def test_selection_helpers_and_geometry_helpers_cover_common_paths(self) -> None:
        self.assertTrue(CanvasView._selection_target_item(_FakeItem("atom")))
        self.assertFalse(CanvasView._selection_target_item(_FakeItem("handle")))

        fake_view = SimpleNamespace(model=SimpleNamespace(bonds=[Bond(0, 1, 1), None, Bond(1, 2, 2)]))
        self.assertEqual(CanvasView._selected_bond_atom_ids(fake_view, {0, 1, 2, 99}), ((0, 1), (1, 2)))

        scene = SimpleNamespace(selectedItems=lambda: (_FakeItem("atom"), _FakeItem("handle"), _FakeItem("note")))
        snapshot_view = SimpleNamespace(
            scene=lambda: scene,
            _selected_ids=lambda: ({1}, {0}),
            _selected_bond_atom_ids=lambda bond_ids: ((1, 2),),
            _selection_target_item=CanvasView._selection_target_item,
        )
        snapshot = CanvasView._selection_snapshot(snapshot_view)
        self.assertEqual(snapshot.selected_atom_ids, frozenset({1, 2}))
        self.assertEqual(len(snapshot.selection_items), 2)

        self.assertEqual((CanvasView._flip_point(QPointF(8.0, 4.0), QPointF(2.0, 1.0), True).x(), CanvasView._flip_point(QPointF(8.0, 4.0), QPointF(2.0, 1.0), True).y()), (-4.0, 4.0))
        self.assertEqual((CanvasView._flip_point(QPointF(8.0, 4.0), QPointF(2.0, 1.0), False).x(), CanvasView._flip_point(QPointF(8.0, 4.0), QPointF(2.0, 1.0), False).y()), (8.0, -2.0))
        self.assertIsNone(CanvasView._bounds_from_points([]))
        bounds = CanvasView._bounds_from_points([QPointF(-2.0, 3.0), QPointF(4.0, -1.0)])
        self.assertEqual((bounds.left(), bounds.top(), bounds.right(), bounds.bottom()), (-2.0, -1.0, 4.0, 3.0))

    def test_structure_selection_and_payload_helpers_cover_selected_and_empty_cases(self) -> None:
        selected_item = SimpleNamespace(isSelected=lambda: True)
        view = SimpleNamespace(
            _structure_hit_from_item=mock.Mock(
                side_effect=[
                    (SimpleNamespace(kind="atom", id=1), None, ()),
                    (SimpleNamespace(kind="bond", id=9), (1, 2), ()),
                    (SimpleNamespace(kind="ring", id=5), None, (7, 8)),
                    (SimpleNamespace(kind="other", id=None), None, ()),
                    (None, None, ()),
                ]
            ),
        )

        self.assertTrue(CanvasView.structure_item_is_selected(view, selected_item, {1}, set()))
        self.assertTrue(CanvasView.structure_item_is_selected(view, selected_item, {1}, set()))
        self.assertTrue(CanvasView.structure_item_is_selected(view, selected_item, {7}, set()))
        self.assertTrue(CanvasView.structure_item_is_selected(view, selected_item, set(), set()))
        self.assertFalse(CanvasView.structure_item_is_selected(view, None, set(), set()))

        selected_ids_view = SimpleNamespace(_selected_chemical_ids=mock.Mock(return_value=({3}, {4})))
        self.assertEqual(CanvasView._selected_structure_ids(selected_ids_view), ({3}, {4}))
        with self.assertRaisesRegex(ValueError, "Select a molecular structure"):
            CanvasView._selected_structure_ids(
                SimpleNamespace(_selected_chemical_ids=mock.Mock(return_value=(set(), set()))),
                require_non_empty=True,
            )

        selected_payload_view = SimpleNamespace(
            _selected_chemical_ids=mock.Mock(return_value=({5}, {6})),
            build_structure_payload=mock.Mock(return_value=("payload", {}, (0.0, 0.0, 1.0, 1.0))),
        )
        selected_payload_view._selected_structure_ids = lambda require_non_empty=False: CanvasView._selected_structure_ids(
            selected_payload_view,
            require_non_empty=require_non_empty,
        )
        self.assertEqual(
            CanvasView.build_selected_structure_payload(selected_payload_view),
            ("payload", {}, (0.0, 0.0, 1.0, 1.0)),
        )
        selected_payload_view.build_structure_payload.assert_called_once_with({5}, {6})

        payload_view = SimpleNamespace(
            model="model",
            _selected_structure_ids=mock.Mock(return_value=({7}, {8})),
            _mark_kinds_by_atom=mock.Mock(return_value={7: ["plus"]}),
            _bounds_for_atoms=mock.Mock(),
        )
        with mock.patch("ui.canvas_view.build_3d_conversion_payload_state", return_value=("export", {"a": 1})) as build_3d:
            self.assertEqual(CanvasView.build_3d_conversion_payload(payload_view), ("export", {"a": 1}))
        build_3d.assert_called_once_with(
            "model",
            {7},
            {8},
            {7: ["plus"]},
            bounds_getter=payload_view._bounds_for_atoms,
        )

        structure_payload_view = SimpleNamespace(
            model="model",
            _mark_kinds_by_atom=mock.Mock(return_value={9: ["minus"]}),
            _bounds_for_atoms=mock.Mock(),
        )
        with mock.patch(
            "ui.canvas_view.build_structure_payload_state",
            return_value=("export", {"b": 2}, (1.0, 2.0, 3.0, 4.0)),
        ) as build_structure:
            self.assertEqual(
                CanvasView.build_structure_payload(structure_payload_view, {9}, {10}),
                ("export", {"b": 2}, (1.0, 2.0, 3.0, 4.0)),
            )
        build_structure.assert_called_once_with(
            "model",
            {9},
            {10},
            {9: ["minus"]},
            bounds_getter=structure_payload_view._bounds_for_atoms,
        )

    def test_translation_helpers_compact_labels_and_selection_overlay_values(self) -> None:
        fake_view = SimpleNamespace(
            _translated_point_value=lambda value, dx, dy: CanvasView._translated_point_value(value, dx, dy),
        )
        self.assertEqual(CanvasView._translated_point_value((1, 2), 3.0, -4.0), (4.0, -2.0))
        self.assertEqual(CanvasView._translated_point_value("bad", 3.0, -4.0), "bad")

        ring_state = CanvasView._translated_scene_item_state(
            fake_view,
            {"kind": "ring", "atom_ids": [1, 2], "points": [(0.0, 0.0), (1.0, 2.0)]},
            dx=2.0,
            dy=3.0,
            atom_id_map={1: 10, 2: 20},
        )
        self.assertEqual(ring_state["atom_ids"], [10, 20])
        self.assertEqual(ring_state["points"], [(2.0, 3.0), (3.0, 5.0)])
        self.assertIsNone(
            CanvasView._translated_scene_item_state(
                fake_view,
                {"kind": "ring", "atom_ids": [1, "bad"], "points": []},
                dx=0.0,
                dy=0.0,
                atom_id_map={1: 10},
            )
        )
        self.assertEqual(
            CanvasView._translated_scene_item_state(
                fake_view,
                {"kind": "mark", "atom_id": 1, "x": 2.0, "y": 3.0},
                dx=4.0,
                dy=-1.0,
                atom_id_map={1: 9},
            ),
            {"kind": "mark", "atom_id": 9, "x": 6.0, "y": 2.0},
        )
        self.assertEqual(
            CanvasView._translated_scene_item_state(
                fake_view,
                {"kind": "orbital", "center": (1.0, 2.0)},
                dx=5.0,
                dy=6.0,
                atom_id_map={},
            ),
            {"kind": "orbital", "center": (6.0, 8.0)},
        )
        self.assertEqual(
            CanvasView._translated_scene_item_state(
                fake_view,
                {"kind": "ts_bracket", "left": 1.0, "right": 3.0, "top": 2.0, "bottom": 4.0},
                dx=2.0,
                dy=-1.0,
                atom_id_map={},
            ),
            {"kind": "ts_bracket", "left": 3.0, "right": 5.0, "top": 1.0, "bottom": 3.0},
        )
        self.assertIsNone(
            CanvasView._translated_scene_item_state(
                fake_view,
                {"kind": "ring", "atom_ids": [], "points": []},
                dx=0.0,
                dy=0.0,
                atom_id_map={},
            )
        )
        self.assertEqual(
            CanvasView._translated_scene_item_state(
                fake_view,
                {"kind": "ring", "atom_ids": [1], "points": ["bad", (1.0, 2.0)]},
                dx=2.0,
                dy=3.0,
                atom_id_map={1: 5},
            ),
            {"kind": "ring", "atom_ids": [5], "points": [(3.0, 5.0)]},
        )
        self.assertEqual(
            CanvasView._translated_scene_item_state(
                fake_view,
                {"kind": "mark", "atom_id": 1, "x": 2.0},
                dx=4.0,
                dy=-1.0,
                atom_id_map={1: 9},
            ),
            {"kind": "mark", "atom_id": 9, "x": 6.0},
        )
        self.assertEqual(
            CanvasView._translated_scene_item_state(
                fake_view,
                {"kind": "mark", "atom_id": 1, "y": 3.0},
                dx=4.0,
                dy=-1.0,
                atom_id_map={1: 9},
            ),
            {"kind": "mark", "atom_id": 9, "y": 2.0},
        )
        self.assertEqual(
            CanvasView._translated_scene_item_state(
                fake_view,
                {"kind": "note", "x": 1.0, "y": 2.0},
                dx=5.0,
                dy=6.0,
                atom_id_map={},
            ),
            {"kind": "note", "x": 6.0, "y": 8.0},
        )
        self.assertEqual(
            CanvasView._translated_scene_item_state(
                fake_view,
                {"kind": "ts_bracket", "left": "bad", "right": 3.0, "top": "bad", "bottom": 4.0},
                dx=2.0,
                dy=-1.0,
                atom_id_map={},
            ),
            {"kind": "ts_bracket", "left": "bad", "right": 5.0, "top": "bad", "bottom": 3.0},
        )
        self.assertEqual(
            CanvasView._translated_scene_item_state(
                fake_view,
                {"kind": "other", "value": 1},
                dx=1.0,
                dy=1.0,
                atom_id_map={},
            ),
            {"kind": "other", "value": 1},
        )
        self.assertIsNone(CanvasView._translated_scene_item_state(fake_view, "bad", dx=0.0, dy=0.0, atom_id_map={}))

        self.assertTrue(CanvasView._uses_compact_label_hit_shape("C"))
        self.assertTrue(CanvasView._uses_compact_label_hit_shape("Cl"))
        self.assertFalse(CanvasView._uses_compact_label_hit_shape("CH3"))
        self.assertEqual(CanvasView._implicit_carbon_dot_brush().alpha(), 0)
        self.assertEqual(CanvasView._clipboard_paste_offset(2, 20.0), (36.0, 36.0))
        self.assertEqual(CanvasView._selection_signature_for({1, 2}, {3}), (frozenset({1, 2}), frozenset({3})))

    def test_wrapper_helpers_delegate_to_state_and_structure_builders(self) -> None:
        with mock.patch("ui.canvas_view.ts_bracket_rect_from_state_helper", return_value="rect") as rect_helper:
            self.assertEqual(CanvasView._ts_bracket_rect_from_state(SimpleNamespace(), {"kind": "ts_bracket"}), "rect")
        rect_helper.assert_called_once_with({"kind": "ts_bracket"})

        with mock.patch("ui.canvas_view.expand_atom_ids_for_structure_state", return_value={1, 2, 3}) as expand_atom_ids:
            self.assertEqual(
                CanvasView._expanded_atom_ids_for_structure(SimpleNamespace(model="model"), {1}, {7}),
                {1, 2, 3},
            )
        expand_atom_ids.assert_called_once_with("model", {1}, {7})

        with mock.patch("ui.canvas_view.build_atom_annotations_state", return_value={5: {"plus": 1}}) as build_annotations:
            view = SimpleNamespace(_mark_kinds_by_atom=mock.Mock(return_value={5: ["plus"]}))
            self.assertEqual(CanvasView._build_atom_annotations(view, {5}, {5: 9}), {5: {"plus": 1}})
        build_annotations.assert_called_once_with({5}, {5: 9}, {5: ["plus"]})

    def test_selection_indicator_overlay_width_and_segment_distance(self) -> None:
        fake_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_spacing_px=4.0)),
            _atom_pick_radius=lambda: 5.0,
            model=SimpleNamespace(atoms={1: Atom("C", 7.0, -2.0)}),
        )
        pen = QPen()
        pen.setWidthF(1.5)
        self.assertEqual(CanvasView._selection_bond_overlay_width(fake_view, pen), 5.7)

        rect = CanvasView._selection_indicator_rect_for_atom(fake_view, 1)
        self.assertEqual((rect.left(), rect.top(), rect.right(), rect.bottom()), (2.0, -7.0, 12.0, 3.0))
        self.assertIsNone(CanvasView._selection_indicator_rect_for_atom(fake_view, 99))

        self.assertAlmostEqual(
            CanvasView._distance_point_to_segment(QPointF(5.0, 5.0), QPointF(0.0, 0.0), QPointF(10.0, 0.0)),
            5.0,
        )
        self.assertAlmostEqual(
            CanvasView._distance_point_to_segment(QPointF(5.0, 5.0), QPointF(0.0, 0.0), QPointF(0.0, 0.0)),
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
            atom_items={1: object()},
        )

        self.assertTrue(CanvasView._atom_has_visible_label(fake_view, 1))
        fake_view.atom_items = {}
        self.assertFalse(CanvasView._atom_has_visible_label(fake_view, 1))
        self.assertTrue(CanvasView._atom_has_visible_label(fake_view, 2))
        self.assertFalse(CanvasView._atom_has_visible_label(fake_view, 99))
        self.assertEqual((CanvasView._atom_point(fake_view, 2).x(), CanvasView._atom_point(fake_view, 2).y()), (4.0, 5.0))

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
            _default_bond_endpoint=lambda start, atom_id: QPointF(5.0, 5.0),
        )

        self.assertIsNone(CanvasView._sprout_bond_endpoint(fake_view, 99))
        self.assertEqual((CanvasView._sprout_bond_endpoint(fake_view, 1, cyclic=False).x(), CanvasView._sprout_bond_endpoint(fake_view, 1, cyclic=False).y()), (5.0, 5.0))

        fake_view.model.bonds = [Bond(1, 2, 1)]
        one_neighbor = CanvasView._sprout_bond_endpoint(fake_view, 1, cyclic=True)
        self.assertAlmostEqual(one_neighbor.x(), -10.0)
        self.assertAlmostEqual(one_neighbor.y(), 17.320508075688775)

        fake_view.model.bonds = [Bond(1, 2, 1), Bond(1, 3, 1)]
        two_neighbors = CanvasView._sprout_bond_endpoint(fake_view, 1, cyclic=True)
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
            _default_bond_endpoint=lambda start, atom_id: QPointF(5.0, 6.0),
            _ring_polygon_points_for_bond=mock.Mock(return_value=[(0.0, 0.0), (1.0, 1.0)]),
        )

        with (
            mock.patch("ui.canvas_view.compute_sprout_bond_endpoint", return_value=(7.0, 8.0)) as sprout,
            mock.patch(
                "ui.canvas_view.compute_regular_ring_points_for_atom",
                return_value=([(1.0, 2.0)], [(1, 0.0, 0.0)]),
            ) as atom_ring,
            mock.patch(
                "ui.canvas_view.compute_regular_ring_points_for_bond",
                return_value=([(3.0, 4.0)], [(1, 0.0, 0.0), (2, 10.0, 0.0)]),
            ) as bond_ring,
            mock.patch(
                "ui.canvas_view.compute_template_points_for_bond",
                return_value=([(5.0, 6.0)], [(1, 0.0, 0.0), (2, 10.0, 0.0)]),
            ) as template,
        ):
            endpoint = CanvasView._sprout_bond_endpoint(fake_view, 1, cyclic=False)
            atom_result = CanvasView._regular_ring_points_for_atom(fake_view, 6, 1)
            bond_result = CanvasView._regular_ring_points_for_bond(fake_view, 6, 0, QPointF(9.0, 10.0))
            template_result = CanvasView._template_points_for_bond(
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
        sprout.assert_called_once_with(
            1,
            atoms=fake_view.model.atoms,
            bonds=fake_view.model.bonds,
            bond_length=20.0,
            cyclic=False,
            default_endpoint=(5.0, 6.0),
        )
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

        with mock.patch("ui.canvas_view.compute_regular_ring_points_for_atom", return_value=None):
            self.assertIsNone(CanvasView._regular_ring_points_for_atom(fake_view, 6, 1))

    def test_ring_polygon_points_for_bond_wrapper_delegates_to_occupancy_helper(self) -> None:
        fake_view = SimpleNamespace(
            model=SimpleNamespace(bonds=[Bond(1, 2, 1)]),
            ring_items=["ring"],
        )

        with mock.patch(
            "ui.canvas_view.ring_polygon_points_for_bond",
            return_value=[(1.0, 2.0), (3.0, 4.0)],
        ) as occupancy:
            result = CanvasView._ring_polygon_points_for_bond(fake_view, 0)

        self.assertEqual(result, [(1.0, 2.0), (3.0, 4.0)])
        occupancy.assert_called_once_with(
            0,
            bonds=fake_view.model.bonds,
            ring_items=fake_view.ring_items,
        )


if __name__ == "__main__":
    unittest.main()
