from __future__ import annotations

from ui.main_window_palette import PALETTE

_P = PALETTE

TOOLBAR_THICKNESS = 30
TOOLBAR_BUTTON_SIZE = 22
TOOLBAR_ICON_SIZE = 18
CONTEXT_BAR_CONTENT_HEIGHT = 22
CONTEXT_BAR_BUTTON_HEIGHT = 22
CONTEXT_BAR_ICON_SIZE = 22


def _flat_toolbutton_style(*, extra: str = "") -> str:
    return (
        "QToolButton {"
        " border: 1px solid transparent;"
        " border-radius: 6px;"
        " padding: 2px;"
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
        f" min-width: {TOOLBAR_BUTTON_SIZE - 2}px;"
        f" max-width: {TOOLBAR_BUTTON_SIZE - 2}px;"
        f" min-height: {TOOLBAR_BUTTON_SIZE - 2}px;"
        f" max-height: {TOOLBAR_BUTTON_SIZE - 2}px;"
        "}"
        "QToolBar::separator {"
        " background: transparent;"
        "}"
        "QToolBar::separator:vertical {"
        " width: 10px;"
        " height: 1px;"
        " margin: 0px 3px;"
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
        " padding: 2px 8px;"
        " font-size: 12px;"
        "}"
    )
)

SMILES_RENDER_BUTTON_STYLE = (
    "QToolButton#smiles_render_button {"
    " border: 1px solid transparent;"
    " border-radius: 6px;"
    " padding: 1px 10px;"
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
    "CONTEXT_BAR_BUTTON_HEIGHT",
    "CONTEXT_BAR_CONTENT_HEIGHT",
    "CONTEXT_BAR_ICON_SIZE",
    "LEFT_TOOLBAR_BUTTON_STYLE",
    "SMILES_RENDER_BUTTON_STYLE",
    "TOOLBAR_BUTTON_SIZE",
    "TOOLBAR_BUTTON_STYLE",
    "TOOLBAR_ICON_SIZE",
    "TOOLBAR_MENU_BUTTON_STYLE",
    "TOOLBAR_THICKNESS",
]
