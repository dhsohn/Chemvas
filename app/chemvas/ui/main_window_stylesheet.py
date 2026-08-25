from __future__ import annotations

from chemvas.ui.main_window_palette import PALETTE
from chemvas.ui.main_window_toolbar_styles import TOOLBAR_BUTTON_SIZE


def main_window_chrome_stylesheet(palette) -> str:
    _P = palette
    return f"""
            QMainWindow {{
                background: {_P["surface_app"]};
            }}
            QToolBar {{
                background: {_P["surface_bar"]};
                border: none;
                border-bottom: 1px solid {_P["border"]};
                spacing: 4px;
                padding: 2px 4px;
            }}
            QToolBar#topRoleToolbar {{
                padding: 2px 4px;
            }}
            QToolBar#contextOptionsBar {{
                background: {_P["surface_context"]};
                border-bottom: 1px solid {_P["border"]};
                padding: 0px 4px;
            }}
            QToolBar::separator {{
                background: {_P["border"]};
            }}
            QToolBar::separator:horizontal {{
                width: 1px;
                height: {TOOLBAR_BUTTON_SIZE - 4}px;
                margin: 3px 9px;
            }}
            QToolBar::separator:vertical {{
                width: 20px;
                height: 1px;
                margin: 4px 5px;
            }}
            QToolBar QLabel#toolbarSectionLabel {{
                background: transparent;
                border: none;
                color: {_P["text_faint"]};
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 0.8px;
                margin: 0 2px;
                padding: 2px 4px;
                text-transform: uppercase;
            }}
            QToolButton {{
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 2px;
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
            QLabel, QCheckBox, QGroupBox, QTabBar, QToolButton {{
                color: {_P["text"]};
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
"""


def main_window_canvas_tab_stylesheet(palette) -> str:
    _P = palette
    return f"""
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
                border-radius: 8px;
                color: {_P["text_muted"]};
                padding: 4px 6px;
            }}
            QTabWidget#canvasTabs QTabBar QToolButton:hover {{
                background: {_P["hover"]};
            }}
"""


def main_window_scrollbar_stylesheet(palette) -> str:
    _P = palette
    return f"""
            QScrollBar:horizontal {{
                background: {_P["surface_app"]};
                height: 10px;
                margin: 0;
                border-top: 1px solid {_P["border"]};
            }}
            QScrollBar::handle:horizontal {{
                background: {_P["scrollbar"]};
                border: 2px solid {_P["surface_app"]};
                border-radius: 8px;
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
                border-radius: 8px;
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
"""


def main_window_form_stylesheet(palette) -> str:
    _P = palette
    return f"""
            QLineEdit, QComboBox, QSpinBox {{
                background: {_P["surface_input"]};
                border: 1px solid {_P["border_strong"]};
                border-radius: 8px;
                padding: 4px 7px;
                color: {_P["text"]};
                selection-background-color: {_P["checked_bg"]};
                selection-color: {_P["checked_text"]};
            }}
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
                border-color: {_P["accent"]};
            }}
            QSpinBox, QDoubleSpinBox {{
                background: {_P["surface_input"]};
                border: 1px solid {_P["border_strong"]};
                border-radius: 8px;
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
                border-radius: 8px;
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
                border-radius: 8px;
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
                border-radius: 8px;
                padding: 3px 6px;
                color: {_P["text"]};
            }}
            QDialog QPushButton, QMessageBox QPushButton {{
                background: {_P["surface_input"]};
                border: 1px solid {_P["border_strong"]};
                border-radius: 8px;
                padding: 5px 14px;
                color: {_P["text"]};
            }}
            QDialog QPushButton:hover, QMessageBox QPushButton:hover {{
                background: {_P["hover"]};
                border-color: {_P["checked_border"]};
            }}
            QDialog QPushButton:pressed, QMessageBox QPushButton:pressed {{
                background: {_P["pressed"]};
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
                border-radius: 8px;
                margin: -5px 0;
            }}
            QSlider::handle:horizontal:hover {{
                background: {_P["checked_text"]};
            }}
"""


def main_window_status_stylesheet(palette) -> str:
    _P = palette
    return f"""
            QStatusBar {{
                background: {_P["surface_bar"]};
                border-top: 1px solid {_P["border"]};
                color: {_P["text_muted"]};
                padding: 2px 8px;
            }}
            QStatusBar[statusState="error"] {{
                background: {_P["danger_bg"]};
                border-top: 1px solid {_P["danger_border"]};
                color: {_P["danger_text"]};
            }}
            QStatusBar QLabel {{
                color: {_P["text_muted"]};
            }}
            QStatusBar QLabel#statusContextLabel {{
                border-left: 1px solid {_P["border"]};
                padding: 0 8px;
            }}
            QStatusBar QToolButton#statusZoomButton {{
                color: {_P["text_muted"]};
                background: transparent;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                min-width: 18px;
                padding: 1px 5px;
                margin: 0;
            }}
            QStatusBar QToolButton#statusZoomButton:hover {{
                background: {_P["hover"]};
                color: {_P["text"]};
            }}
            QStatusBar QToolButton#statusZoomButton:pressed {{
                background: {_P["pressed"]};
            }}
            QStatusBar QToolButton#statusZoomLabel {{
                color: {_P["text"]};
                font-weight: 500;
            }}
            QStatusBar QToolButton#statusZoomLabel:hover {{
                background: {_P["hover"]};
            }}
            QStatusBar QToolButton#statusZoomLabel:pressed {{
                background: {_P["pressed"]};
            }}
            QStatusBar QToolButton#statusZoomFitButton {{
                color: {_P["text_muted"]};
                background: transparent;
                border: 1px solid {_P["border_strong"]};
                border-radius: 4px;
                font-size: 12px;
                font-weight: 500;
                min-width: 18px;
                padding: 1px 7px;
                margin: 0 0 0 3px;
            }}
            QStatusBar QToolButton#statusZoomFitButton:hover {{
                background: {_P["hover"]};
                color: {_P["text"]};
                border-color: {_P["scrollbar_hover"]};
            }}
            QStatusBar QToolButton#statusZoomFitButton:pressed {{
                background: {_P["pressed"]};
            }}
"""


def build_main_window_stylesheet(palette=PALETTE) -> str:
    return "\n".join(
        (
            main_window_chrome_stylesheet(palette),
            main_window_canvas_tab_stylesheet(palette),
            main_window_scrollbar_stylesheet(palette),
            main_window_form_stylesheet(palette),
            main_window_status_stylesheet(palette),
        )
    )


MAIN_WINDOW_STYLESHEET = build_main_window_stylesheet()


__all__ = ["MAIN_WINDOW_STYLESHEET", "build_main_window_stylesheet"]
