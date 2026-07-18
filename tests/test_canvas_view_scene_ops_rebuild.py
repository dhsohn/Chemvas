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
    from chemvas.ui.canvas_atom_graphics_state import (
        atom_dots_for,
        atom_items_for,
        set_atom_dots_for,
        set_atom_items_for,
    )
    from chemvas.ui.canvas_bond_graphics_state import bond_items_for, set_bond_items_for
    from chemvas.ui.canvas_model_access import rebuild_graphics_for
    from chemvas.ui.scene_item_access import (
        clear_scene_item_list_map,
        clear_scene_item_map,
        remove_scene_items,
    )


class _FakeScene:
    def __init__(self) -> None:
        self.removeItem = mock.Mock()


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for canvas view tests"
)
class CanvasViewSceneOpsRebuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_rebuild_graphics_removes_scene_items_and_rerenders_model(self) -> None:
        bond_a = object()
        bond_b = object()
        atom_label = object()
        atom_dot = object()
        scene = _FakeScene()
        view = SimpleNamespace(
            scene=lambda: scene,
            services=SimpleNamespace(
                structure_build_service=SimpleNamespace(render_model=mock.Mock())
            ),
        )
        set_atom_items_for(view, {3: atom_label})
        set_atom_dots_for(view, {4: atom_dot})
        set_bond_items_for(view, {1: [bond_a, bond_b], 2: []})

        rebuild_graphics_for(view)

        self.assertEqual(
            scene.removeItem.call_args_list,
            [
                mock.call(bond_a),
                mock.call(bond_b),
                mock.call(atom_label),
                mock.call(atom_dot),
            ],
        )
        self.assertEqual(bond_items_for(view), {})
        self.assertEqual(atom_items_for(view), {})
        self.assertEqual(atom_dots_for(view), {})
        view.services.structure_build_service.render_model.assert_called_once_with()

    def test_scene_item_clear_helpers_remove_items_and_return_empty_maps(self) -> None:
        scene = _FakeScene()
        bond_a = object()
        bond_b = object()
        atom_label = object()

        self.assertEqual(
            clear_scene_item_list_map(scene, {1: [bond_a], 2: [bond_b]}),
            {},
        )
        self.assertEqual(
            scene.removeItem.call_args_list,
            [mock.call(bond_a), mock.call(bond_b)],
        )

        scene.removeItem.reset_mock()
        self.assertEqual(clear_scene_item_map(scene, {3: atom_label}), {})
        scene.removeItem.assert_called_once_with(atom_label)

        scene.removeItem.reset_mock()
        remove_scene_items(scene, [])
        scene.removeItem.assert_not_called()


if __name__ == "__main__":
    unittest.main()
