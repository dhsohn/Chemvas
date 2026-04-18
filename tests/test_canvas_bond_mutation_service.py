import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.model import Bond
from ui.canvas_bond_mutation_service import CanvasBondMutationService


class _FakeModel:
    def __init__(self, bonds=None) -> None:
        self.bonds = list(bonds or [])
        self.add_bond_calls = []

    def add_bond(self, a: int, b: int, order: int) -> None:
        self.add_bond_calls.append((a, b, order))
        self.bonds.append(Bond(a, b, order))


class _FakeScene:
    def __init__(self) -> None:
        self.removed_items = []

    def removeItem(self, item) -> None:
        self.removed_items.append(item)


class CanvasBondMutationServiceTest(unittest.TestCase):
    def test_add_bond_updates_model_and_graph_indexes(self) -> None:
        model = _FakeModel()
        canvas = SimpleNamespace(
            _bond_id_between=mock.Mock(return_value=None),
            model=model,
            _add_bond_neighbors=mock.Mock(),
            _add_bond_index=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
        )

        bond_id = CanvasBondMutationService(canvas).add_bond(1, 2, 2)

        self.assertEqual(bond_id, 0)
        self.assertEqual(model.add_bond_calls, [(1, 2, 2)])
        self.assertEqual((model.bonds[0].a, model.bonds[0].b, model.bonds[0].order), (1, 2, 2))
        canvas._add_bond_neighbors.assert_called_once_with(1, 2)
        canvas._add_bond_index.assert_called_once_with(0, 1, 2)
        canvas._mark_spatial_index_dirty.assert_called_once_with()

    def test_add_bond_noops_when_duplicate_bond_exists(self) -> None:
        model = _FakeModel([Bond(1, 2, 1)])
        canvas = SimpleNamespace(
            _bond_id_between=mock.Mock(return_value=7),
            model=model,
            _add_bond_neighbors=mock.Mock(),
            _add_bond_index=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
        )

        bond_id = CanvasBondMutationService(canvas).add_bond(1, 2, 3)

        self.assertEqual(bond_id, 7)
        self.assertEqual(model.add_bond_calls, [])
        canvas._add_bond_neighbors.assert_not_called()
        canvas._add_bond_index.assert_not_called()
        canvas._mark_spatial_index_dirty.assert_not_called()

    def test_restore_bond_from_state_rewires_existing_adjacency_and_indexes(self) -> None:
        scene = _FakeScene()
        old_item = object()
        canvas = SimpleNamespace(
            bond_items={0: [old_item]},
            scene=lambda: scene,
            model=SimpleNamespace(bonds=[Bond(1, 2, 1)]),
            _remove_bond_index=mock.Mock(),
            _remove_bond_neighbors=mock.Mock(),
            _add_bond_neighbors=mock.Mock(),
            _add_bond_index=mock.Mock(),
            _add_bond_graphics=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
        )

        CanvasBondMutationService(canvas).restore_bond_from_state(
            0,
            {"a": 2, "b": 3, "order": 2, "style": "double", "color": "#334455"},
        )

        self.assertEqual(scene.removed_items, [old_item])
        self.assertEqual((canvas.model.bonds[0].a, canvas.model.bonds[0].b), (2, 3))
        canvas._remove_bond_index.assert_called_once_with(0, 1, 2)
        canvas._remove_bond_neighbors.assert_called_once_with(1, 2, skip_bond_id=0)
        canvas._add_bond_neighbors.assert_called_once_with(2, 3)
        canvas._add_bond_index.assert_called_once_with(0, 2, 3)
        canvas._add_bond_graphics.assert_called_once_with(0)
        canvas._mark_spatial_index_dirty.assert_called_once_with()
        self.assertNotIn(0, canvas.bond_items)

    def test_restore_bond_from_state_extends_sparse_bond_list(self) -> None:
        canvas = SimpleNamespace(
            bond_items={},
            scene=lambda: _FakeScene(),
            model=SimpleNamespace(bonds=[]),
            _remove_bond_index=mock.Mock(),
            _remove_bond_neighbors=mock.Mock(),
            _add_bond_neighbors=mock.Mock(),
            _add_bond_index=mock.Mock(),
            _add_bond_graphics=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
        )

        CanvasBondMutationService(canvas).restore_bond_from_state(
            2,
            {"a": 8, "b": 9, "order": 1, "style": "single", "color": "#000000"},
        )

        self.assertEqual(len(canvas.model.bonds), 3)
        self.assertIsNone(canvas.model.bonds[0])
        self.assertIsNone(canvas.model.bonds[1])
        self.assertEqual((canvas.model.bonds[2].a, canvas.model.bonds[2].b), (8, 9))
        canvas._remove_bond_index.assert_not_called()
        canvas._remove_bond_neighbors.assert_not_called()
        canvas._add_bond_neighbors.assert_called_once_with(8, 9)
        canvas._add_bond_index.assert_called_once_with(2, 8, 9)
        canvas._add_bond_graphics.assert_called_once_with(2)
        canvas._mark_spatial_index_dirty.assert_called_once_with()

    def test_remove_bond_by_id_cleans_graphics_and_indexes(self) -> None:
        scene = _FakeScene()
        old_item = object()
        canvas = SimpleNamespace(
            model=SimpleNamespace(bonds=[Bond(4, 5, 1)]),
            bond_items={0: [old_item]},
            scene=lambda: scene,
            _remove_bond_index=mock.Mock(),
            _remove_bond_neighbors=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
        )

        service = CanvasBondMutationService(canvas)
        service.remove_bond_by_id(-1)
        service.remove_bond_by_id(0)

        self.assertEqual(scene.removed_items, [old_item])
        self.assertIsNone(canvas.model.bonds[0])
        canvas._remove_bond_index.assert_called_once_with(0, 4, 5)
        canvas._remove_bond_neighbors.assert_called_once_with(4, 5, skip_bond_id=0)
        canvas._mark_spatial_index_dirty.assert_called_once_with()
        self.assertNotIn(0, canvas.bond_items)

    def test_trim_bonds_to_length_removes_tail_cleanup(self) -> None:
        scene = _FakeScene()
        tail_item = object()
        canvas = SimpleNamespace(
            model=SimpleNamespace(bonds=[Bond(1, 2, 1), None, Bond(2, 3, 2)]),
            bond_items={1: [object()], 2: [tail_item]},
            scene=lambda: scene,
            _remove_bond_index=mock.Mock(),
            _remove_bond_neighbors=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
        )

        service = CanvasBondMutationService(canvas)
        service.trim_bonds_to_length(-1)
        service.trim_bonds_to_length(3)
        service.trim_bonds_to_length(1)

        self.assertEqual(len(canvas.model.bonds), 1)
        self.assertEqual(len(scene.removed_items), 2)
        canvas._remove_bond_index.assert_called_once_with(2, 2, 3)
        canvas._remove_bond_neighbors.assert_called_once_with(2, 3, skip_bond_id=2)
        canvas._mark_spatial_index_dirty.assert_called_once_with()
        self.assertNotIn(1, canvas.bond_items)
        self.assertNotIn(2, canvas.bond_items)


if __name__ == "__main__":
    unittest.main()
