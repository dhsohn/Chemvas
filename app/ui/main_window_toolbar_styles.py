from __future__ import annotations

from ui.main_window_palette import PALETTE

_P = PALETTE

TOOLBAR_THICKNESS = 38
TOOLBAR_BUTTON_SIZE = 30
TOOLBAR_ICON_SIZE = 18
CONTEXT_BAR_CONTENT_HEIGHT = 30
CONTEXT_BAR_BUTTON_HEIGHT = 24
CONTEXT_BAR_ICON_SIZE = 16


def _flat_toolbutton_style(*, extra: str = "") -> str:
    return (
        "QToolButton {"
        " border: 1px solid transparent;"
        " border-radius: 6px;"
        " padding: 0px 9px;"
        f" color: {_P['text']};"
        " font-size: 13px;"
        " font-weight: 500;"
        "}"
        "QToolButton[iconOnly=\"true\"] { padding: 0px; }"
        "QToolButton[primaryTool=\"true\"] { padding: 0px; }"
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
        " padding: 0px 10px;"
        " font-size: 13px;"
        "}"
    )
)

SMILES_RENDER_BUTTON_STYLE = (
    "QToolButton#smiles_render_button {"
    " border: 1px solid transparent;"
    " border-radius: 6px;"
    " padding: 0px 14px;"
    f" background-color: {_P['accent_hover']};"
    f" color: {_P['accent_contrast']};"
    " font-weight: 500;"
    "}"
    "QToolButton#smiles_render_button:hover {"
    f" background-color: {_P['accent_pressed']};"
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
    "CONTEXT_BAR_BUTTON_HEIGHT",
    "CONTEXT_BAR_CONTENT_HEIGHT",
    "CONTEXT_BAR_ICON_SIZE",
    "SMILES_RENDER_BUTTON_STYLE",
    "TOOLBAR_BUTTON_SIZE",
    "TOOLBAR_BUTTON_STYLE",
    "TOOLBAR_ICON_SIZE",
    "TOOLBAR_MENU_BUTTON_STYLE",
    "TOOLBAR_THICKNESS",
]
