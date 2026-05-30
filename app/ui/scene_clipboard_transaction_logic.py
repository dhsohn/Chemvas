from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Callable, Collection, Sequence

from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QGraphicsItem


@dataclass(slots=True)
class ClipboardCopyPlan:
    source: QRectF
    scale: float
    image_width: int
    image_height: int
    payload_json: str | None


@dataclass(slots=True)
class ClipboardPastePlan:
    paste_source_json: str
    paste_count: int
    dx: float
    dy: float
    atoms: Sequence[object]
    bonds: Sequence[object]
    rings: Sequence[object]
    marks: Sequence[object]
    scene_items: Sequence[object]
    before_next_atom_id: int
    before_bond_count: int
    before_smiles_input: object

    def has_payload_content(self) -> bool:
        return bool(self.atoms or self.bonds or self.rings or self.marks or self.scene_items)


def build_clipboard_copy_plan(
    items: Sequence[QGraphicsItem],
    *,
    payload: dict | None,
    bond_line_width: float,
    device_pixel_ratio: float,
) -> ClipboardCopyPlan | None:
    bounds = _copy_bounds_for_items(items)
    if bounds is None or bounds.width() <= 0 or bounds.height() <= 0:
        return None
    pad = max(2.0, bond_line_width * 2.0)
    source = bounds.adjusted(-pad, -pad, pad, pad)
    scale = max(1.0, float(device_pixel_ratio))
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True) if payload is not None else None
    return ClipboardCopyPlan(
        source=source,
        scale=scale,
        image_width=max(1, int(math.ceil(source.width() * scale))),
        image_height=max(1, int(math.ceil(source.height() * scale))),
        payload_json=payload_json,
    )


def clipboard_copy_cache_values(payload_json: str | None) -> tuple[str | None, int]:
    if payload_json is None:
        return None, 0
    return payload_json, 0


def visible_items_to_hide_for_copy(
    scene_items: Sequence[QGraphicsItem],
    *,
    selected_items: Collection[QGraphicsItem],
) -> list[QGraphicsItem]:
    hidden: list[QGraphicsItem] = []
    for item in scene_items:
        if item in selected_items:
            continue
        if not item.isVisible():
            continue
        hidden.append(item)
    return hidden


def build_clipboard_paste_plan(
    *,
    payload: dict | None,
    payload_json: str | None,
    previous_source_json: str | None,
    previous_paste_count: int,
    bond_length_px: float,
    clipboard_paste_offset: Callable[[int, float], tuple[float, float]],
    before_next_atom_id: int,
    before_bond_count: int,
    before_smiles_input: object,
) -> ClipboardPastePlan | None:
    if payload is None or payload_json is None:
        return None
    paste_count = previous_paste_count + 1 if payload_json == previous_source_json else 1
    dx, dy = clipboard_paste_offset(paste_count, bond_length_px)
    return ClipboardPastePlan(
        paste_source_json=payload_json,
        paste_count=paste_count,
        dx=dx,
        dy=dy,
        atoms=payload.get("atoms", []),
        bonds=payload.get("bonds", []),
        rings=payload.get("rings", []),
        marks=payload.get("marks", []),
        scene_items=payload.get("scene_items", []),
        before_next_atom_id=before_next_atom_id,
        before_bond_count=before_bond_count,
        before_smiles_input=before_smiles_input,
    )


def _copy_bounds_for_items(items: Sequence[QGraphicsItem]) -> QRectF | None:
    bounds = None
    for item in items:
        rect = item.sceneBoundingRect()
        if not rect.isValid():
            continue
        bounds = rect if bounds is None else bounds.united(rect)
    return bounds


__all__ = [
    "ClipboardCopyPlan",
    "ClipboardPastePlan",
    "build_clipboard_copy_plan",
    "build_clipboard_paste_plan",
    "clipboard_copy_cache_values",
    "visible_items_to_hide_for_copy",
]
