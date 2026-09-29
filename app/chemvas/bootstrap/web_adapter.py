"""Local browser adapter over existing Chemvas UI definitions and editing services."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import secrets
import sys
import webbrowser
from collections import Counter
from contextlib import nullcontext, suppress
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import pairwise
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast, override

from chemvas.core.history import HistoryCommand
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    MAX_ARROW_LABEL_CHARS,
    VALID_ARC_KINDS,
    VALID_EQUILIBRIUM_KINDS,
    VALID_MARK_KINDS,
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
    unmarked_isolated_carbon_ids,
)
from chemvas.domain.document.marks import (
    mark_center_coordinates,
    mark_state_at_position,
    scaled_mark_offset,
)
from chemvas.domain.document.orbitals import (
    Orbital,
    orbital_from_state,
    orbital_to_state,
)
from chemvas.domain.document.ring_fills import RingFill, ring_fill_to_state
from chemvas.domain.document.shapes import (
    Shape,
    moved_shape,
    normalized_shape,
    shape_from_state,
    shape_to_state,
)
from chemvas.domain.document.sheet import (
    CUSTOM_SHEET_SIZE,
    MAX_SHEET_MM,
    MIN_SHEET_MM,
    SHEET_SIZES_MM,
)
from chemvas.domain.document.ts_brackets import (
    TSBracket,
    moved_ts_bracket,
    ts_bracket_from_state,
    ts_bracket_to_state,
)
from chemvas.domain.json_io import strict_json_loads
from chemvas.domain.transactions import RestoreOutcome
from chemvas.features.annotations import (
    ATOM_LABEL_DOCUMENT_MARGIN,
    ATOM_LABEL_HIT_PADDING_RATIO,
    LABEL_SYNTAX_HINT,
    SUB_SCALE,
    arrow_label_html,
    arrow_label_position,
    atom_label_presentation,
    cleaned_arrow_labels,
    flip_annotation,
    hydride_hydrogen_text,
    label_bounding_rect,
    mark_dimensions,
    orbital_geometry,
    parse_atom_label,
    place_hydride_stack,
    place_runs,
    rotate_annotation,
    split_hydride_label,
    uses_compact_label_hit_shape,
)
from chemvas.features.annotations.brackets import (
    BRACKET_MENU_SPECS,
    BRACKET_SYMBOLS,
    DEFAULT_BRACKET_KIND,
    bracket_path_commands,
    bracket_rect_from_points,
    bracket_stroke_width,
    bracket_symbol_layout,
)
from chemvas.features.document_composition import compose_document_state
from chemvas.features.graph import (
    CanvasGraphState,
    add_bond_to_atom_index,
    build_bond_adjacency_index,
    build_ring_edge_index,
    connected_components_for_nodes,
    ring_atom_ids_for_bond,
    selected_ring_cycles,
)
from chemvas.features.hover import (
    ATOM_HOVER_BRUSH_RGBA,
    ATOM_HOVER_PEN_RGBA,
    ATOM_HOVER_RADIUS_RATIO,
    ATOM_HOVER_Z,
    HOVER_PREVIEW_OPACITY,
    HOVER_PREVIEW_Z,
    PREVIEW_COLOR_RGBA,
)
from chemvas.features.insertion import (
    build_atom_annotations,
    opposite_charge_mark,
    plan_mark_rebind,
)
from chemvas.features.rendering import (
    ENDPOINT_SNAP_SCREEN_PX,
    LINE_ANGLE_STEP_DEGREES,
    ACS1996Style,
    RenderMetrics,
    arrow_path_commands,
    arrow_with_moved_endpoint,
    clamp_curved_midpoint,
    control_from_midpoint,
    curved_midpoint,
    cycle_plain_bond_style,
    grid_lines,
    line_click_endpoint,
    line_normal,
    new_arrow_record,
    normalized_arrow_control,
    snapped_drawing_point,
)
from chemvas.features.selection import (
    ARROW_PICK_SCREEN_PX,
    ROTATION_SNAP_STEP_DEGREES,
    AtomHitCandidate,
    BondHitCandidate,
    bond_pick_candidates,
    choose_mark_atom,
    choose_preferred_structure_hit,
    distance_point_to_segment,
    independent_selection_items,
    mark_precedes_atom,
    nearest_atom_id,
    nearest_bond_id,
    nearest_ring_atom_id,
    orbital_handle_positions,
    orbital_rotation_angle,
    orbital_scale_factor,
    reflected_point,
    rotated_atom_positions,
    rotated_point_coordinates,
    rotation_drag_angle,
    selected_atom_ids_with_bond_endpoints,
    selection_frame_applies,
    selection_transform_center,
)
from chemvas.shell import toolbar_styles
from chemvas.shell.icon_design import DESIGN_ICON_NAMES, design_icon_svg
from chemvas.shell.palette import PALETTE, RING_FILL_TINT, SHAPE_FILL_TINT, pastel_rgb
from chemvas.ui.annotations.shape_geometry import (
    EDGE_HANDLE_SCREEN_PX,
    resized_shape_bounds,
    shape_handle_positions,
    shape_outline,
    shape_rect_from_points,
    shape_stroke_width,
)
from chemvas.ui.canvas.canvas_chemdraw_shortcut_service import (
    CanvasChemdrawShortcutService,
)
from chemvas.ui.canvas.canvas_geometry_logic import (
    glyph_clearance_radius,
    glyph_contour_clip_t,
    glyph_convex_hull,
    mark_clearance,
    mark_click_offset,
    mark_target_distance,
    shortcut_mark_offset,
)
from chemvas.ui.canvas.canvas_history_service import CanvasHistoryService
from chemvas.ui.canvas.canvas_history_state import CanvasHistoryState
from chemvas.ui.canvas.canvas_mark_registry import CanvasMarkRegistry
from chemvas.ui.canvas.canvas_move_controller import CanvasMoveController
from chemvas.ui.canvas.canvas_ring_fill_scene_service import rebuild_ring_fill_polygons
from chemvas.ui.canvas.canvas_tool_settings_state import (
    GRID_COLOR,
    GRID_CONTROL_HINT,
    GRID_MODES,
    GRID_STRENGTHS,
    MIN_GRID_SPACING_PX,
    CanvasToolSettingsState,
    grid_step_for,
    normalized_arrow_style,
)
from chemvas.ui.canvas.pick_radius_access import (
    STRUCTURE_BOND_PICK_RADIUS_RATIO,
    atom_pick_radius,
    atom_pick_radius_for,
)
from chemvas.ui.canvas.sheet_setup_logic import (
    OFF_SHEET_EDIT_GUIDANCE,
    SHEET_DIMENSION_DECIMALS,
    SHEET_DIMENSION_STEP_MM,
    SHEET_ORIENTATION_OPTIONS,
    SHEET_SETUP_TEXT,
    normalize_sheet_setup,
    scene_pos_in_sheet,
    sheet_dimensions_px,
    sheet_scene_bounds,
    supported_sheet_sizes,
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
from chemvas.ui.scene.mark_ownership import (
    DISTANT_MARK_COLOR,
    MARK_OWNER_GUIDANCE,
    mark_is_distant_for,
    mark_owner_text_for,
)
from chemvas.ui.scene.scene_align_logic import (
    align_deltas,
    alignment_objects,
    distribute_deltas,
)
from chemvas.ui.scene.scene_delete_plan import (
    DeleteSelectionBuckets,
    build_delete_selection_plan,
    hover_delete_target,
)
from chemvas.ui.scene.stacking_actions import stacked_depths
from chemvas.ui.selection.selection_style_access import (
    SELECTION_OBJECT_PADDING_RATIO,
    SELECTION_OUTLINE_SCREEN_PX,
    selection_arrow_overlay_width,
    selection_atom_rect,
    selection_bond_overlay_width,
    selection_bond_parts,
    selection_structure_ids,
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
    ALIGN_MENU_SPECS,
    ALIGN_SPECS,
    ARROW_MENU_SPECS,
    ARROW_PRESET_SPECS,
    ARROW_SLIDER_LABELS,
    ARROW_SLIDER_PAGE_STEP,
    ARROW_SLIDER_RANGES,
    ATOM_INPUT_SPEC,
    BOND_MODIFIERS,
    BOND_ORDER_SEGMENTS,
    COLOR_PALETTE_SPECS,
    COLOR_TOOL_MESSAGES,
    DISTRIBUTE_MENU_SPECS,
    DISTRIBUTE_SPECS,
    FLIP_ACTION_SPECS,
    HANDLE_ACCENT_COLOR,
    HANDLE_SCREEN_PX,
    LINE_KIND_SPECS,
    MARK_TOOL_ACTION_SPECS,
    MOLECULE_INFO_TITLE,
    MORE_ARROW_KINDS,
    ORBITAL_MO_TEXT,
    ORBITAL_PHASE_SPECS,
    REACTION_MAPPING_TITLE,
    RING_FILL_GUIDANCE,
    RING_FILL_TOOL_ACTION_SPEC,
    ROTATE_ANGLE_DEFAULT,
    ROTATE_ANGLE_RANGE,
    ROTATION_HANDLE_STEM_PX,
    ROTATION_HANDLE_TYPE,
    SELECTION_FRAME_RADIUS,
    SHAPE_KIND_SPECS,
    SHAPE_STROKE_SPECS,
    SHIFT_TOOL_HOTKEYS,
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
    ORBITAL_TYPE_BY_LABEL,
    arrow_preset_from_label,
    bond_style_from_label,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

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
        "line_options": [
            {
                "key": kind,
                "label": label,
                "icon": design_icon_svg("line_plain" if kind == "line" else kind),
            }
            for kind, label in LINE_KIND_SPECS
        ],
        "orbital_options": [
            {
                "key": kind,
                "label": f"Orbital: {label}",
                "icon": design_icon_svg(f"orbital_{kind}")
                if not kind.startswith("mo_")
                else "",
                "text": ORBITAL_MO_TEXT.get(kind),
            }
            for label, kind in ORBITAL_TYPE_BY_LABEL.items()
        ],
        "orbital_phases": [
            {
                "key": enabled,
                "label": label,
                "icon": design_icon_svg(f"orbital_phase_{'on' if enabled else 'off'}"),
            }
            for label, enabled in ORBITAL_PHASE_SPECS
        ],
        "bracket_options": [
            {
                "key": kind,
                "label": label,
                "icon": design_icon_svg(f"bracket_{kind}"),
            }
            for label, kind in BRACKET_MENU_SPECS
        ],
        "default_bracket_kind": CanvasToolSettingsState().active_bracket_type,
        "mark_options": [
            {
                "key": kind,
                "label": label,
                "tip": tip,
                "icon": design_icon_svg(DESIGN_ICON_NAMES[icon]),
            }
            for _key, label, kind, icon, tip in MARK_TOOL_ACTION_SPECS
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
        "arrow_labels": {
            "hint": LABEL_SYNTAX_HINT,
            "limit": MAX_ARROW_LABEL_CHARS,
            "preview": {
                "family": "Arial",
                "pixels": browser_font_pixels(14),
                "script_pixels": browser_font_pixels(14 * 2 // 3),
                "weight": 400,
                "italic": False,
                "color": PALETTE["text"],
            },
        },
        "color_messages": COLOR_TOOL_MESSAGES,
        "color_palette": [
            {"label": label, "color": color} for label, color in COLOR_PALETTE_SPECS
        ],
        "shape_options": [
            {"key": kind, "label": label, "icon": design_icon_svg(f"shape_{kind}")}
            for kind, label in SHAPE_KIND_SPECS
        ],
        "shape_strokes": [
            {"key": kind, "label": label, "icon": design_icon_svg(f"stroke_{kind}")}
            for kind, label in SHAPE_STROKE_SPECS
        ],
        "grid": {
            "modes": GRID_MODES,
            "strengths": GRID_STRENGTHS,
            "hint": GRID_CONTROL_HINT,
            "color": GRID_COLOR,
            "minimum_spacing": MIN_GRID_SPACING_PX,
            "step": CanvasToolSettingsState().grid_snap_step,
            "style": CanvasToolSettingsState().grid_style,
            "opacity": CanvasToolSettingsState().grid_opacity,
            "tiles": {
                style: {
                    "size": [width, height],
                    "lines": grid_lines((0, 0, width, height), step=1, style=style),
                }
                for style, width, height in (("square", 1, 1), ("hex", 3, math.sqrt(3)))
            },
        },
        "sheet_setup": {
            "text": SHEET_SETUP_TEXT,
            "sizes": supported_sheet_sizes(),
            "dimensions": SHEET_SIZES_MM,
            "custom": CUSTOM_SHEET_SIZE,
            "orientations": SHEET_ORIENTATION_OPTIONS,
            "minimum": MIN_SHEET_MM,
            "maximum": MAX_SHEET_MM,
            "decimals": SHEET_DIMENSION_DECIMALS,
            "step": SHEET_DIMENSION_STEP_MM,
        },
        "arrange_actions": {
            kind: [
                {
                    "mode": mode,
                    "tip": tip,
                    "label": labels[mode],
                    "icon": design_icon_svg(f"{icon}_{mode}"),
                }
                for mode, tip in specs
            ]
            for kind, specs, labels, icon in (
                (
                    "align",
                    ALIGN_SPECS,
                    {mode: text for text, mode in ALIGN_MENU_SPECS},
                    "align_objects",
                ),
                (
                    "distribute",
                    DISTRIBUTE_SPECS,
                    {mode: text for text, mode in DISTRIBUTE_MENU_SPECS},
                    "distribute",
                ),
            )
        },
        "flip_actions": [
            {
                "label": label,
                "icon": design_icon_svg(DESIGN_ICON_NAMES[icon]),
                "shortcut": shortcut,
                "horizontal": horizontal,
            }
            for _name, icon, label, shortcut, horizontal in FLIP_ACTION_SPECS
        ],
        "rotation": {
            "minimum": ROTATE_ANGLE_RANGE[0],
            "maximum": ROTATE_ANGLE_RANGE[1],
            "default": ROTATE_ANGLE_DEFAULT,
        },
        "mark_hover": {
            "color": PREVIEW_COLOR_RGBA,
            "opacity": HOVER_PREVIEW_OPACITY,
            "z": HOVER_PREVIEW_Z,
            "atom_z": ATOM_HOVER_Z,
            "pen": ATOM_HOVER_PEN_RGBA,
            "brush": ATOM_HOVER_BRUSH_RGBA,
        },
        "handles": {
            "size": HANDLE_SCREEN_PX,
            "edge_size": EDGE_HANDLE_SCREEN_PX,
            "color": HANDLE_ACCENT_COLOR,
            "rotation_stem": ROTATION_HANDLE_STEM_PX,
            "rotation_type": ROTATION_HANDLE_TYPE,
            "frame_radius": SELECTION_FRAME_RADIUS,
        },
        "arrow_style_controls": [
            {
                "label": f"{label} arrow preset",
                "preset": label,
                "icon": design_icon_svg(f"arrow_preset_{label.lower()}"),
            }
            for label in ARROW_PRESET_SPECS
        ]
        + [
            {
                "label": label,
                "icon": design_icon_svg(icon),
                "setting": setting,
                "minimum": ARROW_SLIDER_RANGES[setting][0],
                "maximum": ARROW_SLIDER_RANGES[setting][1],
                "factor": ARROW_SLIDER_RANGES[setting][2],
                "page_step": ARROW_SLIDER_PAGE_STEP,
            }
            for (setting, label), icon in zip(
                ARROW_SLIDER_LABELS.items(),
                ("arrow_width", "arrow_head_scale"),
                strict=True,
            )
        ],
        # Browsers do not expose the desktop system drag-distance preference.
        "drag_distance": 10,
        "max_document_bytes": MAX_REQUEST_BYTES,
        "hints": TOOL_HINTS,
        "off_sheet_guidance": OFF_SHEET_EDIT_GUIDANCE,
        "tool_hotkeys": TOOL_HOTKEYS,
        "shift_tool_hotkeys": {
            key: {
                "tool": tool,
                "value": {
                    "ts_bracket": DEFAULT_BRACKET_KIND,
                    "orbital": CanvasChemdrawShortcutService.DEFAULT_ORBITAL_TYPE,
                    "mark": CanvasChemdrawShortcutService.DEFAULT_MARK_KIND,
                }[tool],
            }
            for key, tool in SHIFT_TOOL_HOTKEYS.items()
        },
        "hover_shortcuts": sorted(
            CanvasChemdrawShortcutService.ATOM_HOTKEYS
            | CanvasChemdrawShortcutService.BOND_HOTKEYS
        ),
        "default_bond_style": CanvasToolSettingsState().active_bond_style,
        "default_arrow_style": CanvasChemdrawShortcutService.DEFAULT_ARROW_TYPE,
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
                ("molecule_info", MOLECULE_INFO_TITLE),
                ("reaction_mapping", REACTION_MAPPING_TITLE),
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
    payload: object,
    *,
    render: bool = True,
    font: BrowserFontMeasurements | None = None,
    mark_order: dict[int, list[int]] | None = None,
) -> dict[str, Any]:
    """Validate without dropping data; unsupported drawings remain read-only."""
    document = normalize_json_numbers(payload)
    state = extract_document_state(document)
    if len(json.dumps(document, ensure_ascii=False).encode()) > MAX_REQUEST_BYTES:
        raise ValueError("The browser adapter supports documents up to 2 MiB.")
    model = state["model"]
    if len(model["atoms"]) > 2000 or len(model["bonds"]) > 3000:
        raise ValueError(
            "The browser adapter supports up to 2,000 atoms and 3,000 bonds."
        )
    reasons = [
        key.replace("_", " ")
        for key in (
            "images",
            "groups",
            "perspective",
            "calculation_plan",
        )
        if state.get(key)
    ]
    mark_kinds: dict[int, list[str]] = {int(key): [] for key in model["atoms"]}
    for mark in state["marks"]:
        if mark["atom_id"] in mark_kinds:
            mark_kinds[mark["atom_id"]].append(mark["kind"])
    expected_annotations = build_atom_annotations(
        mark_kinds, {key: key for key in mark_kinds}, mark_kinds
    )
    actual_annotations = {
        int(key): {name: value for name, value in annotation.items() if value}
        for key, annotation in model.get("atom_annotations", {}).items()
        if any(annotation.values())
    }
    if actual_annotations != expected_annotations:
        reasons.append("atom charges, isotopes or radicals")
    if any(bond["style"] not in SUPPORTED_BONDS for bond in model["bonds"] if bond):
        reasons.append("additional bond styles")
    if state["notes"]:
        reasons.append("text annotations")
    settings = state["settings"]
    if settings.get("note_box_enabled") or settings.get("note_border_enabled"):
        reasons.append("note backgrounds or borders")
    width, height = sheet_dimensions_px(
        settings["sheet_size"],
        settings["sheet_orientation"],
        settings.get("sheet_custom_size_mm"),
    )
    if mark_order is None:
        mark_order = {}
        for index, mark in enumerate(state["marks"]):
            if mark["atom_id"] is not None:
                mark_order.setdefault(mark["atom_id"], []).append(index)
    info = {
        "mark_order": mark_order,
        "document": document,
        "unsupported": reasons,
        "sheet": [width, height],
        "style": asdict(ACS1996Style()),
    }
    if render:
        if font is None and (
            state["marks"]
            or any(arrow.get("labels") for arrow in state["arrows"])
            or any(
                bracket["bracket_kind"] in BRACKET_SYMBOLS
                for bracket in state["ts_brackets"]
            )
        ):
            font = BrowserFontMeasurements(
                {"family": ACS1996Style().font_family, "metrics": {}, "ink": {}}
            )
        drawing = drawing_geometry(state) if font is None else font.drawing(state)
        if not reasons and not drawing.get("needs_measurements"):
            drawing["scene_rect"] = browser_scene_rect(width, height, drawing)
        info["drawing"] = drawing
    return info


def browser_font_pixels(point_size: float) -> int:
    # The desktop pins AA_Use96Dpi; QFont resolves that em size to integer pixels.
    return max(1, round(point_size * 96 / 72))


def _browser_label_queries(size: int, labels: Any) -> list[dict[str, Any]]:
    texts = {"H", "+", "-"}
    for display, anchor, _at_end, below in labels:
        texts.update(run.text for run in parse_atom_label(display))
        if "\n" in display or "\r" in display:
            texts.update(display.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
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
        "mark_queries": _browser_label_queries(size, [("H", None, False, None)]),
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
            "bounding_width",
        }:
            raise ValueError(
                "Expected advance and bounding widths, ascent, descent, capital height and line height."
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


def place_browser_labels(
    size: int,
    labels: list[tuple[str, str | None, bool, bool | None]],
    measurements: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Adapt measured font metrics to the existing native run placer, at origin."""
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
        height = (
            layout.height
            if layout.has_typography or below is not None
            else float(measurements[f"{size}:{display}"]["line_height"])
        )
        margin = ATOM_LABEL_DOCUMENT_MARGIN
        result.append(
            {
                "rect": (
                    -center_x - margin,
                    -center_y - margin,
                    layout.width + 2 * margin,
                    height + 2 * margin,
                ),
                "runs": [
                    {
                        "text": run.text,
                        "size": run.point_size,
                        "pixels": browser_font_pixels(run.point_size),
                        "x": run.x - center_x,
                        "y": run.baseline - center_y,
                    }
                    for run in layout.runs
                ],
            }
        )
    return result


def shape_geometry(
    state: dict[str, Any], metrics: RenderMetrics
) -> list[dict[str, Any]]:
    result = []
    for source in state["shapes"]:
        shape = normalized_shape(shape_from_state(source))
        kind, x, y, width, height, radius = shape_outline(
            shape.left,
            shape.top,
            shape.right - shape.left,
            shape.bottom - shape.top,
            shape.shape_kind,
        )
        pad = metrics.style.bond_length_px * SELECTION_OBJECT_PADDING_RATIO
        line_width = shape_stroke_width(metrics.style.bond_line_width)
        # A native empty path has an empty scene bound at the origin.
        empty = width == 0 and height == 0
        selection = {
            "outline": {
                "kind": "rect" if empty else kind,
                "x": -pad if empty else x,
                "y": -pad if empty else y,
                "width": pad * 2 if empty else width,
                "height": pad * 2 if empty else height,
                "radius": pad * 0.7 if empty else radius,
            },
            "width": 0.0
            if empty
            else pad * 2 + (0.0 if shape.stroke_style == "none" else line_width),
        }
        half = 0.0 if shape.stroke_style == "none" else line_width / 2
        result.append(
            {
                "kind": kind,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "radius": radius,
                "stroke": shape.stroke_style,
                "line_width": line_width,
                # Painted scene bounds; an empty native path has none.
                "bounds": None
                if empty
                else (x - half, y - half, width + 2 * half, height + 2 * half),
                "selection": selection,
                "color": metrics.style.bond_color,
                "fill": shape.fill,
                "alpha": shape.fill_alpha,
                "z": -10.0 if shape.z is None else shape.z,
                "handles": [
                    {"handle": name, "point": point}
                    for name, point in shape_handle_positions(
                        (shape.left, shape.top, shape.right, shape.bottom)
                    )
                ],
            }
        )
    return result


def arrow_geometry(
    state: dict[str, Any], metrics: RenderMetrics
) -> list[dict[str, Any]]:
    """The same native arrow paths feed browser painting and picking."""
    arrows = []
    arrow_point_count = 0
    endpoint_counts = Counter(
        tuple(point)
        for arrow in state["arrows"]
        for point in (arrow["start"], arrow["end"])
    )
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
        record = normalized_arrow_control(arrow_from_state(arrow))
        positions = [("start", record.start), ("end", record.end)]
        if record.control is not None:
            positions.insert(
                1,
                ("control", curved_midpoint(record.start, record.control, record.end)),
            )
        own_counts = Counter((record.start, record.end))
        width = (
            metrics.bold_bond_width()
            if arrow["kind"] == "line_bold"
            else state["settings"]["arrow_line_width"]
        )
        arrows.append(
            {
                "path": commands,
                "handles": [
                    {
                        "handle": name,
                        "point": pos,
                        "snapped": name != "control"
                        and endpoint_counts[pos] > own_counts[pos],
                    }
                    for name, pos in positions
                ],
                "width": width,
                "selection_width": selection_arrow_overlay_width(
                    width,
                    metrics.style.bond_length_px * 0.12,
                    atom_pick_radius(metrics),
                ),
                "dashed": arrow["kind"] in {"dotted", "line_dashed"},
                "cap": "butt" if arrow["kind"] == "line_bold" else "round",
                "join": "miter" if arrow["kind"] == "line_bold" else "round",
                "color": arrow.get("color") or metrics.style.bond_color,
            }
        )
    return arrows


def _curve_frame_controls(
    start: tuple[float, ...],
    control: tuple[float, ...],
    end: tuple[float, ...],
    width: float,
) -> list[tuple[float, ...]]:
    """Bound the offset cubic controls used by Qt's path-item frame.

    The painted quadratic remains unchanged. Quarter-point distance and normal
    checks split only the bounding approximation, with Qt's width-dependent
    tolerance and bounded subdivision depth.
    """
    result: list[tuple[float, ...]] = []
    threshold = max(0.00025, min(0.25, 1 / width))
    for offset in (-width / 2, width / 2):
        pending = [(start, control, end, 0)]
        while pending:
            a, q, b, depth = pending.pop()
            points = [
                a,
                tuple(a[i] + 2 * (q[i] - a[i]) / 3 for i in (0, 1)),
                tuple(b[i] + 2 * (q[i] - b[i]) / 3 for i in (0, 1)),
                b,
            ]
            unique: list[tuple[float, ...]] = []
            indices = []
            for p in points:
                if not unique or p != unique[-1]:
                    unique.append(p)
                indices.append(len(unique) - 1)
            if len(unique) < 2:
                continue
            normals = []
            for p, r in pairwise(unique):
                dx, dy = r[0] - p[0], r[1] - p[1]
                length = math.hypot(dx, dy)
                normals.append((dy / length, -dx / length))
            normals = [normals[0], *normals, normals[-1]]
            shifted = []
            for i, p in enumerate(unique):
                n, m = normals[i : i + 2]
                divisor = 1 + sum(n[k] * m[k] for k in (0, 1))
                vector = (
                    n
                    if abs(divisor) < 1e-12
                    else tuple((n[k] + m[k]) / divisor for k in (0, 1))
                )
                shifted.append(tuple(p[k] + offset * vector[k] for k in (0, 1)))
            shifted = [shifted[i] for i in indices]
            fits = True
            for t in (0.25, 0.5, 0.75):
                weights = (
                    (1 - t) ** 3,
                    3 * t * (1 - t) ** 2,
                    3 * t * t * (1 - t),
                    t**3,
                )
                delta = [
                    sum((shifted[j][k] - points[j][k]) * weights[j] for j in range(4))
                    for k in (0, 1)
                ]
                tangent = [
                    2 * ((1 - t) * (q[k] - a[k]) + t * (b[k] - q[k])) for k in (0, 1)
                ]
                norm = sum(abs(v) for v in tangent)
                if abs(
                    sum(v * v for v in delta) - offset * offset
                ) > threshold * offset * offset or (
                    norm
                    and abs(sum(tangent[k] * delta[k] for k in (0, 1))) / norm
                    > threshold * abs(offset)
                ):
                    fits = False
                    break
            if fits or depth >= 9:
                result.extend(shifted)
            else:
                left = tuple((a[k] + q[k]) / 2 for k in (0, 1))
                right = tuple((q[k] + b[k]) / 2 for k in (0, 1))
                middle = tuple((left[k] + right[k]) / 2 for k in (0, 1))
                pending.extend(
                    [(middle, right, b, depth + 1), (a, left, middle, depth + 1)]
                )
    return result


def bracket_rect(source: dict[str, Any]) -> tuple[float, float, float, float]:
    left, right = sorted((source["left"], source["right"]))
    top, bottom = sorted((source["top"], source["bottom"]))
    return left, top, right - left, bottom - top


def bracket_glyph_queries(
    state: dict[str, Any], bond_length: float
) -> list[dict[str, Any]]:
    """Font queries for dagger glyphs, measured at their own pixel sizes."""
    queries = {}
    for source in state["ts_brackets"]:
        text = BRACKET_SYMBOLS.get(source["bracket_kind"])
        if text is not None:
            pixels, _x, _y = bracket_symbol_layout(bracket_rect(source), bond_length)
            key = f"bracket:{pixels}:{text}"
            # Point size at the pinned 96 DPI, so the query resolves to ``pixels``.
            queries[key] = {
                "key": key,
                "text": text,
                "size": pixels * 72 / 96,
                "pixels": pixels,
            }
    return list(queries.values())


# QPainterPathStroker's default miter limit, in stroke widths.
_STROKER_MITER_LIMIT = 2.0


def bracket_outline(
    commands: list[tuple[str, tuple[float, ...]]], width: float
) -> list[list[tuple[float, float]]]:
    """Closed rings approximating the flat-cap, miter-join outline Qt fills.

    Points are offset along exact curve normals and joins keep their miter
    corners, so bounds and pick distances agree well below a device pixel;
    Qt offsets curves as curves rather than samples.
    """
    half = width / 2
    limit = _STROKER_MITER_LIMIT * width
    rings: list[list[tuple[float, float]]] = []
    left: list[tuple[float, float]] = []
    right: list[tuple[float, float]] = []
    start = current = (0.0, 0.0)
    first: tuple[float, float] | None = None
    previous: tuple[float, float] | None = None

    def unit_normal(dx: float, dy: float) -> tuple[float, float]:
        length = math.hypot(dx, dy)
        return (-dy / length, dx / length)

    def join(
        point: tuple[float, float],
        before: tuple[float, float],
        after: tuple[float, float],
    ) -> None:
        sx, sy = before[0] + after[0], before[1] + after[1]
        length = math.hypot(sx, sy)
        reach = half / (length / 2) if length else math.inf
        if reach <= limit:
            ux, uy = sx / length, sy / length
            left.append((point[0] + ux * reach, point[1] + uy * reach))
            right.append((point[0] - ux * reach, point[1] - uy * reach))
            return
        # Qt clips an over-long miter at the limit, across the turn.
        # Directions follow from normals: (dx, dy) = (ny, -nx).
        dx, dy = before[1] - after[1], after[0] - before[0]
        length = math.hypot(dx, dy)
        if length:
            ux, uy = dx / length, dy / length
            tip = (point[0] + ux * limit, point[1] + uy * limit)
            left.append((tip[0] - uy * half, tip[1] + ux * half))
            right.append((tip[0] + uy * half, tip[1] - ux * half))

    def close() -> None:
        # Qt strokes a subpath that returns to its start as closed: a join
        # replaces both flat caps there.
        if first is not None and previous is not None and current == start:
            join(start, previous, first)
        if left:
            rings.append([*left, *reversed(right), left[0]])

    for command, values in commands:
        if command == "M":
            close()
            left, right = [], []
            start = current = (values[0], values[1])
            first = previous = None
            continue
        if command == "L":
            end = (values[0], values[1])
            if end == current:
                # A flat square bracket has zero-length sides; Qt drops them.
                continue
            normal = unit_normal(end[0] - current[0], end[1] - current[1])
            samples = [(current, normal), (end, normal)]
        else:
            (x0, y0), (x1, y1, x2, y2, x3, y3) = current, values
            end = (x3, y3)
            samples = []
            for step in range(65):
                t = step / 64
                u = 1 - t
                dx = (
                    3 * u * u * (x1 - x0)
                    + 6 * u * t * (x2 - x1)
                    + 3 * t * t * (x3 - x2)
                )
                dy = (
                    3 * u * u * (y1 - y0)
                    + 6 * u * t * (y2 - y1)
                    + 3 * t * t * (y3 - y2)
                )
                if not dx and not dy:
                    dx, dy = x3 - x0, y3 - y0
                samples.append(
                    (
                        (
                            u**3 * x0
                            + 3 * u * u * t * x1
                            + 3 * u * t * t * x2
                            + t**3 * x3,
                            u**3 * y0
                            + 3 * u * u * t * y1
                            + 3 * u * t * t * y2
                            + t**3 * y3,
                        ),
                        unit_normal(dx, dy),
                    )
                )
        if previous is None:
            first = samples[0][1]
        else:
            join(current, previous, samples[0][1])
        for (x, y), (nx, ny) in samples:
            left.append((x + nx * half, y + ny * half))
            right.append((x - nx * half, y - ny * half))
        previous, current = samples[-1][1], end
    close()
    return rings


def arrow_frame_bounds(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    points = []
    previous = (0, 0)
    pad = geometry["width"] / 2
    for command, values in geometry["path"]:
        end = tuple(values[-2:])
        if command == "Q":
            points.extend(
                _curve_frame_controls(
                    previous, tuple(values[:2]), end, geometry["width"]
                )
            )
        if command in ("L", "Q") and (previous != end or command == "Q"):
            if geometry["cap"] == "butt":
                dx, dy = end[0] - previous[0], end[1] - previous[1]
                length = math.hypot(dx, dy)
                if length:
                    for p in (previous, end):
                        for side in (-1, 1):
                            points.append(
                                (
                                    p[0] + side * pad * dy / length,
                                    p[1] - side * pad * dx / length,
                                )
                            )
            else:
                for p in (previous, end):
                    points.extend([(p[0] - pad, p[1] - pad), (p[0] + pad, p[1] + pad)])
                if command == "L":
                    dx, dy = end[0] - previous[0], end[1] - previous[1]
                    length = math.hypot(dx, dy)
                    tangent, normal = (
                        (dx / length, dy / length),
                        (-dy / length, dx / length),
                    )
                    # Native round caps use two cubic quarters; their controls
                    # extend beyond the painted circle on diagonal segments.
                    for point, direction in ((previous, -1), (end, 1)):
                        for side in (-1, 1):
                            for a, b in ((1.0, 0.5522847498), (0.5522847498, 1.0)):
                                points.append(
                                    tuple(
                                        point[i]
                                        + pad
                                        * (
                                            direction * a * tangent[i]
                                            + side * b * normal[i]
                                        )
                                        for i in (0, 1)
                                    )
                                )
        previous = end
    if not points:
        return (0.0, 0.0, 0.0, 0.0)
    x, y = min(p[0] for p in points), min(p[1] for p in points)
    return (x, y, max(p[0] for p in points) - x, max(p[1] for p in points) - y)


def browser_scene_rect(
    width: float, height: float, drawing: dict[str, Any]
) -> tuple[float, float, float, float]:
    """Adapt persistent drawing bounds to the native sheet scroll range."""
    rects = list(drawing.get("atom_hit_rects", {}).values())
    for primitives in drawing["bonds"].values():
        for primitive in primitives:
            if "line" in primitive:
                x1, y1, x2, y2 = primitive["line"]
                rects.append(
                    arrow_frame_bounds(
                        {
                            "path": [("M", (x1, y1)), ("L", (x2, y2))],
                            "width": drawing["line_width"],
                            "cap": "round",
                        }
                    )
                )
            else:
                points = primitive.get("polygon", primitive.get("dots", []))
                if not points:
                    continue
                pad = (
                    drawing["line_width"] / 2
                    if primitive.get("outlined")
                    else primitive.get("radius", 0)
                )
                left, top = min(p[0] for p in points), min(p[1] for p in points)
                rects.append(
                    (
                        left - pad,
                        top - pad,
                        max(p[0] for p in points) - left + 2 * pad,
                        max(p[1] for p in points) - top + 2 * pad,
                    )
                )
    rects.extend(arrow_frame_bounds(arrow) for arrow in drawing["arrows"])
    rects.extend(
        (label["x"], label["y"], label["width"], label["height"])
        for label in drawing.get("arrow_labels", [])
    )
    for shape in drawing["shapes"]:
        if shape["stroke"] == "none" and (not shape["fill"] or shape["alpha"] == 0):
            continue
        if shape["bounds"] is not None:
            rects.append(shape["bounds"])
    for mark in drawing.get("marks", []):
        if mark["kind"] in {"plus", "minus"}:
            if "hit_rect" in mark:
                rects.append(mark["hit_rect"])
        elif mark["kind"] == "radical":
            radius = mark["radius"]
            rects.append(
                (mark["x"] - radius, mark["y"] - radius, radius * 2, radius * 2)
            )
        else:
            rects.append(mark["bounds"])
    rects.extend(orbital["bounds"] for orbital in drawing.get("orbitals", []))
    rects.extend(
        bracket["bounds"]
        for bracket in drawing.get("brackets", [])
        if bracket["bounds"]
    )
    rects = [rect for rect in rects if rect[2] or rect[3]]
    content = None
    if rects:
        left, top = min(r[0] for r in rects), min(r[1] for r in rects)
        right, bottom = max(r[0] + r[2] for r in rects), max(r[1] + r[3] for r in rects)
        if right > left and bottom > top:
            content = (left, top, right - left, bottom - top)
    return sheet_scene_bounds(width, height, content)


def points_bounds(
    points: list[tuple[float, float]],
) -> tuple[float, float, float, float]:
    left, top = min(x for x, _ in points), min(y for _, y in points)
    return left, top, max(x for x, _ in points) - left, max(y for _, y in points) - top


def validated_color(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", value) is None:
        raise ValueError("Expected a six-digit color.")
    return value


def validated_drawing_scale(value: object) -> float:
    if type(value) not in (int, float, Decimal):
        raise ValueError("Invalid drawing scale.")
    scale = float(cast("Any", value))
    # Fit Page can show a large sheet below the manual zoom minimum.
    if not 0 < scale <= ZOOM_MAX or not math.isfinite(ENDPOINT_SNAP_SCREEN_PX / scale):
        raise ValueError("Invalid drawing scale.")
    return scale


def arrow_pick_segments(
    commands: list[tuple[str, tuple[float, ...]]], scale: float
) -> Iterator[tuple[BrowserPoint, BrowserPoint]]:
    """Flatten native quadratic commands with Qt's screen-space stopping rule.

    The equivalent quadratic flatness test uses the cubic control distances,
    a 0.5-pixel Manhattan threshold and at most nine midpoint subdivisions.
    """
    previous = (0.0, 0.0)
    for command, coordinates in commands:
        end = (coordinates[-2] * scale, coordinates[-1] * scale)
        if command == "L":
            yield BrowserPoint(*previous), BrowserPoint(*end)
        elif command == "Q":
            control = (coordinates[0] * scale, coordinates[1] * scale)
            pending = [(previous, control, end, 9)]
            while pending:
                start, control, finish, depth = pending.pop()
                dx, dy = finish[0] - start[0], finish[1] - start[1]
                length = abs(dx) + abs(dy)
                if length > 1:
                    flat = (
                        abs(dx * (control[1] - start[1]) - dy * (control[0] - start[0]))
                        < 0.375 * length
                    )
                else:
                    flat = (
                        sum(
                            abs(2 * (control[i] - start[i]) / 3)
                            + abs(
                                (finish[i] - start[i] + 2 * (control[i] - start[i])) / 3
                            )
                            for i in (0, 1)
                        )
                        < 0.5
                    )
                if flat or depth == 0:
                    yield BrowserPoint(*start), BrowserPoint(*finish)
                    continue
                left = ((start[0] + control[0]) / 2, (start[1] + control[1]) / 2)
                right = ((control[0] + finish[0]) / 2, (control[1] + finish[1]) / 2)
                middle = ((left[0] + right[0]) / 2, (left[1] + right[1]) / 2)
                pending.extend(
                    (
                        (middle, right, finish, depth - 1),
                        (start, left, middle, depth - 1),
                    )
                )
        previous = end


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
    selection_parts = {}
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
        parts = []
        for primitive in result[str(index)]:
            if "line" in primitive:
                segment = primitive["line"]
                parts.append(
                    {
                        **primitive,
                        "empty": segment[:2] == segment[2:],
                        "width": selection_bond_overlay_width(
                            metrics.bond_line_width(),
                            metrics.style.bond_spacing_px,
                            atom_pick_radius(metrics),
                        ),
                    }
                )
            else:
                parts.append(
                    {
                        "shape": primitive,
                        "empty": not primitive.get("polygon", primitive.get("dots")),
                    }
                )
        selection_parts[str(index)] = selection_bond_parts(
            parts,
            bond=bond,
            atom_a=model.atoms[bond.a],
            atom_b=model.atoms[bond.b],
            trim_line=trim_labels,
            spacing=metrics.style.bond_spacing_px,
            in_ring=bond.order == 2 and ring_center(bond) is not None,
        )
    brackets = []
    for source in state["ts_brackets"]:
        bounds = bracket_rect(source)
        kind = source["bracket_kind"]
        pixels, x, y = bracket_symbol_layout(bounds, metrics.style.bond_length_px)
        path = bracket_path_commands(bounds, kind, metrics.style.bond_length_px)
        width = bracket_stroke_width(metrics.style.bond_line_width)
        brackets.append(
            {
                "kind": kind,
                "path": path,
                "width": width,
                "color": metrics.style.bond_color,
                # Glyph bounds need the measured font; BrowserFontMeasurements adds them.
                "bounds": points_bounds(
                    [point for ring in bracket_outline(path, width) for point in ring]
                )
                if path
                else None,
                "symbol": {
                    "text": BRACKET_SYMBOLS[kind],
                    "x": x,
                    "y": y,
                    "pixels": pixels,
                    "family": metrics.style.font_family,
                }
                if kind in BRACKET_SYMBOLS
                else None,
            }
        )
    orbitals = []
    for source in state["orbitals"]:
        record = orbital_from_state(
            {**source, "kind": "orbital", "orbital_kind": source["kind"]}
        )
        ellipses, node = orbital_geometry(
            record.center, record.kind, metrics.style.bond_length_px
        )
        pad = metrics.bond_line_width() / 2
        left = min(x for x, _y, _w, _h, _phase in ellipses) - pad
        top = min(y for _x, y, _w, _h, _phase in ellipses) - pad
        right = max(x + w for x, _y, w, _h, _phase in ellipses) + pad
        bottom = max(y + h for _x, y, _w, h, _phase in ellipses) + pad
        if node is not None:
            left = min(left, min(node[0], node[2]) - pad)
            top = min(top, min(node[1], node[3]) - pad)
            right = max(right, max(node[0], node[2]) + pad)
            bottom = max(bottom, max(node[1], node[3]) + pad)
        cx, cy = record.center
        corners = [
            rotated_point_coordinates(
                BrowserPoint(
                    cx + (x - cx) * record.scale, cy + (y - cy) * record.scale
                ),
                BrowserPoint(cx, cy),
                math.radians(record.rotation),
            )
            for x, y in ((left, top), (right, top), (right, bottom), (left, bottom))
        ]
        xs, ys = zip(*corners, strict=True)
        orbitals.append(
            {
                "kind": record.kind,
                "center": record.center,
                "scale": record.scale,
                "rotation": record.rotation,
                "hit_rect": (left, top, right - left, bottom - top),
                "polygon": corners,
                "handles": [
                    {"handle": handle, "point": point}
                    for handle, point in zip(
                        ("scale", "rotate"),
                        orbital_handle_positions(
                            record.center, metrics.style.bond_length_px * 0.8
                        ),
                        strict=True,
                    )
                ],
                "bounds": (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)),
                "ellipses": ellipses,
                "node": node,
                "width": metrics.bond_line_width(),
                "color": metrics.style.bond_color,
                "positive": metrics.style.orbital_positive_color,
                "negative": metrics.style.orbital_negative_color,
                "alpha": metrics.style.orbital_alpha,
                "phase": state["settings"]["orbital_phase_enabled"],
            }
        )
    return {
        "bonds": result,
        "selection_bonds": selection_parts,
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
        "arrows": arrow_geometry(state, metrics),
        "selection_style": {
            "screen_width": SELECTION_OUTLINE_SCREEN_PX,
            "color": HANDLE_ACCENT_COLOR,
        },
        "shapes": shape_geometry(state, metrics),
        "orbitals": orbitals,
        "brackets": brackets,
    }


def browser_arrow_labels(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Original rich-text syntax, with Qt font sizes for the browser font engine."""
    settings = state["settings"]
    size = settings["text_font_size"]
    style = {
        "family": settings["text_font_family"],
        "pixels": browser_font_pixels(size),
        "script_pixels": browser_font_pixels(size * 2 // 3),
        "weight": settings["text_font_weight"],
        "italic": settings["text_italic"],
    }
    labels = []
    for index, arrow in enumerate(state["arrows"]):
        for side, text in arrow.get("labels", {}).items():
            html = arrow_label_html(text)
            key = hashlib.sha256(
                json.dumps([style, html], sort_keys=True).encode()
            ).hexdigest()
            labels.append(
                {
                    **style,
                    "key": key,
                    "html": html,
                    "id": index,
                    "side": side,
                    "color": arrow.get("color") or settings["text_color"],
                }
            )
    return labels


class BrowserFontMeasurements:
    """Bounded, replaceable browser font data; never part of document history."""

    def __init__(self, request: Any) -> None:
        if not isinstance(request, dict) or not {"family", "metrics", "ink"} <= set(
            request
        ) <= {"family", "metrics", "ink", "label_boxes"}:
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
        boxes = request.get("label_boxes", {})
        if (
            not isinstance(boxes, dict)
            or len(boxes) > 8192
            or any(
                not isinstance(key, str)
                or len(key) != 64
                or not isinstance(box, list)
                or len(box) != 2
                or any(
                    type(value) not in (int, float, Decimal)
                    or not math.isfinite(value)
                    or not 0 < value <= 100_000
                    for value in box
                )
                for key, box in boxes.items()
            )
        ):
            raise ValueError("Expected bounded arrow label boxes.")
        self.label_boxes = {
            key: tuple(float(value) for value in box) for key, box in boxes.items()
        }
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
        rich_labels = browser_arrow_labels(state)
        spec["arrow_labels"] = rich_labels
        mark_labels = [
            (
                mark.get("text")
                if mark.get("text") is not None
                else "+"
                if mark["kind"] == "plus"
                else "-",
                None,
                False,
                None,
            )
            for mark in state["marks"]
            if mark["kind"] in {"plus", "minus"}
        ]
        mark_labels = [label for label in mark_labels if label[0]]
        glyph_queries = bracket_glyph_queries(state, metrics.style.bond_length_px)
        if (
            not spec["labels"]
            and not rich_labels
            and not state["marks"]
            and not glyph_queries
        ):
            return drawing_geometry(state)
        spec["queries"] = [
            *_browser_label_queries(
                spec["size"],
                list(spec["labels"].values())
                + mark_labels
                + ([("H", None, False, None)] if state["marks"] else []),
            ),
            *glyph_queries,
        ]
        if any(label["key"] not in self.label_boxes for label in rich_labels) or any(
            query["key"] not in self.metrics
            or f"{query['pixels']}:{query['text']}" not in self.ink
            for query in spec["queries"]
        ):
            # Do not render a throwaway, unclipped scene while asking for its font.
            return {"label_measurements": spec, "needs_measurements": True}
        labels = list(
            dict.fromkeys(
                [tuple(label) for label in spec["labels"].values()] + mark_labels
            )
        )
        relative = dict(
            zip(
                labels,
                place_browser_labels(spec["size"], labels, self.metrics),
                strict=True,
            )
        )
        layouts, label_ink, hit_rects, selection_rects, label_rects = {}, {}, {}, {}, {}
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
                for run in relative[tuple(label)]["runs"]
            ]
            bx, by, bw, bh = relative[tuple(label)]["rect"]
            label_rects[key] = (
                atom.x + spec["offset"] + bx,
                atom.y - spec["offset"] + by,
                bw,
                bh,
            )
            selection_rects[key] = label_bounding_rect(
                (atom.x + spec["offset"] + bx, atom.y - spec["offset"] + by, bw, bh),
                metrics.style.bond_length_px * ATOM_LABEL_HIT_PADDING_RATIO,
                atom_pick_radius(metrics)
                if uses_compact_label_hit_shape(atom.element)
                else None,
            )
            if any(not math.isfinite(value) for value in selection_rects[key]):
                raise ValueError("Measured label bounds overflowed.")
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
                hit_rects[key] = points_bounds(points)
        drawing = drawing_geometry(state, label_ink)
        positioned = []
        for label in rich_labels:
            record = normalized_arrow_control(
                arrow_from_state(state["arrows"][label["id"]])
            )
            points = [
                (values[i], values[i + 1])
                for _, values in drawing["arrows"][label["id"]]["path"]
                for i in range(0, len(values), 2)
            ]
            width, height = self.label_boxes[label["key"]]
            x, y = arrow_label_position(
                record,
                points,
                bond_spacing=metrics.style.bond_spacing_px,
                side=label["side"],
                width=width,
                height=height,
            )
            if not all(math.isfinite(value) for value in (x, y)):
                raise ValueError("Measured arrow label coordinates overflowed.")
            positioned.append(
                {**label, "x": x, "y": y, "width": width, "height": height}
            )
        marks = []
        for index, mark in enumerate(state["marks"]):
            center = mark_center_coordinates(mark, model.atoms)
            if center is None:
                continue
            x, y = center
            kind = mark["kind"]
            geometry = {
                "id": index,
                "kind": kind,
                "x": x,
                "y": y,
                "color": mark.get("color") or metrics.style.atom_color,
            }
            if kind in {"plus", "minus"}:
                text = mark.get("text")
                text = ("+" if kind == "plus" else "-") if text is None else text
                runs = relative[(text, None, False, None)]["runs"] if text else []
                if text:
                    bx, by, bw, bh = relative[(text, None, False, None)]["rect"]
                else:
                    height = float(self.metrics[f"{spec['size']}:H"]["line_height"])
                    margin = ATOM_LABEL_DOCUMENT_MARGIN
                    bx, by, bw, bh = (
                        -margin,
                        -height / 2 - margin,
                        margin * 2,
                        height + margin * 2,
                    )
                geometry["runs"] = [
                    {**run, "x": x + run["x"], "y": y + run["y"]} for run in runs
                ]
                lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
                if len(lines) > 1 and all(
                    run.role == "normal" for run in parse_atom_label(text)
                ):
                    base = self.metrics[f"{spec['size']}:H"]
                    width = max(
                        float(self.metrics[f"{spec['size']}:{line}"]["width"])
                        for line in lines
                    )
                    height = float(base["line_height"]) * len(lines)
                    margin = ATOM_LABEL_DOCUMENT_MARGIN
                    bx, by, bw, bh = (
                        -width / 2 - margin,
                        -height / 2 - margin,
                        width + margin * 2,
                        height + margin * 2,
                    )
                    geometry["runs"] = [
                        {
                            "text": line,
                            "size": spec["size"],
                            "pixels": browser_font_pixels(spec["size"]),
                            "x": x - width / 2,
                            "y": y
                            - height / 2
                            + float(base["ascent"])
                            + row * float(base["line_height"]),
                        }
                        for row, line in enumerate(lines)
                        if line
                    ]
                geometry["bounds"] = label_bounding_rect(
                    (x + bx, y + by, bw, bh), 0.0, atom_pick_radius(metrics)
                )
                ink = [
                    (px + run["x"], py + run["y"])
                    for run in geometry["runs"]
                    for px, py in self.ink[f"{run['pixels']}:{run['text']}"]
                ]
                if ink:
                    geometry["hit_rect"] = points_bounds(ink)
            else:
                base_font = self.metrics[f"{spec['size']}:H"]
                radius, stroke, extent = mark_dimensions(
                    kind,
                    metrics.style.bond_line_width,
                    float(base_font["ascent"]) + float(base_font["descent"]),
                )
                geometry.update(radius=radius, stroke=stroke, extent=extent)
                hit_pad = max(0.0, atom_pick_radius(metrics) - radius)
                # Qt path bounds include the custom hit stroke before adding padding.
                bound_radius = (
                    (radius + max(stroke / 2, hit_pad) + hit_pad)
                    if kind.startswith("circled_")
                    else radius + hit_pad
                )
                geometry["bounds"] = (
                    x - bound_radius,
                    y - bound_radius,
                    bound_radius * 2,
                    bound_radius * 2,
                )
            geometry["hit_radius"] = atom_pick_radius(metrics)
            marks.append(geometry)
        if any(
            not math.isfinite(value)
            for mark in marks
            for value in (
                mark["x"],
                mark["y"],
                mark.get("radius", 0),
                mark.get("stroke", 0),
                *mark["bounds"],
                *mark.get("hit_rect", ()),
                *[run[key] for run in mark.get("runs", []) for key in ("x", "y")],
            )
        ):
            raise ValueError("Measured mark coordinates overflowed.")
        result = {
            **drawing,
            "atom_layouts": layouts,
            "atom_label_rects": label_rects,
            "atom_hit_rects": hit_rects,
            "atom_selection_rects": selection_rects,
            "mark_owner_rects": {
                str(atom_id): selection_atom_rect(
                    atom.x,
                    atom.y,
                    atom_pick_radius(metrics),
                    selection_rects.get(str(atom_id)),
                )
                for atom_id, atom in model.atoms.items()
            },
            "arrow_labels": positioned,
            "marks": marks,
        }
        for bracket in result["brackets"]:
            symbol = bracket["symbol"]
            glyph = self.ink[f"{symbol['pixels']}:{symbol['text']}"] if symbol else None
            if glyph:
                outline = [(symbol["x"] + x, symbol["y"] + y) for x, y in glyph]
                bracket["bounds"] = points_bounds(outline)
                # Convex ink hull: the pick outline Qt takes from the glyph path.
                bracket["outline"] = [*outline, outline[0]]
        if marks:
            result["mark_owners"] = BrowserStructureAdapter(state).mark_owner_feedback(
                result, self
            )
        return result


@dataclass(frozen=True)
class BrowserPoint:
    """Coordinate boundary for existing services that consume x()/y() points."""

    px: float
    py: float

    def x(self) -> float:
        return self.px

    def y(self) -> float:
        return self.py


@dataclass(frozen=True)
class BrowserRect:
    """Rectangle port for the original native alignment calculations."""

    x: float
    y: float
    w: float
    h: float

    def left(self) -> float:
        return self.x

    def top(self) -> float:
        return self.y

    def right(self) -> float:
        return self.x + self.w

    def bottom(self) -> float:
        return self.y + self.h

    def width(self) -> float:
        return self.w

    def height(self) -> float:
        return self.h

    def center(self) -> BrowserPoint:
        return BrowserPoint(self.x + self.w / 2, self.y + self.h / 2)

    def isValid(self) -> bool:  # noqa: N802 - graphics port
        return self.w > 0 and self.h > 0

    def united(self, other: BrowserRect) -> BrowserRect:
        if not self.w and not self.h:
            return other
        if not other.w and not other.h:
            return self
        x, y = min(self.x, other.x), min(self.y, other.y)
        return BrowserRect(
            x,
            y,
            max(self.right(), other.right()) - x,
            max(self.bottom(), other.bottom()) - y,
        )


@dataclass
class BrowserRingItem:
    """Ring graphics port: the shared fitter writes a candidate's polygon."""

    record: dict[str, Any]

    def data(self, role: int) -> Any:
        return "ring" if role == 0 else self.record["atom_ids"] if role == 2 else None

    def setPolygon(self, points: tuple[BrowserPoint, ...]) -> None:  # noqa: N802 - graphics port
        self.record["points"] = [(point.x(), point.y()) for point in points]


@dataclass(eq=False)
class BrowserSceneItem:
    """Annotation graphics port over the candidate's canonical document record."""

    record: dict[str, Any]
    bounds: BrowserRect | None = None

    def data(self, role: int) -> Any:
        return self.record["kind"] if role == 0 else None

    def sceneBoundingRect(self) -> BrowserRect:  # noqa: N802 - graphics port
        if self.bounds is None:
            raise ValueError("Alignment bounds have not been measured.")
        return self.bounds


@dataclass(eq=False)
class BrowserOrbitalItem(BrowserSceneItem):
    @override
    def data(self, role: int) -> Any:
        return "orbital" if role == 0 else None

    def orbital_state(self) -> dict[str, object]:
        return {**self.record, "kind": "orbital", "orbital_kind": self.record["kind"]}

    def apply_orbital_state(self, state: Mapping[str, object]) -> None:
        record = orbital_from_state({**self.orbital_state(), **state})
        if record.kind != self.record["kind"]:
            raise ValueError("An orbital kind cannot be replaced in place.")
        self.record.update(
            kind=record.kind,
            center=record.center,
            scale=record.scale,
            rotation=record.rotation,
        )


@dataclass(eq=False)
class BrowserMarkItem:
    """The native move controller sees a mark item; the browser stores its record."""

    record: dict[str, Any]
    center: BrowserPoint
    bounds: BrowserRect | None = None

    def sceneBoundingRect(self) -> BrowserRect:  # noqa: N802 - graphics port
        if self.bounds is None:
            raise ValueError("Alignment bounds have not been measured.")
        return self.bounds

    def data(self, role: int) -> Any:
        return "mark" if role == 0 else self.record if role == 1 else None

    def setData(self, role: int, value: dict[str, Any]) -> None:  # noqa: N802 - graphics port
        if role != 1:
            raise ValueError("Only mark metadata can be changed.")
        self.record.update(value)

    def moveBy(self, dx: float, dy: float) -> None:  # noqa: N802 - graphics port
        self.set_center(BrowserPoint(self.center.x() + dx, self.center.y() + dy))

    def set_center(self, center: BrowserPoint) -> None:
        self.center = center
        self.record.update(x=center.x(), y=center.y())


class BrowserStructureAdapter:
    """Materialize existing structure builders into a candidate document and SVG.

    The existing committer owns atom merging, bond order and ring construction.
    document_info renders the accepted candidate once, instead of creating
    QGraphicsItems during each mutation.
    """

    def __init__(
        self,
        state: dict[str, Any],
        *,
        grid: str = "none",
        mark_order: dict[int, list[int]] | None = None,
        measured_drawing: dict[str, Any] | None = None,
    ) -> None:
        if not isinstance(grid, str) or grid not in GRID_MODES:
            raise ValueError("Unknown grid mode.")
        self.document_state = state
        # Font-measured drawing of the unedited state, for glyph pick outlines.
        self.measured_drawing = measured_drawing
        self.model = deserialize_model_state(state["model"])
        self.renderer = RenderMetrics()
        self.renderer.set_bond_length(state["settings"]["bond_length_px"])
        # document_info materializes the complete SVG after the build commits.
        self.bond_renderer = SimpleNamespace(add_bond_graphics=lambda _bond_id: None)
        self.runtime_state = SimpleNamespace(
            tool_settings_state=CanvasToolSettingsState(
                grid_snap_enabled=grid != "none",
                grid_style="hex" if grid == "hex" else "square",
            ),
            mark_registry=CanvasMarkRegistry(),
            graph_state=SimpleNamespace(atom_bond_ids={}),
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
            scene_decoration_build_service=SimpleNamespace(
                mark_center=lambda item: item.center,
                set_mark_center=lambda item, center: item.set_center(center),
            ),
        )
        self.mark_items = []
        for record in state["marks"]:
            center = mark_center_coordinates(record, self.model.atoms)
            if center is None:
                raise ValueError("A mark requires a valid center.")
            item = BrowserMarkItem(record, BrowserPoint(*center))
            self.mark_items.append(item)
            if record["atom_id"] is not None:
                self.runtime_state.mark_registry.add_for_atom(record["atom_id"], item)
        if mark_order is not None:
            self.runtime_state.mark_registry.by_atom = {
                atom_id: [self.mark_items[index] for index in indices]
                for atom_id, indices in mark_order.items()
            }
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
            update_ring_fills_for_atoms=lambda ids, **_kwargs: (
                rebuild_ring_fill_polygons(
                    self.model,
                    ids,
                    (
                        BrowserRingItem(record)
                        for record in self.document_state["ring_fills"]
                    ),
                    point_factory=BrowserPoint,
                    polygon_factory=tuple,
                )
            ),
            create_ring_fill_item=lambda points, ids: RingFill(
                tuple(ids),
                self.renderer.style.ring_fill_color,
                self.renderer.style.ring_fill_alpha,
            ),
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

    def snapped_point(
        self,
        point: tuple[float, float],
        endpoints: list[tuple[float, float]],
        *,
        radius: float,
        avoid: tuple[float, float] | None = None,
        angle_step: float | None = None,
    ) -> tuple[float, float]:
        """The native drawing funnel with this document's grid settings."""
        settings = self.runtime_state.tool_settings_state
        return snapped_drawing_point(
            point,
            endpoints,
            radius=radius,
            avoid=avoid,
            angle_step=angle_step,
            grid_step=grid_step_for(self) if settings.grid_snap_enabled else 0.0,
            grid_style=settings.grid_style,
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
        self.require_sheet_position(edit["x"], edit["y"])
        x, y = float(edit["x"]), float(edit["y"])
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

    def move_arrow_handle(self, edit: dict[str, Any]) -> None:
        if set(edit) != {"kind", "id", "handle", "position", "previous", "scale"}:
            raise ValueError("Unexpected handle fields.")
        self.selection_buckets([{"target": "arrow", "id": edit["id"]}])
        source = self.document_state["arrows"][edit["id"]]
        pressed = normalized_arrow_control(arrow_from_state(source))
        handle = edit["handle"]
        if handle not in ("start", "end", "control") or (
            handle == "control" and pressed.control is None
        ):
            raise ValueError("Unknown arrow handle.")
        scale = validated_drawing_scale(edit["scale"])
        positions = (
            [edit["position"]]
            if edit["previous"] is None
            else [edit["previous"], edit["position"]]
        )
        for point in positions:
            if (
                not isinstance(point, list)
                or len(point) != 2
                or any(
                    type(v) not in (int, float, Decimal) or not math.isfinite(v)
                    for v in point
                )
            ):
                raise ValueError("A handle position needs two finite coordinates.")
        endpoints = [
            tuple(point)
            for index, arrow in enumerate(self.document_state["arrows"])
            if index != edit["id"]
            for point in (arrow["start"], arrow["end"])
        ]
        record = pressed
        for point in positions:
            moved = (float(point[0]), float(point[1]))
            if handle == "control":
                mid = clamp_curved_midpoint(
                    pressed.start,
                    pressed.end,
                    moved,
                    snap_enabled=self.runtime_state.tool_settings_state.curved_snap,
                    snap_distance=self.renderer.style.bond_length_px
                    * self.runtime_state.tool_settings_state.curved_snap_step,
                )
                record = replace(
                    record,
                    control=control_from_midpoint(pressed.start, pressed.end, mid),
                )
            else:
                moved = self.snapped_point(
                    moved, endpoints, radius=ENDPOINT_SNAP_SCREEN_PX / scale
                )
                record = arrow_with_moved_endpoint(
                    record,
                    pressed,
                    moved,
                    handle,
                    bond_length=self.renderer.style.bond_length_px,
                )
        if record != pressed:
            source.update(arrow_to_state(record))

    def set_arrow_labels(self, edit: dict[str, Any]) -> None:
        self.selection_buckets([{"target": "arrow", "id": edit["id"]}])
        labels = edit["labels"]
        if (
            not isinstance(labels, dict)
            or set(labels) - {"above", "below"}
            or any(
                not isinstance(text, str) or len(text) > MAX_ARROW_LABEL_CHARS
                for text in labels.values()
            )
        ):
            raise ValueError(
                "Arrow labels must contain at most 200 characters per field."
            )
        arrow = self.document_state["arrows"][edit["id"]]
        arrow.pop("labels", None)
        if cleaned := cleaned_arrow_labels(labels):
            arrow["labels"] = cleaned

    def apply_ring_fill(self, edit: dict[str, Any]) -> str | None:
        if set(edit) != {"kind", "selection", "color"}:
            raise ValueError("Unexpected ring fill fields.")
        color = validated_color(edit["color"])
        buckets = self.selection_buckets(edit["selection"])
        targets = [cast("BrowserRingItem", item).record for item in buckets.ring_items]
        existing = {
            frozenset(ring["atom_ids"]): ring
            for ring in self.document_state["ring_fills"]
        }
        for ids in selected_ring_cycles(
            self.model.bonds, buckets.atom_ids, buckets.bond_ids
        ):
            key = frozenset(ids)
            if key not in existing:
                self.attach_ring(RingFill(tuple(ids), None, 0.0))
                existing[key] = self.document_state["ring_fills"][-1]
            if all(ring is not existing[key] for ring in targets):
                targets.append(existing[key])
        if not targets:
            return RING_FILL_GUIDANCE
        rgb = (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))
        fill = "#" + "".join(
            f"{component:02x}" for component in pastel_rgb(rgb, RING_FILL_TINT)
        )
        for ring in targets:
            ring.update(color=fill, alpha=1.0)
        return None

    def apply_color(self, edit: dict[str, Any]) -> str | None:
        fields = {"kind", "selection", "color"}
        if set(edit) not in (fields, fields | {"x", "y", "hits", "scale"}):
            raise ValueError("Unexpected color fields.")
        color = validated_color(edit["color"])
        color = color.lower()
        selection = edit["selection"]
        self.selection_buckets(selection)
        if "x" in edit:
            target = self.pick_target(
                edit["x"], edit["y"], edit["hits"], preferred=False, scale=edit["scale"]
            )
            if target is not None:
                selection = [target]
        buckets = self.selection_buckets(selection)
        for ring_item in buckets.ring_items:
            ids = set(ring_item.data(2))
            buckets.atom_ids.update(ids)
            buckets.bond_ids.update(
                i
                for i, bond in enumerate(self.model.bonds)
                if bond is not None and {bond.a, bond.b} <= ids
            )
        for atom_id in buckets.atom_ids:
            self.model.atoms[atom_id].color = color
        for bond_id in buckets.bond_ids:
            bond = self.model.bonds[bond_id]
            assert bond is not None
            bond.color = color
        for item in buckets.arrow_items:
            cast("BrowserSceneItem", item).record["color"] = color
        for mark in buckets.mark_items:
            cast("BrowserMarkItem", mark).record["color"] = color
        rgb = (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))
        fill = "#" + "".join(
            f"{component:02x}" for component in pastel_rgb(rgb, SHAPE_FILL_TINT)
        )
        for item in buckets.other_items:
            if item.data(0) == "shape":
                cast("BrowserSceneItem", item).record.update(fill=fill, fill_alpha=1.0)
        self.publish_model()
        if buckets.ts_bracket_items:
            return COLOR_TOOL_MESSAGES["ts_bracket"]
        if (
            buckets.atom_ids
            and not (
                buckets.bond_ids
                or buckets.arrow_items
                or buckets.other_items
                or buckets.mark_items
            )
            and all(
                not atom_shows_itself(self.model.atoms[i]) for i in buckets.atom_ids
            )
        ):
            return COLOR_TOOL_MESSAGES["hidden"]
        return None

    def stack_selection(self, edit: dict[str, Any]) -> None:
        if (
            set(edit) != {"kind", "selection", "front"}
            or type(edit["front"]) is not bool
        ):
            raise ValueError("Expected selection and a boolean stacking direction.")
        buckets = self.selection_buckets(edit["selection"])
        selected = {
            id(cast("BrowserSceneItem", item).record) for item in buckets.other_items
        }
        shapes = self.document_state["shapes"]
        for index, z in stacked_depths(
            [float(shape.get("z", -10)) for shape in shapes],
            {i for i, shape in enumerate(shapes) if id(shape) in selected},
            front=edit["front"],
        ):
            shapes[index]["z"] = z

    def move_orbital_handle(self, edit: dict[str, Any]) -> None:
        if set(edit) != {"kind", "id", "handle", "position"}:
            raise ValueError("Unexpected handle fields.")
        buckets = self.selection_buckets([{"target": "orbital", "id": edit["id"]}])
        item = cast("BrowserOrbitalItem", buckets.other_items[0])
        pos = edit["position"]
        if (
            not isinstance(pos, list)
            or len(pos) != 2
            or any(
                type(value) not in (int, float, Decimal) or not math.isfinite(value)
                for value in pos
            )
        ):
            raise ValueError("A handle position needs two finite coordinates.")
        center = BrowserPoint(*item.record["center"])
        position = BrowserPoint(*(float(value) for value in pos))
        if edit["handle"] == "scale":
            item.apply_orbital_state(
                {
                    "scale": orbital_scale_factor(
                        center, position, self.renderer.style.bond_length_px * 0.8
                    )
                }
            )
        elif edit["handle"] == "rotate":
            settings = self.runtime_state.tool_settings_state
            item.apply_orbital_state(
                {
                    "rotation": orbital_rotation_angle(
                        center,
                        position,
                        snap_enabled=settings.orbital_snap_enabled,
                        snap_step=settings.orbital_snap_step,
                    )
                }
            )
        else:
            raise ValueError("Unknown orbital handle.")

    def move_shape_handle(self, edit: dict[str, Any]) -> None:
        if set(edit) != {"kind", "id", "handle", "position"}:
            raise ValueError("Unexpected handle fields.")
        self.selection_buckets([{"target": "shape", "id": edit["id"]}])
        source = self.document_state["shapes"][edit["id"]]
        shape = normalized_shape(shape_from_state(source))
        bounds = (shape.left, shape.top, shape.right, shape.bottom)
        if not isinstance(edit["handle"], str) or edit["handle"] not in dict(
            shape_handle_positions(bounds)
        ):
            raise ValueError("Unknown shape handle.")
        pos = edit["position"]
        if (
            not isinstance(pos, list)
            or len(pos) != 2
            or any(
                type(v) not in (int, float, Decimal) or not math.isfinite(v)
                for v in pos
            )
        ):
            raise ValueError("A handle position needs two finite coordinates.")
        left, top, right, bottom = resized_shape_bounds(
            bounds, edit["handle"], (float(pos[0]), float(pos[1]))
        )
        source.update(
            shape_to_state(
                replace(shape, left=left, top=top, right=right, bottom=bottom)
            )
        )

    def insert_orbital(self, edit: dict[str, Any]) -> None:
        if set(edit) != {"kind", "x", "y", "orbital_kind"}:
            raise ValueError("Unexpected orbital fields.")
        kind = edit["orbital_kind"]
        if not isinstance(kind, str) or kind not in ORBITAL_TYPE_BY_LABEL.values():
            raise ValueError("Unknown orbital kind.")
        self.require_sheet_position(edit["x"], edit["y"])
        x, y = float(edit["x"]), float(edit["y"])
        self.document_state["orbitals"].append(asdict(Orbital(kind, (x, y))))

    def insert_bracket(self, edit: dict[str, Any]) -> None:
        if set(edit) != {"kind", "start", "end", "style"}:
            raise ValueError("Unexpected bracket fields.")
        for point in (edit["start"], edit["end"]):
            if (
                not isinstance(point, list)
                or len(point) != 2
                or any(
                    type(value) not in (int, float, Decimal) or not math.isfinite(value)
                    for value in point
                )
            ):
                raise ValueError("Bracket coordinates must be finite points.")
            self.require_sheet_position(*point)
        kind = edit["style"]
        if not isinstance(kind, str) or kind not in dict(BRACKET_MENU_SPECS).values():
            raise ValueError("Unknown bracket kind.")
        x, y, width, height = bracket_rect_from_points(
            (float(edit["start"][0]), float(edit["start"][1])),
            (float(edit["end"][0]), float(edit["end"][1])),
            self.renderer.style.bond_length_px,
        )
        self.document_state["ts_brackets"].append(
            ts_bracket_to_state(
                TSBracket(
                    left=x,
                    top=y,
                    right=x + width,
                    bottom=y + height,
                    bracket_kind=kind,
                )
            )
        )

    def insert_shape(self, edit: dict[str, Any]) -> None:
        start, end = edit["start"], edit["end"]
        if any(
            not isinstance(point, list) or len(point) != 2 for point in (start, end)
        ):
            raise ValueError("Shape coordinates must be finite points.")
        self.require_sheet_position(*start)
        self.require_sheet_position(*end)
        if (
            not isinstance(edit["style"], str)
            or not isinstance(edit["stroke"], str)
            or edit["style"] not in dict(SHAPE_KIND_SPECS)
            or edit["stroke"] not in dict(SHAPE_STROKE_SPECS)
        ):
            raise ValueError("Unknown shape kind or stroke.")
        x, y, width, height = shape_rect_from_points(
            (float(start[0]), float(start[1])),
            (float(end[0]), float(end[1])),
            self.renderer.style.bond_length_px,
        )
        self.document_state["shapes"].append(
            shape_to_state(
                Shape(
                    left=x,
                    top=y,
                    right=x + width,
                    bottom=y + height,
                    shape_kind=edit["style"],
                    stroke_style=edit["stroke"],
                )
            )
        )

    def set_drawing_settings(self, edit: dict[str, Any]) -> None:
        settings = self.document_state["settings"]
        if edit["kind"] == "orbital_phase":
            if set(edit) != {"kind", "enabled"} or type(edit["enabled"]) is not bool:
                raise ValueError("Expected an orbital phase flag.")
            settings["orbital_phase_enabled"] = edit["enabled"]
            return
        if edit["kind"] == "sheet_setup":
            if set(edit) != {"kind", "size", "orientation", "custom_size_mm"}:
                raise ValueError("Unexpected canvas size fields.")
            if (
                not isinstance(edit["size"], str)
                or not isinstance(edit["orientation"], str)
                or edit["size"] not in supported_sheet_sizes()
                or edit["orientation"] not in dict(SHEET_ORIENTATION_OPTIONS)
            ):
                raise ValueError("Unknown canvas size or orientation.")
            size, orientation, custom = normalize_sheet_setup(
                edit["size"], edit["orientation"], edit["custom_size_mm"]
            )
            settings.update(sheet_size=size, sheet_orientation=orientation)
            settings.pop("sheet_custom_size_mm", None)
            if custom is not None:
                settings["sheet_custom_size_mm"] = list(custom)
            return
        if edit["kind"] == "bond_length":
            if set(edit) != {"kind", "value"}:
                raise ValueError("Unexpected bond length fields.")
            length = float(edit["value"])
            scale = length / float(settings["bond_length_px"])
            if scale == 1:
                return
            before_positions = {
                atom_id: (atom.x, atom.y) for atom_id, atom in self.model.atoms.items()
            }
            if before_positions:
                center_x, center_y = self.model.center()
                self.model.scale_about(center_x, center_y, scale)
                for ring in self.document_state["ring_fills"]:
                    ring["points"] = [
                        (
                            center_x + (x - center_x) * scale,
                            center_y + (y - center_y) * scale,
                        )
                        for x, y in ring["points"]
                    ]
                for atom_id, marks in self.runtime_state.mark_registry.items():
                    atom = self.model.atoms[atom_id]
                    for mark in marks:
                        dx, dy = scaled_mark_offset(
                            mark.record, before_positions[atom_id], scale
                        )
                        mark.record.update(dx=dx, dy=dy)
                        mark.set_center(BrowserPoint(atom.x + dx, atom.y + dy))
            settings["bond_length_px"] = length
            self.renderer.set_bond_length(length)
            self.publish_model()
            return
        width, head = settings["arrow_line_width"], settings["arrow_head_scale"]
        if set(edit) == {"kind", "preset"}:
            if edit["preset"] not in ARROW_PRESET_SPECS:
                raise ValueError("Unknown arrow preset.")
            width, head = arrow_preset_from_label(edit["preset"])
        elif set(edit) == {"kind", "setting", "value"}:
            setting, value = edit["setting"], edit["value"]
            if not isinstance(setting, str) or setting not in ARROW_SLIDER_RANGES:
                raise ValueError("Unknown arrow slider.")
            minimum, maximum, factor = ARROW_SLIDER_RANGES[setting]
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError("Invalid arrow slider value.")
            if setting == "arrow_line_width":
                width = value / factor
            else:
                head = value / factor
        else:
            raise ValueError("Unexpected arrow style fields.")
        settings.update(normalized_arrow_style(width, head))

    def insert_arrow(self, edit: dict[str, Any], *, preview: bool = False) -> None:
        start, end = edit["start"], edit["end"]
        if any(
            not isinstance(point, list) or len(point) != 2 for point in (start, end)
        ):
            raise ValueError("A point needs two coordinates.")
        line_tool = edit["kind"] == "line"
        kind = edit["style"]
        allowed = (
            {value for value, _ in LINE_KIND_SPECS}
            if line_tool
            else {value for _, value in ARROW_MENU_SPECS}
        )
        if not isinstance(kind, str) or kind not in allowed:
            raise ValueError("Unsupported arrow or line style.")
        if line_tool:
            self.selection_buckets(edit["hits"])
        if type(edit["dragged"]) is not bool or type(edit["shift"]) is not bool:
            raise ValueError("Expected arrow gesture flags.")
        scale = validated_drawing_scale(edit["scale"])
        radius = ENDPOINT_SNAP_SCREEN_PX / scale
        self.require_sheet_position(*start)
        self.require_sheet_position(*end)
        if not edit["dragged"] and not line_tool:
            return
        endpoints = [
            tuple(point)
            for arrow in self.document_state["arrows"]
            for point in (arrow["start"], arrow["end"])
        ]
        first = self.snapped_point(
            (float(start[0]), float(start[1])), endpoints, radius=radius
        )
        last = (
            self.snapped_point(
                (float(end[0]), float(end[1])),
                endpoints,
                radius=radius,
                avoid=first,
                angle_step=LINE_ANGLE_STEP_DEGREES
                if line_tool and edit["shift"]
                else None,
            )
            if edit["dragged"]
            else first
        )
        if first == last:
            if not line_tool or preview:
                return
            click_end = line_click_endpoint(
                first,
                bond_length=self.renderer.style.bond_length_px,
                occupied=self.center_inside_ring(BrowserPoint(*first))
                or self.pick_target(*first, edit["hits"], preferred=False, scale=scale)
                is not None,
            )
            if click_end is None:
                return
            last = click_end
        if edit["shift"] and kind in VALID_ARC_KINDS:
            kind = mirrored_arc_kind(kind)
        record = new_arrow_record(first, last, kind)
        self.document_state["arrows"].append(arrow_to_state(record))

    def insert_bond(self, start: list[float], end: list[float], style: str) -> None:
        if any(
            not isinstance(point, list) or len(point) != 2 for point in (start, end)
        ):
            raise ValueError("A point needs two coordinates.")
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
        self,
        x: float,
        y: float,
        key: str,
        direct_atom_id: int | None = None,
        *,
        font: BrowserFontMeasurements | None = None,
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
            mark_scene_service=cast(
                "Any",
                SimpleNamespace(
                    change_charge_for_atom=lambda atom_id, delta: (
                        self.change_charge_for_atom(atom_id, delta, font)
                    )
                ),
            ),
        )
        handled = (
            atom_id is not None and shortcuts.handle_atom_text(key, atom_id)
        ) or (bond_id is not None and shortcuts.handle_bond_text(key, bond_id))
        if handled:
            if self.candidate_accepted:
                self.publish_model()
            return None
        # Without a hovered target the key reaches the native generic hotkeys.
        return TOOL_HOTKEYS.get(key) or SHIFT_TOOL_HOTKEYS.get(key)

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
            bond_pick_candidates(
                self.model, x, y, length * bond_gate_ratio, max(8.0, length)
            ),
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
        self, x: float, y: float, hits: object, *, preferred: bool, scale: object
    ) -> dict[str, Any] | None:
        """Adapt native graphics hits, then use the existing structure picker.

        Select uses preferred structure distance; Shift/eraser use the raw
        graphics target and the native near-bond fallback instead.
        """
        if any(
            type(v) not in (int, float, Decimal) or not math.isfinite(v) for v in (x, y)
        ):
            raise ValueError("Pick coordinates must be finite numbers.")
        x, y = float(x), float(y)
        scale = validated_drawing_scale(scale)
        self.selection_buckets(hits)
        direct: dict[str, int] = {}
        for hit in cast("list[dict[str, Any]]", hits):
            direct.setdefault(hit["target"], hit["id"])
        if "mark" in direct:
            mark = self.mark_items[direct["mark"]]
            atom = self.model.atoms[direct["atom"]] if "atom" in direct else None
            if mark_precedes_atom(
                (x, y),
                (mark.center.x(), mark.center.y()),
                (atom.x, atom.y) if atom is not None else None,
            ):
                return {"target": "mark", "id": direct["mark"]}
        if "atom" in direct:
            return {"target": "atom", "id": direct["atom"]}
        bond_id = direct.get("bond")
        if bond_id is None:
            bond_id = nearest_bond_id(
                self.model,
                bond_pick_candidates(
                    self.model,
                    x,
                    y,
                    self.renderer.style.bond_length_px
                    * STRUCTURE_BOND_PICK_RADIUS_RATIO,
                    max(8.0, self.renderer.style.bond_length_px),
                ),
                BrowserPoint(x, y),
                self.renderer.style.bond_length_px * STRUCTURE_BOND_PICK_RADIUS_RATIO,
                point_factory=BrowserPoint,
            )
        if bond_id is None and "ring" not in direct:
            for index in reversed(range(len(self.document_state["ring_fills"]))):
                if polygon_contains_point(
                    (x, y),
                    self.document_state["ring_fills"][index]["points"],
                ):
                    direct["ring"] = index
                    break

        def preferred_structure() -> dict[str, Any] | None:
            atom_id, preferred_bond = self.structure_target(
                x, y, bond_gate_ratio=STRUCTURE_BOND_PICK_RADIUS_RATIO
            )
            if atom_id is not None:
                return {"target": "atom", "id": atom_id}
            if preferred_bond is not None:
                return {"target": "bond", "id": preferred_bond}
            return None

        if bond_id is None and "ring" in direct:
            if preferred:
                if (structure := preferred_structure()) is not None:
                    return structure
                atom_id = nearest_ring_atom_id(
                    [
                        (
                            i,
                            math.hypot(
                                self.model.atoms[i].x - x, self.model.atoms[i].y - y
                            ),
                        )
                        for i in self.document_state["ring_fills"][direct["ring"]][
                            "atom_ids"
                        ]
                    ],
                    max_distance=self.renderer.style.bond_length_px * 0.4,
                )
                if atom_id is not None:
                    return {"target": "atom", "id": atom_id}
            return {"target": "ring", "id": direct["ring"]}
        # A foreground shape stops the native near-arrow search, while native
        # atom/bond precedence above still applies through decorative panels.
        first_other = next(
            (
                hit
                for hit in cast("list[dict[str, Any]]", hits)
                if hit["target"] in {"shape", "arrow", "orbital", "ts_bracket"}
            ),
            None,
        )
        if (
            bond_id is None
            and first_other is not None
            and (
                first_other["target"] in {"orbital", "ts_bracket"}
                or (
                    first_other["target"] == "shape"
                    and self.document_state["shapes"][first_other["id"]].get("z", -10)
                    >= 0
                )
            )
        ):
            return first_other
        # Native Select takes a directly hit arrow before structure fallback.
        if bond_id is None and "arrow" in direct:
            return {"target": "arrow", "id": direct["arrow"]}
        if bond_id is None and (near := self.nearest_line_target(x, y, scale)):
            return near
        if preferred and (structure := preferred_structure()) is not None:
            return structure
        if bond_id is not None:
            return {"target": "bond", "id": bond_id}
        return {"target": "shape", "id": direct["shape"]} if "shape" in direct else None

    def nearest_line_target(
        self, x: float, y: float, scale: float
    ) -> dict[str, Any] | None:
        """Native Select's near-arrow search, which also takes bracket strokes."""
        nearest = None
        best_distance = ARROW_PICK_SCREEN_PX
        point = BrowserPoint(x * scale, y * scale)
        # Brackets populate after arrows, so they come first at equal depth.
        brackets = self.document_state["ts_brackets"]
        length = self.renderer.style.bond_length_px
        width = bracket_stroke_width(self.renderer.style.bond_line_width)
        measured = (self.measured_drawing or {}).get("brackets")
        for bracket_id in reversed(range(len(brackets))):
            source = brackets[bracket_id]
            path = bracket_path_commands(
                bracket_rect(source), source["bracket_kind"], length
            )
            # Qt measures to its flattened filled outline, not the centre line.
            rings = bracket_outline(path, width) if path else []
            if not path and measured and measured[bracket_id].get("outline"):
                rings = [measured[bracket_id]["outline"]]
            distance = min(
                (
                    distance_point_to_segment(
                        point,
                        BrowserPoint(a[0] * scale, a[1] * scale),
                        BrowserPoint(b[0] * scale, b[1] * scale),
                    )
                    for ring in rings
                    for a, b in pairwise(ring)
                ),
                default=math.inf,
            )
            if distance < best_distance:
                nearest, best_distance = ("ts_bracket", bracket_id), distance
        paths = arrow_geometry(self.document_state, self.renderer)
        segment_count = 0
        # Native scene order puts the last added arrow first on equal distance.
        for arrow_id in reversed(range(len(paths))):
            distance = math.inf
            for a, b in arrow_pick_segments(paths[arrow_id]["path"], scale):
                segment_count += 1
                if segment_count > 500_000:
                    raise ValueError(
                        "Arrow picking exceeds the browser path point limit."
                    )
                distance = min(distance, distance_point_to_segment(point, a, b))
            if distance < best_distance:
                nearest, best_distance = ("arrow", arrow_id), distance
        if nearest is not None:
            return {"target": nearest[0], "id": nearest[1]}
        return None

    def selection_components(
        self, items: object, drawing: dict[str, Any]
    ) -> list[list[dict[str, Any]]]:
        buckets = self.selection_buckets(items)
        atom_ids = set(buckets.atom_ids)
        for ring in buckets.ring_items:
            atom_ids.update(cast("BrowserRingItem", ring).record["atom_ids"])
        neighbors, atom_bonds = build_bond_adjacency_index(
            self.model.atoms, self.model.bonds
        )
        atom_ids, bond_ids = selection_structure_ids(
            self.model, atom_ids, buckets.bond_ids, atom_bonds
        )
        components: list[list[dict[str, Any]]] = []
        for component in connected_components_for_nodes(atom_ids, neighbors):
            bonds = {
                i
                for i in bond_ids
                if (bond := self.model.bond_for_id(i)) is not None
                and bond.a in component
                and bond.b in component
            }
            bonded = {
                a
                for i in bonds
                if (bond := self.model.bond_for_id(i)) is not None
                for a in (bond.a, bond.b)
            }
            parts = []
            for atom_id in sorted(component):
                atom = self.model.atoms[atom_id]
                if atom_id in bonded and not atom_shows_itself(atom):
                    continue
                parts.append(
                    {
                        "rect": selection_atom_rect(
                            atom.x,
                            atom.y,
                            atom_pick_radius(self.renderer),
                            drawing.get("atom_selection_rects", {}).get(str(atom_id)),
                        )
                    }
                )
            for bond_id in sorted(bonds):
                parts.extend(drawing["selection_bonds"].get(str(bond_id), []))
            if parts:
                components.append(parts)
        radius = atom_pick_radius(self.renderer)
        for mark in buckets.mark_items:
            center = cast("BrowserMarkItem", mark).center
            components.append(
                [
                    {
                        "rect": (
                            center.x() - radius,
                            center.y() - radius,
                            radius * 2,
                            radius * 2,
                        )
                    }
                ]
            )
        orbital_ids = {
            id(cast("BrowserOrbitalItem", item).record)
            for item in buckets.other_items
            if isinstance(item, BrowserOrbitalItem)
        }
        for record, geometry in zip(
            self.document_state["orbitals"], drawing["orbitals"], strict=True
        ):
            if id(record) in orbital_ids:
                components.append(
                    [
                        {
                            "polygon": geometry["polygon"],
                            "width": self.renderer.style.bond_length_px
                            * SELECTION_OBJECT_PADDING_RATIO
                            * 2,
                        }
                    ]
                )
        # Native object outline: the filled bracket shape grown by the padding.
        pad = self.renderer.style.bond_length_px * SELECTION_OBJECT_PADDING_RATIO
        bracket_ids = {
            id(cast("BrowserSceneItem", item).record)
            for item in buckets.ts_bracket_items
        }
        for record, geometry in zip(
            self.document_state["ts_brackets"], drawing["brackets"], strict=True
        ):
            if id(record) not in bracket_ids:
                continue
            symbol = geometry["symbol"]
            components.append(
                [
                    {
                        "text": symbol,
                        "width": pad * 2,
                        "bounds": geometry["bounds"],
                    }
                    if symbol
                    else {
                        "path": geometry["path"],
                        "width": geometry["width"] + pad * 2,
                    }
                ]
            )
        return components

    def selected_atom_ids(self, buckets: DeleteSelectionBuckets) -> set[int]:
        """Atoms a selection moves or turns: atoms, bond ends and ring members."""
        atom_ids = selected_atom_ids_with_bond_endpoints(
            buckets.atom_ids, buckets.bond_ids, bonds=self.model.bonds
        )
        for ring in buckets.ring_items:
            atom_ids.update(ring.data(2))
        return atom_ids

    def selection_frame(
        self, items: object, drawing: dict[str, Any]
    ) -> dict[str, Any] | None:
        buckets = self.selection_buckets(items)
        atom_ids = self.selected_atom_ids(buckets)
        orbital_ids = {
            id(cast("BrowserOrbitalItem", item).record)
            for item in buckets.other_items
            if isinstance(item, BrowserOrbitalItem)
        }
        if not selection_frame_applies(
            len(atom_ids), len(buckets.arrow_items) + len(orbital_ids)
        ):
            return None
        rects = []
        for atom_id in sorted(atom_ids):
            atom = self.model.atoms[atom_id]
            label_rect = drawing.get("atom_selection_rects", {}).get(str(atom_id))
            rects.append(
                selection_atom_rect(
                    atom.x, atom.y, atom_pick_radius(self.renderer), label_rect
                )
            )
            if label_rect is not None:
                rects.append(label_rect)
        selected_arrows = {
            id(item.record)
            for item in cast("list[BrowserSceneItem]", buckets.arrow_items)
        }
        for index, record in enumerate(self.document_state["arrows"]):
            if id(record) not in selected_arrows:
                continue
            rects.append(arrow_frame_bounds(drawing["arrows"][index]))
            for label in drawing.get("arrow_labels", []):
                if label["id"] == index:
                    rects.append(
                        (label["x"], label["y"], label["width"], label["height"])
                    )
        rects.extend(
            geometry["bounds"]
            for record, geometry in zip(
                self.document_state["orbitals"], drawing["orbitals"], strict=True
            )
            if id(record) in orbital_ids
        )
        return {
            "rects": rects,
            "padding": self.renderer.style.bond_length_px
            * SELECTION_OBJECT_PADDING_RATIO,
        }

    def selection_buckets(self, items: object) -> DeleteSelectionBuckets:
        if not isinstance(items, list) or len(items) > 5000 + len(
            self.document_state["arrows"]
        ) + len(self.document_state["shapes"]) + len(
            self.document_state["ring_fills"]
        ) + len(self.mark_items) + len(self.document_state["orbitals"]) + len(
            self.document_state["ts_brackets"]
        ):
            raise ValueError("Expected a bounded list of selected items.")
        buckets = DeleteSelectionBuckets()
        annotation_ids = set()
        for item in items:
            if not isinstance(item, dict) or set(item) != {"target", "id"}:
                raise ValueError("Expected target and id for each selected item.")
            kind, item_id = item["target"], item["id"]
            if (
                kind
                not in {
                    "atom",
                    "bond",
                    "arrow",
                    "shape",
                    "ring",
                    "mark",
                    "orbital",
                    "ts_bracket",
                }
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
                records = self.document_state[
                    {
                        "arrow": "arrows",
                        "shape": "shapes",
                        "ring": "ring_fills",
                        "mark": "marks",
                        "orbital": "orbitals",
                        "ts_bracket": "ts_brackets",
                    }[kind]
                ]
                if item_id >= len(records):
                    raise ValueError(f"The {kind} no longer exists.")
                if (kind, item_id) not in annotation_ids:
                    target = {
                        "arrow": buckets.arrow_items,
                        "shape": buckets.other_items,
                        "ring": buckets.ring_items,
                        "mark": buckets.mark_items,
                        "orbital": buckets.other_items,
                        "ts_bracket": buckets.ts_bracket_items,
                    }[kind]
                    wrapper = (
                        BrowserRingItem
                        if kind == "ring"
                        else BrowserOrbitalItem
                        if kind == "orbital"
                        else BrowserSceneItem
                    )
                    cast("list[Any]", target).append(
                        self.mark_items[item_id]
                        if kind == "mark"
                        else wrapper(records[item_id])
                    )
                    annotation_ids.add((kind, item_id))
        return buckets

    def transform_center(
        self,
        atom_ids: set[int],
        buckets: DeleteSelectionBuckets,
        drawing: dict[str, Any] | None,
        *,
        include_dependent_marks: bool,
    ) -> tuple[float, float] | None:
        arrows = cast("list[BrowserSceneItem]", buckets.arrow_items)
        shapes = cast("list[BrowserSceneItem]", buckets.other_items)
        points = [(self.model.atoms[i].x, self.model.atoms[i].y) for i in atom_ids]
        for item in arrows:
            points.extend(
                item.record[key]
                for key in ("start", "end", "control")
                if item.record.get(key) is not None
            )
        selected_shapes = {id(item.record) for item in shapes}
        selected_orbitals = [
            item for item in shapes if isinstance(item, BrowserOrbitalItem)
        ]
        if selected_orbitals:
            orbital_drawing = (
                drawing_geometry(self.document_state)["orbitals"]
                if drawing is None or drawing.get("needs_measurements")
                else drawing["orbitals"]
            )
            for source, geometry in zip(
                self.document_state["orbitals"], orbital_drawing, strict=True
            ):
                if id(source) in selected_shapes:
                    left, top, width, height = geometry["bounds"]
                    points.extend(((left, top), (left + width, top + height)))
        if buckets.ts_bracket_items:
            bracket_ids = {
                id(cast("BrowserSceneItem", item).record)
                for item in buckets.ts_bracket_items
            }
            # Stroke bounds need no font; unmeasured daggers fail closed below.
            bracket_drawing = (
                drawing_geometry(self.document_state)["brackets"]
                if drawing is None or drawing.get("needs_measurements")
                else drawing["brackets"]
            )
            for source, bracket in zip(
                self.document_state["ts_brackets"], bracket_drawing, strict=True
            ):
                if id(source) not in bracket_ids:
                    continue
                if bracket["bounds"] is None:
                    raise ValueError(
                        "Dagger transforms need completed font measurements."
                    )
                left, top, width, height = bracket["bounds"]
                points.extend(((left, top), (left + width, top + height)))
        for source, shape in zip(
            self.document_state["shapes"],
            shape_geometry(self.document_state, self.renderer),
            strict=True,
        ):
            if id(source) not in selected_shapes:
                continue
            if shape["bounds"] is None:
                continue
            left, top, width, height = shape["bounds"]
            if width > 0 and height > 0:
                points.extend([(left, top), (left + width, top + height)])
        pivot_marks = (
            buckets.mark_items
            if include_dependent_marks
            else independent_selection_items(buckets.mark_items, atom_ids)
        )
        if pivot_marks:
            if drawing is None or drawing.get("needs_measurements"):
                raise ValueError("Mark transforms need completed font measurements.")
            bounds_by_record = {
                id(record): geometry["bounds"]
                for record, geometry in zip(
                    self.document_state["marks"], drawing["marks"], strict=True
                )
            }
            for mark_item in pivot_marks:
                left, top, width, height = bounds_by_record[
                    id(cast("BrowserMarkItem", mark_item).record)
                ]
                if width > 0 and height > 0:
                    points.extend(((left, top), (left + width, top + height)))
        return selection_transform_center(points)

    def transform_selection(
        self, edit: dict[str, Any], drawing: dict[str, Any] | None = None
    ) -> None:
        if edit["kind"] in {"align", "distribute"}:
            if set(edit) != {"kind", "selection", "mode"} or drawing is None:
                raise ValueError("Invalid alignment fields.")
            self.arrange_selection(
                edit["selection"],
                edit["mode"],
                distribute=edit["kind"] == "distribute",
                drawing=drawing,
            )
            return
        angle = None
        horizontal = None
        if edit["kind"] == "flip":
            if (
                set(edit) != {"kind", "selection", "horizontal"}
                or type(edit["horizontal"]) is not bool
            ):
                raise ValueError("Invalid flip fields.")
            horizontal = edit["horizontal"]
        elif set(edit) == {"kind", "selection", "value"}:
            angle = float(edit["value"])
            if not ROTATE_ANGLE_RANGE[0] <= angle <= ROTATE_ANGLE_RANGE[1]:
                raise ValueError("Rotation angle must be between -180 and 180 degrees.")
        elif set(edit) == {"kind", "selection", "start", "end", "shift"}:
            if type(edit["shift"]) is not bool:
                raise ValueError("Rotation snap must be a boolean.")
            for key in ("start", "end"):
                point = edit[key]
                if (
                    not isinstance(point, list)
                    or len(point) != 2
                    or any(
                        type(value) not in (int, float, Decimal)
                        or not math.isfinite(value)
                        for value in point
                    )
                ):
                    raise ValueError(
                        "Rotation pointer coordinates must be finite points."
                    )
        else:
            raise ValueError("Invalid rotation fields.")
        buckets = self.selection_buckets(edit["selection"])
        arrows = cast("list[BrowserSceneItem]", buckets.arrow_items)
        shapes = cast("list[BrowserSceneItem]", buckets.other_items)
        if horizontal is not None:
            for item in arrows:
                if (
                    item.record["kind"] in VALID_EQUILIBRIUM_KINDS
                    and item.record["start"] == item.record["end"]
                ):
                    raise ValueError(
                        "Cannot flip a zero-length equilibrium arrow: its direction is undefined. Move an endpoint before flipping this selection."
                    )
        if angle == 0:
            return
        atom_ids = self.selected_atom_ids(buckets)
        center = self.transform_center(
            atom_ids, buckets, drawing, include_dependent_marks=horizontal is not None
        )
        if center is None:
            return
        if angle is None and horizontal is None:
            angle = rotation_drag_angle(
                BrowserPoint(*center),
                BrowserPoint(*(float(value) for value in edit["start"])),
                BrowserPoint(*(float(value) for value in edit["end"])),
                snap_step=ROTATION_SNAP_STEP_DEGREES if edit["shift"] else None,
            )
            if angle == 0:
                return
        positions = (
            {
                i: reflected_point(
                    BrowserPoint(self.model.atoms[i].x, self.model.atoms[i].y),
                    BrowserPoint(*center),
                    horizontal,
                )
                for i in atom_ids
            }
            if horizontal is not None
            else rotated_atom_positions(
                atom_ids,
                atoms=self.model.atoms,
                center=BrowserPoint(*center),
                angle_radians=math.radians(cast("float", angle)),
            )
        )
        selected_mark_ids = {id(item) for item in buckets.mark_items}
        mark_updates = []
        for transformed_mark in self.mark_items:
            if (
                transformed_mark.record["atom_id"] not in atom_ids
                and id(transformed_mark) not in selected_mark_ids
            ):
                continue
            position = (
                reflected_point(
                    transformed_mark.center, BrowserPoint(*center), horizontal
                )
                if horizontal is not None
                else rotated_point_coordinates(
                    transformed_mark.center,
                    BrowserPoint(*center),
                    math.radians(cast("float", angle)),
                )
            )
            mark_updates.append(
                (
                    transformed_mark,
                    mark_state_at_position(
                        transformed_mark.record,
                        position,
                        transformed_atom_positions=positions,
                        atoms=self.model.atoms,
                    ),
                )
            )
        controller = CanvasMoveController(
            cast("Any", self),
            point_factory=BrowserPoint,
            hit_testing_service=cast(
                "Any", SimpleNamespace(mark_spatial_index_dirty=lambda: None)
            ),
        )
        controller.set_atom_positions(positions, update_selection=False)
        for mark_item, state in mark_updates:
            mark_item.record.update(state)
            mark_item.set_center(BrowserPoint(state["x"], state["y"]))

        def transformed(record: Any) -> Any:
            if horizontal is not None:
                return flip_annotation(record, center=center, horizontal=horizontal)
            return rotate_annotation(
                record, center=center, angle_degrees=cast("float", angle)
            )

        for item in arrows:
            state = arrow_to_state(transformed(arrow_from_state(item.record)))
            # False is omitted by the native serializer; remove the prior flag.
            item.record.pop("mirrored", None)
            item.record.update(state)
        for item in shapes:
            if isinstance(item, BrowserOrbitalItem):
                item.apply_orbital_state(
                    orbital_to_state(
                        transformed(orbital_from_state(item.orbital_state()))
                    )
                )
            else:
                item.record.update(
                    shape_to_state(transformed(shape_from_state(item.record)))
                )
        for bracket in buckets.ts_bracket_items:
            source = cast("BrowserSceneItem", bracket).record
            source.update(
                ts_bracket_to_state(transformed(ts_bracket_from_state(source)))
            )
        self.publish_model()

    def arrange_selection(
        self, items: object, mode: str, *, distribute: bool, drawing: dict[str, Any]
    ) -> None:
        buckets = self.selection_buckets(items)
        if drawing.get("needs_measurements") or (
            drawing.get("atom_labels") and not drawing.get("atom_selection_rects")
        ):
            raise ValueError("Alignment needs completed font measurements.")
        selected_atoms = self.selected_atom_ids(buckets)
        neighbors, _ = build_bond_adjacency_index(self.model.atoms, self.model.bonds)
        structures = [
            component
            for component in connected_components_for_nodes(
                set(self.model.atoms), neighbors
            )
            if component & selected_atoms
        ]
        scene_items = independent_selection_items(
            [
                *buckets.arrow_items,
                *buckets.other_items,
                *buckets.mark_items,
                *buckets.ts_bracket_items,
            ],
            selected_atoms,
        )
        keys = {}
        for item_kind, records in (
            ("arrow", self.document_state["arrows"]),
            ("shape", self.document_state["shapes"]),
            ("mark", self.document_state["marks"]),
            ("orbital", self.document_state["orbitals"]),
            ("ts_bracket", self.document_state["ts_brackets"]),
        ):
            for index, record in enumerate(records):
                keys[id(record)] = {"target": item_kind, "id": index}
        for item in scene_items:
            key = keys[id(item.record)]
            if key["target"] == "arrow":
                item.bounds = BrowserRect(
                    *arrow_frame_bounds(drawing["arrows"][key["id"]])
                )
            elif key["target"] == "mark":
                item.bounds = BrowserRect(*drawing["marks"][key["id"]]["bounds"])
            elif key["target"] == "orbital":
                item.bounds = BrowserRect(*drawing["orbitals"][key["id"]]["bounds"])
            elif key["target"] == "ts_bracket":
                bounds = drawing["brackets"][key["id"]]["bounds"]
                item.bounds = BrowserRect(*(bounds or (0, 0, 0, 0)))
            else:
                bounds = drawing["shapes"][key["id"]]["bounds"]
                item.bounds = BrowserRect(*(bounds or (0, 0, 0, 0)))

        def object_rect(atom_ids: set[int], annotations: list[Any]) -> Any:
            rect = None
            radius = atom_pick_radius(self.renderer)
            for atom_id in sorted(atom_ids):
                atom = self.model.atoms[atom_id]
                bounds = drawing.get("atom_selection_rects", {}).get(
                    str(atom_id),
                    (atom.x - radius, atom.y - radius, radius * 2, radius * 2),
                )
                atom_rect = BrowserRect(*bounds)
                rect = atom_rect if rect is None else rect.united(atom_rect)
            for item in annotations:
                item_rect = item.sceneBoundingRect()
                rect = item_rect if rect is None else rect.united(item_rect)
            return rect

        objects = alignment_objects(
            structures, scene_items, groups=(), object_rect=object_rect
        )
        rectangles = [target.rect for target in objects]
        deltas = (
            distribute_deltas(rectangles, mode)
            if distribute
            else align_deltas(rectangles, mode)
        )
        for target, (dx, dy) in zip(objects, deltas, strict=True):
            if abs(dx) < 1e-9 and abs(dy) < 1e-9:
                continue
            selection = [{"target": "atom", "id": i} for i in target.atom_ids]
            selection.extend(
                keys[id(cast("BrowserSceneItem | BrowserMarkItem", item).record)]
                for item in target.items
            )
            self.move_selection(selection, dx, dy)

    def rebind_mark(self, mark_id: int, atom_id: int) -> bool:
        buckets = self.selection_buckets([{"target": "mark", "id": mark_id}])
        item = cast("BrowserMarkItem", buckets.mark_items[0])
        plan = plan_mark_rebind(
            self.model, item, atom_id, self.runtime_state.mark_registry.by_atom
        )
        if plan is None:
            return False
        atom = self.model.atoms[atom_id]
        item.record.update(
            atom_id=atom_id,
            dx=item.center.x() - atom.x,
            dy=item.center.y() - atom.y,
        )
        for owner, marks in plan.after_marks.items():
            self.runtime_state.mark_registry.by_atom[owner] = list(marks)
            self.model.set_atom_annotation(owner, plan.after_annotations.get(owner))
        for owner in unmarked_isolated_carbon_ids(
            {plan.old_id} if plan.old_id is not None else set(),
            atoms=self.model.atoms,
            bonds=self.model.bonds,
            has_visible_label=lambda owner: atom_shows_itself(self.model.atoms[owner]),
            has_marks=lambda owner: bool(
                self.runtime_state.mark_registry.get_for_atom(owner)
            ),
        ):
            self.model.atoms[owner].explicit_label = True
        self.publish_model()
        return True

    def mark_target_distance_for_atom(
        self,
        atom_id: int,
        direction_x: float,
        direction_y: float,
        kind: str,
        *,
        drawing: dict[str, Any],
        font: BrowserFontMeasurements,
    ) -> float:
        atom = self.model.atoms[atom_id]
        length = self.renderer.style.bond_length_px
        size = self.renderer.atom_font_size_pt()
        label_bounds = None
        clearance = 0.0
        label_rect = drawing.get("atom_label_rects", {}).get(str(atom_id))
        if label_rect is not None:
            left, top, width, height = label_rect
            pad = max(0.05, self.renderer.style.bond_line_width * 0.05)
            label_bounds = (
                left - pad,
                top - pad,
                left + width + pad,
                top + height + pad,
            )
            base = font.metrics[f"{size}:H"]
            font_height = float(base["ascent"]) + float(base["descent"])
            symbol_width = 0.0
            if kind in {"plus", "minus"}:
                symbol = "+" if kind == "plus" else "-"
                symbol_width = float(font.metrics[f"{size}:{symbol}"]["bounding_width"])
            clearance = mark_clearance(
                kind,
                bond_length=length,
                line_width=self.renderer.style.bond_line_width,
                font_height=font_height,
                symbol_width=symbol_width,
                symbol_height=font_height,
            )
        return mark_target_distance(
            (atom.x, atom.y), label_bounds, clearance, direction_x, direction_y
        )

    def mark_offset(
        self,
        atom_id: int,
        x: float,
        y: float,
        kind: str,
        drawing: dict[str, Any],
        font: BrowserFontMeasurements,
    ) -> tuple[float, float]:
        atom = self.model.atoms[atom_id]
        return mark_click_offset(
            (atom.x, atom.y),
            (x, y),
            bond_length=self.renderer.style.bond_length_px,
            target_distance=partial(
                self.mark_target_distance_for_atom,
                atom_id,
                kind=kind,
                drawing=drawing,
                font=font,
            ),
        )

    def mark_owner_feedback(
        self, drawing: dict[str, Any], font: BrowserFontMeasurements
    ) -> dict[str, Any]:
        self.render_context.geometry = SimpleNamespace(
            mark_target_distance_for_atom=partial(
                self.mark_target_distance_for_atom, drawing=drawing, font=font
            )
        )
        owners = {}
        for index, item in enumerate(self.mark_items):
            atom_id = item.record["atom_id"]
            atom = self.model.atom_for_id(atom_id)
            feedback: dict[str, Any] = {
                "text": mark_owner_text_for(cast("Any", self), cast("Any", item))
            }
            if atom is not None:
                feedback.update(
                    rect=drawing["mark_owner_rects"][str(atom_id)],
                    line=[atom.x, atom.y, item.center.x(), item.center.y()],
                    color=DISTANT_MARK_COLOR
                    if mark_is_distant_for(cast("Any", self), cast("Any", item))
                    else drawing["selection_style"]["color"],
                    tooltip=f"Owner: {atom.element} #{atom_id}. {MARK_OWNER_GUIDANCE}",
                )
            owners[str(index)] = feedback
        return owners

    def mark_placement(
        self,
        x: float,
        y: float,
        kind: str,
        *,
        scale: float,
        hits: object,
        drawing: dict[str, Any],
        font: BrowserFontMeasurements,
    ) -> tuple[int | None, float, float, float | None, float | None]:
        if not isinstance(kind, str) or kind not in VALID_MARK_KINDS:
            raise ValueError("Unknown charge or radical kind.")
        scale = validated_drawing_scale(scale)
        self.require_sheet_position(x, y)
        x, y = float(x), float(y)
        if drawing.get("needs_measurements"):
            raise ValueError("Mark placement needs completed font measurements.")
        direct = self.selection_buckets(hits).atom_ids
        length = self.renderer.style.bond_length_px
        base_radius = length * 0.35
        tolerance = max(length * 0.05, 1.5 / scale)
        candidates = []
        offsets = {}
        for atom_id, atom in self.model.atoms.items():
            radius = atom_pick_radius(self.renderer)
            bx, by, bw, bh = drawing.get("atom_selection_rects", {}).get(
                str(atom_id), (atom.x - radius, atom.y - radius, radius * 2, radius * 2)
            )
            if (
                bx + bw <= x - base_radius
                or bx >= x + base_radius
                or by + bh <= y - base_radius
                or by >= y + base_radius
            ):
                continue
            offset = self.mark_offset(atom_id, x, y, kind, drawing, font)
            offsets[atom_id] = offset
            candidates.append(
                (
                    atom_id,
                    math.hypot(x - atom.x, y - atom.y),
                    atom_id in direct,
                    math.hypot(*offset),
                )
            )
        owner_id = choose_mark_atom(
            candidates, base_radius=base_radius, tolerance=tolerance
        )
        dx = dy = None
        if owner_id is not None:
            dx, dy = offsets[owner_id]
            atom = self.model.atoms[owner_id]
            x, y = atom.x + dx, atom.y + dy
        return owner_id, x, y, dx, dy

    def insert_mark(
        self,
        x: float,
        y: float,
        kind: str,
        *,
        scale: float,
        hits: object,
        drawing: dict[str, Any],
        font: BrowserFontMeasurements,
    ) -> None:
        owner_id, x, y, dx, dy = self.mark_placement(
            x, y, kind, scale=scale, hits=hits, drawing=drawing, font=font
        )
        self.add_mark_record(kind, owner_id, x, y, dx, dy)

    def add_mark_record(
        self,
        kind: str,
        owner_id: int | None,
        x: float,
        y: float,
        dx: float | None,
        dy: float | None,
    ) -> None:
        record = {
            "kind": kind,
            "text": "+" if kind == "plus" else "-" if kind == "minus" else None,
            "atom_id": owner_id,
            "dx": dx,
            "dy": dy,
            "x": x,
            "y": y,
        }
        self.document_state["marks"].append(record)
        item = BrowserMarkItem(record, BrowserPoint(x, y))
        self.mark_items.append(item)
        if owner_id is not None:
            self.runtime_state.mark_registry.add_for_atom(owner_id, item)
            annotations = build_atom_annotations(
                {owner_id},
                {owner_id: owner_id},
                {
                    owner_id: [
                        item.record["kind"]
                        for item in self.runtime_state.mark_registry.get_for_atom(
                            owner_id
                        )
                    ]
                },
            )
            self.model.set_atom_annotation(owner_id, annotations.get(owner_id))
        self.publish_model()

    def change_charge_for_atom(
        self, atom_id: int, delta: int, font: BrowserFontMeasurements | None
    ) -> None:
        if font is None:
            raise ValueError("Charge placement needs completed font measurements.")
        marks = self.runtime_state.mark_registry.get_for_atom(atom_id) or []
        cancel = opposite_charge_mark(marks, delta)
        if cancel is not None:
            self.delete_selection(
                [{"target": "mark", "id": self.mark_items.index(cancel)}]
            )
            return
        atom = self.model.atoms[atom_id]
        kind = "plus" if delta > 0 else "minus"
        drawing = font.drawing(self.document_state)
        dx, dy = self.mark_offset(atom_id, atom.x, atom.y, kind, drawing, font)
        self.add_mark_record(kind, atom_id, atom.x + dx, atom.y + dy, dx, dy)
        item = self.mark_items[-1]
        drawing = font.drawing(self.document_state)

        def ink_rect(index: int) -> tuple[float, float, float, float]:
            mark = drawing["marks"][index]
            x, y, width, height = (
                mark.get("hit_rect", (0.0, 0.0, 0.0, 0.0))
                if self.mark_items[index].record["kind"] in {"plus", "minus"}
                else mark["bounds"]
            )
            return x, y, x + width, y + height

        left, top, right, bottom = ink_rect(len(self.mark_items) - 1)
        center = item.center
        dx, dy = shortcut_mark_offset(
            (atom.x, atom.y),
            (
                left - center.x(),
                top - center.y(),
                right - center.x(),
                bottom - center.y(),
            ),
            [
                ink_rect(index)
                for index, other in enumerate(self.mark_items)
                if other is not item and other.record["atom_id"] == atom_id
            ],
            bond_length=self.renderer.style.bond_length_px,
            click_offset=lambda x, y: self.mark_offset(
                atom_id, x, y, kind, drawing, font
            ),
        )
        item.set_center(BrowserPoint(atom.x + dx, atom.y + dy))
        item.record.update(dx=dx, dy=dy)

    def move_selection(self, items: object, dx: float, dy: float) -> None:
        buckets = self.selection_buckets(items)
        if dx == 0 and dy == 0:
            return
        atoms = self.selected_atom_ids(buckets)
        controller = CanvasMoveController(
            cast("Any", self),
            point_factory=BrowserPoint,
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
        for item in independent_selection_items(buckets.mark_items, atoms):
            controller.move_item(item, dx, dy, update_selection=False)
        for item in buckets.other_items:
            if item.data(0) == "orbital":
                controller.move_item(item, dx, dy, update_selection=False)
                continue
            source = cast("BrowserSceneItem", item).record
            source.update(
                shape_to_state(
                    moved_shape(normalized_shape(shape_from_state(source)), dx, dy)
                )
            )
        for item in buckets.ts_bracket_items:
            source = cast("BrowserSceneItem", item).record
            source.update(
                ts_bracket_to_state(
                    moved_ts_bracket(ts_bracket_from_state(source), dx, dy)
                )
            )
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
            marks_by_atom=self.runtime_state.mark_registry.by_atom,
            atom_has_visible_label=lambda atom_id: atom_shows_itself(
                self.model.atoms[atom_id]
            ),
        )
        for bond_id in plan.bond_ids_to_remove:
            self.model.clear_bond(bond_id)
        for atom_id in plan.atom_ids:
            self.model.pop_atom(atom_id)
        removed_records = {
            id(cast("BrowserSceneItem", item).record) for item in plan.scene_items
        }
        self.document_state["arrows"] = [
            arrow
            for arrow in self.document_state["arrows"]
            if id(arrow) not in removed_records
        ]
        self.document_state["shapes"] = [
            shape
            for shape in self.document_state["shapes"]
            if id(shape) not in removed_records
        ]
        self.document_state["ts_brackets"] = [
            bracket
            for bracket in self.document_state["ts_brackets"]
            if id(bracket) not in removed_records
        ]
        self.document_state["orbitals"] = [
            orbital
            for orbital in self.document_state["orbitals"]
            if id(orbital) not in removed_records
        ]
        self.document_state["marks"] = [
            record
            for record in self.document_state["marks"]
            if id(record) not in removed_records
        ]
        self.mark_items[:] = [
            item for item in self.mark_items if id(item.record) not in removed_records
        ]
        for _atom_id, marks in self.runtime_state.mark_registry.items():
            marks[:] = [
                item for item in marks if id(item.record) not in removed_records
            ]
        annotations = build_atom_annotations(
            plan.mark_owner_ids,
            {atom_id: atom_id for atom_id in plan.mark_owner_ids},
            {
                atom_id: [item.record["kind"] for item in marks]
                for atom_id, marks in self.runtime_state.mark_registry.items()
            },
        )
        for atom_id in plan.mark_owner_ids:
            self.model.set_atom_annotation(atom_id, annotations.get(atom_id))
        for atom_id in unmarked_isolated_carbon_ids(
            plan.mark_owner_ids,
            atoms=self.model.atoms,
            bonds=self.model.bonds,
            has_visible_label=lambda atom_id: atom_shows_itself(
                self.model.atoms[atom_id]
            ),
            has_marks=lambda atom_id: bool(
                self.runtime_state.mark_registry.get_for_atom(atom_id)
            ),
        ):
            self.model.atoms[atom_id].explicit_label = True
        rings = self.document_state.get("ring_fills", [])
        broken = broken_ring_fill_indices(
            [ring["atom_ids"] for ring in rings],
            atom_ids=set(self.model.atoms),
            bond_pairs=model_bond_pairs(self.model),
        )
        self.document_state["ring_fills"] = [
            ring
            for index, ring in enumerate(rings)
            if index not in broken and id(ring) not in removed_records
        ]
        self.publish_model()


def validated_edit_fields(edit: object) -> tuple[dict[str, Any], str]:
    """Validate common wire fields before adapting an individual edit."""
    if not isinstance(edit, dict):
        raise ValueError("edit must be an object.")
    kind = edit.get("kind")
    for key in ("x", "y", "dx", "dy", "value"):
        if key in edit and (
            type(edit[key]) not in (int, float, Decimal) or not math.isfinite(edit[key])
        ):
            raise ValueError("Edit coordinates and lengths must be finite numbers.")
    if "grid" in edit and kind not in {"arrow", "line", "arrow_handle"}:
        raise ValueError("Grid snapping only applies to arrow and line gestures.")
    if kind in {"bond", "bond_style"} and edit.get("style") not in BOND_ORDERS:
        raise ValueError("Unsupported bond style.")
    fields = dict(edit)
    grid = fields.pop("grid", "none")
    return fields, grid


def edit_document(
    request: object,
    *,
    font: BrowserFontMeasurements | None = None,
    preview: bool = False,
    mark_order: dict[int, list[int]] | None = None,
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
    edit, grid = validated_edit_fields(request["edit"])
    kind = edit.get("kind")
    candidate = deepcopy(extract_document_state(payload))
    daggers = any(
        bracket["bracket_kind"] in BRACKET_SYMBOLS
        for bracket in candidate["ts_brackets"]
    )
    adapter = BrowserStructureAdapter(
        candidate,
        grid=grid,
        mark_order=mark_order,
        measured_drawing=document_info(payload, font=font)["drawing"]
        if daggers and font is not None
        else None,
    )
    shortcut_tool = None
    edit_notice = None
    if kind == "bond" and set(edit) == {"kind", "start", "end", "style"}:
        adapter.insert_bond(edit["start"], edit["end"], edit["style"])
    elif kind in {"arrow", "line"} and set(edit) == {
        "kind",
        "start",
        "end",
        "style",
        "dragged",
        "shift",
        "scale",
    } | ({"hits"} if kind == "line" else set()):
        adapter.insert_arrow(edit, preview=preview)
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
            float(edit["x"]),
            float(edit["y"]),
            edit["key"],
            edit.get("atom_id"),
            font=font,
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
    elif kind in {"rotate", "flip", "align", "distribute"}:
        adapter.transform_selection(
            edit,
            document_info(payload, font=font)["drawing"]
            if kind in {"align", "distribute"} or adapter.mark_items or daggers
            else None,
        )
    elif kind == "move" and set(edit) == {"kind", "selection", "dx", "dy"}:
        adapter.move_selection(edit["selection"], float(edit["dx"]), float(edit["dy"]))
    elif kind == "erase" and set(edit) == {"kind", "x", "y", "hits", "scale"}:
        target = adapter.pick_target(
            edit["x"], edit["y"], edit["hits"], preferred=False, scale=edit["scale"]
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
    elif (
        kind == "atom_prompt" and set(edit) == {"kind", "atom_id", "text", "x", "y"}
    ) or (
        kind == "atom"
        and {"kind", "x", "y", "text"}
        <= set(edit)
        <= {
            "kind",
            "x",
            "y",
            "text",
            "atom_id",
        }
    ):
        adapter.apply_atom_input(edit)
    elif kind == "mark" and set(edit) == {
        "kind",
        "x",
        "y",
        "mark_kind",
        "scale",
        "hits",
    }:
        if font is None:
            raise ValueError("Mark placement needs completed font measurements.")
        adapter.insert_mark(
            edit["x"],
            edit["y"],
            edit["mark_kind"],
            scale=edit["scale"],
            hits=edit["hits"],
            drawing=font.drawing(candidate),
            font=font,
        )
    elif kind == "mark_owner" and set(edit) == {"kind", "id", "atom_id"}:
        adapter.rebind_mark(edit["id"], edit["atom_id"])
    elif kind in {"orbital", "ts_bracket"}:
        (adapter.insert_orbital if kind == "orbital" else adapter.insert_bracket)(edit)
    elif kind == "orbital_handle":
        adapter.move_orbital_handle(edit)
    elif kind in {"arrow_handle", "shape_handle"}:
        (
            adapter.move_arrow_handle
            if kind == "arrow_handle"
            else adapter.move_shape_handle
        )(edit)
    elif kind == "arrow_labels" and set(edit) == {"kind", "id", "labels"}:
        adapter.set_arrow_labels(edit)
    elif kind in {"color", "ring_fill"}:
        edit_notice = (
            adapter.apply_color if kind == "color" else adapter.apply_ring_fill
        )(edit)
    elif kind == "stack":
        adapter.stack_selection(edit)
    elif kind == "shape" and set(edit) == {"kind", "start", "end", "style", "stroke"}:
        adapter.insert_shape(edit)
    elif kind in {"arrow_style", "bond_length", "sheet_setup", "orbital_phase"}:
        adapter.set_drawing_settings(edit)
    else:
        raise ValueError("Unsupported edit or unexpected fields.")
    mark_indices = {id(item): index for index, item in enumerate(adapter.mark_items)}
    next_mark_order = {
        atom_id: [mark_indices[id(item)] for item in items]
        for atom_id, items in adapter.runtime_state.mark_registry.items()
        if items
    }
    result = document_info(
        build_normalized_document_payload(candidate, payload["version"])
        if adapter.candidate_accepted
        else payload,
        font=font,
        mark_order=next_mark_order if adapter.candidate_accepted else mark_order,
    )
    if kind == "hover_shortcut":
        result["shortcut_tool"] = shortcut_tool
    result["edit_notice"] = edit_notice
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
        self.before, self.after = before["document"], after["document"]
        self.before_mark_order, self.after_mark_order = (
            before["mark_order"],
            after["mark_order"],
        )

    @override
    def undo(self, operations: Any) -> None:
        operations.info = document_info(
            self.before, font=operations.font, mark_order=self.before_mark_order
        )

    @override
    def redo(self, operations: Any) -> None:
        operations.info = document_info(
            self.after, font=operations.font, mark_order=self.after_mark_order
        )


def selection_presentation(
    info: dict[str, Any], selection: object
) -> tuple[list[list[dict[str, Any]]], dict[str, Any] | None]:
    adapter = BrowserStructureAdapter(extract_document_state(info["document"]))
    return (
        adapter.selection_components(selection, info["drawing"]),
        adapter.selection_frame(selection, info["drawing"]),
    )


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
        edit_notice = None
        result = None
        if action != "read" and request.get("revision") != self.revision:
            raise StaleRevisionError(
                "This window has stale state. Refresh it before editing."
            )
        if action == "selection":
            if set(request) - {"session", "revision", "action", "selection"}:
                raise ValueError("Unexpected selection presentation fields.")
            info = self.info
            if info["drawing"].get("needs_measurements"):
                raise ValueError("Selection needs completed font measurements.")
            components, frame = selection_presentation(info, request.get("selection"))
            return {"components": components, "frame": frame, "revision": self.revision}
        if action == "mark_preview":
            if set(request) - {
                "session",
                "revision",
                "action",
                "x",
                "y",
                "kind",
                "scale",
                "hits",
                "font",
            }:
                raise ValueError("Unexpected mark preview fields.")
            if self.info["unsupported"]:
                raise ValueError("Mark preview needs an editable drawing.")
            font = BrowserFontMeasurements(request["font"])
            adapter = BrowserStructureAdapter(
                deepcopy(extract_document_state(self.info["document"]))
            )
            drawing = font.drawing(adapter.document_state)
            owner, x, y, _dx, _dy = adapter.mark_placement(
                request["x"],
                request["y"],
                request["kind"],
                scale=request["scale"],
                hits=request["hits"],
                drawing=drawing,
                font=font,
            )
            # A free transient glyph uses the existing renderer without changing chemistry.
            adapter.add_mark_record(request["kind"], None, x, y, None, None)
            atom = adapter.model.atom_for_id(owner)
            return {
                "mark": font.drawing(adapter.document_state)["marks"][-1],
                "atom": [
                    atom.x,
                    atom.y,
                    adapter.renderer.style.bond_length_px * ATOM_HOVER_RADIUS_RATIO,
                ]
                if atom is not None
                else None,
                "owner": owner,
                "revision": self.revision,
            }
        if action == "label_preview":
            if set(request) - {"session", "revision", "action", "labels"}:
                raise ValueError("Unexpected label preview fields.")
            labels = request.get("labels")
            if (
                not isinstance(labels, dict)
                or set(labels) != {"above", "below"}
                or any(
                    not isinstance(text, str) or len(text) > 4096
                    for text in labels.values()
                )
            ):
                raise ValueError("Expected bounded arrow label preview text.")
            return {
                "html": {side: arrow_label_html(text) for side, text in labels.items()}
            }
        if action == "pick":
            if (
                set(request)
                - {
                    "session",
                    "revision",
                    "action",
                    "x",
                    "y",
                    "hits",
                    "preferred",
                    "scale",
                }
                or type(request.get("preferred")) is not bool
            ):
                raise ValueError("Expected a bounded selection pick request.")
            adapter = BrowserStructureAdapter(
                extract_document_state(self.info["document"]),
                measured_drawing=self.info.get("drawing"),
            )
            return {
                "target": adapter.pick_target(
                    request["x"],
                    request["y"],
                    request["hits"],
                    preferred=request["preferred"],
                    scale=request.get("scale"),
                ),
                "revision": self.revision,
            }
        if action == "measure":
            if set(request) - {
                "session",
                "revision",
                "action",
                "font",
                "edit",
                "selection",
            }:
                raise ValueError("Unexpected font measurement fields.")
            font = BrowserFontMeasurements(request["font"])
            result = (
                edit_document(
                    {"document": self.info["document"], "edit": request["edit"]},
                    font=font,
                    mark_order=self.info["mark_order"],
                    preview=True,
                )
                if "edit" in request
                else document_info(
                    self.info["document"], font=font, mark_order=self.info["mark_order"]
                )
            )
            if result["drawing"].get("needs_measurements"):
                raise ValueError("Font measurements do not match the drawing.")
            self.font = font
            if "edit" not in request:
                self.info = result
        elif action == "preview":
            if set(request) - {"session", "revision", "action", "edit", "selection"}:
                raise ValueError("Unexpected preview fields.")
            result = edit_document(
                {"document": self.info["document"], "edit": request["edit"]},
                font=self.font,
                mark_order=self.info["mark_order"],
                preview=True,
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
                mark_order=self.info["mark_order"],
            )
            shortcut_tool = candidate.pop("shortcut_tool", None)
            edit_notice = candidate.pop("edit_notice", None)
            if candidate["document"] != self.info["document"]:
                # Push first: a failed record cannot publish the candidate.
                self.history.push(DocumentChange(self.info, candidate))
                self.info = candidate
        elif action in {"undo", "redo"}:
            getattr(self.history, action)()
        elif action != "read":
            raise ValueError("Unknown browser action.")
        if (
            action in {"preview", "measure"}
            and "selection" in request
            and result is not None
            and not result["drawing"].get("needs_measurements")
        ):
            components, frame = selection_presentation(result, request["selection"])
            result = {
                **result,
                "selection_components": components,
                "selection_frame": frame,
            }
        if action not in {"read", "measure", "preview"}:
            self.revision += 1
        return {
            **(self.info if result is None else result),
            "shortcut_tool": shortcut_tool,
            "edit_notice": edit_notice,
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
