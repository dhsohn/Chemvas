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
    from ui.canvas_view import CanvasView


class _FakeScene:
    def __init__(self) -> None:
        self.removeItem = mock.Mock()


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
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
            bond_items={1: [bond_a, bond_b], 2: []},
            atom_items={3: atom_label},
            atom_dots={4: atom_dot},
            _render_model=mock.Mock(),
        )

        CanvasView._rebuild_graphics(view)

        self.assertEqual(scene.removeItem.call_args_list, [mock.call(bond_a), mock.call(bond_b), mock.call(atom_label), mock.call(atom_dot)])
        self.assertEqual(view.bond_items, {})
        self.assertEqual(view.atom_items, {})
        self.assertEqual(view.atom_dots, {})
        view._render_model.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
