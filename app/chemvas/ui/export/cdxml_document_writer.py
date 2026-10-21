"""Atomic page-sized CDXML saves through the existing native exporter."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from chemvas.core.document_io import atomic_write_via_temp
from chemvas.features.cdxml_document import embed_document
from chemvas.ui.canvas.sheet_setup_access import sheet_rect_for

if TYPE_CHECKING:
    from pathlib import Path

    from chemvas.ui.canvas.canvas_view import CanvasView


def serialize_cdxml_document(canvas: CanvasView, state: dict[str, Any]) -> bytes:
    if "cdxml_source" in state:
        from chemvas.features.cdxml_native_writer import update_native_document
        from chemvas.ui.export.cdxml_native_text import write_native_caption

        return embed_document(
            update_native_document(state, note_writer=write_native_caption), state
        )
    from chemvas.ui.export.cdxml_working_document import serialize_working_document

    return embed_document(
        serialize_working_document(canvas.render_context, sheet_rect_for(canvas)), state
    )


def save_cdxml_document(canvas: CanvasView, path: str, state: dict[str, Any]) -> str:
    raw = serialize_cdxml_document(canvas, state)

    def write(temporary: Path) -> None:
        temporary.write_bytes(raw)

    atomic_write_via_temp(path, write)
    return hashlib.sha256(raw).hexdigest()
