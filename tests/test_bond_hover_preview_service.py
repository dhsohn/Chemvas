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
from ui.bond_hover_preview_service import BondHoverPreviewService


class BondHoverPreviewServiceTest(unittest.TestCase):
    def test_add_bond_style_hover_preview_applies_for_supported_styles_only(self) -> None:
        canvas = SimpleNamespace(
            tools=SimpleNamespace(active=SimpleNamespace(name="bond")),
            active_bond_style="wedge",
            model=SimpleNamespace(
                atoms={1: Atom("C", 10.0, 20.0), 2: Atom("C", 30.0, 20.0)},
            ),
            _hover_preview_style=None,
            _build_bond_preview_items=mock.Mock(return_value=["preview"]),
            _add_hover_preview_items=mock.Mock(),
        )
        service = BondHoverPreviewService(canvas)

        service.add_bond_style_hover_preview(Bond(1, 2))

        self.assertEqual(canvas._hover_preview_style, "wedge")
        canvas._build_bond_preview_items.assert_called_once_with(QPointF(10.0, 20.0), QPointF(30.0, 20.0), 1, 2)
        canvas._add_hover_preview_items.assert_called_once_with(["preview"])

        for tool_name, style_name, atoms in [
            ("select", "wedge", {1: Atom("C", 10.0, 20.0), 2: Atom("C", 30.0, 20.0)}),
            ("bond", "single", {1: Atom("C", 10.0, 20.0), 2: Atom("C", 30.0, 20.0)}),
            ("bond", "hash", {1: Atom("C", 10.0, 20.0)}),
        ]:
            skip_canvas = SimpleNamespace(
                tools=SimpleNamespace(active=SimpleNamespace(name=tool_name)),
                active_bond_style=style_name,
                model=SimpleNamespace(atoms=atoms),
                _hover_preview_style=None,
                _build_bond_preview_items=mock.Mock(),
                _add_hover_preview_items=mock.Mock(),
            )
            BondHoverPreviewService(skip_canvas).add_bond_style_hover_preview(Bond(1, 2))
            skip_canvas._build_bond_preview_items.assert_not_called()
            skip_canvas._add_hover_preview_items.assert_not_called()

    def test_add_bond_tool_hover_preview_uses_hover_endpoint_and_skips_invalid_inputs(self) -> None:
        canvas = SimpleNamespace(
            tools=SimpleNamespace(active=SimpleNamespace(name="bond")),
            model=SimpleNamespace(atoms={1: Atom("C", 10.0, 20.0)}),
            _bond_hover_endpoint=mock.Mock(return_value=QPointF(17.0, 18.0)),
            _build_bond_preview_items=mock.Mock(return_value=["preview"]),
            _add_hover_preview_items=mock.Mock(),
        )
        service = BondHoverPreviewService(canvas)

        service.add_bond_tool_hover_preview(1, QPointF(40.0, 41.0))

        canvas._bond_hover_endpoint.assert_called_once_with(QPointF(10.0, 20.0), QPointF(40.0, 41.0), 1)
        canvas._build_bond_preview_items.assert_called_once_with(QPointF(10.0, 20.0), QPointF(17.0, 18.0), 1, None)
        canvas._add_hover_preview_items.assert_called_once_with(["preview"])

        missing_atom_canvas = SimpleNamespace(
            tools=SimpleNamespace(active=SimpleNamespace(name="bond")),
            model=SimpleNamespace(atoms={}),
            _bond_hover_endpoint=mock.Mock(),
            _build_bond_preview_items=mock.Mock(),
            _add_hover_preview_items=mock.Mock(),
        )
        BondHoverPreviewService(missing_atom_canvas).add_bond_tool_hover_preview(1, QPointF(1.0, 2.0))
        missing_atom_canvas._build_bond_preview_items.assert_not_called()

        nonbond_canvas = SimpleNamespace(
            tools=SimpleNamespace(active=SimpleNamespace(name="select")),
            model=SimpleNamespace(atoms={1: Atom("C", 10.0, 20.0)}),
            _bond_hover_endpoint=mock.Mock(),
            _build_bond_preview_items=mock.Mock(),
            _add_hover_preview_items=mock.Mock(),
        )
        BondHoverPreviewService(nonbond_canvas).add_bond_tool_hover_preview(1, QPointF(1.0, 2.0))
        nonbond_canvas._build_bond_preview_items.assert_not_called()

    def test_add_free_bond_hover_preview_uses_default_horizontal_segment(self) -> None:
        canvas = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            _build_bond_preview_items=mock.Mock(return_value=["preview"]),
            _add_hover_preview_items=mock.Mock(),
        )

        BondHoverPreviewService(canvas).add_free_bond_hover_preview(QPointF(5.0, 6.0))

        canvas._build_bond_preview_items.assert_called_once_with(QPointF(5.0, 6.0), QPointF(25.0, 6.0))
        canvas._add_hover_preview_items.assert_called_once_with(["preview"])


if __name__ == "__main__":
    unittest.main()
