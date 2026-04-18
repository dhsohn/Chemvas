from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import QApplication, QGraphicsEllipseItem, QGraphicsScene, QGraphicsTextItem
except ModuleNotFoundError:
    QApplication = None
    QGraphicsEllipseItem = None
    QGraphicsScene = None
    QGraphicsTextItem = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.model import Atom, Bond
    from ui.bond_hover_preview_service import BondHoverPreviewService
    from ui.canvas_view import CanvasView
    from ui.mark_hover_preview_service import MarkHoverPreviewService


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewHoverPreviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _make_view(
        self,
        *,
        scene: QGraphicsScene | None = None,
        atoms: dict[int, Atom] | None = None,
        bonds: list[Bond | None] | None = None,
        active_tool: str | None = "bond",
        active_bond_style: str = "wedge",
        active_bond_order: int = 1,
        mark_kind: str = "plus",
    ) -> SimpleNamespace:
        scene = scene or QGraphicsScene()
        renderer = SimpleNamespace(
            style=SimpleNamespace(
                atom_color="#224466",
                bond_length_px=20.0,
                bond_line_width=2.0,
                bond_spacing_px=1.5,
                bold_bond_width=3.0,
                hash_spacing_px=1.0,
            ),
            atom_font=lambda: QFont(),
        )
        return SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms=atoms or {}, bonds=bonds or []),
            renderer=renderer,
            tools=SimpleNamespace(active=None if active_tool is None else SimpleNamespace(name=active_tool)),
            hover_items=[],
            hover_atom_id=None,
            hover_bond_id=None,
            _hover_preview_style=None,
            mark_kind=mark_kind,
            active_bond_style=active_bond_style,
            active_bond_order=active_bond_order,
        )

    def _bind_mark_helpers(self, view: SimpleNamespace) -> None:
        view._atom_pick_radius = lambda: CanvasView._atom_pick_radius(view)
        view._mark_selection_radius = lambda: CanvasView._mark_selection_radius(view)
        view._clear_hover_highlight = lambda: CanvasView._clear_hover_highlight(view)
        view._build_mark_item = lambda kind: CanvasView._build_mark_item(view, kind)
        view._set_mark_center = lambda item, center: CanvasView._set_mark_center(view, item, center)
        view._add_atom_hover_indicator = lambda atom_id: CanvasView._add_atom_hover_indicator(view, atom_id)
        view._add_hover_preview_items = lambda items: CanvasView._add_hover_preview_items(view, items)
        view._mark_hover_preview_service = MarkHoverPreviewService(view)

    def _bind_bond_hover_preview_service(self, view: SimpleNamespace) -> None:
        view._bond_hover_preview_service = BondHoverPreviewService(view)

    def test_add_mark_hover_preview_adds_and_skips_duplicate_previews(self) -> None:
        scene = QGraphicsScene()
        view = self._make_view(scene=scene, atoms={1: Atom("C", 10.0, 20.0)}, active_tool=None)
        self._bind_mark_helpers(view)
        view.find_atom_near = mock.Mock(return_value=1)
        view._mark_center_for_pointer = mock.Mock(return_value=QPointF(12.0, 18.0))

        CanvasView._add_mark_hover_preview(view, QPointF(4.0, 5.0))

        self.assertEqual(view.hover_atom_id, 1)
        self.assertEqual(view.hover_bond_id, None)
        self.assertEqual(view._hover_preview_style, "mark:plus:atom:1:12.0:18.0")
        self.assertEqual(len(view.hover_items), 2)
        self.assertEqual(len(scene.items()), 2)

        view.find_atom_near.reset_mock()
        view._mark_center_for_pointer.reset_mock()
        view._clear_hover_highlight = mock.Mock()
        view._add_atom_hover_indicator = mock.Mock()
        view._add_hover_preview_items = mock.Mock()

        CanvasView._add_mark_hover_preview(view, QPointF(4.0, 5.0))

        view._clear_hover_highlight.assert_not_called()
        view._add_atom_hover_indicator.assert_not_called()
        view._add_hover_preview_items.assert_not_called()
        self.assertEqual(len(view.hover_items), 2)
        self.assertEqual(len(scene.items()), 2)

        free_view = self._make_view(active_tool=None)
        self._bind_mark_helpers(free_view)
        free_view.find_atom_near = mock.Mock(return_value=None)
        free_view._mark_center_for_pointer = mock.Mock(return_value=QPointF(3.5, 7.5))
        free_view._hover_preview_style = "mark:plus:free:3.5:7.5"
        free_view._clear_hover_highlight = mock.Mock()

        CanvasView._add_mark_hover_preview(free_view, QPointF(3.5, 7.5))

        free_view._clear_hover_highlight.assert_not_called()
        self.assertEqual(free_view.hover_items, [])

    def test_update_hover_highlight_handles_mark_empty_atom_and_bond_paths(self) -> None:
        mark_view = self._make_view(active_tool="mark")
        mark_view._add_mark_hover_preview = mock.Mock()

        CanvasView._update_hover_highlight(mark_view, QPointF(1.0, 2.0))
        mark_view._add_mark_hover_preview.assert_called_once_with(QPointF(1.0, 2.0))

        no_atoms_clear = self._make_view(atoms={}, bonds=[], active_tool="select")
        no_atoms_clear._clear_hover_highlight = mock.Mock()
        no_atoms_clear._bond_preview_signature = mock.Mock(return_value=None)
        CanvasView._update_hover_highlight(no_atoms_clear, QPointF(2.0, 3.0))
        no_atoms_clear._clear_hover_highlight.assert_called_once_with()

        no_atoms_preview = self._make_view(atoms={}, bonds=[], active_tool="bond")
        self._bind_bond_hover_preview_service(no_atoms_preview)
        no_atoms_preview._clear_hover_highlight = mock.Mock()
        no_atoms_preview._bond_preview_signature = mock.Mock(return_value="wedge:1")
        no_atoms_preview._build_bond_preview_items = mock.Mock(return_value=["preview"])
        no_atoms_preview._add_hover_preview_items = mock.Mock()

        CanvasView._update_hover_highlight(no_atoms_preview, QPointF(8.0, 9.0))

        no_atoms_preview._clear_hover_highlight.assert_called_once_with()
        no_atoms_preview._build_bond_preview_items.assert_called_once_with(QPointF(8.0, 9.0), QPointF(28.0, 9.0))
        no_atoms_preview._add_hover_preview_items.assert_called_once_with(["preview"])
        self.assertEqual(no_atoms_preview._hover_preview_style, "wedge:1:8.0:9.0")

    def test_update_hover_highlight_handles_atom_hits_bond_hits_and_invalid_hits(self) -> None:
        atoms = {1: Atom("C", 10.0, 20.0), 2: Atom("C", 30.0, 20.0)}
        bonds = [Bond(1, 2)]

        atom_view = self._make_view(atoms=atoms, bonds=bonds, active_tool="bond", active_bond_style="wedge")
        self._bind_bond_hover_preview_service(atom_view)
        atom_view.preferred_structure_hit_at_scene_pos = mock.Mock(return_value=SimpleNamespace(kind="atom", id=1))
        atom_view._clear_hover_highlight = mock.Mock()
        atom_view._add_atom_hover_indicator = mock.Mock()
        atom_view._bond_hover_endpoint = mock.Mock(return_value=QPointF(13.0, 14.0))
        atom_view._add_bond_tool_hover_preview = mock.Mock()
        atom_view._bond_preview_signature = lambda: CanvasView._bond_preview_signature(atom_view)

        CanvasView._update_hover_highlight(atom_view, QPointF(11.0, 12.0))

        atom_view._clear_hover_highlight.assert_called_once_with()
        atom_view._add_atom_hover_indicator.assert_called_once_with(1)
        atom_view._add_bond_tool_hover_preview.assert_called_once_with(1, QPointF(11.0, 12.0))
        self.assertEqual(atom_view.hover_atom_id, 1)
        self.assertEqual(atom_view._hover_preview_style, "wedge:1:13.0:14.0")

        bond_view = self._make_view(atoms=atoms, bonds=bonds, active_tool="bond", active_bond_style="hash")
        self._bind_bond_hover_preview_service(bond_view)
        bond_view.preferred_structure_hit_at_scene_pos = mock.Mock(return_value=SimpleNamespace(kind="bond", id=0))
        bond_view._clear_hover_highlight = mock.Mock()
        bond_view._add_bond_style_hover_preview = mock.Mock(
            side_effect=lambda bond: setattr(bond_view, "_hover_preview_style", bond_view.active_bond_style)
        )

        CanvasView._update_hover_highlight(bond_view, QPointF(4.0, 5.0))

        bond_view._clear_hover_highlight.assert_called_once_with()
        bond_view._add_bond_style_hover_preview.assert_called_once_with(bonds[0])
        self.assertEqual(bond_view.hover_bond_id, 0)
        self.assertEqual(bond_view._hover_preview_style, "hash")

        invalid_view = self._make_view(atoms=atoms, bonds=bonds, active_tool="bond")
        invalid_view.preferred_structure_hit_at_scene_pos = mock.Mock(return_value=SimpleNamespace(kind="other", id="x"))
        invalid_view._clear_hover_highlight = mock.Mock()

        CanvasView._update_hover_highlight(invalid_view, QPointF(9.0, 9.0))

        invalid_view._clear_hover_highlight.assert_called_once_with()
        self.assertIsNone(invalid_view.hover_atom_id)
        self.assertIsNone(invalid_view.hover_bond_id)

    def test_add_bond_style_hover_preview_and_add_bond_tool_hover_preview_cover_success_and_skip_paths(self) -> None:
        atoms = {1: Atom("C", 10.0, 20.0), 2: Atom("C", 30.0, 20.0)}
        bond = Bond(1, 2)

        style_view = self._make_view(atoms=atoms, bonds=[bond], active_tool="bond", active_bond_style="wedge")
        self._bind_bond_hover_preview_service(style_view)
        style_view._build_bond_preview_items = mock.Mock(return_value=["style-preview"])
        style_view._add_hover_preview_items = mock.Mock()

        CanvasView._add_bond_style_hover_preview(style_view, bond)

        style_view._build_bond_preview_items.assert_called_once_with(QPointF(10.0, 20.0), QPointF(30.0, 20.0), 1, 2)
        style_view._add_hover_preview_items.assert_called_once_with(["style-preview"])
        self.assertEqual(style_view._hover_preview_style, "wedge")

        for tool_name, style_name, atom_map, expected_calls in [
            ("select", "wedge", atoms, 0),
            ("bond", "single", atoms, 0),
            ("bond", "wedge", {1: Atom("C", 10.0, 20.0)}, 0),
        ]:
            with self.subTest(tool_name=tool_name, style_name=style_name, atom_count=len(atom_map)):
                skip_view = self._make_view(atoms=atom_map, bonds=[bond], active_tool=tool_name, active_bond_style=style_name)
                self._bind_bond_hover_preview_service(skip_view)
                skip_view._build_bond_preview_items = mock.Mock()
                skip_view._add_hover_preview_items = mock.Mock()
                CanvasView._add_bond_style_hover_preview(skip_view, bond)
                self.assertEqual(skip_view._build_bond_preview_items.call_count, expected_calls)
                self.assertEqual(skip_view._add_hover_preview_items.call_count, expected_calls)

        tool_view = self._make_view(atoms=atoms, bonds=[bond], active_tool="bond")
        self._bind_bond_hover_preview_service(tool_view)
        tool_view._bond_hover_endpoint = mock.Mock(return_value=QPointF(17.0, 18.0))
        tool_view._build_bond_preview_items = mock.Mock(return_value=["tool-preview"])
        tool_view._add_hover_preview_items = mock.Mock()

        CanvasView._add_bond_tool_hover_preview(tool_view, 1, QPointF(40.0, 41.0))

        tool_view._bond_hover_endpoint.assert_called_once_with(QPointF(10.0, 20.0), QPointF(40.0, 41.0), 1)
        tool_view._build_bond_preview_items.assert_called_once_with(QPointF(10.0, 20.0), QPointF(17.0, 18.0), 1, None)
        tool_view._add_hover_preview_items.assert_called_once_with(["tool-preview"])

        missing_atom_view = self._make_view(atoms=atoms, bonds=[bond], active_tool="bond")
        self._bind_bond_hover_preview_service(missing_atom_view)
        missing_atom_view._build_bond_preview_items = mock.Mock()
        missing_atom_view._add_hover_preview_items = mock.Mock()
        CanvasView._add_bond_tool_hover_preview(missing_atom_view, 999, QPointF(1.0, 2.0))
        missing_atom_view._build_bond_preview_items.assert_not_called()
        missing_atom_view._add_hover_preview_items.assert_not_called()

        nonbond_view = self._make_view(atoms=atoms, bonds=[bond], active_tool="select")
        self._bind_bond_hover_preview_service(nonbond_view)
        nonbond_view._build_bond_preview_items = mock.Mock()
        nonbond_view._add_hover_preview_items = mock.Mock()
        CanvasView._add_bond_tool_hover_preview(nonbond_view, 1, QPointF(1.0, 2.0))
        nonbond_view._build_bond_preview_items.assert_not_called()
        nonbond_view._add_hover_preview_items.assert_not_called()

    def test_add_hover_preview_items_appends_scene_items_and_ignores_empty_input(self) -> None:
        scene = QGraphicsScene()
        view = self._make_view(scene=scene, active_tool=None)
        existing = object()
        view.hover_items = [existing]

        CanvasView._add_hover_preview_items(view, [])

        self.assertEqual(view.hover_items, [existing])
        self.assertEqual(len(scene.items()), 0)

        text = QGraphicsTextItem("hover")
        dot = QGraphicsEllipseItem(0.0, 0.0, 4.0, 4.0)

        CanvasView._add_hover_preview_items(view, [text, dot])

        self.assertEqual(view.hover_items[0], existing)
        self.assertEqual(view.hover_items[1:], [text, dot])
        self.assertIs(text.scene(), scene)
        self.assertIs(dot.scene(), scene)
        self.assertEqual(len(scene.items()), 2)


if __name__ == "__main__":
    unittest.main()
