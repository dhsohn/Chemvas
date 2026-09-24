"""Populate native document graphics without an editor, history, or view."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor

from chemvas.ui.annotations.materialize import create_scene_item_from_state
from chemvas.ui.canvas_scene_items_state import (
    document_collection_for,
    require_scene_record_id,
)
from chemvas.ui.molecule_scene_renderer import (
    prepare_molecule_for_scene,
    render_molecule,
)
from chemvas.ui.scene_selectability import make_item_selectable
from chemvas.ui.sheet_setup_logic import normalize_sheet_setup

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtWidgets import QGraphicsTextItem

    from chemvas.ui.scene_render_context import SceneRenderContext


def populate_document_scene(
    context: SceneRenderContext,
    state: dict,
    *,
    note_item_factory: Callable[[], QGraphicsTextItem] | None = None,
) -> None:
    """Draw validated state on its cleared scene after the caller installs its model."""
    settings = state["settings"]
    context.renderer.set_bond_length(settings["bond_length_px"])
    tools = context.state.tool_settings_state
    for name in ("arrow_line_width", "arrow_head_scale", "orbital_phase_enabled"):
        setattr(tools, name, settings[name])
    text = context.state.text_style_state
    for name in (
        "text_font_family",
        "text_font_size",
        "text_font_weight",
        "text_italic",
        "text_line_spacing",
        "note_box_enabled",
        "note_box_alpha",
        "note_border_enabled",
        "note_border_width",
        "note_padding",
    ):
        setattr(text, name, settings[name])
    for name in ("text_color", "note_box_color", "note_border_color"):
        setattr(text, name, QColor(settings[name]))
    text.text_alignment = {
        "left": Qt.AlignmentFlag.AlignLeft,
        "center": Qt.AlignmentFlag.AlignHCenter,
        "right": Qt.AlignmentFlag.AlignRight,
        "justify": Qt.AlignmentFlag.AlignJustify,
    }[settings["text_alignment"]]
    sheet = context.state.sheet_setup_state
    sheet.size_name, sheet.orientation = normalize_sheet_setup(
        settings["sheet_size"], settings["sheet_orientation"]
    )

    drawing_items = context.state.scene_items_state

    def attach(item_state: dict, collection_name: str):
        collection = getattr(drawing_items, collection_name)
        item = create_scene_item_from_state(
            context, item_state, note_item_factory=note_item_factory
        )
        if item is None:
            if item_state["kind"] == "mark" and item_state.get("_auto_position"):
                raise RuntimeError(
                    "Failed to materialize an atom annotation as a scene mark."
                )
            raise RuntimeError("Failed to materialize a document scene item.")
        kind = item_state["kind"]
        if kind == "mark":
            atom_id = item_state.get("atom_id")
            if isinstance(atom_id, int):
                context.state.mark_registry.add_for_atom(atom_id, item)
        make_item_selectable(item)
        if isinstance(collection, dict):
            record_id = require_scene_record_id(item)
            document_collection_for(context.state, collection_name).add(record_id)
            collection[record_id] = item
        else:
            collection.append(item)
        context.scene.addItem(item)
        return item

    for item_state in state["ring_fills"]:
        attach({**item_state, "kind": "ring"}, "ring_items")
    for item_state in state.get("images", []):
        attach(item_state, "image_items")

    perspective = state.get("perspective") or {}
    context.state.atom_coords_3d_state.atom_coords_3d = {
        int(atom_id): (float(coords[0]), float(coords[1]), float(coords[2]))
        for atom_id, coords in perspective.get("atom_coords_3d", {}).items()
    }
    rotation = context.state.rotation_state
    center = perspective.get("projection_center_3d")
    anchor = perspective.get("projection_anchor_2d")
    rotation.projection_center_3d = (
        (float(center[0]), float(center[1]), float(center[2]))
        if center is not None
        else None
    )
    rotation.projection_anchor_2d = (
        (float(anchor[0]), float(anchor[1])) if anchor is not None else None
    )
    prepare_molecule_for_scene(context.model)
    render_molecule(context)

    for item_state in state["notes"]:
        attach({**item_state, "kind": "note"}, "note_items")
    for item_state in state["marks"]:
        mark = {
            **item_state,
            "kind": "mark",
            "mark_kind": item_state["kind"],
        }
        if item_state.get("_auto_position") is True:
            atom_id = item_state["atom_id"]
            atom = context.model.atoms.get(atom_id)
            if atom is None:
                raise RuntimeError(
                    "Failed to materialize an atom annotation as a scene mark."
                )
            offset = context.geometry.mark_offset_from_click(
                atom_id,
                QPointF(float(item_state["x"]), float(item_state["y"])),
                kind=item_state["kind"],
            )
            mark.update(
                dx=offset.x(),
                dy=offset.y(),
                x=atom.x + offset.x(),
                y=atom.y + offset.y(),
            )
            if item_state["kind"] in {"plus", "minus"}:
                mark["text"] = "+" if item_state["kind"] == "plus" else "-"
            else:
                mark.pop("text", None)
        attach(mark, "mark_items")
    for item_state in state["arrows"]:
        attach(item_state, "arrow_items")
    for item_state in state["ts_brackets"]:
        attach(item_state, "ts_bracket_items")
    for item_state in state["shapes"]:
        attach(item_state, "shape_items")
    for item_state in state["orbitals"]:
        attach(
            {**item_state, "kind": "orbital", "orbital_kind": item_state["kind"]},
            "orbital_items",
        )
