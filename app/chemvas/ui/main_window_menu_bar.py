from __future__ import annotations

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QAction, QDesktopServices
from PyQt6.QtWidgets import QApplication, QMenuBar

from chemvas.branding import APP_NAME
from chemvas.ui.main_window_about_dialog import GITHUB_URL, show_about_dialog


def build_menu_bar(window) -> QMenuBar:
    """Attach a minimal Help menu to ``window``'s menu bar.

    The About/About-Qt entries carry the standard menu roles, so on macOS Qt
    relocates them into the application menu (the native home for "About"),
    while Windows/Linux show them under a top-level Help menu.
    """
    menu_bar = window.menuBar()
    help_menu = menu_bar.addMenu("Help")

    about_action = QAction(f"About {APP_NAME}", window)
    about_action.setMenuRole(QAction.MenuRole.AboutRole)
    about_action.setStatusTip(f"Show version and license information for {APP_NAME}")
    about_action.triggered.connect(lambda _checked=False: show_about_dialog(window))
    help_menu.addAction(about_action)

    about_qt_action = QAction("About Qt", window)
    about_qt_action.setMenuRole(QAction.MenuRole.AboutQtRole)
    about_qt_action.triggered.connect(lambda _checked=False: QApplication.aboutQt())
    help_menu.addAction(about_qt_action)

    help_menu.addSeparator()

    github_action = QAction(f"{APP_NAME} on GitHub", window)
    github_action.setStatusTip("Open the project repository in your browser")
    github_action.triggered.connect(
        lambda _checked=False: QDesktopServices.openUrl(QUrl(GITHUB_URL))
    )
    help_menu.addAction(github_action)

    return menu_bar


__all__ = ["build_menu_bar"]
