from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QPointF, QRectF

from chemvas.features.export import content_bounds, export_item_closure
from chemvas.features.scheme_layout import (
    MAX_LAYOUT_ROWS,
    LayoutBlock,
    LayoutRequest,
    merged_layout_groups,
    wrap_layout_row,
)
from chemvas.ui.canvas_atom_graphics_state import atom_items_for
from chemvas.ui.canvas_bond_graphics_state import bond_items_for
from chemvas.ui.canvas_document_state import document_item_lists_for
from chemvas.ui.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas_model_access import model_for
from chemvas.ui.canvas_scene_items_state import ring_items_for
from chemvas.ui.layout_qa_service import note_paint_scene_path
from chemvas.ui.move_access import move_atoms_for, move_item_for
from chemvas.ui.scene_item_access import apply_scene_item_state
from chemvas.ui.scene_item_state import scene_item_state_for

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsItem, QGraphicsTextItem

    from chemvas.ui.canvas_view import CanvasView


@dataclass(frozen=True)
class _Caption:
    index: int
    item: QGraphicsTextItem
    bounds: QRectF
    baseline: float


@dataclass(frozen=True)
class _Block:
    request: LayoutBlock
    bounds: QRectF
    anchor_y: float
    captions: tuple[_Caption, ...]

    @property
    def width(self) -> float:
        return max(self.bounds.width(), *(c.bounds.width() for c in self.captions), 0.0)


@dataclass(frozen=True)
class _Line:
    source_row: int
    source_start: int
    blocks: tuple[_Block, ...]
    arrows: tuple[int, ...]
    leading_arrow: int | None = None


@dataclass(frozen=True)
class CanvasLayoutPlan:
    """Measured moves and requested colors; planning never changes the canvas."""

    atom_moves: tuple[tuple[LayoutBlock, float, float], ...]
    item_moves: dict[tuple[str, int], tuple[float, float]]
    report: dict[str, object]
    arrow_colors: dict[int, str] = field(default_factory=dict)


def _caption(index: int, item: QGraphicsTextItem) -> _Caption:
    document = item.document()
    assert document is not None
    block = document.begin()
    while block.isValid():
        if block.textList() is not None:
            raise ValueError(
                f"note {index} uses an automatic list and cannot be a caption level; "
                "keep it as a group item by omitting its caption number"
            )
        block = block.next()
    bounds = note_paint_scene_path(item).boundingRect()
    if bounds.isEmpty():
        raise ValueError(f"caption note {index} has no visible text")
    layout = document.firstBlock().layout()
    if layout is None or layout.lineCount() == 0:
        raise ValueError(f"caption note {index} has no text baseline")
    line = layout.lineAt(0)
    baseline = item.mapToScene(
        QPointF(0.0, layout.position().y() + line.y() + line.ascent())
    ).y()
    return _Caption(index, item, bounds, baseline)


def _block(
    canvas: CanvasView, request: LayoutBlock, items: dict[str, list[Any]]
) -> _Block:
    bounds = _molecular_bounds(
        canvas,
        set(request.atoms),
        [items[kind][index] for kind, index in request.items],
    )
    model = model_for(canvas)
    anchor_y = (
        model.atoms[request.anchor_atom].y
        if request.anchor_atom is not None
        else bounds.center().y()
    )
    return _Block(
        request,
        bounds,
        anchor_y,
        tuple(_caption(index, items["notes"][index]) for index in request.captions),
    )


def _molecular_bounds(
    canvas: CanvasView,
    atom_ids: set[int],
    extra: list[QGraphicsItem] | None = None,
) -> QRectF:
    labels = atom_items_for(canvas)
    graphics: list[QGraphicsItem] = [labels[a] for a in atom_ids if a in labels]
    model = model_for(canvas)
    for bond_id, pieces in bond_items_for(canvas).items():
        if model.bonds[bond_id].a in atom_ids:
            graphics.extend(pieces)
    registry = mark_registry_for(canvas)
    for atom_id in atom_ids:
        graphics.extend(registry.get_for_atom(atom_id) or [])
    for ring in ring_items_for(canvas):
        if set(ring.data(2) or []).issubset(atom_ids):
            graphics.append(ring)
    graphics.extend(extra or [])
    bounds = content_bounds(export_item_closure(graphics))
    if bounds is None:
        raise ValueError("each layout block must contain visible structure geometry")
    return bounds


def _rect_values(bounds: QRectF) -> list[float]:
    return [bounds.left(), bounds.top(), bounds.right(), bounds.bottom()]


def _plan_align_y(canvas: CanvasView, request: LayoutRequest) -> CanvasLayoutPlan:
    atom_moves: list[tuple[LayoutBlock, float, float]] = []
    item_moves: dict[tuple[str, int], tuple[float, float]] = {}
    placements: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    extent = QRectF()
    for row_index, row in enumerate(request.rows):
        bounds = [_molecular_bounds(canvas, set(block.atoms)) for block in row.blocks]
        references = row.reference_blocks or tuple(range(len(row.blocks)))
        target = (
            min(bounds[i].top() for i in references)
            + max(bounds[i].bottom() for i in references)
        ) / 2
        rows.append(
            {"row": row_index, "reference_blocks": list(references), "target_y": target}
        )
        for column, block in enumerate(row.blocks):
            for part_index, part in enumerate(block.parts or (block.atoms,)):
                before = _molecular_bounds(canvas, set(part))
                dy = target - before.center().y()
                after = before.translated(0, dy)
                extent = extent.united(after)
                atom_moves.append((LayoutBlock(part), 0.0, dy))
                placements.append(
                    {
                        "row": row_index,
                        "column": column,
                        "part": part_index,
                        "atoms": list(part),
                        "center_x": before.center().x(),
                        "anchor_y": target,
                        "dx": 0.0,
                        "dy": dy,
                        "bounds_before": _rect_values(before),
                        "bounds_after": _rect_values(after),
                    }
                )
            for kind, index in block.items:
                if kind != "notes":
                    item_moves[(kind, index)] = (0.0, dy)
    return CanvasLayoutPlan(
        tuple(atom_moves),
        item_moves,
        {
            "mode": "align-y",
            "row_count": len(rows),
            "block_count": sum(len(row.blocks) for row in request.rows),
            "part_count": len(atom_moves),
            "rows": rows,
            "placements": placements,
            "layout_width": extent.width(),
            "layout_height": extent.height(),
            "bounds_scope": "aligned molecular paint only; fixed notes and decorations excluded",
        },
    )


def _line_geometry(
    request: LayoutRequest,
    rows: list[tuple[_Block, ...]],
    arrow_bounds: dict[int, QRectF],
) -> tuple[
    list[_Line],
    dict[int | str, list[float]],
    dict[int | str, list[float]],
    dict[int | str, float],
]:
    """Resolve line breaks and widths before any scene mutation."""
    wrapped = request.max_row_width is not None
    lines: list[_Line] = []
    for source_row, (row_request, blocks) in enumerate(
        zip(request.rows, rows, strict=True)
    ):
        slices: tuple[tuple[int, int], ...]
        if request.max_row_width is None:
            slices = ((0, len(blocks)),)
        else:
            try:
                slices = wrap_layout_row(
                    [block.width for block in blocks],
                    [arrow_bounds[index].width() for index in row_request.arrows],
                    gap=request.gap,
                    max_row_width=request.max_row_width,
                )
            except ValueError as exc:
                raise ValueError(f"source row {source_row}: {exc}") from exc
        for start, stop in slices:
            lines.append(
                _Line(
                    source_row,
                    start,
                    blocks[start:stop],
                    row_request.arrows[start : stop - 1],
                    row_request.arrows[start - 1]
                    if start and row_request.arrows
                    else None,
                )
            )
    if len(lines) > MAX_LAYOUT_ROWS:
        raise ValueError(f"wrapped layout exceeds the {MAX_LAYOUT_ROWS}-row limit")

    # Explicit comparison groups share columns only with their own rows;
    # ungrouped rows retain block-count sharing. Captions count toward cell
    # widths. Width-limited lines keep independent widths to respect the budget.
    columns: dict[int | str, list[float]] = {}
    slots: dict[int | str, list[float]] = {}
    for line_index, line in enumerate(lines):
        count = len(line.blocks)
        key = _column_key(request, line, line_index)
        widths = columns.setdefault(key, [0.0] * count)
        gaps = slots.setdefault(key, [request.gap] * (count - 1))
        for index, block in enumerate(line.blocks):
            widths[index] = max(widths[index], block.width)
        for index, arrow_index in enumerate(line.arrows):
            gaps[index] = max(
                gaps[index], arrow_bounds[arrow_index].width() + 2 * request.gap
            )
    row_widths = {
        count: sum(widths) + sum(slots[count]) for count, widths in columns.items()
    }
    if wrapped:
        for line_index, line in enumerate(lines):
            if line.leading_arrow is not None:
                row_widths[line_index] += (
                    arrow_bounds[line.leading_arrow].width() + request.gap
                )
            assert request.max_row_width is not None
            if row_widths[line_index] > request.max_row_width + 1e-6:
                raise ValueError(
                    f"display row {line_index} exceeds max_row_width after measuring "
                    "all native structure, caption and arrow bounds"
                )
    return lines, columns, slots, row_widths


def _column_key(request: LayoutRequest, line: _Line, index: int) -> int | str:
    if request.max_row_width is not None:
        return index
    return request.rows[line.source_row].column_group or len(line.blocks)


def _place_row_captions(
    blocks: tuple[_Block, ...],
    centers: list[float],
    caption_top: float,
    request: LayoutRequest,
    item_moves: dict[tuple[str, int], tuple[float, float]],
) -> float:
    levels = max(len(block.captions) for block in blocks)
    for level in range(levels):
        captions = [
            block.captions[level] for block in blocks if level < len(block.captions)
        ]
        ascent = max(c.baseline - c.bounds.top() for c in captions)
        descent = max(c.bounds.bottom() - c.baseline for c in captions)
        baseline = caption_top + ascent
        for center, block in zip(centers, blocks, strict=True):
            if level < len(block.captions):
                caption = block.captions[level]
                item_moves[("notes", caption.index)] = (
                    center - caption.bounds.center().x(),
                    baseline - caption.baseline,
                )
        caption_top = baseline + descent + request.line_gap
    return caption_top - request.line_gap


def _place_structure_captions(
    blocks: tuple[_Block, ...],
    centers: list[float],
    axis: float,
    request: LayoutRequest,
    item_moves: dict[tuple[str, int], tuple[float, float]],
) -> tuple[float, list[dict[str, object]]]:
    bottom = axis
    placements: list[dict[str, object]] = []
    for column, (center, block) in enumerate(zip(centers, blocks, strict=True)):
        caption_top = (
            axis + block.bounds.bottom() - block.anchor_y + request.caption_gap
        )
        for caption in block.captions:
            item_moves[("notes", caption.index)] = (
                center - caption.bounds.center().x(),
                caption_top - caption.bounds.top(),
            )
            caption_bottom = caption_top + caption.bounds.height()
            placements.append(
                {
                    "column": column,
                    "note": caption.index,
                    "center_x": center,
                    "top": caption_top,
                    "bottom": caption_bottom,
                }
            )
            bottom = max(bottom, caption_bottom)
            caption_top = caption_bottom + request.line_gap
    return bottom, placements


def plan_canvas_layout(
    canvas: CanvasView, source: dict[str, Any], request: LayoutRequest
) -> CanvasLayoutPlan:
    """Measure native paint and validate all line budgets before any mutation."""
    if request.mode == "align-y":
        return _plan_align_y(canvas, request)
    items = document_item_lists_for(canvas)
    rows = [
        tuple(_block(canvas, block, items) for block in row.blocks)
        for row in request.rows
    ]
    arrow_bounds: dict[int, QRectF] = {}
    arrow_axes: dict[int, float] = {}
    for row in request.rows:
        for index in row.arrows:
            arrow = items["arrows"][index]
            bounds = content_bounds(export_item_closure([arrow]))
            if bounds is None:
                raise ValueError(f"row arrow {index} has no visible geometry")
            arrow_bounds[index] = bounds
            arrow_axes[index] = float(source["arrows"][index]["start"][1])

    wrapped = request.max_row_width is not None
    lines, columns, slots, row_widths = _line_geometry(request, rows, arrow_bounds)
    total_width = max(row_widths.values())
    top = 0.0
    atom_moves: list[tuple[LayoutBlock, float, float]] = []
    item_moves: dict[tuple[str, int], tuple[float, float]] = {}
    placements: list[dict[str, object]] = []
    line_provenance: list[dict[str, object]] = []
    caption_placements: list[dict[str, object]] = []

    for row_number, line in enumerate(lines):
        blocks = line.blocks
        count = len(blocks)
        key = _column_key(request, line, row_number)
        above = max(block.anchor_y - block.bounds.top() for block in blocks)
        below = max(block.bounds.bottom() - block.anchor_y for block in blocks)
        line_arrows = line.arrows + (
            (line.leading_arrow,) if line.leading_arrow is not None else ()
        )
        for index in line_arrows:
            above = max(above, arrow_axes[index] - arrow_bounds[index].top())
            below = max(below, arrow_bounds[index].bottom() - arrow_axes[index])
        axis = top + above
        cursor = 0.0 if wrapped else (total_width - row_widths[key]) / 2
        if line.leading_arrow is not None:
            index = line.leading_arrow
            bounds = arrow_bounds[index]
            item_moves[("arrows", index)] = (-bounds.left(), axis - arrow_axes[index])
            cursor = bounds.width() + request.gap
        if wrapped:
            line_provenance.append(
                {
                    "display_row": row_number,
                    "source_row": line.source_row,
                    "source_columns": list(
                        range(line.source_start, line.source_start + count)
                    ),
                    "leading_arrow": line.leading_arrow,
                    "arrows": list(line.arrows),
                    "width": row_widths[key],
                }
            )
        centers = []
        for column, block in enumerate(blocks):
            center = cursor + columns[key][column] / 2
            centers.append(center)
            dx, dy = center - block.bounds.center().x(), axis - block.anchor_y
            atom_moves.append((block.request, dx, dy))
            for reference in block.request.items:
                item_moves[reference] = (dx, dy)
            placements.append(
                {
                    "row": row_number,
                    "column": column,
                    "atoms": list(block.request.atoms),
                    "center_x": center,
                    "anchor_y": axis,
                    "dx": dx,
                    "dy": dy,
                }
            )
            if wrapped:
                placements[-1].update(
                    source_row=line.source_row,
                    source_column=line.source_start + column,
                )
            cursor += columns[key][column]
            if column < count - 1:
                if line.arrows:
                    index = line.arrows[column]
                    bounds = arrow_bounds[index]
                    item_moves[("arrows", index)] = (
                        cursor + slots[key][column] / 2 - bounds.center().x(),
                        axis - arrow_axes[index],
                    )
                cursor += slots[key][column]

        row_bottom = axis + below
        if request.caption_alignment == "structure":
            caption_bottom, records = _place_structure_captions(
                blocks, centers, axis, request, item_moves
            )
            row_bottom = max(row_bottom, caption_bottom)
            caption_placements.extend(
                {"row": row_number, **record} for record in records
            )
        elif any(block.captions for block in blocks):
            row_bottom = _place_row_captions(
                blocks, centers, row_bottom + request.caption_gap, request, item_moves
            )
        top = row_bottom + request.row_gap

    report: dict[str, object] = {
        "row_count": len(lines),
        "block_count": len(atom_moves),
        "layout_width": total_width,
        "layout_height": top - request.row_gap,
        "placements": placements,
    }
    if wrapped:
        report.update(
            max_row_width=request.max_row_width,
            logical_row_count=len(rows),
            lines=line_provenance,
        )
    if any(row.column_group is not None for row in request.rows):
        report["column_groups"] = [row.column_group for row in request.rows]
    if request.caption_alignment != "row":
        report.update(
            caption_alignment=request.caption_alignment,
            caption_placements=caption_placements,
        )
    arrow_colors = {
        index: request.arrow_color
        for row in request.rows
        for index in row.arrows
        if request.arrow_color is not None
    }
    if arrow_colors:
        report["arrow_color_changes"] = [
            {
                "arrow": index,
                "before": source["arrows"][index].get("color"),
                "after": color,
            }
            for index, color in arrow_colors.items()
        ]
    return CanvasLayoutPlan(tuple(atom_moves), item_moves, report, arrow_colors)


def arrange_canvas(
    canvas: CanvasView, source: dict[str, Any], request: LayoutRequest
) -> tuple[dict[str, Any], dict[str, object]]:
    """Arrange a disposable canvas without rewriting text or molecular properties.

    Text HTML and unselected records retain their exact source values. Only
    explicitly requested row-arrow colors change outside geometry and groups.
    """
    plan = plan_canvas_layout(canvas, source, request)
    items = document_item_lists_for(canvas)
    for index, color in plan.arrow_colors.items():
        arrow = items["arrows"][index]
        state = scene_item_state_for(canvas, arrow)
        apply_scene_item_state(canvas, arrow, {**state, "color": color})
    for block_request, dx, dy in plan.atom_moves:
        move_atoms_for(canvas, set(block_request.atoms), dx, dy, update_selection=False)
    for (kind, index), (dx, dy) in plan.item_moves.items():
        move_item_for(canvas, items[kind][index], dx, dy, update_selection=False)

    candidate = deepcopy(source)
    for index, color in plan.arrow_colors.items():
        candidate["arrows"][index]["color"] = color
    selected_atoms = {atom for block, _, _ in plan.atom_moves for atom in block.atoms}
    model = model_for(canvas)
    for atom_id, atom in candidate["model"]["atoms"].items():
        if int(atom_id) in selected_atoms:
            live = model.atoms[int(atom_id)]
            if request.mode == "align-y":
                atom["y"] = live.y
            else:
                atom.update(x=live.x, y=live.y)
    for ring in candidate.get("ring_fills", []):
        if set(ring["atom_ids"]).issubset(selected_atoms):
            if request.mode == "align-y":
                atom = ring["atom_ids"][0]
                original = source["model"]["atoms"].get(
                    atom, source["model"]["atoms"].get(str(atom))
                )
                dy = model.atoms[atom].y - original["y"]
                ring["points"] = [[x, y + dy] for x, y in ring["points"]]
            else:
                ring["points"] = [
                    [model.atoms[a].x, model.atoms[a].y] for a in ring["atom_ids"]
                ]
    for index, mark in enumerate(candidate.get("marks", [])):
        if mark.get("atom_id") in selected_atoms:
            current = scene_item_state_for(canvas, items["marks"][index])
            if request.mode == "align-y":
                mark["y"] = current["y"]
            else:
                mark.update(x=current["x"], y=current["y"])
    coordinate_keys = {
        "notes": ("x", "y"),
        "ts_brackets": ("left", "top", "right", "bottom"),
        "shapes": ("left", "top", "right", "bottom"),
        "arrows": ("start", "end", "control"),
    }
    for kind, index in plan.item_moves:
        current = scene_item_state_for(canvas, items[kind][index])
        for coordinate_key in coordinate_keys[kind]:
            if coordinate_key in candidate[kind][index]:
                if request.mode == "align-y" and coordinate_key in {
                    "x",
                    "left",
                    "right",
                    "control",
                }:
                    continue
                if request.mode == "align-y" and coordinate_key in {"start", "end"}:
                    old = candidate[kind][index][coordinate_key]
                    candidate[kind][index][coordinate_key] = [
                        old[0],
                        current[coordinate_key][1],
                    ]
                else:
                    candidate[kind][index][coordinate_key] = current[coordinate_key]
    if request.mode != "align-y":
        candidate["groups"] = merged_layout_groups(source, request)
    return candidate, plan.report


__all__ = ["CanvasLayoutPlan", "arrange_canvas", "plan_canvas_layout"]
