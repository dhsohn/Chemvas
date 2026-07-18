from __future__ import annotations

from PyQt6.QtCore import QByteArray, QRectF
from PyQt6.QtGui import QPainter
from PyQt6.QtSvg import QSvgRenderer

from chemvas.ui.main_window_palette import PALETTE

_ICON_COLOR = PALETTE["icon"]

_SVG_BY_NAME: dict[str, str] = {
    "select": '<path d="M14 4 L5 13 L9 13 L8 20 L19 9 L13 9 Z"/>',
    "bond": '<line x1="5" y1="17" x2="19" y2="7"/>',
    "bond_double": '<line x1="4" y1="15" x2="18" y2="5"/><line x1="6" y1="19" x2="20" y2="9"/>',
    "bond_triple": (
        '<line x1="3" y1="14" x2="17" y2="4"/>'
        '<line x1="5" y1="17" x2="19" y2="7"/>'
        '<line x1="7" y1="20" x2="21" y2="10"/>'
    ),
    "wedge": '<path d="M5 18 L18 5 L20 8 Z"/>',
    "hash": (
        '<line x1="6" y1="16.5" x2="7.5" y2="14.5"/>'
        '<line x1="8.5" y1="15.2" x2="10.6" y2="12.4"/>'
        '<line x1="11.2" y1="13.7" x2="13.8" y2="10.3"/>'
        '<line x1="14.4" y1="12" x2="17.4" y2="8"/>'
    ),
    "benzene": (
        '<polygon points="12,3 19.5,7.5 19.5,16.5 12,21 4.5,16.5 4.5,7.5"/>'
        '<circle cx="12" cy="12" r="4.2"/>'
    ),
    "arrow": '<line x1="3" y1="12" x2="20" y2="12"/><polyline points="15,7 20.5,12 15,17"/>',
    "bracket": '<path d="M9 4 H6 V20 H9"/><path d="M15 4 H18 V20 H15"/>',
    "orbital": '<ellipse cx="8" cy="12" rx="5" ry="7"/><ellipse cx="16" cy="12" rx="5" ry="7"/>',
    # Periodic-table silhouette — the "choose a specific element" tool. Filled
    # cells on the 24 box: row 1 corner pair (H/He), row 2 two towers with the
    # central notch, row 3 full row, row 4 left block. Cells run slightly tall
    # (3.0 x 3.7) so the landscape grid fills the icon box and stays legible at
    # the 18 px toolbar size.
    "atom": (
        '<g fill="currentColor" stroke="none">'
        '<rect x="0.3" y="4.0" width="3.0" height="3.7" rx="0.4"/>'
        '<rect x="20.7" y="4.0" width="3.0" height="3.7" rx="0.4"/>'
        '<rect x="0.3" y="8.1" width="3.0" height="3.7" rx="0.4"/>'
        '<rect x="3.7" y="8.1" width="3.0" height="3.7" rx="0.4"/>'
        '<rect x="13.9" y="8.1" width="3.0" height="3.7" rx="0.4"/>'
        '<rect x="17.3" y="8.1" width="3.0" height="3.7" rx="0.4"/>'
        '<rect x="20.7" y="8.1" width="3.0" height="3.7" rx="0.4"/>'
        '<rect x="0.3" y="12.2" width="3.0" height="3.7" rx="0.4"/>'
        '<rect x="3.7" y="12.2" width="3.0" height="3.7" rx="0.4"/>'
        '<rect x="7.1" y="12.2" width="3.0" height="3.7" rx="0.4"/>'
        '<rect x="10.5" y="12.2" width="3.0" height="3.7" rx="0.4"/>'
        '<rect x="13.9" y="12.2" width="3.0" height="3.7" rx="0.4"/>'
        '<rect x="17.3" y="12.2" width="3.0" height="3.7" rx="0.4"/>'
        '<rect x="20.7" y="12.2" width="3.0" height="3.7" rx="0.4"/>'
        '<rect x="0.3" y="16.3" width="3.0" height="3.7" rx="0.4"/>'
        '<rect x="3.7" y="16.3" width="3.0" height="3.7" rx="0.4"/>'
        '<rect x="7.1" y="16.3" width="3.0" height="3.7" rx="0.4"/>'
        '<rect x="10.5" y="16.3" width="3.0" height="3.7" rx="0.4"/>'
        "</g>"
    ),
    "note": (
        '<g transform="translate(12 12) skewX(-14) translate(-12 -12)">'
        '<path d="M5 4 H19 M12 4 V20"/></g>'
    ),
    "font": '<path d="M2.5 18 6 5 9.5 18 M4 13.2 H8"/><circle cx="16.2" cy="14.6" r="3.4"/><path d="M19.6 11.4 V18"/>',
    "text_bold": '<path d="M7.5 5 V19 M7.5 5 H13 C16.5 5 16.5 11.5 13 11.5 H7.5 M7.5 11.5 H14 C17.8 11.5 17.8 19 14 19 H7.5"/><path d="M9.3 5 V19"/>',
    "text_italic": '<path d="M10 5 H17 M7 19 H14 M14.5 5 L9.5 19"/>',
    "text_superscript": '<path d="M5 16.5 11 10 M5 10 11 16.5"/><path d="M14 8.4 C14 6.6 18.6 6.6 18.6 8.9 C18.6 10.8 14 11.1 14 12.6 H18.8"/>',
    "text_subscript": '<path d="M5 7.5 11 14 M5 14 11 7.5"/><path d="M14 13.4 C14 11.6 18.6 11.6 18.6 13.9 C18.6 15.8 14 16.1 14 17.6 H18.8"/>',
    "text_size_increase": '<path d="M3.5 18 7.5 7 11.5 18 M4.8 14.5 H10.2 M16.5 18 V8.5 M13.5 11.5 16.5 8.5 19.5 11.5"/>',
    "text_size_decrease": '<path d="M4.5 18 8 8.5 11.5 18 M5.6 15 H10.4 M16.5 8.5 V18 M13.5 15 16.5 18 19.5 15"/>',
    "align_left": '<path d="M4 6 H20 M4 11 H14 M4 16 H18 M4 21 H12"/>',
    "align_center": '<path d="M4 6 H20 M7 11 H17 M5 16 H19 M8 21 H16"/>',
    "align_right": '<path d="M4 6 H20 M10 11 H20 M6 16 H20 M12 21 H20"/>',
    "atom_orbit": (
        '<circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/>'
        '<ellipse cx="12" cy="12" rx="9.5" ry="4" transform="rotate(45 12 12)"/>'
        '<ellipse cx="12" cy="12" rx="9.5" ry="4" transform="rotate(-45 12 12)"/>'
    ),
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>',
    "redo": '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5A5.5 5.5 0 0 0 4 14.5A5.5 5.5 0 0 0 9.5 20H13"/>',
    "save": (
        '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>'
        '<path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/>'
        '<path d="M7 3v4a1 1 0 0 0 1 1h7"/>'
    ),
    "open": (
        '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>'
    ),
    "panel_right": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M15 3v18"/>',
    "canvas": (
        '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/>'
        '<path d="M14 2v5a1 1 0 0 0 1 1h5"/>'
        '<path d="M9 15h6"/><path d="M12 18v-6"/>'
    ),
    "sheet": (
        '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/>'
        '<path d="M14 2v5a1 1 0 0 0 1 1h5"/>'
    ),
    "flip_h": (
        '<path d="m3 7 5 5-5 5V7"/><path d="m21 7-5 5 5 5V7"/>'
        '<path d="M12 20v2"/><path d="M12 14v2"/><path d="M12 8v2"/><path d="M12 2v2"/>'
    ),
    "flip_v": (
        '<path d="m17 3-5 5-5-5h10"/><path d="m17 21-5-5-5 5h10"/>'
        '<path d="M4 12H2"/><path d="M10 12H8"/><path d="M16 12h-2"/><path d="M22 12h-2"/>'
    ),
    "rotate": (
        '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/>'
        '<path d="M21 3v5h-5"/>'
    ),
    "perspective": (
        '<path d="m15.194 13.707 3.814 1.86-1.86 3.814"/>'
        '<path d="M16.47214 7.52786 A 5 10 0 1 0 13 21.79796"/>'
        '<path d="M21.79796 11 A 10 5 0 1 0 19 15.57071"/>'
    ),
    "color": (
        '<path d="M12 22a1 1 0 0 1 0-20 10 9 0 0 1 10 9 5 5 0 0 1-5 5h-2.25a1.75 1.75 0 0 0-1.4 2.8l.3.4a1.75 1.75 0 0 1-1.4 2.8z"/>'
        '<circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/>'
        '<circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/>'
        '<circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/>'
        '<circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/>'
    ),
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "move": (
        '<path d="M12 2v20"/><path d="m15 19-3 3-3-3"/><path d="m19 9 3 3-3 3"/>'
        '<path d="M2 12h20"/><path d="m5 9-3 3 3 3"/><path d="m9 5 3-3 3 3"/>'
    ),
    "plus": '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "minus": '<line x1="5" y1="12" x2="19" y2="12"/>',
    "radical": '<circle cx="12" cy="12" r="2.5" fill="currentColor" stroke="none"/>',
    "circled_plus": '<circle cx="12" cy="12" r="9"/><path d="M12 7.2v9.6"/><path d="M7.2 12h9.6"/>',
    "circled_minus": '<circle cx="12" cy="12" r="9"/><path d="M7.2 12h9.6"/>',
    "ring_fill": (
        '<polygon points="12,3 20.56,9.22 17.29,19.28 6.71,19.28 3.44,9.22" '
        'fill="#ededeb" stroke-width="2"/>'
    ),
    "templates": '<polygon points="0.04,19.08 3.97,9.35 14.46,9.35 23.96,4.92 20.03,14.65 9.54,14.65"/>',
    "bond_bold": '<line x1="5" y1="17" x2="19" y2="7" stroke-width="3.6"/>',
    "bond_dotted": '<line x1="5" y1="17" x2="19" y2="7" stroke-dasharray="0.1 3.4"/>',
    "bond_length": (
        '<line x1="3" y1="12" x2="21" y2="12"/>'
        '<line x1="3" y1="8" x2="3" y2="16"/>'
        '<line x1="21" y1="8" x2="21" y2="16"/>'
    ),
    # --- Arrow previews ---
    "arrow_reaction": '<line x1="0" y1="12" x2="24" y2="12"/><line x1="19.92" y1="13.9" x2="24" y2="12"/><line x1="19.92" y1="10.1" x2="24" y2="12"/>',
    "arrow_equilibrium": '<line x1="0" y1="7" x2="24" y2="7"/><line x1="19.92" y1="8.9" x2="24" y2="7"/><line x1="19.92" y1="5.1" x2="24" y2="7"/><line x1="24" y1="17" x2="0" y2="17"/><line x1="4.08" y1="15.1" x2="0" y2="17"/><line x1="4.08" y1="18.9" x2="0" y2="17"/>',
    "arrow_resonance": '<line x1="0" y1="12" x2="24" y2="12"/><line x1="19.92" y1="13.9" x2="24" y2="12"/><line x1="19.92" y1="10.1" x2="24" y2="12"/><line x1="4.08" y1="10.1" x2="0" y2="12"/><line x1="4.08" y1="13.9" x2="0" y2="12"/>',
    "arrow_curved_single": '<path d="M1 19 Q12 0 23 12"/><line x1="18.7" y1="10.66" x2="23" y2="12"/><line x1="21.26" y1="7.85" x2="23" y2="12"/>',
    "arrow_curved_double": '<path d="M1 19 Q12 0 23 12"/><line x1="18.7" y1="10.66" x2="23" y2="12"/><line x1="21.26" y1="7.85" x2="23" y2="12"/><line x1="1.62" y1="14.54" x2="1" y2="19"/><line x1="4.81" y1="16.61" x2="1" y2="19"/>',
    "arrow_inhibit": '<line x1="0" y1="12" x2="23" y2="12"/><line x1="23" y1="5" x2="23" y2="19"/>',
    "arrow_dotted": '<line x1="0" y1="12" x2="24" y2="12" stroke-dasharray="3 3"/><line x1="19.92" y1="13.9" x2="24" y2="12"/><line x1="19.92" y1="10.1" x2="24" y2="12"/>',
    # --- Arrow presets ---
    "arrow_preset_default": '<line x1="2" y1="12" x2="21" y2="12" stroke-width="1.8"/><line x1="16.92" y1="13.9" x2="21" y2="12"/><line x1="16.92" y1="10.1" x2="21" y2="12"/>',
    "arrow_preset_bold": '<line x1="2" y1="12" x2="21" y2="12" stroke-width="2.9"/><line x1="16.92" y1="13.9" x2="21" y2="12"/><line x1="16.92" y1="10.1" x2="21" y2="12"/>',
    "arrow_preset_fine": '<line x1="2" y1="12" x2="21" y2="12" stroke-width="1.0"/><line x1="16.92" y1="13.9" x2="21" y2="12"/><line x1="16.92" y1="10.1" x2="21" y2="12"/>',
    # --- Arrow controls ---
    "arrow_width": '<line x1="3" y1="7" x2="21" y2="7" stroke="#8c8c87" stroke-width="1.2"/><line x1="3" y1="16" x2="21" y2="16" stroke-width="2.4"/>',
    "arrow_head_scale": '<line x1="2" y1="12" x2="21" y2="12"/><line x1="16.92" y1="13.9" x2="21" y2="12"/><line x1="16.92" y1="10.1" x2="21" y2="12"/>',
    # --- Orbital previews ---
    "orbital_s": '<circle cx="12" cy="12" r="6"/>',
    "orbital_p": '<circle cx="8" cy="13" r="5"/><circle cx="16" cy="11" r="5"/>',
    "orbital_sp": '<circle cx="8" cy="14" r="5"/><circle cx="18" cy="10" r="5"/><line x1="2" y1="15" x2="22" y2="9"/>',
    "orbital_sp2": '<circle cx="8" cy="8" r="4"/><circle cx="16" cy="8" r="4"/><circle cx="12" cy="16" r="4"/>',
    "orbital_sp3": '<circle cx="8" cy="8" r="4"/><circle cx="16" cy="8" r="4"/><circle cx="12" cy="16" r="4"/><circle cx="12" cy="3" r="4"/>',
    "orbital_d": '<circle cx="7" cy="11" r="4"/><circle cx="17" cy="11" r="4"/><circle cx="12" cy="6" r="4"/><circle cx="12" cy="16" r="4"/>',
    # Phase toggle: a p-orbital dumbbell read as one sign (both lobes hollow)
    # versus two signs (top lobe filled), echoing the +/- lobe colouring.
    "orbital_phase_off": '<circle cx="12" cy="7" r="5"/><circle cx="12" cy="17" r="5"/>',
    "orbital_phase_on": '<circle cx="12" cy="7" r="5" fill="currentColor"/><circle cx="12" cy="17" r="5"/>',
    # --- Shapes (decorative) ---
    "shape": '<rect x="3.5" y="8.5" width="11" height="11" rx="1"/><circle cx="15.5" cy="9" r="5.5"/>',
    "shape_circle": '<circle cx="12" cy="12" r="8"/>',
    "shape_ellipse": '<ellipse cx="12" cy="12" rx="9" ry="6"/>',
    "shape_rounded_rect": '<rect x="3.5" y="6" width="17" height="12" rx="3.5"/>',
    "shape_rect": '<rect x="3.5" y="6" width="17" height="12"/>',
    "stroke_solid": '<line x1="3" y1="12" x2="21" y2="12"/>',
    "stroke_dashed": '<line x1="3" y1="12" x2="21" y2="12" stroke-dasharray="4 3"/>',
    "stroke_dotted": '<line x1="3" y1="12" x2="21" y2="12" stroke-dasharray="0.1 3.4"/>',
    "stroke_none": '<line x1="3" y1="12" x2="21" y2="12" stroke-dasharray="0.1 3.4"/><line x1="19" y1="6" x2="5" y2="18"/>',
    # --- Template previews ---
    "template_benzene": '<polygon points="12.0,2.0 20.66,7.0 20.66,17.0 12.0,22.0 3.34,17.0 3.34,7.0"/><line x1="12.0" y1="4.2" x2="18.75" y2="8.1"/><line x1="18.75" y1="15.9" x2="12.0" y2="19.8"/><line x1="5.25" y1="15.9" x2="5.25" y2="8.1"/>',
    "template_ring3": '<polygon points="12.0,2.0 20.66,17.0 3.34,17.0"/>',
    "template_ring4": '<polygon points="12.0,2.0 22.0,12.0 12.0,22.0 2.0,12.0"/>',
    "template_ring5": '<polygon points="12.0,2.0 21.51,8.91 17.88,20.09 6.12,20.09 2.49,8.91"/>',
    "template_ring6": '<polygon points="12.0,2.0 20.66,7.0 20.66,17.0 12.0,22.0 3.34,17.0 3.34,7.0"/>',
    "template_ring7": '<polygon points="12.0,2.0 19.82,5.77 21.75,14.23 16.34,21.01 7.66,21.01 2.25,14.23 4.18,5.77"/>',
    "template_ring8": '<polygon points="12.0,2.0 19.07,4.93 22.0,12.0 19.07,19.07 12.0,22.0 4.93,19.07 2.0,12.0 4.93,4.93"/>',
    "template_chair": '<polygon points="0.04,19.08 3.97,9.35 14.46,9.35 23.96,4.92 20.03,14.65 9.54,14.65"/>',
    "template_chair_flip": '<polygon points="23.96,19.08 20.03,9.35 9.54,9.35 0.04,4.92 3.97,14.65 14.46,14.65"/>',
    # --- Bracket previews ---
    "bracket_square_pair": '<line x1="5.76" y1="2.5" x2="1.8" y2="2.5"/><line x1="1.8" y1="2.5" x2="1.8" y2="21.5"/><line x1="1.8" y1="21.5" x2="5.76" y2="21.5"/><line x1="18.24" y1="2.5" x2="22.2" y2="2.5"/><line x1="22.2" y1="2.5" x2="22.2" y2="21.5"/><line x1="22.2" y1="21.5" x2="18.24" y2="21.5"/>',
    "bracket_parentheses_pair": '<path d="M9.0 2.5 C1.8 6.68 1.8 7.82 1.8 12.0 C1.8 16.18 1.8 17.32 9.0 21.5"/><path d="M15.0 2.5 C22.2 6.68 22.2 7.82 22.2 12.0 C22.2 16.18 22.2 17.32 15.0 21.5"/>',
    "bracket_braces_pair": '<path d="M9.0 2.5 C1.8 2.5 1.8 5.11 3.1 7.25 C6.26 8.77 6.26 10.34 1.8 12.0 C6.26 13.66 6.26 15.23 3.1 16.75 C1.8 18.89 1.8 21.5 9.0 21.5"/><path d="M15.0 2.5 C22.2 2.5 22.2 5.11 20.9 7.25 C17.74 8.77 17.74 10.34 22.2 12.0 C17.74 13.66 17.74 15.23 20.9 16.75 C22.2 18.89 22.2 21.5 15.0 21.5"/>',
    "bracket_square_left": '<line x1="9.71" y1="2.5" x2="5.2" y2="2.5"/><line x1="5.2" y1="2.5" x2="5.2" y2="21.5"/><line x1="5.2" y1="21.5" x2="9.71" y2="21.5"/>',
    "bracket_parenthesis_left": '<path d="M13.4 2.5 C5.2 6.68 5.2 7.82 5.2 12.0 C5.2 16.18 5.2 17.32 13.4 21.5"/>',
    "bracket_brace_left": '<path d="M13.4 2.5 C5.2 2.5 5.2 5.11 6.68 7.25 C10.28 8.77 10.28 10.34 5.2 12.0 C10.28 13.66 10.28 15.23 6.68 16.75 C5.2 18.89 5.2 21.5 13.4 21.5"/>',
    "bracket_dagger": '<line x1="12" y1="4" x2="12" y2="20"/><line x1="8" y1="8.5" x2="16" y2="8.5"/>',
    "bracket_double_dagger": '<line x1="12" y1="4" x2="12" y2="20"/><line x1="8" y1="7.5" x2="16" y2="7.5"/><line x1="8" y1="16.5" x2="16" y2="16.5"/>',
}


def _svg_document(name: str, color: str) -> str:
    fill = "currentColor" if name == "wedge" else "none"
    width = "1.6" if name == "hash" else "1.8"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="{fill}" stroke="currentColor" stroke-width="{width}" '
        f'stroke-linecap="round" stroke-linejoin="round" color="{color}">'
        f"{_SVG_BY_NAME[name]}</svg>"
    )


DESIGN_ICON_NAMES = frozenset(_SVG_BY_NAME)


def has_design_icon(name: str) -> bool:
    return name in _SVG_BY_NAME


def draw_design_icon(
    painter: QPainter, name: str, *, color: str | None = None, size: float = 30.0
) -> None:
    renderer = QSvgRenderer(
        QByteArray(_svg_document(name, color or _ICON_COLOR).encode("utf-8"))
    )
    # Render the 24-unit viewBox into the central 80% of the target size so the
    # glyph keeps the same 10% padding it has in the default 30px icon canvas.
    pad = size * 0.1
    renderer.render(painter, QRectF(pad, pad, size * 0.8, size * 0.8))


__all__ = ["DESIGN_ICON_NAMES", "draw_design_icon", "has_design_icon"]
