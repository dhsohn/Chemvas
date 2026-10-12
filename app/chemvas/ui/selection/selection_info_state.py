from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(slots=True, kw_only=True)
class SelectionInfoState:
    # The active window's selection observer: status label, text options and
    # action availability refresh from the canvas when it fires.
    callback: Callable[[], None] | None = None


__all__ = ["SelectionInfoState"]
