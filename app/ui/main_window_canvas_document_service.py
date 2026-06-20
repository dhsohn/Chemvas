from __future__ import annotations

from pathlib import Path

from ui.canvas_document_metadata_state import (
    document_display_name_for,
    document_file_path_for,
    document_is_dirty_for,
    mark_document_clean_for,
    set_document_display_name_for,
    set_document_file_path_for,
)
from ui.canvas_view import CanvasView
from ui.canvas_window_access import restore_canvas_state_for, snapshot_canvas_state_for
from ui.main_window_canvas_logic import copy_canvas_template_settings


class MainWindowCanvasDocumentService:
    def __init__(
        self,
        *,
        active_canvas_ui,
        tab_refs_for_window,
        active_canvas_or_none_for_window,
        next_canvas_name_for_window,
        set_last_canvas_tab_index_for_window,
    ) -> None:
        self._active_canvas_ui = active_canvas_ui
        self._tab_refs_for_window = tab_refs_for_window
        self._active_canvas_or_none_for_window = active_canvas_or_none_for_window
        self._next_canvas_name_for_window = next_canvas_name_for_window
        self._set_last_canvas_tab_index_for_window = set_last_canvas_tab_index_for_window

    def create_canvas(self, window, *, template: CanvasView | None = None) -> CanvasView:
        canvas = CanvasView()
        canvas.setFrameStyle(0)
        copy_canvas_template_settings(canvas, template)
        return canvas

    def add_canvas(
        self,
        window,
        *,
        name: str | None = None,
        display_name: str | None = None,
        state: dict | None = None,
        file_path: str | None = None,
        select: bool = True,
        template: CanvasView | None = None,
    ) -> CanvasView:
        canvas = self.create_canvas(window, template=template)
        if state is not None:
            restore_canvas_state_for(canvas, state)
        resolved_display_name = display_name or (self.display_name_for_path(file_path) if file_path else name)
        if not resolved_display_name:
            resolved_display_name = self._next_canvas_name_for_window(window)
        set_document_display_name_for(canvas, resolved_display_name)
        set_document_file_path_for(canvas, file_path)
        mark_document_clean_for(canvas, snapshot_canvas_state_for(canvas))

        tab_refs = self._tab_refs_for_window(window)
        index = tab_refs.canvas_tabs.addTab(canvas, resolved_display_name)
        if select:
            tab_refs.canvas_tabs.setCurrentIndex(index)
            self._set_last_canvas_tab_index_for_window(window, index)
        self._active_canvas_ui.bind_active_canvas(window)
        return canvas

    def new_canvas(self, window) -> CanvasView:
        template = self._active_canvas_or_none_for_window(window)
        return self.add_canvas(
            window,
            name=self._next_canvas_name_for_window(window),
            select=True,
            template=template,
        )

    def replace_canvas_with_state(
        self,
        window,
        canvas: CanvasView,
        *,
        state: dict,
        file_path: str | None,
        display_name: str | None = None,
    ) -> None:
        restore_canvas_state_for(canvas, state)
        resolved_name = display_name or self.display_name_for_path(file_path) or document_display_name_for(canvas)
        set_document_display_name_for(canvas, resolved_name)
        set_document_file_path_for(canvas, file_path)
        mark_document_clean_for(canvas, snapshot_canvas_state_for(canvas))
        self.refresh_tab_title(window, canvas)
        self._active_canvas_ui.refresh_active_canvas_ui(window)

    def open_state(
        self,
        window,
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
            tab_refs = self._tab_refs_for_window(window)
            index = tab_refs.active_canvas_tab_index(target)
            if index >= 0:
                tab_refs.canvas_tabs.setCurrentIndex(index)
                self._set_last_canvas_tab_index_for_window(window, index)
            return target
        return self.add_canvas(
            window,
            state=state,
            file_path=file_path,
            display_name=display_name,
            select=True,
        )

    def reusable_open_target(self, window) -> CanvasView | None:
        tab_refs = self._tab_refs_for_window(window)
        canvases = tab_refs.all_canvases()
        if len(canvases) != 1:
            return None
        canvas = canvases[0]
        if document_file_path_for(canvas) is not None:
            return None
        if self.is_dirty(canvas):
            return None
        return canvas

    def remove_canvas(self, window, canvas: CanvasView) -> None:
        tab_refs = self._tab_refs_for_window(window)
        index = tab_refs.active_canvas_tab_index(canvas)
        if index < 0:
            return
        tab_refs.canvas_tabs.removeTab(index)
        canvas.deleteLater()
        if tab_refs.canvas_count() == 0:
            self.add_canvas(window, name=self._next_canvas_name_for_window(window), select=True)
            return
        new_index = min(index, tab_refs.canvas_tabs.count() - 1)
        tab_refs.canvas_tabs.setCurrentIndex(new_index)
        self._set_last_canvas_tab_index_for_window(window, new_index)
        self._active_canvas_ui.refresh_active_canvas_ui(window)

    def is_dirty(self, canvas: CanvasView) -> bool:
        return document_is_dirty_for(canvas, snapshot_canvas_state_for(canvas))

    def mark_clean(self, canvas: CanvasView) -> None:
        mark_document_clean_for(canvas, snapshot_canvas_state_for(canvas))

    def file_path(self, canvas: CanvasView) -> str | None:
        return document_file_path_for(canvas)

    def set_file_path(self, canvas: CanvasView, path: str | None) -> None:
        set_document_file_path_for(canvas, path)

    def set_display_name(self, canvas: CanvasView, name: str) -> None:
        set_document_display_name_for(canvas, name)

    def display_name(self, canvas: CanvasView) -> str:
        return document_display_name_for(canvas)

    def refresh_tab_title(self, window, canvas: CanvasView) -> None:
        tab_refs = self._tab_refs_for_window(window)
        index = tab_refs.active_canvas_tab_index(canvas)
        if index >= 0:
            tab_refs.canvas_tabs.setTabText(index, self.display_name(canvas))

    @staticmethod
    def display_name_for_path(path: str | None) -> str | None:
        if not path:
            return None
        return Path(path).name


__all__ = ["MainWindowCanvasDocumentService"]
