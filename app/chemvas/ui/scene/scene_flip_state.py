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
from chemvas.features.annotations import flip_annotation
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
            if horizontal:
                after_state["x"] = before_state.get("x", 0.0) + 2 * (
                    center.x() - rect.center().x()
                )
                after_state["y"] = before_state.get("y", 0.0)
            else:
                after_state["x"] = before_state.get("x", 0.0)
                after_state["y"] = before_state.get("y", 0.0) + 2 * (
                    center.y() - rect.center().y()
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
        after_state["x"] = flipped.x()
        after_state["y"] = flipped.y()
        atom_id = before_state.get("atom_id")
        if isinstance(atom_id, int):
            atom_position = transformed_atom_positions.get(atom_id)
            if atom_position is None:
                atom = atoms.get(atom_id)
                if atom is not None:
                    atom_position = (atom.x, atom.y)
            if atom_position is not None:
                after_state["dx"] = flipped.x() - atom_position[0]
                after_state["dy"] = flipped.y() - atom_position[1]
        return after_state
    if kind == "orbital":
        center_state = before_state.get("center")
        if center_state is not None:
            flipped = flip_point(QPointF(*center_state), center, horizontal)
            after_state["center"] = (flipped.x(), flipped.y())
        rotation = float(before_state.get("rotation", 0.0))
        after_state["rotation"] = 180.0 - rotation if horizontal else -rotation
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
