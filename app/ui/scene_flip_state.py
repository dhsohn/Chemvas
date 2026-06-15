from __future__ import annotations

from collections.abc import Callable, Mapping

from core.model import Atom
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsItem

from ui.scene_item_state import ARROW_KINDS


def flip_scene_item_state(
    item: QGraphicsItem,
    before_state: dict,
    *,
    center: QPointF,
    horizontal: bool,
    transformed_atom_positions: Mapping[int, tuple[float, float]],
    atoms: Mapping[int, Atom],
    flip_point: Callable[[QPointF, QPointF, bool], QPointF],
    ts_bracket_rect_from_state: Callable[[dict], QRectF | None],
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
    if kind == "note":
        rect = item.sceneBoundingRect()
        if rect.isValid():
            if horizontal:
                after_state["x"] = center.x() - (rect.right() - center.x())
                after_state["y"] = before_state.get("y", 0.0)
            else:
                after_state["x"] = before_state.get("x", 0.0)
                after_state["y"] = center.y() - (rect.bottom() - center.y())
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
    if kind == "ts_bracket":
        bracket_rect = ts_bracket_rect_from_state(before_state)
        if bracket_rect is None:
            return after_state
        flipped_rect = QRectF(
            flip_point(bracket_rect.topLeft(), center, horizontal),
            flip_point(bracket_rect.bottomRight(), center, horizontal),
        ).normalized()
        after_state["left"] = flipped_rect.left()
        after_state["top"] = flipped_rect.top()
        after_state["right"] = flipped_rect.right()
        after_state["bottom"] = flipped_rect.bottom()
        return after_state
    if kind in ARROW_KINDS:
        for key in ("start", "end", "control"):
            point = before_state.get(key)
            if point is None:
                continue
            flipped = flip_point(QPointF(*point), center, horizontal)
            after_state[key] = (flipped.x(), flipped.y())
        return after_state
    return {}


__all__ = ["flip_scene_item_state"]
