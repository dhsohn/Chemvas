import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QBrush, QColor, QPolygonF, QTextCursor
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsEllipseItem,
        QGraphicsPathItem,
        QGraphicsPolygonItem,
        QGraphicsScene,
        QGraphicsTextItem,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.history import UpdateAtomColorCommand, UpdateBondCommand
    from core.model import Atom, Bond
    from ui.canvas_atom_graphics_state import (
        atom_dots_for,
        atom_items_for,
        set_atom_dots_for,
        set_atom_items_for,
    )
    from ui.canvas_bond_graphics_state import bond_items_for, set_bond_items_for
    from ui.canvas_color_mutation_service import CanvasColorMutationService
    from ui.canvas_smiles_input_state import CanvasSmilesInputState
    from ui.graphics_items import AtomDotItem
    from ui.history_commands import UpdateSceneItemCommand


def _history_service(push=None):
    return SimpleNamespace(push=push if push is not None else mock.Mock())


def _set_atom_graphics(canvas, items=None, dots=None) -> None:
    set_atom_items_for(canvas, dict(items or {}))
    set_atom_dots_for(canvas, dict(dots or {}))


def _color_service_for(canvas, *, graph_service=None) -> CanvasColorMutationService:
    if graph_service is None:
        graph_service = SimpleNamespace(bond_sets_for_atoms=mock.Mock(return_value=(set(), set())))
    return CanvasColorMutationService(
        canvas,
        graph_service=graph_service,
        history_service=canvas.services.history_service,
    )


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
            smiles_input_state=CanvasSmilesInputState(last_smiles_input="smiles"),
            _bond_state_dict=lambda bond: {
                "a": bond.a,
                "b": bond.b,
                "order": bond.order,
                "style": bond.style,
                "color": bond.color,
            },
            services=SimpleNamespace(history_service=_history_service(bond_pushes.append)),
        )
        set_bond_items_for(bond_canvas, {0: [bond_item]})
        _color_service_for(bond_canvas).apply_color_to_item(bond_item, QColor("#ff0000"))
        self.assertEqual(bond_canvas.model.bonds[0].color, "#ff0000")
        self.assertEqual(bond_item.pen().color().name(), "#ff0000")
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
            services=SimpleNamespace(
                history_service=_history_service(atom_pushes.append),
                atom_label_service=SimpleNamespace(implicit_carbon_dot_brush=mock.Mock(return_value="dot-brush"))
            ),
        )
        _set_atom_graphics(atom_canvas, {7: atom_item}, {7: dot_item})
        _color_service_for(atom_canvas).apply_color_to_item(atom_item, QColor("#00aa00"))
        self.assertEqual(atom_canvas.model.atoms[7].color, "#00aa00")
        self.assertEqual(atom_item.defaultTextColor().name(), "#00aa00")
        dot_item.setBrush.assert_called_once_with("dot-brush")
        self.assertIsInstance(atom_pushes.pop(), UpdateAtomColorCommand)

        ring_item = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(1.0, 0.0), QPointF(0.0, 1.0)])
        )
        ring_item.setData(0, "ring")
        ring_item.setData(2, [1, 2])
        scene.addItem(ring_item)
        recurse_canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 1.0, 0.0)}),
            services=SimpleNamespace(
                history_service=_history_service(),
            ),
        )
        graph_service = SimpleNamespace(bond_sets_for_atoms=mock.Mock(return_value=({3}, set())))
        _set_atom_graphics(recurse_canvas, {1: object()}, {2: object()})
        set_bond_items_for(recurse_canvas, {3: [object()]})
        recurse_service = _color_service_for(recurse_canvas, graph_service=graph_service)
        recurse_service.apply_color_to_item = mock.Mock()
        recurse_service._apply_ring_structure_color(ring_item, QColor("#336699"))
        graph_service.bond_sets_for_atoms.assert_called_once_with({1, 2})
        self.assertEqual(
            recurse_service.apply_color_to_item.call_args_list,
            [
                mock.call(atom_items_for(recurse_canvas)[1], QColor("#336699")),
                mock.call(atom_dots_for(recurse_canvas)[2], QColor("#336699")),
                mock.call(bond_items_for(recurse_canvas)[3][0], QColor("#336699")),
            ],
        )

        fill_pushes = []
        fill_canvas = SimpleNamespace(
            services=SimpleNamespace(history_service=_history_service(fill_pushes.append)),
        )
        _color_service_for(fill_canvas).apply_ring_fill_color(ring_item, QColor("#123456"), alpha=2.0)
        self.assertAlmostEqual(ring_item.brush().color().alphaF(), 1.0)
        self.assertIsInstance(fill_pushes.pop(), UpdateSceneItemCommand)

        _color_service_for(atom_canvas).apply_color_to_item(None, QColor("#ffffff"))
        _color_service_for(fill_canvas).apply_ring_fill_color(None, QColor("#ffffff"))

    def test_coloring_a_ring_pushes_a_single_composite_command(self) -> None:
        from core.history import CompositeCommand

        scene = QGraphicsScene()
        ring_item = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(1.0, 0.0), QPointF(0.0, 1.0)])
        )
        ring_item.setData(0, "ring")
        ring_item.setData(2, [1, 2])
        scene.addItem(ring_item)

        label_a = QGraphicsTextItem("C")
        label_a.setData(0, "atom")
        label_a.setData(1, 1)
        scene.addItem(label_a)
        label_b = QGraphicsTextItem("O")
        label_b.setData(0, "atom")
        label_b.setData(1, 2)
        scene.addItem(label_b)
        bond_item = QGraphicsPathItem()
        bond_item.setData(0, "bond")
        bond_item.setData(1, 0)
        scene.addItem(bond_item)

        pushes: list = []
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 1.0, 0.0)},
                bonds=[Bond(1, 2, 1, color="#000000")],
            ),
            smiles_input_state=CanvasSmilesInputState(last_smiles_input=None),
            services=SimpleNamespace(
                history_service=_history_service(pushes.append),
                atom_label_service=SimpleNamespace(
                    implicit_carbon_dot_brush=mock.Mock(return_value=QBrush())
                ),
            ),
        )
        _set_atom_graphics(canvas, {1: label_a, 2: label_b})
        set_bond_items_for(canvas, {0: [bond_item]})
        graph_service = SimpleNamespace(bond_sets_for_atoms=mock.Mock(return_value=({0}, set())))
        service = _color_service_for(canvas, graph_service=graph_service)

        service.apply_color_to_item(ring_item, QColor("#ff8800"))

        # One ring click == one undo step, even though it touches every atom and bond.
        self.assertEqual(len(pushes), 1)
        composite = pushes[0]
        self.assertIsInstance(composite, CompositeCommand)
        self.assertEqual(len(composite.commands), 3)
        # History service is restored after the bundled mutation.
        self.assertIs(service.history, canvas.services.history_service)

    def test_apply_color_to_item_washes_shape_fill_and_records_history(self) -> None:
        scene = QGraphicsScene()
        pushes: list = []
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={}, bonds=[]),
            services=SimpleNamespace(history_service=_history_service(pushes.append)),
        )
        _set_atom_graphics(canvas)
        set_bond_items_for(canvas, {})
        service = _color_service_for(canvas)

        shape = QGraphicsPathItem()
        shape.setData(0, "shape")
        scene.addItem(shape)

        picked = QColor("#d84a3a")
        service.apply_color_to_item(shape, picked)

        # Shapes are background panels: the picked colour is diluted toward the
        # white sheet and applied opaque, so molecules on top stay readable and
        # nothing shows through the panel.
        fill = shape.brush().color()
        tint = CanvasColorMutationService.SHAPE_FILL_TINT
        self.assertEqual(fill.alphaF(), 1.0)
        self.assertEqual(fill.red(), round(255 - (255 - picked.red()) * tint))
        self.assertEqual(fill.green(), round(255 - (255 - picked.green()) * tint))
        self.assertEqual(fill.blue(), round(255 - (255 - picked.blue()) * tint))
        self.assertEqual(len(pushes), 1)
        self.assertIsInstance(pushes[0], UpdateSceneItemCommand)

    def test_apply_ring_fill_color_applies_opaque_pastel(self) -> None:
        ring_item = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(1.0, 0.0), QPointF(0.0, 1.0)])
        )
        ring_item.setData(0, "ring")
        pushes: list = []
        canvas = SimpleNamespace(
            services=SimpleNamespace(history_service=_history_service(pushes.append)),
        )
        service = _color_service_for(canvas)

        picked = QColor("#d84a3a")
        service.apply_ring_fill_color(ring_item, picked)

        fill = ring_item.brush().color()
        self.assertEqual(fill.alphaF(), 1.0)
        self.assertEqual(fill.red(), round(255 - (255 - picked.red()) * 0.25))
        self.assertEqual(fill.green(), round(255 - (255 - picked.green()) * 0.25))
        self.assertEqual(fill.blue(), round(255 - (255 - picked.blue()) * 0.25))
        self.assertEqual(len(pushes), 1)
        self.assertIsInstance(pushes[0], UpdateSceneItemCommand)

    def test_apply_color_to_item_colors_note_text_and_records_history(self) -> None:
        scene = QGraphicsScene()
        push_command = mock.Mock()
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={}, bonds=[]),
            push_command=push_command,
            services=SimpleNamespace(history_service=_history_service(push_command)),
        )
        _set_atom_graphics(canvas)
        set_bond_items_for(canvas, {})
        service = _color_service_for(canvas)

        note = QGraphicsTextItem("memo")
        note.setData(0, "note")
        scene.addItem(note)

        service.apply_color_to_item(note, QColor("#cc3344"))

        self.assertEqual(note.defaultTextColor().name(), "#cc3344")
        self.assertIn("#cc3344", note.toHtml())
        self.assertEqual(push_command.call_count, 1)
        self.assertIsInstance(push_command.call_args.args[0], UpdateSceneItemCommand)

    def test_apply_color_to_note_recolors_only_selected_text(self) -> None:
        scene = QGraphicsScene()
        push_command = mock.Mock()
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={}, bonds=[]),
            push_command=push_command,
            services=SimpleNamespace(history_service=_history_service(push_command)),
        )
        _set_atom_graphics(canvas)
        set_bond_items_for(canvas, {})
        service = _color_service_for(canvas)

        note = QGraphicsTextItem("Hello World")
        note.setData(0, "note")
        scene.addItem(note)
        cursor = note.textCursor()
        cursor.setPosition(6)
        cursor.setPosition(11, QTextCursor.MoveMode.KeepAnchor)
        note.setTextCursor(cursor)

        service.apply_color_to_item(note, QColor("#e53935"))

        html = note.toHtml().lower()
        # The colour lands on the selected word only, not the whole-document default.
        self.assertIn("e53935", html)
        self.assertNotEqual(note.defaultTextColor().name().lower(), "#e53935")
        self.assertTrue(note.textCursor().hasSelection())
        self.assertEqual(push_command.call_count, 1)

    def test_apply_color_to_item_short_circuits_for_invalid_scene_runtime_and_unknown_kind(self) -> None:
        scene = QGraphicsScene()
        other_scene = QGraphicsScene()
        color = QColor("#224466")
        push_command = mock.Mock()
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={}, bonds=[]),
            push_command=push_command,
            services=SimpleNamespace(history_service=_history_service(push_command)),
        )
        _set_atom_graphics(canvas)
        set_bond_items_for(canvas, {})
        service = _color_service_for(canvas)

        invalid_kind_item = QGraphicsTextItem("X")
        invalid_kind_item.setData(0, "mystery")
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

        push_command.assert_not_called()
        self.assertEqual(invalid_kind_item.defaultTextColor().name(), "#000000")

    def test_apply_ring_fill_color_ignores_non_ring_and_unchanged_state(self) -> None:
        non_ring_item = QGraphicsPathItem()
        non_ring_item.setData(0, "atom")
        ring_item = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(1.0, 0.0), QPointF(0.0, 1.0)])
        )
        ring_item.setData(0, "ring")
        fill = QColor("#abcdef")
        fill.setAlphaF(0.0)
        ring_item.setBrush(QBrush(fill))
        pushes = []
        canvas = SimpleNamespace(
            services=SimpleNamespace(history_service=_history_service(pushes.append)),
        )
        service = _color_service_for(canvas)

        service.apply_ring_fill_color(non_ring_item, QColor("#abcdef"))
        service.apply_ring_fill_color(ring_item, QColor("#abcdef"), alpha=-3.0)

        self.assertEqual(pushes, [])
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
            smiles_input_state=CanvasSmilesInputState(last_smiles_input="same"),
            _bond_state_dict=lambda current: {"color": current.color},
            services=SimpleNamespace(history_service=_history_service(pushes.append)),
        )
        set_bond_items_for(canvas, {0: [], 1: [none_item]})
        service = _color_service_for(canvas)

        service.apply_color_to_item(invalid_item, QColor("#112233"))
        service.apply_color_to_item(none_item, QColor("#112233"))
        service.apply_color_to_item(unchanged_item, QColor("#445566"))

        self.assertEqual(pushes, [])
        self.assertNotEqual(unchanged_item.pen().color().name(), "#445566")

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
            services=SimpleNamespace(
                history_service=_history_service(pushes.append),
                atom_label_service=SimpleNamespace(implicit_carbon_dot_brush=mock.Mock(return_value=brush))
            ),
        )
        _set_atom_graphics(canvas, {3: label_item}, {3: dot_proxy})
        service = _color_service_for(canvas)

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

    def test_apply_ring_structure_color_covers_invalid_metadata_and_dispatch(self) -> None:
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
            services=SimpleNamespace(
                history_service=_history_service(),
            ),
        )
        graph_service = SimpleNamespace(bond_sets_for_atoms=mock.Mock(return_value=({7}, set())))
        _set_atom_graphics(fallback_canvas, {1: atom_item})
        set_bond_items_for(fallback_canvas, {7: []})
        service = _color_service_for(fallback_canvas, graph_service=graph_service)
        service.apply_color_to_item = mock.Mock()

        service._apply_ring_structure_color(invalid_item, QColor("#123456"))
        service._apply_ring_structure_color(empty_item, QColor("#123456"))
        service._apply_ring_structure_color(ring_item, QColor("#123456"))

        graph_service.bond_sets_for_atoms.assert_called_once_with({1, 2})
        service.apply_color_to_item.assert_called_once_with(atom_item, QColor("#123456"))


if __name__ == "__main__":
    unittest.main()
