import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PyQt6.QtCore import QPointF


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.model import Atom, Bond
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
        return SimpleNamespace(
            model=SimpleNamespace(atoms=atoms or {}, bonds=bonds or []),
            tools=SimpleNamespace(active=None if active_tool is None else SimpleNamespace(name=active_tool)),
            hover_atom_id=None,
            hover_bond_id=None,
            _hover_preview_style=None,
            active_bond_style=active_bond_style,
            active_bond_order=active_bond_order,
            _clear_hover_highlight=mock.Mock(),
            _add_mark_hover_preview=mock.Mock(),
            _add_atom_hover_indicator=mock.Mock(),
            _add_bond_hover_indicator=mock.Mock(),
            _add_bond_tool_hover_preview=mock.Mock(),
            _add_bond_style_hover_preview=mock.Mock(),
            _bond_hover_preview_service=mock.Mock(),
        )

    def test_update_hover_highlight_delegates_mark_tool(self) -> None:
        canvas = self._make_canvas(active_tool="mark")

        HoverInteractionService(canvas).update_hover_highlight(QPointF(1.0, 2.0))

        canvas._add_mark_hover_preview.assert_called_once_with(QPointF(1.0, 2.0))
        canvas._clear_hover_highlight.assert_not_called()

    def test_update_hover_highlight_handles_no_atom_clear_and_preview_paths(self) -> None:
        clear_canvas = self._make_canvas(atoms={}, bonds=[], active_tool="select")
        clear_canvas._bond_preview_signature = mock.Mock(return_value=None)

        HoverInteractionService(clear_canvas).update_hover_highlight(QPointF(2.0, 3.0))

        clear_canvas._clear_hover_highlight.assert_called_once_with()
        clear_canvas._bond_hover_preview_service.add_free_bond_hover_preview.assert_not_called()

        preview_canvas = self._make_canvas(atoms={}, bonds=[], active_tool="bond")
        preview_canvas._bond_preview_signature = mock.Mock(return_value="wedge:1")

        HoverInteractionService(preview_canvas).update_hover_highlight(QPointF(8.0, 9.0))

        preview_canvas._clear_hover_highlight.assert_called_once_with()
        preview_canvas._bond_hover_preview_service.add_free_bond_hover_preview.assert_called_once_with(QPointF(8.0, 9.0))
        self.assertEqual(preview_canvas._hover_preview_style, "wedge:1:8.0:9.0")

    def test_update_hover_highlight_handles_atom_bond_and_invalid_hits(self) -> None:
        atoms = {1: Atom("C", 10.0, 20.0), 2: Atom("C", 30.0, 20.0)}
        bonds = [Bond(1, 2)]

        atom_canvas = self._make_canvas(atoms=atoms, bonds=bonds, active_tool="bond", active_bond_style="wedge")
        atom_canvas.preferred_structure_hit_at_scene_pos = mock.Mock(return_value=SimpleNamespace(kind="atom", id=1))
        atom_canvas._bond_preview_signature = mock.Mock(return_value="wedge:1")
        atom_canvas._bond_hover_endpoint = mock.Mock(return_value=QPointF(13.0, 14.0))

        HoverInteractionService(atom_canvas).update_hover_highlight(QPointF(11.0, 12.0))

        atom_canvas._clear_hover_highlight.assert_called_once_with()
        atom_canvas._add_atom_hover_indicator.assert_called_once_with(1)
        atom_canvas._add_bond_tool_hover_preview.assert_called_once_with(1, QPointF(11.0, 12.0))
        self.assertEqual(atom_canvas.hover_atom_id, 1)
        self.assertEqual(atom_canvas._hover_preview_style, "wedge:1:13.0:14.0")

        bond_canvas = self._make_canvas(atoms=atoms, bonds=bonds, active_tool="bond", active_bond_style="hash")
        bond_canvas.preferred_structure_hit_at_scene_pos = mock.Mock(return_value=SimpleNamespace(kind="bond", id=0))
        bond_canvas._bond_preview_signature = mock.Mock(return_value="hash:1")

        HoverInteractionService(bond_canvas).update_hover_highlight(QPointF(4.0, 5.0))

        bond_canvas._clear_hover_highlight.assert_called_once_with()
        bond_canvas._add_bond_hover_indicator.assert_called_once_with(0)
        bond_canvas._add_bond_style_hover_preview.assert_called_once_with(bonds[0])
        self.assertEqual(bond_canvas.hover_bond_id, 0)

        invalid_canvas = self._make_canvas(atoms=atoms, bonds=bonds, active_tool="bond")
        invalid_canvas.preferred_structure_hit_at_scene_pos = mock.Mock(return_value=SimpleNamespace(kind="other", id="x"))
        invalid_canvas._bond_preview_signature = mock.Mock(return_value="wedge:1")

        HoverInteractionService(invalid_canvas).update_hover_highlight(QPointF(9.0, 9.0))

        invalid_canvas._clear_hover_highlight.assert_called_once_with()
        invalid_canvas._add_atom_hover_indicator.assert_not_called()
        invalid_canvas._add_bond_hover_indicator.assert_not_called()

    def test_update_hover_highlight_skips_noop_paths(self) -> None:
        atom_canvas = self._make_canvas(atoms={1: Atom("C", 10.0, 20.0)}, active_tool="bond")
        atom_canvas.preferred_structure_hit_at_scene_pos = mock.Mock(return_value=SimpleNamespace(kind="atom", id=1))
        atom_canvas.hover_atom_id = 1
        atom_canvas._hover_preview_style = "wedge:1:13.0:14.0"
        atom_canvas._bond_preview_signature = mock.Mock(return_value="wedge:1")
        atom_canvas._bond_hover_endpoint = mock.Mock(return_value=QPointF(13.0, 14.0))

        HoverInteractionService(atom_canvas).update_hover_highlight(QPointF(11.0, 12.0))

        atom_canvas._clear_hover_highlight.assert_not_called()
        atom_canvas._add_atom_hover_indicator.assert_not_called()
        atom_canvas._add_bond_tool_hover_preview.assert_not_called()

        bond_canvas = self._make_canvas(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 1.0, 1.0)}, bonds=[Bond(1, 2)], active_tool="bond", active_bond_style="hash")
        bond_canvas.preferred_structure_hit_at_scene_pos = mock.Mock(return_value=SimpleNamespace(kind="bond", id=0))
        bond_canvas.hover_bond_id = 0
        bond_canvas._hover_preview_style = "hash"
        bond_canvas._bond_preview_signature = mock.Mock(return_value="hash:1")

        HoverInteractionService(bond_canvas).update_hover_highlight(QPointF(4.0, 5.0))

        bond_canvas._clear_hover_highlight.assert_not_called()
        bond_canvas._add_bond_hover_indicator.assert_not_called()
        bond_canvas._add_bond_style_hover_preview.assert_not_called()

    def test_atom_preview_returns_signature_without_key_for_missing_atom(self) -> None:
        canvas = self._make_canvas(atoms={1: Atom("C", 0.0, 0.0)}, active_tool="bond")
        canvas._bond_preview_signature = mock.Mock(return_value="wedge:1")

        signature, key = HoverInteractionService(canvas)._atom_preview(
            QPointF(4.0, 5.0),
            SimpleNamespace(kind="atom", id=99),
        )

        self.assertEqual(signature, "wedge:1")
        self.assertIsNone(key)

    def test_apply_plan_clears_for_missing_atom_or_bond_targets(self) -> None:
        canvas = self._make_canvas(atoms={1: Atom("C", 0.0, 0.0)}, active_tool="bond")
        service = HoverInteractionService(canvas)

        service._apply_plan(SimpleNamespace(action="atom_hit", hover_atom_id=None, preview_key="wedge"), QPointF())
        canvas._clear_hover_highlight.assert_called_once_with()
        canvas._add_atom_hover_indicator.assert_not_called()

        canvas._clear_hover_highlight.reset_mock()
        service._apply_plan(SimpleNamespace(action="bond_hit", hover_bond_id=None, preview_key="hash"), QPointF())
        canvas._clear_hover_highlight.assert_called_once_with()
        canvas._add_bond_hover_indicator.assert_not_called()

    def test_apply_plan_skips_missing_bond_objects_and_bond_lookup_handles_exceptions(self) -> None:
        none_bond_canvas = self._make_canvas(
            atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 1.0, 0.0)},
            bonds=[None],
            active_tool="bond",
        )
        service = HoverInteractionService(none_bond_canvas)

        service._apply_plan(SimpleNamespace(action="bond_hit", hover_bond_id=0, preview_key="hash"), QPointF())

        none_bond_canvas._clear_hover_highlight.assert_called_once_with()
        self.assertEqual(none_bond_canvas.hover_bond_id, 0)
        none_bond_canvas._add_bond_hover_indicator.assert_not_called()
        none_bond_canvas._add_bond_style_hover_preview.assert_not_called()

        bad_key_canvas = self._make_canvas()
        bad_key_canvas.model.bonds = {}
        self.assertIsNone(HoverInteractionService(bad_key_canvas)._bond_for_id(3))

        bad_type_canvas = self._make_canvas()
        bad_type_canvas.model.bonds = None
        self.assertIsNone(HoverInteractionService(bad_type_canvas)._bond_for_id(0))


if __name__ == "__main__":
    unittest.main()
