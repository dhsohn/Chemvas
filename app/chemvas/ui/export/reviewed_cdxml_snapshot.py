"""A reviewed saved drawing and its export scope, detached from editor IDs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsItem

from chemvas.features.groups import restored_groups
from chemvas.ui.canvas.canvas_document_state import GROUP_COLLECTION_STATES
from chemvas.ui.canvas.canvas_scene_items_state import SCENE_ITEM_COLLECTION_ATTRS
from chemvas.ui.canvas.document_scene import detached_document_scene
from chemvas.ui.export.export_scope import (
    EXPORT_EXCLUDED_KINDS,
    collect_export_items,
    export_item_closure,
)
from chemvas.ui.export.figure_export_service import FigureExportService

if TYPE_CHECKING:
    from collections.abc import Sequence

    from chemvas.features.export import CdxmlLabelBindings, ExportPlan
    from chemvas.ui.scene.scene_render_context import SceneRenderContext

ItemRef = tuple[str | int, ...]
PaintEntry = tuple[ItemRef, float, ItemRef | None, bool, bool]


def _restore_paint_order(
    context: SceneRenderContext,
    index: dict[ItemRef, QGraphicsItem],
    order: tuple[PaintEntry, ...],
) -> None:
    """Restore sibling stacking without flattening parent/child paint ownership."""
    by_item = {item: ref for ref, item in index.items()}
    siblings: dict[tuple[ItemRef | None, float], list[QGraphicsItem]] = {}
    flags = QGraphicsItem.GraphicsItemFlag
    for ref, z, parent_ref, behind, negative_behind in order:
        item = index.get(ref)
        if item is None or item.parentItem() is not (
            None if parent_ref is None else index.get(parent_ref)
        ):
            raise ValueError("The saved drawing cannot reproduce captured paint order.")
        item.setFlag(flags.ItemNegativeZStacksBehindParent, negative_behind)
        item.setZValue(z)
        item.setFlag(flags.ItemStacksBehindParent, behind)
        siblings.setdefault((parent_ref, z), []).append(item)
    for items in siblings.values():
        for before, after in zip(
            reversed(items[:-1]), reversed(items[1:]), strict=True
        ):
            before.stackBefore(after)
    actual = tuple(
        by_item[item]
        for item in context.scene.items(Qt.SortOrder.AscendingOrder)
        if item in by_item
    )
    if actual != tuple(row[0] for row in order):
        raise ValueError("The saved drawing cannot reproduce captured paint order.")


def _scene_item_index(context: SceneRenderContext) -> dict[ItemRef, QGraphicsItem]:
    """Use document order for bonds/annotations, never a sidecar-derived mapping."""
    result: dict[ItemRef, QGraphicsItem] = {}

    def add(ref: ItemRef, item: QGraphicsItem) -> None:
        if item.data(0) in EXPORT_EXCLUDED_KINDS:
            return
        result[ref] = item
        children = [
            child
            for child in item.childItems()
            if child.data(0) not in EXPORT_EXCLUDED_KINDS
        ]
        for index, child in enumerate(children):
            add((*ref, "child", index), child)

    atoms = context.state.atom_graphics_state
    for kind, items in (("atom", atoms.atom_items), ("dot", atoms.atom_dots)):
        for atom_id, item in items.items():
            add((kind, atom_id), item)
    saved_bond_id = 0
    for live_bond_id, bond in enumerate(context.model.bonds):
        if bond is None:
            continue
        for index, item in enumerate(
            context.state.bond_graphics_state.bond_items.get(live_bond_id, ())
        ):
            add(("bond", saved_bond_id, index), item)
        saved_bond_id += 1
    for name in SCENE_ITEM_COLLECTION_ATTRS:
        for index, item in enumerate(context.state.scene_items(name)):
            if item is not None:
                add((name, index), item)
    return result


@dataclass(frozen=True)
class ReviewedCdxmlSnapshot:
    """Immutable saved state, reviewed meanings and one captured scope generation."""

    document_json: bytes
    label_bindings: CdxmlLabelBindings
    scope: str
    visible_refs: frozenset[ItemRef]
    selection_refs: tuple[ItemRef, ...] | None
    paint_order: tuple[PaintEntry, ...]

    @classmethod
    def capture(
        cls,
        context: SceneRenderContext,
        state: dict,
        label_bindings: CdxmlLabelBindings,
        *,
        scope: str,
        selection: Sequence[QGraphicsItem] | None,
    ) -> ReviewedCdxmlSnapshot:
        index = _scene_item_index(context)
        by_item = {item: ref for ref, item in index.items()}

        def reference(item: QGraphicsItem) -> ItemRef:
            try:
                return by_item[item]
            except KeyError as exc:
                raise ValueError(
                    "The export scope contains graphics without a saved document "
                    "reference. No file was written."
                ) from exc

        # Check exactly the requested scope, including its child graphics. An
        # unsupported item outside selection must not block a selected export.
        items = (
            export_item_closure(selection or ())
            if scope == "selection"
            else collect_export_items(context.scene)
        )
        for item in items:
            reference(item)
        selected = (
            tuple(reference(item) for item in selection)
            if selection is not None
            else None
        )
        flags = QGraphicsItem.GraphicsItemFlag
        paint_order = tuple(
            (
                reference(item),
                item.zValue(),
                reference(parent)
                if (parent := item.parentItem()) is not None
                else None,
                bool(item.flags() & flags.ItemStacksBehindParent),
                bool(item.flags() & flags.ItemNegativeZStacksBehindParent),
            )
            for item in context.scene.items(Qt.SortOrder.AscendingOrder)
            if item in by_item
        )
        return cls(
            json.dumps(state, allow_nan=False).encode("utf-8"),
            label_bindings,
            scope,
            frozenset(ref for ref, item in index.items() if item.isVisible()),
            selected,
            paint_order,
        )

    def export(
        self,
        path: str,
        *,
        dpi: int,
        background: str,
        sizing: str,
        target_width_mm: float | None,
        max_height_mm: float | None,
        min_font_pt: float | None,
    ) -> ExportPlan:
        state = json.loads(self.document_json)
        with detached_document_scene(state) as context:
            index = _scene_item_index(context)
            required = self.visible_refs | frozenset(self.selection_refs or ())
            if not required <= index.keys():
                raise ValueError(
                    "The saved drawing cannot reproduce the captured export scope. "
                    "No file was written."
                )
            for ref, item in index.items():
                item.setVisible(ref in self.visible_refs)
            _restore_paint_order(context, index, self.paint_order)
            selection = (
                [index[ref] for ref in self.selection_refs]
                if self.selection_refs is not None
                else None
            )
            groups = restored_groups(
                state.get("groups") or [],
                context.model.atoms,
                {
                    key: context.state.document_collection(name).order
                    for key, name in GROUP_COLLECTION_STATES.items()
                },
            )
            return FigureExportService(
                context, groups=dict(enumerate(groups, start=1))
            ).export_figure(
                path,
                fmt="cdxml",
                scope=self.scope,
                selection=selection,
                dpi=dpi,
                background=background,
                sizing=sizing,
                target_width_mm=target_width_mm,
                max_height_mm=max_height_mm,
                min_font_pt=min_font_pt,
                label_bindings=self.label_bindings,
            )


__all__ = ["ReviewedCdxmlSnapshot"]
