"""Arrow-label mini-syntax: ``_`` starts a subscript, ``^`` a superscript.

A marker applies to the braced group that follows it, or else to the run of
characters up to the next space or marker, so ``k_-1``, ``K_{eq}`` and
``ΔG^‡`` read the way a chemist types them. A marker with nothing after it is
shown literally.
"""

from __future__ import annotations

import html
import math
from typing import TYPE_CHECKING

from chemvas.domain.document import ARC_KIND_SWEEPS, ARROW_LABEL_SIDES

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chemvas.domain.document import Arrow

from .label_layout import LabelRun

_MARKER_ROLES = {"_": "sub", "^": "super"}


def _append_run(runs: list[LabelRun], text: str, role: str) -> None:
    if not text:
        return
    if runs and runs[-1].role == role:
        runs[-1] = LabelRun(runs[-1].text + text, role)
        return
    runs.append(LabelRun(text, role))


# The label dialog previews on paper in the interface font at this size.
ARROW_LABEL_PREVIEW_POINT_SIZE = 14

LABEL_SYNTAX_HINT = (
    "Use _{...} for subscripts and ^{...} for superscripts. "
    "Examples: K_{2}CO_{3}, H_{2}SO_{4}, ΔG^{‡}.\n"
    "Without braces, _ or ^ applies until the next space, _ or ^. "
    "Braces do not nest and backslash escaping is not supported. "
    "A trailing _ or ^, or one followed by a space, is literal. "
    "Enter inserts a line break; Tab moves to the next field. "
    "Each field is limited to 200 characters; shorten longer text before OK, "
    "or use a Note. "
    "Leave a field empty to remove that label."
)


def cleaned_arrow_labels(labels: Mapping[str, str]) -> dict[str, str]:
    return {
        side: text
        for side, text in labels.items()
        if side in ARROW_LABEL_SIDES and text.strip()
    }


def arrow_label_position(
    record: Arrow,
    path_points: list[tuple[float, float]],
    *,
    bond_spacing: float,
    side: str,
    width: float,
    height: float,
) -> tuple[float, float]:
    """Native label placement; adapters supply their font engine's box size."""
    from chemvas.features.rendering import arc_midpoint, curved_midpoint

    start, end, control = record.start, record.end, record.control
    if control is not None:
        mid = curved_midpoint(start, control, end)
    elif record.kind in ARC_KIND_SWEEPS:
        sweep, left = ARC_KIND_SWEEPS[record.kind]
        mid = arc_midpoint(start, end, sweep_degrees=sweep, bulge_left=left)
    else:
        mid = ((start[0] + end[0]) * 0.5, (start[1] + end[1]) * 0.5)
    nx, ny = arrow_label_normal(end[0] - start[0], end[1] - start[1])
    # Measure how far the arrow's own strokes (harpoons, barbs) reach
    # from the axis along the normal, so the label clears them at any
    # bond length; a curved arrow's or arc's chord ends are not part of
    # that, since their labels sit at the curve midpoint instead.
    extent = 0.0
    if control is None and record.kind not in ARC_KIND_SWEEPS:
        for x, y in path_points:
            extent = max(extent, abs((x - mid[0]) * nx + (y - mid[1]) * ny))
    gap = extent + bond_spacing
    # Half of the label box projected onto the normal, so a vertical
    # arrow clears the label's width and a horizontal one its height.
    half_extent = abs(nx) * width * 0.5 + abs(ny) * height * 0.5
    distance = gap + half_extent
    sign = 1.0 if side == "above" else -1.0
    return (
        mid[0] + nx * sign * distance - width * 0.5,
        mid[1] + ny * sign * distance - height * 0.5,
    )


def arrow_label_normal(dx: float, dy: float) -> tuple[float, float]:
    """The readable Above side: toward smaller y, or left for vertical arrows."""
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    if ny > 1e-9 or (abs(ny) <= 1e-9 and nx > 0.0):
        nx, ny = -nx, -ny
    return nx, ny


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


__all__ = [
    "ARROW_LABEL_PREVIEW_POINT_SIZE",
    "LABEL_SYNTAX_HINT",
    "arrow_label_html",
    "arrow_label_normal",
    "arrow_label_position",
    "cleaned_arrow_labels",
    "parse_arrow_label",
]
