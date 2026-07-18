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
    from chemvas.domain.document import Atom, Bond
    from chemvas.ui.canvas_graph_service import CanvasGraphService
    from chemvas.ui.canvas_graph_state import CanvasGraphState


def _component_lookup(components: dict[tuple[int, int], set[int]]):
    def _lookup(atom_id: int, bond_id: int) -> set[int]:
        return set(components[(atom_id, bond_id)])

    return _lookup


def _bind_graph_service(view) -> CanvasGraphService:
    service = CanvasGraphService(view)
    view.services = SimpleNamespace(canvas_graph_service=service)
    return service


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for canvas view tests"
)
class CanvasViewRotationAxisHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_rotation_side_for_bond_prefers_selected_side_endpoint_and_fallback(
        self,
    ) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(bonds=[Bond(1, 2, 1)]),
        )
        service = _bind_graph_service(view)
        service.component_without_bond = _component_lookup(
            {
                (1, 0): {1, 3},
                (2, 0): {2, 4, 5},
            }
        )

        self.assertEqual(
            service.rotation_side_for_bond(0, {1, 3}, allow_fallback=False), {1, 3}
        )
        self.assertEqual(
            service.rotation_side_for_bond(0, {2, 4}, allow_fallback=False), {2, 4, 5}
        )
        self.assertEqual(
            service.rotation_side_for_bond(0, {1}, allow_fallback=False), {1, 3}
        )
        self.assertEqual(
            service.rotation_side_for_bond(0, {1, 2, 3, 4}, allow_fallback=True),
            {2, 4, 5},
        )
        self.assertIsNone(
            service.rotation_side_for_bond(0, {1, 2, 3, 4}, allow_fallback=False)
        )
        self.assertIsNone(service.rotation_side_for_bond(99, {1}, allow_fallback=True))

    def test_preferred_rotation_side_for_bond_uses_partial_coverage_press_pos_and_fallback(
        self,
    ) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(
                bonds=[Bond(1, 2, 1)],
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 10.0, 0.0),
                },
            ),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
        )
        service = _bind_graph_service(view)
        service.component_without_bond = _component_lookup(
            {
                (1, 0): {1, 3, 6},
                (2, 0): {2, 4, 5, 7},
            }
        )

        self.assertEqual(
            service.preferred_rotation_side_for_bond(0, {1, 3}, allow_fallback=True),
            {1, 3, 6},
        )
        self.assertEqual(
            service.preferred_rotation_side_for_bond(
                0,
                {1, 2, 3, 4},
                press_pos=QPointF(1.0, 0.0),
                allow_fallback=True,
            ),
            {1, 3, 6},
        )
        self.assertEqual(
            service.preferred_rotation_side_for_bond(
                0,
                {1, 2, 3, 4},
                allow_fallback=True,
            ),
            {1, 3, 6},
        )
        self.assertIsNone(
            service.preferred_rotation_side_for_bond(
                0,
                {1, 2, 3, 4, 5, 6, 7},
                allow_fallback=False,
            )
        )
        self.assertIsNone(
            service.preferred_rotation_side_for_bond(99, {1}, allow_fallback=True)
        )

    def test_rotatable_axis_from_selection_uses_cache_and_invalidates_on_graph_change(
        self,
    ) -> None:
        preferred = mock.Mock(return_value={1, 3})
        view = SimpleNamespace(
            graph_state=CanvasGraphState(
                rotation_axis_cache_version=5, graph_version=5
            ),
            model=SimpleNamespace(bonds=[Bond(1, 2, 1)]),
        )
        service = _bind_graph_service(view)
        service.bond_is_rotatable = mock.Mock(return_value=True)
        service.preferred_rotation_side_for_bond = preferred
        service.rotation_side_for_bond = mock.Mock()

        first = service.rotatable_axis_from_selection({1, 2}, {0})
        second = service.rotatable_axis_from_selection({1, 2}, {0})

        self.assertEqual(first, (0, {1, 3}))
        self.assertEqual(second, (0, {1, 3}))
        preferred.assert_called_once_with(0, {1, 2}, allow_fallback=True)

        view.graph_state.graph_version = 6
        preferred.return_value = {2, 4}
        third = service.rotatable_axis_from_selection({1, 2}, {0})
        self.assertEqual(third, (0, {2, 4}))
        self.assertEqual(preferred.call_count, 2)

    def test_rotatable_axis_from_selection_handles_leaf_candidate_boundary_and_none_paths(
        self,
    ) -> None:
        leaf_rotation = mock.Mock(return_value={2, 3})
        leaf_view = SimpleNamespace(
            graph_state=CanvasGraphState(
                rotation_axis_cache_version=1, graph_version=1
            ),
            model=SimpleNamespace(
                bonds=[
                    Bond(1, 2, 1),
                    Bond(2, 3, 1),
                    Bond(3, 4, 1),
                ]
            ),
        )
        leaf_service = _bind_graph_service(leaf_view)
        leaf_service.bond_is_rotatable = mock.Mock(
            side_effect=lambda bond_id: bond_id in {0, 1}
        )
        leaf_service.preferred_rotation_side_for_bond = mock.Mock(return_value=None)
        leaf_service.rotation_side_for_bond = leaf_rotation

        self.assertEqual(
            leaf_service.rotatable_axis_from_selection(set(), {0, 1}), (1, {2, 3})
        )
        leaf_rotation.assert_called_once_with(1, {1, 2, 3}, allow_fallback=True)

        boundary_rotation = mock.Mock(return_value={1, 2})
        boundary_view = SimpleNamespace(
            graph_state=CanvasGraphState(
                rotation_axis_cache_version=2, graph_version=2
            ),
            model=SimpleNamespace(
                bonds=[
                    Bond(1, 2, 1),
                    Bond(2, 3, 1),
                ]
            ),
        )
        boundary_service = _bind_graph_service(boundary_view)
        boundary_service.bond_is_rotatable = mock.Mock(
            side_effect=lambda bond_id: bond_id == 1
        )
        boundary_service.preferred_rotation_side_for_bond = mock.Mock(return_value=None)
        boundary_service.rotation_side_for_bond = boundary_rotation

        self.assertEqual(
            boundary_service.rotatable_axis_from_selection({1, 2}, set()), (1, {1, 2})
        )
        boundary_rotation.assert_called_once_with(1, {1, 2}, allow_fallback=False)

        none_view = SimpleNamespace(
            graph_state=CanvasGraphState(
                rotation_axis_cache_version=3, graph_version=3
            ),
            model=SimpleNamespace(bonds=[]),
        )
        none_service = _bind_graph_service(none_view)
        none_service.bond_is_rotatable = mock.Mock(return_value=False)
        none_service.preferred_rotation_side_for_bond = mock.Mock(return_value=None)
        none_service.rotation_side_for_bond = mock.Mock(return_value=None)

        self.assertIsNone(none_service.rotatable_axis_from_selection(set(), set()))


if __name__ == "__main__":
    unittest.main()
