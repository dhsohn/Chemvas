import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.core.history import (
        CompositeCommand,
        DeleteAtomsCommand,
        DeleteBondCommand,
    )
    from chemvas.domain.document import Atom, Bond
    from chemvas.ui.canvas_bond_graphics_state import bond_items_for, set_bond_items_for
    from chemvas.ui.canvas_mark_registry import CanvasMarkRegistry
    from chemvas.ui.canvas_smiles_input_state import (
        CanvasSmilesInputState,
        last_smiles_input_for,
    )
    from chemvas.ui.history_commands import DeleteSceneItemsCommand
    from chemvas.ui.scene_delete_controller import SceneDeleteController
    from chemvas.ui.scene_transform_controller import SceneTransformController


class _FakeScene:
    def __init__(self) -> None:
        self.removeItem = mock.Mock()


class _FakeSelectableItem:
    def __init__(self, *, selected: bool = False) -> None:
        self._selected = selected

    def isSelected(self) -> bool:
        return self._selected

    def setSelected(self, selected: bool) -> None:
        self._selected = selected


class _StateItem:
    def __init__(self, state: dict) -> None:
        self._state = dict(state)

    def data(self, key: int):
        if key == 9:
            return dict(self._state)
        return None


def _scene_delete_controller_for(view) -> SceneDeleteController:
    services = getattr(view, "services", SimpleNamespace())
    return SceneDeleteController(
        view,
        move_controller=getattr(services, "move_controller", None),
        atom_mutation_service=getattr(services, "canvas_atom_mutation_service", None),
        bond_mutation_service=getattr(services, "canvas_bond_mutation_service", None),
        style_controller=getattr(services, "style_controller", None),
        history_service=getattr(services, "history_service", None),
    )


def _scene_transform_controller_for(view) -> SceneTransformController:
    services = getattr(view, "services", SimpleNamespace())
    return SceneTransformController(
        view,
        move_controller=getattr(services, "move_controller", None),
        graph_service=getattr(services, "canvas_graph_service", None),
        history_service=getattr(services, "history_service", None),
    )


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for canvas view tests"
)
class CanvasViewDeleteAndBondStyleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_scene_ops_delete_atom_returns_single_delete_atoms_command_without_bonds(
        self,
    ) -> None:
        def remove_atom_only(atom_id: int, remove_marks: bool = True) -> None:
            del view.model.atoms[atom_id]
            view.model.next_atom_id = 4

        remove_bond_by_id = mock.Mock()
        atom_mutation_service = SimpleNamespace(
            remove_atom_only=mock.Mock(side_effect=remove_atom_only)
        )
        move_controller = SimpleNamespace(redraw_connected_bonds=mock.Mock())
        mark_item = _StateItem({"mark": 1})
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0)}, bonds=[], next_atom_id=5
            ),
            smiles_input_state=CanvasSmilesInputState(last_smiles_input="C"),
            mark_registry=CanvasMarkRegistry({1: [mark_item]}),
            _bond_state_dict=mock.Mock(),
            services=SimpleNamespace(
                canvas_atom_mutation_service=atom_mutation_service,
                canvas_bond_mutation_service=SimpleNamespace(
                    remove_bond_by_id=remove_bond_by_id
                ),
                move_controller=move_controller,
            ),
            push_command=mock.Mock(),
        )
        view.services.history_service = SimpleNamespace(push=view.push_command)
        controller = _scene_delete_controller_for(view)

        self.assertIsNone(controller.delete_atom("bad"))
        self.assertIsNone(controller.delete_atom(9))

        command = controller.delete_atom(1)

        self.assertIsInstance(command, DeleteAtomsCommand)
        self.assertEqual(
            command.atom_states,
            {
                1: {
                    "element": "C",
                    "x": 0.0,
                    "y": 0.0,
                    "color": "#000000",
                    "explicit_label": False,
                }
            },
        )
        self.assertEqual(command.mark_states, [{"mark": 1}])
        self.assertEqual(command.before_next_atom_id, 5)
        self.assertEqual(command.after_next_atom_id, 4)
        self.assertIsNone(last_smiles_input_for(view))
        remove_bond_by_id.assert_not_called()
        view.push_command.assert_called_once_with(command)

    def test_scene_ops_delete_atom_builds_composite_command_for_connected_bonds(
        self,
    ) -> None:
        def remove_atom_only(atom_id: int, remove_marks: bool = True) -> None:
            view.model.atoms.pop(atom_id, None)
            view.model.next_atom_id = 9

        bonds = [Bond(1, 2, 1), Bond(3, 1, 2), None]
        remove_bond_by_id = mock.Mock()
        atom_mutation_service = SimpleNamespace(
            remove_atom_only=mock.Mock(side_effect=remove_atom_only)
        )
        move_controller = SimpleNamespace(redraw_connected_bonds=mock.Mock())
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("O", 1.0, 0.0),
                    3: Atom("N", -1.0, 0.0),
                },
                bonds=bonds,
                next_atom_id=10,
            ),
            smiles_input_state=CanvasSmilesInputState(last_smiles_input="CO"),
            mark_registry=CanvasMarkRegistry({1: []}),
            _atom_state_dict=mock.Mock(return_value={"atom": 1}),
            _bond_state_dict=mock.Mock(
                side_effect=lambda bond: {"a": bond.a, "b": bond.b, "order": bond.order}
            ),
            services=SimpleNamespace(
                canvas_atom_mutation_service=atom_mutation_service,
                canvas_bond_mutation_service=SimpleNamespace(
                    remove_bond_by_id=remove_bond_by_id
                ),
                move_controller=move_controller,
            ),
            push_command=mock.Mock(),
        )
        view.services.history_service = SimpleNamespace(push=view.push_command)
        controller = _scene_delete_controller_for(view)

        command = controller.delete_atom(1, record=False)

        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual(
            [type(child) for child in command.commands],
            [DeleteBondCommand, DeleteBondCommand, DeleteAtomsCommand],
        )
        self.assertEqual([child.bond_id for child in command.commands[:2]], [1, 0])
        remove_bond_by_id.assert_has_calls([mock.call(1), mock.call(0)])
        move_controller.redraw_connected_bonds.assert_has_calls(
            [
                mock.call(3, skip_bond_id=None),
                mock.call(1, skip_bond_id=None),
                mock.call(1, skip_bond_id=None),
                mock.call(2, skip_bond_id=None),
            ]
        )
        view.push_command.assert_not_called()

    def test_scene_ops_delete_bond_handles_invalid_none_and_valid_paths(self) -> None:
        bonds = [Bond(1, 2, 1), None]
        remove_bond_by_id = mock.Mock()
        move_controller = SimpleNamespace(redraw_connected_bonds=mock.Mock())
        view = SimpleNamespace(
            model=SimpleNamespace(bonds=bonds),
            smiles_input_state=CanvasSmilesInputState(last_smiles_input="CC"),
            _bond_state_dict=mock.Mock(return_value={"bond": 0}),
            services=SimpleNamespace(
                canvas_bond_mutation_service=SimpleNamespace(
                    remove_bond_by_id=remove_bond_by_id
                ),
                move_controller=move_controller,
            ),
            push_command=mock.Mock(),
        )
        view.services.history_service = SimpleNamespace(push=view.push_command)
        controller = _scene_delete_controller_for(view)

        self.assertIsNone(controller.delete_bond(None))
        self.assertIsNone(controller.delete_bond(-1))
        self.assertIsNone(controller.delete_bond(1))

        command = controller.delete_bond(0, record=False)

        self.assertIsInstance(command, DeleteBondCommand)
        self.assertEqual(command.bond_id, 0)
        remove_bond_by_id.assert_called_once_with(0)
        move_controller.redraw_connected_bonds.assert_has_calls(
            [mock.call(1, skip_bond_id=None), mock.call(2, skip_bond_id=None)]
        )
        view.push_command.assert_not_called()

    def test_scene_ops_delete_ring_builds_delete_scene_items_command(self) -> None:
        ring_item = _StateItem({"kind": "ring"})
        scene_item_controller = SimpleNamespace(remove_scene_item=mock.Mock())
        view = SimpleNamespace(
            services=SimpleNamespace(scene_item_controller=scene_item_controller),
            push_command=mock.Mock(),
        )
        view.services.history_service = SimpleNamespace(push=view.push_command)
        controller = _scene_delete_controller_for(view)

        command = controller.delete_ring(ring_item, record=False)

        self.assertIsInstance(command, DeleteSceneItemsCommand)
        self.assertEqual(command.item_states, [{"kind": "ring"}])
        self.assertEqual(command.items, [ring_item])
        scene_item_controller.remove_scene_item.assert_called_once_with(ring_item)
        view.push_command.assert_not_called()

    def test_scene_ops_flip_bond_direction_requires_directional_style_and_updates_graphics(
        self,
    ) -> None:
        scene = _FakeScene()
        wedge_bond = Bond(1, 2, 1, style="wedge")
        plain_bond = Bond(3, 4, 1, style="single")
        replacement_item = _FakeSelectableItem()
        original_selected_item = _FakeSelectableItem(selected=True)
        move_controller = SimpleNamespace(redraw_connected_bonds=mock.Mock())
        record_bond_update = mock.Mock()
        view = SimpleNamespace(
            model=SimpleNamespace(bonds=[wedge_bond, plain_bond]),
            scene=lambda: scene,
            smiles_input_state=CanvasSmilesInputState(last_smiles_input="C=C"),
            _bond_state_dict=mock.Mock(
                side_effect=lambda bond: {"a": bond.a, "b": bond.b, "style": bond.style}
            ),
            services=SimpleNamespace(
                history_service=SimpleNamespace(push=mock.Mock()),
                move_controller=move_controller,
                canvas_history_recording_service=SimpleNamespace(
                    record_bond_update=record_bond_update
                ),
            ),
        )
        set_bond_items_for(view, {0: [original_selected_item, "old-b"], 1: ["old-c"]})
        view.bond_renderer = SimpleNamespace(
            add_bond_graphics=mock.Mock(
                side_effect=lambda bond_id: bond_items_for(view).__setitem__(
                    bond_id, [replacement_item]
                )
            )
        )
        controller = _scene_transform_controller_for(view)

        controller.flip_bond_direction(9)
        controller.flip_bond_direction(1)
        controller.flip_bond_direction(0)

        self.assertEqual((wedge_bond.a, wedge_bond.b), (2, 1))
        self.assertEqual(bond_items_for(view)[0], [replacement_item])
        self.assertTrue(replacement_item.isSelected())
        scene.removeItem.assert_has_calls(
            [mock.call(original_selected_item), mock.call("old-b")]
        )
        view.bond_renderer.add_bond_graphics.assert_called_once_with(0)
        move_controller.redraw_connected_bonds.assert_has_calls(
            [mock.call(2, skip_bond_id=0), mock.call(1, skip_bond_id=0)]
        )
        record_bond_update.assert_called_once()

    def test_scene_ops_apply_and_cycle_bond_style_refresh_graphics_and_record_update(
        self,
    ) -> None:
        scene = _FakeScene()
        styled_bond = Bond(1, 2, 1, style="single")
        cycled_bond = Bond(3, 4, 1, style="single")
        styled_replacement = _FakeSelectableItem()
        cycled_replacement = _FakeSelectableItem()
        original_style_item = _FakeSelectableItem(selected=True)
        original_cycle_item = _FakeSelectableItem(selected=True)
        move_controller = SimpleNamespace(redraw_connected_bonds=mock.Mock())
        record_bond_update = mock.Mock()
        view = SimpleNamespace(
            model=SimpleNamespace(bonds=[styled_bond, cycled_bond]),
            scene=lambda: scene,
            smiles_input_state=CanvasSmilesInputState(last_smiles_input="CN"),
            _bond_state_dict=mock.Mock(
                side_effect=lambda bond: {
                    "a": bond.a,
                    "b": bond.b,
                    "style": bond.style,
                    "order": bond.order,
                }
            ),
            services=SimpleNamespace(
                history_service=SimpleNamespace(push=mock.Mock()),
                move_controller=move_controller,
                canvas_history_recording_service=SimpleNamespace(
                    record_bond_update=record_bond_update
                ),
            ),
        )
        set_bond_items_for(view, {0: [original_style_item], 1: [original_cycle_item]})
        view.bond_renderer = SimpleNamespace(
            add_bond_graphics=mock.Mock(
                side_effect=lambda bond_id: bond_items_for(view).__setitem__(
                    bond_id,
                    [styled_replacement if bond_id == 0 else cycled_replacement],
                )
            )
        )
        controller = _scene_transform_controller_for(view)

        controller.apply_bond_style(0, "double", 2)

        self.assertEqual((styled_bond.style, styled_bond.order), ("double", 2))
        self.assertEqual(bond_items_for(view)[0], [styled_replacement])
        self.assertTrue(styled_replacement.isSelected())
        view.bond_renderer.add_bond_graphics.assert_called_once_with(0)
        move_controller.redraw_connected_bonds.assert_has_calls(
            [mock.call(1, skip_bond_id=0), mock.call(2, skip_bond_id=0)]
        )

        with mock.patch(
            "chemvas.ui.scene_single_item_mutation_logic.cycle_plain_bond_style",
            return_value=("aromatic", 3),
        ) as cycle_style:
            controller.cycle_bond_style(1)

        cycle_style.assert_called_once_with("single", 1, allow_double_variants=False)
        self.assertEqual((cycled_bond.style, cycled_bond.order), ("aromatic", 3))
        self.assertEqual(bond_items_for(view)[1], [cycled_replacement])
        self.assertTrue(cycled_replacement.isSelected())
        self.assertEqual(
            view.bond_renderer.add_bond_graphics.call_args_list[-1], mock.call(1)
        )
        self.assertEqual(record_bond_update.call_count, 2)

    def test_delete_and_transform_services_stay_split(self) -> None:
        delete_controller = mock.Mock()
        transform_controller = mock.Mock()
        view = SimpleNamespace(
            services=SimpleNamespace(
                scene_delete_controller=delete_controller,
                scene_transform_controller=transform_controller,
            )
        )

        view.services.scene_delete_controller.delete_atom(1, record=False)
        view.services.scene_delete_controller.delete_bond(2, record=True)
        view.services.scene_delete_controller.delete_ring("ring", record=False)
        view.services.scene_transform_controller.flip_bond_direction(3)
        view.services.scene_transform_controller.apply_bond_style(4, "double", 2)
        view.services.scene_transform_controller.cycle_bond_style(5)

        delete_controller.delete_atom.assert_called_once_with(1, record=False)
        delete_controller.delete_bond.assert_called_once_with(2, record=True)
        delete_controller.delete_ring.assert_called_once_with("ring", record=False)
        transform_controller.flip_bond_direction.assert_called_once_with(3)
        transform_controller.apply_bond_style.assert_called_once_with(4, "double", 2)
        transform_controller.cycle_bond_style.assert_called_once_with(5)


if __name__ == "__main__":
    unittest.main()
