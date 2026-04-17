import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsTextItem
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.model import Atom, Bond
    from ui.selection_controller import SelectionController
    from ui.selection_hit_logic import StructureHit


class _FakeItem:
    def __init__(
        self,
        kind=None,
        *,
        data1=None,
        data2=None,
        selected=False,
        rect: QRectF | None = None,
        contains=False,
    ) -> None:
        self._data = {0: kind, 1: data1, 2: data2}
        self._selected = bool(selected)
        self._rect = QRectF(rect or QRectF(0.0, 0.0, 10.0, 6.0))
        self._contains = contains
        self.moves = []

    def data(self, key):
        return self._data.get(key)

    def setSelected(self, selected: bool) -> None:
        self._selected = bool(selected)

    def isSelected(self) -> bool:
        return self._selected

    def sceneBoundingRect(self) -> QRectF:
        return QRectF(self._rect)

    def contains(self, _pos) -> bool:
        return self._contains

    def mapFromScene(self, pos):
        return pos

    def moveBy(self, dx: float, dy: float) -> None:
        self.moves.append((dx, dy))


class _FakeScene:
    def __init__(self, selected_items=None) -> None:
        self._selected_items = list(selected_items or [])
        self.block_signal_calls = []
        self.removed_items = []
        self.clear_selection_calls = 0

    def selectedItems(self):
        return list(self._selected_items)

    def blockSignals(self, enabled: bool) -> None:
        self.block_signal_calls.append(enabled)

    def removeItem(self, item) -> None:
        self.removed_items.append(item)

    def clearSelection(self) -> None:
        self.clear_selection_calls += 1
        for item in self._selected_items:
            item.setSelected(False)


def _make_canvas(**overrides):
    scene = overrides.pop("scene", _FakeScene())
    defaults = dict(
        atom_items={},
        atom_dots={},
        bond_items={},
        model=SimpleNamespace(atoms={}, bonds=[]),
        renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
        selection_outlines=[],
        _suspend_selection_outline=False,
        _selection_color="#1f5eff",
        _emit_selection_info=mock.Mock(),
        scene=lambda: scene,
        item_at_scene_pos=mock.Mock(return_value=None),
        _atom_has_visible_label=mock.Mock(return_value=True),
        _atom_pick_radius=mock.Mock(return_value=6.0),
        _bond_pick_radius=mock.Mock(return_value=4.0),
        _find_bond_near=mock.Mock(return_value=None),
        find_atom_near=mock.Mock(return_value=None),
        _distance_point_to_segment=mock.Mock(return_value=1.5),
        _connected_components=mock.Mock(return_value=[]),
        _bounds_for_atoms=mock.Mock(return_value=None),
        _selected_ids=mock.Mock(return_value=(set(), set())),
        _bounding_box_center_for_atoms=mock.Mock(return_value=QPointF(5.0, 6.0)),
        tools=SimpleNamespace(active=None),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for selection controller tests")
class SelectionControllerAdditionalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_structure_hit_and_item_helpers_cover_atom_bond_ring_and_other(self) -> None:
        atom_item = _FakeItem("atom", data1=1)
        bad_atom_item = _FakeItem("atom", data1="x")
        bond_item = _FakeItem("bond", data1=0)
        bad_bond_item = _FakeItem("bond", data1=9)
        ring_item = _FakeItem("ring", data2=[1, 2, 3])
        bare_ring_item = _FakeItem("ring", data2="bad")
        other_item = _FakeItem("note")
        canvas = _make_canvas(
            atom_items={1: atom_item},
            atom_dots={2: _FakeItem("atom", data1=2)},
            bond_items={0: [bond_item]},
            model=SimpleNamespace(atoms={}, bonds=[Bond(1, 2, 1)]),
        )
        controller = SelectionController(canvas)

        self.assertEqual(controller._structure_hit_from_item(None), (None, None, None))
        self.assertEqual(controller._structure_hit_from_item(atom_item)[0], StructureHit(kind="atom", id=1))
        self.assertEqual(controller._structure_hit_from_item(bad_atom_item), (None, None, None))
        self.assertEqual(controller._structure_hit_from_item(bond_item)[0], StructureHit(kind="bond", id=0))
        self.assertEqual(controller._structure_hit_from_item(bond_item)[1], (1, 2))
        self.assertEqual(controller._structure_hit_from_item(bad_bond_item), (None, None, None))
        self.assertEqual(controller._structure_hit_from_item(ring_item)[0], StructureHit(kind="ring"))
        self.assertEqual(controller._structure_hit_from_item(ring_item)[2], [1, 2, 3])
        self.assertEqual(controller._structure_hit_from_item(bare_ring_item)[0], StructureHit(kind="ring"))
        self.assertEqual(controller._structure_hit_from_item(other_item)[0], StructureHit(kind="other"))

        self.assertIs(controller._structure_item_for_hit(StructureHit(kind="atom", id=1)), atom_item)
        self.assertIs(controller._structure_item_for_hit(StructureHit(kind="atom", id=2)), canvas.atom_dots[2])
        self.assertIs(controller._structure_item_for_hit(StructureHit(kind="bond", id=0)), bond_item)
        self.assertIsNone(controller._structure_item_for_hit(StructureHit(kind="bond", id=5)))
        self.assertIsNone(controller._structure_item_for_hit(StructureHit(kind="ring")))

    def test_selection_targets_and_toggle_item_selection_cover_target_resolution(self) -> None:
        scene = _FakeScene()
        atom_target = _FakeItem("atom", data1=1, selected=False)
        bond_target = _FakeItem("bond", data1=0, selected=True)
        overlay_item = _FakeItem("orbital")
        canvas = _make_canvas(
            scene=scene,
            atom_items={1: atom_target},
            bond_items={0: [bond_target, None]},
        )
        controller = SelectionController(canvas)
        controller.update_selection_outline = mock.Mock()

        self.assertEqual(controller._selection_targets_for_item(_FakeItem("atom", data1=1)), [atom_target])
        self.assertEqual(controller._selection_targets_for_item(_FakeItem("bond", data1=0)), [bond_target])
        self.assertEqual(controller._selection_targets_for_item(overlay_item), [overlay_item])
        self.assertEqual(controller._selection_targets_for_item(_FakeItem("atom", data1="bad")), [])
        self.assertEqual(controller._selection_targets_for_item(_FakeItem("unknown")), [])

        self.assertTrue(controller.toggle_item_selection(_FakeItem("atom", data1=1)))
        self.assertTrue(atom_target.isSelected())
        self.assertEqual(scene.block_signal_calls[:2], [True, False])

        self.assertTrue(controller.toggle_item_selection(_FakeItem("bond", data1=0)))
        self.assertFalse(bond_target.isSelected())
        self.assertEqual(controller.update_selection_outline.call_count, 2)

        self.assertFalse(controller.toggle_item_selection(_FakeItem("atom", data1="bad")))

    def test_preferred_structure_hit_at_scene_pos_prefers_atom_hit_ring_atom_and_fallback(self) -> None:
        atom_item = _FakeItem("atom", data1=1)
        ring_item = _FakeItem("ring", data2=[1, 2, 3])
        fallback_item = _FakeItem("note")
        canvas = _make_canvas(
            atom_items={1: atom_item},
            item_at_scene_pos=mock.Mock(return_value=atom_item),
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0)}, bonds=[]),
        )
        controller = SelectionController(canvas)
        self.assertEqual(controller.preferred_structure_hit_at_scene_pos(QPointF(0.0, 0.0)), StructureHit(kind="atom", id=1))

        ring_canvas = _make_canvas(
            atom_items={2: _FakeItem("atom", data1=2)},
            item_at_scene_pos=mock.Mock(return_value=ring_item),
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 2.0, 0.0),
                    3: Atom("C", 1.0, 2.0),
                },
                bonds=[],
            ),
        )
        ring_controller = SelectionController(ring_canvas)
        with (
            mock.patch("ui.selection_controller.choose_preferred_structure_hit", return_value=None),
            mock.patch("ui.selection_controller.nearest_ring_atom_id", return_value=2),
        ):
            self.assertEqual(
                ring_controller.preferred_structure_hit_at_scene_pos(QPointF(1.5, 0.2)),
                StructureHit(kind="atom", id=2),
            )

        fallback_canvas = _make_canvas(
            item_at_scene_pos=mock.Mock(return_value=fallback_item),
            model=SimpleNamespace(atoms={}, bonds=[]),
        )
        fallback_controller = SelectionController(fallback_canvas)
        with mock.patch("ui.selection_controller.choose_preferred_structure_hit", return_value=None):
            self.assertEqual(
                fallback_controller.preferred_structure_hit_at_scene_pos(QPointF(0.0, 0.0)),
                StructureHit(kind="other"),
            )

    def test_preferred_structure_item_at_scene_pos_returns_hit_item_or_original_item(self) -> None:
        canvas = _make_canvas(item_at_scene_pos=mock.Mock(return_value=_FakeItem("ring")))
        controller = SelectionController(canvas)
        controller.preferred_structure_hit_at_scene_pos = mock.Mock(return_value=StructureHit(kind="atom", id=1))
        controller._structure_item_for_hit = mock.Mock(return_value="atom-item")
        self.assertEqual(controller.preferred_structure_item_at_scene_pos(QPointF(0.0, 0.0)), "atom-item")

        controller.preferred_structure_hit_at_scene_pos = mock.Mock(return_value=StructureHit(kind="ring"))
        self.assertIsInstance(controller.preferred_structure_item_at_scene_pos(QPointF(1.0, 1.0)), _FakeItem)

        controller.preferred_structure_hit_at_scene_pos = mock.Mock(return_value=None)
        self.assertIsNone(controller.preferred_structure_item_at_scene_pos(QPointF(2.0, 2.0)))

    def test_select_structure_for_item_selects_structure_and_overlay_items(self) -> None:
        atom_item = _FakeItem("atom", data1=1)
        atom_item_2 = _FakeItem("atom", data1=2)
        bond_item = _FakeItem("bond", data1=0)
        bond_graphic = _FakeItem("bond")
        ring_item = _FakeItem("ring", data2=[1, 2])
        note_item = _FakeItem("note")
        scene = _FakeScene([atom_item, bond_item, ring_item, note_item])
        canvas = _make_canvas(
            scene=scene,
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 2.0, 0.0)},
                bonds=[Bond(1, 2, 1)],
            ),
            atom_items={1: atom_item, 2: atom_item_2},
            atom_dots={},
            bond_items={0: [bond_graphic]},
            ring_items=[ring_item],
            _expand_connected_atoms=mock.Mock(return_value={1, 2}),
            _update_selection_outline=mock.Mock(),
        )
        controller = SelectionController(canvas)

        self.assertTrue(controller.select_structure_for_item(atom_item))
        self.assertEqual(scene.clear_selection_calls, 1)
        self.assertTrue(atom_item.isSelected())
        self.assertTrue(atom_item_2.isSelected())
        self.assertTrue(bond_graphic.isSelected())
        self.assertTrue(ring_item.isSelected())
        canvas._update_selection_outline.assert_called_once_with()

        scene.clear_selection_calls = 0
        canvas._update_selection_outline.reset_mock()
        self.assertTrue(controller.select_structure_for_item(note_item))
        self.assertEqual(scene.clear_selection_calls, 1)
        self.assertTrue(note_item.isSelected())
        canvas._update_selection_outline.assert_not_called()

        invalid_atom = _FakeItem("atom", data1="bad")
        self.assertFalse(controller.select_structure_for_item(invalid_atom))
        self.assertFalse(controller.select_structure_for_item(None))

    def test_note_selection_helpers_manage_selected_notes_and_selection_boxes(self) -> None:
        scene = QGraphicsScene()
        note_a = QGraphicsTextItem("A")
        note_b = QGraphicsTextItem("B")
        scene.addItem(note_a)
        scene.addItem(note_b)
        canvas = SimpleNamespace(
            selected_notes=[note_a],
            note_padding=6.0,
            _selection_color=QColor("#1f5eff"),
            _selection_stroke_delta=0.8,
            clear_note_selection=None,
            _update_note_selection_box=None,
        )
        controller = SelectionController(canvas)
        canvas.clear_note_selection = controller.clear_note_selection
        canvas._update_note_selection_box = controller.update_note_selection_box

        controller.select_note(note_b, additive=False)
        self.assertEqual(canvas.selected_notes, [note_b])
        self.assertTrue(note_a.data(21) is None or not note_a.data(21).isVisible())
        self.assertTrue(note_b.data(21).isVisible())

        controller.select_note(note_a, additive=True)
        self.assertEqual(canvas.selected_notes, [note_b, note_a])

        controller.toggle_note_selection(note_b)
        self.assertEqual(canvas.selected_notes, [note_a])
        self.assertFalse(note_b.data(21).isVisible())

        controller.clear_note_selection()
        self.assertEqual(canvas.selected_notes, [])
        self.assertFalse(note_a.data(21).isVisible())

    def test_selection_rects_and_hit_test_build_request_from_snapshot(self) -> None:
        note_item = _FakeItem("note", rect=QRectF(5.0, 6.0, 7.0, 8.0))
        arrow_item = _FakeItem("arrow", rect=QRectF(9.0, 9.0, 2.0, 2.0))
        atom_item = _FakeItem("atom", data1=1)
        selected_bond_item = _FakeItem("bond", data1=0, selected=True)
        outline = _FakeItem("selection_outline", data2={"kind": "component"}, contains=True)
        snapshot = SimpleNamespace(
            selected_atom_ids={1, 2},
            selected_bond_ids={0},
            selection_items=[note_item, arrow_item, atom_item],
        )
        canvas = _make_canvas(
            selection_outlines=[outline],
            item_at_scene_pos=mock.Mock(return_value=selected_bond_item),
            _connected_components=mock.Mock(return_value=[{1, 2}]),
            _bounds_for_atoms=mock.Mock(return_value=(1.0, 2.0, 3.0, 4.0)),
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 2.0, 0.0)}, bonds=[Bond(1, 2, 1)]),
        )
        controller = SelectionController(canvas)

        rects = controller._selection_rects_for_snapshot(snapshot)
        self.assertEqual(len(rects), 2)
        self.assertEqual((rects[0].left, rects[0].top, rects[0].right, rects[0].bottom), (1.0, 2.0, 3.0, 4.0))
        self.assertEqual((rects[1].left, rects[1].top, rects[1].right, rects[1].bottom), (5.0, 6.0, 12.0, 14.0))

        with mock.patch("ui.selection_controller.selection_hit_matches", return_value=True) as matches:
            self.assertTrue(controller.selection_hit_test(QPointF(4.0, 5.0), snapshot=snapshot))

        request = matches.call_args.args[0]
        self.assertTrue(request.outline_hit)
        self.assertEqual(request.hit, StructureHit(kind="bond", id=0))
        self.assertTrue(request.item_is_selected)
        self.assertEqual(request.selected_atom_ids, {1, 2})
        self.assertEqual(request.selected_bond_ids, {0})

    def test_update_selection_outline_covers_suspend_clear_filtered_and_overlay_paths(self) -> None:
        suspended_canvas = _make_canvas(_suspend_selection_outline=True)
        SelectionController(suspended_canvas).update_selection_outline()
        suspended_canvas._emit_selection_info.assert_not_called()

        empty_outline = _FakeItem("selection_outline")
        empty_scene = _FakeScene([])
        empty_canvas = _make_canvas(scene=empty_scene, selection_outlines=[empty_outline])
        SelectionController(empty_canvas).update_selection_outline()
        self.assertEqual(empty_scene.removed_items, [empty_outline])
        self.assertEqual(empty_canvas.selection_outlines, [])
        empty_canvas._emit_selection_info.assert_called_once_with()

        filtered_scene = _FakeScene([_FakeItem("handle")])
        filtered_canvas = _make_canvas(scene=filtered_scene, selection_outlines=[_FakeItem("selection_outline")])
        SelectionController(filtered_canvas).update_selection_outline()
        filtered_canvas._emit_selection_info.assert_not_called()

        atom_item = _FakeItem("atom", data1=1)
        bond_item = _FakeItem("bond", data1=0)
        object_item = _FakeItem("arrow")
        old_outline = _FakeItem("selection_outline")
        active_scene = _FakeScene([atom_item, bond_item, object_item])
        active_canvas = _make_canvas(
            scene=active_scene,
            selection_outlines=[old_outline],
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 2.0, 0.0)}, bonds=[Bond(1, 2, 1)]),
            _selected_ids=mock.Mock(return_value=({1}, {0})),
            _connected_components=mock.Mock(return_value=[{1, 2}]),
        )
        controller = SelectionController(active_canvas)
        controller._add_selection_component_overlay = mock.Mock()
        controller._selection_center_for_atoms = mock.Mock(return_value=QPointF(1.0, 0.0))
        controller._selection_center_marker_enabled = mock.Mock(return_value=True)
        controller._add_selection_center_marker = mock.Mock()
        controller._add_selection_object_overlay = mock.Mock()

        controller.update_selection_outline()

        self.assertEqual(active_scene.removed_items, [old_outline])
        controller._add_selection_component_overlay.assert_called_once()
        self.assertEqual(controller._add_selection_component_overlay.call_args.args[0], {1, 2})
        self.assertEqual(controller._add_selection_component_overlay.call_args.args[1], {0})
        controller._add_selection_center_marker.assert_called_once_with(QPointF(1.0, 0.0))
        controller._add_selection_object_overlay.assert_called_once_with(object_item, mock.ANY)
        active_canvas._emit_selection_info.assert_called_once_with()

    def test_shift_selection_outlines_and_center_helpers_cover_simple_branches(self) -> None:
        outline = _FakeItem("selection_outline")
        canvas = _make_canvas(selection_outlines=[outline], tools=SimpleNamespace(active=SimpleNamespace(name="perspective")))
        controller = SelectionController(canvas)

        controller.shift_selection_outlines(3.0, -2.0)
        self.assertEqual(outline.moves, [(3.0, -2.0)])

        self.assertIsNone(controller._selection_center_for_atoms({1}))
        self.assertEqual(controller._selection_center_for_atoms({1, 2}), QPointF(5.0, 6.0))
        self.assertTrue(controller._selection_center_marker_enabled())

        canvas.tools = SimpleNamespace(active=SimpleNamespace(name="select"))
        self.assertFalse(controller._selection_center_marker_enabled())


if __name__ == "__main__":
    unittest.main()
