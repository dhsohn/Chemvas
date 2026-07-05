from __future__ import annotations

from html import escape
from html.parser import HTMLParser

SAFE_NOTE_HTML_TAGS = frozenset(
    (
        "b",
        "blockquote",
        "body",
        "br",
        "code",
        "div",
        "em",
        "font",
        "head",
        "html",
        "i",
        "li",
        "meta",
        "ol",
        "p",
        "pre",
        "s",
        "span",
        "strike",
        "strong",
        "sub",
        "sup",
        "u",
        "ul",
    )
)
VOID_NOTE_HTML_TAGS = frozenset(("br", "meta"))
SKIP_NOTE_HTML_CONTENT_TAGS = frozenset(("embed", "iframe", "math", "object", "script", "style", "svg"))
SAFE_NOTE_HTML_ATTRS = frozenset(("align", "color", "content", "dir", "face", "name", "size", "style"))
UNSAFE_NOTE_HTML_VALUE_MARKERS = ("javascript:", "vbscript:", "file:", "data:", "url(", "@import", "expression")
SAFE_NOTE_STYLE_PROPERTIES = frozenset(
    (
        "-qt-block-indent",
        "-qt-paragraph-type",
        "background-color",
        "color",
        "font-family",
        "font-size",
        "font-style",
        "font-weight",
        "line-height",
        "margin-bottom",
        "margin-left",
        "margin-right",
        "margin-top",
        "text-decoration",
        "text-indent",
        "vertical-align",
        "white-space",
    )
)
MAX_NOTE_HTML_CHARS = 1_000_000


def sanitize_note_html(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if len(value) > MAX_NOTE_HTML_CHARS:
        return None
    parser = _NoteHtmlSanitizer()
    parser.feed(value)
    parser.close()
    sanitized = "".join(parser.parts).strip()
    return sanitized or None


class _NoteHtmlSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in SKIP_NOTE_HTML_CONTENT_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth or tag not in SAFE_NOTE_HTML_TAGS:
            return
        attr_text = self._sanitized_attrs(attrs)
        self.parts.append(f"<{tag}{attr_text}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self._skip_depth or tag not in SAFE_NOTE_HTML_TAGS:
            return
        attr_text = self._sanitized_attrs(attrs)
        self.parts.append(f"<{tag}{attr_text}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in SKIP_NOTE_HTML_CONTENT_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth or tag not in SAFE_NOTE_HTML_TAGS or tag in VOID_NOTE_HTML_TAGS:
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self.parts.append(escape(data, quote=False))

    def _sanitized_attrs(self, attrs: list[tuple[str, str | None]]) -> str:
        parts: list[str] = []
        for name, value in attrs:
            name = name.lower()
            if name.startswith("on") or name not in SAFE_NOTE_HTML_ATTRS or value is None:
                continue
            if name == "style":
                value = _sanitized_style_value(value)
                if value is None:
                    continue
            if not _is_safe_attr_value(value):
                continue
            parts.append(f' {name}="{escape(value, quote=True)}"')
        return "".join(parts)


def _is_safe_attr_value(value: str) -> bool:
    lower_value = value.lower()
    if "\\" in lower_value:
        return False
    return not any(marker in lower_value for marker in UNSAFE_NOTE_HTML_VALUE_MARKERS)


def _sanitized_style_value(value: str) -> str | None:
    declarations: list[str] = []
    for declaration in value.split(";"):
        if ":" not in declaration:
            continue
        property_name, property_value = declaration.split(":", 1)
        property_name = property_name.strip().lower()
        property_value = property_value.strip()
        if property_name not in SAFE_NOTE_STYLE_PROPERTIES or not property_value:
            continue
        if not _is_safe_style_property_value(property_value):
            continue
        declarations.append(f"{property_name}:{property_value}")
    return "; ".join(declarations) if declarations else None


def _is_safe_style_property_value(value: str) -> bool:
    lower_value = value.lower()
    if any(char in lower_value for char in ("\\", "@", "(", ")")):
        return False
    return not any(marker in lower_value for marker in UNSAFE_NOTE_HTML_VALUE_MARKERS)


__all__ = ["MAX_NOTE_HTML_CHARS", "sanitize_note_html"]
