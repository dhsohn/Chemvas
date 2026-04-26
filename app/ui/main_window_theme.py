from __future__ import annotations


MAIN_WINDOW_STYLESHEET = """
            QMainWindow {
                background: #eef0f2;
            }
            QToolBar {
                background: #f8f9fb;
                border: none;
                border-bottom: 1px solid #d9dde3;
                spacing: 4px;
                padding: 4px;
            }
            QToolBar::separator {
                background: #d4d9e1;
            }
            QToolBar::separator:horizontal {
                width: 1px;
                height: 20px;
                margin: 4px 8px;
            }
            QToolBar::separator:vertical {
                width: 22px;
                height: 1px;
                margin: 7px 5px;
            }
            QToolBar QLabel#toolbarSectionLabel {
                background: transparent;
                border: none;
                color: #6a7280;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0px;
                margin: 0 1px;
                padding: 2px 4px;
            }
            QToolButton {
                border: 1px solid transparent;
                border-radius: 5px;
                padding: 5px;
                color: #242933;
            }
            QToolButton:hover {
                background: #edf1f5;
                border-color: #cbd3df;
            }
            QToolButton:pressed {
                background: #e2e8f0;
                border-color: #b8c2d0;
            }
            QToolButton:checked {
                background: #dbeafe;
                border-color: #6aa3e8;
                color: #163b66;
            }
            QToolButton:disabled {
                color: #a5adba;
                background: transparent;
                border-color: transparent;
            }
            QLabel, QCheckBox, QGroupBox, QTabBar, QDockWidget, QToolButton {
                color: #242933;
            }
            QDockWidget {
                background: #f8f9fb;
                border: 1px solid #d9dde3;
            }
            QTabWidget::pane {
                border: 1px solid #d9dde3;
                background: #f8f9fb;
            }
            QTabBar::tab {
                background: #eef0f2;
                padding: 6px 10px;
                border: 1px solid #d9dde3;
                border-bottom: none;
                margin-right: 2px;
                color: #242933;
            }
            QTabBar::tab:selected {
                background: #ffffff;
            }
            QTabWidget#canvasTabs {
                background: #eef0f2;
            }
            QTabWidget#canvasTabs::tab-bar {
                alignment: left;
                left: 8px;
            }
            QTabWidget#canvasTabs::pane {
                border: 1px solid #d9dde3;
                background: #ffffff;
            }
            QTabWidget#canvasTabs QTabBar {
                background: #eef0f2;
                padding: 2px 6px 0 6px;
            }
            QTabWidget#canvasTabs QTabBar::tab {
                background: transparent;
                color: #5c6675;
                border: 1px solid transparent;
                border-top: 2px solid transparent;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
                padding: 3px 12px 4px 12px;
                margin: 0 2px 0 0;
            }
            QTabWidget#canvasTabs QTabBar::tab:last {
                padding: 3px 8px 4px 8px;
                min-width: 20px;
            }
            QTabWidget#canvasTabs QTabBar::tab:hover:!selected {
                background: #e4e8ee;
            }
            QTabWidget#canvasTabs QTabBar::tab:selected {
                background: #ffffff;
                color: #1f2937;
                border-color: #d9dde3;
                border-top-color: #3b82c4;
            }
            QTabWidget#canvasTabs QTabBar QToolButton {
                background: transparent;
                border: none;
                border-radius: 5px;
                color: #5c6675;
                padding: 4px 6px;
            }
            QTabWidget#canvasTabs QTabBar QToolButton:hover {
                background: #e4e8ee;
            }
            QTabWidget#canvasTabs QToolButton#sheetAddButton {
                background: transparent;
                border: 1px solid transparent;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
                color: #5c6675;
                font-size: 18px;
                font-weight: 500;
                margin: 0 4px 0 0;
                min-width: 26px;
                padding: 1px 6px 5px 6px;
            }
            QTabWidget#canvasTabs QToolButton#sheetAddButton:hover {
                background: #e4e8ee;
                border-color: #d9dde3;
            }
            QTabWidget#canvasTabs QToolButton#sheetAddButton:pressed {
                background: #d8dee8;
            }
            QScrollBar:horizontal {
                background: #eef0f2;
                height: 10px;
                margin: 0;
                border-top: 1px solid #dde2e8;
            }
            QScrollBar::handle:horizontal {
                background: #c6ced8;
                border: 2px solid #eef0f2;
                border-radius: 5px;
                min-width: 36px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #9da8b8;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                background: transparent;
                border: none;
                width: 0px;
                subcontrol-origin: margin;
            }
            QScrollBar::sub-line:horizontal {
                subcontrol-position: left;
            }
            QScrollBar::add-line:horizontal {
                subcontrol-position: right;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: #eef0f2;
            }
            QScrollBar:vertical {
                background: #eef0f2;
                width: 10px;
                margin: 0;
                border-left: 1px solid #dde2e8;
            }
            QScrollBar::handle:vertical {
                background: #c6ced8;
                border: 2px solid #eef0f2;
                border-radius: 5px;
                min-height: 36px;
            }
            QScrollBar::handle:vertical:hover {
                background: #9da8b8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                background: transparent;
                border: none;
                height: 0px;
                subcontrol-origin: margin;
            }
            QScrollBar::sub-line:vertical {
                subcontrol-position: top;
            }
            QScrollBar::add-line:vertical {
                subcontrol-position: bottom;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: #eef0f2;
            }
            QAbstractScrollArea::corner {
                background: #eef0f2;
                border-top: 1px solid #dde2e8;
                border-left: 1px solid #dde2e8;
            }
            QLineEdit, QComboBox, QSpinBox {
                background: #ffffff;
                border: 1px solid #cbd3df;
                border-radius: 4px;
                padding: 3px 6px;
                color: #242933;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #3b82c4;
            }
            QSpinBox, QDoubleSpinBox {
                background: #ffffff;
                border: 1px solid #cbd3df;
                border-radius: 4px;
                padding: 2px 6px;
                color: #242933;
            }
            QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
                background: #f8f9fb;
                border-left: 1px solid #cbd3df;
                width: 14px;
            }
            QFrame#spinFrame {
                background: #ffffff;
                border: 1px solid #cbd3df;
                border-radius: 4px;
            }
            QFrame#spinFrame QDoubleSpinBox {
                background: transparent;
                border: none;
                padding: 2px 6px;
                color: #242933;
            }
            QToolButton#spinUpButton {
                background: #f8f9fb;
                border-left: 1px solid #cbd3df;
                border-bottom: 1px solid #cbd3df;
            }
            QToolButton#spinDownButton {
                background: #f8f9fb;
                border-left: 1px solid #cbd3df;
            }
            QComboBox QAbstractItemView {
                background: #ffffff;
                color: #242933;
                border: 1px solid #cbd3df;
                selection-background-color: #dbeafe;
                selection-color: #163b66;
            }
            QAbstractItemView {
                background: #ffffff;
                color: #242933;
                border: 1px solid #cbd3df;
            }
            QAbstractItemView::item {
                background: #ffffff;
                color: #242933;
            }
            QPushButton {
                color: #242933;
                border: 1px solid #cbd3df;
                border-radius: 4px;
                padding: 4px 12px;
                background: #ffffff;
            }
            QPushButton:hover {
                background: #edf1f5;
                border-color: #b8c2d0;
            }
            QPushButton:pressed {
                background: #e2e8f0;
            }
            QMenu {
                background: #ffffff;
                border: 1px solid #d9dde3;
                border-radius: 6px;
                padding: 4px 0;
            }
            QMenu::item {
                padding: 6px 24px 6px 12px;
                color: #242933;
            }
            QMenu::item:selected {
                background: #edf1f5;
                border-radius: 4px;
            }
            QMenu::separator {
                height: 1px;
                background: #d9dde3;
                margin: 4px 8px;
            }
            QDialog, QMessageBox {
                background: #f8f9fb;
            }
            QDialog QLabel, QMessageBox QLabel {
                color: #242933;
            }
            QDialog QLineEdit, QMessageBox QLineEdit {
                background: #ffffff;
                border: 1px solid #cbd3df;
                border-radius: 4px;
                padding: 3px 6px;
                color: #242933;
            }
            QDialog QPushButton, QMessageBox QPushButton {
                background: #ffffff;
                border: 1px solid #cbd3df;
                border-radius: 4px;
                padding: 5px 14px;
                color: #242933;
            }
            QDialog QPushButton:hover, QMessageBox QPushButton:hover {
                background: #edf1f5;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #d7dee8;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 12px;
                height: 12px;
                background: #3b82c4;
                border-radius: 6px;
                margin: -4px 0;
            }
            QSlider::handle:horizontal:hover {
                background: #2563a8;
            }
            QStatusBar {
                background: #f8f9fb;
                border-top: 1px solid #d9dde3;
                color: #697386;
                padding: 2px 8px;
            }
            QStatusBar QLabel {
                color: #697386;
            }
            QStatusBar QLabel#statusContextLabel {
                border-left: 1px solid #d9dde3;
                padding: 0 8px;
            }
            QStatusBar QLabel#statusZoomLabel {
                padding: 0 8px 0 4px;
            }
"""

TOOLBAR_BUTTON_STYLE = (
    "QToolButton {"
    " border: 1px solid transparent;"
    " border-radius: 5px;"
    " padding: 4px;"
    " color: #242933;"
    "}"
    "QToolButton:hover {"
    " background-color: #edf1f5;"
    " border-color: #cbd3df;"
    "}"
    "QToolButton:pressed {"
    " background-color: #e2e8f0;"
    " border-color: #b8c2d0;"
    "}"
    "QToolButton:checked {"
    " background-color: #dbeafe;"
    " border-color: #6aa3e8;"
    " color: #163b66;"
    "}"
    "QToolButton:disabled {"
    " color: #a5adba;"
    " background: transparent;"
    " border-color: transparent;"
    "}"
)

TOOLBAR_MENU_BUTTON_STYLE = (
    "QToolButton {"
    " border: 1px solid transparent;"
    " border-radius: 5px;"
    " padding: 4px;"
    " padding-right: 8px;"
    " color: #242933;"
    "}"
    "QToolButton:hover {"
    " background-color: #edf1f5;"
    " border-color: #cbd3df;"
    "}"
    "QToolButton:pressed {"
    " background-color: #e2e8f0;"
    " border-color: #b8c2d0;"
    "}"
    "QToolButton:checked {"
    " background-color: #dbeafe;"
    " border-color: #6aa3e8;"
    " color: #163b66;"
    "}"
    "QToolButton:disabled {"
    " color: #a5adba;"
    " background: transparent;"
    " border-color: transparent;"
    "}"
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
    "QToolButton::menu-arrow { image: none; width: 0px; height: 0px; border: none; background: transparent; }"
)

SMILES_RENDER_BUTTON_STYLE = (
    "QToolButton#smiles_render_button {"
    " border: 1px solid #cbd3df;"
    " border-radius: 5px;"
    " padding: 3px 10px;"
    " background-color: #ffffff;"
    " color: #242933;"
    "}"
    "QToolButton#smiles_render_button:hover {"
    " background-color: #edf1f5;"
    " border-color: #b8c2d0;"
    "}"
    "QToolButton#smiles_render_button:pressed {"
    " background-color: #e2e8f0;"
    " border-color: #3b82c4;"
    "}"
    "QToolButton#smiles_render_button:disabled {"
    " color: #a5adba;"
    " background: transparent;"
    " border-color: transparent;"
    "}"
)


__all__ = ["MAIN_WINDOW_STYLESHEET"]
