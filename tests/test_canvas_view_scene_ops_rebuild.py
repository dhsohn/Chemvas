import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
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
