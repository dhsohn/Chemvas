from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.main_window_tab_references import MainWindowTabReferences


def tab_references_for_window(window) -> MainWindowTabReferences:
    return window.tab_references


__all__ = ["tab_references_for_window"]
