from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ACS1996Style:
    # Approximate ChemDraw ACS 1996 defaults (screen-friendly units).
    bond_length_px: float = 20.0
    # Physical print bond length in points (1/72"). ACS uses ~0.2 in = 14.4 pt.
    # This is what export uses to size the figure independently of on-screen zoom.
    bond_length_pt: float = 14.4
    bond_line_width: float = 1.5
    bold_bond_width: float = 2.2
    hash_bond_width: float = 1.3
    bond_spacing_px: float = 4.4
    hash_spacing_px: float = 3.0
    wedge_width_px: float = 8.0
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
