from __future__ import annotations

import math
from collections.abc import Callable, Mapping

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsItem

from chemvas.domain.document import Atom
from chemvas.ui.scene_item_state import ARROW_KINDS


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
    ts_bracket_rect_from_state: Callable[[dict], QRectF | None],
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
        rect = item.sceneBoundingRect()
        if rect.isValid():
            # Notes stay upright: orbit the text block's center around the
            # pivot and carry the anchor along by the same offset.
            rotated_center = rotated_point(rect.center(), center, angle_radians)
            after_state["x"] = (
                before_state.get("x", 0.0) + rotated_center.x() - rect.center().x()
            )
            after_state["y"] = (
                before_state.get("y", 0.0) + rotated_center.y() - rect.center().y()
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
    if kind in {"ts_bracket", "shape"}:
        state_rect = ts_bracket_rect_from_state(before_state)
        if state_rect is None:
            return after_state
        # Brackets and shapes stay axis-aligned: orbit the rect around the
        # pivot without changing its size.
        rotated_rect = QRectF(state_rect)
        rotated_rect.moveCenter(
            rotated_point(state_rect.center(), center, angle_radians)
        )
        after_state["left"] = rotated_rect.left()
        after_state["top"] = rotated_rect.top()
        after_state["right"] = rotated_rect.right()
        after_state["bottom"] = rotated_rect.bottom()
        return after_state
    if kind in ARROW_KINDS:
        for key in ("start", "end", "control"):
            point = before_state.get(key)
            if point is None:
                continue
            rotated = rotated_point(QPointF(*point), center, angle_radians)
            after_state[key] = (rotated.x(), rotated.y())
        return after_state
    return {}


__all__ = ["rotate_scene_item_state", "rotated_point"]
