import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
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

    def test_scene_ops_wrappers_delegate_to_scene_ops_controller(self) -> None:
        controller = SimpleNamespace(
            _flip_bounds_for_item=mock.Mock(return_value=QRectF(1.0, 2.0, 3.0, 4.0)),
            _flip_center_for_selection=mock.Mock(return_value=QPointF(5.0, 6.0)),
            _flip_scene_item_state=mock.Mock(return_value={"kind": "flipped"}),
            _selected_atom_components_for_transform=mock.Mock(return_value=[{1, 2}]),
            _center_for_flip_group=mock.Mock(return_value=QPointF(7.0, 8.0)),
        )
        item = object()
        before_state = {"kind": "atom"}
        transformed_atom_positions = {1: (9.0, 10.0)}
        atom_ids = {1, 2}
        items = [object(), object()]

        view = SimpleNamespace(_scene_ops_controller=controller)

        self.assertEqual(CanvasView._flip_bounds_for_item(view, item), controller._flip_bounds_for_item.return_value)
        self.assertEqual(
            CanvasView._flip_center_for_selection(view, atom_ids, items),
            controller._flip_center_for_selection.return_value,
        )
        self.assertEqual(
            CanvasView._flip_scene_item_state(
                view,
                item,
                before_state,
                QPointF(11.0, 12.0),
                True,
                transformed_atom_positions,
            ),
            controller._flip_scene_item_state.return_value,
        )
        self.assertEqual(
            CanvasView._selected_atom_components_for_transform(view, atom_ids),
            controller._selected_atom_components_for_transform.return_value,
        )
        self.assertEqual(
            CanvasView._center_for_flip_group(view, atom_ids, items),
            controller._center_for_flip_group.return_value,
        )

        controller._flip_bounds_for_item.assert_called_once_with(item)
        controller._flip_center_for_selection.assert_called_once_with(atom_ids, items)
        controller._flip_scene_item_state.assert_called_once_with(
            item,
            before_state,
            QPointF(11.0, 12.0),
            True,
            transformed_atom_positions,
        )
        controller._selected_atom_components_for_transform.assert_called_once_with(atom_ids)
        controller._center_for_flip_group.assert_called_once_with(atom_ids, items)

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
