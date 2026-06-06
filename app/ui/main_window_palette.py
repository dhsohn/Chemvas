from __future__ import annotations

# Light palette with a teal accent. Kept as a single source of truth so the
# whole app stays visually consistent; a future dark theme can swap these values.
# Neutrals stay warm-gray; the accent ramp carries every "active/primary" cue
# (selected tool, focus ring, primary button, selection highlight).
PALETTE = {
    "surface_app": "#f1f1f0",
    "surface_bar": "#fbfbfa",
    "surface_context": "#f4f4f3",
    "surface_panel": "#fbfbfa",
    "surface_canvas": "#ffffff",
    "surface_input": "#ffffff",
    "border": "#e4e4e1",
    "border_strong": "#cfcfca",
    "text": "#232322",
    "text_muted": "#6f6f6c",
    "text_faint": "#9b9b96",
    "hover": "#ededeb",
    "pressed": "#e2e2df",
    "scrollbar": "#cfcfc9",
    "scrollbar_hover": "#a6a6a0",
    # Teal accent ramp.
    "accent": "#0d9488",
    "accent_hover": "#0f766e",
    "accent_pressed": "#115e59",
    "accent_contrast": "#ffffff",
    # Active/checked controls read as a soft teal, no longer flat gray.
    "checked_bg": "#d6ece7",
    "checked_border": "#5fb3a6",
    "checked_text": "#0b5750",
}


__all__ = ["PALETTE"]
