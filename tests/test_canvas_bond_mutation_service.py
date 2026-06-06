import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.model import Bond
from ui.canvas_bond_graphics_state import bond_items_for, set_bond_items_for
from ui.canvas_bond_mutation_service import CanvasBondMutationService


class _FakeModel:
    def __init__(self, bonds=None) -> None:
        self.bonds = list(bonds or [])
        self.add_bond_calls = []

    def add_bond(self, a: int, b: int, order: int) -> int:
        self.add_bond_calls.append((a, b, order))
        bond_id = len(self.bonds)
        self.bonds.append(Bond(a, b, order))
        return bond_id


class _FakeScene:
    def __init__(self) -> None:
        self.removed_items = []

    def removeItem(self, item) -> None:
        self.removed_items.append(item)


def _graph_service(*, bond_id_between=None):
    return SimpleNamespace(
        bond_id_between=mock.Mock(return_value=bond_id_between),
        add_bond_neighbors=mock.Mock(),
        remove_bond_neighbors=mock.Mock(),
        add_bond_index=mock.Mock(),
        remove_bond_index=mock.Mock(),
    )


def _hit_testing_service():
    return SimpleNamespace(mark_spatial_index_dirty=mock.Mock())


def _services(*, graph=None, hit_testing=None, bond_mutation=None):
    return SimpleNamespace(
        canvas_graph_service=graph,
        hit_testing_service=hit_testing,
        canvas_bond_mutation_service=bond_mutation,
    )


def _service_for(canvas) -> CanvasBondMutationService:
    return CanvasBondMutationService(
        canvas,
        hit_testing_service=canvas.services.hit_testing_service,
        graph_service=canvas.services.canvas_graph_service,
    )


class CanvasBondMutationServiceTest(unittest.TestCase):
    def test_add_bond_updates_model_and_graph_indexes(self) -> None:
        model = _FakeModel()
        graph = _graph_service()
        hit_testing = _hit_testing_service()
        canvas = SimpleNamespace(
            services=_services(graph=graph, hit_testing=hit_testing),
            model=model,
        )

        bond_id = _service_for(canvas).add_bond(1, 2, 2)

        self.assertEqual(bond_id, 0)
        self.assertEqual(model.add_bond_calls, [(1, 2, 2)])
        self.assertEqual((model.bonds[0].a, model.bonds[0].b, model.bonds[0].order), (1, 2, 2))
        graph.add_bond_neighbors.assert_called_once_with(1, 2)
        graph.add_bond_index.assert_called_once_with(0, 1, 2)
        hit_testing.mark_spatial_index_dirty.assert_called_once_with()

    def test_add_bond_uses_injected_hit_testing_service_for_spatial_dirty_mark(self) -> None:
        model = _FakeModel()
        graph = _graph_service()
        injected_hit_testing = _hit_testing_service()
        registry_hit_testing = SimpleNamespace(
            mark_spatial_index_dirty=mock.Mock(side_effect=AssertionError("registry service should not be used"))
        )
        canvas = SimpleNamespace(
            services=_services(graph=graph, hit_testing=registry_hit_testing),
            model=model,
        )

        bond_id = CanvasBondMutationService(
            canvas,
            hit_testing_service=injected_hit_testing,
            graph_service=graph,
        ).add_bond(1, 2, 2)

        self.assertEqual(bond_id, 0)
        injected_hit_testing.mark_spatial_index_dirty.assert_called_once_with()
        registry_hit_testing.mark_spatial_index_dirty.assert_not_called()

    def test_add_bond_noops_when_duplicate_bond_exists(self) -> None:
        model = _FakeModel([Bond(1, 2, 1)])
        graph = _graph_service(bond_id_between=7)
        hit_testing = _hit_testing_service()
        canvas = SimpleNamespace(
            services=_services(graph=graph, hit_testing=hit_testing),
            model=model,
        )

        bond_id = _service_for(canvas).add_bond(1, 2, 3)

        self.assertEqual(bond_id, 7)
        self.assertEqual(model.add_bond_calls, [])
        graph.add_bond_neighbors.assert_not_called()
        graph.add_bond_index.assert_not_called()
        hit_testing.mark_spatial_index_dirty.assert_not_called()

    def test_restore_bond_from_state_rewires_existing_adjacency_and_indexes(self) -> None:
        scene = _FakeScene()
        old_item = object()
        graph = _graph_service()
        hit_testing = _hit_testing_service()
        canvas = SimpleNamespace(
            services=_services(graph=graph, hit_testing=hit_testing),
            scene=lambda: scene,
            model=SimpleNamespace(bonds=[Bond(1, 2, 1)]),
            bond_renderer=SimpleNamespace(add_bond_graphics=mock.Mock()),
        )
        set_bond_items_for(canvas, {0: [old_item]})

        _service_for(canvas).restore_bond_from_state(
            0,
            {"a": 2, "b": 3, "order": 2, "style": "double", "color": "#334455"},
        )

        self.assertEqual(scene.removed_items, [old_item])
        self.assertEqual((canvas.model.bonds[0].a, canvas.model.bonds[0].b), (2, 3))
        graph.remove_bond_index.assert_called_once_with(0, 1, 2)
        graph.remove_bond_neighbors.assert_called_once_with(1, 2, skip_bond_id=0)
        graph.add_bond_neighbors.assert_called_once_with(2, 3)
        graph.add_bond_index.assert_called_once_with(0, 2, 3)
        canvas.bond_renderer.add_bond_graphics.assert_called_once_with(0)
        hit_testing.mark_spatial_index_dirty.assert_called_once_with()
        self.assertNotIn(0, bond_items_for(canvas))

    def test_restore_bond_from_state_extends_sparse_bond_list(self) -> None:
        graph = _graph_service()
        hit_testing = _hit_testing_service()
        canvas = SimpleNamespace(
            services=_services(graph=graph, hit_testing=hit_testing),
            scene=lambda: _FakeScene(),
            model=SimpleNamespace(bonds=[]),
            bond_renderer=SimpleNamespace(add_bond_graphics=mock.Mock()),
        )
        set_bond_items_for(canvas, {})

        _service_for(canvas).restore_bond_from_state(
            2,
            {"a": 8, "b": 9, "order": 1, "style": "single", "color": "#000000"},
        )

        self.assertEqual(len(canvas.model.bonds), 3)
        self.assertIsNone(canvas.model.bonds[0])
        self.assertIsNone(canvas.model.bonds[1])
        self.assertEqual((canvas.model.bonds[2].a, canvas.model.bonds[2].b), (8, 9))
        graph.remove_bond_index.assert_not_called()
        graph.remove_bond_neighbors.assert_not_called()
        graph.add_bond_neighbors.assert_called_once_with(8, 9)
        graph.add_bond_index.assert_called_once_with(2, 8, 9)
        canvas.bond_renderer.add_bond_graphics.assert_called_once_with(2)
        hit_testing.mark_spatial_index_dirty.assert_called_once_with()

    def test_remove_bond_by_id_cleans_graphics_and_indexes(self) -> None:
        scene = _FakeScene()
        old_item = object()
        graph = _graph_service()
        hit_testing = _hit_testing_service()
        canvas = SimpleNamespace(
            services=_services(graph=graph, hit_testing=hit_testing),
            model=SimpleNamespace(bonds=[Bond(4, 5, 1)]),
            scene=lambda: scene,
        )
        set_bond_items_for(canvas, {0: [old_item]})

        service = _service_for(canvas)
        service.remove_bond_by_id(-1)
        service.remove_bond_by_id(0)

        self.assertEqual(scene.removed_items, [old_item])
        self.assertIsNone(canvas.model.bonds[0])
        graph.remove_bond_index.assert_called_once_with(0, 4, 5)
        graph.remove_bond_neighbors.assert_called_once_with(4, 5, skip_bond_id=0)
        hit_testing.mark_spatial_index_dirty.assert_called_once_with()
        self.assertNotIn(0, bond_items_for(canvas))

    def test_remove_bond_by_id_skips_index_cleanup_for_none_bond(self) -> None:
        scene = _FakeScene()
        old_item = object()
        graph = _graph_service()
        hit_testing = _hit_testing_service()
        canvas = SimpleNamespace(
            services=_services(graph=graph, hit_testing=hit_testing),
            model=SimpleNamespace(bonds=[None]),
            scene=lambda: scene,
        )
        set_bond_items_for(canvas, {0: [old_item]})

        _service_for(canvas).remove_bond_by_id(0)

        self.assertEqual(scene.removed_items, [old_item])
        self.assertIsNone(canvas.model.bonds[0])
        graph.remove_bond_index.assert_not_called()
        graph.remove_bond_neighbors.assert_not_called()
        hit_testing.mark_spatial_index_dirty.assert_called_once_with()

    def test_trim_bonds_to_length_removes_tail_cleanup(self) -> None:
        scene = _FakeScene()
        tail_item = object()
        graph = _graph_service()
        hit_testing = _hit_testing_service()
        canvas = SimpleNamespace(
            services=_services(graph=graph, hit_testing=hit_testing),
            model=SimpleNamespace(bonds=[Bond(1, 2, 1), None, Bond(2, 3, 2)]),
            scene=lambda: scene,
        )
        set_bond_items_for(canvas, {1: [object()], 2: [tail_item]})

        service = _service_for(canvas)
        service.trim_bonds_to_length(-1)
        service.trim_bonds_to_length(3)
        service.trim_bonds_to_length(1)

        self.assertEqual(len(canvas.model.bonds), 1)
        self.assertEqual(len(scene.removed_items), 2)
        graph.remove_bond_index.assert_called_once_with(2, 2, 3)
        graph.remove_bond_neighbors.assert_called_once_with(2, 3, skip_bond_id=2)
        hit_testing.mark_spatial_index_dirty.assert_called_once_with()
        self.assertNotIn(1, bond_items_for(canvas))
        self.assertNotIn(2, bond_items_for(canvas))

    def test_restore_bond_from_state_ignores_empty_state(self) -> None:
        hit_testing = _hit_testing_service()
        canvas = SimpleNamespace(
            services=_services(graph=_graph_service(), hit_testing=hit_testing),
            scene=lambda: _FakeScene(),
            model=SimpleNamespace(bonds=[]),
            bond_renderer=SimpleNamespace(add_bond_graphics=mock.Mock()),
        )
        set_bond_items_for(canvas, {})

        _service_for(canvas).restore_bond_from_state(0, {})
        canvas.bond_renderer.add_bond_graphics.assert_not_called()
        hit_testing.mark_spatial_index_dirty.assert_not_called()


if __name__ == "__main__":
    unittest.main()
