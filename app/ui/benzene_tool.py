from __future__ import annotations

from core.tool_overlay_logic import activate_tool_no_drag

from ui.benzene_preview_access import clear_benzene_preview_for
from ui.tool_base import Tool


class BenzeneTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("benzene", canvas, context=context)

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)
        clear_benzene_preview_for(self.canvas)

    def deactivate(self) -> None:
        clear_benzene_preview_for(self.canvas)


__all__ = ["BenzeneTool"]
