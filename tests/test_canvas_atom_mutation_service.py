import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.model import Atom, Bond
from PyQt6.QtGui import QColor
from ui.atom_coords_access import atom_coords_3d_for, set_atom_coords_3d_for
from ui.canvas_atom_graphics_state import (
    atom_dots_for,
    atom_items_for,
    set_atom_dots_for,
    set_atom_items_for,
)
from ui.canvas_atom_mutation_service import CanvasAtomMutationService
from ui.canvas_graph_state import CanvasGraphState


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


def _graph_service():
    return SimpleNamespace(
        ensure_atom_neighbors=mock.Mock(),
        ensure_atom_bond_ids=mock.Mock(),
    )


def _hit_testing_service():
    return SimpleNamespace(mark_spatial_index_dirty=mock.Mock())


def _services(
    *,
    graph=None,
    atom_label=None,
    hit_testing=None,
    mark_scene=None,
    atom_mutation=None,
):
    return SimpleNamespace(
        canvas_graph_service=graph,
        atom_label_service=atom_label,
        hit_testing_service=hit_testing,
        canvas_mark_scene_service=mark_scene,
        canvas_atom_mutation_service=atom_mutation,
    )


def _set_atom_graphics(canvas, items=None, dots=None) -> None:
    set_atom_items_for(canvas, dict(items or {}))
    set_atom_dots_for(canvas, dict(dots or {}))


def _service_for(canvas) -> CanvasAtomMutationService:
    return CanvasAtomMutationService(
        canvas,
        hit_testing_service=canvas.services.hit_testing_service,
        graph_service=canvas.services.canvas_graph_service,
    )


class CanvasAtomMutationServiceTest(unittest.TestCase):
    def test_add_atom_registers_graph_state_and_implicit_carbon_dot(self) -> None:
        model = _FakeModel(next_atom_id=3)
        graph = _graph_service()
        atom_label = mock.Mock()
        hit_testing = _hit_testing_service()
        canvas = SimpleNamespace(
            services=_services(graph=graph, atom_label=atom_label, hit_testing=hit_testing),
            model=model,
        )

        atom_id = _service_for(canvas).add_atom("C", 1.0, 2.0)

        self.assertEqual(atom_id, 3)
        self.assertEqual(model.atoms[3].element, "C")
        graph.ensure_atom_neighbors.assert_called_once_with(3)
        graph.ensure_atom_bond_ids.assert_called_once_with(3)
        atom_label.ensure_carbon_dot.assert_called_once_with(3)
        atom_label.add_or_update_atom_label.assert_not_called()
        hit_testing.mark_spatial_index_dirty.assert_called_once_with()

    def test_add_atom_uses_injected_hit_testing_service_for_spatial_dirty_mark(self) -> None:
        model = _FakeModel(next_atom_id=3)
        graph = _graph_service()
        atom_label = mock.Mock()
        injected_hit_testing = _hit_testing_service()
        registry_hit_testing = SimpleNamespace(
            mark_spatial_index_dirty=mock.Mock(side_effect=AssertionError("registry service should not be used"))
        )
        canvas = SimpleNamespace(
            services=_services(graph=graph, atom_label=atom_label, hit_testing=registry_hit_testing),
            model=model,
        )

        atom_id = CanvasAtomMutationService(
            canvas,
            hit_testing_service=injected_hit_testing,
            graph_service=graph,
        ).add_atom("C", 1.0, 2.0)

        self.assertEqual(atom_id, 3)
        injected_hit_testing.mark_spatial_index_dirty.assert_called_once_with()
        registry_hit_testing.mark_spatial_index_dirty.assert_not_called()

    def test_add_atom_uses_atom_label_service_for_non_carbon(self) -> None:
        atom_label = mock.Mock()
        canvas = SimpleNamespace(
            services=_services(graph=_graph_service(), atom_label=atom_label, hit_testing=_hit_testing_service()),
            model=_FakeModel(),
        )

        atom_id = _service_for(canvas).add_atom("O", -1.5, 3.25)

        self.assertEqual(atom_id, 0)
        atom_label.ensure_carbon_dot.assert_not_called()
        atom_label.add_or_update_atom_label.assert_called_once_with(
            0,
            "O",
            clear_smiles=False,
            record=False,
        )

    def test_remove_atom_only_cleans_scene_state_graph_links_and_bond_ids(self) -> None:
        scene = _FakeScene()
        label_item = object()
        dot_item = object()
        mark_scene = SimpleNamespace(remove_marks_for_atom=mock.Mock())
        hit_testing = _hit_testing_service()
        canvas = SimpleNamespace(
            services=_services(mark_scene=mark_scene, hit_testing=hit_testing),
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 2.0, 0.0)},
                bonds=[Bond(1, 2, 1)],
                atom_annotations={1: {"formal_charge": 1}},
            ),
            graph_state=CanvasGraphState(
                atom_neighbors={1: {2}, 2: {1}},
                graph_version=4,
                selection_component_cache_signature="cached",
                atom_bond_ids={1: {0}, 2: {0}},
            ),
            scene=lambda: scene,
        )
        set_atom_coords_3d_for(canvas, {1: (0.0, 0.0, 0.0)})
        _set_atom_graphics(canvas, {1: label_item}, {1: dot_item})

        _service_for(canvas).remove_atom_only(1)

        self.assertEqual(scene.removed_items, [label_item, dot_item])
        mark_scene.remove_marks_for_atom.assert_called_once_with(1)
        self.assertNotIn(1, canvas.model.atoms)
        self.assertNotIn(1, canvas.model.atom_annotations)
        self.assertNotIn(1, atom_coords_3d_for(canvas))
        self.assertNotIn(1, canvas.graph_state.atom_neighbors)
        self.assertEqual(canvas.graph_state.atom_neighbors[2], set())
        self.assertEqual(canvas.graph_state.graph_version, 5)
        self.assertIsNone(canvas.graph_state.selection_component_cache_signature)
        self.assertEqual(canvas.graph_state.atom_bond_ids[2], set())
        hit_testing.mark_spatial_index_dirty.assert_called_once_with()

    def test_remove_atom_only_skips_mark_removal_when_requested(self) -> None:
        mark_scene = SimpleNamespace(remove_marks_for_atom=mock.Mock())
        hit_testing = _hit_testing_service()
        canvas = SimpleNamespace(
            services=_services(mark_scene=mark_scene, hit_testing=hit_testing),
            model=SimpleNamespace(atoms={}, bonds=[]),
            atom_coords_3d={},
            graph_state=CanvasGraphState(),
            scene=lambda: _FakeScene(),
        )
        _set_atom_graphics(canvas)

        _service_for(canvas).remove_atom_only(3, remove_marks=False)

        mark_scene.remove_marks_for_atom.assert_not_called()
        hit_testing.mark_spatial_index_dirty.assert_called_once_with()

    def test_restore_atom_from_state_replaces_visuals_and_advances_next_atom_id(self) -> None:
        scene = _FakeScene()
        old_label = object()
        old_dot = object()
        graph = _graph_service()
        atom_label = mock.Mock()
        hit_testing = _hit_testing_service()
        canvas = SimpleNamespace(
            services=_services(graph=graph, atom_label=atom_label, hit_testing=hit_testing),
            model=_FakeModel(next_atom_id=1),
            scene=lambda: scene,
        )
        _set_atom_graphics(canvas, {4: old_label}, {4: old_dot})
        service = _service_for(canvas)
        service.apply_atom_color = mock.Mock()

        service.restore_atom_from_state(
            4,
            {
                "element": "C",
                "x": 3.0,
                "y": 4.0,
                "color": "#00ff00",
                "explicit_label": True,
                "annotation": {"formal_charge": 1},
            },
        )

        self.assertEqual(scene.removed_items, [old_label, old_dot])
        self.assertEqual(canvas.model.next_atom_id, 5)
        self.assertEqual(canvas.model.atom_annotations, {4: {"formal_charge": 1}})
        graph.ensure_atom_neighbors.assert_called_once_with(4)
        graph.ensure_atom_bond_ids.assert_called_once_with(4)
        atom_label.add_or_update_atom_label.assert_called_once_with(
            4,
            "C",
            clear_smiles=False,
            record=False,
            allow_merge=False,
            show_carbon=True,
        )
        atom_label.ensure_carbon_dot.assert_not_called()
        service.apply_atom_color.assert_called_once_with(4, "#00ff00")
        hit_testing.mark_spatial_index_dirty.assert_called_once_with()

    def test_restore_atom_from_state_uses_implicit_carbon_dot_when_label_is_not_explicit(self) -> None:
        atom_label = mock.Mock()
        canvas = SimpleNamespace(
            services=_services(graph=_graph_service(), atom_label=atom_label, hit_testing=_hit_testing_service()),
            model=_FakeModel(next_atom_id=0),
            scene=lambda: _FakeScene(),
        )
        _set_atom_graphics(canvas)

        _service_for(canvas).restore_atom_from_state(
            2,
            {"element": "C", "x": 0.0, "y": 0.0, "color": "#000000", "explicit_label": False},
        )

        atom_label.ensure_carbon_dot.assert_called_once_with(2)
        atom_label.add_or_update_atom_label.assert_not_called()

    def test_apply_atom_color_updates_model_and_visible_items_for_valid_color(self) -> None:
        atom_label = SimpleNamespace(implicit_carbon_dot_brush=mock.Mock(return_value="brush"))
        canvas = SimpleNamespace(
            services=_services(atom_label=atom_label),
            model=SimpleNamespace(atoms={7: Atom("O", 0.0, 0.0, color="#101010")}),
        )
        _set_atom_graphics(canvas, {7: mock.Mock()}, {7: mock.Mock()})

        _service_for(canvas).apply_atom_color(7, QColor("#aabbcc"))

        self.assertEqual(canvas.model.atoms[7].color, "#aabbcc")
        atom_items_for(canvas)[7].setDefaultTextColor.assert_called_once()
        atom_dots_for(canvas)[7].setBrush.assert_called_once_with("brush")

    def test_apply_atom_color_ignores_invalid_color_and_missing_atom(self) -> None:
        atom_label = SimpleNamespace(implicit_carbon_dot_brush=mock.Mock(return_value="brush"))
        canvas = SimpleNamespace(
            services=_services(atom_label=atom_label),
            model=SimpleNamespace(atoms={7: Atom("O", 0.0, 0.0, color="#101010")}),
        )
        _set_atom_graphics(canvas, {7: mock.Mock()}, {7: mock.Mock()})

        service = _service_for(canvas)
        service.apply_atom_color(7, "not-a-color")
        service.apply_atom_color(99, "#ffffff")

        self.assertEqual(canvas.model.atoms[7].color, "#101010")
        atom_items_for(canvas)[7].setDefaultTextColor.assert_not_called()
        atom_dots_for(canvas)[7].setBrush.assert_not_called()

    def test_remove_atom_only_tolerates_sparse_neighbor_and_bond_indexes(self) -> None:
        hit_testing = _hit_testing_service()
        canvas = SimpleNamespace(
            services=_services(
                mark_scene=SimpleNamespace(remove_marks_for_atom=mock.Mock()),
                hit_testing=hit_testing,
            ),
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0)},
                bonds=[None, Bond(1, 9, 1)],
            ),
            atom_coords_3d={},
            graph_state=CanvasGraphState(
                atom_neighbors={1: {2, 3}, 2: {1}},
                graph_version=7,
                selection_component_cache_signature="cached",
                atom_bond_ids={1: {0, 1, 8}, 2: set()},
            ),
            scene=lambda: _FakeScene(),
        )
        _set_atom_graphics(canvas)

        _service_for(canvas).remove_atom_only(1)

        self.assertEqual(canvas.graph_state.atom_neighbors[2], set())
        self.assertEqual(canvas.graph_state.graph_version, 8)
        self.assertIsNone(canvas.graph_state.selection_component_cache_signature)
        hit_testing.mark_spatial_index_dirty.assert_called_once_with()

    def test_restore_atom_from_state_skips_empty_input_and_labels_noncarbon_atoms(self) -> None:
        graph = _graph_service()
        atom_label = mock.Mock()
        canvas = SimpleNamespace(
            services=_services(graph=graph, atom_label=atom_label, hit_testing=_hit_testing_service()),
            model=_FakeModel(next_atom_id=10),
            scene=lambda: _FakeScene(),
        )
        _set_atom_graphics(canvas)
        service = _service_for(canvas)
        service.apply_atom_color = mock.Mock()

        service.restore_atom_from_state(5, {})
        graph.ensure_atom_neighbors.assert_not_called()
        atom_label.add_or_update_atom_label.assert_not_called()

        service.restore_atom_from_state(
            5,
            {"element": "O", "x": 1.0, "y": 2.0, "color": "#123456", "explicit_label": False},
        )

        graph.ensure_atom_neighbors.assert_called_once_with(5)
        graph.ensure_atom_bond_ids.assert_called_once_with(5)
        atom_label.add_or_update_atom_label.assert_called_once_with(
            5,
            "O",
            clear_smiles=False,
            record=False,
            allow_merge=False,
        )
        atom_label.ensure_carbon_dot.assert_not_called()
        service.apply_atom_color.assert_called_once_with(5, "#123456")
        self.assertEqual(canvas.model.next_atom_id, 10)


if __name__ == "__main__":
    unittest.main()
