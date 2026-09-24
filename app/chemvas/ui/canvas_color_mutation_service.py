from __future__ import annotations

from dataclasses import dataclass, replace
from functools import partial
from typing import TYPE_CHECKING, Protocol, override

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsTextItem

from chemvas.core.history import (
    CompositeCommand,
    HistoryCommand,
    UpdateAtomColorCommand,
)
from chemvas.features.graph import find_rings
from chemvas.ui.annotations.materialize import restore_ring_projections
from chemvas.ui.annotations.records import (
    require_shape_record_for,
    set_shape_record_for,
)
from chemvas.ui.annotations.state import (
    ARROW_KINDS,
    arrow_state_dict_for,
    mark_state_dict_for,
    ring_state_dict_for,
    shape_state_dict_for,
)
from chemvas.ui.atom_label_access import implicit_carbon_dot_brush_for
from chemvas.ui.bond_graphics_access import apply_color_to_bond_item_for
from chemvas.ui.canvas_atom_graphics_state import (
    atom_dots_for,
    atom_items_for,
    visible_atom_item_for,
)
from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id
from chemvas.ui.canvas_model_access import (
    atom_for_id,
    atoms_for,
    bond_for_id,
    bonds_for,
)
from chemvas.ui.canvas_ring_fill_scene_access import create_ring_fill_item_for
from chemvas.ui.canvas_scene_items_state import require_scene_record_id
from chemvas.ui.canvas_window_access import notify_error_for
from chemvas.ui.graphics_items import AtomDotItem
from chemvas.ui.history_commands import AddSceneItemsCommand, UpdateSceneItemCommand
from chemvas.ui.mark_item_access import apply_mark_color_for
from chemvas.ui.scene_item_access import attach_scene_item, item_is_in_canvas_scene
from chemvas.ui.scene_render_access import scene_render_context_for
from chemvas.ui.transactions.document import document_transaction
from chemvas.ui.transactions.scene_runtime import graphics_item_is_deleted

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from chemvas.ui.canvas_note_controller import CanvasNoteController
    from chemvas.ui.canvas_view import CanvasView


def apply_bond_color_in_place(canvas, bond_id: int, color: QColor | str) -> None:
    """Apply a value inside the caller's document/history transaction."""
    bond = bond_for_id(canvas, bond_id)
    color_value = QColor(color)
    if bond is None or not color_value.isValid():
        return
    bond.color = color_value.name()
    for item in bond_items_for_id(canvas, bond_id):
        apply_color_to_bond_item_for(canvas, item, color_value)


class HistoryBondColorOperations(Protocol):
    def apply_bond_color(self, bond_id: int, color: str) -> None: ...


@dataclass
class UpdateBondColorCommand(HistoryCommand):
    history_transaction_owns_exact_state = True
    history_transaction_snapshot_covers_state = True

    bond_id: int
    before_color: str
    after_color: str

    @override
    def undo(self, operations: HistoryBondColorOperations) -> None:
        operations.apply_bond_color(self.bond_id, self.before_color)

    @override
    def redo(self, operations: HistoryBondColorOperations) -> None:
        operations.apply_bond_color(self.bond_id, self.after_color)


class CanvasColorMutationService:
    # Opaque pastel panels read as tinted paper behind a structure.
    SHAPE_FILL_TINT = 0.12

    def __init__(
        self,
        canvas: CanvasView,
        *,
        graph_service,
        note_controller: CanvasNoteController,
        history_service=None,
    ) -> None:
        self.canvas = canvas
        self.graph_service = graph_service
        self.note_controller = note_controller
        self.history = history_service

    def _live_items(self, items: Iterable[object]) -> list:
        return [
            item
            for item in items
            if item is not None
            and not graphics_item_is_deleted(item)
            and item_is_in_canvas_scene(self.canvas, item)
        ]

    def _publish(self, commands: list[HistoryCommand]) -> None:
        if commands and self.history is not None:
            command = commands[0] if len(commands) == 1 else CompositeCommand(commands)
            if self.history.push(command) is False:
                raise RuntimeError("Color history push did not commit")

    def apply_color_to_item(self, item, color: QColor) -> None:
        self.apply_color_to_items([item], color)

    def apply_color_to_items(self, items: Iterable[object], color: QColor) -> None:
        if not color.isValid():
            return
        selected = self._live_items(items)
        if not selected:
            return
        with document_transaction(self.canvas, history_service=self.history):
            targets = []
            seen: set[int] = set()
            for item in selected:
                expanded = (
                    self._resolve_ring_structure_targets(item)
                    if item.data(0) == "ring"
                    else (item,)
                )
                for target in expanded:
                    if id(target) not in seen:
                        seen.add(id(target))
                        targets.append(target)
            commands = []
            for item in targets:
                commands.extend(self._apply_color(item, color))
            self._publish(commands)
        if all(
            isinstance(item, AtomDotItem) and item.brush().color().alpha() == 0
            for item in selected
        ):
            notify_error_for(
                self.canvas,
                "Color stored for implicit carbon; hidden carbon vertices stay hidden. "
                "Color the bonds or show an explicit atom label for visible color.",
            )

    def _apply_color(self, item, color: QColor) -> list[HistoryCommand]:
        kind = item.data(0)
        if kind == "bond":
            bond_id = item.data(1)
            bond = (
                bond_for_id(self.canvas, bond_id) if isinstance(bond_id, int) else None
            )
            if bond is None or bond.color == color.name():
                return []
            before = bond.color
            apply_bond_color_in_place(self.canvas, bond_id, color)
            return [UpdateBondColorCommand(bond_id, before, bond.color)]
        if kind == "atom":
            return self._apply_atom_color(item, color)
        if kind == "note" and isinstance(item, QGraphicsTextItem):
            return self.note_controller.apply_note_color(item, color)
        if kind == "shape":
            fill = self._pastel_fill(color, self.SHAPE_FILL_TINT)
            return self._mutate_scene_item(
                item,
                shape_state_dict_for,
                lambda: set_shape_record_for(
                    self.canvas,
                    item,
                    replace(
                        require_shape_record_for(self.canvas, item),
                        fill=fill.name(),
                        fill_alpha=fill.alphaF(),
                    ),
                ),
            )
        if kind == "mark":
            return self._mutate_scene_item(
                item,
                mark_state_dict_for,
                lambda: apply_mark_color_for(self.canvas, item, color.name()),
            )
        if kind in ARROW_KINDS:
            arrows = scene_render_context_for(self.canvas).arrows
            return self._mutate_scene_item(
                item,
                arrow_state_dict_for,
                lambda: arrows.set_record(
                    item, replace(arrows.record(item), color=color.name())
                ),
            )
        if kind == "ts_bracket":
            notify_error_for(
                self.canvas,
                "TS brackets and daggers use the document bond color; "
                "per-item color is not supported.",
            )
        return []

    def _mutate_scene_item(
        self,
        item,
        state_for: Callable[[object, object], dict],
        mutation: Callable[[], object],
    ) -> list[HistoryCommand]:
        before = state_for(self.canvas, item)
        mutation()
        after = state_for(self.canvas, item)
        return (
            [UpdateSceneItemCommand(require_scene_record_id(item), before, after)]
            if before != after
            else []
        )

    @staticmethod
    def _pastel_fill(color: QColor, tint: float) -> QColor:
        return QColor(
            round(255 - (255 - color.red()) * tint),
            round(255 - (255 - color.green()) * tint),
            round(255 - (255 - color.blue()) * tint),
        )

    def _apply_atom_item_graphic(self, item, color: QColor) -> None:
        if isinstance(item, QGraphicsTextItem):
            item.setDefaultTextColor(color)
        elif isinstance(item, AtomDotItem):
            item.setBrush(implicit_carbon_dot_brush_for(self.canvas))
        elif isinstance(item, QGraphicsEllipseItem):
            item.setBrush(color)

    def _apply_atom_color(self, item, color: QColor) -> list[HistoryCommand]:
        atom_id = item.data(1)
        atom = atom_for_id(self.canvas, atom_id if isinstance(atom_id, int) else None)
        if atom is None:
            self._apply_atom_item_graphic(item, color)
            return []
        if atom.color == color.name():
            return []
        before = atom.color
        atom.color = color.name()
        self._apply_atom_item_graphic(item, color)
        label = atom_items_for(self.canvas).get(atom_id)
        if label is not None and label is not item:
            label.setDefaultTextColor(color)
        dot = atom_dots_for(self.canvas).get(atom_id)
        if dot is not None and dot is not item:
            dot.setBrush(implicit_carbon_dot_brush_for(self.canvas))
        return [UpdateAtomColorCommand(atom_id, before, atom.color)]

    def apply_ring_fill_color(self, item, color: QColor, alpha: float = 0.25) -> None:
        if (
            item is not None
            and not graphics_item_is_deleted(item)
            and item.data(0) == "ring"
        ):
            self.apply_ring_fill_color_to_items([item], color, alpha)

    def apply_ring_fill_color_to_items(
        self, items: Iterable[object], color: QColor, alpha: float = 0.25
    ) -> None:
        if not color.isValid():
            return
        selected = self._live_items(items)
        targets = list(
            dict.fromkeys(item for item in selected if item.data(0) == "ring")
        )
        with document_transaction(self.canvas, history_service=self.history):
            selected_atoms: set[int] = set()
            selected_bond_ids: set[int] = set()
            for item in selected:
                kind = item.data(0)
                entity_id = item.data(1)
                if not isinstance(entity_id, int):
                    continue
                if kind == "atom":
                    selected_atoms.add(entity_id)
                elif kind == "bond":
                    bond = bond_for_id(self.canvas, entity_id)
                    if bond is not None:
                        selected_bond_ids.add(entity_id)
            created = []
            if selected_atoms or selected_bond_ids:
                atoms = atoms_for(self.canvas)
                existing = {
                    frozenset(item.data(2)): item
                    for item in restore_ring_projections(
                        scene_render_context_for(self.canvas)
                    )
                }
                atom_selection_bonds = [
                    bond
                    for bond in bonds_for(self.canvas)
                    if bond is not None and {bond.a, bond.b} <= selected_atoms
                ]
                # A complete atom selection OR a complete bond selection qualifies.
                # Combining their endpoints would invent unselected cycle edges.
                selected_rings = find_rings(atom_selection_bonds) + find_rings(
                    bond_for_id(self.canvas, bond_id)
                    for bond_id in sorted(selected_bond_ids)
                )
                unique_rings = {frozenset(ring): ring for ring in selected_rings}
                for ring in unique_rings.values():
                    item = existing.get(frozenset(ring))
                    if item is not None:
                        if item not in targets:
                            targets.append(item)
                    elif alpha > 0:
                        item = create_ring_fill_item_for(
                            self.canvas,
                            [
                                QPointF(atoms[atom_id].x, atoms[atom_id].y)
                                for atom_id in ring
                            ],
                            ring,
                        )
                        item.set_fill(self._pastel_fill(color, min(1.0, float(alpha))))
                        created.append(item)
            if not targets and not created:
                if alpha > 0:
                    notify_error_for(
                        self.canvas,
                        "Ring Fill: select a complete ring (all its atoms or bonds) first.",
                    )
                return

            commands: list[HistoryCommand] = []
            for item in created:
                attach_scene_item(self.canvas, item)
            if created:
                commands.append(
                    AddSceneItemsCommand.from_items(
                        items=created,
                        item_states=[
                            ring_state_dict_for(self.canvas, item) for item in created
                        ],
                    )
                )
            tint = max(0.0, min(1.0, float(alpha)))
            fill = self._pastel_fill(color, tint) if tint > 0 else QColor(color)
            if tint <= 0:
                fill.setAlphaF(0.0)
            for item in targets:
                commands.extend(
                    self._mutate_scene_item(
                        item,
                        ring_state_dict_for,
                        partial(item.set_fill, fill),
                    )
                )
            self._publish(commands)

    def _resolve_ring_structure_targets(self, item) -> tuple[object, ...]:
        ring_atom_ids = item.data(2)
        if not isinstance(ring_atom_ids, list):
            return ()
        atom_ids = {
            atom_id
            for atom_id in ring_atom_ids
            if isinstance(atom_id, int)
            and atom_for_id(self.canvas, atom_id) is not None
        }
        if not atom_ids:
            return ()
        bond_ids, _ = self.graph_service.bond_sets_for_atoms(atom_ids)
        targets: list[object] = []
        for atom_id in sorted(atom_ids):
            atom_item = visible_atom_item_for(self.canvas, atom_id)
            if atom_item is not None:
                targets.append(atom_item)
        for bond_id in sorted(bond_ids):
            bond_items = bond_items_for_id(self.canvas, bond_id)
            if bond_items:
                targets.append(bond_items[0])
        return tuple(targets)
