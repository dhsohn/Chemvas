from unittest import mock
from unittest.mock import Mock

from core.model import Atom, Bond, MoleculeModel
from PyQt6.QtCore import QPointF
from ui.canvas_scene_items_state import set_scene_item_collection_for
from ui.structure_benzene_build_service import StructureBenzeneBuildService
from ui.structure_build_committer import StructureBuildCommitter

from tests.test_structure_build_service import _FakeCanvas, _FakeRingItem


def _builder_for(canvas: _FakeCanvas) -> StructureBenzeneBuildService:
    return StructureBenzeneBuildService(canvas, StructureBuildCommitter(canvas))


def test_structure_benzene_build_service_plans_attached_and_free_ring_points() -> None:
    canvas = _FakeCanvas()
    canvas.model = MoleculeModel(
        atoms={
            1: Atom("C", 0.0, 0.0),
            2: Atom("C", 10.0, 0.0),
        },
        bonds=[Bond(1, 2, 1)],
    )
    builder = _builder_for(canvas)
    regular_for_bond = Mock(return_value=([QPointF(1.0, 2.0)], [(1, 0.0, 0.0)]))
    regular_for_atom = Mock(return_value=([QPointF(3.0, 4.0)], [(1, 0.0, 0.0)]))

    bond_result = builder.benzene_ring_points(
        QPointF(5.0, 6.0),
        attach_atom_id=1,
        attach_bond_id=0,
        regular_ring_points_for_bond=regular_for_bond,
        regular_ring_points_for_atom=regular_for_atom,
    )
    atom_result = builder.benzene_ring_points(
        QPointF(5.0, 6.0),
        attach_atom_id=1,
        attach_bond_id=9,
        regular_ring_points_for_bond=regular_for_bond,
        regular_ring_points_for_atom=regular_for_atom,
    )

    assert bond_result == ([QPointF(1.0, 2.0)], [(1, 0.0, 0.0)])
    assert atom_result == ([QPointF(3.0, 4.0)], [(1, 0.0, 0.0)])
    regular_for_bond.assert_called_once_with(6, 0, QPointF(5.0, 6.0))
    regular_for_atom.assert_called_once_with(6, 1)


def test_structure_benzene_build_service_blocks_occupied_free_ring_and_uses_free_fallback() -> None:
    canvas = _FakeCanvas()
    builder = _builder_for(canvas)
    set_scene_item_collection_for(canvas, "ring_items", [_FakeRingItem(True)])

    assert (
        builder.benzene_ring_points(
            QPointF(5.0, 6.0),
            regular_ring_points_for_bond=Mock(),
            regular_ring_points_for_atom=Mock(),
        )
        is None
    )

    set_scene_item_collection_for(canvas, "ring_items", [_FakeRingItem(False)])
    with mock.patch(
        "ui.structure_benzene_build_service.compute_free_benzene_ring_points",
        return_value=[(1.0, 2.0), (3.0, 4.0)],
    ) as free_ring:
        result = builder.benzene_ring_points(
            QPointF(7.0, 8.0),
            regular_ring_points_for_bond=Mock(),
            regular_ring_points_for_atom=Mock(),
        )

    assert result == ([QPointF(1.0, 2.0), QPointF(3.0, 4.0)], [])
    free_ring.assert_called_once_with((7.0, 8.0), bond_length=20.0)


def test_structure_benzene_build_service_adds_ring_item_and_records_scene_item() -> None:
    canvas = _FakeCanvas()
    builder = _builder_for(canvas)

    ring_item = builder.add_benzene_ring(
        QPointF(5.0, 6.0),
        benzene_ring_points=lambda *args, **kwargs: (
            [QPointF(float(index), float(index % 2)) for index in range(6)],
            [],
        ),
        add_atom_with_merge=lambda point, element, merge: canvas.model.add_atom(element, point.x(), point.y()),
        bond_exists=canvas.bond_exists,
        create_ring_fill_item=canvas._create_ring_fill_item,
        run_recorded_build=lambda action, **kwargs: StructureBuildCommitter(canvas).record_additions(
            StructureBuildCommitter(canvas).begin_recorded_change(
                before_smiles_input=kwargs.get("before_smiles_input")
            ),
            added_scene_items=action() or [],
        ),
    )

    assert ring_item == canvas.ring_items[0]
    assert canvas.scene_items == [ring_item]
    assert len(canvas.model.bonds) == 6
    assert canvas.added_graphics == [0, 1, 2, 3, 4, 5]
