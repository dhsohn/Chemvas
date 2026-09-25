from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsTextItem, QLineEdit, QStatusBar

    from chemvas.ui.canvas.canvas_color_mutation_service import (
        CanvasColorMutationService,
    )
    from chemvas.ui.canvas.canvas_document_session_service import (
        CanvasDocumentSessionService,
    )
    from chemvas.ui.canvas.canvas_geometry_controller import CanvasGeometryController
    from chemvas.ui.canvas.canvas_style_controller import CanvasStyleController
    from chemvas.ui.canvas.canvas_tool_mode_controller import CanvasToolModeController
    from chemvas.ui.canvas.canvas_view import CanvasView
    from chemvas.ui.insert.insert_controller import InsertController
    from chemvas.ui.scene.scene_clipboard_controller import SceneClipboardController
    from chemvas.ui.scene.scene_delete_controller import SceneDeleteController
    from chemvas.ui.scene.scene_transform_controller import SceneTransformController
    from chemvas.ui.window.main_window_like import MainWindowLike


def status_bar_for(window: MainWindowLike) -> QStatusBar:
    """``QMainWindow.statusBar()`` creates the bar on first use; the stub says ``None``."""
    status_bar = window.statusBar()
    if status_bar is None:
        raise RuntimeError("Main window has no status bar.")
    return status_bar


def set_grid_snap_for_window(window: MainWindowLike, enabled: bool) -> None:
    # Imported here, not at module scope: every window service imports
    # this module, and these two pull in Qt widget code.

    canvas = active_canvas_or_none_for_window(window)
    if canvas is None:
        return
    canvas.runtime_state.tool_settings_state.grid_snap_enabled = bool(enabled)
    viewport = canvas.viewport()
    if viewport is not None:
        viewport.update()
    services = window.services
    services.action_availability_service.sync_grid_snap_action(window)
    services.status_service.update_grid_control(window)


def set_valence_checking_for_window(window: MainWindowLike, enabled: bool) -> None:

    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        canvas.runtime_state.tool_settings_state.valence_checking = enabled
        viewport = canvas.viewport()
        if viewport is not None:
            viewport.update()


def active_canvas_for_window(window: MainWindowLike) -> CanvasView:
    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        return canvas
    raise RuntimeError("No active canvas.")


def active_canvas_or_none_for_window(window: MainWindowLike) -> CanvasView | None:
    return window.tab_references.active_canvas_or_none(
        window.runtime_state.last_canvas_tab_index
    )


def style_controller_for_window(window: MainWindowLike) -> CanvasStyleController:
    return active_canvas_for_window(window).services.style_controller


def tool_mode_controller_for_window(window: MainWindowLike) -> CanvasToolModeController:
    return active_canvas_for_window(window).services.tool_mode_controller


def insert_controller_for_window(window: MainWindowLike) -> InsertController:
    return active_canvas_for_window(window).services.insert_controller


def color_mutation_service_for_window(
    window: MainWindowLike,
) -> CanvasColorMutationService:
    return active_canvas_for_window(window).services.canvas_color_mutation_service


def scene_transform_controller_for_window(
    window: MainWindowLike,
) -> SceneTransformController:
    return active_canvas_for_window(window).services.scene_transform_controller


def document_session_service_for_window(
    window: MainWindowLike,
) -> CanvasDocumentSessionService:
    return active_canvas_for_window(window).services.canvas_document_session_service


def geometry_controller_for_window(window: MainWindowLike) -> CanvasGeometryController:
    return active_canvas_for_window(window).services.geometry_controller


def history_service_for_window(window: MainWindowLike):
    from chemvas.ui.canvas.canvas_window_access import history_service_for_canvas

    return history_service_for_canvas(active_canvas_for_window(window))


def scene_clipboard_controller_for_window(
    window: MainWindowLike,
) -> SceneClipboardController:
    return active_canvas_for_window(window).services.scene_clipboard_controller


def scene_delete_controller_for_window(window: MainWindowLike) -> SceneDeleteController:
    return active_canvas_for_window(window).services.scene_delete_controller


def _text_editor_for_window(
    window: MainWindowLike,
) -> QLineEdit | QGraphicsTextItem | None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QGraphicsTextItem, QLineEdit, QWidget

    if not isinstance(window, QWidget):
        return None
    # QWidget retains this window's focus target while its native menu is open.
    # QApplication.focusWidget() could instead belong to another window.
    widget = window.focusWidget()
    if widget is None:
        return None
    if isinstance(widget, QLineEdit):
        return widget
    canvas = active_canvas_or_none_for_window(window)
    if canvas is None or widget not in (canvas, canvas.viewport()):
        return None
    from chemvas.ui.canvas.input_view_access import focused_scene_item_for

    item = focused_scene_item_for(canvas)
    if isinstance(item, QGraphicsTextItem) and (
        item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditable
    ):
        return item
    return None


def text_history_availability_for_window(
    window: MainWindowLike,
) -> tuple[bool, bool] | None:
    from PyQt6.QtWidgets import QGraphicsTextItem, QLineEdit

    editor = _text_editor_for_window(window)
    if isinstance(editor, QLineEdit):
        if editor.isReadOnly():
            return False, False
        return editor.isUndoAvailable(), editor.isRedoAvailable()
    if isinstance(editor, QGraphicsTextItem):
        document = editor.document()
        assert document is not None
        return document.isUndoAvailable(), document.isRedoAvailable()
    return None


def _edit_text_for_window(window: MainWindowLike, operation: str) -> bool:
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QKeyEvent, QKeySequence
    from PyQt6.QtWidgets import QLineEdit

    editor = _text_editor_for_window(window)
    if editor is None:
        return False
    if isinstance(editor, QLineEdit):
        if not editor.isReadOnly() or operation in {"Copy", "SelectAll"}:
            getattr(editor, operation[0].lower() + operation[1:])()
    else:
        # Reuse Qt's native rich-text editing, including its clipboard formats
        # and text undo stack, without reimplementing QTextControl operations.
        key = QKeySequence(getattr(QKeySequence.StandardKey, operation))[0]
        event = QKeyEvent(
            QEvent.Type.KeyPress, key.key().value, key.keyboardModifiers()
        )
        scene = editor.scene()
        assert scene is not None
        scene.sendEvent(editor, event)
    # An empty selection or exhausted text history must never fall through to
    # a destructive canvas command.
    return True


def _prepare_document_edit_for_window(window: MainWindowLike) -> None:
    if active_canvas_or_none_for_window(window) is not None:
        active_canvas_for_window(
            window
        ).services.tool_controller.prepare_for_document_edit()


def note_appearance_for_window(window: MainWindowLike) -> None:
    _prepare_document_edit_for_window(window)
    active_canvas_for_window(window).services.note_controller.finish_note_edit()
    window.services.text_style_service.edit_note_appearance(window)


def undo_for_window(window: MainWindowLike) -> None:
    if not _edit_text_for_window(window, "Undo"):
        _prepare_document_edit_for_window(window)
        history_service_for_window(window).undo()


def redo_for_window(window: MainWindowLike) -> None:
    if not _edit_text_for_window(window, "Redo"):
        _prepare_document_edit_for_window(window)
        history_service_for_window(window).redo()


def copy_selection_for_window(window: MainWindowLike) -> bool:
    if _edit_text_for_window(window, "Copy"):
        return True
    if active_canvas_or_none_for_window(window) is None:
        return False
    return bool(
        scene_clipboard_controller_for_window(window).copy_selection_to_clipboard()
    )


def cut_selection_for_window(window: MainWindowLike) -> None:
    if _edit_text_for_window(window, "Cut"):
        return
    _prepare_document_edit_for_window(window)
    if copy_selection_for_window(window):
        scene_delete_controller_for_window(window).delete_selected_items()


def paste_selection_for_window(window: MainWindowLike) -> None:
    if _edit_text_for_window(window, "Paste"):
        return
    if active_canvas_or_none_for_window(window) is None:
        return
    _prepare_document_edit_for_window(window)
    scene_clipboard_controller_for_window(window).paste_selection_from_clipboard()


def select_all_for_window(window: MainWindowLike) -> None:
    if _edit_text_for_window(window, "SelectAll"):
        return

    canvas = active_canvas_or_none_for_window(window)
    if canvas is None:
        return
    tool_mode_controller_for_window(window).set_tool("select")
    canvas.services.selection.select_all()


def group_selection_for_window(window: MainWindowLike) -> None:
    from chemvas.ui.scene.scene_group_operations import group_selection_for

    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        _prepare_document_edit_for_window(window)
        group_selection_for(canvas)


def ungroup_selection_for_window(window: MainWindowLike) -> None:
    from chemvas.ui.scene.scene_group_operations import ungroup_selection_for

    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        _prepare_document_edit_for_window(window)
        ungroup_selection_for(canvas)


def rotate_selection_for_window(window: MainWindowLike, angle_degrees: float) -> None:
    if active_canvas_or_none_for_window(window) is None:
        return
    _prepare_document_edit_for_window(window)
    scene_transform_controller_for_window(window).rotate_selected_items(angle_degrees)


def flip_selection_for_window(window: MainWindowLike, *, horizontal: bool) -> None:
    if active_canvas_or_none_for_window(window) is None:
        return
    _prepare_document_edit_for_window(window)
    scene_transform_controller_for_window(window).flip_selected_items(
        horizontal=horizontal
    )


def align_selection_for_window(window: MainWindowLike, mode: str) -> None:
    if active_canvas_or_none_for_window(window) is None:
        return
    _prepare_document_edit_for_window(window)
    scene_transform_controller_for_window(window).align_selected_items(mode)


def distribute_selection_for_window(window: MainWindowLike, axis: str) -> None:
    if active_canvas_or_none_for_window(window) is None:
        return
    _prepare_document_edit_for_window(window)
    scene_transform_controller_for_window(window).distribute_selected_items(axis)


def active_tool_name_for_window(window: MainWindowLike):
    canvas = active_canvas_or_none_for_window(window)
    if canvas is None:
        return None
    active_tool = getattr(canvas.services.tool_controller, "active", None)
    name = getattr(active_tool, "name", None)
    return str(name) if name else None


def current_zoom_percent_for_window(window: MainWindowLike) -> int:

    canvas = active_canvas_or_none_for_window(window)
    if canvas is None:
        return 100
    return max(1, round(float(canvas.runtime_state.input_view_state.zoom) * 100))


def zoom_in_for_window(window: MainWindowLike) -> int:
    from chemvas.ui.canvas.input_view_access import zoom_in_for

    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        zoom_in_for(canvas)
    return current_zoom_percent_for_window(window)


def zoom_out_for_window(window: MainWindowLike) -> int:
    from chemvas.ui.canvas.input_view_access import zoom_out_for

    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        zoom_out_for(canvas)
    return current_zoom_percent_for_window(window)


def reset_zoom_for_window(window: MainWindowLike) -> int:
    from chemvas.ui.canvas.input_view_access import reset_zoom_for

    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        reset_zoom_for(canvas)
    return current_zoom_percent_for_window(window)


def fit_canvas_to_view_for_window(window: MainWindowLike) -> int:
    from chemvas.ui.canvas.input_view_access import fit_canvas_to_view_for

    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        fit_canvas_to_view_for(canvas)
    return current_zoom_percent_for_window(window)


def set_zoom_percent_for_window(window: MainWindowLike, percent: float) -> int:
    from chemvas.ui.canvas.input_view_access import set_zoom_for

    canvas = active_canvas_or_none_for_window(window)
    if canvas is not None:
        set_zoom_for(canvas, percent / 100.0)
    return current_zoom_percent_for_window(window)


def active_canvas_name_for_window(window: MainWindowLike) -> str:
    return window.tab_references.active_canvas_name(
        active_canvas_or_none_for_window(window)
    )


def active_canvas_index_for_window(window: MainWindowLike) -> int:
    return window.tab_references.active_canvas_index(
        active_canvas_or_none_for_window(window)
    )


def set_bond_length_for_window(window: MainWindowLike, value: float) -> None:
    if active_canvas_or_none_for_window(window) is None:
        return
    _prepare_document_edit_for_window(window)
    geometry_controller_for_window(window).set_bond_length(float(value))


def bond_length_px_for_window(window: MainWindowLike) -> float:

    return active_canvas_for_window(window).renderer.style.bond_length_px


def sheet_size_for_window(window: MainWindowLike) -> str:
    from chemvas.ui.canvas.sheet_setup_access import sheet_size_for

    return sheet_size_for(active_canvas_for_window(window))


def sheet_orientation_for_window(window: MainWindowLike) -> str:
    from chemvas.ui.canvas.sheet_setup_access import sheet_orientation_for

    return sheet_orientation_for(active_canvas_for_window(window))


def set_sheet_setup_for_window(
    window: MainWindowLike, size: str, orientation: str
) -> None:
    from chemvas.ui.canvas.sheet_setup_service import change_sheet_setup_for

    change_sheet_setup_for(active_canvas_for_window(window), size, orientation)


def next_canvas_name_for_window(window: MainWindowLike, prefix: str = "Canvas") -> str:
    return window.runtime_state.next_canvas_name(prefix)


def note_controller_for_window(window: MainWindowLike):
    canvas = active_canvas_or_none_for_window(window)
    return None if canvas is None else canvas.services.note_controller


def color_tool_for_window(window: MainWindowLike):
    return getattr(
        active_canvas_for_window(window).services.tool_controller, "tools", {}
    ).get("color")


def selected_scene_items_for_window(window: MainWindowLike, *, excluded_kinds):
    from chemvas.ui.selection.selection_queries import selected_scene_items_for

    return selected_scene_items_for(
        active_canvas_for_window(window), excluded_kinds=excluded_kinds
    )


__all__ = [
    "active_canvas_for_window",
    "active_canvas_index_for_window",
    "active_canvas_name_for_window",
    "active_canvas_or_none_for_window",
    "active_tool_name_for_window",
    "align_selection_for_window",
    "bond_length_px_for_window",
    "color_mutation_service_for_window",
    "color_tool_for_window",
    "copy_selection_for_window",
    "current_zoom_percent_for_window",
    "cut_selection_for_window",
    "distribute_selection_for_window",
    "document_session_service_for_window",
    "fit_canvas_to_view_for_window",
    "flip_selection_for_window",
    "geometry_controller_for_window",
    "group_selection_for_window",
    "history_service_for_window",
    "insert_controller_for_window",
    "next_canvas_name_for_window",
    "note_appearance_for_window",
    "note_controller_for_window",
    "paste_selection_for_window",
    "redo_for_window",
    "reset_zoom_for_window",
    "rotate_selection_for_window",
    "scene_clipboard_controller_for_window",
    "scene_delete_controller_for_window",
    "scene_transform_controller_for_window",
    "select_all_for_window",
    "selected_scene_items_for_window",
    "set_bond_length_for_window",
    "set_grid_snap_for_window",
    "set_sheet_setup_for_window",
    "set_zoom_percent_for_window",
    "sheet_orientation_for_window",
    "sheet_size_for_window",
    "status_bar_for",
    "style_controller_for_window",
    "text_history_availability_for_window",
    "tool_mode_controller_for_window",
    "undo_for_window",
    "ungroup_selection_for_window",
    "zoom_in_for_window",
    "zoom_out_for_window",
]
