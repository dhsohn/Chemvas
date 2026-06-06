from __future__ import annotations

from ui.main_window_palette import PALETTE

_P = PALETTE


def _flat_toolbutton_style(*, extra: str = "") -> str:
    return (
        "QToolButton {"
        " border: 1px solid transparent;"
        " border-radius: 8px;"
        " padding: 4px;"
        f" color: {_P['text']};"
        "}"
        "QToolButton:hover {"
        f" background-color: {_P['hover']};"
        " border-color: transparent;"
        "}"
        "QToolButton:pressed {"
        f" background-color: {_P['pressed']};"
        " border-color: transparent;"
        "}"
        "QToolButton:checked {"
        f" background-color: {_P['checked_bg']};"
        f" border-color: {_P['checked_border']};"
        f" color: {_P['checked_text']};"
        "}"
        "QToolButton:disabled {"
        f" color: {_P['text_faint']};"
        " background: transparent;"
        " border-color: transparent;"
        "}"
        + extra
    )


TOOLBAR_BUTTON_STYLE = _flat_toolbutton_style()

LEFT_TOOLBAR_BUTTON_STYLE = _flat_toolbutton_style(
    extra=(
        "QToolBar {"
        f" background: {_P['surface_bar']};"
        " border: none;"
        f" border-bottom: 1px solid {_P['border']};"
        " spacing: 0px;"
        " padding: 2px 4px;"
        "}"
        "QToolButton {"
        " padding: 0px;"
        " margin: 0px;"
        " border-radius: 6px;"
        " min-width: 24px;"
        " max-width: 24px;"
        " min-height: 24px;"
        " max-height: 24px;"
        "}"
        "QToolBar::separator {"
        " background: transparent;"
        "}"
        "QToolBar::separator:vertical {"
        " width: 14px;"
        " height: 1px;"
        " margin: 0px 5px;"
        "}"
    )
)

TOOLBAR_MENU_BUTTON_STYLE = _flat_toolbutton_style(
    extra=(
        "QToolButton { padding-right: 8px; }"
        "QToolButton::menu-button {"
        " subcontrol-origin: padding;"
        " subcontrol-position: top right;"
        " width: 14px;"
        " border: none;"
        " background: transparent;"
        "}"
        "QToolButton::menu-button:hover { background: transparent; }"
        "QToolButton::menu-button:pressed { background: transparent; }"
        "QToolButton::menu-indicator { image: none; width: 0px; height: 0px; }"
        "QToolButton::menu-arrow { image: none; width: 0px; height: 0px;"
        " border: none; background: transparent; }"
    )
)

# Segmented flat toggle buttons used inside the context options bar.
CONTEXT_SEGMENT_STYLE = _flat_toolbutton_style(
    extra=(
        "QToolButton {"
        " padding: 4px 10px;"
        " font-size: 12px;"
        "}"
    )
)

SMILES_RENDER_BUTTON_STYLE = (
    "QToolButton#smiles_render_button {"
    " border: 1px solid transparent;"
    " border-radius: 8px;"
    " padding: 4px 12px;"
    f" background-color: {_P['accent']};"
    f" color: {_P['accent_contrast']};"
    " font-weight: 600;"
    "}"
    "QToolButton#smiles_render_button:hover {"
    f" background-color: {_P['accent_hover']};"
    "}"
    "QToolButton#smiles_render_button:pressed {"
    f" background-color: {_P['accent_pressed']};"
    "}"
    "QToolButton#smiles_render_button:disabled {"
    f" color: {_P['text_faint']};"
    f" background: {_P['pressed']};"
    " border-color: transparent;"
    "}"
)


__all__ = [
    "CONTEXT_SEGMENT_STYLE",
    "LEFT_TOOLBAR_BUTTON_STYLE",
    "SMILES_RENDER_BUTTON_STYLE",
    "TOOLBAR_BUTTON_STYLE",
    "TOOLBAR_MENU_BUTTON_STYLE",
]
