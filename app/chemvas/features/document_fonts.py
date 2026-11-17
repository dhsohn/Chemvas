"""Font families a document's text asks for, independent of what is installed."""

from __future__ import annotations

import html
import re
from typing import TYPE_CHECKING, Any

from chemvas.domain.document.cdxml_source import parse_native_xml

if TYPE_CHECKING:
    from collections.abc import Iterable

_FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;\"]+)", re.IGNORECASE)


def _css_families(value: str) -> list[str]:
    families = []
    for raw in value.split(","):
        name = raw.strip()
        if len(name) >= 2 and name[0] == name[-1] and name[0] in "'\"":
            name = name[1:-1].replace("\\" + name[0], name[0]).replace("\\\\", "\\")
        if name:
            families.append(name)
    return families


def _note_families(note_html: str) -> list[str]:
    families = []
    for match in _FONT_FAMILY.finditer(html.unescape(note_html)):
        families.extend(_css_families(match.group(1)))
    return families


def _native_families(source: dict[str, Any]) -> list[str]:
    """Fonts named by the retained CDXML's text runs, in fonttable order."""
    root = parse_native_xml(source["xml"])
    used = {e.get("font") for e in root.iter() if e.tag != "font" and e.get("font")}
    return [
        name
        for font in root.iter("font")
        if font.get("id") in used and (name := (font.get("name") or "").strip())
    ]


def document_font_families(state: dict[str, Any]) -> list[str]:
    """Distinct families the document's text is drawn with, in first-use order.

    Native CDXML runs name their fonts in the retained fonttable. Note HTML
    names explicit families; a note's other text uses the document's text
    font, so that counts as soon as the document has a note.
    """
    found: list[str] = []
    source = state.get("cdxml_source")
    if isinstance(source, dict) and isinstance(source.get("xml"), str):
        found.extend(_native_families(source))
    notes = state.get("notes") or []
    if notes:
        settings = state.get("settings") or {}
        family = settings.get("text_font_family")
        if isinstance(family, str) and family.strip():
            found.append(family.strip())
    for note in notes:
        note_html = note.get("html") if isinstance(note, dict) else None
        if isinstance(note_html, str):
            found.extend(_note_families(note_html))
    return _unique(found)


def _unique(names: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for name in names:
        key = name.casefold()
        if key not in seen:
            seen.add(key)
            result.append(name)
    return result
