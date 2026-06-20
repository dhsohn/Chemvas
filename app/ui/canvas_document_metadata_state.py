from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from ui.canvas_state_lookup import canvas_state_object


@dataclass
class CanvasDocumentMetadataState:
    file_path: str | None = None
    display_name: str = "Canvas 1"
    clean_digest: str | None = None


def document_metadata_state_for(canvas: Any) -> CanvasDocumentMetadataState:
    state = canvas_state_object(canvas, "document_metadata_state")
    if isinstance(state, CanvasDocumentMetadataState):
        return state
    state = CanvasDocumentMetadataState()
    canvas.document_metadata_state = state
    return state


def canonical_document_digest(state: dict) -> str:
    payload = json.dumps(
        state,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def mark_document_clean_for(canvas: Any, state: dict) -> None:
    document_metadata_state_for(canvas).clean_digest = canonical_document_digest(state)


def set_document_file_path_for(canvas: Any, path: str | None) -> None:
    document_metadata_state_for(canvas).file_path = path


def document_file_path_for(canvas: Any) -> str | None:
    return document_metadata_state_for(canvas).file_path


def set_document_display_name_for(canvas: Any, name: str) -> None:
    document_metadata_state_for(canvas).display_name = name


def document_display_name_for(canvas: Any) -> str:
    return document_metadata_state_for(canvas).display_name


def document_is_dirty_for(canvas: Any, state: dict) -> bool:
    clean_digest = document_metadata_state_for(canvas).clean_digest
    return clean_digest is not None and canonical_document_digest(state) != clean_digest


__all__ = [
    "CanvasDocumentMetadataState",
    "canonical_document_digest",
    "document_display_name_for",
    "document_file_path_for",
    "document_is_dirty_for",
    "document_metadata_state_for",
    "mark_document_clean_for",
    "set_document_display_name_for",
    "set_document_file_path_for",
]
