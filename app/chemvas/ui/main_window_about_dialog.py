from __future__ import annotations

import importlib.metadata
import importlib.util
import platform

from PyQt6.QtCore import QT_VERSION_STR, QSize, Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from chemvas.branding import APP_NAME, APP_VERSION, app_icon

GITHUB_URL = "https://github.com/dhsohn/Chemvas"
DESCRIPTION = "A lightweight 2D chemical structure drawing canvas."


def rdkit_status() -> str:
    """One-line description of the optional RDKit backend's availability.

    Uses ``find_spec``/metadata so it never imports (and pays the load cost of)
    RDKit just to render the About box.
    """
    if importlib.util.find_spec("rdkit") is None:
        return "Not installed — SMILES, formula, and 3D features are disabled"
    for distribution in ("rdkit", "rdkit-pypi"):
        try:
            return f"Available ({importlib.metadata.version(distribution)})"
        except importlib.metadata.PackageNotFoundError:
            continue
    return "Available"


def _info_rows() -> tuple[tuple[str, str], ...]:
    return (
        ("License", "MIT"),
        ("RDKit backend", rdkit_status()),
        ("Qt", QT_VERSION_STR),
        ("Python", platform.python_version()),
    )


def show_about_dialog(window) -> None:
    dialog = QDialog(window)
    dialog.setObjectName("aboutDialog")
    dialog.setWindowTitle(f"About {APP_NAME}")
    dialog.setStyleSheet(window.styleSheet())
    layout = QVBoxLayout(dialog)
    layout.setSpacing(14)

    header = QHBoxLayout()
    header.setSpacing(14)
    icon_label = QLabel()
    icon_label.setObjectName("aboutIcon")
    icon_label.setPixmap(app_icon().pixmap(QSize(64, 64)))
    icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
    header.addWidget(icon_label)

    heading = QVBoxLayout()
    heading.setSpacing(2)
    title_label = QLabel(APP_NAME)
    title_label.setObjectName("aboutTitle")
    title_font = title_label.font()
    base_point_size = title_font.pointSize()
    if base_point_size > 0:
        title_font.setPointSize(base_point_size + 6)
    title_font.setBold(True)
    title_label.setFont(title_font)
    heading.addWidget(title_label)
    version_label = QLabel(f"Version {APP_VERSION}")
    version_label.setObjectName("aboutVersion")
    heading.addWidget(version_label)
    description_label = QLabel(DESCRIPTION)
    description_label.setObjectName("aboutDescription")
    description_label.setWordWrap(True)
    heading.addWidget(description_label)
    header.addLayout(heading, 1)
    layout.addLayout(header)

    separator = QFrame()
    separator.setFrameShape(QFrame.Shape.HLine)
    separator.setFrameShadow(QFrame.Shadow.Sunken)
    layout.addWidget(separator)

    info = QGridLayout()
    info.setHorizontalSpacing(16)
    info.setVerticalSpacing(4)
    for row, (name, value) in enumerate(_info_rows()):
        name_label = QLabel(name)
        name_label.setObjectName("aboutFieldName")
        value_label = QLabel(value)
        value_label.setObjectName("aboutFieldValue")
        value_label.setWordWrap(True)
        info.addWidget(name_label, row, 0, Qt.AlignmentFlag.AlignTop)
        info.addWidget(value_label, row, 1)
    info.setColumnStretch(1, 1)
    layout.addLayout(info)

    link_label = QLabel(f'<a href="{GITHUB_URL}">{GITHUB_URL}</a>')
    link_label.setObjectName("aboutLink")
    link_label.setOpenExternalLinks(True)
    link_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    layout.addWidget(link_label)

    action_row = QHBoxLayout()
    action_row.addStretch(1)
    close_button = QPushButton("Close")
    close_button.setObjectName("aboutCloseButton")
    close_button.setDefault(True)
    close_button.clicked.connect(dialog.accept)
    action_row.addWidget(close_button)
    layout.addLayout(action_row)

    dialog.exec()


__all__ = ["DESCRIPTION", "GITHUB_URL", "rdkit_status", "show_about_dialog"]
