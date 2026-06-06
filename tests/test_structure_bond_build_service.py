from unittest import mock
from unittest.mock import Mock

from PyQt6.QtCore import QPointF
from ui.structure_bond_build_service import StructureBondBuildService
from ui.structure_build_committer import StructureBuildCommitter

from tests.test_structure_build_service import _FakeCanvas


def _builder_for(canvas: _FakeCanvas) -> StructureBondBuildService:
    return StructureBondBuildService(
        canvas,
        StructureBuildCommitter(canvas),
        hit_testing_service=canvas.services.hit_testing_service,
        move_controller=canvas.services.move_controller,
        graph_service=canvas.services.canvas_graph_service,
    )


def test_structure_bond_build_service_creates_bond_and_records_additions() -> None:
    canvas = _FakeCanvas()
    builder = _builder_for(canvas)

    result = builder.add_bond_between_points(QPointF(0.0, 0.0), QPointF(10.0, 0.0), "double", 2)

    assert result == (0, 1)
    assert len(canvas.model.bonds) == 1
    assert (canvas.model.bonds[0].style, canvas.model.bonds[0].order) == ("double", 2)
    assert canvas.added_graphics == [0]
    assert canvas.redrawn_connected == [(0, 0), (1, 0)]
    assert canvas.record_calls == [
        {
            "before_next_atom_id": 0,
            "before_bond_count": 0,
            "before_smiles_input": "before",
        }
    ]


def test_structure_bond_build_service_updates_existing_bond_without_recording_addition() -> None:
    canvas = _FakeCanvas()
    builder = _builder_for(canvas)
    builder.add_bond_between_points(QPointF(0.0, 0.0), QPointF(10.0, 0.0), "single", 1)
    canvas.record_calls.clear()
    canvas.hit_testing_find_atom_near = Mock(side_effect=[0, 1])
    canvas.services.hit_testing_service.find_atom_near = canvas.hit_testing_find_atom_near
    builder = _builder_for(canvas)

    result = builder.add_bond_between_points(QPointF(0.0, 0.0), QPointF(10.0, 0.0), "wedge", 1)

    assert result == (0, 1)
    assert canvas.redrawn_bonds == [0]
    assert canvas.redrawn_connected[-2:] == [(0, 0), (1, 0)]
    assert len(canvas.recorded_bond_updates) == 1
    assert canvas.record_calls == []


def test_structure_bond_build_service_uses_hit_testing_service_for_snap_lookup() -> None:
    canvas = _FakeCanvas()
    hit_testing_service = mock.Mock()
    hit_testing_service.find_atom_near = Mock(side_effect=[None, None])
    registry_hit_testing_service = mock.Mock()
    registry_hit_testing_service.find_atom_near = Mock(side_effect=AssertionError("registry service should not be used"))
    canvas.services.hit_testing_service = registry_hit_testing_service
    canvas.find_atom_near = Mock(side_effect=AssertionError("canvas facade should not be used"))
    builder = StructureBondBuildService(
        canvas,
        StructureBuildCommitter(canvas),
        hit_testing_service=hit_testing_service,
        move_controller=canvas.services.move_controller,
        graph_service=canvas.services.canvas_graph_service,
    )

    result = builder.add_bond_between_points(QPointF(0.0, 0.0), QPointF(10.0, 0.0), "single", 1)

    assert result == (0, 1)
    assert hit_testing_service.find_atom_near.call_args_list == [
        mock.call(0.0, 0.0, 2.0),
        mock.call(10.0, 0.0, 2.0),
    ]
    registry_hit_testing_service.find_atom_near.assert_not_called()
    canvas.find_atom_near.assert_not_called()
