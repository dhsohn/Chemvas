import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor

from core.model import Atom, Bond
from ui.canvas_atom_mutation_service import CanvasAtomMutationService, canvas_atom_mutation_service_for


class _FakeModel:
    def __init__(self, atoms=None, bonds=None, next_atom_id: int = 0) -> None:
        self.atoms = dict(atoms or {})
        self.bonds = list(bonds or [])
        self.next_atom_id = next_atom_id

    def add_atom(self, element: str, x: float, y: float) -> int:
        atom_id = self.next_atom_id
        self.atoms[atom_id] = Atom(element, x, y)
        self.next_atom_id += 1
        return atom_id


class _FakeScene:
    def __init__(self) -> None:
        self.removed_items = []

    def removeItem(self, item) -> None:
        self.removed_items.append(item)


class CanvasAtomMutationServiceTest(unittest.TestCase):
    def test_add_atom_registers_graph_state_and_implicit_carbon_dot(self) -> None:
        model = _FakeModel(next_atom_id=3)
        canvas = SimpleNamespace(
            model=model,
            _ensure_atom_neighbors=mock.Mock(),
            _ensure_atom_bond_ids=mock.Mock(),
            _ensure_carbon_dot=mock.Mock(),
            _atom_label_service=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
        )

        atom_id = CanvasAtomMutationService(canvas).add_atom("C", 1.0, 2.0)

        self.assertEqual(atom_id, 3)
        self.assertEqual(model.atoms[3].element, "C")
        canvas._ensure_atom_neighbors.assert_called_once_with(3)
        canvas._ensure_atom_bond_ids.assert_called_once_with(3)
        canvas._ensure_carbon_dot.assert_called_once_with(3)
        canvas._atom_label_service.add_or_update_atom_label.assert_not_called()
        canvas._mark_spatial_index_dirty.assert_called_once_with()

    def test_add_atom_uses_atom_label_service_for_non_carbon(self) -> None:
        canvas = SimpleNamespace(
            model=_FakeModel(),
            _ensure_atom_neighbors=mock.Mock(),
            _ensure_atom_bond_ids=mock.Mock(),
            _ensure_carbon_dot=mock.Mock(),
            _atom_label_service=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
        )

        atom_id = CanvasAtomMutationService(canvas).add_atom("O", -1.5, 3.25)

        self.assertEqual(atom_id, 0)
        canvas._ensure_carbon_dot.assert_not_called()
        canvas._atom_label_service.add_or_update_atom_label.assert_called_once_with(
            0,
            "O",
            clear_smiles=False,
            record=False,
        )

    def test_remove_atom_only_cleans_scene_state_graph_links_and_bond_ids(self) -> None:
        scene = _FakeScene()
        label_item = object()
        dot_item = object()
        canvas = SimpleNamespace(
            atom_items={1: label_item},
            atom_dots={1: dot_item},
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 2.0, 0.0)},
                bonds=[Bond(1, 2, 1)],
            ),
            atom_coords_3d={1: (0.0, 0.0, 0.0)},
            _atom_neighbors={1: {2}, 2: {1}},
            _graph_version=4,
            _selection_component_cache_signature="cached",
            _atom_bond_ids={1: {0}, 2: {0}},
            _remove_marks_for_atom=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
            scene=lambda: scene,
        )

        CanvasAtomMutationService(canvas).remove_atom_only(1)

        self.assertEqual(scene.removed_items, [label_item, dot_item])
        canvas._remove_marks_for_atom.assert_called_once_with(1)
        self.assertNotIn(1, canvas.model.atoms)
        self.assertNotIn(1, canvas.atom_coords_3d)
        self.assertNotIn(1, canvas._atom_neighbors)
        self.assertEqual(canvas._atom_neighbors[2], set())
        self.assertEqual(canvas._graph_version, 5)
        self.assertIsNone(canvas._selection_component_cache_signature)
        self.assertEqual(canvas._atom_bond_ids[2], set())
        canvas._mark_spatial_index_dirty.assert_called_once_with()

    def test_remove_atom_only_skips_mark_removal_when_requested(self) -> None:
        canvas = SimpleNamespace(
            atom_items={},
            atom_dots={},
            model=SimpleNamespace(atoms={}, bonds=[]),
            atom_coords_3d={},
            _atom_neighbors={},
            _graph_version=0,
            _selection_component_cache_signature=None,
            _atom_bond_ids={},
            _remove_marks_for_atom=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
            scene=lambda: _FakeScene(),
        )

        CanvasAtomMutationService(canvas).remove_atom_only(3, remove_marks=False)

        canvas._remove_marks_for_atom.assert_not_called()
        canvas._mark_spatial_index_dirty.assert_called_once_with()

    def test_restore_atom_from_state_replaces_visuals_and_advances_next_atom_id(self) -> None:
        scene = _FakeScene()
        old_label = object()
        old_dot = object()
        canvas = SimpleNamespace(
            model=_FakeModel(next_atom_id=1),
            atom_items={4: old_label},
            atom_dots={4: old_dot},
            scene=lambda: scene,
            _ensure_atom_neighbors=mock.Mock(),
            _ensure_atom_bond_ids=mock.Mock(),
            _atom_label_service=mock.Mock(),
            _ensure_carbon_dot=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
        )
        service = CanvasAtomMutationService(canvas)
        service.apply_atom_color = mock.Mock()

        service.restore_atom_from_state(
            4,
            {"element": "C", "x": 3.0, "y": 4.0, "color": "#00ff00", "explicit_label": True},
        )

        self.assertEqual(scene.removed_items, [old_label, old_dot])
        self.assertEqual(canvas.model.next_atom_id, 5)
        canvas._ensure_atom_neighbors.assert_called_once_with(4)
        canvas._ensure_atom_bond_ids.assert_called_once_with(4)
        canvas._atom_label_service.add_or_update_atom_label.assert_called_once_with(
            4,
            "C",
            clear_smiles=False,
            record=False,
            allow_merge=False,
            show_carbon=True,
        )
        canvas._ensure_carbon_dot.assert_not_called()
        service.apply_atom_color.assert_called_once_with(4, "#00ff00")
        canvas._mark_spatial_index_dirty.assert_called_once_with()

    def test_restore_atom_from_state_uses_implicit_carbon_dot_when_label_is_not_explicit(self) -> None:
        canvas = SimpleNamespace(
            model=_FakeModel(next_atom_id=0),
            atom_items={},
            atom_dots={},
            scene=lambda: _FakeScene(),
            _ensure_atom_neighbors=mock.Mock(),
            _ensure_atom_bond_ids=mock.Mock(),
            _atom_label_service=mock.Mock(),
            _ensure_carbon_dot=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
        )

        CanvasAtomMutationService(canvas).restore_atom_from_state(
            2,
            {"element": "C", "x": 0.0, "y": 0.0, "color": "#000000", "explicit_label": False},
        )

        canvas._ensure_carbon_dot.assert_called_once_with(2)
        canvas._atom_label_service.add_or_update_atom_label.assert_not_called()

    def test_apply_atom_color_updates_model_and_visible_items_for_valid_color(self) -> None:
        canvas = SimpleNamespace(
            model=SimpleNamespace(atoms={7: Atom("O", 0.0, 0.0, color="#101010")}),
            atom_items={7: mock.Mock()},
            atom_dots={7: mock.Mock()},
            _implicit_carbon_dot_brush=mock.Mock(return_value="brush"),
        )

        CanvasAtomMutationService(canvas).apply_atom_color(7, QColor("#aabbcc"))

        self.assertEqual(canvas.model.atoms[7].color, "#aabbcc")
        canvas.atom_items[7].setDefaultTextColor.assert_called_once()
        canvas.atom_dots[7].setBrush.assert_called_once_with("brush")

    def test_apply_atom_color_ignores_invalid_color_and_missing_atom(self) -> None:
        canvas = SimpleNamespace(
            model=SimpleNamespace(atoms={7: Atom("O", 0.0, 0.0, color="#101010")}),
            atom_items={7: mock.Mock()},
            atom_dots={7: mock.Mock()},
            _implicit_carbon_dot_brush=mock.Mock(return_value="brush"),
        )

        service = CanvasAtomMutationService(canvas)
        service.apply_atom_color(7, "not-a-color")
        service.apply_atom_color(99, "#ffffff")

        self.assertEqual(canvas.model.atoms[7].color, "#101010")
        canvas.atom_items[7].setDefaultTextColor.assert_not_called()
        canvas.atom_dots[7].setBrush.assert_not_called()

    def test_remove_atom_only_tolerates_sparse_neighbor_and_bond_indexes(self) -> None:
        canvas = SimpleNamespace(
            atom_items={},
            atom_dots={},
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0)},
                bonds=[None, Bond(1, 9, 1)],
            ),
            atom_coords_3d={},
            _atom_neighbors={1: {2, 3}, 2: {1}},
            _graph_version=7,
            _selection_component_cache_signature="cached",
            _atom_bond_ids={1: {0, 1, 8}, 2: set()},
            _remove_marks_for_atom=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
            scene=lambda: _FakeScene(),
        )

        CanvasAtomMutationService(canvas).remove_atom_only(1)

        self.assertEqual(canvas._atom_neighbors[2], set())
        self.assertEqual(canvas._graph_version, 8)
        self.assertIsNone(canvas._selection_component_cache_signature)
        canvas._mark_spatial_index_dirty.assert_called_once_with()

    def test_restore_atom_from_state_skips_empty_input_and_labels_noncarbon_atoms(self) -> None:
        canvas = SimpleNamespace(
            model=_FakeModel(next_atom_id=10),
            atom_items={},
            atom_dots={},
            scene=lambda: _FakeScene(),
            _ensure_atom_neighbors=mock.Mock(),
            _ensure_atom_bond_ids=mock.Mock(),
            _atom_label_service=mock.Mock(),
            _ensure_carbon_dot=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
        )
        service = CanvasAtomMutationService(canvas)
        service.apply_atom_color = mock.Mock()

        service.restore_atom_from_state(5, {})
        canvas._ensure_atom_neighbors.assert_not_called()
        canvas._atom_label_service.add_or_update_atom_label.assert_not_called()

        service.restore_atom_from_state(
            5,
            {"element": "O", "x": 1.0, "y": 2.0, "color": "#123456", "explicit_label": False},
        )

        canvas._ensure_atom_neighbors.assert_called_once_with(5)
        canvas._ensure_atom_bond_ids.assert_called_once_with(5)
        canvas._atom_label_service.add_or_update_atom_label.assert_called_once_with(
            5,
            "O",
            clear_smiles=False,
            record=False,
            allow_merge=False,
        )
        canvas._ensure_carbon_dot.assert_not_called()
        service.apply_atom_color.assert_called_once_with(5, "#123456")
        self.assertEqual(canvas.model.next_atom_id, 10)

    def test_service_factory_returns_bound_service(self) -> None:
        canvas = SimpleNamespace()
        real_service = CanvasAtomMutationService(canvas)
        canvas._canvas_atom_mutation_service = real_service
        self.assertIs(canvas_atom_mutation_service_for(canvas), real_service)

        duck_service = SimpleNamespace(
            add_atom=mock.Mock(),
            remove_atom_only=mock.Mock(),
            restore_atom_from_state=mock.Mock(),
            apply_atom_color=mock.Mock(),
        )
        canvas._canvas_atom_mutation_service = duck_service
        self.assertIs(canvas_atom_mutation_service_for(canvas), duck_service)

        placeholder = object()
        canvas._canvas_atom_mutation_service = placeholder
        self.assertIs(canvas_atom_mutation_service_for(canvas), placeholder)


if __name__ == "__main__":
    unittest.main()
