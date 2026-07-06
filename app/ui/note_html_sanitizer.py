from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser

SAFE_NOTE_HTML_TAGS = frozenset(("b", "br", "i", "p", "span", "sub", "sup"))
VOID_NOTE_HTML_TAGS = frozenset(("br",))
SKIP_NOTE_HTML_CONTENT_TAGS = frozenset(
    ("embed", "head", "iframe", "math", "object", "script", "style", "svg", "title")
)
SAFE_NOTE_HTML_ATTRS_BY_TAG = {
    "p": frozenset(("align", "style")),
    "span": frozenset(("style",)),
}
SAFE_NOTE_ALIGN_VALUES = frozenset(("center", "justify", "left", "right"))
UNSAFE_NOTE_HTML_VALUE_MARKERS = ("javascript:", "vbscript:", "file:", "data:", "url(", "@import", "expression")
SAFE_NOTE_STYLE_PROPERTIES = frozenset(
    (
        "color",
        "font-family",
        "font-size",
        "font-style",
        "font-weight",
        "line-height",
        "text-decoration",
        "vertical-align",
    )
)
MAX_NOTE_HTML_CHARS = 1_000_000
_CSS_COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\Z")
_CSS_FONT_WEIGHT_RE = re.compile(r"[1-9]00\Z")
_CSS_LENGTH_RE = re.compile(r"\d{1,3}(?:\.\d{1,2})?(?:em|pt|px|rem|%)\Z")
_CSS_NUMBER_RE = re.compile(r"\d{1,3}(?:\.\d{1,2})?\Z")


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
        attr_text = self._sanitized_attrs(tag, attrs)
        self.parts.append(f"<{tag}{attr_text}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in SKIP_NOTE_HTML_CONTENT_TAGS:
            return
        if self._skip_depth or tag not in SAFE_NOTE_HTML_TAGS:
            return
        attr_text = self._sanitized_attrs(tag, attrs)
        if tag in VOID_NOTE_HTML_TAGS:
            self.parts.append(f"<{tag}{attr_text}>")
        else:
            self.parts.append(f"<{tag}{attr_text}></{tag}>")

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

    def _sanitized_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        allowed_attrs = SAFE_NOTE_HTML_ATTRS_BY_TAG.get(tag, frozenset())
        if not allowed_attrs:
            return ""
        parts: list[str] = []
        seen_attrs: set[str] = set()
        for name, value in attrs:
            name = name.lower()
            if name.startswith("on") or name not in allowed_attrs or name in seen_attrs or value is None:
                continue
            seen_attrs.add(name)
            if name == "style":
                value = _sanitized_style_value(value)
                if value is None:
                    continue
            elif name == "align":
                value = _sanitized_align_value(value)
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
        if not _is_safe_style_property_value(property_name, property_value):
            continue
        declarations.append(f"{property_name}:{property_value}")
    return "; ".join(declarations) if declarations else None


def _sanitized_align_value(value: str) -> str | None:
    value = value.strip().lower()
    if value not in SAFE_NOTE_ALIGN_VALUES:
        return None
    return value


def _is_safe_style_property_value(property_name: str, value: str) -> bool:
    lower_value = value.lower()
    if any(char in lower_value for char in ("\\", "@", "(", ")")):
        return False
    if any(marker in lower_value for marker in UNSAFE_NOTE_HTML_VALUE_MARKERS):
        return False
    if property_name == "color":
        return _CSS_COLOR_RE.fullmatch(value) is not None
    if property_name == "font-family":
        return _is_safe_font_family_value(value)
    if property_name == "font-size":
        return _CSS_LENGTH_RE.fullmatch(lower_value) is not None
    if property_name == "font-style":
        return lower_value in {"italic", "normal", "oblique"}
    if property_name == "font-weight":
        return lower_value in {"bold", "bolder", "lighter", "normal"} or _CSS_FONT_WEIGHT_RE.fullmatch(
            lower_value
        ) is not None
    if property_name == "line-height":
        return (
            lower_value == "normal"
            or _CSS_NUMBER_RE.fullmatch(lower_value) is not None
            or _CSS_LENGTH_RE.fullmatch(lower_value) is not None
        )
    if property_name == "text-decoration":
        values = lower_value.split()
        return bool(values) and all(token in {"line-through", "none", "overline", "underline"} for token in values)
    if property_name == "vertical-align":
        return lower_value in {"baseline", "sub", "super"}
    return False


def _is_safe_font_family_value(value: str) -> bool:
    if len(value) > 128 or not any(char.isalnum() for char in value):
        return False
    return all(char.isalnum() or char in " ,'\"._-" for char in value)


__all__ = ["MAX_NOTE_HTML_CHARS", "sanitize_note_html"]
