from __future__ import annotations

import json
import math
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass

from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QGraphicsItem

from chemvas.ui.scene_item_state import ARROW_KINDS


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
    perspective: object | None
    before_next_atom_id: int
    before_bond_count: int
    before_smiles_input: object

    def has_payload_content(self) -> bool:
        return bool(
            self.atoms or self.bonds or self.rings or self.marks or self.scene_items
        )


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
    payload_json = (
        json.dumps(payload, separators=(",", ":"), sort_keys=True)
        if payload is not None
        else None
    )
    return ClipboardCopyPlan(
        source=source,
        scale=scale,
        image_width=max(1, math.ceil(source.width() * scale)),
        image_height=max(1, math.ceil(source.height() * scale)),
        payload_json=payload_json,
    )


def clipboard_copy_cache_values(payload_json: str | None) -> tuple[str | None, int]:
    if payload_json is None:
        return None, 0
    return payload_json, 0


def clipboard_paste_offset(step: int, bond_length_px: float) -> tuple[float, float]:
    magnitude = max(18.0, bond_length_px * 0.35) * max(1, step)
    return magnitude, magnitude


def translated_point_value(value, dx: float, dy: float):
    if (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
    ):
        return (float(value[0]) + dx, float(value[1]) + dy)
    return value


def translated_scene_item_state(
    state: dict,
    *,
    dx: float,
    dy: float,
    atom_id_map: dict[int, int],
) -> dict | None:
    if not isinstance(state, dict):
        return None
    translated = dict(state)
    kind = translated.get("kind")
    if kind == "ring":
        ring_atom_ids = translated.get("atom_ids")
        if not isinstance(ring_atom_ids, list) or not ring_atom_ids:
            return None
        mapped_atom_ids: list[int] = []
        for atom_id in ring_atom_ids:
            if not isinstance(atom_id, int) or atom_id not in atom_id_map:
                return None
            mapped_atom_ids.append(atom_id_map[atom_id])
        points = translated.get("points", [])
        translated_points = []
        for point in points:
            translated_point = translated_point_value(point, dx, dy)
            if translated_point is None or translated_point is point:
                continue
            translated_points.append(translated_point)
        translated["atom_ids"] = mapped_atom_ids
        translated["points"] = translated_points
        return translated
    if kind == "mark":
        atom_id = translated.get("atom_id")
        translated["atom_id"] = (
            atom_id_map.get(atom_id) if isinstance(atom_id, int) else None
        )
        if isinstance(translated.get("x"), (int, float)):
            translated["x"] = float(translated["x"]) + dx
        if isinstance(translated.get("y"), (int, float)):
            translated["y"] = float(translated["y"]) + dy
        return translated
    if kind == "note":
        if isinstance(translated.get("x"), (int, float)):
            translated["x"] = float(translated["x"]) + dx
        if isinstance(translated.get("y"), (int, float)):
            translated["y"] = float(translated["y"]) + dy
        return translated
    if kind in ARROW_KINDS:
        translated["start"] = translated_point_value(translated.get("start"), dx, dy)
        translated["end"] = translated_point_value(translated.get("end"), dx, dy)
        translated["control"] = translated_point_value(
            translated.get("control"), dx, dy
        )
        return translated
    if kind == "ts_bracket":
        rect = translated.get("rect")
        if (
            isinstance(rect, (list, tuple))
            and len(rect) == 4
            and all(isinstance(value, (int, float)) for value in rect)
        ):
            translated_rect = [
                float(rect[0]) + dx,
                float(rect[1]) + dy,
                float(rect[2]),
                float(rect[3]),
            ]
            translated["rect"] = (
                tuple(translated_rect) if isinstance(rect, tuple) else translated_rect
            )
            return translated
    if kind in {"ts_bracket", "shape"}:
        for key in ("left", "right"):
            if isinstance(translated.get(key), (int, float)):
                translated[key] = float(translated[key]) + dx
        for key in ("top", "bottom"):
            if isinstance(translated.get(key), (int, float)):
                translated[key] = float(translated[key]) + dy
        return translated
    if kind == "orbital":
        translated["center"] = translated_point_value(translated.get("center"), dx, dy)
        return translated
    return translated


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
    paste_count = (
        previous_paste_count + 1 if payload_json == previous_source_json else 1
    )
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
        perspective=payload.get("perspective"),
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
    "clipboard_paste_offset",
    "translated_point_value",
    "translated_scene_item_state",
    "visible_items_to_hide_for_copy",
]
