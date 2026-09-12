"""Arrow-label mini-syntax: ``_`` starts a subscript, ``^`` a superscript.

A marker applies to the braced group that follows it, or else to the run of
characters up to the next space or marker, so ``k_-1``, ``K_{eq}`` and
``ΔG^‡`` read the way a chemist types them. A marker with nothing after it is
shown literally.
"""

from __future__ import annotations

import html

from .label_layout import LabelRun

_MARKER_ROLES = {"_": "sub", "^": "super"}


def _append_run(runs: list[LabelRun], text: str, role: str) -> None:
    if not text:
        return
    if runs and runs[-1].role == role:
        runs[-1] = LabelRun(runs[-1].text + text, role)
        return
    runs.append(LabelRun(text, role))


def parse_arrow_label(text: str) -> tuple[LabelRun, ...]:
    runs: list[LabelRun] = []
    normal: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        role = _MARKER_ROLES.get(char)
        if role is None:
            normal.append(char)
            index += 1
            continue
        rest = text[index + 1 :]
        if rest.startswith("{"):
            close = rest.find("}")
            group = rest[1:close] if close >= 0 else rest[1:]
            consumed = 1 + (close + 1 if close >= 0 else len(rest))
        else:
            group_chars: list[str] = []
            for next_char in rest:
                if next_char.isspace() or next_char in _MARKER_ROLES:
                    break
                group_chars.append(next_char)
            group = "".join(group_chars)
            consumed = 1 + len(group)
        if not group:
            normal.append(char)
            index += 1
            continue
        _append_run(runs, "".join(normal), "normal")
        normal = []
        _append_run(runs, group, role)
        index += consumed
    _append_run(runs, "".join(normal), "normal")
    return tuple(runs)


def arrow_label_html(text: str) -> str:
    parts: list[str] = []
    for run in parse_arrow_label(text):
        escaped = (
            html.escape(run.text)
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\n", "<br>")
        )
        if run.role == "sub":
            parts.append(f"<sub>{escaped}</sub>")
        elif run.role == "super":
            parts.append(f"<sup>{escaped}</sup>")
        else:
            parts.append(escaped)
    return "".join(parts)


__all__ = ["arrow_label_html", "parse_arrow_label"]
