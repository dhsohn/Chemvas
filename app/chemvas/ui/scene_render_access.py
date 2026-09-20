from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from chemvas.ui.scene_render_context import SceneRenderContext


def scene_render_context_for(canvas: Any) -> SceneRenderContext:
    return cast("SceneRenderContext", canvas.render_context)
