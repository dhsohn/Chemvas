from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.main_window_services import MainWindowServices


def services_for_window(window) -> MainWindowServices:
    return window._services


__all__ = ["services_for_window"]
