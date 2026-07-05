import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
except ModuleNotFoundError:
    QPointF = None

if QPointF is not None:
    from core.model import Atom
    from ui.scene_item_state import ts_bracket_rect_from_state
    from ui.scene_rotation_state import rotate_scene_item_state, rotated_point


def _rotate_state(item, before_state, *, transformed=None, atoms=None):
    return rotate_scene_item_state(
        item,
        before_state,
        center=QPointF(0.0, 0.0),
        angle_degrees=90.0,
        transformed_atom_positions=transformed or {},
        atoms=atoms or {},
        ts_bracket_rect_from_state=ts_bracket_rect_from_state,
    )


def _item(kind: str, *, bounding_rect: QRectF | None = None):
    rect = bounding_rect if bounding_rect is not None else QRectF()
    return SimpleNamespace(data=lambda _key: kind, sceneBoundingRect=lambda: rect)


@unittest.skipUnless(QPointF is not None, "PyQt6 is required for scene rotation state tests")
class SceneRotationStateTest(unittest.TestCase):
    def test_rotated_point_rotates_clockwise_in_scene_coordinates(self) -> None:
        rotated = rotated_point(QPointF(10.0, 0.0), QPointF(0.0, 0.0), 3.141592653589793 / 2.0)
        self.assertAlmostEqual(rotated.x(), 0.0)
        self.assertAlmostEqual(rotated.y(), 10.0)

    def test_rotate_state_handles_ring_points_and_arrow_endpoints(self) -> None:
        ring_state = _rotate_state(_item("ring"), {"kind": "ring", "points": [(10.0, 0.0), (0.0, 10.0)]})
        self.assertAlmostEqual(ring_state["points"][0][0], 0.0)
        self.assertAlmostEqual(ring_state["points"][0][1], 10.0)
        self.assertAlmostEqual(ring_state["points"][1][0], -10.0)
        self.assertAlmostEqual(ring_state["points"][1][1], 0.0)

        arrow_state = _rotate_state(
            _item("arrow"),
            {"kind": "arrow", "start": (10.0, 0.0), "end": (20.0, 0.0)},
        )
        self.assertAlmostEqual(arrow_state["start"][0], 0.0)
        self.assertAlmostEqual(arrow_state["start"][1], 10.0)
        self.assertAlmostEqual(arrow_state["end"][0], 0.0)
        self.assertAlmostEqual(arrow_state["end"][1], 20.0)
        self.assertNotIn("control", arrow_state)

    def test_rotate_state_orbits_note_center_while_keeping_text_upright(self) -> None:
        note_state = _rotate_state(
            _item("note", bounding_rect=QRectF(10.0, 0.0, 10.0, 10.0)),
            {"kind": "note", "text": "hi", "x": 10.0, "y": 0.0},
        )
        self.assertAlmostEqual(note_state["x"], -10.0)
        self.assertAlmostEqual(note_state["y"], 10.0)

        fallback_state = _rotate_state(
            _item("note"),
            {"kind": "note", "text": "hi", "x": 10.0, "y": 0.0},
        )
        self.assertAlmostEqual(fallback_state["x"], 0.0)
        self.assertAlmostEqual(fallback_state["y"], 10.0)

    def test_rotate_state_updates_mark_offsets_against_transformed_atom(self) -> None:
        mark_state = _rotate_state(
            _item("mark"),
            {"kind": "mark", "atom_id": 1, "x": 10.0, "y": 0.0, "dx": 5.0, "dy": 0.0},
            transformed={1: (5.0, 5.0)},
        )
        self.assertAlmostEqual(mark_state["x"], 0.0)
        self.assertAlmostEqual(mark_state["y"], 10.0)
        self.assertAlmostEqual(mark_state["dx"], -5.0)
        self.assertAlmostEqual(mark_state["dy"], 5.0)

        detached_state = _rotate_state(
            _item("mark"),
            {"kind": "mark", "atom_id": 2, "x": 10.0, "y": 0.0},
            atoms={2: Atom("C", 0.0, 10.0)},
        )
        self.assertAlmostEqual(detached_state["dx"], 0.0)
        self.assertAlmostEqual(detached_state["dy"], 0.0)

    def test_rotate_state_spins_orbitals_and_orbits_axis_aligned_rects(self) -> None:
        orbital_state = _rotate_state(
            _item("orbital"),
            {"kind": "orbital", "center": (10.0, 0.0), "rotation": 15.0},
        )
        self.assertAlmostEqual(orbital_state["center"][0], 0.0)
        self.assertAlmostEqual(orbital_state["center"][1], 10.0)
        self.assertAlmostEqual(orbital_state["rotation"], 105.0)

        bracket_state = _rotate_state(
            _item("ts_bracket"),
            {"kind": "ts_bracket", "left": 10.0, "top": 10.0, "right": 20.0, "bottom": 20.0},
        )
        self.assertAlmostEqual(bracket_state["left"], -20.0)
        self.assertAlmostEqual(bracket_state["top"], 10.0)
        self.assertAlmostEqual(bracket_state["right"], -10.0)
        self.assertAlmostEqual(bracket_state["bottom"], 20.0)

    def test_rotate_state_ignores_empty_and_unknown_states(self) -> None:
        self.assertEqual(_rotate_state(_item("arrow"), {}), {})
        self.assertEqual(_rotate_state(_item("mystery"), {"kind": "mystery"}), {})


if __name__ == "__main__":
    unittest.main()
