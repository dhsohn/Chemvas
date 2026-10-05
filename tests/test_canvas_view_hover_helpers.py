import unittest
from types import SimpleNamespace
from unittest import mock
from unittest.mock import NonCallableMock

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from chemvas.domain.document import Atom, Bond, MoleculeModel
from chemvas.ui.canvas.canvas_mark_registry import CanvasMarkRegistry
from chemvas.ui.canvas.canvas_mark_scene_service import CanvasMarkSceneService
from chemvas.ui.canvas.canvas_tool_settings_state import CanvasToolSettingsState
from chemvas.ui.molecule.bond_preview_access import bond_hover_endpoint_for
from chemvas.ui.molecule.structure_geometry_access import (
    connected_atom_unit_vectors_for,
    default_bond_angle_for_vectors,
    default_bond_endpoint_for,
)
from chemvas.ui.scene.mark_item_access import mark_center_for_pointer_for
from chemvas.ui.selection.selection_info_access import (
    emit_selection_info_for,
)
from chemvas.ui.selection.selection_info_state import SelectionInfoState
from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state


class _SelectedItem:
    def __init__(self, kind: str, item_id: int) -> None:
        self.kind = kind
        self.item_id = item_id

    def data(self, index: int):
        if index == 0:
            return self.kind
        if index == 1:
            return self.item_id
        return None


def _scene_with_selected(*items):
    return SimpleNamespace(selectedItems=lambda: list(items))


class CanvasViewHoverHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_emit_selection_info_returns_immediately_without_callback(self) -> None:
        no_callback_view = SimpleNamespace(
            runtime_state=canvas_runtime_state(
                selection_info_state=SelectionInfoState(callback=None)
            )
        )

        emit_selection_info_for(no_callback_view)

    def test_mark_center_and_bond_helpers_cover_pointer_and_endpoint_logic(
        self,
    ) -> None:
        view = SimpleNamespace(
            model=MoleculeModel(atoms={7: Atom("C", 10.0, 20.0)}, bonds=[]),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=10.0)),
            runtime_state=canvas_runtime_state(
                mark_registry=CanvasMarkRegistry(),
                tool_settings_state=CanvasToolSettingsState(
                    active_bond_style="double",
                    active_bond_order=2,
                    snap_angle_step=45,
                ),
            ),
        )
        mark_scene_service = CanvasMarkSceneService(
            view, history_service=NonCallableMock(spec=())
        )
        mark_scene_service.mark_offset_from_click = mock.Mock(
            return_value=QPointF(1.5, -2.5)
        )
        view.services = canvas_runtime_services(
            canvas_mark_scene_service=mark_scene_service,
            tool_controller=SimpleNamespace(active=SimpleNamespace(name="bond")),
        )

        point = QPointF(5.0, 6.0)
        self.assertEqual(
            mark_center_for_pointer_for(view, point, None, kind=None).toPoint(),
            point.toPoint(),
        )
        self.assertEqual(
            mark_center_for_pointer_for(view, point, 999, kind=None).toPoint(),
            point.toPoint(),
        )

        centered = mark_center_for_pointer_for(view, point, 7, kind="minus")
        self.assertAlmostEqual(centered.x(), 11.5)
        self.assertAlmostEqual(centered.y(), 17.5)
        mark_scene_service.mark_offset_from_click.assert_called_once_with(
            7, point, kind="minus"
        )

        endpoint = bond_hover_endpoint_for(view, QPointF(0.0, 0.0), QPointF(1.0, 1.0))
        self.assertAlmostEqual(endpoint.x(), 7.071, places=3)
        self.assertAlmostEqual(endpoint.y(), 7.071, places=3)

        zero_length = bond_hover_endpoint_for(
            view, QPointF(0.0, 0.0), QPointF(0.0, 0.0)
        )
        self.assertAlmostEqual(zero_length.x(), 10.0)
        self.assertAlmostEqual(zero_length.y(), 0.0)

        delegated = bond_hover_endpoint_for(
            view, QPointF(0.0, 0.0), QPointF(9.0, 9.0), start_atom_id=7
        )
        self.assertAlmostEqual(delegated.x(), 10.0)
        self.assertAlmostEqual(delegated.y(), 0.0)

    def test_default_bond_endpoint_handles_missing_single_and_balanced_neighbor_vectors(
        self,
    ) -> None:
        single_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=10.0)),
            model=MoleculeModel(
                atoms={
                    0: Atom("C", 10.0, 10.0),
                    1: Atom("C", 20.0, 10.0),
                },
                bonds=[Bond(0, 1)],
            ),
        )

        missing = default_bond_endpoint_for(single_view, QPointF(3.0, 4.0), 999)
        self.assertAlmostEqual(missing.x(), 13.0)
        self.assertAlmostEqual(missing.y(), 4.0)

        no_atom = default_bond_endpoint_for(single_view, QPointF(3.0, 4.0), None)
        self.assertAlmostEqual(no_atom.x(), 13.0)
        self.assertAlmostEqual(no_atom.y(), 4.0)

        single = default_bond_endpoint_for(single_view, QPointF(10.0, 10.0), 0)
        self.assertAlmostEqual(single.x(), 5.0, places=2)
        self.assertAlmostEqual(single.y(), 1.34, places=2)

        balanced_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=10.0)),
            model=MoleculeModel(
                atoms={
                    0: Atom("C", 0.0, 0.0),
                    1: Atom("C", 10.0, 0.0),
                    2: Atom("C", -10.0, 0.0),
                },
                bonds=[Bond(0, 1), Bond(0, 2)],
            ),
        )
        balanced = default_bond_endpoint_for(balanced_view, QPointF(0.0, 0.0), 0)
        self.assertAlmostEqual(balanced.x(), 0.0, places=2)
        self.assertAlmostEqual(balanced.y(), -10.0, places=2)

    def test_connected_atom_vectors_and_angle_helper_skip_invalid_neighbors(
        self,
    ) -> None:
        view = SimpleNamespace(
            model=MoleculeModel(
                atoms={
                    0: Atom("C", 0.0, 0.0),
                    1: Atom("C", 10.0, 0.0),
                    2: Atom("C", 0.0, 10.0),
                    3: Atom("C", 0.0, 0.0),
                },
                bonds=[Bond(0, 1), Bond(0, 2), Bond(0, 99), Bond(0, 3), None],
            )
        )

        vectors = connected_atom_unit_vectors_for(view, 0)
        self.assertEqual(len(vectors), 2)
        self.assertEqual(vectors, [(1.0, 0.0), (0.0, 1.0)])
        self.assertEqual(connected_atom_unit_vectors_for(view, 999), [])

        self.assertEqual(default_bond_angle_for_vectors([]), 0.0)
        self.assertEqual(default_bond_angle_for_vectors([(1.0, 0.0)]), -120.0)
        self.assertEqual(
            default_bond_angle_for_vectors([(1.0, 0.0), (-1.0, 0.0)]),
            -90.0,
        )
        self.assertEqual(
            default_bond_angle_for_vectors([(1.0, 0.0), (0.0, 1.0)]),
            -135.0,
        )
