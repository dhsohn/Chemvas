from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Callable

from core.model import Bond
from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QGraphicsItem

from ui.export_render_service import (
    render_scene_to_pdf_bytes,
    render_scene_to_svg_bytes,
)
from ui.scene_clipboard_logic import build_selection_clipboard_payload
from ui.scene_clipboard_state import scene_clipboard_state_for
from ui.scene_clipboard_transaction_logic import visible_items_to_hide_for_copy
from ui.scene_item_access import canvas_scene_for


def clipboard_paste_source_json_for(canvas) -> str | None:
    return scene_clipboard_state_for(canvas).paste_source_json


def set_clipboard_paste_source_json_for(canvas, value: str | None) -> None:
    scene_clipboard_state_for(canvas).paste_source_json = value


def clipboard_paste_count_for(canvas) -> int:
    return scene_clipboard_state_for(canvas).paste_count


def set_clipboard_paste_count_for(canvas, value: int) -> None:
    scene_clipboard_state_for(canvas).paste_count = int(value)


def build_selection_clipboard_payload_for_canvas(
    canvas,
    *,
    selected_items: Sequence[QGraphicsItem],
    explicit_atom_ids: set[int],
    selected_bond_ids: set[int],
    bonds: Sequence[Bond | None],
    ring_items: Sequence[QGraphicsItem],
    marks_by_atom: Mapping[int, Sequence[QGraphicsItem]],
    atom_state_getter: Callable[[int], dict],
    bond_state_getter: Callable[[object], dict],
    scene_item_state_getter: Callable[[QGraphicsItem], dict],
    version: int,
) -> dict | None:
    return build_selection_clipboard_payload(
        selected_items=selected_items,
        explicit_atom_ids=explicit_atom_ids,
        selected_bond_ids=selected_bond_ids,
        bonds=bonds,
        ring_items=ring_items,
        marks_by_atom=marks_by_atom,
        scene=canvas_scene_for(canvas),
        atom_state_getter=atom_state_getter,
        bond_state_getter=bond_state_getter,
        scene_item_state_getter=scene_item_state_getter,
        version=version,
    )


def visible_canvas_items_to_hide_for_copy(
    canvas,
    source: QRectF,
    *,
    selected_items: Collection[QGraphicsItem],
) -> list[QGraphicsItem]:
    return visible_items_to_hide_for_copy(
        canvas_scene_for(canvas).items(source),
        selected_items=selected_items,
    )


def render_canvas_scene_region(canvas, painter, *, source: QRectF) -> None:
    target = QRectF(0, 0, source.width(), source.height())
    canvas_scene_for(canvas).render(painter, target, source)


def render_canvas_selection_vector_bytes(
    canvas,
    *,
    source: QRectF,
    items: Sequence[QGraphicsItem],
    title: str | None = None,
) -> tuple[bytes, bytes]:
    scene = canvas_scene_for(canvas)
    return (
        render_scene_to_svg_bytes(scene, source=source, items=items, title=title),
        render_scene_to_pdf_bytes(scene, source=source, items=items, title=title),
    )


__all__ = [
    "build_selection_clipboard_payload_for_canvas",
    "clipboard_paste_count_for",
    "clipboard_paste_source_json_for",
    "render_canvas_scene_region",
    "render_canvas_selection_vector_bytes",
    "set_clipboard_paste_count_for",
    "set_clipboard_paste_source_json_for",
    "visible_canvas_items_to_hide_for_copy",
]
