from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser

SAFE_NOTE_HTML_TAGS = frozenset(
    (
        "b",
        "blockquote",
        "br",
        "div",
        "em",
        "font",
        "i",
        "li",
        "ol",
        "p",
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
VOID_NOTE_HTML_TAGS = frozenset(("br",))
SKIP_NOTE_HTML_CONTENT_TAGS = frozenset(
    (
        "embed",
        "head",
        "iframe",
        "math",
        "object",
        "script",
        "style",
        "svg",
        "template",
        "title",
    )
)
SAFE_NOTE_HTML_ATTRS_BY_TAG = {
    tag: frozenset(("style",)) for tag in SAFE_NOTE_HTML_TAGS - VOID_NOTE_HTML_TAGS
}
SAFE_NOTE_HTML_ATTRS_BY_TAG.update(
    {
        "blockquote": frozenset(("align", "style")),
        "div": frozenset(("align", "style")),
        "font": frozenset(("color", "face", "size", "style")),
        "li": frozenset(("align", "style", "type", "value")),
        "ol": frozenset(("start", "style", "type")),
        "p": frozenset(("align", "style")),
        "ul": frozenset(("style", "type")),
    }
)
SAFE_NOTE_ALIGN_VALUES = frozenset(("center", "justify", "left", "right"))
UNSAFE_NOTE_HTML_VALUE_MARKERS = (
    "javascript:",
    "vbscript:",
    "file:",
    "data:",
    "url(",
    "@import",
    "expression",
)
SAFE_NOTE_STYLE_PROPERTIES = frozenset(
    (
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
        "text-align",
        "text-decoration",
        "text-indent",
        "vertical-align",
    )
)
MAX_NOTE_HTML_CHARS = 1_000_000
_CSS_COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\Z")
_CSS_FONT_WEIGHT_RE = re.compile(r"[1-9]00\Z")
_CSS_LENGTH_RE = re.compile(r"\d{1,3}(?:\.\d{1,2})?(?:em|pt|px|rem|%)\Z")
_CSS_NUMBER_RE = re.compile(r"\d{1,3}(?:\.\d{1,2})?\Z")
_CSS_RGB_COLOR_RE = re.compile(
    r"rgba?\(\s*(?:\d{1,3}%?\s*,\s*){2}\d{1,3}%?(?:\s*,\s*(?:0|1|0?\.\d{1,3}|\d{1,3}%))?\s*\)\Z"
)
_CSS_FONT_SIZE_KEYWORDS = frozenset(
    (
        "large",
        "larger",
        "medium",
        "small",
        "smaller",
        "x-large",
        "x-small",
        "xx-large",
        "xx-small",
    )
)
_CSS_NAMED_COLORS = frozenset(
    (
        "aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet brown "
        "burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan "
        "darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid "
        "darkred darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise darkviolet "
        "deeppink deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro "
        "ghostwhite gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki "
        "lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow "
        "lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen lightskyblue lightslategray "
        "lightslategrey lightsteelblue lightyellow lime limegreen linen magenta maroon mediumaquamarine "
        "mediumblue mediumorchid mediumpurple mediumseagreen mediumslateblue mediumspringgreen mediumturquoise "
        "mediumvioletred midnightblue mintcream mistyrose moccasin navajowhite navy oldlace olive olivedrab "
        "orange orangered orchid palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru "
        "pink plum powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown "
        "seagreen seashell sienna silver skyblue slateblue slategray slategrey snow springgreen steelblue tan "
        "teal thistle tomato transparent turquoise violet wheat white whitesmoke yellow yellowgreen"
    ).split()
)
_HTML_FONT_SIZE_RE = re.compile(r"[+-]?[1-7]\Z")
_HTML_INTEGER_RE = re.compile(r"\d{1,4}\Z")


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
        if (
            self._skip_depth
            or tag not in SAFE_NOTE_HTML_TAGS
            or tag in VOID_NOTE_HTML_TAGS
        ):
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
        style_values: list[str] = []
        for name, value in attrs:
            name = name.lower()
            if name.startswith("on") or name not in allowed_attrs or value is None:
                continue
            if name == "style":
                value = _sanitized_style_value(value)
                if value is None:
                    continue
                style_values.append(value)
                continue
            if name in seen_attrs:
                continue
            seen_attrs.add(name)
            if name == "color":
                value = _sanitized_color_attr_value(value)
                if value is None:
                    continue
            elif name == "face":
                value = _sanitized_font_family_attr_value(value)
                if value is None:
                    continue
            elif name == "size":
                value = _sanitized_font_size_attr_value(value)
                if value is None:
                    continue
            elif name == "align":
                value = _sanitized_align_value(value)
                if value is None:
                    continue
            elif name == "type":
                value = _sanitized_list_type_value(tag, value)
                if value is None:
                    continue
            elif name in {"start", "value"}:
                value = _sanitized_integer_attr_value(value)
                if value is None:
                    continue
            if not _is_safe_attr_value(value):
                continue
            parts.append(f' {name}="{escape(value, quote=True)}"')
        style_value = "; ".join(style_values)
        if style_value and _is_safe_attr_value(style_value):
            parts.append(f' style="{escape(style_value, quote=True)}"')
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
    if any(char in lower_value for char in ("\\", "@")):
        return False
    if any(marker in lower_value for marker in UNSAFE_NOTE_HTML_VALUE_MARKERS):
        return False
    if property_name in {"background-color", "color"}:
        return _is_safe_color_value(value)
    if property_name == "font-family":
        return _is_safe_font_family_value(value)
    if property_name == "font-size":
        return (
            lower_value in _CSS_FONT_SIZE_KEYWORDS
            or _CSS_LENGTH_RE.fullmatch(lower_value) is not None
        )
    if property_name == "font-style":
        return lower_value in {"italic", "normal", "oblique"}
    if property_name == "font-weight":
        return (
            lower_value in {"bold", "bolder", "lighter", "normal"}
            or _CSS_FONT_WEIGHT_RE.fullmatch(lower_value) is not None
        )
    if property_name == "line-height":
        return (
            lower_value == "normal"
            or _CSS_NUMBER_RE.fullmatch(lower_value) is not None
            or _CSS_LENGTH_RE.fullmatch(lower_value) is not None
        )
    if property_name in {
        "margin-bottom",
        "margin-left",
        "margin-right",
        "margin-top",
        "text-indent",
    }:
        return lower_value == "0" or _CSS_LENGTH_RE.fullmatch(lower_value) is not None
    if property_name == "text-align":
        return lower_value in SAFE_NOTE_ALIGN_VALUES
    if property_name == "text-decoration":
        values = lower_value.split()
        return bool(values) and all(
            token in {"line-through", "none", "overline", "underline"}
            for token in values
        )
    if property_name == "vertical-align":
        return lower_value in {"baseline", "sub", "super"}
    return False


def _is_safe_color_value(value: str) -> bool:
    value = value.strip()
    lower_value = value.lower()
    if _CSS_COLOR_RE.fullmatch(value) is not None or lower_value in _CSS_NAMED_COLORS:
        return True
    return _CSS_RGB_COLOR_RE.fullmatch(
        lower_value
    ) is not None and _is_safe_rgb_color_value(lower_value)


def _is_safe_rgb_color_value(value: str) -> bool:
    channels = value[value.find("(") + 1 : -1].split(",")
    if len(channels) not in {3, 4}:
        return False
    for channel in channels[:3]:
        channel = channel.strip()
        maximum = 100.0 if channel.endswith("%") else 255.0
        if float(channel.rstrip("%")) > maximum:
            return False
    if len(channels) == 4:
        alpha = channels[3].strip()
        maximum = 100.0 if alpha.endswith("%") else 1.0
        if float(alpha.rstrip("%")) > maximum:
            return False
    return True


def _is_safe_font_family_value(value: str) -> bool:
    if len(value) > 128 or not any(char.isalnum() for char in value):
        return False
    return all(char.isalnum() or char in " ,'\"._-" for char in value)


def _sanitized_color_attr_value(value: str) -> str | None:
    value = value.strip()
    return value if _is_safe_color_value(value) else None


def _sanitized_font_family_attr_value(value: str) -> str | None:
    value = value.strip()
    return value if _is_safe_font_family_value(value) else None


def _sanitized_font_size_attr_value(value: str) -> str | None:
    value = value.strip()
    return value if _HTML_FONT_SIZE_RE.fullmatch(value) is not None else None


def _sanitized_list_type_value(tag: str, value: str) -> str | None:
    value = value.strip()
    if tag == "ol" and value in {"1", "A", "I", "a", "i"}:
        return value
    lower_value = value.lower()
    if tag == "ul" and lower_value in {"circle", "disc", "square"}:
        return lower_value
    if tag == "li" and (
        value in {"1", "A", "I", "a", "i"}
        or lower_value in {"circle", "disc", "square"}
    ):
        return value if value in {"1", "A", "I", "a", "i"} else lower_value
    return None


def _sanitized_integer_attr_value(value: str) -> str | None:
    value = value.strip()
    return value if _HTML_INTEGER_RE.fullmatch(value) is not None else None


__all__ = ["MAX_NOTE_HTML_CHARS", "sanitize_note_html"]
