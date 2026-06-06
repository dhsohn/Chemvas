from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsEllipseItem,
        QGraphicsScene,
        QGraphicsTextItem,
    )
except ModuleNotFoundError:
    QApplication = None
    QGraphicsEllipseItem = None
    QGraphicsScene = None
    QGraphicsTextItem = None

if QApplication is not None:
    from core.model import Atom, Bond
    from ui.bond_hover_preview_service import BondHoverPreviewService
    from ui.canvas_hover_state import (
        HoverPreviewState,
        hover_preview_state_for,
        hover_state_for,
        set_hover_items_for,
    )
    from ui.canvas_scene_decoration_build_service import (
        CanvasSceneDecorationBuildService,
    )
    from ui.canvas_tool_settings_state import CanvasToolSettingsState
    from ui.hover_highlight_access import add_hover_preview_items_for
    from ui.hover_interaction_access import update_hover_highlight_for
    from ui.hover_interaction_service import HoverInteractionService
    from ui.hover_scene_service import HoverSceneService
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
        view = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms=atoms or {}, bonds=bonds or []),
            renderer=renderer,
            hover_preview_state=HoverPreviewState(),
            tool_settings_state=CanvasToolSettingsState(
                mark_kind=mark_kind,
                active_bond_style=active_bond_style,
                active_bond_order=active_bond_order,
            ),
        )
        view.services = SimpleNamespace()
        view.services.tools = SimpleNamespace(active=None if active_tool is None else SimpleNamespace(name=active_tool))
        view.active_tool_provider = lambda: getattr(view.services.tools, "active", None)
        view.active_tool_name_provider = lambda: (
            str(name) if (name := getattr(view.active_tool_provider(), "name", None)) else None
        )
        view.services.hover_scene_service = HoverSceneService(view)
        view.services.hover_interaction_service = HoverInteractionService(
            view,
            selection_controller=getattr(view.services, "selection_controller", None),
            active_tool_provider=view.active_tool_provider,
        )
        return view

    def _bind_mark_helpers(self, view: SimpleNamespace) -> None:
        view.services.scene_decoration_build_service = CanvasSceneDecorationBuildService(view)
        view.services.mark_hover_preview_service = MarkHoverPreviewService(
            view,
            hit_testing_service=view.services.hit_testing_service,
            hover_scene_service=view.services.hover_scene_service,
        )

    def _bind_bond_hover_preview_service(self, view: SimpleNamespace) -> None:
        view.services.hover_scene_service = SimpleNamespace(
            add_hover_preview_items=mock.Mock(),
            clear_hover_highlight=mock.Mock(),
        )
        view.bond_preview_build_items = mock.Mock(return_value=["preview"])
        view.bond_hover_endpoint = mock.Mock(return_value=QPointF(17.0, 18.0))
        build_patcher = mock.patch(
            "ui.bond_hover_preview_service.build_bond_preview_items_for",
            side_effect=lambda canvas, start, end, *atom_ids: canvas.bond_preview_build_items(
                start,
                end,
                *atom_ids,
            ),
        )
        endpoint_patcher = mock.patch(
            "ui.bond_hover_preview_service.bond_hover_endpoint_for",
            side_effect=lambda canvas, start, pos, atom_id: canvas.bond_hover_endpoint(start, pos, atom_id),
        )
        build_patcher.start()
        endpoint_patcher.start()
        self.addCleanup(build_patcher.stop)
        self.addCleanup(endpoint_patcher.stop)
        view.services.bond_hover_preview_service = BondHoverPreviewService(
            view,
            hover_scene_service=view.services.hover_scene_service,
            active_tool_name_provider=view.active_tool_name_provider,
        )

    def test_add_mark_hover_preview_adds_and_skips_duplicate_previews(self) -> None:
        scene = QGraphicsScene()
        view = self._make_view(scene=scene, atoms={1: Atom("C", 10.0, 20.0)}, active_tool=None)
        view.services.hit_testing_service = SimpleNamespace(find_atom_near=mock.Mock(return_value=1))
        self._bind_mark_helpers(view)
        view.services.canvas_mark_scene_service = SimpleNamespace(
            mark_center_for_pointer=mock.Mock(return_value=QPointF(12.0, 18.0))
        )

        view.services.mark_hover_preview_service.add_mark_hover_preview(QPointF(4.0, 5.0))

        self.assertEqual(hover_state_for(view).atom_id, 1)
        self.assertEqual(hover_state_for(view).bond_id, None)
        self.assertEqual(hover_preview_state_for(view).style, "mark:plus:atom:1:12.0:18.0")
        self.assertEqual(len(hover_state_for(view).items), 2)
        self.assertEqual(len(scene.items()), 2)

        view.services.hit_testing_service.find_atom_near.reset_mock()
        view.services.canvas_mark_scene_service.mark_center_for_pointer.reset_mock()
        view.services.hover_scene_service.clear_hover_highlight = mock.Mock()
        view.services.hover_scene_service.add_atom_hover_indicator = mock.Mock()
        view.services.hover_scene_service.add_hover_preview_items = mock.Mock()

        view.services.mark_hover_preview_service.add_mark_hover_preview(QPointF(4.0, 5.0))

        view.services.hover_scene_service.clear_hover_highlight.assert_not_called()
        view.services.hover_scene_service.add_atom_hover_indicator.assert_not_called()
        view.services.hover_scene_service.add_hover_preview_items.assert_not_called()
        self.assertEqual(len(hover_state_for(view).items), 2)
        self.assertEqual(len(scene.items()), 2)

        free_view = self._make_view(active_tool=None)
        free_view.services.hit_testing_service = SimpleNamespace(find_atom_near=mock.Mock(return_value=None))
        self._bind_mark_helpers(free_view)
        free_view.services.canvas_mark_scene_service = SimpleNamespace(
            mark_center_for_pointer=mock.Mock(return_value=QPointF(3.5, 7.5))
        )
        hover_preview_state_for(free_view).style = "mark:plus:free:3.5:7.5"
        free_view.services.hover_scene_service.clear_hover_highlight = mock.Mock()

        free_view.services.mark_hover_preview_service.add_mark_hover_preview(QPointF(3.5, 7.5))

        free_view.services.hover_scene_service.clear_hover_highlight.assert_not_called()
        self.assertEqual(hover_state_for(free_view).items, [])

    def test_update_hover_highlight_handles_mark_empty_atom_and_bond_paths(self) -> None:
        mark_view = self._make_view(active_tool="mark")
        mark_view.services.mark_hover_preview_service = SimpleNamespace(add_mark_hover_preview=mock.Mock())

        update_hover_highlight_for(mark_view, QPointF(1.0, 2.0))
        mark_view.services.mark_hover_preview_service.add_mark_hover_preview.assert_called_once_with(QPointF(1.0, 2.0))

        no_atoms_clear = self._make_view(atoms={}, bonds=[], active_tool="select")
        no_atoms_clear.services.hover_scene_service.clear_hover_highlight = mock.Mock()
        update_hover_highlight_for(no_atoms_clear, QPointF(2.0, 3.0))
        no_atoms_clear.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()

        no_atoms_preview = self._make_view(atoms={}, bonds=[], active_tool="bond")
        self._bind_bond_hover_preview_service(no_atoms_preview)
        no_atoms_preview.bond_preview_build_items.return_value = ["preview"]

        update_hover_highlight_for(no_atoms_preview, QPointF(8.0, 9.0))

        no_atoms_preview.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()
        no_atoms_preview.bond_preview_build_items.assert_called_once_with(
            QPointF(8.0, 9.0),
            QPointF(28.0, 9.0),
        )
        no_atoms_preview.services.hover_scene_service.add_hover_preview_items.assert_called_once_with(["preview"])
        self.assertEqual(hover_preview_state_for(no_atoms_preview).style, "wedge:1:8.0:9.0")

    def test_update_hover_highlight_handles_atom_hits_bond_hits_and_invalid_hits(self) -> None:
        atoms = {1: Atom("C", 10.0, 20.0), 2: Atom("C", 30.0, 20.0)}
        bonds = [Bond(1, 2)]

        atom_view = self._make_view(atoms=atoms, bonds=bonds, active_tool="bond", active_bond_style="wedge")
        self._bind_bond_hover_preview_service(atom_view)
        atom_view.services.selection_controller = SimpleNamespace(
            preferred_structure_hit_at_scene_pos=mock.Mock(return_value=SimpleNamespace(kind="atom", id=1))
        )
        atom_view.services.hover_interaction_service = HoverInteractionService(
            atom_view,
            selection_controller=atom_view.services.selection_controller,
            active_tool_provider=atom_view.active_tool_provider,
        )
        atom_view.services.hover_scene_service.clear_hover_highlight = mock.Mock()
        atom_view.services.hover_scene_service.add_atom_hover_indicator = mock.Mock()
        atom_view.bond_hover_endpoint.return_value = QPointF(13.0, 14.0)
        atom_view.bond_preview_build_items.return_value = ["atom-preview"]

        update_hover_highlight_for(atom_view, QPointF(11.0, 12.0))

        atom_view.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()
        atom_view.services.hover_scene_service.add_atom_hover_indicator.assert_called_once_with(1)
        atom_view.bond_preview_build_items.assert_called_once_with(
            QPointF(10.0, 20.0),
            QPointF(13.0, 14.0),
            1,
            None,
        )
        atom_view.services.hover_scene_service.add_hover_preview_items.assert_called_once_with(["atom-preview"])
        self.assertEqual(hover_state_for(atom_view).atom_id, 1)
        self.assertEqual(hover_preview_state_for(atom_view).style, "wedge:1:0.0:2.7")

        bond_view = self._make_view(atoms=atoms, bonds=bonds, active_tool="bond", active_bond_style="hash")
        self._bind_bond_hover_preview_service(bond_view)
        bond_view.services.selection_controller = SimpleNamespace(
            preferred_structure_hit_at_scene_pos=mock.Mock(return_value=SimpleNamespace(kind="bond", id=0))
        )
        bond_view.services.hover_interaction_service = HoverInteractionService(
            bond_view,
            selection_controller=bond_view.services.selection_controller,
            active_tool_provider=bond_view.active_tool_provider,
        )
        bond_view.bond_preview_build_items.return_value = ["bond-preview"]

        update_hover_highlight_for(bond_view, QPointF(4.0, 5.0))

        bond_view.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()
        bond_view.bond_preview_build_items.assert_called_once_with(
            QPointF(10.0, 20.0),
            QPointF(30.0, 20.0),
            1,
            2,
        )
        bond_view.services.hover_scene_service.add_hover_preview_items.assert_called_once_with(["bond-preview"])
        self.assertEqual(hover_state_for(bond_view).bond_id, 0)
        self.assertEqual(hover_preview_state_for(bond_view).style, "hash")

        invalid_view = self._make_view(atoms=atoms, bonds=bonds, active_tool="bond")
        invalid_view.services.selection_controller = SimpleNamespace(
            preferred_structure_hit_at_scene_pos=mock.Mock(return_value=SimpleNamespace(kind="other", id="x"))
        )
        invalid_view.services.hover_interaction_service = HoverInteractionService(
            invalid_view,
            selection_controller=invalid_view.services.selection_controller,
            active_tool_provider=invalid_view.active_tool_provider,
        )
        invalid_view.services.hover_scene_service.clear_hover_highlight = mock.Mock()

        update_hover_highlight_for(invalid_view, QPointF(9.0, 9.0))

        invalid_view.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()
        self.assertIsNone(hover_state_for(invalid_view).atom_id)
        self.assertIsNone(hover_state_for(invalid_view).bond_id)

    def test_add_bond_style_hover_preview_and_add_bond_tool_hover_preview_cover_success_and_skip_paths(self) -> None:
        atoms = {1: Atom("C", 10.0, 20.0), 2: Atom("C", 30.0, 20.0)}
        bond = Bond(1, 2)

        style_view = self._make_view(atoms=atoms, bonds=[bond], active_tool="bond", active_bond_style="wedge")
        self._bind_bond_hover_preview_service(style_view)
        style_view.bond_preview_build_items.return_value = ["style-preview"]

        style_view.services.bond_hover_preview_service.add_bond_style_hover_preview(bond)

        style_view.bond_preview_build_items.assert_called_once_with(
            QPointF(10.0, 20.0),
            QPointF(30.0, 20.0),
            1,
            2,
        )
        style_view.services.hover_scene_service.add_hover_preview_items.assert_called_once_with(["style-preview"])
        self.assertEqual(hover_preview_state_for(style_view).style, "wedge")

        for tool_name, style_name, atom_map, expected_calls in [
            ("select", "wedge", atoms, 0),
            ("bond", "single", atoms, 0),
            ("bond", "wedge", {1: Atom("C", 10.0, 20.0)}, 0),
        ]:
            with self.subTest(tool_name=tool_name, style_name=style_name, atom_count=len(atom_map)):
                skip_view = self._make_view(atoms=atom_map, bonds=[bond], active_tool=tool_name, active_bond_style=style_name)
                self._bind_bond_hover_preview_service(skip_view)
                skip_view.services.bond_hover_preview_service.add_bond_style_hover_preview(bond)
                self.assertEqual(skip_view.bond_preview_build_items.call_count, expected_calls)
                self.assertEqual(skip_view.services.hover_scene_service.add_hover_preview_items.call_count, expected_calls)

        tool_view = self._make_view(atoms=atoms, bonds=[bond], active_tool="bond")
        self._bind_bond_hover_preview_service(tool_view)
        tool_view.bond_hover_endpoint.return_value = QPointF(17.0, 18.0)
        tool_view.bond_preview_build_items.return_value = ["tool-preview"]

        tool_view.services.bond_hover_preview_service.add_bond_tool_hover_preview(1, QPointF(40.0, 41.0))

        tool_view.bond_hover_endpoint.assert_called_once_with(
            QPointF(10.0, 20.0),
            QPointF(40.0, 41.0),
            1,
        )
        tool_view.bond_preview_build_items.assert_called_once_with(
            QPointF(10.0, 20.0),
            QPointF(17.0, 18.0),
            1,
            None,
        )
        tool_view.services.hover_scene_service.add_hover_preview_items.assert_called_once_with(["tool-preview"])

        missing_atom_view = self._make_view(atoms=atoms, bonds=[bond], active_tool="bond")
        self._bind_bond_hover_preview_service(missing_atom_view)
        missing_atom_view.services.bond_hover_preview_service.add_bond_tool_hover_preview(999, QPointF(1.0, 2.0))
        missing_atom_view.bond_preview_build_items.assert_not_called()
        missing_atom_view.services.hover_scene_service.add_hover_preview_items.assert_not_called()

        nonbond_view = self._make_view(atoms=atoms, bonds=[bond], active_tool="select")
        self._bind_bond_hover_preview_service(nonbond_view)
        nonbond_view.services.bond_hover_preview_service.add_bond_tool_hover_preview(1, QPointF(1.0, 2.0))
        nonbond_view.bond_preview_build_items.assert_not_called()
        nonbond_view.services.hover_scene_service.add_hover_preview_items.assert_not_called()

    def test_add_hover_preview_items_appends_scene_items_and_ignores_empty_input(self) -> None:
        scene = QGraphicsScene()
        view = self._make_view(scene=scene, active_tool=None)
        existing = object()
        set_hover_items_for(view, [existing])

        add_hover_preview_items_for(view, [])

        self.assertEqual(hover_state_for(view).items, [existing])
        self.assertEqual(len(scene.items()), 0)

        text = QGraphicsTextItem("hover")
        dot = QGraphicsEllipseItem(0.0, 0.0, 4.0, 4.0)

        add_hover_preview_items_for(view, [text, dot])

        self.assertEqual(hover_state_for(view).items[0], existing)
        self.assertEqual(hover_state_for(view).items[1:], [text, dot])
        self.assertIs(text.scene(), scene)
        self.assertIs(dot.scene(), scene)
        self.assertEqual(len(scene.items()), 2)


if __name__ == "__main__":
    unittest.main()
