from __future__ import annotations


# Monochrome light palette. Kept as a single source of truth so the whole app
# stays visually consistent; a future dark theme can swap these values.
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
    "checked_bg": "#dcdcd8",
    "checked_border": "#a8a8a2",
    "checked_text": "#141413",
    "accent": "#3a3a37",
    "scrollbar": "#cfcfc9",
    "scrollbar_hover": "#a6a6a0",
}

_P = PALETTE


MAIN_WINDOW_STYLESHEET = f"""
            QMainWindow {{
                background: {_P["surface_app"]};
            }}
            QToolBar {{
                background: {_P["surface_bar"]};
                border: none;
                border-bottom: 1px solid {_P["border"]};
                spacing: 4px;
                padding: 5px 6px;
            }}
            QToolBar#contextOptionsBar {{
                background: {_P["surface_context"]};
                border-bottom: 1px solid {_P["border"]};
                padding: 3px 8px;
            }}
            QToolBar::separator {{
                background: {_P["border"]};
            }}
            QToolBar::separator:horizontal {{
                width: 1px;
                height: 18px;
                margin: 4px 8px;
            }}
            QToolBar::separator:vertical {{
                width: 20px;
                height: 1px;
                margin: 7px 6px;
            }}
            QToolBar QLabel#toolbarSectionLabel {{
                background: transparent;
                border: none;
                color: {_P["text_faint"]};
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.6px;
                margin: 0 2px;
                padding: 2px 4px;
                text-transform: uppercase;
            }}
            QToolButton {{
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 5px;
                color: {_P["text"]};
            }}
            QToolButton:hover {{
                background: {_P["hover"]};
                border-color: transparent;
            }}
            QToolButton:pressed {{
                background: {_P["pressed"]};
                border-color: transparent;
            }}
            QToolButton:checked {{
                background: {_P["checked_bg"]};
                border-color: {_P["checked_border"]};
                color: {_P["checked_text"]};
            }}
            QToolButton:disabled {{
                color: {_P["text_faint"]};
                background: transparent;
                border-color: transparent;
            }}
            QLabel, QCheckBox, QGroupBox, QTabBar, QDockWidget, QToolButton {{
                color: {_P["text"]};
            }}
            QDockWidget {{
                background: {_P["surface_panel"]};
                border: 1px solid {_P["border"]};
            }}
            QTabWidget::pane {{
                border: 1px solid {_P["border"]};
                background: {_P["surface_panel"]};
            }}
            QTabBar::tab {{
                background: {_P["surface_app"]};
                padding: 6px 10px;
                border: 1px solid {_P["border"]};
                border-bottom: none;
                margin-right: 2px;
                color: {_P["text"]};
            }}
            QTabBar::tab:selected {{
                background: {_P["surface_canvas"]};
            }}
            QTabWidget#canvasTabs {{
                background: {_P["surface_app"]};
            }}
            QTabWidget#canvasTabs::tab-bar {{
                alignment: left;
                left: 8px;
            }}
            QTabWidget#canvasTabs::pane {{
                border: 1px solid {_P["border"]};
                background: {_P["surface_canvas"]};
            }}
            QTabWidget#canvasTabs QTabBar {{
                background: {_P["surface_app"]};
                padding: 2px 6px 0 6px;
            }}
            QTabWidget#canvasTabs QTabBar::tab {{
                background: transparent;
                color: {_P["text_muted"]};
                border: 1px solid transparent;
                border-top: 2px solid transparent;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
                padding: 4px 14px 5px 14px;
                margin: 0 2px 0 0;
            }}
            QTabWidget#canvasTabs QTabBar::tab:last {{
                padding: 4px 8px 5px 8px;
                min-width: 20px;
            }}
            QTabWidget#canvasTabs QTabBar::tab:hover:!selected {{
                background: {_P["hover"]};
            }}
            QTabWidget#canvasTabs QTabBar::tab:selected {{
                background: {_P["surface_canvas"]};
                color: {_P["text"]};
                border-color: {_P["border"]};
                border-top-color: {_P["accent"]};
            }}
            QTabWidget#canvasTabs QTabBar QToolButton {{
                background: transparent;
                border: none;
                border-radius: 5px;
                color: {_P["text_muted"]};
                padding: 4px 6px;
            }}
            QTabWidget#canvasTabs QTabBar QToolButton:hover {{
                background: {_P["hover"]};
            }}
            QTabWidget#canvasTabs QToolButton#sheetAddButton {{
                background: transparent;
                border: 1px solid transparent;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
                color: {_P["text_muted"]};
                font-size: 18px;
                font-weight: 500;
                margin: 0 4px 0 0;
                min-width: 26px;
                padding: 1px 6px 5px 6px;
            }}
            QTabWidget#canvasTabs QToolButton#sheetAddButton:hover {{
                background: {_P["hover"]};
                border-color: {_P["border"]};
            }}
            QTabWidget#canvasTabs QToolButton#sheetAddButton:pressed {{
                background: {_P["pressed"]};
            }}
            QScrollBar:horizontal {{
                background: {_P["surface_app"]};
                height: 10px;
                margin: 0;
                border-top: 1px solid {_P["border"]};
            }}
            QScrollBar::handle:horizontal {{
                background: {_P["scrollbar"]};
                border: 2px solid {_P["surface_app"]};
                border-radius: 5px;
                min-width: 36px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {_P["scrollbar_hover"]};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                background: transparent;
                border: none;
                width: 0px;
                subcontrol-origin: margin;
            }}
            QScrollBar::sub-line:horizontal {{
                subcontrol-position: left;
            }}
            QScrollBar::add-line:horizontal {{
                subcontrol-position: right;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: {_P["surface_app"]};
            }}
            QScrollBar:vertical {{
                background: {_P["surface_app"]};
                width: 10px;
                margin: 0;
                border-left: 1px solid {_P["border"]};
            }}
            QScrollBar::handle:vertical {{
                background: {_P["scrollbar"]};
                border: 2px solid {_P["surface_app"]};
                border-radius: 5px;
                min-height: 36px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {_P["scrollbar_hover"]};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                background: transparent;
                border: none;
                height: 0px;
                subcontrol-origin: margin;
            }}
            QScrollBar::sub-line:vertical {{
                subcontrol-position: top;
            }}
            QScrollBar::add-line:vertical {{
                subcontrol-position: bottom;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: {_P["surface_app"]};
            }}
            QAbstractScrollArea::corner {{
                background: {_P["surface_app"]};
                border-top: 1px solid {_P["border"]};
                border-left: 1px solid {_P["border"]};
            }}
            QLineEdit, QComboBox, QSpinBox {{
                background: {_P["surface_input"]};
                border: 1px solid {_P["border_strong"]};
                border-radius: 5px;
                padding: 4px 7px;
                color: {_P["text"]};
                selection-background-color: {_P["checked_bg"]};
                selection-color: {_P["checked_text"]};
            }}
            QLineEdit:focus, QComboBox:focus {{
                border-color: {_P["accent"]};
            }}
            QSpinBox, QDoubleSpinBox {{
                background: {_P["surface_input"]};
                border: 1px solid {_P["border_strong"]};
                border-radius: 5px;
                padding: 2px 6px;
                color: {_P["text"]};
            }}
            QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
                background: {_P["surface_bar"]};
                border-left: 1px solid {_P["border_strong"]};
                width: 14px;
            }}
            QFrame#spinFrame {{
                background: {_P["surface_input"]};
                border: 1px solid {_P["border_strong"]};
                border-radius: 5px;
            }}
            QFrame#spinFrame QDoubleSpinBox {{
                background: transparent;
                border: none;
                padding: 2px 6px;
                color: {_P["text"]};
            }}
            QToolButton#spinUpButton {{
                background: {_P["surface_bar"]};
                border-left: 1px solid {_P["border_strong"]};
                border-bottom: 1px solid {_P["border_strong"]};
            }}
            QToolButton#spinDownButton {{
                background: {_P["surface_bar"]};
                border-left: 1px solid {_P["border_strong"]};
            }}
            QComboBox QAbstractItemView {{
                background: {_P["surface_input"]};
                color: {_P["text"]};
                border: 1px solid {_P["border_strong"]};
                selection-background-color: {_P["checked_bg"]};
                selection-color: {_P["checked_text"]};
            }}
            QAbstractItemView {{
                background: {_P["surface_input"]};
                color: {_P["text"]};
                border: 1px solid {_P["border_strong"]};
            }}
            QAbstractItemView::item {{
                background: {_P["surface_input"]};
                color: {_P["text"]};
            }}
            QPushButton {{
                color: {_P["text"]};
                border: 1px solid {_P["border_strong"]};
                border-radius: 5px;
                padding: 5px 12px;
                background: {_P["surface_input"]};
            }}
            QPushButton:hover {{
                background: {_P["hover"]};
                border-color: {_P["checked_border"]};
            }}
            QPushButton:pressed {{
                background: {_P["pressed"]};
            }}
            QMenu {{
                background: {_P["surface_input"]};
                border: 1px solid {_P["border"]};
                border-radius: 8px;
                padding: 5px 0;
            }}
            QMenu::item {{
                padding: 6px 24px 6px 12px;
                color: {_P["text"]};
            }}
            QMenu::item:selected {{
                background: {_P["hover"]};
                border-radius: 4px;
            }}
            QMenu::separator {{
                height: 1px;
                background: {_P["border"]};
                margin: 4px 8px;
            }}
            QDialog, QMessageBox {{
                background: {_P["surface_bar"]};
            }}
            QDialog QLabel, QMessageBox QLabel {{
                color: {_P["text"]};
            }}
            QDialog QLineEdit, QMessageBox QLineEdit {{
                background: {_P["surface_input"]};
                border: 1px solid {_P["border_strong"]};
                border-radius: 5px;
                padding: 3px 6px;
                color: {_P["text"]};
            }}
            QDialog QPushButton, QMessageBox QPushButton {{
                background: {_P["surface_input"]};
                border: 1px solid {_P["border_strong"]};
                border-radius: 5px;
                padding: 5px 14px;
                color: {_P["text"]};
            }}
            QDialog QPushButton:hover, QMessageBox QPushButton:hover {{
                background: {_P["hover"]};
            }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: {_P["border_strong"]};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 12px;
                height: 12px;
                background: {_P["accent"]};
                border-radius: 6px;
                margin: -5px 0;
            }}
            QSlider::handle:horizontal:hover {{
                background: {_P["checked_text"]};
            }}
            QStatusBar {{
                background: {_P["surface_bar"]};
                border-top: 1px solid {_P["border"]};
                color: {_P["text_muted"]};
                padding: 2px 8px;
            }}
            QStatusBar[statusState="error"] {{
                background: #f6eded;
                border-top: 1px solid {_P["border_strong"]};
                color: #8a2020;
            }}
            QStatusBar QLabel {{
                color: {_P["text_muted"]};
            }}
            QStatusBar QLabel#statusContextLabel {{
                border-left: 1px solid {_P["border"]};
                padding: 0 8px;
            }}
            QStatusBar QLabel#statusZoomLabel {{
                padding: 0 8px 0 4px;
            }}
"""


def _flat_toolbutton_style(*, extra: str = "") -> str:
    return (
        "QToolButton {"
        " border: 1px solid transparent;"
        " border-radius: 6px;"
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
    " border-radius: 6px;"
    " padding: 4px 12px;"
    f" background-color: {_P['accent']};"
    " color: #f4f4f3;"
    " font-weight: 600;"
    "}"
    "QToolButton#smiles_render_button:hover {"
    f" background-color: {_P['checked_text']};"
    "}"
    "QToolButton#smiles_render_button:pressed {"
    " background-color: #000000;"
    "}"
    "QToolButton#smiles_render_button:disabled {"
    f" color: {_P['text_faint']};"
    f" background: {_P['pressed']};"
    " border-color: transparent;"
    "}"
)


__all__ = [
    "PALETTE",
    "MAIN_WINDOW_STYLESHEET",
    "TOOLBAR_BUTTON_STYLE",
    "TOOLBAR_MENU_BUTTON_STYLE",
    "CONTEXT_SEGMENT_STYLE",
    "SMILES_RENDER_BUTTON_STYLE",
]
