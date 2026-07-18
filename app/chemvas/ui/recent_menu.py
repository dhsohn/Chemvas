"""The "Open Recent" submenu for the File dropdown.

The menu repopulates itself from the recent-documents store every time it is
shown (via ``aboutToShow``), so it reflects files opened/saved since the window
was built and prunes ones that have since been deleted.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QWidget

from chemvas.ui.recent_documents_logic import recent_menu_entries
from chemvas.ui.recent_documents_store import clear_recent, load_recent


def build_recent_menu(
    parent: QWidget,
    *,
    open_path: Callable[[str], None],
    load_recent_paths: Callable[[], list[str]] = load_recent,
    clear: Callable[[], None] = clear_recent,
) -> QMenu:
    menu = QMenu("Open Recent", parent)

    def repopulate() -> None:
        menu.clear()
        entries = recent_menu_entries(load_recent_paths())
        if not entries:
            empty = QAction("No Recent Files", menu)
            empty.setEnabled(False)
            menu.addAction(empty)
            return
        for label, path in entries:
            action = QAction(label, menu)
            action.setToolTip(path)
            action.setStatusTip(path)
            action.triggered.connect(
                lambda _checked=False, target=path: open_path(target)
            )
            menu.addAction(action)
        menu.addSeparator()
        clear_action = QAction("Clear Recent Files", menu)
        clear_action.triggered.connect(lambda _checked=False: clear())
        menu.addAction(clear_action)

    menu.aboutToShow.connect(repopulate)
    return menu


__all__ = ["build_recent_menu"]
