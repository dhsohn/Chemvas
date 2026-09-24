from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from chemvas.ui.canvas.canvas_document_metadata_state import (
    document_is_dirty_for,
    mark_document_clean_for,
    mark_document_dirty_for,
    note_chrome_dirty_for,
    set_document_file_path_for,
    validate_document_file_path,
)
from chemvas.ui.canvas.canvas_lifecycle import schedule_canvas_deletion_for
from chemvas.ui.window.main_window_canvas_logic import copy_canvas_template_settings
from chemvas.ui.window.main_window_ports import (
    active_canvas_or_none_for_window,
    next_canvas_name_for_window,
)
from chemvas.ui.window.tab_title_logic import decorate_tab_title, window_title

if TYPE_CHECKING:
    from collections.abc import Callable

    from chemvas.ui.canvas.canvas_view import CanvasView
    from chemvas.ui.window.main_window_like import MainWindowLike


class MainWindowCanvasDocumentService:
    def __init__(
        self,
        *,
        active_canvas_ui,
        canvas_factory: Callable[[], CanvasView],
        status_service,
    ) -> None:
        self._active_canvas_ui = active_canvas_ui
        self._canvas_factory = canvas_factory
        self._status = status_service

    def create_canvas(
        self, window: MainWindowLike, *, template: CanvasView | None = None
    ) -> CanvasView:
        canvas = self._canvas_factory()
        copy_canvas_template_settings(canvas, template)
        return canvas

    def add_canvas(
        self,
        window: MainWindowLike,
        *,
        name: str | None = None,
        display_name: str | None = None,
        state: dict | None = None,
        file_path: str | None = None,
        select: bool = True,
        template: CanvasView | None = None,
    ) -> CanvasView:
        validate_document_file_path(file_path)
        canvas = self.create_canvas(window, template=template)
        if state is not None:
            canvas.services.canvas_document_session_service.restore_state(state)
        resolved_display_name = display_name or (
            self.display_name_for_path(file_path) if file_path else name
        )
        if not resolved_display_name:
            resolved_display_name = next_canvas_name_for_window(window)
        canvas.runtime_state.document_metadata_state.display_name = (
            resolved_display_name
        )
        set_document_file_path_for(canvas, file_path)
        mark_document_clean_for(
            canvas, canvas.services.canvas_document_session_service.snapshot_state()
        )

        tab_refs = window.tab_references
        index = tab_refs.canvas_tabs.addTab(canvas, resolved_display_name)
        if select:
            tab_refs.canvas_tabs.setCurrentIndex(index)
            window.runtime_state.last_canvas_tab_index = index
        self._active_canvas_ui.bind_active_canvas(window)
        return canvas

    def new_canvas(self, window: MainWindowLike) -> CanvasView:
        template = active_canvas_or_none_for_window(window)
        return self.add_canvas(
            window,
            name=next_canvas_name_for_window(window),
            select=True,
            template=template,
        )

    def replace_canvas_with_state(
        self,
        window: MainWindowLike,
        canvas: CanvasView,
        *,
        state: dict,
        file_path: str | None,
        display_name: str | None = None,
    ) -> None:
        validate_document_file_path(file_path)
        canvas.services.canvas_document_session_service.restore_state(state)
        resolved_name = (
            display_name
            or self.display_name_for_path(file_path)
            or canvas.runtime_state.document_metadata_state.display_name
        )
        canvas.runtime_state.document_metadata_state.display_name = resolved_name
        set_document_file_path_for(canvas, file_path)
        mark_document_clean_for(
            canvas, canvas.services.canvas_document_session_service.snapshot_state()
        )
        self.refresh_tab_title(window, canvas)
        self._active_canvas_ui.refresh_active_canvas_ui(window)

    def open_state(
        self,
        window: MainWindowLike,
        *,
        state: dict,
        file_path: str | None,
        display_name: str | None = None,
    ) -> CanvasView:
        target = self.reusable_open_target(window)
        if target is not None:
            self.replace_canvas_with_state(
                window,
                target,
                state=state,
                file_path=file_path,
                display_name=display_name,
            )
            tab_refs = window.tab_references
            index = tab_refs.active_canvas_tab_index(target)
            if index >= 0:
                tab_refs.canvas_tabs.setCurrentIndex(index)
                window.runtime_state.last_canvas_tab_index = index
            return target
        return self.add_canvas(
            window,
            state=state,
            file_path=file_path,
            display_name=display_name,
            select=True,
        )

    def reusable_open_target(self, window: MainWindowLike) -> CanvasView | None:
        tab_refs = window.tab_references
        canvases = tab_refs.all_canvases()
        if len(canvases) != 1:
            return None
        canvas = canvases[0]
        if canvas.runtime_state.document_metadata_state.file_path is not None:
            return None
        state = canvas.services.canvas_document_session_service.snapshot_state()
        if document_is_dirty_for(canvas, state):
            return None
        # Imported MOL/editable SVG documents can be clean but unbound. Only
        # an actually empty canvas may be replaced without keeping its window.
        # Ignore settings and the allocation counter, not scene/model content.
        if any(
            value for key, value in state.items() if key not in {"model", "settings"}
        ):
            return None
        if any(value for key, value in state["model"].items() if key != "next_atom_id"):
            return None
        return canvas

    def remove_canvas(self, window: MainWindowLike, canvas: CanvasView) -> None:
        tab_refs = window.tab_references
        index = tab_refs.active_canvas_tab_index(canvas)
        if index < 0:
            return
        tab_refs.canvas_tabs.removeTab(index)
        schedule_canvas_deletion_for(canvas)
        if tab_refs.canvas_count() == 0:
            self.add_canvas(
                window, name=next_canvas_name_for_window(window), select=True
            )
            return
        new_index = min(index, tab_refs.canvas_tabs.count() - 1)
        tab_refs.canvas_tabs.setCurrentIndex(new_index)
        window.runtime_state.last_canvas_tab_index = new_index
        self._active_canvas_ui.refresh_active_canvas_ui(window)

    def is_dirty(self, canvas: CanvasView) -> bool:
        return document_is_dirty_for(
            canvas, canvas.services.canvas_document_session_service.snapshot_state()
        )

    def mark_clean(self, canvas: CanvasView) -> None:
        mark_document_clean_for(
            canvas, canvas.services.canvas_document_session_service.snapshot_state()
        )

    def mark_dirty(self, canvas: CanvasView) -> None:
        """Force a document to read as unsaved — used when restoring recovered
        work whose last-saved baseline is unknown."""
        mark_document_dirty_for(canvas)

    def file_path(self, canvas: CanvasView) -> str | None:
        return canvas.runtime_state.document_metadata_state.file_path

    def set_file_path(self, canvas: CanvasView, path: str | None) -> None:
        set_document_file_path_for(canvas, path)

    def set_display_name(self, canvas: CanvasView, name: str) -> None:
        canvas.runtime_state.document_metadata_state.display_name = name

    def display_name(self, canvas: CanvasView) -> str:
        return canvas.runtime_state.document_metadata_state.display_name

    def refresh_tab_title(
        self, window: MainWindowLike, canvas: CanvasView, *, edited_note=None
    ) -> None:
        tab_refs = window.tab_references
        if edited_note is None:
            canvas.runtime_state.document_metadata_state.note_chrome_session = None
            dirty = self.is_dirty(canvas)
        else:
            dirty = note_chrome_dirty_for(
                canvas,
                edited_note,
                lambda target: (
                    target.services.canvas_document_session_service.snapshot_state()
                ),
            )
        index = tab_refs.active_canvas_tab_index(canvas)
        if index >= 0:
            tab_refs.canvas_tabs.setTabText(
                index, decorate_tab_title(self.display_name(canvas), dirty=dirty)
            )
        self._refresh_window_title(window, canvas, dirty=dirty)
        self._status.update_sheet_status_label(window)

    def _refresh_window_title(
        self, window: MainWindowLike, canvas: CanvasView, *, dirty: bool | None = None
    ) -> None:
        if dirty is None:
            dirty = self.is_dirty(canvas)
        set_modified = getattr(window, "setWindowModified", None)
        if callable(set_modified):
            set_modified(dirty)
        set_title = getattr(window, "setWindowTitle", None)
        if callable(set_title):
            set_title(window_title(self.display_name(canvas)))

    @staticmethod
    def display_name_for_path(path: str | None) -> str | None:
        if not path:
            return None
        return Path(path).name


__all__ = ["MainWindowCanvasDocumentService"]
