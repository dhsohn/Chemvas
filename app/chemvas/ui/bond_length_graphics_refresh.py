from __future__ import annotations

import inspect

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QFont, QPen

from chemvas.ui.atom_label_access import (
    atom_label_service,
    uses_compact_label_hit_shape_for,
)
from chemvas.ui.bond_renderer_access import update_bond_geometry_for
from chemvas.ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from chemvas.ui.canvas_bond_graphics_state import bond_items_for, bond_items_for_id
from chemvas.ui.canvas_model_access import atoms_for, bonds_for
from chemvas.ui.graphics_items import AtomDotItem, AtomLabelItem
from chemvas.ui.pick_radius_access import atom_pick_radius_for
from chemvas.ui.renderer_style_access import (
    atom_font_for,
    atom_label_offset_px_for,
    bond_length_px_for,
    bond_line_width_for,
    renderer_bond_line_width_for,
)
from chemvas.ui.selection_service_access import refresh_selection_outline_for

_MISSING_GRAPHICS_PORT = object()


def _optional_graphics_callable(item, name: str):
    try:
        port = getattr(item, name)
    except AttributeError:
        if (
            inspect.getattr_static(item, name, _MISSING_GRAPHICS_PORT)
            is not _MISSING_GRAPHICS_PORT
        ):
            raise
        return None
    return port if callable(port) else None


def _require_graphics_value(
    actual: object,
    expected: object,
    *,
    description: str,
) -> None:
    try:
        matches = bool(actual == expected)
    except BaseException:
        matches = False
    if not matches:
        raise RuntimeError(f"{description} setter did not apply the requested value")


def _expected_label_position(canvas, label: AtomLabelItem, atom) -> QPointF:
    anchor_center = _optional_graphics_callable(label, "anchor_center")
    center = anchor_center() if anchor_center is not None else None
    if center is None:
        bounding_rect = _optional_graphics_callable(label, "boundingRect")
        if bounding_rect is None:
            raise RuntimeError("atom label has no bounding-rect getter")
        center = bounding_rect().center()
    offset = atom_label_offset_px_for(canvas)
    return QPointF(
        atom.x - center.x() + offset,
        atom.y - center.y() - offset,
    )


def _refresh_atom_graphics(canvas) -> None:
    labels = atom_items_for(canvas)
    dots = atom_dots_for(canvas)
    if not labels and not dots:
        return
    label_service = atom_label_service(canvas) if labels else None
    font = atom_font_for(canvas)
    label_hit_padding = bond_length_px_for(canvas) * 0.12
    pick_radius = atom_pick_radius_for(canvas)
    dot_radius = max(0.6, bond_line_width_for(canvas) * 0.6)

    for atom_id, atom in atoms_for(canvas).items():
        label = labels.get(atom_id)
        if label is not None:
            if isinstance(label, AtomLabelItem):
                hit_padding_setter = _optional_graphics_callable(
                    label,
                    "set_hit_padding",
                )
                hit_radius_setter = _optional_graphics_callable(
                    label,
                    "set_hit_radius",
                )
                if hit_padding_setter is None or hit_radius_setter is None:
                    raise RuntimeError("atom label has incomplete hit-shape setters")
                hit_radius = (
                    pick_radius
                    if uses_compact_label_hit_shape_for(canvas, atom.element)
                    else None
                )
                hit_padding_setter(label_hit_padding)
                _require_graphics_value(
                    object.__getattribute__(label, "_hit_padding"),
                    max(0.0, float(label_hit_padding)),
                    description="atom-label hit padding",
                )
                hit_radius_setter(hit_radius)
                expected_hit_radius = (
                    None if hit_radius is None else max(0.0, float(hit_radius))
                )
                _require_graphics_value(
                    object.__getattribute__(label, "_hit_radius"),
                    expected_hit_radius,
                    description="atom-label hit radius",
                )
            font_getter = _optional_graphics_callable(label, "font")
            font_setter = _optional_graphics_callable(label, "setFont")
            if font_getter is None or font_setter is None:
                raise RuntimeError("atom label has incomplete font ports")
            expected_font = QFont(font)
            font_setter(expected_font)
            _require_graphics_value(
                font_getter(),
                expected_font,
                description="atom-label font",
            )
            if label_service is not None:
                expected_position = _expected_label_position(canvas, label, atom)
                label_service.position_label(label, atom.x, atom.y)
                position_getter = _optional_graphics_callable(label, "pos")
                if position_getter is None:
                    raise RuntimeError("atom label has no position getter")
                _require_graphics_value(
                    position_getter(),
                    expected_position,
                    description="atom-label position",
                )

        dot = dots.get(atom_id)
        if isinstance(dot, AtomDotItem):
            rect_getter = _optional_graphics_callable(dot, "rect")
            rect_setter = _optional_graphics_callable(dot, "setRect")
            hit_padding_setter = _optional_graphics_callable(
                dot,
                "set_hit_padding",
            )
            position_getter = _optional_graphics_callable(dot, "pos")
            position_setter = _optional_graphics_callable(dot, "setPos")
            if any(
                port is None
                for port in (
                    rect_getter,
                    rect_setter,
                    hit_padding_setter,
                    position_getter,
                    position_setter,
                )
            ):
                raise RuntimeError("atom dot has incomplete geometry ports")
            assert rect_getter is not None
            assert rect_setter is not None
            assert hit_padding_setter is not None
            assert position_getter is not None
            assert position_setter is not None
            expected_rect = QRectF(
                -dot_radius,
                -dot_radius,
                dot_radius * 2.0,
                dot_radius * 2.0,
            )
            rect_setter(expected_rect)
            _require_graphics_value(
                rect_getter(),
                expected_rect,
                description="atom-dot rect",
            )
            expected_hit_padding = max(0.0, pick_radius - dot_radius)
            hit_padding_setter(expected_hit_padding)
            _require_graphics_value(
                object.__getattribute__(dot, "_hit_padding"),
                expected_hit_padding,
                description="atom-dot hit padding",
            )
            expected_position = QPointF(atom.x, atom.y)
            position_setter(expected_position)
            _require_graphics_value(
                position_getter(),
                expected_position,
                description="atom-dot position",
            )


def _refresh_bond_graphics(canvas) -> None:
    if not bond_items_for(canvas):
        return
    line_width = renderer_bond_line_width_for(canvas)
    for bond_id, bond in enumerate(bonds_for(canvas)):
        if bond is None:
            continue
        items = bond_items_for_id(canvas, bond_id)
        for item in items:
            # Read each optional port once. A property that exists but raises
            # AttributeError is a live failure, not an absent styling API.
            pen_getter = _optional_graphics_callable(item, "pen")
            pen_setter = _optional_graphics_callable(item, "setPen")
            if pen_getter is None or pen_setter is None:
                continue
            pen = pen_getter()
            if not isinstance(pen, QPen):
                raise RuntimeError("bond graphics pen getter returned an invalid value")
            if pen.style() == Qt.PenStyle.NoPen:
                continue
            expected_pen = QPen(pen)
            expected_pen.setWidthF(line_width)
            pen_setter(expected_pen)
            actual_pen = pen_getter()
            if not isinstance(actual_pen, QPen):
                raise RuntimeError("bond graphics pen getter returned an invalid value")
            _require_graphics_value(
                actual_pen,
                expected_pen,
                description="bond graphics pen",
            )
        update_bond_geometry_for(canvas, bond_id)


def refresh_bond_length_graphics_for(canvas) -> None:
    """Restyle model graphics after a bond-length change without replacing them."""

    _refresh_atom_graphics(canvas)
    _refresh_bond_graphics(canvas)
    refresh_selection_outline_for(canvas)


__all__ = ["refresh_bond_length_graphics_for"]
