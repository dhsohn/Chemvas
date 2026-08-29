from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QKeySequence
from PyQt6.QtWidgets import QApplication, QMenu, QMenuBar

from chemvas.branding import APP_NAME
from chemvas.ui.calculation_step_dialog import edit_calculation_plan_for_window
from chemvas.ui.main_window_about_dialog import GITHUB_URL, show_about_dialog
from chemvas.ui.main_window_document_dialogs import prompt_sheet_setup
from chemvas.ui.main_window_ports import (
    copy_selection_for_window,
    cut_selection_for_window,
    fit_canvas_to_view_for_window,
    group_selection_for_window,
    history_service_for_window,
    paste_selection_for_window,
    reset_zoom_for_window,
    scene_transform_controller_for_window,
    select_all_for_window,
    set_sheet_setup_for_window,
    sheet_orientation_for_window,
    sheet_size_for_window,
    ungroup_selection_for_window,
    zoom_in_for_window,
    zoom_out_for_window,
)
from chemvas.ui.recent_menu import build_recent_menu

if TYPE_CHECKING:
    from chemvas.ui.main_window_panel_toolbar import MainWindowPanelToolbarCallbacks


@dataclass(frozen=True)
class MainWindowMenuBarAssembly:
    menu_bar: QMenuBar
    undo_action: QAction
    redo_action: QAction


def _add_menu(menu_bar: QMenuBar, title: str) -> QMenu:
    menu = menu_bar.addMenu(title)
    if menu is None:
        raise RuntimeError(f"Could not create the {title} menu.")
    return menu


def run_sheet_setup_dialog(window) -> None:
    selection = prompt_sheet_setup(
        window,
        current_size=sheet_size_for_window(window),
        current_orientation=sheet_orientation_for_window(window),
    )
    if selection is not None:
        set_sheet_setup_for_window(window, selection.size, selection.orientation)


def _add_action(
    menu,
    window,
    text: str,
    *,
    status_tip: str,
    triggered,
    shortcut: QKeySequence | QKeySequence.StandardKey | None = None,
) -> QAction:
    action = QAction(text, window)
    action.setStatusTip(status_tip)
    if shortcut is not None:
        action.setShortcut(shortcut)
    action.triggered.connect(lambda _checked=False: triggered())
    menu.addAction(action)
    return action


def _build_file_menu(
    menu_bar: QMenuBar, window, callbacks: MainWindowPanelToolbarCallbacks
) -> None:
    file_menu = _add_menu(menu_bar, "File")
    _add_action(
        file_menu,
        window,
        "New Canvas",
        status_tip="Create a new canvas",
        shortcut=QKeySequence.StandardKey.New,
        triggered=lambda: callbacks.new_canvas(window),
    )
    file_menu.addSeparator()
    _add_action(
        file_menu,
        window,
        "Open...",
        status_tip="Open a drawing",
        shortcut=QKeySequence.StandardKey.Open,
        triggered=lambda: callbacks.load_canvas(window),
    )
    file_menu.addMenu(
        build_recent_menu(
            window,
            open_path=lambda path: callbacks.open_recent_path(window, path),
        )
    )
    file_menu.addSeparator()
    _add_action(
        file_menu,
        window,
        "Save",
        status_tip="Save the current drawing",
        shortcut=QKeySequence.StandardKey.Save,
        triggered=lambda: callbacks.save_canvas(window),
    )
    _add_action(
        file_menu,
        window,
        "Save As...",
        status_tip="Save the current drawing to a new file",
        shortcut=QKeySequence.StandardKey.SaveAs,
        triggered=lambda: callbacks.save_canvas_as(window),
    )
    file_menu.addSeparator()
    _add_action(
        file_menu,
        window,
        "Canvas Size...",
        status_tip="Change the canvas sheet size and orientation",
        triggered=lambda: run_sheet_setup_dialog(window),
    )
    file_menu.addSeparator()
    _add_action(
        file_menu,
        window,
        "Export Figure...",
        status_tip="Export the drawing as SVG, PDF, or high-resolution PNG/TIFF",
        triggered=lambda: callbacks.export_figure(window),
    )
    _add_action(
        file_menu,
        window,
        "Export MOL...",
        status_tip="Export the selected structure as an MDL Molfile (.mol)",
        triggered=lambda: callbacks.export_mol(window),
    )


def _build_edit_menu(
    menu_bar: QMenuBar, window, callbacks: MainWindowPanelToolbarCallbacks
) -> tuple[QAction, QAction]:
    edit_menu = _add_menu(menu_bar, "Edit")
    undo_action = _add_action(
        edit_menu,
        window,
        "Undo",
        status_tip="Undo the last edit",
        shortcut=QKeySequence.StandardKey.Undo,
        triggered=lambda: history_service_for_window(window).undo(),
    )
    redo_action = _add_action(
        edit_menu,
        window,
        "Redo",
        status_tip="Redo the last undone edit",
        shortcut=QKeySequence.StandardKey.Redo,
        triggered=lambda: history_service_for_window(window).redo(),
    )
    edit_menu.addSeparator()
    # Cut/Copy/Paste/Select All/Group keys are handled by the canvas key-press
    # path (and by native text fields while they have focus). Registering the
    # same sequences on these window-level actions would intercept them before
    # the focused widget sees them, so the menu items stay shortcut-free and
    # name the key in their status tip instead.
    _add_action(
        edit_menu,
        window,
        "Cut",
        status_tip="Cut the selection to the clipboard (Ctrl+X)",
        triggered=lambda: cut_selection_for_window(window),
    )
    _add_action(
        edit_menu,
        window,
        "Copy",
        status_tip="Copy the selection to the clipboard (Ctrl+C)",
        triggered=lambda: copy_selection_for_window(window),
    )
    _add_action(
        edit_menu,
        window,
        "Paste",
        status_tip="Paste the copied selection (Ctrl+V)",
        triggered=lambda: paste_selection_for_window(window),
    )
    edit_menu.addSeparator()
    _add_action(
        edit_menu,
        window,
        "Select All",
        status_tip="Select everything on the canvas (Ctrl+A)",
        triggered=lambda: select_all_for_window(window),
    )
    edit_menu.addSeparator()
    _add_action(
        edit_menu,
        window,
        "Group",
        status_tip="Group the selected items (Ctrl+G)",
        triggered=lambda: group_selection_for_window(window),
    )
    _add_action(
        edit_menu,
        window,
        "Ungroup",
        status_tip="Ungroup the selected group (Ctrl+Shift+G)",
        triggered=lambda: ungroup_selection_for_window(window),
    )
    edit_menu.addSeparator()
    _add_action(
        edit_menu,
        window,
        "Flip Horizontal",
        status_tip="Flip the current selection horizontally (Ctrl+Shift+H)",
        triggered=lambda: scene_transform_controller_for_window(
            window
        ).flip_selected_items(horizontal=True),
    )
    _add_action(
        edit_menu,
        window,
        "Flip Vertical",
        status_tip="Flip the current selection vertically (Ctrl+Shift+V)",
        triggered=lambda: scene_transform_controller_for_window(
            window
        ).flip_selected_items(horizontal=False),
    )
    _add_action(
        edit_menu,
        window,
        "Rotate...",
        status_tip="Enter an angle to rotate the current selection",
        triggered=lambda: callbacks.show_rotate_options(window),
    )
    return undo_action, redo_action


def _build_view_menu(
    menu_bar: QMenuBar, window, callbacks: MainWindowPanelToolbarCallbacks
) -> None:
    view_menu = _add_menu(menu_bar, "View")
    _add_action(
        view_menu,
        window,
        "Actual Size",
        status_tip="Reset the zoom to 100%",
        shortcut=QKeySequence("F5"),
        triggered=lambda: reset_zoom_for_window(window),
    )
    _add_action(
        view_menu,
        window,
        "Fit to Window",
        status_tip="Fit the canvas sheet to the window",
        shortcut=QKeySequence("F6"),
        triggered=lambda: fit_canvas_to_view_for_window(window),
    )
    _add_action(
        view_menu,
        window,
        "Zoom In",
        status_tip="Magnify the canvas",
        shortcut=QKeySequence("F7"),
        triggered=lambda: zoom_in_for_window(window),
    )
    _add_action(
        view_menu,
        window,
        "Zoom Out",
        status_tip="Reduce the canvas",
        shortcut=QKeySequence("F8"),
        triggered=lambda: zoom_out_for_window(window),
    )
    view_menu.addSeparator()
    _add_action(
        view_menu,
        window,
        "Molecule Info",
        status_tip="Open the selected molecule in a separate molecule info window",
        triggered=lambda: callbacks.open_preview_window(window),
    )


def _build_calculation_menu(menu_bar: QMenuBar, window) -> None:
    calculation_menu = _add_menu(menu_bar, "Calculation")
    _add_action(
        calculation_menu,
        window,
        "Edit States and Steps...",
        status_tip=(
            "Assign reactant, product, catalyst, and spectator roles for DFT export"
        ),
        triggered=lambda: edit_calculation_plan_for_window(window),
    )


def _build_help_menu(menu_bar: QMenuBar, window) -> None:
    help_menu = _add_menu(menu_bar, "Help")

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


def build_menu_bar(
    window, *, callbacks: MainWindowPanelToolbarCallbacks
) -> MainWindowMenuBarAssembly:
    """Attach the File/Edit/View/Help menus to ``window``'s menu bar.

    The About/About-Qt entries carry the standard menu roles, so on macOS Qt
    relocates them into the application menu (the native home for "About"),
    while Windows/Linux show them under a top-level Help menu.
    """
    menu_bar = window.menuBar()
    _build_file_menu(menu_bar, window, callbacks)
    undo_action, redo_action = _build_edit_menu(menu_bar, window, callbacks)
    _build_view_menu(menu_bar, window, callbacks)
    _build_calculation_menu(menu_bar, window)
    _build_help_menu(menu_bar, window)
    return MainWindowMenuBarAssembly(
        menu_bar=menu_bar,
        undo_action=undo_action,
        redo_action=redo_action,
    )


__all__ = [
    "MainWindowMenuBarAssembly",
    "build_menu_bar",
    "run_sheet_setup_dialog",
]
