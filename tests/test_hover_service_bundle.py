from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import ui.hover_service_bundle as hover_service_bundle
from ui.hover_service_bundle import HoverServiceBundle, build_hover_services


def _stub_service_class(name: str):
    class StubService:
        def __init__(self, *args, **kwargs) -> None:
            self.service_name = name
            self.args = args
            self.kwargs = kwargs

        def update_hover_highlight(self, pos) -> None:
            self.last_hover_pos = pos

        def clear_hover_highlight(self) -> None:
            self.cleared = True

    return StubService


def test_build_hover_services_wires_explicit_collaborators(monkeypatch) -> None:
    for class_name in (
        "BondHoverPreviewService",
        "HoverInteractionService",
        "HoverSceneService",
        "MarkHoverPreviewService",
    ):
        monkeypatch.setattr(hover_service_bundle, class_name, _stub_service_class(class_name))

    canvas = SimpleNamespace()
    selection_controller = object()
    hit_testing_service = object()
    active_tool_provider = mock.Mock(return_value=None)
    active_tool_name_provider = mock.Mock(return_value=None)

    services = build_hover_services(
        canvas,
        selection_controller=selection_controller,
        hit_testing_service=hit_testing_service,
        active_tool_provider=active_tool_provider,
        active_tool_name_provider=active_tool_name_provider,
    )

    assert isinstance(services, HoverServiceBundle)
    assert services.hover_interaction_service.kwargs == {
        "selection_controller": selection_controller,
        "active_tool_provider": active_tool_provider,
    }
    assert services.mark_hover_preview_service.kwargs == {
        "hit_testing_service": hit_testing_service,
        "hover_scene_service": services.hover_scene_service,
    }
    assert services.bond_hover_preview_service.kwargs == {
        "hover_scene_service": services.hover_scene_service,
        "active_tool_name_provider": active_tool_name_provider,
    }
    assert callable(services.hover_refresh)


def test_hover_refresh_uses_injected_hover_ports(monkeypatch) -> None:
    refresh_hover_from_cursor_for = mock.Mock()
    monkeypatch.setattr(
        hover_service_bundle,
        "refresh_hover_from_cursor_for",
        refresh_hover_from_cursor_for,
    )
    canvas = SimpleNamespace()
    services = build_hover_services(
        canvas,
        selection_controller=object(),
        hit_testing_service=object(),
        active_tool_provider=lambda: None,
        active_tool_name_provider=lambda: None,
    )

    services.hover_refresh()

    refresh_hover_from_cursor_for.assert_called_once_with(
        canvas,
        update_hover_highlight=services.hover_interaction_service.update_hover_highlight,
        clear_hover_highlight=services.hover_scene_service.clear_hover_highlight,
    )
