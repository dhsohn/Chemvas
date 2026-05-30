from __future__ import annotations

from core.document_io import read_document, write_document
from core.document_state import deserialize_model_state
from ui.canvas_document_state import (
    apply_document_settings,
    restore_document_post_model_items,
    restore_document_pre_model_items,
    snapshot_canvas_document_state,
)


class CanvasDocumentSessionService:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def snapshot_state(self) -> dict:
        return snapshot_canvas_document_state(self.canvas)

    def apply_state(self, state: dict) -> None:
        self.canvas._history_enabled = False
        try:
            self.canvas.clear_scene()
            apply_document_settings(self.canvas, state)
            self.canvas.model = deserialize_model_state(state["model"])
            self.canvas._rebuild_bond_adjacency()
            restore_document_pre_model_items(self.canvas, state)
            self.canvas._render_model()
            restore_document_post_model_items(self.canvas, state)
            self.canvas._mark_spatial_index_dirty()
        finally:
            self.canvas._history_enabled = True

    def restore_state(self, state: dict) -> None:
        self.apply_state(state)
        self.canvas._history = []
        self.canvas._redo_stack = []
        self.canvas._notify_history_change()

    def save_to_file(self, path: str) -> None:
        write_document(path, self.snapshot_state(), self.canvas.FILE_FORMAT_VERSION)

    def load_from_file(self, path: str) -> None:
        document = read_document(path)
        self.restore_state(document.state)


__all__ = ["CanvasDocumentSessionService"]
