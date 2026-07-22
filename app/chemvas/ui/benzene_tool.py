from __future__ import annotations

from chemvas.core.tool_overlay_logic import activate_tool_no_drag
from chemvas.ui.tool_base import Tool


class BenzeneTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("benzene", canvas, context=context)

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)


__all__ = ["BenzeneTool"]
