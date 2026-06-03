"""Named drawing-style presets (journal / use-case variants of ACS1996Style).

A preset is just an ``ACS1996Style`` instance with different metrics (font,
line widths, physical bond length). The registry is pure data so it can be
unit-tested and reused by both the UI picker and figure export.

Applying a preset keeps the user's on-screen ``bond_length_px`` (their working
zoom) and adopts the rest, so switching presets re-styles line weights, font and
the physical export size without rescaling the drawing on screen.
"""

from __future__ import annotations

from dataclasses import replace

from core.style_acs1996 import ACS1996Style

DEFAULT_PRESET = "ACS 1996"

# Insertion order is the display order.
_PRESETS: dict[str, ACS1996Style] = {
    # ACS 1996 document settings: Arial/Helvetica, ~0.2 in bonds, 0.6 pt lines.
    "ACS 1996": ACS1996Style(),
    # Compact journal style: slightly thinner lines and shorter bonds.
    "Nature / RSC": replace(
        ACS1996Style(),
        font_family="Helvetica",
        bond_line_width=1.3,
        bold_bond_width=2.0,
        bond_length_pt=12.96,  # ~0.18 in
    ),
    # Large, bold style for slides and posters.
    "Presentation": replace(
        ACS1996Style(),
        font_size_pt=16,
        bond_line_width=2.2,
        bold_bond_width=3.2,
        bond_spacing_px=5.2,
        bond_length_pt=21.6,  # ~0.3 in
    ),
}


def preset_names() -> list[str]:
    return list(_PRESETS)


def style_for_preset(name: str) -> ACS1996Style:
    return _PRESETS.get(name, _PRESETS[DEFAULT_PRESET])


def apply_preset_to_current(name: str, current: ACS1996Style) -> ACS1996Style:
    """Return the preset style but keep the current on-screen bond length (zoom)."""
    preset = style_for_preset(name)
    return replace(preset, bond_length_px=current.bond_length_px)


__all__ = [
    "DEFAULT_PRESET",
    "preset_names",
    "style_for_preset",
    "apply_preset_to_current",
]
