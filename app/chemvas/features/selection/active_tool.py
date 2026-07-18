from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ActiveToolReference:
    tool_controller: Any | None = None

    def active_tool(self) -> Any:
        return getattr(self.tool_controller, "active", None)

    def active_tool_name(self) -> str | None:
        name = getattr(self.active_tool(), "name", None)
        return str(name) if name else None


__all__ = ["ActiveToolReference"]
