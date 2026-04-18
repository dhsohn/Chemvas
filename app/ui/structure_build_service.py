from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from ui.atom_label_access import add_or_update_atom_label
from ui.bond_style_logic import style_for_existing_bond_overlay
from ui.scene_item_access import attach_scene_item
from ui.structure_benzene_logic import plan_benzene_ring_points
from ui.structure_growth_logic import (
    alternating_ring_bond_specs,
    crown_ether_elements,
    fused_benzene_centers,
    mirrored_local_points,
    other_atom_id_from_bond_result,
    resolve_bond_placement_context,
)
from ui.structure_geometry_logic import compute_free_benzene_ring_points

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class StructureBuildService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def viewport_center(self) -> QPointF:
        return self.canvas.mapToScene(self.canvas.viewport().rect().center())

    def run_recorded_build(
        self,
        action: Callable[[], list | None],
        *,
        before_smiles_input: str | None = None,
    ) -> list:
        if before_smiles_input is None:
            before_smiles_input = self.canvas.last_smiles_input
        before_next_atom_id = self.canvas.model.next_atom_id
        before_bond_count = len(self.canvas.model.bonds)
        self.canvas.last_smiles_input = None
        added_scene_items = action() or []
        self.canvas._record_additions(
            before_next_atom_id=before_next_atom_id,
            before_bond_count=before_bond_count,
            before_smiles_input=before_smiles_input,
            added_scene_items=added_scene_items,
        )
        return added_scene_items

    def _run_recorded_additions_action(
        self,
        action: Callable[[], bool],
        *,
        before_smiles_input: str | None = None,
    ) -> bool:
        if before_smiles_input is None:
            before_smiles_input = self.canvas.last_smiles_input
        before_next_atom_id = self.canvas.model.next_atom_id
        before_bond_count = len(self.canvas.model.bonds)
        self.canvas.last_smiles_input = None
        if not action():
            return False
        self.canvas._record_additions(
            before_next_atom_id=before_next_atom_id,
            before_bond_count=before_bond_count,
            before_smiles_input=before_smiles_input,
        )
        return True

    def add_regular_ring_template(self, n: int) -> None:
        center = self.viewport_center()
        radius = self.canvas._regular_ring_radius(n)
        self.add_ring_from_points(self.canvas._ring_points(center, n, radius=radius))

    def add_hetero_ring_template(self, n: int, elements: list[str]) -> None:
        center = self.viewport_center()
        radius = self.canvas._regular_ring_radius(n)
        self.add_ring_from_points(self.canvas._ring_points(center, n, radius=radius), elements=elements)

    def add_fused_benzenes(self, count: int, mode: str = "linear") -> None:
        center = self.viewport_center()
        step = self.canvas.renderer.style.bond_length_px * 1.5
        merge = []
        for ring_center in fused_benzene_centers(center, step, count, mode):
            self.add_ring_from_points(self.canvas._ring_points(ring_center, 6), merge=merge)

    def add_crown_ether(self, atoms: int, oxygens: int) -> None:
        center = self.viewport_center()
        points = self.canvas._ring_points(center, atoms, radius=self.canvas.renderer.style.bond_length_px * 1.4)
        self.add_ring_from_points(points, elements=crown_ether_elements(atoms, oxygens))

    def add_cyclohexane_chair(self) -> None:
        def _build() -> None:
            center = self.viewport_center()
            self.add_ring_from_points(self.canvas._cyclohexane_chair_points(center))

        self.run_recorded_build(_build)

    def add_cyclohexane_boat(self) -> None:
        def _build() -> None:
            center = self.viewport_center()
            self.add_ring_from_points(self.canvas._cyclohexane_boat_points(center))

        self.run_recorded_build(_build)

    def add_indole(self) -> None:
        self.run_recorded_build(
            lambda: self._add_fused_heterocycle_template(
                ring_size=5,
                elements=["N", "C", "C", "C", "C"],
                x_scale=1.1,
                y_scale=0.6,
            )
        )

    def add_quinoline(self) -> None:
        self.run_recorded_build(
            lambda: self._add_fused_heterocycle_template(
                ring_size=6,
                elements=["N", "C", "C", "C", "C", "C"],
                x_scale=1.5,
            )
        )

    def add_isoquinoline(self) -> None:
        self.run_recorded_build(
            lambda: self._add_fused_heterocycle_template(
                ring_size=6,
                elements=["C", "C", "C", "C", "N", "C"],
                x_scale=1.5,
            )
        )

    def add_benzimidazole(self) -> None:
        self.run_recorded_build(
            lambda: self._add_fused_heterocycle_template(
                ring_size=5,
                elements=["N", "C", "N", "C", "C"],
                x_scale=1.1,
                y_scale=0.6,
            )
        )

    def add_phenyl(self) -> None:
        def _build() -> None:
            center = self.viewport_center()
            atom_ids = self.add_ring_from_points(self.canvas._ring_points(center, 6))
            attach = QPointF(center.x() - self.canvas.renderer.style.bond_length_px * 2.0, center.y())
            attach_id = self.canvas.add_atom("C", attach.x(), attach.y())
            self.canvas.add_bond(atom_ids[0], attach_id)
            self.canvas._add_bond_graphics(len(self.canvas.model.bonds) - 1)

        self.run_recorded_build(_build)

    def add_benzyl(self) -> None:
        def _build() -> None:
            center = self.viewport_center()
            atom_ids = self.add_ring_from_points(self.canvas._ring_points(center, 6))
            start = QPointF(center.x() - self.canvas.renderer.style.bond_length_px * 2.0, center.y())
            mid = QPointF(start.x() - self.canvas.renderer.style.bond_length_px, start.y())
            chain_ids = self.add_linear_chain([start, mid], ["C", "C"], [1])
            self.canvas.add_bond(atom_ids[0], chain_ids[0])
            self.canvas._add_bond_graphics(len(self.canvas.model.bonds) - 1)

        self.run_recorded_build(_build)

    def add_vinyl(self) -> None:
        def _build() -> None:
            center = self.viewport_center()
            p1 = QPointF(center.x() - self.canvas.renderer.style.bond_length_px, center.y())
            p2 = QPointF(center.x(), center.y())
            self.add_linear_chain([p1, p2], ["C", "C"], [2])

        self.run_recorded_build(_build)

    def add_allyl(self) -> None:
        def _build() -> None:
            center = self.viewport_center()
            step = self.canvas.renderer.style.bond_length_px
            points = [
                QPointF(center.x() - step, center.y()),
                QPointF(center.x(), center.y()),
                QPointF(center.x() + step, center.y()),
            ]
            self.add_linear_chain(points, ["C", "C", "C"], [2, 1])

        self.run_recorded_build(_build)

    def add_carboxyl(self) -> None:
        def _build() -> None:
            center = self.viewport_center()
            step = self.canvas.renderer.style.bond_length_px
            carbon = QPointF(center.x(), center.y())
            oxygen_upper = QPointF(center.x() + step, center.y() - step * 0.6)
            oxygen_lower = QPointF(center.x() + step, center.y() + step * 0.6)
            self.add_linear_chain([carbon, oxygen_upper], ["C", "O"], [2])
            self.add_linear_chain([carbon, oxygen_lower], ["C", "O"], [1])

        self.run_recorded_build(_build)

    def add_nitro(self) -> None:
        def _build() -> None:
            center = self.viewport_center()
            step = self.canvas.renderer.style.bond_length_px
            nitrogen = QPointF(center.x(), center.y())
            oxygen_upper = QPointF(center.x() + step, center.y() - step * 0.6)
            oxygen_lower = QPointF(center.x() + step, center.y() + step * 0.6)
            self.add_linear_chain([nitrogen, oxygen_upper], ["N", "O"], [2])
            self.add_linear_chain([nitrogen, oxygen_lower], ["N", "O"], [2])

        self.run_recorded_build(_build)

    def add_sulfonyl(self) -> None:
        def _build() -> None:
            center = self.viewport_center()
            step = self.canvas.renderer.style.bond_length_px
            sulfur = QPointF(center.x(), center.y())
            oxygen_upper = QPointF(center.x() + step, center.y() - step * 0.7)
            oxygen_lower = QPointF(center.x() + step, center.y() + step * 0.7)
            self.add_linear_chain([sulfur, oxygen_upper], ["S", "O"], [2])
            self.add_linear_chain([sulfur, oxygen_lower], ["S", "O"], [2])

        self.run_recorded_build(_build)

    def add_carbonyl(self) -> None:
        def _build() -> None:
            center = self.viewport_center()
            step = self.canvas.renderer.style.bond_length_px
            carbon = QPointF(center.x(), center.y())
            oxygen = QPointF(center.x() + step, center.y())
            self.add_linear_chain([carbon, oxygen], ["C", "O"], [2])

        self.run_recorded_build(_build)

    def add_tbu(self) -> None:
        def _build() -> None:
            center = self.viewport_center()
            step = self.canvas.renderer.style.bond_length_px
            carbon = QPointF(center.x(), center.y())
            branches = [
                QPointF(center.x() + step, center.y()),
                QPointF(center.x() - step, center.y()),
                QPointF(center.x(), center.y() - step),
            ]
            for branch in branches:
                self.add_linear_chain([carbon, branch], ["C", "C"], [1])

        self.run_recorded_build(_build)

    def add_ipr(self) -> None:
        def _build() -> None:
            center = self.viewport_center()
            step = self.canvas.renderer.style.bond_length_px
            carbon = QPointF(center.x(), center.y())
            branch_right = QPointF(center.x() + step, center.y())
            branch_up = QPointF(center.x(), center.y() - step)
            self.add_linear_chain([carbon, branch_right], ["C", "C"], [1])
            self.add_linear_chain([carbon, branch_up], ["C", "C"], [1])

        self.run_recorded_build(_build)

    def add_me(self) -> None:
        def _build() -> None:
            self.add_linear_chain([self.viewport_center()], ["C"], [])

        self.run_recorded_build(_build)

    def add_et(self) -> None:
        def _build() -> None:
            center = self.viewport_center()
            step = self.canvas.renderer.style.bond_length_px
            p1 = QPointF(center.x() - step / 2, center.y())
            p2 = QPointF(center.x() + step / 2, center.y())
            self.add_linear_chain([p1, p2], ["C", "C"], [1])

        self.run_recorded_build(_build)

    def add_peptide_2(self) -> None:
        def _build() -> None:
            center = self.viewport_center()
            step = self.canvas.renderer.style.bond_length_px
            points = [
                QPointF(center.x() - step * 2, center.y()),
                QPointF(center.x() - step, center.y()),
                QPointF(center.x(), center.y()),
                QPointF(center.x() + step, center.y()),
                QPointF(center.x() + step * 2, center.y()),
                QPointF(center.x() + step * 3, center.y()),
            ]
            chain_ids = self.add_linear_chain(
                points,
                ["N", "C", "C", "N", "C", "C"],
                [1, 1, 1, 1, 1],
            )
            oxygen_1 = QPointF(points[1].x(), points[1].y() - step * 0.8)
            oxygen_2 = QPointF(points[4].x(), points[4].y() - step * 0.8)
            oxygen_1_id = self.canvas.add_atom("O", oxygen_1.x(), oxygen_1.y())
            oxygen_2_id = self.canvas.add_atom("O", oxygen_2.x(), oxygen_2.y())
            self.canvas.add_bond(chain_ids[1], oxygen_1_id, 2)
            self.canvas.add_bond(chain_ids[4], oxygen_2_id, 2)
            self.canvas._add_bond_graphics(len(self.canvas.model.bonds) - 2)
            self.canvas._add_bond_graphics(len(self.canvas.model.bonds) - 1)
            self.canvas._atom_label_service.add_or_update_atom_label(oxygen_1_id, "O", record=False)
            self.canvas._atom_label_service.add_or_update_atom_label(oxygen_2_id, "O", record=False)

        self.run_recorded_build(_build)

    def _add_fused_heterocycle_template(
        self,
        *,
        ring_size: int,
        elements: list[str],
        x_scale: float,
        y_scale: float = 0.0,
    ) -> None:
        center = self.viewport_center()
        merge: list[tuple[int, float, float]] = []
        self.add_ring_from_points(self.canvas._ring_points(center, 6), merge=merge)
        other_center = QPointF(
            center.x() + self.canvas.renderer.style.bond_length_px * x_scale,
            center.y() + self.canvas.renderer.style.bond_length_px * y_scale,
        )
        self.add_ring_from_points(
            self.canvas._ring_points(other_center, ring_size),
            elements=elements,
            merge=merge,
        )

    def sprout_bond_from_atom(
        self,
        atom_id: int,
        *,
        style: str,
        order: int,
        cyclic: bool = False,
    ) -> tuple[int, int] | None:
        start = self.canvas._atom_point(atom_id)
        end = self.canvas._sprout_bond_endpoint(atom_id, cyclic=cyclic)
        if end is None:
            return None
        return self.add_bond_between_points(start, end, style, order)

    def sprout_benzene_from_atom(self, atom_id: int) -> object | None:
        return self.add_benzene_ring(self.canvas._atom_point(atom_id), attach_atom_id=atom_id)

    def sprout_acetyl_from_atom(self, atom_id: int) -> None:
        start = self.canvas._atom_point(atom_id)
        carbon_end = self.canvas._sprout_bond_endpoint(atom_id, cyclic=False)
        if carbon_end is None:
            return
        result = self.add_bond_between_points(start, carbon_end, "single", 1)
        carbon_id = other_atom_id_from_bond_result(atom_id, result)
        if carbon_id not in self.canvas.model.atoms:
            return
        carbon_point = self.canvas._atom_point(carbon_id)
        oxygen_end = self.canvas._default_bond_endpoint(carbon_point, carbon_id)
        result = self.add_bond_between_points(carbon_point, oxygen_end, "double", 2)
        oxygen_id = other_atom_id_from_bond_result(carbon_id, result)
        if oxygen_id in self.canvas.model.atoms:
            add_or_update_atom_label(self.canvas, oxygen_id, "O", show_carbon=True)
        methyl_end = self.canvas._default_bond_endpoint(carbon_point, carbon_id)
        self.add_bond_between_points(carbon_point, methyl_end, "single", 1)

    def sprout_regular_ring_from_atom(self, atom_id: int, n: int) -> None:
        def _build() -> bool:
            result = self.canvas._regular_ring_points_for_atom(n, atom_id)
            if result is None:
                return False
            points, merge = result
            self.add_ring_from_points(points, merge=merge)
            return True

        self._run_recorded_additions_action(_build)

    def fuse_regular_ring_to_bond(self, bond_id: int, n: int) -> None:
        def _build() -> bool:
            placement = resolve_bond_placement_context(
                bond_id,
                bonds=self.canvas.model.bonds,
                atoms=self.canvas.model.atoms,
            )
            if placement is None:
                return False
            result = self.canvas._regular_ring_points_for_bond(n, bond_id, placement.midpoint)
            if result is None:
                return False
            points, merge = result
            self.add_ring_from_points(points, merge=merge)
            return True

        self._run_recorded_additions_action(_build)

    def fuse_chair_to_bond(self, bond_id: int, mirrored: bool = False) -> None:
        def _build() -> bool:
            local_center = QPointF(0.0, 0.0)
            points_local = mirrored_local_points(self.canvas._cyclohexane_chair_points(local_center), mirrored)
            placement = resolve_bond_placement_context(
                bond_id,
                bonds=self.canvas.model.bonds,
                atoms=self.canvas.model.atoms,
            )
            if placement is None:
                return False
            result = self.canvas._template_points_for_bond(points_local, bond_id, placement.midpoint)
            if result is None:
                return False
            points, merge = result
            self.add_ring_from_points(points, merge=merge)
            return True

        self._run_recorded_additions_action(_build)

    def fuse_benzene_to_bond(self, bond_id: int) -> object | None:
        placement = resolve_bond_placement_context(
            bond_id,
            bonds=self.canvas.model.bonds,
            atoms=self.canvas.model.atoms,
        )
        if placement is None:
            return None
        return self.add_benzene_ring(placement.midpoint, attach_bond_id=bond_id)

    def add_bond_between_points(
        self,
        start: QPointF,
        end: QPointF,
        style: str,
        order: int,
    ) -> tuple[int, int] | None:
        if start == end:
            return None
        before_smiles_input = self.canvas.last_smiles_input
        before_next_atom_id = self.canvas.model.next_atom_id
        before_bond_count = len(self.canvas.model.bonds)
        self.canvas.last_smiles_input = None
        snap_tol = self.canvas.renderer.style.bond_length_px * 0.1
        start_id = self.canvas.find_atom_near(start.x(), start.y(), snap_tol)
        if start_id is None:
            start_id = self.canvas.add_atom("C", start.x(), start.y())
        end_id = self.canvas.find_atom_near(end.x(), end.y(), snap_tol)
        if end_id is None:
            end_id = self.canvas.add_atom("C", end.x(), end.y())
        if start_id == end_id:
            return None
        existing_bond_id = self.canvas._bond_id_between(start_id, end_id)
        if existing_bond_id is not None:
            bond = self.canvas.model.bonds[existing_bond_id]
            if bond is None:
                return None
            before_state = self.canvas._bond_state_dict(bond)
            next_style, next_order = style_for_existing_bond_overlay(
                bond.style,
                bond.order,
                style,
                order,
            )
            bond.style = next_style
            bond.order = next_order
            self.canvas._redraw_bond(existing_bond_id)
            self.canvas._redraw_connected_bonds(bond.a, skip_bond_id=existing_bond_id)
            self.canvas._redraw_connected_bonds(bond.b, skip_bond_id=existing_bond_id)
            after_state = self.canvas._bond_state_dict(bond)
            self.canvas._record_bond_update(
                existing_bond_id,
                before_state,
                after_state,
                before_smiles_input,
                self.canvas.last_smiles_input,
            )
            return start_id, end_id
        bond_id = self.canvas.add_bond(start_id, end_id, order)
        bond = self.canvas.model.bonds[bond_id]
        if bond is None:
            return None
        bond.style = style
        self.canvas._add_bond_graphics(bond_id)
        self.canvas._redraw_connected_bonds(start_id, skip_bond_id=bond_id)
        self.canvas._redraw_connected_bonds(end_id, skip_bond_id=bond_id)
        self.canvas._record_additions(
            before_next_atom_id=before_next_atom_id,
            before_bond_count=before_bond_count,
            before_smiles_input=before_smiles_input,
        )
        return start_id, end_id

    def benzene_ring_points(
        self,
        center: QPointF,
        attach_atom_id: int | None = None,
        attach_bond_id: int | None = None,
    ) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
        return plan_benzene_ring_points(
            center,
            attach_atom_id=attach_atom_id,
            attach_bond_id=attach_bond_id,
            bonds=self.canvas.model.bonds,
            atoms=self.canvas.model.atoms,
            ring_items=self.canvas.ring_items,
            bond_length=self.canvas.renderer.style.bond_length_px,
            regular_ring_points_for_bond=self.canvas._regular_ring_points_for_bond,
            regular_ring_points_for_atom=self.canvas._regular_ring_points_for_atom,
            compute_free_points=compute_free_benzene_ring_points,
        )

    def add_benzene_ring(
        self,
        center: QPointF,
        attach_atom_id: int | None = None,
        attach_bond_id: int | None = None,
        *,
        before_smiles_input: str | None = None,
    ) -> object | None:
        built_ring_item = None

        def _build():
            nonlocal built_ring_item
            result = self.benzene_ring_points(center, attach_atom_id, attach_bond_id)
            if result is None:
                return []
            points, merge = result

            atom_ids: list[int] = []
            for point in points:
                atom_ids.append(self.add_atom_with_merge(point, "C", merge))

            bonds_start = len(self.canvas.model.bonds)
            for a_id, b_id, order in alternating_ring_bond_specs(atom_ids):
                if self.canvas._bond_exists(a_id, b_id):
                    continue
                self.canvas.add_bond(a_id, b_id, order)

            built_ring_item = self.canvas._create_ring_fill_item(points, atom_ids)
            attach_scene_item(self.canvas, built_ring_item)

            for bond_id in range(bonds_start, len(self.canvas.model.bonds)):
                self.canvas._add_bond_graphics(bond_id)
            return [built_ring_item]

        self.run_recorded_build(_build, before_smiles_input=before_smiles_input)
        return built_ring_item

    def add_ring_from_points(
        self,
        points,
        elements: list[str] | None = None,
        merge: list | None = None,
    ) -> list[int]:
        merge = merge or []
        atom_ids = []
        for idx, point in enumerate(points):
            element = elements[idx] if elements else "C"
            atom_id = self.add_atom_with_merge(point, element, merge)
            atom_ids.append(atom_id)
        bonds_start = len(self.canvas.model.bonds)
        for i in range(len(atom_ids)):
            self.canvas.add_bond(atom_ids[i], atom_ids[(i + 1) % len(atom_ids)])
        for bond_id in range(bonds_start, len(self.canvas.model.bonds)):
            self.canvas._add_bond_graphics(bond_id)
        for atom_id, element in zip(atom_ids, elements or ["C"] * len(atom_ids)):
            if element != "C":
                atom = self.canvas.model.atoms[atom_id]
                add_or_update_atom_label(
                    self.canvas,
                    atom_id,
                    atom.element,
                    record=False,
                )
        return atom_ids

    def add_atom_with_merge(self, point: QPointF, element: str, merge: list) -> int:
        tol = self.canvas.renderer.style.bond_length_px * 0.2
        for entry in merge:
            atom_id, x, y = entry
            if abs(point.x() - x) < tol and abs(point.y() - y) < tol:
                return atom_id
        atom_id = self.canvas.add_atom(element, point.x(), point.y())
        merge.append((atom_id, point.x(), point.y()))
        return atom_id

    def add_linear_chain(self, points: list[QPointF], elements: list[str], bonds: list[int]):
        atom_ids = []
        for point, element in zip(points, elements):
            atom_ids.append(self.canvas.add_atom(element, point.x(), point.y()))
        bonds_start = len(self.canvas.model.bonds)
        for i, order in enumerate(bonds):
            self.canvas.add_bond(atom_ids[i], atom_ids[i + 1], order)
        for bond_id in range(bonds_start, len(self.canvas.model.bonds)):
            self.canvas._add_bond_graphics(bond_id)
        for atom_id, element in zip(atom_ids, elements):
            if element != "C":
                add_or_update_atom_label(self.canvas, atom_id, element, record=False)
        return atom_ids

    def render_model(self) -> None:
        for bond_id, bond in enumerate(self.canvas.model.bonds):
            if bond is None:
                continue
            self.canvas._add_bond_graphics(bond_id)

        for atom_id, atom in self.canvas.model.atoms.items():
            if atom.element == "C":
                if atom.explicit_label:
                    add_or_update_atom_label(
                        self.canvas,
                        atom_id,
                        atom.element,
                        clear_smiles=False,
                        record=False,
                        show_carbon=True,
                    )
                else:
                    self.canvas._ensure_carbon_dot(atom_id)
            else:
                add_or_update_atom_label(
                    self.canvas,
                    atom_id,
                    atom.element,
                    clear_smiles=False,
                    record=False,
                )


__all__ = ["StructureBuildService"]
