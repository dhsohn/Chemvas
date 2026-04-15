import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QFocusEvent, QPen
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
    from ui.canvas_view import CanvasView, NoteItem


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

    def test_chemdraw_shortcut_helpers_dispatch_to_expected_actions(self) -> None:
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

        view = SimpleNamespace(
            _shortcut_modifiers=lambda event: CanvasView._shortcut_modifiers(event),
            flip_horizontal=mock.Mock(),
            flip_vertical=mock.Mock(),
            set_tool=mock.Mock(),
            set_bond_style=mock.Mock(),
        )
        self.assertTrue(CanvasView._handle_chemdraw_object_shortcut(view, _FakeKeyEvent(Qt.Key.Key_H, Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier)))
        view.flip_horizontal.assert_called_once()
        self.assertTrue(CanvasView._handle_chemdraw_object_shortcut(view, _FakeKeyEvent(Qt.Key.Key_V, Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier)))
        view.flip_vertical.assert_called_once()
        self.assertFalse(CanvasView._handle_chemdraw_object_shortcut(view, _FakeKeyEvent(Qt.Key.Key_X)))

        self.assertTrue(CanvasView._handle_chemdraw_generic_hotkey(view, _FakeKeyEvent(Qt.Key.Key_Space)))
        view.set_tool.assert_called_with("select")
        self.assertTrue(CanvasView._handle_chemdraw_generic_hotkey(view, _FakeKeyEvent(Qt.Key.Key_X)))
        view.set_bond_style.assert_called_with("single", 1)
        self.assertTrue(CanvasView._handle_chemdraw_generic_hotkey(view, _FakeKeyEvent(Qt.Key.Key_G, Qt.KeyboardModifier.ShiftModifier)))
        self.assertTrue(CanvasView._handle_chemdraw_generic_hotkey(view, _FakeKeyEvent(Qt.Key.Key_D, Qt.KeyboardModifier.AltModifier)))
        self.assertFalse(CanvasView._handle_chemdraw_generic_hotkey(view, _FakeKeyEvent(Qt.Key.Key_Z)))

    def test_handle_chemdraw_shortcut_routes_between_object_atom_bond_and_generic_handlers(self) -> None:
        view = SimpleNamespace(
            _handle_chemdraw_object_shortcut=mock.Mock(return_value=False),
            _handle_chemdraw_atom_hotkey=mock.Mock(return_value=True),
            _handle_chemdraw_bond_hotkey=mock.Mock(return_value=True),
            _handle_chemdraw_generic_hotkey=mock.Mock(return_value=True),
            hover_atom_id=4,
            hover_bond_id=None,
        )
        event = _FakeKeyEvent(Qt.Key.Key_C, text="c")
        self.assertTrue(CanvasView._handle_chemdraw_shortcut(view, event))
        view._handle_chemdraw_atom_hotkey.assert_called_once_with(event, 4)

        view.hover_atom_id = None
        view.hover_bond_id = 7
        self.assertTrue(CanvasView._handle_chemdraw_shortcut(view, event))
        view._handle_chemdraw_bond_hotkey.assert_called_once_with(event, 7)

        view.hover_bond_id = None
        self.assertTrue(CanvasView._handle_chemdraw_shortcut(view, event))
        view._handle_chemdraw_generic_hotkey.assert_called_once_with(event)

        view._handle_chemdraw_object_shortcut.return_value = True
        self.assertTrue(CanvasView._handle_chemdraw_shortcut(view, event))

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
        self.assertIsNone(CanvasView._translated_scene_item_state(fake_view, "bad", dx=0.0, dy=0.0, atom_id_map={}))

        self.assertTrue(CanvasView._uses_compact_label_hit_shape("C"))
        self.assertTrue(CanvasView._uses_compact_label_hit_shape("Cl"))
        self.assertFalse(CanvasView._uses_compact_label_hit_shape("CH3"))
        self.assertEqual(CanvasView._implicit_carbon_dot_brush().alpha(), 0)
        self.assertEqual(CanvasView._clipboard_paste_offset(2, 20.0), (36.0, 36.0))
        self.assertEqual(CanvasView._selection_signature_for({1, 2}, {3}), (frozenset({1, 2}), frozenset({3})))

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

    def test_atom_hotkey_routes_to_prompt_marks_labels_and_sprouts(self) -> None:
        calls: list[tuple] = []
        fake_view = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 1.0, 2.0)}, bonds=[]),
            _shortcut_modifiers=lambda event: CanvasView._shortcut_modifiers(event),
            prompt_atom_label=lambda atom_id: calls.append(("prompt", atom_id)),
            _atom_point=lambda atom_id: QPointF(1.0, 2.0),
            add_mark_for_atom=lambda atom_id, pos, kind: calls.append(("mark", atom_id, pos.x(), pos.y(), kind)),
            add_or_update_atom_label=lambda atom_id, text, show_carbon=True: calls.append(("label", atom_id, text, show_carbon)),
            _sprout_bond_from_atom=lambda atom_id, style, order, cyclic=False: calls.append(("bond", atom_id, style, order, cyclic)),
            _sprout_acetyl_from_atom=lambda atom_id: calls.append(("acetyl", atom_id)),
            _sprout_benzene_from_atom=lambda atom_id: calls.append(("benzene", atom_id)),
            _sprout_regular_ring_from_atom=lambda atom_id, n: calls.append(("ring", atom_id, n)),
        )

        self.assertFalse(CanvasView._handle_chemdraw_atom_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_C, text="c"), 99))
        self.assertFalse(
            CanvasView._handle_chemdraw_atom_hotkey(
                fake_view,
                _FakeKeyEvent(Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier, text="c"),
                1,
            )
        )
        self.assertTrue(CanvasView._handle_chemdraw_atom_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_Return), 1))
        self.assertTrue(CanvasView._handle_chemdraw_atom_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_Plus, text="+"), 1))
        self.assertTrue(CanvasView._handle_chemdraw_atom_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_Minus, text="-"), 1))
        self.assertTrue(CanvasView._handle_chemdraw_atom_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_F, text="F"), 1))
        self.assertTrue(CanvasView._handle_chemdraw_atom_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_0, text="0"), 1))
        self.assertTrue(CanvasView._handle_chemdraw_atom_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_2, text="2"), 1))
        self.assertTrue(CanvasView._handle_chemdraw_atom_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_3, text="3"), 1))
        self.assertTrue(CanvasView._handle_chemdraw_atom_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_4, text="4"), 1))
        self.assertTrue(CanvasView._handle_chemdraw_atom_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_6, text="6"), 1))
        self.assertTrue(CanvasView._handle_chemdraw_atom_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_8, text="8"), 1))
        self.assertTrue(CanvasView._handle_chemdraw_atom_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_Z, text="z"), 1))
        self.assertTrue(CanvasView._handle_chemdraw_atom_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_V, text="v"), 1))
        self.assertFalse(CanvasView._handle_chemdraw_atom_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_unknown, text=""), 1))
        self.assertIn(("prompt", 1), calls)
        self.assertIn(("mark", 1, 1.0, 2.0, "plus"), calls)
        self.assertIn(("mark", 1, 1.0, 2.0, "minus"), calls)
        self.assertIn(("label", 1, "CF3", True), calls)
        self.assertIn(("bond", 1, "single", 1, True), calls)
        self.assertIn(("acetyl", 1), calls)
        self.assertIn(("benzene", 1), calls)
        self.assertIn(("ring", 1, 6), calls)
        self.assertIn(("bond", 1, "double", 2, False), calls)
        self.assertIn(("bond", 1, "triple", 3, False), calls)
        self.assertIn(("ring", 1, 3), calls)

    def test_bond_hotkey_visible_label_and_atom_point_helpers(self) -> None:
        calls: list[tuple] = []
        fake_view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 1.0, 2.0),
                    2: Atom("O", 4.0, 5.0),
                },
                bonds=[Bond(1, 2, 1), None],
            ),
            atom_items={1: object()},
            _shortcut_modifiers=lambda event: CanvasView._shortcut_modifiers(event),
            apply_bond_style=lambda bond_id, style, order: calls.append(("style", bond_id, style, order)),
            _fuse_benzene_to_bond=lambda bond_id: calls.append(("benzene", bond_id)),
            _fuse_regular_ring_to_bond=lambda bond_id, n: calls.append(("ring", bond_id, n)),
            _fuse_chair_to_bond=lambda bond_id, mirrored=False: calls.append(("chair", bond_id, mirrored)),
        )

        self.assertFalse(CanvasView._handle_chemdraw_bond_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_1, text="1"), 1))
        self.assertFalse(
            CanvasView._handle_chemdraw_bond_hotkey(
                fake_view,
                _FakeKeyEvent(Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier, text="1"),
                0,
            )
        )
        self.assertTrue(CanvasView._handle_chemdraw_bond_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_B, Qt.KeyboardModifier.ShiftModifier, text="B"), 0))
        self.assertTrue(CanvasView._handle_chemdraw_bond_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_H, Qt.KeyboardModifier.ShiftModifier, text="H"), 0))
        self.assertTrue(CanvasView._handle_chemdraw_bond_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_1, text="1"), 0))
        self.assertTrue(CanvasView._handle_chemdraw_bond_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_2, text="2"), 0))
        self.assertTrue(CanvasView._handle_chemdraw_bond_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_3, text="3"), 0))
        self.assertTrue(CanvasView._handle_chemdraw_bond_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_B, text="b"), 0))
        self.assertTrue(CanvasView._handle_chemdraw_bond_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_W, text="w"), 0))
        self.assertTrue(CanvasView._handle_chemdraw_bond_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_H, text="h"), 0))
        self.assertTrue(CanvasView._handle_chemdraw_bond_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_A, text="a"), 0))
        self.assertTrue(CanvasView._handle_chemdraw_bond_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_6, text="6"), 0))
        self.assertTrue(CanvasView._handle_chemdraw_bond_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_0, text="0"), 0))
        self.assertFalse(CanvasView._handle_chemdraw_bond_hotkey(fake_view, _FakeKeyEvent(Qt.Key.Key_X, text="x"), 0))
        self.assertTrue(CanvasView._atom_has_visible_label(fake_view, 1))
        fake_view.atom_items = {}
        self.assertFalse(CanvasView._atom_has_visible_label(fake_view, 1))
        self.assertTrue(CanvasView._atom_has_visible_label(fake_view, 2))
        self.assertEqual((CanvasView._atom_point(fake_view, 2).x(), CanvasView._atom_point(fake_view, 2).y()), (4.0, 5.0))
        self.assertIn(("style", 0, "bold_in", 2), calls)
        self.assertIn(("style", 0, "hash", 1), calls)
        self.assertIn(("style", 0, "single", 1), calls)
        self.assertIn(("style", 0, "double", 2), calls)
        self.assertIn(("style", 0, "triple", 3), calls)
        self.assertIn(("benzene", 0), calls)
        self.assertIn(("ring", 0, 6), calls)
        self.assertIn(("chair", 0, True), calls)

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


if __name__ == "__main__":
    unittest.main()
