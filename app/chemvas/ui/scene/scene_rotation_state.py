from __future__ import annotations

import math
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
from chemvas.features.annotations import rotate_annotation
from chemvas.ui.annotations.state import ARROW_KINDS

if TYPE_CHECKING:
    from collections.abc import Mapping

    from PyQt6.QtWidgets import QGraphicsItem

    from chemvas.domain.document import Atom


def rotated_point(point: QPointF, center: QPointF, angle_radians: float) -> QPointF:
    cos_a = math.cos(angle_radians)
    sin_a = math.sin(angle_radians)
    dx = point.x() - center.x()
    dy = point.y() - center.y()
    return QPointF(
        center.x() + dx * cos_a - dy * sin_a,
        center.y() + dx * sin_a + dy * cos_a,
    )


def rotate_scene_item_state(
    item: QGraphicsItem,
    before_state: dict,
    *,
    center: QPointF,
    angle_degrees: float,
    transformed_atom_positions: Mapping[int, tuple[float, float]],
    atoms: Mapping[int, Atom],
) -> dict:
    if not before_state:
        return {}
    angle_radians = math.radians(angle_degrees)
    kind = before_state.get("kind")
    after_state = dict(before_state)
    if kind == "ring":
        after_state["points"] = [
            (rotated.x(), rotated.y())
            for rotated in (
                rotated_point(QPointF(x, y), center, angle_radians)
                for x, y in before_state.get("points", [])
            )
        ]
        return after_state
    if kind == "note":
        anchor = rotated_point(
            QPointF(before_state.get("x", 0.0), before_state.get("y", 0.0)),
            center,
            angle_radians,
        )
        after_state["x"] = anchor.x()
        after_state["y"] = anchor.y()
        after_state["rotation"] = (
            float(before_state.get("rotation", 0.0)) + angle_degrees
        ) % 360.0
        return after_state
    if kind == "image":
        rect = item.boundingRect()
        if rect.isValid():
            # Image pixels stay upright: orbit the block's center around the
            # pivot and carry the anchor along by the same offset. Use the captured
            # anchor, not the live scene center left by a previous preview frame.
            before_center = rect.center() + QPointF(
                before_state.get("x", 0.0), before_state.get("y", 0.0)
            )
            rotated_center = rotated_point(before_center, center, angle_radians)
            after_state["x"] = (
                before_state.get("x", 0.0) + rotated_center.x() - before_center.x()
            )
            after_state["y"] = (
                before_state.get("y", 0.0) + rotated_center.y() - before_center.y()
            )
        else:
            rotated = rotated_point(
                QPointF(before_state.get("x", 0.0), before_state.get("y", 0.0)),
                center,
                angle_radians,
            )
            after_state["x"] = rotated.x()
            after_state["y"] = rotated.y()
        return after_state
    if kind == "mark":
        rotated = rotated_point(
            QPointF(before_state.get("x", 0.0), before_state.get("y", 0.0)),
            center,
            angle_radians,
        )
        after_state["x"] = rotated.x()
        after_state["y"] = rotated.y()
        atom_id = before_state.get("atom_id")
        if isinstance(atom_id, int):
            atom_position = transformed_atom_positions.get(atom_id)
            if atom_position is None:
                atom = atoms.get(atom_id)
                if atom is not None:
                    atom_position = (atom.x, atom.y)
            if atom_position is not None:
                after_state["dx"] = rotated.x() - atom_position[0]
                after_state["dy"] = rotated.y() - atom_position[1]
        return after_state
    if kind == "orbital":
        center_state = before_state.get("center")
        if center_state is not None:
            rotated = rotated_point(QPointF(*center_state), center, angle_radians)
            after_state["center"] = (rotated.x(), rotated.y())
        after_state["rotation"] = (
            float(before_state.get("rotation", 0.0)) + angle_degrees
        ) % 360.0
        return after_state
    if kind == "shape":
        return shape_to_state(
            rotate_annotation(
                shape_from_state(before_state),
                center=(center.x(), center.y()),
                angle_degrees=angle_degrees,
            )
        )
    if kind == "ts_bracket":
        return ts_bracket_to_state(
            rotate_annotation(
                ts_bracket_from_state(before_state),
                center=(center.x(), center.y()),
                angle_degrees=angle_degrees,
            )
        )
    if kind in ARROW_KINDS:
        return arrow_to_state(
            rotate_annotation(
                arrow_from_state(before_state),
                center=(center.x(), center.y()),
                angle_degrees=angle_degrees,
            )
        )
    return {}


__all__ = ["rotate_scene_item_state", "rotated_point"]
