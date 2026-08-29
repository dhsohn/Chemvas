from __future__ import annotations

from chemvas.ui.main_window_palette import PALETTE
from chemvas.ui.main_window_toolbar_styles import TOOLBAR_BUTTON_SIZE


def main_window_chrome_stylesheet(palette) -> str:
    return f"""
            QMainWindow {{
                background: {palette["surface_app"]};
            }}
            QToolBar {{
                background: {palette["surface_bar"]};
                border: none;
                border-bottom: 1px solid {palette["border"]};
                spacing: 4px;
                padding: 2px 4px;
            }}
            QToolBar#topRoleToolbar {{
                padding: 2px 4px;
            }}
            QToolBar#contextOptionsBar {{
                background: {palette["surface_context"]};
                border-bottom: 1px solid {palette["border"]};
                padding: 0px 4px;
            }}
            QToolBar::separator {{
                background: {palette["border"]};
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
                color: {palette["text_faint"]};
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
                color: {palette["text"]};
            }}
            QToolButton:hover {{
                background: {palette["hover"]};
                border-color: transparent;
            }}
            QToolButton:pressed {{
                background: {palette["pressed"]};
                border-color: transparent;
            }}
            QToolButton:checked {{
                background: {palette["checked_bg"]};
                border-color: {palette["checked_border"]};
                color: {palette["checked_text"]};
            }}
            QToolButton:disabled {{
                color: {palette["text_faint"]};
                background: transparent;
                border-color: transparent;
            }}
            QLabel, QCheckBox, QGroupBox, QTabBar, QToolButton {{
                color: {palette["text"]};
            }}
            QTabWidget::pane {{
                border: 1px solid {palette["border"]};
                background: {palette["surface_panel"]};
            }}
            QTabBar::tab {{
                background: {palette["surface_app"]};
                padding: 6px 10px;
                border: 1px solid {palette["border"]};
                border-bottom: none;
                margin-right: 2px;
                color: {palette["text"]};
            }}
            QTabBar::tab:selected {{
                background: {palette["surface_canvas"]};
            }}
"""


def main_window_canvas_tab_stylesheet(palette) -> str:
    return f"""
            QTabWidget#canvasTabs {{
                background: {palette["surface_app"]};
            }}
            QTabWidget#canvasTabs::tab-bar {{
                alignment: left;
                left: 8px;
            }}
            QTabWidget#canvasTabs::pane {{
                border: 1px solid {palette["border"]};
                background: {palette["surface_canvas"]};
            }}
            QTabWidget#canvasTabs QTabBar {{
                background: {palette["surface_app"]};
                padding: 2px 6px 0 6px;
            }}
            QTabWidget#canvasTabs QTabBar::tab {{
                background: transparent;
                color: {palette["text_muted"]};
                border: 1px solid transparent;
                border-top: 2px solid transparent;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
                padding: 4px 14px 5px 14px;
                margin: 0 2px 0 0;
            }}
            QTabWidget#canvasTabs QTabBar::tab:hover:!selected {{
                background: {palette["hover"]};
            }}
            QTabWidget#canvasTabs QTabBar::tab:selected {{
                background: {palette["surface_canvas"]};
                color: {palette["text"]};
                border-color: {palette["border"]};
                border-top-color: {palette["accent"]};
            }}
            QTabWidget#canvasTabs QTabBar QToolButton {{
                background: transparent;
                border: none;
                border-radius: 8px;
                color: {palette["text_muted"]};
                padding: 4px 6px;
            }}
            QTabWidget#canvasTabs QTabBar QToolButton:hover {{
                background: {palette["hover"]};
            }}
"""


def main_window_scrollbar_stylesheet(palette) -> str:
    return f"""
            QScrollBar:horizontal {{
                background: {palette["surface_app"]};
                height: 10px;
                margin: 0;
                border-top: 1px solid {palette["border"]};
            }}
            QScrollBar::handle:horizontal {{
                background: {palette["scrollbar"]};
                border: 2px solid {palette["surface_app"]};
                border-radius: 8px;
                min-width: 36px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {palette["scrollbar_hover"]};
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
                background: {palette["surface_app"]};
            }}
            QScrollBar:vertical {{
                background: {palette["surface_app"]};
                width: 10px;
                margin: 0;
                border-left: 1px solid {palette["border"]};
            }}
            QScrollBar::handle:vertical {{
                background: {palette["scrollbar"]};
                border: 2px solid {palette["surface_app"]};
                border-radius: 8px;
                min-height: 36px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {palette["scrollbar_hover"]};
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
                background: {palette["surface_app"]};
            }}
            QAbstractScrollArea::corner {{
                background: {palette["surface_app"]};
                border-top: 1px solid {palette["border"]};
                border-left: 1px solid {palette["border"]};
            }}
"""


def main_window_form_stylesheet(palette) -> str:
    return f"""
            QLineEdit, QComboBox, QSpinBox {{
                background: {palette["surface_input"]};
                border: 1px solid {palette["border_strong"]};
                border-radius: 8px;
                padding: 4px 7px;
                color: {palette["text"]};
                selection-background-color: {palette["checked_bg"]};
                selection-color: {palette["checked_text"]};
            }}
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
                border-color: {palette["accent"]};
            }}
            QSpinBox, QDoubleSpinBox {{
                background: {palette["surface_input"]};
                border: 1px solid {palette["border_strong"]};
                border-radius: 8px;
                padding: 2px 6px;
                color: {palette["text"]};
            }}
            QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
                background: {palette["surface_bar"]};
                border-left: 1px solid {palette["border_strong"]};
                width: 14px;
            }}
            QFrame#spinFrame {{
                background: {palette["surface_input"]};
                border: 1px solid {palette["border_strong"]};
                border-radius: 8px;
            }}
            QFrame#spinFrame QDoubleSpinBox {{
                background: transparent;
                border: none;
                padding: 2px 6px;
                color: {palette["text"]};
            }}
            QToolButton#spinUpButton {{
                background: {palette["surface_bar"]};
                border-left: 1px solid {palette["border_strong"]};
                border-bottom: 1px solid {palette["border_strong"]};
            }}
            QToolButton#spinDownButton {{
                background: {palette["surface_bar"]};
                border-left: 1px solid {palette["border_strong"]};
            }}
            QComboBox QAbstractItemView {{
                background: {palette["surface_input"]};
                color: {palette["text"]};
                border: 1px solid {palette["border_strong"]};
                selection-background-color: {palette["checked_bg"]};
                selection-color: {palette["checked_text"]};
            }}
            QAbstractItemView {{
                background: {palette["surface_input"]};
                color: {palette["text"]};
                border: 1px solid {palette["border_strong"]};
            }}
            QAbstractItemView::item {{
                background: {palette["surface_input"]};
                color: {palette["text"]};
            }}
            QPushButton {{
                color: {palette["text"]};
                border: 1px solid {palette["border_strong"]};
                border-radius: 8px;
                padding: 5px 12px;
                background: {palette["surface_input"]};
            }}
            QPushButton:hover {{
                background: {palette["hover"]};
                border-color: {palette["checked_border"]};
            }}
            QPushButton:pressed {{
                background: {palette["pressed"]};
            }}
            QMenu {{
                background: {palette["surface_input"]};
                border: 1px solid {palette["border"]};
                border-radius: 8px;
                padding: 5px 0;
            }}
            QMenu::item {{
                padding: 6px 24px 6px 12px;
                color: {palette["text"]};
            }}
            QMenu::item:selected {{
                background: {palette["hover"]};
                border-radius: 4px;
            }}
            QMenu::separator {{
                height: 1px;
                background: {palette["border"]};
                margin: 4px 8px;
            }}
            QDialog, QMessageBox {{
                background: {palette["surface_bar"]};
            }}
            QDialog QLabel, QMessageBox QLabel {{
                color: {palette["text"]};
            }}
            QDialog QLineEdit, QMessageBox QLineEdit {{
                background: {palette["surface_input"]};
                border: 1px solid {palette["border_strong"]};
                border-radius: 8px;
                padding: 3px 6px;
                color: {palette["text"]};
            }}
            QDialog QPushButton, QMessageBox QPushButton {{
                background: {palette["surface_input"]};
                border: 1px solid {palette["border_strong"]};
                border-radius: 8px;
                padding: 5px 14px;
                color: {palette["text"]};
            }}
            QDialog QPushButton:hover, QMessageBox QPushButton:hover {{
                background: {palette["hover"]};
                border-color: {palette["checked_border"]};
            }}
            QDialog QPushButton:pressed, QMessageBox QPushButton:pressed {{
                background: {palette["pressed"]};
            }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: {palette["border_strong"]};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 12px;
                height: 12px;
                background: {palette["accent"]};
                border-radius: 8px;
                margin: -5px 0;
            }}
            QSlider::handle:horizontal:hover {{
                background: {palette["checked_text"]};
            }}
"""


def main_window_status_stylesheet(palette) -> str:
    return f"""
            QStatusBar {{
                background: {palette["surface_bar"]};
                border-top: 1px solid {palette["border"]};
                color: {palette["text_muted"]};
                padding: 2px 8px;
            }}
            QStatusBar[statusState="error"] {{
                background: {palette["danger_bg"]};
                border-top: 1px solid {palette["danger_border"]};
                color: {palette["danger_text"]};
            }}
            QStatusBar QLabel {{
                color: {palette["text_muted"]};
            }}
            QStatusBar QLabel#statusContextLabel {{
                border-left: 1px solid {palette["border"]};
                padding: 0 8px;
            }}
            QStatusBar QToolButton#statusZoomButton {{
                color: {palette["text_muted"]};
                background: transparent;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                min-width: 18px;
                padding: 1px 5px;
                margin: 0;
            }}
            QStatusBar QToolButton#statusZoomButton:hover {{
                background: {palette["hover"]};
                color: {palette["text"]};
            }}
            QStatusBar QToolButton#statusZoomButton:pressed {{
                background: {palette["pressed"]};
            }}
            QStatusBar QToolButton#statusZoomLabel {{
                color: {palette["text"]};
                font-weight: 500;
            }}
            QStatusBar QToolButton#statusZoomLabel:hover {{
                background: {palette["hover"]};
            }}
            QStatusBar QToolButton#statusZoomLabel:pressed {{
                background: {palette["pressed"]};
            }}
            QStatusBar QToolButton#statusZoomFitButton {{
                color: {palette["text_muted"]};
                background: transparent;
                border: 1px solid {palette["border_strong"]};
                border-radius: 4px;
                font-size: 12px;
                font-weight: 500;
                min-width: 18px;
                padding: 1px 7px;
                margin: 0 0 0 3px;
            }}
            QStatusBar QToolButton#statusZoomFitButton:hover {{
                background: {palette["hover"]};
                color: {palette["text"]};
                border-color: {palette["scrollbar_hover"]};
            }}
            QStatusBar QToolButton#statusZoomFitButton:pressed {{
                background: {palette["pressed"]};
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
