import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.scene_transform_logic import (
        build_flip_atom_position_maps,
        center_for_flip_group,
        flip_bounds_for_item,
        flip_center_for_selection,
        flip_scene_item_state,
        group_items_for_flip_transform,
    )

    from tests.test_scene_ops_controller import (
        _FakeCanvas,
        _make_note_item,
        _make_rect_item,
        _make_ring_item,
    )


class _FakeSceneItem:
    def __init__(self, kind: str, rect: QRectF, *, state: dict | None = None) -> None:
        self._kind = kind
        self._rect = QRectF(rect)
        self._state = dict(state or {})

    def data(self, role: int):
        if role == 0:
            return self._kind
        if role == 9:
            return dict(self._state)
        return None

    def sceneBoundingRect(self) -> QRectF:
        return QRectF(self._rect)


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene transform logic tests")
class SceneTransformLogicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_group_items_for_flip_transform_partitions_component_and_standalone_items(self) -> None:
        atom_item = _make_rect_item("atom", data1=1)
        bond_item = _make_rect_item("bond", data1=0)
        linked_mark = _make_rect_item(
            "mark",
            data1={"atom_id": 1},
            state={"kind": "mark", "atom_id": 1, "x": 1.0, "y": 2.0},
        )
        selected_linked_mark = linked_mark
        second_component_mark = _make_rect_item(
            "mark",
            data1={"atom_id": 7},
            state={"kind": "mark", "atom_id": 7, "x": 3.0, "y": 4.0},
        )
        free_mark = _make_rect_item(
            "mark",
            data1={"atom_id": None},
            state={"kind": "mark", "atom_id": None, "x": 5.0, "y": 6.0},
        )
        component_ring = _make_ring_item()
        component_ring.setData(2, [2, 9])
        standalone_ring = _make_ring_item()
        standalone_ring.setData(2, [99])
        arrow_item = _make_rect_item("arrow", state={"kind": "arrow"})

        groups = group_items_for_flip_transform(
            [
                atom_item,
                bond_item,
                selected_linked_mark,
                free_mark,
                component_ring,
                standalone_ring,
                arrow_item,
            ],
            atom_components=[{1, 2}, {7}],
            marks_by_atom={1: [linked_mark], 7: [second_component_mark]},
        )

        self.assertEqual(groups.component_items[0], [linked_mark, component_ring])
        self.assertEqual(groups.component_items[1], [second_component_mark])
        self.assertEqual(groups.standalone_items, [free_mark, standalone_ring, arrow_item])

    def test_group_items_for_flip_transform_sends_unbound_mark_to_standalone(self) -> None:
        loose_mark = _make_rect_item(
            "mark",
            data1={"atom_id": "bad"},
            state={"kind": "mark", "atom_id": None, "x": 2.0, "y": 3.0},
        )

        groups = group_items_for_flip_transform(
            [loose_mark],
            atom_components=[{1}],
            marks_by_atom={},
        )

        self.assertEqual(groups.component_items, [[]])
        self.assertEqual(groups.standalone_items, [loose_mark])

    def test_build_flip_atom_position_maps_skips_missing_atoms_and_flips_remaining_atoms(self) -> None:
        atoms = {
            1: SimpleNamespace(x=2.0, y=1.0),
            3: SimpleNamespace(x=8.0, y=5.0),
        }

        maps = build_flip_atom_position_maps(
            [1, 2, 3],
            atoms=atoms,
            center=QPointF(5.0, 2.0),
            flip_point=lambda point, center: QPointF(center.x() - (point.x() - center.x()), point.y()),
        )

        self.assertEqual(maps.before_positions, {1: (2.0, 1.0), 3: (8.0, 5.0)})
        self.assertEqual(maps.after_positions, {1: (8.0, 1.0), 3: (2.0, 5.0)})
        self.assertEqual(maps.transformed_atom_positions, {1: (8.0, 1.0), 3: (2.0, 5.0)})

    def test_flip_bounds_and_center_helpers_cover_ring_arrow_note_and_bogus_paths(self) -> None:
        canvas = _FakeCanvas()
        canvas.model.atoms = {
            1: SimpleNamespace(x=0.0, y=0.0),
            2: SimpleNamespace(x=20.0, y=10.0),
        }
        ring_item = _make_ring_item()
        note_item = _make_note_item("note", 3.0, 4.0)
        arrow_item = _make_rect_item(
            "arrow",
            state={"kind": "arrow", "start": (1.0, 2.0), "end": (5.0, 6.0), "control": (3.0, 8.0)},
        )
        bogus_item = _make_rect_item("mystery")

        self.assertEqual(
            flip_bounds_for_item(
                ring_item,
                scene_item_state_getter=canvas.scene_item_state,
                bounds_from_points=canvas._bounds_from_points,
            ),
            QRectF(0.0, 0.0, 12.0, 10.0),
        )
        arrow_bounds = flip_bounds_for_item(
            arrow_item,
            scene_item_state_getter=canvas.scene_item_state,
            bounds_from_points=canvas._bounds_from_points,
        )
        note_bounds = flip_bounds_for_item(
            note_item,
            scene_item_state_getter=canvas.scene_item_state,
            bounds_from_points=canvas._bounds_from_points,
        )

        self.assertIsNotNone(note_bounds)
        self.assertEqual((arrow_bounds.left(), arrow_bounds.top(), arrow_bounds.right(), arrow_bounds.bottom()), (1.0, 2.0, 5.0, 8.0))
        self.assertIsNone(
            flip_bounds_for_item(
                bogus_item,
                scene_item_state_getter=canvas.scene_item_state,
                bounds_from_points=canvas._bounds_from_points,
            )
        )
        self.assertEqual(
            flip_center_for_selection(
                set(),
                [ring_item],
                atoms=canvas.model.atoms,
                flip_bounds_getter=lambda item: flip_bounds_for_item(
                    item,
                    scene_item_state_getter=canvas.scene_item_state,
                    bounds_from_points=canvas._bounds_from_points,
                ),
            ),
            QPointF(6.0, 5.0),
        )
        self.assertEqual(
            center_for_flip_group(
                {1, 2},
                [],
                bounding_box_center_for_atoms=canvas._bounding_box_center_for_atoms,
                flip_center_for_selection_getter=lambda atom_ids, items: flip_center_for_selection(
                    atom_ids,
                    items,
                    atoms=canvas.model.atoms,
                    flip_bounds_getter=lambda item: flip_bounds_for_item(
                        item,
                        scene_item_state_getter=canvas.scene_item_state,
                        bounds_from_points=canvas._bounds_from_points,
                    ),
                ),
            ),
            QPointF(10.0, 5.0),
        )

    def test_flip_scene_item_state_recomputes_mark_offset_and_flips_other_scene_items(self) -> None:
        canvas = _FakeCanvas()
        canvas.model.atoms[7] = SimpleNamespace(x=10.0, y=2.0)
        mark_item = _make_rect_item("mark")
        note_item = _make_note_item("note", 3.0, 4.0)
        orbital_item = _make_rect_item(
            "orbital",
            state={"kind": "orbital", "center": (6.0, 4.0), "rotation": 15.0},
        )
        bracket_item = _make_rect_item(
            "ts_bracket",
            state={"kind": "ts_bracket", "left": 1.0, "top": 2.0, "right": 3.0, "bottom": 6.0},
        )
        arrow_item = _make_rect_item(
            "arrow",
            state={"kind": "arrow", "start": (1.0, 2.0), "end": (5.0, 6.0), "control": (3.0, 8.0)},
        )

        mark_state = flip_scene_item_state(
            mark_item,
            {"kind": "mark", "atom_id": 7, "x": 7.0, "y": 3.0, "dx": -3.0, "dy": 1.0},
            center=QPointF(5.0, 0.0),
            horizontal=True,
            transformed_atom_positions={7: (1.0, 2.0)},
            atoms=canvas.model.atoms,
            flip_point=canvas._flip_point,
            ts_bracket_rect_from_state=canvas._ts_bracket_rect_from_state,
        )
        note_state = flip_scene_item_state(
            note_item,
            {"kind": "note", "text": "note", "x": 3.0, "y": 4.0},
            center=QPointF(8.0, 0.0),
            horizontal=True,
            transformed_atom_positions={},
            atoms=canvas.model.atoms,
            flip_point=canvas._flip_point,
            ts_bracket_rect_from_state=canvas._ts_bracket_rect_from_state,
        )
        orbital_state = flip_scene_item_state(
            orbital_item,
            {"kind": "orbital", "center": (6.0, 4.0), "rotation": 15.0},
            center=QPointF(5.0, 0.0),
            horizontal=True,
            transformed_atom_positions={},
            atoms=canvas.model.atoms,
            flip_point=canvas._flip_point,
            ts_bracket_rect_from_state=canvas._ts_bracket_rect_from_state,
        )
        bracket_state = flip_scene_item_state(
            bracket_item,
            {"kind": "ts_bracket", "left": 1.0, "top": 2.0, "right": 3.0, "bottom": 6.0},
            center=QPointF(5.0, 5.0),
            horizontal=False,
            transformed_atom_positions={},
            atoms=canvas.model.atoms,
            flip_point=canvas._flip_point,
            ts_bracket_rect_from_state=canvas._ts_bracket_rect_from_state,
        )
        arrow_state = flip_scene_item_state(
            arrow_item,
            {"kind": "arrow", "start": (1.0, 2.0), "end": (5.0, 6.0), "control": (3.0, 8.0)},
            center=QPointF(4.0, 0.0),
            horizontal=True,
            transformed_atom_positions={},
            atoms=canvas.model.atoms,
            flip_point=canvas._flip_point,
            ts_bracket_rect_from_state=canvas._ts_bracket_rect_from_state,
        )

        self.assertEqual(mark_state["x"], 3.0)
        self.assertEqual(mark_state["y"], 3.0)
        self.assertEqual(mark_state["dx"], 2.0)
        self.assertEqual(mark_state["dy"], 1.0)
        expected_note_x = 2.0 * 8.0 - note_item.sceneBoundingRect().right()
        self.assertEqual(note_state["x"], expected_note_x)
        self.assertEqual(note_state["y"], 4.0)
        self.assertEqual(orbital_state["center"], (4.0, 4.0))
        self.assertEqual(orbital_state["rotation"], 165.0)
        self.assertEqual(bracket_state["top"], 4.0)
        self.assertEqual(bracket_state["bottom"], 8.0)
        self.assertEqual(arrow_state["start"], (7.0, 2.0))
        self.assertEqual(arrow_state["end"], (3.0, 6.0))
        self.assertEqual(arrow_state["control"], (5.0, 8.0))

    def test_flip_bounds_and_center_helpers_cover_stateful_fallback_and_skip_atom_bond_items(self) -> None:
        canvas = _FakeCanvas()
        canvas.model.atoms = {
            1: SimpleNamespace(x=0.0, y=0.0),
        }
        weird_item = _FakeSceneItem(
            "weird",
            QRectF(10.0, 20.0, 30.0, 40.0),
            state={"kind": "weird", "value": 1},
        )
        atom_item = _make_rect_item("atom", data1=1)
        bond_item = _make_rect_item("bond", data1=0)

        weird_bounds = flip_bounds_for_item(
            weird_item,
            scene_item_state_getter=canvas.scene_item_state,
            bounds_from_points=canvas._bounds_from_points,
        )
        selection_center = flip_center_for_selection(
            {1, 99},
            [atom_item, bond_item, weird_item],
            atoms=canvas.model.atoms,
            flip_bounds_getter=lambda item: flip_bounds_for_item(
                item,
                scene_item_state_getter=canvas.scene_item_state,
                bounds_from_points=canvas._bounds_from_points,
            ),
        )

        self.assertEqual(weird_bounds, QRectF(10.0, 20.0, 30.0, 40.0))
        self.assertEqual(selection_center, QPointF(20.0, 30.0))

    def test_flip_scene_item_state_handles_empty_unknown_and_fallback_paths(self) -> None:
        canvas = _FakeCanvas()
        canvas.model.atoms[7] = SimpleNamespace(x=10.0, y=2.0)
        invalid_note_item = _FakeSceneItem("note", QRectF(0.0, 0.0, -1.0, -1.0))
        mark_item = _make_rect_item("mark")
        orbital_item = _make_rect_item("orbital")
        bracket_item = _make_rect_item("ts_bracket")

        self.assertEqual(
            flip_scene_item_state(
                mark_item,
                {},
                center=QPointF(5.0, 0.0),
                horizontal=True,
                transformed_atom_positions={},
                atoms=canvas.model.atoms,
                flip_point=canvas._flip_point,
                ts_bracket_rect_from_state=canvas._ts_bracket_rect_from_state,
            ),
            {},
        )
        self.assertEqual(
            flip_scene_item_state(
                mark_item,
                {"kind": "unknown", "x": 1.0, "y": 2.0},
                center=QPointF(5.0, 0.0),
                horizontal=True,
                transformed_atom_positions={},
                atoms=canvas.model.atoms,
                flip_point=canvas._flip_point,
                ts_bracket_rect_from_state=canvas._ts_bracket_rect_from_state,
            ),
            {},
        )

        note_state = flip_scene_item_state(
            invalid_note_item,
            {"kind": "note", "text": "fallback", "x": 1.0, "y": 2.0},
            center=QPointF(5.0, 10.0),
            horizontal=False,
            transformed_atom_positions={},
            atoms=canvas.model.atoms,
            flip_point=canvas._flip_point,
            ts_bracket_rect_from_state=canvas._ts_bracket_rect_from_state,
        )
        mark_state = flip_scene_item_state(
            mark_item,
            {"kind": "mark", "atom_id": 7, "x": 7.0, "y": 3.0, "dx": -3.0, "dy": 1.0},
            center=QPointF(5.0, 0.0),
            horizontal=True,
            transformed_atom_positions={},
            atoms=canvas.model.atoms,
            flip_point=canvas._flip_point,
            ts_bracket_rect_from_state=canvas._ts_bracket_rect_from_state,
        )
        unresolved_mark_state = flip_scene_item_state(
            mark_item,
            {"kind": "mark", "atom_id": 99, "x": 7.0, "y": 3.0, "dx": -3.0, "dy": 1.0},
            center=QPointF(5.0, 0.0),
            horizontal=True,
            transformed_atom_positions={},
            atoms=canvas.model.atoms,
            flip_point=canvas._flip_point,
            ts_bracket_rect_from_state=canvas._ts_bracket_rect_from_state,
        )
        orbital_state = flip_scene_item_state(
            orbital_item,
            {"kind": "orbital", "rotation": 15.0},
            center=QPointF(5.0, 5.0),
            horizontal=False,
            transformed_atom_positions={},
            atoms=canvas.model.atoms,
            flip_point=canvas._flip_point,
            ts_bracket_rect_from_state=canvas._ts_bracket_rect_from_state,
        )
        bracket_state = flip_scene_item_state(
            bracket_item,
            {"kind": "ts_bracket", "left": 1.0, "top": 2.0},
            center=QPointF(5.0, 5.0),
            horizontal=False,
            transformed_atom_positions={},
            atoms=canvas.model.atoms,
            flip_point=canvas._flip_point,
            ts_bracket_rect_from_state=canvas._ts_bracket_rect_from_state,
        )

        self.assertEqual(note_state["x"], 1.0)
        self.assertEqual(note_state["y"], 18.0)
        self.assertEqual(mark_state["dx"], -7.0)
        self.assertEqual(mark_state["dy"], 1.0)
        self.assertEqual(unresolved_mark_state["dx"], -3.0)
        self.assertEqual(unresolved_mark_state["dy"], 1.0)
        self.assertNotIn("center", orbital_state)
        self.assertEqual(orbital_state["rotation"], -15.0)
        self.assertEqual(bracket_state, {"kind": "ts_bracket", "left": 1.0, "top": 2.0})

    def test_group_items_for_flip_transform_deduplicates_duplicate_standalone_items(self) -> None:
        arrow_item = _make_rect_item("arrow", state={"kind": "arrow"})

        groups = group_items_for_flip_transform(
            [arrow_item, arrow_item],
            atom_components=[],
            marks_by_atom={},
        )

        self.assertEqual(groups.component_items, [])
        self.assertEqual(groups.standalone_items, [arrow_item])


if __name__ == "__main__":
    unittest.main()
