import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtGui import QBrush, QColor
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsEllipseItem,
        QGraphicsPathItem,
        QGraphicsScene,
        QGraphicsTextItem,
    )
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.history import UpdateAtomColorCommand, UpdateBondCommand, UpdateSceneItemCommand
    from core.model import Atom, Bond
    from ui.canvas_color_mutation_service import (
        CanvasColorMutationService,
        canvas_color_mutation_service_for,
    )
    from ui.graphics_items import AtomDotItem


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas color mutation tests")
class CanvasColorMutationServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_apply_color_and_fill_helpers_cover_bond_atom_ring_and_commands(self) -> None:
        scene = QGraphicsScene()

        bond_item = QGraphicsPathItem()
        bond_item.setData(0, "bond")
        bond_item.setData(1, 0)
        scene.addItem(bond_item)
        bond_pushes = []
        bond_canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(bonds=[Bond(1, 2, 1, color="#000000")]),
            bond_items={0: [bond_item]},
            last_smiles_input="smiles",
            _bond_state_dict=lambda bond: {
                "a": bond.a,
                "b": bond.b,
                "order": bond.order,
                "style": bond.style,
                "color": bond.color,
            },
            _apply_color_to_bond_item=mock.Mock(),
            _push_command=bond_pushes.append,
        )
        CanvasColorMutationService(bond_canvas).apply_color_to_item(bond_item, QColor("#ff0000"))
        self.assertEqual(bond_canvas.model.bonds[0].color, "#ff0000")
        bond_canvas._apply_color_to_bond_item.assert_called_once()
        self.assertIsInstance(bond_pushes.pop(), UpdateBondCommand)

        atom_item = QGraphicsTextItem("O")
        atom_item.setData(0, "atom")
        atom_item.setData(1, 7)
        scene.addItem(atom_item)
        dot_item = mock.Mock()
        atom_pushes = []
        atom_canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={7: Atom("O", 0.0, 0.0, color="#101010")}),
            atom_items={7: atom_item},
            atom_dots={7: dot_item},
            _implicit_carbon_dot_brush=mock.Mock(return_value="dot-brush"),
            _push_command=atom_pushes.append,
        )
        CanvasColorMutationService(atom_canvas).apply_color_to_item(atom_item, QColor("#00aa00"))
        self.assertEqual(atom_canvas.model.atoms[7].color, "#00aa00")
        self.assertEqual(atom_item.defaultTextColor().name(), "#00aa00")
        dot_item.setBrush.assert_called_once_with("dot-brush")
        self.assertIsInstance(atom_pushes.pop(), UpdateAtomColorCommand)

        ring_item = QGraphicsPathItem()
        ring_item.setData(0, "ring")
        ring_item.setData(2, [1, 2])
        scene.addItem(ring_item)
        recurse_canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 1.0, 0.0)}),
            atom_items={1: object()},
            atom_dots={2: object()},
            bond_items={3: [object()]},
            bond_sets_for_atoms=mock.Mock(return_value=({3}, set())),
            apply_color_to_item=mock.Mock(),
        )
        recurse_service = CanvasColorMutationService(recurse_canvas)
        recurse_service.apply_color_to_item(ring_item, QColor("#336699"))
        self.assertEqual(
            recurse_canvas.apply_color_to_item.call_args_list,
            [
                mock.call(recurse_canvas.atom_items[1], QColor("#336699")),
                mock.call(recurse_canvas.atom_dots[2], QColor("#336699")),
                mock.call(recurse_canvas.bond_items[3][0], QColor("#336699")),
            ],
        )

        fill_pushes = []
        fill_canvas = SimpleNamespace(
            _ring_state_dict=lambda item: {
                "kind": "ring",
                "color": item.brush().color().name(),
                "alpha": round(item.brush().color().alphaF(), 2),
            },
            _push_command=fill_pushes.append,
        )
        CanvasColorMutationService(fill_canvas).apply_ring_fill_color(ring_item, QColor("#123456"), alpha=2.0)
        self.assertAlmostEqual(ring_item.brush().color().alphaF(), 1.0)
        self.assertIsInstance(fill_pushes.pop(), UpdateSceneItemCommand)

        CanvasColorMutationService(atom_canvas).apply_color_to_item(None, QColor("#ffffff"))
        CanvasColorMutationService(fill_canvas).apply_ring_fill_color(None, QColor("#ffffff"))

    def test_apply_color_to_item_short_circuits_for_invalid_scene_runtime_and_unknown_kind(self) -> None:
        scene = QGraphicsScene()
        other_scene = QGraphicsScene()
        color = QColor("#224466")
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={}, bonds=[]),
            atom_items={},
            atom_dots={},
            bond_items={},
            _push_command=mock.Mock(),
        )
        service = CanvasColorMutationService(canvas)

        invalid_kind_item = QGraphicsTextItem("X")
        invalid_kind_item.setData(0, "note")
        invalid_kind_item.setData(1, 1)
        scene.addItem(invalid_kind_item)
        mismatched_item = QGraphicsTextItem("Y")
        mismatched_item.setData(0, "atom")
        mismatched_item.setData(1, 1)
        other_scene.addItem(mismatched_item)
        deleted_item = mock.Mock()
        deleted_item.scene.side_effect = RuntimeError

        service.apply_color_to_item(invalid_kind_item, QColor())
        service.apply_color_to_item(mismatched_item, color)
        service.apply_color_to_item(deleted_item, color)
        service.apply_color_to_item(invalid_kind_item, color)

        canvas._push_command.assert_not_called()
        self.assertEqual(invalid_kind_item.defaultTextColor().name(), "#000000")

    def test_apply_ring_fill_color_ignores_non_ring_and_unchanged_state(self) -> None:
        non_ring_item = QGraphicsPathItem()
        non_ring_item.setData(0, "atom")
        ring_item = QGraphicsPathItem()
        ring_item.setData(0, "ring")
        pushes = []
        state = {"kind": "ring", "color": "#abcdef", "alpha": 0.0}
        canvas = SimpleNamespace(
            _ring_state_dict=mock.Mock(side_effect=[state, state]),
            _push_command=pushes.append,
        )
        service = CanvasColorMutationService(canvas)

        service.apply_ring_fill_color(non_ring_item, QColor("#abcdef"))
        service.apply_ring_fill_color(ring_item, QColor("#abcdef"), alpha=-3.0)

        self.assertEqual(pushes, [])
        self.assertEqual(canvas._ring_state_dict.call_count, 2)
        self.assertAlmostEqual(ring_item.brush().color().alphaF(), 0.0)

    def test_apply_bond_color_ignores_invalid_none_and_unchanged_bonds(self) -> None:
        scene = QGraphicsScene()
        invalid_item = QGraphicsPathItem()
        invalid_item.setData(0, "bond")
        invalid_item.setData(1, "bad-id")
        scene.addItem(invalid_item)
        none_item = QGraphicsPathItem()
        none_item.setData(0, "bond")
        none_item.setData(1, 1)
        scene.addItem(none_item)
        unchanged_item = QGraphicsPathItem()
        unchanged_item.setData(0, "bond")
        unchanged_item.setData(1, 0)
        scene.addItem(unchanged_item)
        bond = Bond(1, 2, 1, color="#445566")
        pushes = []
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(bonds=[bond, None]),
            bond_items={0: [], 1: [none_item]},
            last_smiles_input="same",
            _bond_state_dict=lambda current: {"color": current.color},
            _apply_color_to_bond_item=mock.Mock(),
            _push_command=pushes.append,
        )
        service = CanvasColorMutationService(canvas)

        service.apply_color_to_item(invalid_item, QColor("#112233"))
        service.apply_color_to_item(none_item, QColor("#112233"))
        service.apply_color_to_item(unchanged_item, QColor("#445566"))

        self.assertEqual(pushes, [])
        canvas._apply_color_to_bond_item.assert_not_called()

    def test_apply_atom_color_covers_ellipse_dot_missing_atom_and_same_color_paths(self) -> None:
        scene = QGraphicsScene()
        ellipse_item = QGraphicsEllipseItem(0.0, 0.0, 8.0, 8.0)
        ellipse_item.setData(0, "atom")
        ellipse_item.setData(1, 3)
        scene.addItem(ellipse_item)
        label_item = QGraphicsTextItem("N")
        scene.addItem(label_item)
        dot_proxy = mock.Mock()
        pushes = []
        brush = QBrush(QColor("#fedcba"))
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={3: Atom("N", 0.0, 0.0, color="#010101")}),
            atom_items={3: label_item},
            atom_dots={3: dot_proxy},
            _implicit_carbon_dot_brush=mock.Mock(return_value=brush),
            _push_command=pushes.append,
        )
        service = CanvasColorMutationService(canvas)

        service.apply_color_to_item(ellipse_item, QColor("#abcdef"))

        self.assertEqual(ellipse_item.brush().color().name(), "#abcdef")
        self.assertEqual(label_item.defaultTextColor().name(), "#abcdef")
        dot_proxy.setBrush.assert_called_once_with(brush)
        self.assertIsInstance(pushes.pop(), UpdateAtomColorCommand)

        dot_item = AtomDotItem(-1.0, -1.0, 2.0, 2.0)
        dot_item.setData(0, "atom")
        dot_item.setData(1, 99)
        scene.addItem(dot_item)
        same_color_item = QGraphicsEllipseItem(0.0, 0.0, 6.0, 6.0)
        same_color_item.setData(0, "atom")
        same_color_item.setData(1, 3)
        scene.addItem(same_color_item)
        canvas.model.atoms[3].color = "#abcdef"

        service.apply_color_to_item(dot_item, QColor("#123456"))
        service.apply_color_to_item(same_color_item, QColor("#abcdef"))

        self.assertEqual(dot_item.brush().color().name(), "#fedcba")
        self.assertEqual(pushes, [])

    def test_apply_ring_structure_color_covers_invalid_metadata_and_fallback_dispatch(self) -> None:
        scene = QGraphicsScene()
        invalid_item = QGraphicsPathItem()
        invalid_item.setData(0, "ring")
        invalid_item.setData(2, "bad")
        scene.addItem(invalid_item)
        empty_item = QGraphicsPathItem()
        empty_item.setData(0, "ring")
        empty_item.setData(2, ["x"])
        scene.addItem(empty_item)
        ring_item = QGraphicsPathItem()
        ring_item.setData(0, "ring")
        ring_item.setData(2, [1, 2, "x"])
        scene.addItem(ring_item)
        atom_item = object()
        fallback_canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 1.0, 0.0)}),
            atom_items={1: atom_item},
            atom_dots={},
            bond_items={7: []},
            bond_sets_for_atoms=mock.Mock(return_value=({7}, set())),
            apply_color_to_item=None,
        )
        service = CanvasColorMutationService(fallback_canvas)
        service.apply_color_to_item = mock.Mock()

        service._apply_ring_structure_color(invalid_item, QColor("#123456"))
        service._apply_ring_structure_color(empty_item, QColor("#123456"))
        service._apply_ring_structure_color(ring_item, QColor("#123456"))

        service.apply_color_to_item.assert_called_once_with(atom_item, QColor("#123456"))

    def test_canvas_color_mutation_service_for_reuses_real_duck_typed_and_fallback_services(self) -> None:
        canvas = SimpleNamespace()
        real_service = CanvasColorMutationService(canvas)
        canvas._canvas_color_mutation_service = real_service

        self.assertIs(canvas_color_mutation_service_for(canvas), real_service)

        duck_service = SimpleNamespace(
            apply_color_to_item=mock.Mock(),
            apply_ring_fill_color=mock.Mock(),
        )
        canvas._canvas_color_mutation_service = duck_service

        self.assertIs(canvas_color_mutation_service_for(canvas), duck_service)

        canvas._canvas_color_mutation_service = object()

        self.assertIsInstance(canvas_color_mutation_service_for(canvas), CanvasColorMutationService)


if __name__ == "__main__":
    unittest.main()
