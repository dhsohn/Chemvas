"""Local browser adapter over existing Chemvas UI definitions and editing services."""

from __future__ import annotations

import argparse
import json
import math
import secrets
import sys
import webbrowser
from contextlib import nullcontext, suppress
from copy import deepcopy
from dataclasses import asdict, dataclass
from decimal import Decimal
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast, override

from chemvas.core.history import HistoryCommand
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    VALID_ARC_KINDS,
    Bond,
    arrow_from_state,
    arrow_to_state,
    atom_shows_itself,
    broken_ring_fill_indices,
    build_normalized_document_payload,
    deserialize_model_state,
    extract_document_state,
    mirrored_arc_kind,
    model_bond_pairs,
    normalize_json_numbers,
    serialize_model_state_with_warnings,
)
from chemvas.domain.document.ring_fills import RingFill, ring_fill_to_state
from chemvas.domain.json_io import strict_json_loads
from chemvas.domain.transactions import RestoreOutcome
from chemvas.features.annotations import (
    SUB_SCALE,
    atom_label_presentation,
    hydride_hydrogen_text,
    parse_atom_label,
    place_hydride_stack,
    place_runs,
    split_hydride_label,
    uses_compact_label_hit_shape,
)
from chemvas.features.document_composition import compose_document_state
from chemvas.features.graph import (
    CanvasGraphState,
    add_bond_to_atom_index,
    build_ring_edge_index,
    ring_atom_ids_for_bond,
)
from chemvas.features.rendering import (
    ENDPOINT_SNAP_SCREEN_PX,
    ACS1996Style,
    RenderMetrics,
    arrow_path_commands,
    cycle_plain_bond_style,
    line_normal,
    new_arrow_record,
    snapped_drawing_point,
)
from chemvas.features.selection import (
    AtomHitCandidate,
    BondHitCandidate,
    choose_preferred_structure_hit,
    distance_point_to_segment,
    nearest_atom_id,
    nearest_bond_id,
    selected_atom_ids_with_bond_endpoints,
)
from chemvas.shell import toolbar_styles
from chemvas.shell.icon_design import DESIGN_ICON_NAMES, design_icon_svg
from chemvas.shell.palette import PALETTE
from chemvas.ui.canvas.canvas_chemdraw_shortcut_service import (
    CanvasChemdrawShortcutService,
)
from chemvas.ui.canvas.canvas_geometry_logic import (
    glyph_clearance_radius,
    glyph_contour_clip_t,
    glyph_convex_hull,
)
from chemvas.ui.canvas.canvas_history_service import CanvasHistoryService
from chemvas.ui.canvas.canvas_history_state import CanvasHistoryState
from chemvas.ui.canvas.canvas_mark_registry import CanvasMarkRegistry
from chemvas.ui.canvas.canvas_move_controller import CanvasMoveController
from chemvas.ui.canvas.canvas_ring_fill_scene_service import rebuild_ring_fill_polygons
from chemvas.ui.canvas.canvas_tool_settings_state import CanvasToolSettingsState
from chemvas.ui.canvas.pick_radius_access import (
    STRUCTURE_BOND_PICK_RADIUS_RATIO,
    atom_pick_radius,
    atom_pick_radius_for,
)
from chemvas.ui.canvas.sheet_setup_logic import (
    OFF_SHEET_EDIT_GUIDANCE,
    scene_pos_in_sheet,
    sheet_dimensions_px,
)
from chemvas.ui.insert.insert_mode_logic import (
    TEMPLATE_BOND_GATE_RATIO,
)
from chemvas.ui.molecule.atom_label_merge_service import AtomLabelMergeService
from chemvas.ui.molecule.atom_label_service import AtomLabelService
from chemvas.ui.molecule.bond_geometry_plan_service import (
    BondGeometryPlanService,
    BondLinePrimitive,
    BondPathPrimitive,
    BondPolygonPrimitive,
)
from chemvas.ui.molecule.bond_graphics_draw_service import BondGraphicsDrawService
from chemvas.ui.molecule.bond_line_geometry_service import BondLineGeometryService
from chemvas.ui.molecule.bond_ring_double_geometry_service import (
    BondRingDoubleGeometryService,
)
from chemvas.ui.molecule.structure_benzene_build_service import (
    StructureBenzeneBuildService,
)
from chemvas.ui.molecule.structure_bond_build_service import StructureBondBuildService
from chemvas.ui.molecule.structure_build_committer import StructureBuildCommitter
from chemvas.ui.molecule.structure_geometry_access import (
    cyclohexane_chair_points_for,
    default_bond_endpoint_for,
    regular_ring_points_for_atom_for,
    regular_ring_points_for_bond_for,
    sprout_bond_endpoint_for,
    template_points_for_bond_for,
)
from chemvas.ui.molecule.structure_growth_build_service import (
    StructureGrowthBuildActions,
    StructureGrowthBuildService,
)
from chemvas.ui.molecule.structure_growth_geometry import resolve_bond_placement_context
from chemvas.ui.molecule.template_geometry import polygon_contains_point
from chemvas.ui.scene.scene_delete_plan import (
    DeleteSelectionBuckets,
    build_delete_selection_plan,
    hover_delete_target,
)
from chemvas.ui.tools.bond_tool_logic import (
    BOND_PICK_RADIUS_RATIO,
    BOND_SNAP_RADIUS_RATIO,
    apply_active_bond_style,
    is_short_bond_gesture,
    resolve_bond_endpoint_target,
    resolve_bond_press_target,
    resolve_bond_snap_target,
)
from chemvas.ui.tools.text_tool_logic import (
    TextToolTarget,
    apply_text_input,
    normalize_text_symbol,
    plan_text_input,
    resolve_text_tool_target,
)
from chemvas.ui.window.main_window_config import (
    ARROW_MENU_SPECS,
    ARROW_PRESET_SPECS,
    ATOM_INPUT_SPEC,
    BOND_MODIFIERS,
    BOND_ORDER_SEGMENTS,
    MORE_ARROW_KINDS,
    RING_FILL_TOOL_ACTION_SPEC,
    TOOL_ACTION_SPECS,
    TOOL_HINTS,
    TOOL_HOTKEYS,
    TOOLBAR_TOOL_GROUPS,
    WHEEL_ANGLE_PER_PIXEL,
    WHEEL_ZOOM_BASE,
    ZOOM_MAX,
    ZOOM_MIN,
    ZOOM_STEP,
)
from chemvas.ui.window.main_window_toolbar_logic import (
    BOND_STYLE_BY_LABEL,
    bond_style_from_label,
)

if TYPE_CHECKING:
    from collections.abc import Callable

MAX_REQUEST_BYTES = 2 * 1024 * 1024
ASSETS = Path(__file__).resolve().parents[1] / "web"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.mjs": ("app.mjs", "text/javascript; charset=utf-8"),
    "/transport.mjs": ("transport.mjs", "text/javascript; charset=utf-8"),
    "/scene.mjs": ("scene.mjs", "text/javascript; charset=utf-8"),
}
BOND_ORDERS = dict(BOND_STYLE_BY_LABEL.values())
SUPPORTED_BONDS = {
    "single",
    "double",
    "double_center",
    "triple",
    "wedge",
    "hash",
    "bold_in",
    "bold_center",
    "bold_out",
    "dotted",
    "dotted_double",
    "dotted_double_outer",
}


def ui_spec() -> dict[str, Any]:
    """Serialize the desktop's existing declarations, rather than copy its design."""
    tools = {
        key: {
            "key": key,
            "label": label,
            "icon": design_icon_svg(DESIGN_ICON_NAMES[icon]),
            "tip": tip,
        }
        for key, label, _tool, icon, tip in TOOL_ACTION_SPECS
    }
    key, label, icon, tip = RING_FILL_TOOL_ACTION_SPEC
    tools[key] = {
        "key": key,
        "label": label,
        "icon": design_icon_svg(DESIGN_ICON_NAMES[icon]),
        "tip": tip,
    }
    return {
        "groups": [[tools[key] for key in group] for group in TOOLBAR_TOOL_GROUPS],
        "bond_groups": [
            [
                {
                    "key": bond_style_from_label(label)[0],
                    "label": label,
                    "tip": tip,
                    "icon": design_icon_svg(DESIGN_ICON_NAMES[icon]),
                }
                for label, icon, tip in group
            ]
            for group in (BOND_ORDER_SEGMENTS, BOND_MODIFIERS)
        ],
        "arrow_options": [
            {
                "key": kind,
                "label": label,
                "icon": design_icon_svg(f"arrow_{kind}"),
                "more": kind in MORE_ARROW_KINDS,
            }
            for label, kind in ARROW_MENU_SPECS
        ],
        "arrow_style_controls": [
            {
                "label": f"{label} arrow preset",
                "icon": design_icon_svg(f"arrow_preset_{label.lower()}"),
            }
            for label in ARROW_PRESET_SPECS
        ]
        + [
            {"label": label, "icon": design_icon_svg(icon)}
            for label, icon in (
                ("Arrow line width", "arrow_width"),
                ("Arrow head scale", "arrow_head_scale"),
            )
        ],
        # Browsers do not expose the desktop system drag-distance preference.
        "drag_distance": 10,
        "hints": TOOL_HINTS,
        "off_sheet_guidance": OFF_SHEET_EDIT_GUIDANCE,
        "tool_hotkeys": TOOL_HOTKEYS,
        "hover_shortcuts": sorted(
            CanvasChemdrawShortcutService.ATOM_HOTKEYS
            | CanvasChemdrawShortcutService.BOND_HOTKEYS
        ),
        "default_bond_style": CanvasToolSettingsState().active_bond_style,
        "navigation": {
            "zoom_modifier": "meta" if sys.platform == "darwin" else "control",
            "min": ZOOM_MIN,
            "max": ZOOM_MAX,
            "step": ZOOM_STEP,
            "wheel_base": WHEEL_ZOOM_BASE,
            "angle_per_pixel": WHEEL_ANGLE_PER_PIXEL,
        },
        "atom_input": {
            **ATOM_INPUT_SPEC,
            "value": CanvasToolSettingsState().atom_symbol,
        },
        "panels": [
            {"key": key, "label": label, "icon": design_icon_svg(key)}
            for key, label in (
                ("molecule_info", "Molecule Info"),
                ("reaction_mapping", "Reaction Mapping"),
            )
        ],
    }


def ui_css() -> str:
    values = {
        **PALETTE,
        **{
            key.lower(): str(getattr(toolbar_styles, key)) + "px"
            for key in (
                "TOOLBAR_THICKNESS",
                "TOOLBAR_BUTTON_SIZE",
                "TOOLBAR_ICON_SIZE",
                "CONTEXT_BAR_CONTENT_HEIGHT",
                "CONTEXT_BAR_BUTTON_HEIGHT",
                "CONTEXT_BAR_ICON_SIZE",
            )
        },
    }
    return (
        ":root{"
        + ";".join(
            f"--{key.replace('_', '-')}: {value}" for key, value in values.items()
        )
        + "}"
    )


def new_document() -> dict[str, Any]:
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 2,
            "atoms": [],
            "bonds": [],
        }
    )
    return build_normalized_document_payload(state, CANVAS_FILE_VERSION)


def document_info(
    payload: object, *, render: bool = True, font: BrowserFontMeasurements | None = None
) -> dict[str, Any]:
    """Validate without dropping data; unsupported drawings remain read-only."""
    state = extract_document_state(normalize_json_numbers(payload))
    if (
        len(json.dumps(normalize_json_numbers(payload), ensure_ascii=False).encode())
        > MAX_REQUEST_BYTES
    ):
        raise ValueError("The browser adapter supports documents up to 2 MiB.")
    model = state["model"]
    if len(model["atoms"]) > 2000 or len(model["bonds"]) > 3000:
        raise ValueError(
            "The browser adapter supports up to 2,000 atoms and 3,000 bonds."
        )
    reasons = [
        key.replace("_", " ")
        for key in (
            "marks",
            "shapes",
            "images",
            "orbitals",
            "ts_brackets",
            "groups",
            "perspective",
            "calculation_plan",
        )
        if state.get(key)
    ]
    if model.get("atom_annotations"):
        reasons.append("atom charges, isotopes or radicals")
    if any(bond["style"] not in SUPPORTED_BONDS for bond in model["bonds"] if bond):
        reasons.append("additional bond styles")
    if state["notes"]:
        reasons.append("text annotations")
    if any(arrow.get("labels") for arrow in state["arrows"]):
        reasons.append("arrow labels")
    settings = state["settings"]
    if settings.get("note_box_enabled") or settings.get("note_border_enabled"):
        reasons.append("note backgrounds or borders")
    width, height = sheet_dimensions_px(
        settings["sheet_size"],
        settings["sheet_orientation"],
        settings.get("sheet_custom_size_mm"),
    )
    info = {
        "document": normalize_json_numbers(payload),
        "unsupported": reasons,
        "sheet": [width, height],
        "style": asdict(ACS1996Style()),
    }
    if render:
        info["drawing"] = (
            drawing_geometry(state) if font is None else font.drawing(state)
        )
    return info


def browser_font_pixels(point_size: float) -> int:
    # The desktop pins AA_Use96Dpi; QFont resolves that em size to integer pixels.
    return max(1, round(point_size * 96 / 72))


def _browser_label_queries(size: int, labels: Any) -> list[dict[str, Any]]:
    texts = {"H"}
    for display, anchor, _at_end, below in labels:
        texts.update(run.text for run in parse_atom_label(display))
        if anchor:
            texts.add(anchor)
        if below is not None:
            split = split_hydride_label(display)
            assert split is not None
            element, count = split
            texts.update(
                run.text for run in parse_atom_label(hydride_hydrogen_text(count))
            )
            texts.add(element)
    queries = (
        [
            {
                "key": f"{point_size}:{text}",
                "text": text,
                "size": point_size,
                "pixels": browser_font_pixels(point_size),
            }
            for text in sorted(texts)
            for point_size in (size, size * SUB_SCALE)
        ]
        if labels
        else []
    )
    return queries


def browser_label_layouts(model: Any, metrics: RenderMetrics) -> dict[str, Any]:
    """Describe native label presentation without serializing the document twice."""
    labels = {
        str(atom_id): atom_label_presentation(model, atom_id, atom.element)
        for atom_id, atom in model.atoms.items()
        if atom_shows_itself(atom)
    }
    size = metrics.atom_font_size_pt()
    return {
        "family": metrics.style.font_family,
        "size": size,
        "offset": metrics.style.atom_label_offset_px,
        "labels": labels,
        "queries": _browser_label_queries(size, list(labels.values())),
    }


def validate_font_metrics(measurements: Any) -> None:
    if not isinstance(measurements, dict):
        raise ValueError("Expected browser font measurements.")
    for value in measurements.values():
        if not isinstance(value, dict) or set(value) != {
            "width",
            "ascent",
            "descent",
            "cap_height",
            "line_height",
        }:
            raise ValueError(
                "Expected width, ascent, descent, capital height and line height."
            )
        if any(
            type(number) not in (int, float, Decimal)
            or not math.isfinite(number)
            or number < 0
            for number in value.values()
        ):
            raise ValueError("Font measurements must be finite nonnegative numbers.")
        if value["ascent"] <= 0 or value["line_height"] <= 0:
            raise ValueError("Font ascent and line height must be positive.")


def place_browser_labels(request: Any) -> list[list[dict[str, Any]]]:
    """Adapt measured font metrics to the existing native run placer, at origin."""
    if not isinstance(request, dict) or set(request) != {
        "size",
        "labels",
        "measurements",
    }:
        raise ValueError("Expected label presentations and font measurements.")
    size, labels, measurements = (
        request["size"],
        request["labels"],
        request["measurements"],
    )
    if type(size) is not int or size < 1 or not math.isfinite(size):
        raise ValueError("Expected a positive point size.")
    if not isinstance(labels, list) or len(labels) > 2000:
        raise ValueError("Expected up to 2,000 label presentations.")
    for label in labels:
        if not isinstance(label, (list, tuple)) or len(label) != 4:
            raise ValueError("Invalid label presentation.")
        display, anchor, at_end, below = label
        if (
            not isinstance(display, str)
            or not display
            or (anchor is not None and not isinstance(anchor, str))
            or type(at_end) is not bool
            or (below is not None and type(below) is not bool)
            or (below is not None and split_hydride_label(display) is None)
        ):
            raise ValueError("Invalid label presentation.")
    queries = _browser_label_queries(size, labels)
    validate_font_metrics(measurements)
    if not {query["key"] for query in queries}.issubset(measurements):
        raise ValueError("Font measurements do not match the document labels.")
    if not labels:
        return []
    font = measurements[f"{size}:H"]

    def measure(text: str, point_size: float) -> float:
        return float(measurements[f"{point_size}:{text}"]["width"])

    parameters: dict[str, Any] = {
        "measure": measure,
        "ascent": float(font["ascent"]),
        "descent": float(font["descent"]),
        "base_point_size": size,
    }
    result = []
    for display, anchor, at_end, below in labels:
        if below is not None:
            split = split_hydride_label(display)
            assert split is not None
            element, count = split
            layout, box = place_hydride_stack(
                element,
                count,
                hydrogens_below=below,
                cap_height=float(font["cap_height"]),
                **parameters,
            )
            center_x, center_y = box[0] + box[2] / 2, box[1] + box[3] / 2
        else:
            layout = place_runs(parse_atom_label(display), **parameters)
            center_x, center_y = layout.width / 2, layout.height / 2
            if not layout.has_typography:
                center_y = float(measurements[f"{size}:{display}"]["line_height"]) / 2
            if anchor:
                anchor_width = measure(anchor, size)
                center_x = (
                    layout.width - anchor_width / 2 if at_end else anchor_width / 2
                )
        result.append(
            [
                {
                    "text": run.text,
                    "size": run.point_size,
                    "pixels": browser_font_pixels(run.point_size),
                    "x": run.x - center_x,
                    "y": run.baseline - center_y,
                }
                for run in layout.runs
            ]
        )
    return result


def drawing_geometry(
    state: dict[str, Any],
    label_ink: dict[int, list[tuple[float, float]]] | None = None,
) -> dict[str, Any]:
    """Connect the actual desktop geometry planner to SVG-compatible primitives."""
    model = deserialize_model_state(state["model"])
    graph = CanvasGraphState()
    for index, bond in enumerate(model.bonds):
        if bond:
            add_bond_to_atom_index(graph.atom_bond_ids, index, bond.a, bond.b)
    edges = build_ring_edge_index(model.atoms, model.bonds)

    point = BrowserPoint

    def ring_center(bond: Bond) -> Any:
        ring = ring_atom_ids_for_bond(
            bond,
            (record["atom_ids"] for record in state.get("ring_fills", [])),
            edges,
        )
        return (
            None
            if ring is None
            else point(
                sum(model.atoms[i].x for i in ring) / len(ring),
                sum(model.atoms[i].y for i in ring) / len(ring),
            )
        )

    def label_rect(atom_id: int | None) -> bool | None:
        if atom_id is None:
            return None
        atom = model.atoms.get(atom_id)
        return True if atom and atom_shows_itself(atom) else None

    metrics = RenderMetrics()
    metrics.set_bond_length(state["settings"]["bond_length_px"])
    # Qt supplies a rounded QPainterPath stroke; the browser supplies sampled ink.
    # A circumscribed 64-sided disk bounds the same radius without a Qt dependency.
    radius = glyph_clearance_radius(metrics.bond_line_width()) / math.cos(math.pi / 64)
    disk = [
        (radius * math.cos(i * math.tau / 64), radius * math.sin(i * math.tau / 64))
        for i in range(64)
    ]
    contours = {}
    for atom_id, ink in (label_ink or {}).items():
        hull = glyph_convex_hull(ink)
        expanded = glyph_convex_hull(
            (x + dx, y + dy) for x, y in hull for dx, dy in disk
        )
        if expanded:
            contours[atom_id] = [*expanded, expanded[0]]

    def trim_labels(
        a_id: int | None,
        b_id: int | None,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        offsets: tuple[tuple[float, float], ...] = (),
    ) -> tuple[float, float]:
        t0, t1 = 0.0, 1.0
        for atom_id, start in ((a_id, True), (b_id, False)):
            contour = contours.get(atom_id) if atom_id is not None else None
            if contour is None:
                continue
            clipped = glyph_contour_clip_t(
                (x1, y1),
                (x2, y2),
                [contour],
                offsets,
                start_inside=polygon_contains_point((x1, y1), contour),
                end_inside=polygon_contains_point((x2, y2), contour),
            )
            if clipped is not None:
                if start:
                    t0 = max(t0, clipped[1])
                else:
                    t1 = min(t1, clipped[0])
        return t0, max(t0, t1)

    geometry: Any = SimpleNamespace(
        trim_line_for_labels=trim_labels,
        label_rect_for_atom=label_rect,
        line_normal=line_normal,
        bond_offset_unit_3d=lambda *args, **kwargs: None,
        ring_center_for_bond=ring_center,
        ring_center_3d_for_bond=lambda bond: None,
    )
    rendering = SimpleNamespace(
        bond_spacing=metrics.bond_spacing,
        bond_line_width=metrics.bond_line_width,
        bold_bond_width=metrics.bold_bond_width,
        hash_spacing=metrics.hash_spacing,
        bold_bond_pen=lambda: SimpleNamespace(widthF=metrics.bold_bond_width),
    )
    context: Any = SimpleNamespace(
        model=model,
        state=SimpleNamespace(graph_state=graph),
        geometry=geometry,
        renderer=rendering,
    )
    lines = BondLineGeometryService(context, point_factory=point)
    ring_lines = BondRingDoubleGeometryService(context, renderer=geometry)
    for name in (
        "parallel_bond_segments",
        "plain_double_segments",
        "hash_segments",
        "hash_topology_count",
    ):
        setattr(geometry, name, getattr(lines, name))
    # Preserve the native dot data until SVG materialization instead of making a Qt path.
    geometry.dotted_bond_path = lines.dotted_bond_dots
    geometry.wedge_polygon = lines.wedge_triangle
    geometry.ring_double_segments = ring_lines.ring_double_segments
    geometry.graphics_drawer = BondGraphicsDrawService(
        context,
        renderer=geometry,
        point_factory=point,
        polygon_factory=lambda points: [(p.x(), p.y()) for p in points],
    )
    planner = BondGeometryPlanService(context, renderer=geometry)
    result: dict[str, list[dict[str, Any]]] = {}
    for index, bond in enumerate(model.bonds):
        if not bond or bond.style not in SUPPORTED_BONDS:
            continue
        primitives = planner.primitives_for_bond(
            bond, model.atoms[bond.a], model.atoms[bond.b]
        )
        result[str(index)] = []
        for item in primitives:
            if isinstance(item, BondLinePrimitive):
                result[str(index)].append({"line": item.segment})
            elif isinstance(item, BondPolygonPrimitive):
                result[str(index)].append(
                    {
                        "polygon": list(cast("Any", item.polygon)),
                        "outlined": item.outlined,
                    }
                )
            elif isinstance(item, BondPathPrimitive):
                centers, radius = cast("Any", item.path)
                result[str(index)].append({"dots": centers, "radius": radius})
    arrows = []
    arrow_point_count = 0
    for arrow in state["arrows"]:
        commands = arrow_path_commands(
            tuple(arrow["start"]),
            tuple(arrow["end"]),
            arrow["kind"],
            bond_length=metrics.style.bond_length_px,
            bond_spacing=metrics.style.bond_spacing_px,
            wave_spacing=metrics.bond_spacing(),
            line_width=state["settings"]["arrow_line_width"],
            head_scale=state["settings"]["arrow_head_scale"],
            control=None if arrow.get("control") is None else tuple(arrow["control"]),
            double=arrow.get("double", False),
            mirrored=arrow.get("mirrored", False),
        )
        arrow_point_count += sum(len(coordinates) // 2 for _, coordinates in commands)
        if arrow_point_count > 500_000:
            raise ValueError("Arrow drawing exceeds the browser path point limit.")
        arrows.append(
            {
                "path": commands,
                "width": metrics.bold_bond_width()
                if arrow["kind"] == "line_bold"
                else state["settings"]["arrow_line_width"],
                "dashed": arrow["kind"] in {"dotted", "line_dashed"},
                "cap": "butt" if arrow["kind"] == "line_bold" else "round",
                "join": "miter" if arrow["kind"] == "line_bold" else "round",
                "color": arrow.get("color") or metrics.style.bond_color,
            }
        )
    return {
        "bonds": result,
        "atom_labels": {
            str(i): atom.element
            for i, atom in model.atoms.items()
            if atom_shows_itself(atom)
        },
        "line_width": metrics.bond_line_width(),
        "font_size": metrics.atom_font_size_pt(),
        "label_measurements": browser_label_layouts(model, metrics),
        "atom_hit_radii": {
            str(atom_id): atom_pick_radius(metrics)
            if not atom_shows_itself(atom) or uses_compact_label_hit_shape(atom.element)
            else None
            for atom_id, atom in model.atoms.items()
        },
        "arrows": arrows,
    }


class BrowserFontMeasurements:
    """Bounded, replaceable browser font data; never part of document history."""

    def __init__(self, request: Any) -> None:
        if not isinstance(request, dict) or set(request) != {
            "family",
            "metrics",
            "ink",
        }:
            raise ValueError("Expected font family, metrics and glyph ink.")
        if request["family"] != ACS1996Style().font_family:
            raise ValueError("Unexpected browser font family.")
        measurements, ink = request["metrics"], request["ink"]
        for values in (measurements, ink):
            if (
                not isinstance(values, dict)
                or len(values) > 8192
                or any(not isinstance(key, str) or len(key) > 300 for key in values)
            ):
                raise ValueError("Expected bounded font measurements.")
        validate_font_metrics(measurements)
        point_count = 0
        for points in ink.values():
            if (
                not isinstance(points, list)
                or len(points) > 4096
                or any(
                    not isinstance(point, list)
                    or len(point) != 2
                    or any(
                        type(value) not in (int, float, Decimal)
                        or not math.isfinite(value)
                        for value in point
                    )
                    for point in points
                )
            ):
                raise ValueError("Glyph ink must contain bounded finite points.")
            point_count += len(points)
        if point_count > 500_000:
            raise ValueError("Measured glyph geometry is too large.")
        self.metrics = deepcopy(measurements)
        self.ink = {
            key: glyph_convex_hull((float(x), float(y)) for x, y in points)
            for key, points in ink.items()
        }

    def drawing(self, state: dict[str, Any]) -> dict[str, Any]:
        model = deserialize_model_state(state["model"])
        metrics = RenderMetrics()
        metrics.set_bond_length(state["settings"]["bond_length_px"])
        spec = browser_label_layouts(model, metrics)
        if not spec["labels"]:
            return drawing_geometry(state)
        if any(
            query["key"] not in self.metrics
            or f"{query['pixels']}:{query['text']}" not in self.ink
            for query in spec["queries"]
        ):
            # Do not render a throwaway, unclipped scene while asking for its font.
            return {"label_measurements": spec, "needs_measurements": True}
        labels = list(dict.fromkeys(tuple(label) for label in spec["labels"].values()))
        relative = dict(
            zip(
                labels,
                place_browser_labels(
                    {
                        "size": spec["size"],
                        "labels": labels,
                        "measurements": self.metrics,
                    }
                ),
                strict=True,
            )
        )
        layouts, label_ink, hit_rects = {}, {}, {}
        point_count = 0
        for key, label in spec["labels"].items():
            atom_id = int(key)
            atom = model.atoms[atom_id]
            runs = [
                {
                    **run,
                    "x": atom.x + spec["offset"] + run["x"],
                    "y": atom.y - spec["offset"] + run["y"],
                }
                for run in relative[tuple(label)]
            ]
            if any(not math.isfinite(run[key]) for run in runs for key in ("x", "y")):
                raise ValueError("Measured label coordinates overflowed.")
            points = [
                (x + run["x"], y + run["y"])
                for run in runs
                for x, y in self.ink[f"{run['pixels']}:{run['text']}"]
            ]
            point_count += len(points)
            if point_count > 500_000:
                raise ValueError("Measured label geometry is too large.")
            if any(not math.isfinite(value) for point in points for value in point):
                raise ValueError("Measured label coordinates overflowed.")
            layouts[key], label_ink[atom_id] = runs, points
            if points:
                left, top = min(x for x, _ in points), min(y for _, y in points)
                hit_rects[key] = (
                    left,
                    top,
                    max(x for x, _ in points) - left,
                    max(y for _, y in points) - top,
                )
        return {
            **drawing_geometry(state, label_ink),
            "atom_layouts": layouts,
            "atom_hit_rects": hit_rects,
        }


@dataclass(frozen=True)
class BrowserPoint:
    """Coordinate boundary for existing services that consume x()/y() points."""

    px: float
    py: float

    def x(self) -> float:
        return self.px

    def y(self) -> float:
        return self.py


@dataclass
class BrowserRingItem:
    """Ring graphics port: the shared fitter writes a candidate's polygon."""

    record: dict[str, Any]

    def data(self, role: int) -> Any:
        return self.record["atom_ids"] if role == 2 else None

    def setPolygon(self, points: tuple[BrowserPoint, ...]) -> None:  # noqa: N802 - graphics port
        self.record["points"] = [(point.x(), point.y()) for point in points]


@dataclass
class BrowserArrowItem:
    """Arrow graphics port over the candidate's canonical document record."""

    record: dict[str, Any]

    def data(self, role: int) -> Any:
        return self.record["kind"] if role == 0 else None


class BrowserStructureAdapter:
    """Materialize existing structure builders into a candidate document and SVG.

    The existing committer owns atom merging, bond order and ring construction.
    document_info renders the accepted candidate once, instead of creating
    QGraphicsItems during each mutation.
    """

    def __init__(self, state: dict[str, Any]) -> None:
        self.document_state = state
        self.model = deserialize_model_state(state["model"])
        self.renderer = RenderMetrics()
        self.renderer.set_bond_length(state["settings"]["bond_length_px"])
        # document_info materializes the complete SVG after the build commits.
        self.bond_renderer = SimpleNamespace(add_bond_graphics=lambda _bond_id: None)
        self.runtime_state = SimpleNamespace(
            tool_settings_state=CanvasToolSettingsState(),
            mark_registry=CanvasMarkRegistry(),
            atom_graphics_state=SimpleNamespace(atom_items={}, atom_dots={}),
            bond_graphics_state=SimpleNamespace(bond_items={}),
            atom_coords_3d_state=SimpleNamespace(atom_coords_3d={}),
            hover_preview_state=SimpleNamespace(atom_id=None),
            handle_state=SimpleNamespace(target=None),
            ring_items=lambda: (),
            callback_state=SimpleNamespace(error=self.reject_edit),
        )
        self.services = SimpleNamespace(
            canvas_atom_mutation_service=self.model,
            canvas_bond_mutation_service=self.model,
            scene_item_controller=SimpleNamespace(attach_scene_item=self.attach_ring),
        )
        # The browser materializes labels once, after candidate validation.
        self.render_context = SimpleNamespace(
            arrows=SimpleNamespace(
                record=lambda item: arrow_from_state(item.record),
                set_record=lambda item, record: item.record.update(
                    arrow_to_state(record)
                ),
            ),
            atom_labels=SimpleNamespace(
                atom_item_for_id=lambda _id: None,
                draw_atom=lambda _id, **kwargs: None,
                relayout_atom_label=lambda _id: False,
            ),
        )
        graph = SimpleNamespace(rebuild_bond_adjacency=lambda: None)
        self.labels = AtomLabelService(
            cast("Any", self),
            graph_service=graph,
            merge_service=AtomLabelMergeService(
                self, graph_service=graph, capture_history=False
            ),
            connection_allowed=lambda _ids: True,
        )
        self.committer = StructureBuildCommitter(cast("Any", self))
        self.bond_builder = StructureBondBuildService(
            self,
            self.committer,
            hit_testing_service=self,
            graph_service=self.committer,
            move_controller=SimpleNamespace(
                redraw_bond=lambda _id: None,
                redraw_connected_bonds=lambda _id, **kwargs: None,
            ),
            # Grouped documents are read-only until group adapters are connected.
            connection_allowed=lambda _anchors: True,
        )
        self.builder = StructureBenzeneBuildService(
            self,
            self.committer,
            point_factory=BrowserPoint,
            center_inside_existing_ring=self.center_inside_ring,
        )

        self.services.atom_label_service = self.labels
        self.services.canvas_ring_fill_scene_service = SimpleNamespace(
            create_ring_fill_item=lambda points, ids: RingFill(
                tuple(ids),
                self.renderer.style.ring_fill_color,
                self.renderer.style.ring_fill_alpha,
            )
        )
        self.candidate_accepted = True

        def run_growth(action: Callable[[], bool]) -> bool:
            self.candidate_accepted = action()
            return self.candidate_accepted

        self.growth = StructureGrowthBuildService(
            StructureGrowthBuildActions(
                atom_point=lambda atom_id: cast(
                    "Any",
                    BrowserPoint(
                        self.model.atoms[atom_id].x, self.model.atoms[atom_id].y
                    ),
                ),
                sprout_bond_endpoint=partial(
                    sprout_bond_endpoint_for, self, point_factory=BrowserPoint
                ),
                add_bond_between_points=partial(
                    self.bond_builder.add_bond_between_points, record=False
                ),
                add_benzene_ring=lambda center, attach_atom_id=None, attach_bond_id=None: (
                    self.insert_benzene(
                        center.x(), center.y(), attach_atom_id, attach_bond_id
                    )
                ),
                has_atom=lambda atom_id: self.model.atom_for_id(atom_id) is not None,
                default_bond_endpoint=partial(
                    default_bond_endpoint_for, self, point_factory=BrowserPoint
                ),
                add_atom_label=self.committer.add_atom_label,
                regular_ring_points_for_atom=partial(
                    regular_ring_points_for_atom_for, self, point_factory=BrowserPoint
                ),
                regular_ring_points_for_bond=partial(
                    regular_ring_points_for_bond_for, self, point_factory=BrowserPoint
                ),
                cyclohexane_chair_points=partial(
                    cyclohexane_chair_points_for, self, point_factory=BrowserPoint
                ),
                template_points_for_bond=partial(
                    template_points_for_bond_for, self, point_factory=BrowserPoint
                ),
                add_ring_from_points=self.committer.add_ring_from_points,
                bond_placement_context=lambda bond_id: resolve_bond_placement_context(
                    bond_id,
                    bonds=self.model.bonds,
                    atoms=self.model.atoms,
                    point_factory=BrowserPoint,
                ),
                # The browser candidate and session own this transaction/history.
                run_recorded_additions_action=run_growth,
                add_atom=self.committer.add_atom,
                add_bond=self.committer.add_bond,
                add_bond_graphics=self.committer.add_bond_graphics,
            ),
            point_factory=BrowserPoint,
        )

    @staticmethod
    def reject_edit(message: str) -> None:
        raise ValueError(message)

    def find_atom_near(self, x: float, y: float, max_dist: float) -> int | None:
        return nearest_atom_id(
            self.model.atoms, self.model.atoms, x=x, y=y, max_dist=max_dist
        )

    def require_sheet_position(self, x: float, y: float) -> None:
        if any(
            type(v) not in (int, float, Decimal) or not math.isfinite(v) for v in (x, y)
        ):
            raise ValueError("Edit coordinates must be finite numbers.")
        settings = self.document_state["settings"]
        width, height = sheet_dimensions_px(
            settings["sheet_size"],
            settings["sheet_orientation"],
            settings.get("sheet_custom_size_mm"),
        )
        if not scene_pos_in_sheet(x, y, (-width / 2, -height / 2, width, height)):
            raise ValueError(OFF_SHEET_EDIT_GUIDANCE)

    def atom_target(self, edit: dict[str, Any]) -> TextToolTarget:
        x, y = edit["x"], edit["y"]
        if any(
            type(v) not in (int, float, Decimal) or not math.isfinite(v) for v in (x, y)
        ):
            raise ValueError("Atom coordinates must be finite numbers.")
        x, y = float(x), float(y)
        self.require_sheet_position(x, y)
        atom_id = edit.get("atom_id")
        if atom_id is not None and (
            type(atom_id) is not int or self.model.atom_for_id(atom_id) is None
        ):
            raise ValueError("Unknown atom tool target.")
        radius = self.renderer.style.bond_length_px
        hover_atom_id, hover_bond_id = self.structure_target(
            x,
            y,
            bond_gate_ratio=STRUCTURE_BOND_PICK_RADIUS_RATIO,
            direct_atom_id=atom_id,
        )
        needs_nearby = hover_atom_id is None and atom_id is None
        return resolve_text_tool_target(
            self.model,
            pos=(x, y),
            hover_atom_id=hover_atom_id,
            item_atom_id=atom_id,
            hover_bond_id=hover_bond_id,
            nearby_atom_id=self.find_atom_near(x, y, radius * 0.9)
            if needs_nearby
            else None,
            nearby_bond_id=nearest_bond_id(
                self.model,
                range(len(self.model.bonds)),
                BrowserPoint(x, y),
                radius * 0.6,
                point_factory=BrowserPoint,
            )
            if needs_nearby
            else None,
        )

    def apply_atom_input(self, edit: dict[str, Any]) -> None:
        text = edit["text"]
        if not isinstance(text, str) or len(text) > int(ATOM_INPUT_SPEC["max_length"]):
            raise ValueError("Atom labels must contain at most 255 characters.")
        if edit["kind"] == "atom_prompt":
            atom_id = edit["atom_id"]
            if type(atom_id) is not int or self.model.atom_for_id(atom_id) is None:
                raise ValueError("The atom no longer exists.")
            self.require_sheet_position(edit["x"], edit["y"])
            self.labels.apply_atom_label_prompt(atom_id, text, record=False)
            self.publish_model()
            return
        target = self.atom_target(edit)
        atom = self.model.atom_for_id(target.atom_id)
        apply_text_input(
            target,
            normalize_text_symbol(text),
            atom.element if atom is not None else "",
            add_atom=lambda text, x, y: self.labels.add_labelled_atom(
                text, x, y, record=False
            ),
            update_label=lambda atom_id, text, **kwargs: (
                self.labels.add_or_update_atom_label(
                    atom_id, text, record=False, **kwargs
                )
            ),
            notify_error=self.reject_edit,
        )
        self.publish_model()

    def insert_arrow(self, edit: dict[str, Any]) -> None:
        start, end = edit["start"], edit["end"]
        if any(
            not isinstance(point, list) or len(point) != 2 for point in (start, end)
        ):
            raise ValueError("A point needs two coordinates.")
        if any(
            type(v) not in (int, float, Decimal) or not math.isfinite(v)
            for v in (*start, *end)
        ):
            raise ValueError("Arrow coordinates must be finite numbers.")
        kind = edit["style"]
        if not isinstance(kind, str) or kind not in {
            value for _, value in ARROW_MENU_SPECS
        }:
            raise ValueError("Unsupported arrow style.")
        if type(edit["dragged"]) is not bool or type(edit["shift"]) is not bool:
            raise ValueError("Expected arrow gesture flags.")
        scale = edit["scale"]
        if type(scale) not in (int, float, Decimal):
            raise ValueError("Invalid drawing scale.")
        scale = float(scale)
        # Fit Page can show a large sheet below the manual zoom minimum.
        if not 0 < scale <= ZOOM_MAX:
            raise ValueError("Invalid drawing scale.")
        radius = ENDPOINT_SNAP_SCREEN_PX / scale
        if not math.isfinite(radius):
            raise ValueError("Invalid drawing scale.")
        self.require_sheet_position(*start)
        self.require_sheet_position(*end)
        if not edit["dragged"]:
            return
        endpoints = [
            tuple(point)
            for arrow in self.document_state["arrows"]
            for point in (arrow["start"], arrow["end"])
        ]
        first = snapped_drawing_point(
            (float(start[0]), float(start[1])), endpoints, radius=radius
        )
        last = snapped_drawing_point(
            (float(end[0]), float(end[1])), endpoints, radius=radius, avoid=first
        )
        if first == last:
            return
        if edit["shift"] and kind in VALID_ARC_KINDS:
            kind = mirrored_arc_kind(kind)
        record = new_arrow_record(first, last, kind)
        self.document_state["arrows"].append(arrow_to_state(record))

    def insert_bond(self, start: list[float], end: list[float], style: str) -> None:
        if any(
            not isinstance(point, list) or len(point) != 2 for point in (start, end)
        ):
            raise ValueError("A point needs two coordinates.")
        if any(
            type(v) not in (int, float, Decimal) or not math.isfinite(v)
            for v in (*start, *end)
        ):
            raise ValueError("Bond coordinates must be finite numbers.")
        self.require_sheet_position(*start)
        self.require_sheet_position(*end)
        start_point = BrowserPoint(*(float(value) for value in start))
        end_point = BrowserPoint(*(float(value) for value in end))
        radius = self.renderer.style.bond_length_px * BOND_PICK_RADIUS_RATIO
        start_id = self.find_atom_near(start_point.x(), start_point.y(), radius)
        _atom_id, preferred_bond_id = self.structure_target(
            start_point.x(),
            start_point.y(),
            bond_gate_ratio=STRUCTURE_BOND_PICK_RADIUS_RATIO,
        )
        press_bond_id = resolve_bond_press_target(
            atom_id=start_id,
            item_kind="bond" if preferred_bond_id is not None else None,
            item_bond_id=preferred_bond_id,
            nearby_bond_id=nearest_bond_id(
                self.model,
                range(len(self.model.bonds)),
                start_point,
                radius,
                point_factory=BrowserPoint,
            )
            if start_id is None
            else None,
            hover_bond_id=None,
        )
        if press_bond_id is not None:
            self.apply_bond_style(press_bond_id, style)
            return
        short_click = is_short_bond_gesture(
            (start_point.x(), start_point.y()),
            (end_point.x(), end_point.y()),
            self.renderer.style.bond_length_px,
        )
        if start_id is not None:
            atom = self.model.atoms[start_id]
            start_point = BrowserPoint(atom.x, atom.y)
        end_id = self.find_atom_near(end_point.x(), end_point.y(), radius)
        snapped = resolve_bond_snap_target(
            self.model,
            pos=(end_point.x(), end_point.y()),
            atom_id=end_id,
            bond_id=nearest_bond_id(
                self.model,
                range(len(self.model.bonds)),
                end_point,
                self.renderer.style.bond_length_px * BOND_SNAP_RADIUS_RATIO,
                point_factory=BrowserPoint,
            )
            if end_id is None
            else None,
            start_atom_id=start_id,
            ignore_start=True,
        )
        end_point = BrowserPoint(*snapped.pos)
        end_id = self.find_atom_near(end_point.x(), end_point.y(), radius)
        endpoint = resolve_bond_endpoint_target(
            self.model,
            start=(start_point.x(), start_point.y()),
            end=(end_point.x(), end_point.y()),
            atom_id=end_id,
            start_atom_id=start_id,
            snap_angle_step=self.runtime_state.tool_settings_state.snap_angle_step,
            bond_length=self.renderer.style.bond_length_px,
        )
        if short_click:
            end_point = cast(
                "BrowserPoint",
                default_bond_endpoint_for(
                    self, cast("Any", start_point), start_id, point_factory=BrowserPoint
                ),
            )
        else:
            end_point = BrowserPoint(*endpoint)
        self.bond_builder.add_bond_between_points(
            cast("Any", start_point),
            cast("Any", end_point),
            style,
            BOND_ORDERS[style],
            record=False,
        )
        self.publish_model()

    def apply_bond_style(self, bond_id: int, style: str) -> None:
        bond = self.model.bond_for_id(bond_id)
        if type(bond_id) is not int or bond is None:
            raise ValueError("Unknown bond.")

        def apply_style(style: str, order: int) -> None:
            bond.style, bond.order = style, order

        apply_active_bond_style(
            bond,
            style,
            BOND_ORDERS[style],
            apply_style=apply_style,
            cycle_style=lambda: apply_style(
                *cycle_plain_bond_style(
                    bond.style, bond.order, allow_double_variants=False
                )
            ),
            notify_error=self.reject_edit,
        )
        self.publish_model()

    def apply_hover_shortcut(
        self, x: float, y: float, key: str, direct_atom_id: int | None = None
    ) -> str | None:
        if not isinstance(key, str) or key not in (
            CanvasChemdrawShortcutService.ATOM_HOTKEYS
            | CanvasChemdrawShortcutService.BOND_HOTKEYS
            | TOOL_HOTKEYS.keys()
        ):
            raise ValueError("Unsupported hover shortcut.")
        atom_id, bond_id = self.structure_target(
            x,
            y,
            bond_gate_ratio=STRUCTURE_BOND_PICK_RADIUS_RATIO,
            direct_atom_id=direct_atom_id,
        )

        if (
            atom_id is not None and key in CanvasChemdrawShortcutService.ATOM_HOTKEYS
        ) or (
            bond_id is not None and key in CanvasChemdrawShortcutService.BOND_HOTKEYS
        ):
            self.require_sheet_position(x, y)

        def restyle(bond_id: int, style: str, order: int) -> None:
            bond = self.model.bond_for_id(bond_id)
            assert bond is not None
            bond.style, bond.order = style, order

        shortcuts = CanvasChemdrawShortcutService(
            lambda: self.model,
            hover_state=cast("Any", None),
            atom_label_service=cast(
                "Any",
                SimpleNamespace(
                    add_or_update_atom_label=partial(
                        self.labels.add_or_update_atom_label, record=False
                    ),
                ),
            ),
            structure_build_service=cast("Any", self.growth),
            notify_error=self.reject_edit,
            scene_transform_controller=cast(
                "Any", SimpleNamespace(apply_bond_style=restyle)
            ),
            tool_mode_controller=cast("Any", None),
        )
        if atom_id is not None and key in {"+", "-"}:
            raise ValueError(
                "Charge marks are not connected in the browser yet. Use Qt for this shortcut."
            )
        handled = (
            atom_id is not None and shortcuts.handle_atom_text(key, atom_id)
        ) or (bond_id is not None and shortcuts.handle_bond_text(key, bond_id))
        if handled:
            if self.candidate_accepted:
                self.publish_model()
            return None
        return TOOL_HOTKEYS.get(key)

    def center_inside_ring(self, center: BrowserPoint) -> bool:
        return any(
            polygon_contains_point((center.x(), center.y()), ring["points"])
            for ring in self.document_state.get("ring_fills", [])
        )

    def attach_ring(self, ring: RingFill) -> None:
        record = ring_fill_to_state(ring, self.model.atoms)
        record.pop("kind")
        self.document_state.setdefault("ring_fills", []).append(record)

    def ring_points(
        self, center: Any, atom_id: int | None = None, bond_id: int | None = None
    ) -> Any:
        return self.builder.benzene_ring_points(
            center,
            atom_id,
            bond_id,
            regular_ring_points_for_atom=lambda n, atom_id: (
                regular_ring_points_for_atom_for(
                    self,
                    n,
                    atom_id,
                    point_factory=BrowserPoint,
                )
            ),
            regular_ring_points_for_bond=lambda n, bond_id, hint: (
                regular_ring_points_for_bond_for(
                    self,
                    n,
                    bond_id,
                    hint,
                    point_factory=BrowserPoint,
                )
            ),
        )

    def structure_target(
        self,
        x: float,
        y: float,
        *,
        bond_gate_ratio: float,
        direct_atom_id: int | None = None,
    ) -> tuple[int | None, int | None]:
        if any(
            type(v) not in (int, float, Decimal) or not math.isfinite(v) for v in (x, y)
        ):
            raise ValueError("Atom coordinates must be finite numbers.")
        x, y = float(x), float(y)
        if direct_atom_id is not None:
            if (
                type(direct_atom_id) is not int
                or direct_atom_id not in self.model.atoms
            ):
                raise ValueError("Unknown atom hit target.")
            return direct_atom_id, None
        radius = atom_pick_radius_for(self)
        atom_id = self.find_atom_near(x, y, radius)
        atom = self.model.atom_for_id(atom_id) if atom_id is not None else None
        pos = BrowserPoint(x, y)
        length = self.renderer.style.bond_length_px
        bond_id = nearest_bond_id(
            self.model,
            range(len(self.model.bonds)),
            pos,
            length * bond_gate_ratio,
            point_factory=BrowserPoint,
        )
        bond_hit = None
        if bond_id is not None:
            bond = self.model.bonds[bond_id]
            assert bond is not None
            a, b = self.model.atoms[bond.a], self.model.atoms[bond.b]
            bond_hit = BondHitCandidate(
                bond_id,
                distance_point_to_segment(
                    pos, BrowserPoint(a.x, a.y), BrowserPoint(b.x, b.y)
                ),
            )
        hit = choose_preferred_structure_hit(
            AtomHitCandidate(atom_id, math.hypot(atom.x - x, atom.y - y))
            if atom_id is not None and atom is not None
            else None,
            bond_hit,
            atom_pick_radius=radius,
            bond_pick_radius=length * STRUCTURE_BOND_PICK_RADIUS_RATIO,
        )
        return (
            hit.id if hit is not None and hit.kind == "atom" else None,
            hit.id if hit is not None and hit.kind == "bond" else None,
        )

    def insert_benzene(
        self, x: float, y: float, atom_id: int | None = None, bond_id: int | None = None
    ) -> None:
        for target, records in (
            (atom_id, self.model.atoms),
            (bond_id, dict(enumerate(self.model.bonds))),
        ):
            if target is not None and (
                type(target) is not int
                or target not in records
                or records[target] is None
            ):
                raise ValueError("Unknown ring attachment.")
        self.builder.build_benzene_ring(
            cast("Any", BrowserPoint(x, y)),
            atom_id,
            bond_id,
            benzene_ring_points=self.ring_points,
            add_atom_with_merge=self.committer.add_atom_with_merge,
            bond_exists=lambda a, b: self.committer.bond_id_between(a, b) is not None,
            create_ring_fill_item=lambda points, ids: RingFill(
                tuple(ids),
                self.renderer.style.ring_fill_color,
                self.renderer.style.ring_fill_alpha,
            ),
        )
        self.publish_model()

    def publish_model(self) -> None:
        state, warnings = serialize_model_state_with_warnings(
            self.model,
            {key for key, atom in self.model.atoms.items() if atom.explicit_label},
        )
        if warnings:
            raise ValueError(
                "The edit produced invalid model data: " + "; ".join(warnings)
            )
        self.document_state["model"] = state

    def pick_target(
        self, x: float, y: float, hits: object, *, preferred: bool
    ) -> dict[str, Any] | None:
        """Adapt native graphics hits, then use the existing structure picker.

        Select uses preferred structure distance; Shift/eraser use the raw
        graphics target and the native near-bond fallback instead.
        """
        if any(
            type(v) not in (int, float, Decimal) or not math.isfinite(v) for v in (x, y)
        ):
            raise ValueError("Pick coordinates must be finite numbers.")
        self.selection_buckets(hits)
        direct: dict[str, int] = {}
        for hit in cast("list[dict[str, Any]]", hits):
            direct.setdefault(hit["target"], hit["id"])
        if "atom" in direct:
            return {"target": "atom", "id": direct["atom"]}
        bond_id = direct.get("bond")
        if bond_id is None:
            bond_id = nearest_bond_id(
                self.model,
                range(len(self.model.bonds)),
                BrowserPoint(float(x), float(y)),
                self.renderer.style.bond_length_px * STRUCTURE_BOND_PICK_RADIUS_RATIO,
                point_factory=BrowserPoint,
            )
        # Native Select takes a directly hit arrow before structure fallback.
        if bond_id is None and "arrow" in direct:
            return {"target": "arrow", "id": direct["arrow"]}
        if preferred:
            atom_id, preferred_bond = self.structure_target(
                x, y, bond_gate_ratio=STRUCTURE_BOND_PICK_RADIUS_RATIO
            )
            if atom_id is not None:
                return {"target": "atom", "id": atom_id}
            if preferred_bond is not None:
                return {"target": "bond", "id": preferred_bond}
        return None if bond_id is None else {"target": "bond", "id": bond_id}

    def selection_buckets(self, items: object) -> DeleteSelectionBuckets:
        if not isinstance(items, list) or len(items) > 5000 + len(
            self.document_state["arrows"]
        ):
            raise ValueError("Expected a bounded list of selected items.")
        buckets = DeleteSelectionBuckets()
        arrow_ids = set()
        for item in items:
            if not isinstance(item, dict) or set(item) != {"target", "id"}:
                raise ValueError("Expected target and id for each selected item.")
            kind, item_id = item["target"], item["id"]
            if (
                kind not in {"atom", "bond", "arrow"}
                or type(item_id) is not int
                or item_id < 0
            ):
                raise ValueError("Invalid selection target.")
            if kind == "atom":
                if self.model.atom_for_id(item_id) is None:
                    raise ValueError("The atom no longer exists.")
                buckets.atom_ids.add(item_id)
            elif kind == "bond":
                if self.model.bond_for_id(item_id) is None:
                    raise ValueError("The bond no longer exists.")
                buckets.bond_ids.add(item_id)
            else:
                arrows = self.document_state["arrows"]
                if item_id >= len(arrows):
                    raise ValueError("The arrow no longer exists.")
                if item_id not in arrow_ids:
                    buckets.arrow_items.append(
                        cast("Any", BrowserArrowItem(arrows[item_id]))
                    )
                    arrow_ids.add(item_id)
        return buckets

    def move_selection(self, items: object, dx: float, dy: float) -> None:
        if not math.isfinite(dx) or not math.isfinite(dy):
            raise ValueError("Movement must be finite.")
        buckets = self.selection_buckets(items)
        if dx == 0 and dy == 0:
            return
        atoms = selected_atom_ids_with_bond_endpoints(
            buckets.atom_ids, buckets.bond_ids, bonds=self.model.bonds
        )
        controller = CanvasMoveController(
            cast("Any", self),
            hit_testing_service=cast(
                "Any", SimpleNamespace(mark_spatial_index_dirty=lambda: None)
            ),
            ring_polygon_rebuilder=partial(
                rebuild_ring_fill_polygons,
                point_factory=BrowserPoint,
                polygon_factory=tuple,
            ),
        )
        controller.move_atoms(
            atoms,
            dx,
            dy,
            bond_ids=set(),
            redraw_bond_ids=set(),
            update_selection=False,
            affected_ring_items=tuple(
                BrowserRingItem(ring)
                for ring in self.document_state.get("ring_fills", [])
            ),
        )
        for item in buckets.arrow_items:
            controller.move_item(item, dx, dy, update_selection=False)
        self.publish_model()

    def delete_hover(
        self, x: float, y: float, direct_atom_id: int | None = None
    ) -> None:
        target = hover_delete_target(
            *self.structure_target(
                x,
                y,
                bond_gate_ratio=STRUCTURE_BOND_PICK_RADIUS_RATIO,
                direct_atom_id=direct_atom_id,
            ),
            bonds=self.model.bonds,
            atom_has_visible_label=lambda atom_id: atom_shows_itself(
                self.model.atoms[atom_id]
            ),
        )
        if target is None:
            return
        self.require_sheet_position(x, y)
        kind, item_id = target
        if kind == "label":
            self.labels.add_or_update_atom_label(
                item_id, "C", record=False, show_carbon=False
            )
            self.publish_model()
        else:
            self.delete_selection([{"target": kind, "id": item_id}])

    def delete_selection(self, items: object) -> None:
        buckets = self.selection_buckets(items)
        plan = build_delete_selection_plan(
            buckets,
            bonds=self.model.bonds,
            marks_by_atom={},
            atom_has_visible_label=lambda atom_id: atom_shows_itself(
                self.model.atoms[atom_id]
            ),
        )
        for bond_id in plan.bond_ids_to_remove:
            self.model.clear_bond(bond_id)
        for atom_id in plan.atom_ids:
            self.model.pop_atom(atom_id)
        removed_arrows = {
            id(cast("BrowserArrowItem", item).record) for item in plan.scene_items
        }
        self.document_state["arrows"] = [
            arrow
            for arrow in self.document_state["arrows"]
            if id(arrow) not in removed_arrows
        ]
        rings = self.document_state.get("ring_fills", [])
        broken = broken_ring_fill_indices(
            [ring["atom_ids"] for ring in rings],
            atom_ids=set(self.model.atoms),
            bond_pairs=model_bond_pairs(self.model),
        )
        self.document_state["ring_fills"] = [
            ring for index, ring in enumerate(rings) if index not in broken
        ]
        self.publish_model()


def edit_document(
    request: object, *, font: BrowserFontMeasurements | None = None
) -> dict[str, Any]:
    """Only connected Chemvas operations can publish a validated candidate."""
    if not isinstance(request, dict) or set(request) != {"document", "edit"}:
        raise ValueError("Expected document and edit.")
    info = document_info(request["document"], render=False)
    if info["unsupported"]:
        raise ValueError(
            "This document is read-only in the browser. Use Qt to edit it."
        )
    payload = info["document"]
    edit = request["edit"]
    if not isinstance(edit, dict):
        raise ValueError("edit must be an object.")
    kind = edit.get("kind")
    for key in ("x", "y", "dx", "dy", "value"):
        if key in edit and (
            type(edit[key]) not in (int, float, Decimal) or not math.isfinite(edit[key])
        ):
            raise ValueError("Edit coordinates and lengths must be finite numbers.")
    candidate = deepcopy(extract_document_state(payload))
    adapter = BrowserStructureAdapter(candidate)
    if kind in {"bond", "bond_style"}:
        if edit.get("style") not in BOND_ORDERS:
            raise ValueError("Unsupported bond style.")
    shortcut_tool = None
    if kind == "bond" and set(edit) == {"kind", "start", "end", "style"}:
        adapter.insert_bond(edit["start"], edit["end"], edit["style"])
    elif kind == "arrow" and set(edit) == {
        "kind",
        "start",
        "end",
        "style",
        "dragged",
        "shift",
        "scale",
    }:
        adapter.insert_arrow(edit)
    elif kind == "bond_style" and set(edit) == {"kind", "id", "style"}:
        adapter.apply_bond_style(edit["id"], edit["style"])
    elif kind == "hover_shortcut" and {"kind", "x", "y", "key"} <= set(edit) <= {
        "kind",
        "x",
        "y",
        "key",
        "atom_id",
    }:
        shortcut_tool = adapter.apply_hover_shortcut(
            float(edit["x"]), float(edit["y"]), edit["key"], edit.get("atom_id")
        )
    elif kind == "ring" and {"kind", "x", "y"} <= set(edit) <= {
        "kind",
        "x",
        "y",
        "atom_id",
    }:
        x, y = float(edit["x"]), float(edit["y"])
        adapter.require_sheet_position(x, y)
        adapter.insert_benzene(
            x,
            y,
            *adapter.structure_target(
                x,
                y,
                bond_gate_ratio=TEMPLATE_BOND_GATE_RATIO,
                direct_atom_id=edit.get("atom_id"),
            ),
        )
    elif kind == "move" and set(edit) == {"kind", "selection", "dx", "dy"}:
        adapter.move_selection(edit["selection"], float(edit["dx"]), float(edit["dy"]))
    elif kind == "erase" and set(edit) == {"kind", "x", "y", "hits"}:
        target = adapter.pick_target(
            edit["x"], edit["y"], edit["hits"], preferred=False
        )
        if target is not None:
            adapter.delete_selection([target])
    elif kind == "delete_selection" and set(edit) == {"kind", "selection"}:
        adapter.delete_selection(edit["selection"])
    elif kind == "delete_hover" and {"kind", "x", "y"} <= set(edit) <= {
        "kind",
        "x",
        "y",
        "atom_id",
    }:
        adapter.delete_hover(float(edit["x"]), float(edit["y"]), edit.get("atom_id"))
    elif kind == "atom_prompt" and set(edit) == {"kind", "atom_id", "text", "x", "y"}:
        adapter.apply_atom_input(edit)
    elif kind == "atom" and {"kind", "x", "y", "text"} <= set(edit) <= {
        "kind",
        "x",
        "y",
        "text",
        "atom_id",
    }:
        adapter.apply_atom_input(edit)
    elif kind == "bond_length" and set(edit) == {"kind", "value"}:
        candidate["settings"]["bond_length_px"] = edit["value"]
    else:
        raise ValueError("Unsupported edit or unexpected fields.")
    result = document_info(
        build_normalized_document_payload(candidate, payload["version"])
        if adapter.candidate_accepted
        else payload,
        font=font,
    )
    if kind == "hover_shortcut":
        result["shortcut_tool"] = shortcut_tool
    return result


def atom_input_plan(request: object) -> dict[str, Any]:
    if (
        not isinstance(request, dict)
        or set(request) != {"document", "edit", "symbol"}
        or not isinstance(request["edit"], dict)
    ):
        raise ValueError("Expected document, atom input target and symbol.")
    info = document_info(request["document"], render=False)
    if info["unsupported"]:
        raise ValueError("This document is read-only in the browser.")
    symbol = request["symbol"]
    if not isinstance(symbol, str) or len(symbol) > int(ATOM_INPUT_SPEC["max_length"]):
        raise ValueError("Atom labels must contain at most 255 characters.")
    adapter = BrowserStructureAdapter(extract_document_state(info["document"]))
    if request["edit"].get("kind") == "atom_prompt":
        if (
            not {"kind", "x", "y"}
            <= set(request["edit"])
            <= {"kind", "x", "y", "atom_id"}
        ):
            raise ValueError("Expected the atom prompt scene position.")
        atom_id, _bond_id = adapter.structure_target(
            request["edit"]["x"],
            request["edit"]["y"],
            bond_gate_ratio=STRUCTURE_BOND_PICK_RADIUS_RATIO,
            direct_atom_id=request["edit"].get("atom_id"),
        )
        if atom_id is not None:
            adapter.require_sheet_position(request["edit"]["x"], request["edit"]["y"])
        initial = (
            adapter.labels.atom_label_prompt_initial(atom_id)
            if atom_id is not None
            else None
        )
        return {
            "atom_id": atom_id,
            "needs_prompt": initial is not None,
            "initial": initial or "",
            "text": None,
        }
    target = adapter.atom_target(request["edit"])
    atom = adapter.model.atom_for_id(target.atom_id)
    return asdict(plan_text_input(symbol, atom.element if atom is not None else ""))


class StaleRevisionError(ValueError):
    """The client must read current state before it can edit again."""


class DocumentChange(HistoryCommand):
    """Adapt a validated document value to Chemvas's existing history service."""

    history_transaction_owns_exact_state = True
    history_transaction_snapshot_covers_state = True

    def __init__(self, before: dict[str, Any], after: dict[str, Any]) -> None:
        self.before, self.after = before, after

    @override
    def undo(self, operations: Any) -> None:
        operations.info = document_info(self.before, font=operations.font)

    @override
    def redo(self, operations: Any) -> None:
        operations.info = document_info(self.after, font=operations.font)


class BrowserSession:
    """One document owner; the browser only mirrors accepted state."""

    def __init__(self) -> None:
        self.lock = RLock()
        self.closed = False
        self.font = BrowserFontMeasurements(
            {"family": ACS1996Style().font_family, "metrics": {}, "ink": {}}
        )
        self.info = document_info(new_document(), font=self.font)
        self.saved = json.dumps(self.info["document"], sort_keys=True)
        self.name = "Canvas 1.chemvas"
        self.revision = 0
        self.state = CanvasHistoryState()
        operations: Any = self
        self.history = CanvasHistoryService(
            operations, self.state, replay_context=nullcontext
        )

    def capture_history_transaction_for_history(self, **kwargs: Any) -> dict[str, Any]:
        return self.info

    def restore_history_transaction_for_history(
        self, snapshot: dict[str, Any]
    ) -> RestoreOutcome:
        self.info = snapshot
        return RestoreOutcome(authoritative=True)

    def release_history_transaction_for_history(self, snapshot: dict[str, Any]) -> None:
        pass

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")
        shortcut_tool = None
        result = None
        if action != "read" and request.get("revision") != self.revision:
            raise StaleRevisionError(
                "This window has stale state. Refresh it before editing."
            )
        if action == "pick":
            if (
                set(request)
                - {"session", "revision", "action", "x", "y", "hits", "preferred"}
                or type(request.get("preferred")) is not bool
            ):
                raise ValueError("Expected a bounded selection pick request.")
            adapter = BrowserStructureAdapter(
                extract_document_state(self.info["document"])
            )
            return {
                "target": adapter.pick_target(
                    request["x"],
                    request["y"],
                    request["hits"],
                    preferred=request["preferred"],
                ),
                "revision": self.revision,
            }
        if action == "measure":
            if set(request) - {"session", "revision", "action", "font", "edit"}:
                raise ValueError("Unexpected font measurement fields.")
            font = BrowserFontMeasurements(request["font"])
            result = (
                edit_document(
                    {"document": self.info["document"], "edit": request["edit"]},
                    font=font,
                )
                if "edit" in request
                else document_info(self.info["document"], font=font)
            )
            if result["drawing"].get("needs_measurements"):
                raise ValueError("Font measurements do not match the drawing.")
            self.font = font
            if "edit" not in request:
                self.info = result
        elif action == "preview":
            if set(request) - {"session", "revision", "action", "edit"}:
                raise ValueError("Unexpected preview fields.")
            result = edit_document(
                {"document": self.info["document"], "edit": request["edit"]},
                font=self.font,
            )
        elif action == "load":
            name = request.get("name", "Canvas 1.chemvas")
            if not isinstance(name, str):
                raise ValueError("The document name must be text.")
            candidate = document_info(request["document"], font=self.font)
            self.history.clear()
            self.name = name
            self.info = candidate
            self.saved = json.dumps(candidate["document"], sort_keys=True)
        elif action == "edit":
            candidate = edit_document(
                {"document": self.info["document"], "edit": request["edit"]},
                font=self.font,
            )
            shortcut_tool = candidate.pop("shortcut_tool", None)
            if candidate["document"] != self.info["document"]:
                # Push first: a failed record cannot publish the candidate.
                self.history.push(
                    DocumentChange(self.info["document"], candidate["document"])
                )
                self.info = candidate
        elif action in {"undo", "redo"}:
            getattr(self.history, action)()
        elif action != "read":
            raise ValueError("Unknown browser action.")
        if action not in {"read", "measure", "preview"}:
            self.revision += 1
        return {
            **(self.info if result is None else result),
            "shortcut_tool": shortcut_tool,
            "revision": self.revision,
            "name": self.name,
            "can_undo": bool(self.state.history),
            "can_redo": bool(self.state.redo_stack),
            "dirty": json.dumps(self.info["document"], sort_keys=True) != self.saved,
        }


class BrowserServer(ThreadingHTTPServer):
    """One loopback server with isolated in-memory document sessions and no file writes."""

    def __init__(self, port: int = 0) -> None:
        self.token = secrets.token_urlsafe(32)
        self.sessions: dict[str, BrowserSession] = {}
        self.session_lock = RLock()
        super().__init__(("127.0.0.1", port), BrowserHandler)
        self.origin = f"http://127.0.0.1:{self.server_port}"


class BrowserHandler(BaseHTTPRequestHandler):
    server: BrowserServer

    @override
    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10)

    @override
    def log_message(self, format: str, *args: Any) -> None:
        """Request bodies and launch credentials are never logged."""

    def _reply(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value: object) -> None:
        self._reply(
            status,
            json.dumps(value, ensure_ascii=False, allow_nan=False).encode(),
            "application/json; charset=utf-8",
        )

    def _allowed(self, *, api: bool) -> bool:
        host = self.server.origin.removeprefix("http://")
        if (
            self.headers.get("Host") != host
            or self.headers.get("Origin", self.server.origin) != self.server.origin
        ):
            self._json(
                403,
                {"error": "This browser adapter accepts its own local window only."},
            )
            return False
        if api and not secrets.compare_digest(
            self.headers.get("Authorization", "").encode(),
            ("Bearer " + self.server.token).encode(),
        ):
            self._json(
                401, {"error": "Launch Chemvas again to open an authorized window."}
            )
            return False
        return True

    def do_GET(self) -> None:
        if not self._allowed(api=self.path.startswith("/api/")):
            return
        if self.path == "/api/new":
            self._json(200, document_info(new_document(), render=False))
        elif self.path == "/api/ui":
            self._json(200, ui_spec())
        elif self.path == "/ui.css":
            self._reply(200, ui_css().encode(), "text/css; charset=utf-8")
        elif self.path in STATIC_FILES:
            filename, mime = STATIC_FILES[self.path]
            self._reply(200, (ASSETS / filename).read_bytes(), mime)
        else:
            self._json(404, {"error": "Not found."})

    def do_POST(self) -> None:
        if not self._allowed(api=True):
            return
        if self.path not in {
            "/api/open",
            "/api/session",
            "/api/atom-input",
        }:
            self._json(404, {"error": "Not found."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_REQUEST_BYTES:
                self._json(
                    413,
                    {"error": "The browser adapter accepts JSON files up to 2 MiB."},
                )
                return
            if self.headers.get(
                "Content-Type"
            ) != "application/json" or self.headers.get("Transfer-Encoding"):
                self._json(
                    415, {"error": "Expected a JSON request with Content-Length."}
                )
                return
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("Incomplete request.")
            request = strict_json_loads(body)
            if self.path == "/api/atom-input":
                self._json(200, atom_input_plan(request))
                return
            if self.path == "/api/session":
                if not isinstance(request, dict):
                    raise ValueError("Expected a session request.")
                session_result: dict[str, Any] | None = None
                with self.server.session_lock:
                    session_id = request.get("session")
                    session: BrowserSession | None
                    if not session_id:
                        if request.get("revision") != 0:
                            raise ValueError(
                                "A new session must start at revision zero."
                            )
                        if len(self.server.sessions) >= 16:
                            raise ValueError(
                                "Close a browser window before opening another."
                            )
                        session_id = secrets.token_urlsafe(24)
                        session = BrowserSession()
                        if request.get("action") == "close":
                            session_result = {}
                        else:
                            session_result = {
                                **session.dispatch(request),
                                "session": session_id,
                            }
                            self.server.sessions[session_id] = session
                    else:
                        session = self.server.sessions.get(session_id)
                    if session is None:
                        raise ValueError("This browser adapter session has ended.")
                if session_result is None:
                    with session.lock:
                        if session.closed:
                            raise ValueError("This browser adapter session has ended.")
                        if request.get("action") == "close":
                            session.closed = True
                            with self.server.session_lock:
                                self.server.sessions.pop(session_id, None)
                            session_result = {}
                        else:
                            session_result = {
                                **session.dispatch(request),
                                "session": session_id,
                            }
                self._json(200, session_result)
                return
            result = document_info(request, render=False)
        except StaleRevisionError as exc:
            self._json(409, {"error": str(exc)})
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
            self._json(400, {"error": str(exc) or "Invalid document."})
        else:
            self._json(200, result)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Open the Chemvas browser adapter. Stop with Ctrl+C."
    )
    parser.add_argument(
        "--port", type=int, default=0, help="Local port (default: choose a free port)"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Print the launch URL without opening a browser",
    )
    args = parser.parse_args(argv)
    with BrowserServer(args.port) as server:
        url = f"{server.origin}/#token={server.token}"
        print(f"Chemvas browser adapter: {url}", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        with suppress(KeyboardInterrupt):
            server.serve_forever()


if __name__ == "__main__":
    main()
