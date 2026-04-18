from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from ui.atom_label_access import add_or_update_atom_label
from ui.smiles_insert_logic import SmilesCommitPlan
from ui.template_insert_logic import TemplateInsertPlan, TemplateInsertRequest, TemplateInsertResolution

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


@dataclass(slots=True)
class InsertCommitService:
    canvas: CanvasView

    def apply_smiles_commit(
        self,
        plan: SmilesCommitPlan | None,
        *,
        before_smiles_input: str | None = None,
        after_smiles_input: str | None,
    ) -> bool:
        return apply_smiles_commit_plan(
            self.canvas,
            plan,
            before_smiles_input=self.canvas.last_smiles_input if before_smiles_input is None else before_smiles_input,
            after_smiles_input=after_smiles_input,
        )

    def apply_smiles_commit_plan(
        self,
        plan: SmilesCommitPlan | None,
        *,
        before_smiles_input: str | None,
        after_smiles_input: str | None,
    ) -> bool:
        return apply_smiles_commit_plan(
            self.canvas,
            plan,
            before_smiles_input=before_smiles_input,
            after_smiles_input=after_smiles_input,
        )

    def apply_template_commit(
        self,
        pos: QPointF,
        *,
        request: TemplateInsertRequest,
        plan: TemplateInsertPlan,
        resolution: TemplateInsertResolution | None,
        before_smiles_input: str | None = None,
        after_smiles_input: str | None = None,
    ) -> bool:
        if request.cursor_pos != (pos.x(), pos.y()):
            request = TemplateInsertRequest(
                ring_size=request.ring_size,
                cursor_pos=(pos.x(), pos.y()),
                bond_id=request.bond_id,
                ring_style=request.ring_style,
            )
        return apply_template_commit_resolution(
            self.canvas,
            request,
            plan,
            resolution,
            before_smiles_input=self.canvas.last_smiles_input if before_smiles_input is None else before_smiles_input,
            after_smiles_input=after_smiles_input,
        )

    def apply_template_commit_resolution(
        self,
        request: TemplateInsertRequest,
        plan: TemplateInsertPlan,
        resolution: TemplateInsertResolution | None,
        *,
        before_smiles_input: str | None,
        after_smiles_input: str | None = None,
    ) -> bool:
        return apply_template_commit_resolution(
            self.canvas,
            request,
            plan,
            resolution,
            before_smiles_input=before_smiles_input,
            after_smiles_input=after_smiles_input,
        )

    def _bond_merge_seed(self, bond_id: int | None) -> list[tuple[int, float, float]]:
        if bond_id is None:
            return []
        return _bond_merge_seed(self.canvas, bond_id)


def apply_smiles_commit_plan(
    canvas: CanvasView,
    plan: SmilesCommitPlan | None,
    *,
    before_smiles_input: str | None,
    after_smiles_input: str | None,
) -> bool:
    if plan is None or not plan.atoms:
        return False
    source_atom_ids = {atom.source_atom_id for atom in plan.atoms}
    if len(source_atom_ids) != len(plan.atoms):
        return False
    for bond_plan in plan.bonds:
        if bond_plan.source_a not in source_atom_ids or bond_plan.source_b not in source_atom_ids:
            return False

    before_next_atom_id = canvas.model.next_atom_id
    before_bond_count = len(canvas.model.bonds)

    id_map: dict[int, int] = {}
    for atom_plan in plan.atoms:
        new_id = canvas.add_atom(atom_plan.element, atom_plan.x, atom_plan.y)
        canvas.model.atoms[new_id].color = atom_plan.color
        canvas.model.atoms[new_id].explicit_label = atom_plan.explicit_label
        id_map[atom_plan.source_atom_id] = new_id

    bonds_start = len(canvas.model.bonds)
    for bond_plan in plan.bonds:
        a_id = id_map.get(bond_plan.source_a)
        b_id = id_map.get(bond_plan.source_b)
        if a_id is None or b_id is None:
            return False
        canvas.add_bond(a_id, b_id, bond_plan.order)
        created = canvas.model.bonds[-1]
        created.style = bond_plan.style
        created.color = bond_plan.color

    for new_bond_id in range(bonds_start, len(canvas.model.bonds)):
        canvas._add_bond_graphics(new_bond_id)

    for new_id in id_map.values():
        atom = canvas.model.atoms[new_id]
        if atom.element == "C" and not atom.explicit_label:
            canvas._ensure_carbon_dot(new_id)
        else:
            add_or_update_atom_label(
                canvas,
                new_id,
                atom.element,
                clear_smiles=False,
                record=False,
            )

    canvas.last_smiles_input = after_smiles_input
    canvas._record_additions(
        before_next_atom_id=before_next_atom_id,
        before_bond_count=before_bond_count,
        before_smiles_input=before_smiles_input,
    )
    return True


def apply_template_commit_resolution(
    canvas: CanvasView,
    request: TemplateInsertRequest,
    plan: TemplateInsertPlan,
    resolution: TemplateInsertResolution | None,
    *,
    before_smiles_input: str | None,
    after_smiles_input: str | None = None,
) -> bool:
    if plan.generator == "benzene":
        center = QPointF(*request.cursor_pos)
        before_next_atom_id = canvas.model.next_atom_id
        before_bond_count = len(canvas.model.bonds)
        canvas.last_smiles_input = after_smiles_input
        canvas.add_benzene_ring(
            center,
            attach_bond_id=plan.bond_id,
            before_smiles_input=before_smiles_input,
        )
        return canvas.model.next_atom_id != before_next_atom_id or len(canvas.model.bonds) != before_bond_count

    if resolution is None or resolution.points is None:
        return False

    points = [QPointF(x, y) for x, y in resolution.points]
    before_next_atom_id = canvas.model.next_atom_id
    before_bond_count = len(canvas.model.bonds)
    canvas.last_smiles_input = after_smiles_input

    if plan.generator in {"bond_regular_ring", "bond_template_shape"}:
        if plan.bond_id is None:
            return False
        merge = _bond_merge_seed(canvas, plan.bond_id)
        atom_ids: list[int] = []
        for point in points:
            atom_ids.append(canvas._add_atom_with_merge(point, "C", merge))
        bonds_start = len(canvas.model.bonds)
        for index in range(len(atom_ids)):
            a_id = atom_ids[index]
            b_id = atom_ids[(index + 1) % len(atom_ids)]
            if canvas._bond_exists(a_id, b_id):
                continue
            canvas.add_bond(a_id, b_id)
        for new_bond_id in range(bonds_start, len(canvas.model.bonds)):
            canvas._add_bond_graphics(new_bond_id)
    else:
        canvas._add_ring_from_points(points)

    canvas._record_additions(
        before_next_atom_id=before_next_atom_id,
        before_bond_count=before_bond_count,
        before_smiles_input=before_smiles_input,
    )
    return True


def _bond_merge_seed(canvas: CanvasView, bond_id: int) -> list[tuple[int, float, float]]:
    if not (0 <= bond_id < len(canvas.model.bonds)):
        return []
    bond = canvas.model.bonds[bond_id]
    if bond is None:
        return []
    atom_a = canvas.model.atoms.get(bond.a)
    atom_b = canvas.model.atoms.get(bond.b)
    if atom_a is None or atom_b is None:
        return []
    return [(bond.a, atom_a.x, atom_a.y), (bond.b, atom_b.x, atom_b.y)]


__all__ = [
    "InsertCommitService",
    "apply_smiles_commit_plan",
    "apply_template_commit_resolution",
]
