from __future__ import annotations

from chemvas.shell.palette import PALETTE

_P = PALETTE

# The two bars share one scale: a 20 px glyph in a 32 px button on the tool
# bar, an 18 px glyph in a 26 px button on the context bar, 4 px between
# buttons and 12 px between groups.
TOOLBAR_THICKNESS = 40
TOOLBAR_BUTTON_SIZE = 32
TOOLBAR_ICON_SIZE = 20
CONTEXT_BAR_CONTENT_HEIGHT = 32
CONTEXT_BAR_BUTTON_HEIGHT = 26
CONTEXT_BAR_ICON_SIZE = 18


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
        'QToolButton[iconOnly="true"] { padding: 0px; }'
        'QToolButton[primaryTool="true"] { padding: 0px; }'
        "QToolButton:hover {"
        f" background-color: {_P['hover']};"
        " border-color: transparent;"
        "}"
        "QToolButton:pressed {"
        f" background-color: {_P['pressed']};"
        " border-color: transparent;"
        "}"
        # The active tool is a tinted pill, no outline: an outline reads
        # heavier than the line icons it sits around.
        "QToolButton:checked {"
        f" background-color: {_P['checked_bg']};"
        " border-color: transparent;"
        f" color: {_P['checked_text']};"
        "}"
        "QToolButton:disabled {"
        f" color: {_P['text_faint']};"
        " background: transparent;"
        " border-color: transparent;"
        "}" + extra
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

# Outlined action button used inside the context options bar (e.g. Apply).
CONTEXT_ACTION_BUTTON_STYLE = (
    "QToolButton {"
    f" border: 1px solid {_P['border_strong']};"
    " border-radius: 6px;"
    " padding: 0px 12px;"
    f" background-color: {_P['surface_input']};"
    f" color: {_P['text']};"
    " font-size: 13px;"
    " font-weight: 500;"
    "}"
    "QToolButton:hover {"
    f" background-color: {_P['hover']};"
    f" border-color: {_P['accent']};"
    "}"
    "QToolButton:pressed {"
    f" background-color: {_P['pressed']};"
    f" border-color: {_P['accent']};"
    "}"
    "QToolButton:disabled {"
    f" color: {_P['text_faint']};"
    f" border-color: {_P['border_strong']};"
    "}"
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
    "CONTEXT_ACTION_BUTTON_STYLE",
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
