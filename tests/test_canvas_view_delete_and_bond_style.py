import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.history import CompositeCommand, DeleteAtomsCommand, DeleteBondCommand, DeleteSceneItemsCommand
    from core.model import Atom, Bond
    from ui.canvas_view import CanvasView
    from ui.scene_ops_controller import SceneOpsController


class _FakeScene:
    def __init__(self) -> None:
        self.removeItem = mock.Mock()


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewDeleteAndBondStyleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_scene_ops_delete_atom_returns_single_delete_atoms_command_without_bonds(self) -> None:
        def remove_atom_only(atom_id: int, remove_marks: bool = True) -> None:
            del view.model.atoms[atom_id]
            view.model.next_atom_id = 4

        view = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0)}, bonds=[], next_atom_id=5),
            last_smiles_input="C",
            _marks_by_atom={1: ["mark"]},
            _mark_state_dict=mock.Mock(return_value={"mark": 1}),
            _atom_state_dict=mock.Mock(return_value={"atom": 1}),
            _bond_state_dict=mock.Mock(),
            _remove_bond_by_id=mock.Mock(),
            _redraw_connected_bonds=mock.Mock(),
            _remove_atom_only=mock.Mock(side_effect=remove_atom_only),
            _push_command=mock.Mock(),
        )
        controller = SceneOpsController(view)

        self.assertIsNone(controller.delete_atom("bad"))

        command = controller.delete_atom(1)

        self.assertIsInstance(command, DeleteAtomsCommand)
        self.assertEqual(command.atom_states, {1: {"atom": 1}})
        self.assertEqual(command.mark_states, [{"mark": 1}])
        self.assertEqual(command.before_next_atom_id, 5)
        self.assertEqual(command.after_next_atom_id, 4)
        self.assertIsNone(view.last_smiles_input)
        view._remove_bond_by_id.assert_not_called()
        view._push_command.assert_called_once_with(command)

    def test_scene_ops_delete_atom_builds_composite_command_for_connected_bonds(self) -> None:
        def remove_atom_only(atom_id: int, remove_marks: bool = True) -> None:
            view.model.atoms.pop(atom_id, None)
            view.model.next_atom_id = 9

        bonds = [Bond(1, 2, 1), Bond(3, 1, 2), None]
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 1.0, 0.0), 3: Atom("N", -1.0, 0.0)},
                bonds=bonds,
                next_atom_id=10,
            ),
            last_smiles_input="CO",
            _marks_by_atom={1: []},
            _mark_state_dict=mock.Mock(),
            _atom_state_dict=mock.Mock(return_value={"atom": 1}),
            _bond_state_dict=mock.Mock(side_effect=lambda bond: {"a": bond.a, "b": bond.b, "order": bond.order}),
            _remove_bond_by_id=mock.Mock(),
            _redraw_connected_bonds=mock.Mock(),
            _remove_atom_only=mock.Mock(side_effect=remove_atom_only),
            _push_command=mock.Mock(),
        )
        controller = SceneOpsController(view)

        command = controller.delete_atom(1, record=False)

        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual([type(child) for child in command.commands], [DeleteBondCommand, DeleteBondCommand, DeleteAtomsCommand])
        self.assertEqual([child.bond_id for child in command.commands[:2]], [1, 0])
        view._remove_bond_by_id.assert_has_calls([mock.call(1), mock.call(0)])
        view._redraw_connected_bonds.assert_has_calls([mock.call(3), mock.call(1), mock.call(1), mock.call(2)])
        view._push_command.assert_not_called()

    def test_scene_ops_delete_bond_handles_invalid_none_and_valid_paths(self) -> None:
        bonds = [Bond(1, 2, 1), None]
        view = SimpleNamespace(
            model=SimpleNamespace(bonds=bonds),
            last_smiles_input="CC",
            _bond_state_dict=mock.Mock(return_value={"bond": 0}),
            _remove_bond_by_id=mock.Mock(),
            _redraw_connected_bonds=mock.Mock(),
            _push_command=mock.Mock(),
        )
        controller = SceneOpsController(view)

        self.assertIsNone(controller.delete_bond(-1))
        self.assertIsNone(controller.delete_bond(1))

        command = controller.delete_bond(0, record=False)

        self.assertIsInstance(command, DeleteBondCommand)
        self.assertEqual(command.bond_id, 0)
        view._remove_bond_by_id.assert_called_once_with(0)
        view._redraw_connected_bonds.assert_has_calls([mock.call(1), mock.call(2)])
        view._push_command.assert_not_called()

    def test_scene_ops_delete_ring_builds_delete_scene_items_command(self) -> None:
        ring_item = object()
        view = SimpleNamespace(
            _ring_state_dict=mock.Mock(return_value={"kind": "ring"}),
            remove_scene_item=mock.Mock(),
            _push_command=mock.Mock(),
        )
        controller = SceneOpsController(view)

        command = controller.delete_ring(ring_item, record=False)

        self.assertIsInstance(command, DeleteSceneItemsCommand)
        self.assertEqual(command.item_states, [{"kind": "ring"}])
        self.assertEqual(command.items, [ring_item])
        view.remove_scene_item.assert_called_once_with(ring_item)
        view._push_command.assert_not_called()

    def test_scene_ops_flip_bond_direction_requires_directional_style_and_updates_graphics(self) -> None:
        scene = _FakeScene()
        wedge_bond = Bond(1, 2, 1, style="wedge")
        plain_bond = Bond(3, 4, 1, style="single")
        view = SimpleNamespace(
            model=SimpleNamespace(bonds=[wedge_bond, plain_bond]),
            bond_items={0: ["old-a", "old-b"], 1: ["old-c"]},
            scene=lambda: scene,
            last_smiles_input="C=C",
            _bond_state_dict=mock.Mock(side_effect=lambda bond: {"a": bond.a, "b": bond.b, "style": bond.style}),
            _add_bond_graphics=mock.Mock(),
            _redraw_connected_bonds=mock.Mock(),
            _record_bond_update=mock.Mock(),
        )
        controller = SceneOpsController(view)

        controller.flip_bond_direction(9)
        controller.flip_bond_direction(1)
        controller.flip_bond_direction(0)

        self.assertEqual((wedge_bond.a, wedge_bond.b), (2, 1))
        self.assertEqual(view.bond_items[0], [])
        scene.removeItem.assert_has_calls([mock.call("old-a"), mock.call("old-b")])
        view._add_bond_graphics.assert_called_once_with(0)
        view._redraw_connected_bonds.assert_has_calls([mock.call(2, skip_bond_id=0), mock.call(1, skip_bond_id=0)])
        view._record_bond_update.assert_called_once()

    def test_scene_ops_apply_and_cycle_bond_style_refresh_graphics_and_record_update(self) -> None:
        scene = _FakeScene()
        styled_bond = Bond(1, 2, 1, style="single")
        cycled_bond = Bond(3, 4, 1, style="single")
        view = SimpleNamespace(
            model=SimpleNamespace(bonds=[styled_bond, cycled_bond]),
            bond_items={0: ["style-item"], 1: ["cycle-item"]},
            scene=lambda: scene,
            last_smiles_input="CN",
            _bond_state_dict=mock.Mock(side_effect=lambda bond: {"a": bond.a, "b": bond.b, "style": bond.style, "order": bond.order}),
            _add_bond_graphics=mock.Mock(),
            _redraw_connected_bonds=mock.Mock(),
            _record_bond_update=mock.Mock(),
        )
        controller = SceneOpsController(view)

        controller.apply_bond_style(0, "double", 2)

        self.assertEqual((styled_bond.style, styled_bond.order), ("double", 2))
        self.assertEqual(view.bond_items[0], [])
        view._add_bond_graphics.assert_called_once_with(0)
        view._redraw_connected_bonds.assert_has_calls([mock.call(1, skip_bond_id=0), mock.call(2, skip_bond_id=0)])

        with mock.patch("ui.scene_ops_controller.cycle_plain_bond_style", return_value=("aromatic", 3)) as cycle_style:
            controller.cycle_bond_style(1)

        cycle_style.assert_called_once_with("single", 1)
        self.assertEqual((cycled_bond.style, cycled_bond.order), ("aromatic", 3))
        self.assertEqual(view.bond_items[1], [])
        self.assertEqual(view._add_bond_graphics.call_args_list[-1], mock.call(1))
        self.assertEqual(view._record_bond_update.call_count, 2)

    def test_canvas_view_delete_and_bond_style_wrappers_delegate_to_scene_ops_controller(self) -> None:
        controller = mock.Mock()
        view = SimpleNamespace(_scene_ops_controller=controller)

        CanvasView.delete_atom(view, 1, record=False)
        CanvasView.delete_bond(view, 2, record=True)
        CanvasView.delete_ring(view, "ring", record=False)
        CanvasView.flip_bond_direction(view, 3)
        CanvasView.apply_bond_style(view, 4, "double", 2)
        CanvasView.cycle_bond_style(view, 5)

        controller.delete_atom.assert_called_once_with(1, record=False)
        controller.delete_bond.assert_called_once_with(2, record=True)
        controller.delete_ring.assert_called_once_with("ring", record=False)
        controller.flip_bond_direction.assert_called_once_with(3)
        controller.apply_bond_style.assert_called_once_with(4, "double", 2)
        controller.cycle_bond_style.assert_called_once_with(5)


if __name__ == "__main__":
    unittest.main()
