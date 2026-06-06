from __future__ import annotations

from types import SimpleNamespace

from ui.benzene_preview_ports import benzene_preview_service_for_access
from ui.canvas_scene_reset_ports import scene_reset_service_for_access
from ui.hover_ports import (
    bond_hover_preview_service_for_access,
    hover_interaction_service_for_access,
    hover_scene_service_for_access,
    mark_hover_preview_service_for_access,
)
from ui.insert_session_ports import insert_controller_for_access
from ui.note_item_ports import note_controller_for_access
from ui.selection_highlight_ports import selection_highlight_styler_for_access


def test_simple_canvas_ports_return_attached_services() -> None:
    services = SimpleNamespace(
        benzene_preview_service=object(),
        bond_hover_preview_service=object(),
        canvas_scene_reset_service=object(),
        hover_interaction_service=object(),
        hover_scene_service=object(),
        insert_controller=object(),
        mark_hover_preview_service=object(),
        note_controller=object(),
        selection_highlight_styler=object(),
    )
    canvas = SimpleNamespace(services=services)

    assert benzene_preview_service_for_access(canvas) is services.benzene_preview_service
    assert bond_hover_preview_service_for_access(canvas) is services.bond_hover_preview_service
    assert scene_reset_service_for_access(canvas) is services.canvas_scene_reset_service
    assert hover_interaction_service_for_access(canvas) is services.hover_interaction_service
    assert hover_scene_service_for_access(canvas) is services.hover_scene_service
    assert insert_controller_for_access(canvas) is services.insert_controller
    assert mark_hover_preview_service_for_access(canvas) is services.mark_hover_preview_service
    assert note_controller_for_access(canvas) is services.note_controller
    assert selection_highlight_styler_for_access(canvas) is services.selection_highlight_styler
