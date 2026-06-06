import unittest
from types import SimpleNamespace
from unittest import mock

from core.model import Atom, Bond
from PyQt6.QtCore import QPointF
from ui.canvas_hover_state import (
    HoverPreviewState,
    hover_preview_state_for,
    hover_state_for,
    set_hover_atom_id_for,
    set_hover_bond_id_for,
)
from ui.canvas_tool_settings_state import CanvasToolSettingsState
from ui.hover_interaction_service import HoverInteractionService


class HoverInteractionServiceTest(unittest.TestCase):
    def _make_canvas(
        self,
        *,
        atoms: dict[int, Atom] | None = None,
        bonds: list[Bond | None] | None = None,
        active_tool: str | None = "bond",
        active_bond_style: str = "wedge",
        active_bond_order: int = 1,
    ) -> SimpleNamespace:
        hover_scene_service = SimpleNamespace(
            clear_hover_highlight=mock.Mock(),
            add_atom_hover_indicator=mock.Mock(),
            add_bond_hover_indicator=mock.Mock(),
        )
        mark_hover_preview_service = SimpleNamespace(add_mark_hover_preview=mock.Mock())
        bond_hover_preview_service = mock.Mock()
        return SimpleNamespace(
            model=SimpleNamespace(atoms=atoms or {}, bonds=bonds or []),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            hover_preview_state=HoverPreviewState(),
            tool_settings_state=CanvasToolSettingsState(
                active_bond_style=active_bond_style,
                active_bond_order=active_bond_order,
            ),
            services=SimpleNamespace(
                tools=SimpleNamespace(active=None if active_tool is None else SimpleNamespace(name=active_tool)),
                hover_scene_service=hover_scene_service,
                mark_hover_preview_service=mark_hover_preview_service,
                bond_hover_preview_service=bond_hover_preview_service,
            ),
        )

    def _set_preferred_hit(self, canvas, hit):
        selection_controller = SimpleNamespace(preferred_structure_hit_at_scene_pos=mock.Mock(return_value=hit))
        canvas.services.selection_controller = selection_controller
        canvas.preferred_structure_hit_at_scene_pos = mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        )
        return selection_controller

    def _hover_service(self, canvas) -> HoverInteractionService:
        def active_tool():
            return getattr(canvas.services.tools, "active", None)

        return HoverInteractionService(
            canvas,
            selection_controller=getattr(canvas.services, "selection_controller", None),
            active_tool_provider=active_tool,
        )

    def test_update_hover_highlight_delegates_mark_tool(self) -> None:
        canvas = self._make_canvas(active_tool="mark")

        self._hover_service(canvas).update_hover_highlight(QPointF(1.0, 2.0))

        canvas.services.mark_hover_preview_service.add_mark_hover_preview.assert_called_once_with(QPointF(1.0, 2.0))
        canvas.services.hover_scene_service.clear_hover_highlight.assert_not_called()

    def test_update_hover_highlight_handles_no_atom_clear_and_preview_paths(self) -> None:
        clear_canvas = self._make_canvas(atoms={}, bonds=[], active_tool="select")

        self._hover_service(clear_canvas).update_hover_highlight(QPointF(2.0, 3.0))

        clear_canvas.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()
        clear_canvas.services.bond_hover_preview_service.add_free_bond_hover_preview.assert_not_called()

        preview_canvas = self._make_canvas(atoms={}, bonds=[], active_tool="bond")

        self._hover_service(preview_canvas).update_hover_highlight(QPointF(8.0, 9.0))

        preview_canvas.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()
        preview_canvas.services.bond_hover_preview_service.add_free_bond_hover_preview.assert_called_once_with(
            QPointF(8.0, 9.0)
        )
        self.assertEqual(hover_preview_state_for(preview_canvas).style, "wedge:1:8.0:9.0")

    def test_update_hover_highlight_handles_atom_bond_and_invalid_hits(self) -> None:
        atoms = {1: Atom("C", 10.0, 20.0), 2: Atom("C", 30.0, 20.0)}
        bonds = [Bond(1, 2)]

        atom_canvas = self._make_canvas(atoms=atoms, bonds=[], active_tool="bond", active_bond_style="wedge")
        self._set_preferred_hit(atom_canvas, SimpleNamespace(kind="atom", id=1))

        self._hover_service(atom_canvas).update_hover_highlight(QPointF(11.0, 12.0))

        atom_canvas.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()
        atom_canvas.services.hover_scene_service.add_atom_hover_indicator.assert_called_once_with(1)
        atom_canvas.services.bond_hover_preview_service.add_bond_tool_hover_preview.assert_called_once_with(
            1,
            QPointF(11.0, 12.0),
        )
        self.assertEqual(hover_state_for(atom_canvas).atom_id, 1)
        self.assertEqual(hover_preview_state_for(atom_canvas).style, "wedge:1:30.0:20.0")

        bond_canvas = self._make_canvas(atoms=atoms, bonds=bonds, active_tool="bond", active_bond_style="hash")
        self._set_preferred_hit(bond_canvas, SimpleNamespace(kind="bond", id=0))

        self._hover_service(bond_canvas).update_hover_highlight(QPointF(4.0, 5.0))

        bond_canvas.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()
        bond_canvas.services.hover_scene_service.add_bond_hover_indicator.assert_called_once_with(0)
        bond_canvas.services.bond_hover_preview_service.add_bond_style_hover_preview.assert_called_once_with(bonds[0])
        self.assertEqual(hover_state_for(bond_canvas).bond_id, 0)

        invalid_canvas = self._make_canvas(atoms=atoms, bonds=bonds, active_tool="bond")
        self._set_preferred_hit(invalid_canvas, SimpleNamespace(kind="other", id="x"))

        self._hover_service(invalid_canvas).update_hover_highlight(QPointF(9.0, 9.0))

        invalid_canvas.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()
        invalid_canvas.services.hover_scene_service.add_atom_hover_indicator.assert_not_called()
        invalid_canvas.services.hover_scene_service.add_bond_hover_indicator.assert_not_called()

    def test_update_hover_highlight_uses_selection_controller_when_available(self) -> None:
        atoms = {1: Atom("C", 10.0, 20.0)}
        selection_controller = SimpleNamespace(
            preferred_structure_hit_at_scene_pos=mock.Mock(return_value=SimpleNamespace(kind="atom", id=1))
        )
        canvas = self._make_canvas(atoms=atoms, active_tool="bond", active_bond_style="wedge")
        canvas.services.selection_controller = selection_controller
        canvas.preferred_structure_hit_at_scene_pos = mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        )

        self._hover_service(canvas).update_hover_highlight(QPointF(11.0, 12.0))

        selection_controller.preferred_structure_hit_at_scene_pos.assert_called_once_with(QPointF(11.0, 12.0))
        canvas.preferred_structure_hit_at_scene_pos.assert_not_called()
        canvas.services.hover_scene_service.add_atom_hover_indicator.assert_called_once_with(1)

    def test_update_hover_highlight_uses_services_selection_controller(self) -> None:
        atoms = {1: Atom("C", 10.0, 20.0)}
        selection_controller = SimpleNamespace(
            preferred_structure_hit_at_scene_pos=mock.Mock(return_value=SimpleNamespace(kind="atom", id=1))
        )
        canvas = self._make_canvas(atoms=atoms, active_tool="select", active_bond_style="wedge")
        canvas.services.selection_controller = selection_controller
        canvas.preferred_structure_hit_at_scene_pos = mock.Mock(
            side_effect=AssertionError("canvas facade should not be used")
        )

        self._hover_service(canvas).update_hover_highlight(QPointF(11.0, 12.0))

        selection_controller.preferred_structure_hit_at_scene_pos.assert_called_once_with(QPointF(11.0, 12.0))
        canvas.preferred_structure_hit_at_scene_pos.assert_not_called()
        canvas.services.hover_scene_service.add_atom_hover_indicator.assert_called_once_with(1)

    def test_update_hover_highlight_skips_noop_paths(self) -> None:
        atom_canvas = self._make_canvas(atoms={1: Atom("C", 10.0, 20.0)}, active_tool="bond")
        self._set_preferred_hit(atom_canvas, SimpleNamespace(kind="atom", id=1))
        set_hover_atom_id_for(atom_canvas, 1)
        hover_preview_state_for(atom_canvas).style = "wedge:1:30.0:20.0"

        self._hover_service(atom_canvas).update_hover_highlight(QPointF(11.0, 12.0))

        atom_canvas.services.hover_scene_service.clear_hover_highlight.assert_not_called()
        atom_canvas.services.hover_scene_service.add_atom_hover_indicator.assert_not_called()
        atom_canvas.services.bond_hover_preview_service.add_bond_tool_hover_preview.assert_not_called()

        bond_canvas = self._make_canvas(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 1.0, 1.0)}, bonds=[Bond(1, 2)], active_tool="bond", active_bond_style="hash")
        self._set_preferred_hit(bond_canvas, SimpleNamespace(kind="bond", id=0))
        set_hover_bond_id_for(bond_canvas, 0)
        hover_preview_state_for(bond_canvas).style = "hash"

        self._hover_service(bond_canvas).update_hover_highlight(QPointF(4.0, 5.0))

        bond_canvas.services.hover_scene_service.clear_hover_highlight.assert_not_called()
        bond_canvas.services.hover_scene_service.add_bond_hover_indicator.assert_not_called()
        bond_canvas.services.bond_hover_preview_service.add_bond_style_hover_preview.assert_not_called()

    def test_atom_preview_returns_signature_without_key_for_missing_atom(self) -> None:
        canvas = self._make_canvas(atoms={1: Atom("C", 0.0, 0.0)}, active_tool="bond")

        signature, key = self._hover_service(canvas)._atom_preview(
            QPointF(4.0, 5.0),
            SimpleNamespace(kind="atom", id=99),
        )

        self.assertEqual(signature, "wedge:1")
        self.assertIsNone(key)

    def test_apply_plan_clears_for_missing_atom_or_bond_targets(self) -> None:
        canvas = self._make_canvas(atoms={1: Atom("C", 0.0, 0.0)}, active_tool="bond")
        service = self._hover_service(canvas)

        service._apply_plan(SimpleNamespace(action="atom_hit", hover_atom_id=None, preview_key="wedge"), QPointF())
        canvas.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()
        canvas.services.hover_scene_service.add_atom_hover_indicator.assert_not_called()

        canvas.services.hover_scene_service.clear_hover_highlight.reset_mock()
        service._apply_plan(SimpleNamespace(action="bond_hit", hover_bond_id=None, preview_key="hash"), QPointF())
        canvas.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()
        canvas.services.hover_scene_service.add_bond_hover_indicator.assert_not_called()

    def test_apply_plan_skips_missing_bond_objects_and_bond_lookup_handles_exceptions(self) -> None:
        none_bond_canvas = self._make_canvas(
            atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 1.0, 0.0)},
            bonds=[None],
            active_tool="bond",
        )
        service = self._hover_service(none_bond_canvas)

        service._apply_plan(SimpleNamespace(action="bond_hit", hover_bond_id=0, preview_key="hash"), QPointF())

        none_bond_canvas.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()
        self.assertEqual(hover_state_for(none_bond_canvas).bond_id, 0)
        none_bond_canvas.services.hover_scene_service.add_bond_hover_indicator.assert_not_called()
        none_bond_canvas.services.bond_hover_preview_service.add_bond_style_hover_preview.assert_not_called()

        bad_key_canvas = self._make_canvas()
        bad_key_canvas.model.bonds = {}
        self.assertIsNone(self._hover_service(bad_key_canvas)._bond_for_id(3))

        bad_type_canvas = self._make_canvas()
        bad_type_canvas.model.bonds = None
        self.assertIsNone(self._hover_service(bad_type_canvas)._bond_for_id(0))


if __name__ == "__main__":
    unittest.main()
