from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import QProcess, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QKeySequence
from PyQt6.QtWidgets import QApplication, QMenu, QMenuBar

from chemvas.branding import APP_NAME
from chemvas.ui.calculation_step_dialog import edit_calculation_plan_for_window
from chemvas.ui.image_actions import (
    image_properties_for_window,
    insert_image_for_window,
)
from chemvas.ui.main_window_about_dialog import GITHUB_URL, show_about_dialog
from chemvas.ui.main_window_document_dialogs import prompt_sheet_setup
from chemvas.ui.main_window_ports import (
    align_selection_for_window,
    copy_selection_for_window,
    cut_selection_for_window,
    distribute_selection_for_window,
    fit_canvas_to_view_for_window,
    flip_selection_for_window,
    group_selection_for_window,
    paste_selection_for_window,
    redo_for_window,
    reset_zoom_for_window,
    select_all_for_window,
    services_for_window,
    set_grid_snap_for_window,
    set_sheet_setup_for_window,
    sheet_orientation_for_window,
    sheet_size_for_window,
    undo_for_window,
    ungroup_selection_for_window,
    zoom_in_for_window,
    zoom_out_for_window,
)
from chemvas.ui.recent_menu import build_recent_menu
from chemvas.ui.scheme_layout_dialog import arrange_scheme_for_window

if TYPE_CHECKING:
    from chemvas.ui.main_window_panel_toolbar import MainWindowPanelToolbarCallbacks


@dataclass(frozen=True)
class MainWindowMenuBarAssembly:
    menu_bar: QMenuBar
    undo_action: QAction
    redo_action: QAction
    grid_snap_action: QAction


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


ALIGN_MENU_SPECS: tuple[tuple[str, str], ...] = (
    ("Left", "left"),
    ("Center", "center"),
    ("Right", "right"),
    ("Top", "top"),
    ("Middle", "middle"),
    ("Bottom", "bottom"),
)
DISTRIBUTE_MENU_SPECS: tuple[tuple[str, str], ...] = (
    ("Horizontally", "horizontal"),
    ("Vertically", "vertical"),
)


def _add_action(
    menu,
    window,
    text: str,
    *,
    status_tip: str,
    triggered,
    shortcut: QKeySequence | QKeySequence.StandardKey | None = None,
    checkable: bool = False,
) -> QAction:
    action = QAction(text, window)
    action.setStatusTip(status_tip)
    if shortcut is not None:
        action.setShortcut(shortcut)
    if checkable:
        action.setCheckable(True)
        action.triggered.connect(lambda checked=False: triggered(checked))
    else:
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
        "Insert Image...",
        status_tip="Embed an original PNG or JPEG image in the current drawing",
        triggered=lambda: insert_image_for_window(window),
    )
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

    file_menu.addSeparator()
    close_action = _add_action(
        file_menu,
        window,
        "Close Window",
        status_tip="Close this window, asking to save any unsaved drawings",
        triggered=window.close,
    )
    close_action.setShortcuts(QKeySequence.StandardKey.Close)


def _build_edit_menu(
    menu_bar: QMenuBar, window, callbacks: MainWindowPanelToolbarCallbacks
) -> tuple[QAction, QAction]:
    def text_action_tip(description: str, key: QKeySequence.StandardKey) -> str:
        shortcut = QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText)
        return f"{description} ({shortcut})"

    edit_menu = _add_menu(menu_bar, "Edit")
    edit_menu.aboutToShow.connect(
        lambda: services_for_window(
            window
        ).action_availability_service.update_action_availability(window)
    )
    undo_action = _add_action(
        edit_menu,
        window,
        "Undo",
        status_tip="Undo the last edit",
        shortcut=QKeySequence.StandardKey.Undo,
        triggered=lambda: undo_for_window(window),
    )
    redo_action = _add_action(
        edit_menu,
        window,
        "Redo",
        status_tip="Redo the last undone edit",
        shortcut=QKeySequence.StandardKey.Redo,
        triggered=lambda: redo_for_window(window),
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
        status_tip=text_action_tip(
            "Cut selected text or objects", QKeySequence.StandardKey.Cut
        ),
        triggered=lambda: cut_selection_for_window(window),
    )
    _add_action(
        edit_menu,
        window,
        "Copy",
        status_tip=text_action_tip(
            "Copy selected text or objects", QKeySequence.StandardKey.Copy
        ),
        triggered=lambda: copy_selection_for_window(window),
    )
    _add_action(
        edit_menu,
        window,
        "Paste",
        status_tip=text_action_tip(
            "Paste into the text editor or canvas", QKeySequence.StandardKey.Paste
        ),
        triggered=lambda: paste_selection_for_window(window),
    )
    edit_menu.addSeparator()
    _add_action(
        edit_menu,
        window,
        "Select All",
        status_tip=text_action_tip(
            "Select all text or canvas objects", QKeySequence.StandardKey.SelectAll
        ),
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
    _add_action(
        edit_menu,
        window,
        "Image Properties...",
        status_tip="Set the selected image's position, size, aspect ratio and opacity",
        triggered=lambda: image_properties_for_window(window),
    )
    _add_action(
        edit_menu,
        window,
        "Arrange Scheme...",
        status_tip="Arrange existing structure/caption groups and explicit pathway arrows",
        triggered=lambda: arrange_scheme_for_window(window),
    )
    edit_menu.addSeparator()
    _add_action(
        edit_menu,
        window,
        "Flip Horizontal",
        status_tip="Flip the current selection horizontally (Ctrl+Shift+H)",
        triggered=lambda: flip_selection_for_window(window, horizontal=True),
    )
    _add_action(
        edit_menu,
        window,
        "Flip Vertical",
        status_tip="Flip the current selection vertically (Ctrl+Shift+V)",
        triggered=lambda: flip_selection_for_window(window, horizontal=False),
    )
    _add_action(
        edit_menu,
        window,
        "Rotate...",
        status_tip="Enter an angle to rotate the current selection",
        triggered=lambda: callbacks.show_rotate_options(window),
    )
    align_menu = edit_menu.addMenu("Align")
    for text, mode in ALIGN_MENU_SPECS:
        _add_action(
            align_menu,
            window,
            text,
            status_tip=f"Align the selected structures and objects by their {text.lower()}",
            triggered=lambda mode=mode: align_selection_for_window(window, mode),
        )
    distribute_menu = edit_menu.addMenu("Distribute")
    for text, axis in DISTRIBUTE_MENU_SPECS:
        _add_action(
            distribute_menu,
            window,
            text,
            status_tip=f"Spread the selected structures and objects {text.lower()} with equal gaps",
            triggered=lambda axis=axis: distribute_selection_for_window(window, axis),
        )
    return undo_action, redo_action


def _build_view_menu(
    menu_bar: QMenuBar, window, callbacks: MainWindowPanelToolbarCallbacks
) -> QAction:
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
    grid_snap_action = _add_action(
        view_menu,
        window,
        "Snap to Grid",
        status_tip=(
            "Show a grid on the sheet and snap drawn arrows, lines and their "
            "endpoint handles to it"
        ),
        triggered=lambda checked: set_grid_snap_for_window(window, checked),
        checkable=True,
    )
    view_menu.addSeparator()
    _add_action(
        view_menu,
        window,
        "Molecule Info",
        status_tip="Open the selected molecule in a separate molecule info window",
        triggered=lambda: callbacks.open_preview_window(window),
    )
    return grid_snap_action


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


def _open_project_repository() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        wslview = shutil.which("wslview")
        if wslview is not None:
            started, _pid = QProcess.startDetached(wslview, [GITHUB_URL])
            if started:
                return True
    return QDesktopServices.openUrl(QUrl(GITHUB_URL))


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
    github_action.triggered.connect(lambda _checked=False: _open_project_repository())
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
    grid_snap_action = _build_view_menu(menu_bar, window, callbacks)
    _build_calculation_menu(menu_bar, window)
    _build_help_menu(menu_bar, window)
    return MainWindowMenuBarAssembly(
        menu_bar=menu_bar,
        undo_action=undo_action,
        redo_action=redo_action,
        grid_snap_action=grid_snap_action,
    )


__all__ = [
    "MainWindowMenuBarAssembly",
    "build_menu_bar",
    "run_sheet_setup_dialog",
]
