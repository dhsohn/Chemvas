from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class _NamedTool(Protocol):
    @property
    def name(self) -> str: ...


class _ActiveToolProvider(Protocol):
    @property
    def active(self) -> _NamedTool | None: ...


@dataclass(slots=True)
class ActiveToolReference:
    tool_controller: _ActiveToolProvider | None = None

    def active_tool(self) -> _NamedTool | None:
        if self.tool_controller is None:
            return None
        return self.tool_controller.active

    def active_tool_name(self) -> str | None:
        active_tool = self.active_tool()
        name = active_tool.name if active_tool is not None else None
        return str(name) if name else None


__all__ = ["ActiveToolReference"]
