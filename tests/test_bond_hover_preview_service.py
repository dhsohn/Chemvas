import unittest
from types import SimpleNamespace
from unittest import mock

from core.model import Atom, Bond
from PyQt6.QtCore import QPointF
from ui.bond_hover_preview_service import BondHoverPreviewService
from ui.canvas_hover_state import HoverPreviewState
from ui.canvas_tool_settings_state import CanvasToolSettingsState


class _PreviewMocks:
    def __init__(self, *, endpoint: QPointF | None = None) -> None:
        self.add_hover_preview_items = mock.Mock()
        self.build_bond_preview_items = mock.Mock(return_value=["preview"])
        self.bond_hover_endpoint = mock.Mock(return_value=endpoint or QPointF(17.0, 18.0))


class BondHoverPreviewServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        build_patcher = mock.patch(
            "ui.bond_hover_preview_service.build_bond_preview_items_for",
            side_effect=lambda canvas, start, end, *atom_ids: canvas.preview_mocks.build_bond_preview_items(
                start,
                end,
                *atom_ids,
            ),
        )
        endpoint_patcher = mock.patch(
            "ui.bond_hover_preview_service.bond_hover_endpoint_for",
            side_effect=lambda canvas, start, pos, atom_id: canvas.preview_mocks.bond_hover_endpoint(
                start,
                pos,
                atom_id,
            ),
        )
        build_patcher.start()
        endpoint_patcher.start()
        self.addCleanup(build_patcher.stop)
        self.addCleanup(endpoint_patcher.stop)

    def _make_canvas(
        self,
        *,
        atoms: dict[int, Atom] | None = None,
        active_tool: str = "bond",
        active_bond_style: str = "wedge",
        preview_mocks: _PreviewMocks | None = None,
    ) -> SimpleNamespace:
        preview_mocks = preview_mocks or _PreviewMocks()
        return SimpleNamespace(
            model=SimpleNamespace(atoms=atoms or {}),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            hover_preview_state=HoverPreviewState(),
            tool_settings_state=CanvasToolSettingsState(active_bond_style=active_bond_style),
            preview_mocks=preview_mocks,
            services=SimpleNamespace(
                tools=SimpleNamespace(active=SimpleNamespace(name=active_tool)),
                hover_scene_service=SimpleNamespace(add_hover_preview_items=preview_mocks.add_hover_preview_items),
            ),
        )

    def _service_for(self, canvas: SimpleNamespace) -> BondHoverPreviewService:
        def active_tool_name() -> str | None:
            active_tool = getattr(canvas.services.tools, "active", None)
            name = getattr(active_tool, "name", None)
            return str(name) if name else None

        return BondHoverPreviewService(
            canvas,
            hover_scene_service=canvas.services.hover_scene_service,
            active_tool_name_provider=active_tool_name,
        )

    def test_add_bond_hover_preview_uses_injected_hover_scene_service(self) -> None:
        preview_mocks = _PreviewMocks()
        canvas = self._make_canvas(
            atoms={1: Atom("C", 10.0, 20.0), 2: Atom("C", 30.0, 20.0)},
            preview_mocks=preview_mocks,
        )
        service = self._service_for(canvas)

        service.add_bond_style_hover_preview(Bond(1, 2))
        service.add_bond_tool_hover_preview(1, QPointF(40.0, 41.0))
        service.add_free_bond_hover_preview(QPointF(5.0, 6.0))

        self.assertEqual(preview_mocks.add_hover_preview_items.call_count, 3)

    def test_add_bond_style_hover_preview_applies_for_supported_styles_only(self) -> None:
        preview_mocks = _PreviewMocks()
        canvas = self._make_canvas(
            atoms={1: Atom("C", 10.0, 20.0), 2: Atom("C", 30.0, 20.0)},
            preview_mocks=preview_mocks,
        )
        service = self._service_for(canvas)

        service.add_bond_style_hover_preview(Bond(1, 2))

        self.assertEqual(canvas.hover_preview_state.style, "wedge")
        preview_mocks.build_bond_preview_items.assert_called_once_with(
            QPointF(10.0, 20.0),
            QPointF(30.0, 20.0),
            1,
            2,
        )
        preview_mocks.add_hover_preview_items.assert_called_once_with(["preview"])

        for tool_name, style_name, atoms in [
            ("select", "wedge", {1: Atom("C", 10.0, 20.0), 2: Atom("C", 30.0, 20.0)}),
            ("bond", "single", {1: Atom("C", 10.0, 20.0), 2: Atom("C", 30.0, 20.0)}),
            ("bond", "hash", {1: Atom("C", 10.0, 20.0)}),
        ]:
            skip_mocks = _PreviewMocks()
            skip_canvas = self._make_canvas(
                atoms=atoms,
                active_tool=tool_name,
                active_bond_style=style_name,
                preview_mocks=skip_mocks,
            )
            self._service_for(skip_canvas).add_bond_style_hover_preview(Bond(1, 2))
            skip_mocks.build_bond_preview_items.assert_not_called()
            skip_mocks.add_hover_preview_items.assert_not_called()

    def test_add_bond_tool_hover_preview_uses_hover_endpoint_and_skips_invalid_inputs(self) -> None:
        preview_mocks = _PreviewMocks()
        canvas = self._make_canvas(atoms={1: Atom("C", 10.0, 20.0)}, preview_mocks=preview_mocks)
        service = self._service_for(canvas)

        service.add_bond_tool_hover_preview(1, QPointF(40.0, 41.0))

        preview_mocks.bond_hover_endpoint.assert_called_once_with(QPointF(10.0, 20.0), QPointF(40.0, 41.0), 1)
        preview_mocks.build_bond_preview_items.assert_called_once_with(
            QPointF(10.0, 20.0),
            QPointF(17.0, 18.0),
            1,
            None,
        )
        preview_mocks.add_hover_preview_items.assert_called_once_with(["preview"])

        missing_atom_mocks = _PreviewMocks()
        missing_atom_canvas = self._make_canvas(atoms={}, preview_mocks=missing_atom_mocks)
        self._service_for(missing_atom_canvas).add_bond_tool_hover_preview(1, QPointF(1.0, 2.0))
        missing_atom_mocks.build_bond_preview_items.assert_not_called()

        nonbond_mocks = _PreviewMocks()
        nonbond_canvas = self._make_canvas(
            atoms={1: Atom("C", 10.0, 20.0)},
            active_tool="select",
            preview_mocks=nonbond_mocks,
        )
        self._service_for(nonbond_canvas).add_bond_tool_hover_preview(1, QPointF(1.0, 2.0))
        nonbond_mocks.build_bond_preview_items.assert_not_called()

    def test_add_free_bond_hover_preview_uses_default_horizontal_segment(self) -> None:
        preview_mocks = _PreviewMocks()
        canvas = self._make_canvas(preview_mocks=preview_mocks)

        self._service_for(canvas).add_free_bond_hover_preview(QPointF(5.0, 6.0))

        preview_mocks.build_bond_preview_items.assert_called_once_with(QPointF(5.0, 6.0), QPointF(25.0, 6.0))
        preview_mocks.add_hover_preview_items.assert_called_once_with(["preview"])


if __name__ == "__main__":
    unittest.main()
