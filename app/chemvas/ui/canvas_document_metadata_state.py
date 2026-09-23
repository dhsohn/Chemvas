from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from chemvas.ui.main_window_path_logic import is_canonical_saved_document_path

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(slots=True)
class _NoteChromeSession:
    item: object
    other_dirty: bool
    clean_note: str | None


@dataclass(slots=True)
class CanvasDocumentMetadataState:
    file_path: str | None = None
    display_name: str = "Canvas 1"
    clean_digest: str | None = None
    source_sha256: str | None = None
    clean_non_notes_digest: str | None = None
    clean_notes: tuple[str, ...] = ()
    note_chrome_session: _NoteChromeSession | None = None


def document_metadata_state_for(canvas: Any) -> CanvasDocumentMetadataState:
    return cast(
        "CanvasDocumentMetadataState",
        canvas.runtime_state.document_metadata_state,
    )


def canonical_document_digest(state: dict) -> str:
    payload = json.dumps(
        state,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def mark_document_clean_for(canvas: Any, state: dict) -> None:
    metadata = document_metadata_state_for(canvas)
    metadata.clean_digest = canonical_document_digest(state)
    metadata.clean_non_notes_digest = _non_notes_digest(state)
    metadata.clean_notes = _note_fingerprints(state)
    metadata.note_chrome_session = None


def _non_notes_digest(state: dict) -> str:
    return canonical_document_digest(
        {key: value for key, value in state.items() if key != "notes"}
    )


def _note_fingerprints(state: dict) -> tuple[str, ...]:
    return tuple(canonical_document_digest(note) for note in state.get("notes", []))


def invalidate_note_chrome_for(canvas: Any) -> None:
    document_metadata_state_for(canvas).note_chrome_session = None


def note_chrome_dirty_for(
    canvas: Any, item: object, snapshot: Callable[[Any], dict]
) -> bool:
    """A live-note UI hint; save/close/recovery always use the exact full digest.

    Cache only the part untouched by typing. General UI refreshes, tab binding,
    history publication and saving invalidate this bounded editing session.
    """
    from chemvas.ui.canvas_document_state import snapshot_note_document_state
    from chemvas.ui.canvas_scene_items_state import note_items_for
    from chemvas.ui.scene_item_access import attached_canvas_scene_items

    metadata = document_metadata_state_for(canvas)
    if metadata.clean_digest is None:
        return False
    if metadata.clean_digest == _RECOVERED_DIRTY_DIGEST:
        return True
    session = metadata.note_chrome_session
    if session is None or session.item is not item:
        state = snapshot(canvas)
        items = attached_canvas_scene_items(canvas, note_items_for(canvas))
        if item not in items or metadata.clean_non_notes_digest is None:
            return document_is_dirty_for(canvas, state)
        index = items.index(item)
        notes = _note_fingerprints(state)
        clean = metadata.clean_notes
        session = _NoteChromeSession(
            item=item,
            other_dirty=(
                _non_notes_digest(state) != metadata.clean_non_notes_digest
                or len(notes) != len(clean)
                or notes[:index] != clean[:index]
                or notes[index + 1 :] != clean[index + 1 :]
            ),
            clean_note=clean[index] if index < len(clean) else None,
        )
        metadata.note_chrome_session = session
    return session.other_dirty or (
        canonical_document_digest(snapshot_note_document_state(canvas, item))
        != session.clean_note
    )


# A non-hex sentinel that no real SHA-256 digest can equal, so the document
# reads as dirty until the next genuine save. Used when restoring recovered
# unsaved work, whose "last saved" baseline is unknown.
_RECOVERED_DIRTY_DIGEST = "recovered-unsaved"


def mark_document_dirty_for(canvas: Any) -> None:
    document_metadata_state_for(canvas).clean_digest = _RECOVERED_DIRTY_DIGEST
    invalidate_note_chrome_for(canvas)


def set_document_file_path_for(canvas: Any, path: str | None) -> None:
    validate_document_file_path(path)
    document_metadata_state_for(canvas).file_path = path
    document_metadata_state_for(canvas).source_sha256 = None


def document_source_sha256_for(canvas: Any) -> str | None:
    return document_metadata_state_for(canvas).source_sha256


def set_document_source_sha256_for(canvas: Any, digest: str | None) -> None:
    document_metadata_state_for(canvas).source_sha256 = digest


def validate_document_file_path(path: str | None) -> None:
    if path is not None and not is_canonical_saved_document_path(path):
        msg = "Chemvas document paths must use the .chemvas filename extension."
        raise ValueError(msg)


def document_file_path_for(canvas: Any) -> str | None:
    return document_metadata_state_for(canvas).file_path


def set_document_display_name_for(canvas: Any, name: str) -> None:
    document_metadata_state_for(canvas).display_name = name


def document_display_name_for(canvas: Any) -> str:
    return document_metadata_state_for(canvas).display_name


def document_is_dirty_for(canvas: Any, state: dict) -> bool:
    return document_dirty_status_for(canvas, state)[0]


def document_dirty_status_for(canvas: Any, state: dict) -> tuple[bool, str | None]:
    """Return dirtiness and the digest already computed for this exact snapshot."""
    clean_digest = document_metadata_state_for(canvas).clean_digest
    if clean_digest == _RECOVERED_DIRTY_DIGEST:
        return True, None
    if clean_digest is None:
        return False, None
    digest = canonical_document_digest(state)
    return digest != clean_digest, digest


__all__ = [
    "CanvasDocumentMetadataState",
    "canonical_document_digest",
    "document_dirty_status_for",
    "document_display_name_for",
    "document_file_path_for",
    "document_is_dirty_for",
    "document_metadata_state_for",
    "document_source_sha256_for",
    "mark_document_clean_for",
    "mark_document_dirty_for",
    "set_document_display_name_for",
    "set_document_file_path_for",
    "set_document_source_sha256_for",
    "validate_document_file_path",
]
