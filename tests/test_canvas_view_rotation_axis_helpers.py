import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.model import Atom, Bond
    from ui.canvas_view import CanvasView


def _component_lookup(components: dict[tuple[int, int], set[int]]):
    def _lookup(atom_id: int, bond_id: int) -> set[int]:
        return set(components[(atom_id, bond_id)])

    return _lookup


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewRotationAxisHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_rotation_side_for_bond_prefers_selected_side_endpoint_and_fallback(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(bonds=[Bond(1, 2, 1)]),
            _component_without_bond=_component_lookup(
                {
                    (1, 0): {1, 3},
                    (2, 0): {2, 4, 5},
                }
            ),
        )

        self.assertEqual(CanvasView._rotation_side_for_bond(view, 0, {1, 3}, allow_fallback=False), {1, 3})
        self.assertEqual(CanvasView._rotation_side_for_bond(view, 0, {2, 4}, allow_fallback=False), {2, 4, 5})
        self.assertEqual(CanvasView._rotation_side_for_bond(view, 0, {1}, allow_fallback=False), {1, 3})
        self.assertEqual(CanvasView._rotation_side_for_bond(view, 0, {1, 2, 3, 4}, allow_fallback=True), {2, 4, 5})
        self.assertIsNone(CanvasView._rotation_side_for_bond(view, 0, {1, 2, 3, 4}, allow_fallback=False))
        self.assertIsNone(CanvasView._rotation_side_for_bond(view, 99, {1}, allow_fallback=True))

    def test_preferred_rotation_side_for_bond_uses_partial_coverage_press_pos_and_fallback(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(
                bonds=[Bond(1, 2, 1)],
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 10.0, 0.0),
                },
            ),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            _component_without_bond=_component_lookup(
                {
                    (1, 0): {1, 3, 6},
                    (2, 0): {2, 4, 5, 7},
                }
            ),
        )

        self.assertEqual(CanvasView._preferred_rotation_side_for_bond(view, 0, {1, 3}, allow_fallback=True), {1, 3, 6})
        self.assertEqual(
            CanvasView._preferred_rotation_side_for_bond(
                view,
                0,
                {1, 2, 3, 4},
                press_pos=QPointF(1.0, 0.0),
                allow_fallback=True,
            ),
            {1, 3, 6},
        )
        self.assertEqual(
            CanvasView._preferred_rotation_side_for_bond(
                view,
                0,
                {1, 2, 3, 4},
                allow_fallback=True,
            ),
            {1, 3, 6},
        )
        self.assertIsNone(
            CanvasView._preferred_rotation_side_for_bond(
                view,
                0,
                {1, 2, 3, 4, 5, 6, 7},
                allow_fallback=False,
            )
        )
        self.assertIsNone(CanvasView._preferred_rotation_side_for_bond(view, 99, {1}, allow_fallback=True))

    def test_rotatable_axis_from_selection_uses_cache_and_invalidates_on_graph_change(self) -> None:
        preferred = mock.Mock(return_value={1, 3})
        view = SimpleNamespace(
            _rotation_axis_cache={},
            _rotation_axis_cache_version=5,
            _graph_version=5,
            model=SimpleNamespace(bonds=[Bond(1, 2, 1)]),
            _bond_is_rotatable=mock.Mock(return_value=True),
            _preferred_rotation_side_for_bond=preferred,
            _rotation_side_for_bond=mock.Mock(),
        )

        first = CanvasView._rotatable_axis_from_selection(view, {1, 2}, {0})
        second = CanvasView._rotatable_axis_from_selection(view, {1, 2}, {0})

        self.assertEqual(first, (0, {1, 3}))
        self.assertEqual(second, (0, {1, 3}))
        preferred.assert_called_once_with(0, {1, 2}, allow_fallback=True)

        view._graph_version = 6
        preferred.return_value = {2, 4}
        third = CanvasView._rotatable_axis_from_selection(view, {1, 2}, {0})
        self.assertEqual(third, (0, {2, 4}))
        self.assertEqual(preferred.call_count, 2)

    def test_rotatable_axis_from_selection_handles_leaf_candidate_boundary_and_none_paths(self) -> None:
        leaf_rotation = mock.Mock(return_value={2, 3})
        leaf_view = SimpleNamespace(
            _rotation_axis_cache={},
            _rotation_axis_cache_version=1,
            _graph_version=1,
            model=SimpleNamespace(
                bonds=[
                    Bond(1, 2, 1),
                    Bond(2, 3, 1),
                    Bond(3, 4, 1),
                ]
            ),
            _bond_is_rotatable=mock.Mock(side_effect=lambda bond_id: bond_id in {0, 1}),
            _preferred_rotation_side_for_bond=mock.Mock(return_value=None),
            _rotation_side_for_bond=leaf_rotation,
        )

        self.assertEqual(CanvasView._rotatable_axis_from_selection(leaf_view, set(), {0, 1}), (1, {2, 3}))
        leaf_rotation.assert_called_once_with(1, {1, 2, 3}, allow_fallback=True)

        boundary_rotation = mock.Mock(return_value={1, 2})
        boundary_view = SimpleNamespace(
            _rotation_axis_cache={},
            _rotation_axis_cache_version=2,
            _graph_version=2,
            model=SimpleNamespace(
                bonds=[
                    Bond(1, 2, 1),
                    Bond(2, 3, 1),
                ]
            ),
            _bond_is_rotatable=mock.Mock(side_effect=lambda bond_id: bond_id == 1),
            _preferred_rotation_side_for_bond=mock.Mock(return_value=None),
            _rotation_side_for_bond=boundary_rotation,
        )

        self.assertEqual(CanvasView._rotatable_axis_from_selection(boundary_view, {1, 2}, set()), (1, {1, 2}))
        boundary_rotation.assert_called_once_with(1, {1, 2}, allow_fallback=False)

        none_view = SimpleNamespace(
            _rotation_axis_cache={},
            _rotation_axis_cache_version=3,
            _graph_version=3,
            model=SimpleNamespace(bonds=[]),
            _bond_is_rotatable=mock.Mock(return_value=False),
            _preferred_rotation_side_for_bond=mock.Mock(return_value=None),
            _rotation_side_for_bond=mock.Mock(return_value=None),
        )

        self.assertIsNone(CanvasView._rotatable_axis_from_selection(none_view, set(), set()))


if __name__ == "__main__":
    unittest.main()
