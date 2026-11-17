"""Which of a document's font families this system cannot draw as named."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtGui import QFont, QFontDatabase, QFontInfo

from chemvas.features.document_fonts import document_font_families

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Any


def missing_font_families(families: Iterable[str]) -> tuple[str, ...]:
    """Families Qt would draw with a substitute font.

    A family counts as installed when the font database lists it or when Qt
    resolves a request for it to that same family (platform-private families
    such as macOS's ``.AppleSystemUIFont`` are resolvable without being listed).
    """
    installed = {family.casefold() for family in QFontDatabase.families()}
    missing = []
    for family in families:
        key = family.casefold()
        if key in installed or QFontInfo(QFont(family)).family().casefold() == key:
            continue
        missing.append(family)
    return tuple(missing)


def missing_document_fonts(state: dict[str, Any]) -> tuple[str, ...]:
    return missing_font_families(document_font_families(state))
