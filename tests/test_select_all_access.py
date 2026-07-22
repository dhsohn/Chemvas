import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsView,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.ui.canvas_atom_graphics_state import (
        set_atom_dot_for,
        set_atom_item_for,
    )
    from chemvas.ui.canvas_bond_graphics_state import bond_items_for
    from chemvas.ui.canvas_scene_items_state import append_scene_item_for
    from chemvas.ui.select_all_access import select_all_scene_items_for


if QApplication is not None:

    class _Canvas(QGraphicsView):
        def __init__(self) -> None:
            super().__init__(QGraphicsScene())
            self.selection_controller = SimpleNamespace(
                select_note=mock.Mock(),
                update_selection_outline=mock.Mock(),
            )
            self.services = canvas_runtime_services(
                selection_controller=self.selection_controller
            )

        def add_scene_item(self, kind: str):
            item = QGraphicsRectItem(0.0, 0.0, 5.0, 5.0)
            item.setData(0, kind)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            self.scene().addItem(item)
            return item


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for select-all tests")
class SelectAllAccessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_select_all_selects_structure_items_scene_items_and_notes(self) -> None:
        canvas = _Canvas()
        atom_item = canvas.add_scene_item("atom")
        atom_item.setData(1, 0)
        set_atom_item_for(canvas, 0, atom_item)
        bond_item = canvas.add_scene_item("bond")
        bond_item.setData(1, 0)
        bond_items_for(canvas)[0] = [bond_item]
        arrow_item = canvas.add_scene_item("arrow")
        append_scene_item_for(canvas, "arrow_items", arrow_item)
        shape_item = canvas.add_scene_item("shape")
        append_scene_item_for(canvas, "shape_items", shape_item)
        note_item = canvas.add_scene_item("note")
        append_scene_item_for(canvas, "note_items", note_item)

        self.assertTrue(select_all_scene_items_for(canvas))

        self.assertTrue(atom_item.isSelected())
        self.assertTrue(bond_item.isSelected())
        self.assertTrue(arrow_item.isSelected())
        self.assertTrue(shape_item.isSelected())
        canvas.selection_controller.select_note.assert_called_once_with(
            note_item, additive=True
        )
        canvas.selection_controller.update_selection_outline.assert_called_once_with()

    def test_select_all_selects_implicit_carbon_dots(self) -> None:
        canvas = _Canvas()
        dot_item = canvas.add_scene_item("atom")
        dot_item.setData(1, 3)
        set_atom_dot_for(canvas, 3, dot_item)

        self.assertTrue(select_all_scene_items_for(canvas))
        self.assertTrue(dot_item.isSelected())

    def test_select_all_returns_false_for_empty_canvas(self) -> None:
        canvas = _Canvas()

        self.assertFalse(select_all_scene_items_for(canvas))
        canvas.selection_controller.update_selection_outline.assert_not_called()

    def test_select_all_skips_detached_items(self) -> None:
        canvas = _Canvas()
        detached = QGraphicsRectItem(0.0, 0.0, 5.0, 5.0)
        detached.setData(0, "arrow")
        append_scene_item_for(canvas, "arrow_items", detached)

        self.assertFalse(select_all_scene_items_for(canvas))


if __name__ == "__main__":
    unittest.main()
