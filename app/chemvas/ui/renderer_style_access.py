from __future__ import annotations

from typing import Any


def renderer_for(canvas: Any):
    return canvas.renderer


def renderer_style_for(canvas: Any):
    return renderer_for(canvas).style


def bond_pen_for(canvas: Any):
    return renderer_for(canvas).bond_pen()


def bold_bond_pen_for(canvas: Any):
    return renderer_for(canvas).bold_bond_pen()


def dotted_bond_pen_for(canvas: Any):
    return renderer_for(canvas).dotted_bond_pen()


def atom_font_for(canvas: Any):
    return renderer_for(canvas).atom_font()


def ring_fill_brush_for(canvas: Any):
    return renderer_for(canvas).ring_fill_brush()


def renderer_bond_line_width_for(canvas: Any) -> float:
    return renderer_for(canvas).bond_line_width()


def renderer_bold_bond_width_for(canvas: Any) -> float:
    return renderer_for(canvas).bold_bond_width()


def renderer_bond_spacing_for(canvas: Any) -> float:
    return renderer_for(canvas).bond_spacing()


def renderer_hash_spacing_for(canvas: Any) -> float:
    return renderer_for(canvas).hash_spacing()


def set_bond_length_for(canvas: Any, length_px: float) -> None:
    renderer_for(canvas).set_bond_length(length_px)


def bond_length_px_for(canvas: Any) -> float:
    return renderer_style_for(canvas).bond_length_px


def bond_line_width_for(canvas: Any) -> float:
    return renderer_style_for(canvas).bond_line_width


def bond_spacing_px_for(canvas: Any) -> float:
    return renderer_style_for(canvas).bond_spacing_px


def bold_bond_width_for(canvas: Any) -> float:
    return renderer_style_for(canvas).bold_bond_width


def hash_spacing_px_for(canvas: Any) -> float:
    return renderer_style_for(canvas).hash_spacing_px


def atom_color_for(canvas: Any) -> str:
    return renderer_style_for(canvas).atom_color


def atom_label_offset_px_for(canvas: Any) -> float:
    return renderer_style_for(canvas).atom_label_offset_px


def bond_color_for(canvas: Any) -> str:
    return renderer_style_for(canvas).bond_color


def bond_length_pt_for(canvas: Any) -> float:
    return renderer_style_for(canvas).bond_length_pt


def font_family_for(canvas: Any) -> str:
    return renderer_style_for(canvas).font_family


def font_size_pt_for(canvas: Any) -> int:
    return renderer_style_for(canvas).font_size_pt


def orbital_positive_color_for(canvas: Any) -> str:
    return renderer_style_for(canvas).orbital_positive_color


def orbital_negative_color_for(canvas: Any) -> str:
    return renderer_style_for(canvas).orbital_negative_color


def orbital_alpha_for(canvas: Any) -> float:
    return renderer_style_for(canvas).orbital_alpha


__all__ = [
    "atom_color_for",
    "atom_font_for",
    "atom_label_offset_px_for",
    "bold_bond_pen_for",
    "bold_bond_width_for",
    "bond_color_for",
    "bond_length_pt_for",
    "bond_length_px_for",
    "bond_line_width_for",
    "bond_pen_for",
    "bond_spacing_px_for",
    "dotted_bond_pen_for",
    "font_family_for",
    "font_size_pt_for",
    "hash_spacing_px_for",
    "orbital_alpha_for",
    "orbital_negative_color_for",
    "orbital_positive_color_for",
    "renderer_bold_bond_width_for",
    "renderer_bond_line_width_for",
    "renderer_bond_spacing_for",
    "renderer_for",
    "renderer_hash_spacing_for",
    "renderer_style_for",
    "ring_fill_brush_for",
    "set_bond_length_for",
]
