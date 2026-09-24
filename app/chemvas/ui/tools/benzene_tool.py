from __future__ import annotations

from typing import override

from chemvas.ui.tools.tool_base import Tool
from chemvas.ui.tools.tool_overlay_logic import activate_tool_no_drag


class BenzeneTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("benzene", canvas, context=context)

    @override
    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)


__all__ = ["BenzeneTool"]
