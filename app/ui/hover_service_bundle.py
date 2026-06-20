from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ui.bond_hover_preview_service import BondHoverPreviewService
from ui.canvas_hover_refresh import refresh_hover_from_cursor_for
from ui.hover_interaction_service import HoverInteractionService
from ui.hover_scene_service import HoverSceneService
from ui.mark_hover_preview_service import MarkHoverPreviewService

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView
    from ui.selection_controller import SelectionController


@dataclass(slots=True)
class HoverServiceBundle:
    hover_interaction_service: HoverInteractionService
    hover_scene_service: HoverSceneService
    mark_hover_preview_service: MarkHoverPreviewService
    bond_hover_preview_service: BondHoverPreviewService
    hover_refresh: Callable[..., None]


def build_hover_services(
    canvas: CanvasView | Any,
    *,
    selection_controller: SelectionController | Any,
    hit_testing_service: Any,
    active_tool_provider: Callable[[], Any],
    active_tool_name_provider: Callable[[], str | None],
) -> HoverServiceBundle:
    hover_interaction_service = HoverInteractionService(
        canvas,
        selection_controller=selection_controller,
        active_tool_provider=active_tool_provider,
    )
    hover_scene_service = HoverSceneService(canvas)
    mark_hover_preview_service = MarkHoverPreviewService(
        canvas,
        hit_testing_service=hit_testing_service,
        hover_scene_service=hover_scene_service,
    )
    bond_hover_preview_service = BondHoverPreviewService(
        canvas,
        hover_scene_service=hover_scene_service,
        active_tool_name_provider=active_tool_name_provider,
    )

    def insert_controller_method(name: str):
        services = getattr(canvas, "services", None)
        insert_controller = getattr(services, "insert_controller", None)
        method = getattr(insert_controller, name, None)
        return method if callable(method) else None

    def hover_refresh(*, render_insert_preview: bool = False) -> None:
        refresh_hover_from_cursor_for(
            canvas,
            update_hover_highlight=hover_interaction_service.update_hover_highlight,
            clear_hover_highlight=hover_scene_service.clear_hover_highlight,
            render_template_preview=(
                insert_controller_method("render_template_preview") if render_insert_preview else None
            ),
            render_smiles_preview=insert_controller_method("render_smiles_preview") if render_insert_preview else None,
        )

    return HoverServiceBundle(
        hover_interaction_service=hover_interaction_service,
        hover_scene_service=hover_scene_service,
        mark_hover_preview_service=mark_hover_preview_service,
        bond_hover_preview_service=bond_hover_preview_service,
        hover_refresh=hover_refresh,
    )


__all__ = ["HoverServiceBundle", "build_hover_services"]
