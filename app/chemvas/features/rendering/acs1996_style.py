from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, kw_only=True)
class ACS1996Style:
    """Approximate ChemDraw ACS 1996 defaults in screen-friendly units."""

    bond_length_px: float = 20.0
    # Physical print bond length in points (1/72"). ACS uses ~0.2 in = 14.4 pt.
    # This is what export uses to size the figure independently of on-screen zoom.
    bond_length_pt: float = 14.4
    bond_line_width: float = 1.5
    # Effective drawn width of bold bonds. Both the canvas renderer and the
    # bond preview consume this value as-is — keep any emphasis factor folded
    # in here rather than multiplying at the call sites.
    bold_bond_width: float = 3.3
    bond_spacing_px: float = 4.4
    hash_spacing_px: float = 3.0
    atom_label_offset_px: float = 0.0
    font_family: str = "Arial"
    font_size_pt: int = 12
    atom_color: str = "#000000"
    bond_color: str = "#000000"
    ring_fill_color: str = "#f4d06f"
    ring_fill_alpha: float = 0.0
    orbital_positive_color: str = "#2f6ed3"
    orbital_negative_color: str = "#d84a3a"
    orbital_alpha: float = 0.25


class RenderMetrics:
    """Existing desktop metric calculations, shared by rendering adapters."""

    BASE_BOND_LENGTH_PX = 20.0

    def __init__(self, style: ACS1996Style | None = None) -> None:
        self.style = style or ACS1996Style()

    def set_bond_length(self, length_px: float) -> None:
        self.style = replace(self.style, bond_length_px=length_px)

    def metric_scale(self) -> float:
        if self.style.bond_length_px <= 0:
            return 1.0
        return self.style.bond_length_px / self.BASE_BOND_LENGTH_PX

    def scaled_style_metric(self, value: float) -> float:
        return value * self.metric_scale()

    def bond_line_width(self) -> float:
        return self.scaled_style_metric(self.style.bond_line_width)

    def bold_bond_width(self) -> float:
        return self.scaled_style_metric(self.style.bold_bond_width)

    def bond_spacing(self) -> float:
        return self.scaled_style_metric(self.style.bond_spacing_px)

    def hash_spacing(self) -> float:
        return self.scaled_style_metric(self.style.hash_spacing_px)

    def atom_font_size_pt(self) -> int:
        return max(1, round(self.scaled_style_metric(float(self.style.font_size_pt))))
