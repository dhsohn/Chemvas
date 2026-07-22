from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol, cast

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

from chemvas.domain.document import Atom, Bond, MoleculeModel
from chemvas.features.hover import (
    HoverState,
    HoverUpdatePlan,
    plan_structure_hover_update,
)
from chemvas.features.selection import StructureHit
from chemvas.ui.bond_preview_access import (
    bond_hover_endpoint_for,
    build_bond_preview_items_for,
)
from chemvas.ui.canvas_hover_state import hover_state_for as _hover_state_for
from chemvas.ui.canvas_insert_state import insert_state_for
from chemvas.ui.canvas_model_state import model_for
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.hover_rendering import (
    add_hover_preview_items as add_hover_preview_items_to_scene,
)
from chemvas.ui.hover_rendering import (
    build_atom_hover_indicator as build_atom_hover_indicator_item,
)
from chemvas.ui.hover_rendering import (
    build_bond_hover_indicator as build_bond_hover_indicator_item,
)
from chemvas.ui.hover_rendering import clear_hover_items
from chemvas.ui.input_view_access import scene_pos_from_global_pos_for
from chemvas.ui.renderer_style_access import bond_length_px_for
from chemvas.ui.sheet_setup_access import scene_pos_in_sheet_for


class _HoverCanvas(Protocol):
    def scene(self) -> QGraphicsScene | None: ...


class _SelectionController(Protocol):
    def preferred_structure_hit_at_scene_pos(
        self, pos: QPointF
    ) -> StructureHit | None: ...


class _HitTestingService(Protocol):
    def find_atom_near(self, x: float, y: float, max_dist: float) -> int | None: ...


class _InsertController(Protocol):
    def render_template_preview(self, pos: QPointF) -> None: ...

    def render_smiles_preview(self, pos: QPointF) -> None: ...


class _SceneDecorationBuildService(Protocol):
    def build_mark_item(self, kind: str) -> QGraphicsItem | None: ...

    def set_mark_center(self, item: QGraphicsItem, center: QPointF) -> None: ...


class _MarkSceneService(Protocol):
    def mark_center_for_pointer(
        self,
        pos: QPointF,
        atom_id: int | None = None,
        *,
        kind: str | None = None,
    ) -> QPointF: ...


class HoverController:
    def __init__(
        self,
        canvas: _HoverCanvas,
        *,
        selection_controller: _SelectionController,
        hit_testing_service: _HitTestingService,
        insert_controller: _InsertController,
        scene_decoration_build_service: _SceneDecorationBuildService,
        mark_scene_service: _MarkSceneService,
        active_tool_name_provider: Callable[[], str | None],
    ) -> None:
        self.canvas = canvas
        self.selection_controller = selection_controller
        self.hit_testing_service = hit_testing_service
        self.insert_controller = insert_controller
        self.scene_decoration_build_service = scene_decoration_build_service
        self.mark_scene_service = mark_scene_service
        self._active_tool_name = active_tool_name_provider

    def update_hover_highlight(self, pos: QPointF) -> None:
        if not scene_pos_in_sheet_for(self.canvas, pos):
            self.clear_hover_highlight()
            return

        if self._active_tool_name() == "mark":
            self.add_mark_hover_preview(pos)
            return

        has_atoms = bool(self._model().atoms)
        preferred_hit = (
            self.selection_controller.preferred_structure_hit_at_scene_pos(pos)
            if has_atoms
            else None
        )
        free_preview_key = self._free_preview_key(pos)
        atom_preview_signature, atom_preview_key = self._atom_preview(
            pos, preferred_hit
        )
        bond_preview_key = self._bond_preview_key(preferred_hit)
        state = self._state()

        plan = plan_structure_hover_update(
            has_atoms=has_atoms,
            current_hover_atom_id=state.atom_id,
            current_hover_bond_id=state.bond_id,
            current_preview_key=state.style,
            preferred_hit=preferred_hit,
            free_preview_key=free_preview_key,
            atom_preview_signature=atom_preview_signature,
            atom_preview_key=atom_preview_key,
            bond_preview_key=bond_preview_key,
        )
        self._apply_plan(plan, pos)

    def clear_hover_highlight(self) -> None:
        state = self._state()
        items = [cast(QGraphicsItem, item) for item in state.items]
        clear_hover_items(self._scene(), items)
        state.items.clear()
        state.atom_id = None
        state.bond_id = None
        state.style = None

    def add_hover_preview_items(self, items: Sequence[QGraphicsItem]) -> None:
        if not items:
            return
        state = self._state()
        state.items.extend(add_hover_preview_items_to_scene(self._scene(), items))

    def add_atom_hover_indicator(self, atom_id: int) -> None:
        atom = self._atom_for_id(atom_id)
        if atom is None:
            return
        radius = bond_length_px_for(self.canvas) * 0.25
        indicator = build_atom_hover_indicator_item(QPointF(atom.x, atom.y), radius)
        self._scene().addItem(indicator)
        self._state().items.append(indicator)

    def add_bond_hover_indicator(self, bond_id: int | None) -> None:
        bond = self._bond_for_id(bond_id)
        if bond is None:
            return
        start_atom = self._atom_for_id(bond.a)
        end_atom = self._atom_for_id(bond.b)
        if start_atom is None or end_atom is None:
            return
        radius = bond_length_px_for(self.canvas) * 0.22
        indicator = build_bond_hover_indicator_item(
            QPointF(start_atom.x, start_atom.y),
            QPointF(end_atom.x, end_atom.y),
            radius,
        )
        self._scene().addItem(indicator)
        self._state().items.append(indicator)

    def add_bond_style_hover_preview(self, bond: Bond) -> None:
        if self._active_tool_name() != "bond":
            return
        style = tool_settings_state_for(self.canvas).active_bond_style
        if style not in {"wedge", "hash"}:
            return
        atom_a = self._atom_for_id(bond.a)
        atom_b = self._atom_for_id(bond.b)
        if atom_a is None or atom_b is None:
            return
        self._state().style = style
        self.add_hover_preview_items(
            build_bond_preview_items_for(
                self.canvas,
                QPointF(atom_a.x, atom_a.y),
                QPointF(atom_b.x, atom_b.y),
                bond.a,
                bond.b,
            )
        )

    def add_bond_tool_hover_preview(self, atom_id: int, pos: QPointF) -> None:
        if self._active_tool_name() != "bond":
            return
        atom = self._atom_for_id(atom_id)
        if atom is None:
            return
        start = QPointF(atom.x, atom.y)
        end = bond_hover_endpoint_for(self.canvas, start, pos, atom_id)
        self.add_hover_preview_items(
            build_bond_preview_items_for(self.canvas, start, end, atom_id, None)
        )

    def add_free_bond_hover_preview(self, pos: QPointF) -> None:
        start = QPointF(pos)
        end = QPointF(pos.x() + bond_length_px_for(self.canvas), pos.y())
        self.add_hover_preview_items(
            build_bond_preview_items_for(self.canvas, start, end)
        )

    def add_mark_hover_preview(self, pos: QPointF) -> None:
        atom_id = self.hit_testing_service.find_atom_near(
            pos.x(),
            pos.y(),
            bond_length_px_for(self.canvas) * 0.35,
        )
        kind = tool_settings_state_for(self.canvas).mark_kind
        center = self.mark_scene_service.mark_center_for_pointer(
            pos, atom_id, kind=kind
        )
        scope = f"atom:{atom_id}" if atom_id is not None else "free"
        preview_key = (
            f"mark:{kind}:{scope}:{round(center.x(), 1)}:{round(center.y(), 1)}"
        )
        state = self._state()
        if atom_id == state.atom_id and preview_key == state.style:
            return
        self.clear_hover_highlight()
        if atom_id is not None:
            state.atom_id = atom_id
            self.add_atom_hover_indicator(atom_id)
        item = self.scene_decoration_build_service.build_mark_item(kind)
        if item is None:
            return
        self.scene_decoration_build_service.set_mark_center(item, center)
        state.style = preview_key
        self.add_hover_preview_items([item])

    def refresh(self, *, render_insert_preview: bool = False) -> None:
        scene_pos = scene_pos_from_global_pos_for(self.canvas, QCursor.pos())
        insert_state = insert_state_for(self.canvas)
        if insert_state.template_active or insert_state.smiles_active:
            self.clear_hover_highlight()
            if scene_pos is not None and render_insert_preview:
                if insert_state.template_active:
                    self.insert_controller.render_template_preview(scene_pos)
                elif insert_state.smiles_active:
                    self.insert_controller.render_smiles_preview(scene_pos)
            return
        if scene_pos is not None:
            self.update_hover_highlight(scene_pos)
            return
        self.clear_hover_highlight()

    def _scene(self) -> QGraphicsScene:
        scene = self.canvas.scene()
        if scene is None:
            raise RuntimeError("HoverController requires an attached QGraphicsScene")
        return scene

    def _model(self) -> MoleculeModel:
        return cast(MoleculeModel, model_for(self.canvas))

    def _state(self) -> HoverState:
        return cast(HoverState, _hover_state_for(self.canvas))

    def _atom_for_id(self, atom_id: int | None) -> Atom | None:
        if atom_id is None:
            return None
        return self._model().atoms.get(atom_id)

    def _bond_for_id(self, bond_id: int | None) -> Bond | None:
        if bond_id is None or bond_id < 0:
            return None
        try:
            return self._model().bonds[bond_id]
        except IndexError:
            return None

    def _bond_preview_signature(self) -> str | None:
        if self._active_tool_name() != "bond":
            return None
        settings = tool_settings_state_for(self.canvas)
        return f"{settings.active_bond_style}:{settings.active_bond_order}"

    def _free_preview_key(self, pos: QPointF) -> str | None:
        preview_signature = self._bond_preview_signature()
        if preview_signature is None:
            return None
        return f"{preview_signature}:{round(pos.x(), 1)}:{round(pos.y(), 1)}"

    def _atom_preview(
        self, pos: QPointF, preferred_hit: StructureHit | None
    ) -> tuple[str | None, str | None]:
        if (
            preferred_hit is None
            or preferred_hit.kind != "atom"
            or not isinstance(preferred_hit.id, int)
        ):
            return None, None
        preview_signature = self._bond_preview_signature()
        if preview_signature is None:
            return None, None
        atom = self._atom_for_id(preferred_hit.id)
        if atom is None:
            return preview_signature, None
        end = bond_hover_endpoint_for(
            self.canvas,
            QPointF(atom.x, atom.y),
            pos,
            preferred_hit.id,
        )
        return (
            preview_signature,
            f"{preview_signature}:{round(end.x(), 1)}:{round(end.y(), 1)}",
        )

    def _bond_preview_key(self, preferred_hit: StructureHit | None) -> str | None:
        if (
            preferred_hit is None
            or preferred_hit.kind != "bond"
            or not isinstance(preferred_hit.id, int)
            or self._active_tool_name() != "bond"
        ):
            return None
        active_bond_style = tool_settings_state_for(self.canvas).active_bond_style
        if active_bond_style not in {"wedge", "hash"}:
            return None
        return active_bond_style

    def _apply_plan(self, plan: HoverUpdatePlan, pos: QPointF) -> None:
        if plan.action == "noop":
            return
        if plan.action == "clear":
            self.clear_hover_highlight()
            return
        if plan.action == "free_bond_preview":
            self.clear_hover_highlight()
            self._state().style = plan.preview_key
            self.add_free_bond_hover_preview(pos)
            return
        if plan.action == "atom_hit":
            atom_id = plan.hover_atom_id
            if atom_id is None:
                self.clear_hover_highlight()
                return
            self.clear_hover_highlight()
            self._state().atom_id = atom_id
            self.add_atom_hover_indicator(atom_id)
            if plan.preview_key is not None:
                self._state().style = plan.preview_key
                self.add_bond_tool_hover_preview(atom_id, pos)
            return

        self.clear_hover_highlight()
        bond_id = plan.hover_bond_id
        if bond_id is None:
            return
        self._state().bond_id = bond_id
        bond = self._bond_for_id(bond_id)
        if bond is None:
            return
        self.add_bond_hover_indicator(bond_id)
        if plan.preview_key is not None:
            self.add_bond_style_hover_preview(bond)


def build_hover_controller(
    canvas: _HoverCanvas,
    *,
    selection_controller: _SelectionController,
    hit_testing_service: _HitTestingService,
    insert_controller: _InsertController,
    scene_decoration_build_service: _SceneDecorationBuildService,
    mark_scene_service: _MarkSceneService,
    active_tool_name_provider: Callable[[], str | None],
) -> HoverController:
    return HoverController(
        canvas,
        selection_controller=selection_controller,
        hit_testing_service=hit_testing_service,
        insert_controller=insert_controller,
        scene_decoration_build_service=scene_decoration_build_service,
        mark_scene_service=mark_scene_service,
        active_tool_name_provider=active_tool_name_provider,
    )


__all__ = [
    "HoverController",
    "build_hover_controller",
]
