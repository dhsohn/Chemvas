import os
import unittest
from types import SimpleNamespace

from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from chemvas.domain.document import Atom, Bond
from chemvas.ui.canvas_graph_service import CanvasGraphService
from chemvas.ui.canvas_graph_state import CanvasGraphState


def _component_lookup(components: dict[tuple[int, int], set[int]]):
    def _lookup(atom_id: int, bond_id: int) -> set[int]:
        return set(components[(atom_id, bond_id)])

    return _lookup


def _bind_graph_service(view) -> CanvasGraphService:
    service = CanvasGraphService(view)
    view.services = canvas_runtime_services(graph_service=service)
    return service


class CanvasViewRotationAxisHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

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
            runtime_state=canvas_runtime_state(graph_state=CanvasGraphState()),
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
