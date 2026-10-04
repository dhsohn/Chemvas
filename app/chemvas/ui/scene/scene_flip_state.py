from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from chemvas.domain.document import (
    arrow_from_state,
    arrow_to_state,
    shape_from_state,
    shape_to_state,
    ts_bracket_from_state,
    ts_bracket_to_state,
)
from chemvas.domain.document.marks import mark_state_at_position
from chemvas.domain.document.orbitals import Orbital
from chemvas.features.annotations import flip_annotation, mirrored_box_position
from chemvas.ui.annotations.state import ARROW_KINDS

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from PyQt6.QtWidgets import QGraphicsItem

    from chemvas.domain.document import Atom


def flip_scene_item_state(
    item: QGraphicsItem,
    before_state: dict,
    *,
    center: QPointF,
    horizontal: bool,
    transformed_atom_positions: Mapping[int, tuple[float, float]],
    atoms: Mapping[int, Atom],
    flip_point: Callable[[QPointF, QPointF, bool], QPointF],
) -> dict:
    if not before_state:
        return {}
    kind = before_state.get("kind")
    after_state = dict(before_state)
    if kind == "ring":
        after_state["points"] = [
            (flipped.x(), flipped.y())
            for flipped in (
                flip_point(QPointF(x, y), center, horizontal)
                for x, y in before_state.get("points", [])
            )
        ]
        return after_state
    if kind in {"note", "image"}:
        rect = item.sceneBoundingRect()
        if rect.isValid():
            after_state["x"], after_state["y"] = mirrored_box_position(
                (before_state.get("x", 0.0), before_state.get("y", 0.0)),
                (rect.x(), rect.y(), rect.width(), rect.height()),
                center=(center.x(), center.y()),
                horizontal=horizontal,
            )
        else:
            flipped = flip_point(
                QPointF(before_state.get("x", 0.0), before_state.get("y", 0.0)),
                center,
                horizontal,
            )
            after_state["x"] = flipped.x()
            after_state["y"] = flipped.y()
        return after_state
    if kind == "mark":
        flipped = flip_point(
            QPointF(before_state.get("x", 0.0), before_state.get("y", 0.0)),
            center,
            horizontal,
        )
        return mark_state_at_position(
            before_state,
            (flipped.x(), flipped.y()),
            transformed_atom_positions=transformed_atom_positions,
            atoms=atoms,
        )
    if kind == "orbital":
        center_state = before_state.get("center")
        orbital = flip_annotation(
            Orbital(
                kind=str(before_state.get("orbital_kind", "s")),
                center=center_state if center_state is not None else (0.0, 0.0),
                rotation=float(before_state.get("rotation", 0.0)),
            ),
            center=(center.x(), center.y()),
            horizontal=horizontal,
        )
        if center_state is not None:
            after_state["center"] = orbital.center
        after_state["rotation"] = orbital.rotation
        return after_state
    if kind == "shape":
        return shape_to_state(
            flip_annotation(
                shape_from_state(before_state),
                center=(center.x(), center.y()),
                horizontal=horizontal,
            )
        )
    if kind == "ts_bracket":
        return ts_bracket_to_state(
            flip_annotation(
                ts_bracket_from_state(before_state),
                center=(center.x(), center.y()),
                horizontal=horizontal,
            )
        )
    if kind in ARROW_KINDS:
        return arrow_to_state(
            flip_annotation(
                arrow_from_state(before_state),
                center=(center.x(), center.y()),
                horizontal=horizontal,
            )
        )
    return {}


__all__ = ["flip_scene_item_state"]
