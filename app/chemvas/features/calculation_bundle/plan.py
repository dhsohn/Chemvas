from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING

from chemvas.domain.document import (
    CalculationAtomCorrespondence,
    CalculationPlan,
    CalculationState,
    CalculationStateMember,
    CalculationStep,
    MoleculeModel,
    bond_pair_key,
    calculation_plan_from_state,
    calculation_plan_to_state,
    included_atom_ids,
    model_bond_pairs,
    validate_calculation_plan,
    validated_plan_and_inventory,
)
from chemvas.domain.document.calculation_plan import NO_PRECOMPLEX
from chemvas.domain.document.inspection import (
    document_model,
    inspect_component_inventory,
)

from .service import (
    _select_components,
    select_components,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from chemvas.domain.document.inspection import ComponentInventory, ComponentSummary

    from .model import (
        AtomMapEntry,
        CalculationArtifacts,
        CalculationStateSelection,
    )


@dataclass(frozen=True)
class StepReadiness:
    reactant_atom_count: int
    product_atom_count: int
    mapped_atom_count: int
    mapping_complete: bool
    ready_for_step_pack: bool


@dataclass(frozen=True, kw_only=True)
class PathPrecheck:
    reactant_charge: int
    product_charge: int
    charge_matches: bool
    reactant_multiplicity: int
    product_multiplicity: int
    multiplicity_matches: bool
    reactant_component_count: int
    product_component_count: int
    single_component_endpoints: bool
    source_mapping_complete: bool
    ready_for_path_endpoints: bool
    blocking_reasons: tuple[str, ...]


@dataclass(frozen=True)
class CalculationStepPreparation:
    """One pack request's validated graph; never reuse across document edits.

    Later checks stay explicit so bootstrap preserves their ordering around
    backend artifact generation. This is not a replacement public validator.
    """

    plan: CalculationPlan
    step: CalculationStep
    precheck: PathPrecheck
    reactant_selection: CalculationStateSelection
    product_selection: CalculationStateSelection
    # One selection per included component, in the state's member order. A
    # drawing does not place separate molecules relative to each other, so
    # each component is converted on its own.
    reactant_component_selections: tuple[CalculationStateSelection, ...]
    product_component_selections: tuple[CalculationStateSelection, ...]
    _inventory: ComponentInventory

    def bond_changes(self) -> tuple[dict[str, object], ...]:
        require_step_ready(self.plan, self.step)
        return _calculate_bond_changes(self._inventory.model, self.plan, self.step)


def prepare_calculation_step(
    document_state: Mapping[str, object], step_id: str
) -> CalculationStepPreparation:
    """Prepare one pack request without retaining or changing its source state."""
    plan, inventory = validated_plan_and_inventory(
        document_state, _document_plan_state(document_state)
    )
    step = calculation_step_by_id(plan, step_id)
    require_step_ready(plan, step)
    precheck = path_precheck(plan, step)
    included = tuple(
        [
            member.component_atom_ids
            for member in calculation_state_by_id(plan, endpoint.state_id).members
            if member.inclusion == "included"
        ]
        for endpoint in (step.reactant, step.product)
    )
    return CalculationStepPreparation(
        plan,
        step,
        precheck,
        _select_components(inventory, included[0]),
        _select_components(inventory, included[1]),
        tuple(_select_components(inventory, [ids]) for ids in included[0]),
        tuple(_select_components(inventory, [ids]) for ids in included[1]),
        inventory,
    )


def calculation_plan_for_document(
    document_state: Mapping[str, object],
) -> CalculationPlan:
    return validate_calculation_plan(
        document_state, _document_plan_state(document_state)
    )


def structural_calculation_plan_for_document(
    document_state: Mapping[str, object],
) -> CalculationPlan:
    raw_plan = _document_plan_state(document_state)
    model = document_model(document_state)
    return calculation_plan_from_state(
        raw_plan,
        atom_ids=set(model.atoms),
        bond_pairs=model_bond_pairs(model),
    )


def prepare_calculation_step_editor(
    document_state: Mapping[str, object],
) -> tuple[ComponentInventory, CalculationPlan | None]:
    """Inspect the source once while allowing semantically invalid plan drafts."""
    inventory = inspect_component_inventory(document_state)
    raw_plan = document_state.get("calculation_plan")
    plan = (
        calculation_plan_from_state(
            raw_plan,
            atom_ids=set(inventory.model.atoms),
            bond_pairs=model_bond_pairs(inventory.model),
        )
        if raw_plan is not None
        else None
    )
    return inventory, plan


def _document_plan_state(document_state: Mapping[str, object]) -> object:
    raw_plan = document_state.get("calculation_plan")
    if raw_plan is None:
        raise ValueError("The Chemvas document does not contain a calculation plan.")
    return raw_plan


def calculation_plan_report(
    document_state: Mapping[str, object],
) -> dict[str, object]:
    plan, inventory = validated_plan_and_inventory(
        document_state, _document_plan_state(document_state)
    )
    components = {summary.atom_ids: summary for summary in inventory.components}
    return {
        "format": "chemvas-calculation-plan-inspection",
        "version": 1,
        "states": [_state_report(state, components) for state in plan.states],
        "steps": [
            {
                "id": step.id,
                "reactant_state": step.reactant.state_id,
                "product_state": step.product.state_id,
                "readiness": asdict(step_readiness(plan, step)),
                "path_precheck": asdict(path_precheck(plan, step)),
            }
            for step in plan.steps
        ],
        "plan": calculation_plan_to_state(plan),
    }


def _state_report(
    state: CalculationState,
    components: Mapping[tuple[int, ...], ComponentSummary],
) -> dict[str, object]:
    included = [member for member in state.members if member.inclusion == "included"]
    return {
        "id": state.id,
        "charge": state.charge,
        "multiplicity": state.multiplicity,
        "included_component_count": len(included),
        "included_atom_count": sum(
            len(member.component_atom_ids) for member in included
        ),
        "modeled_formal_charge": sum(
            components[member.component_atom_ids].formal_charge for member in included
        ),
        "members": [
            {
                "component_atom_ids": list(member.component_atom_ids),
                "inclusion": member.inclusion,
            }
            for member in state.members
        ],
    }


def calculation_step_by_id(plan: CalculationPlan, step_id: str) -> CalculationStep:
    for step in plan.steps:
        if step.id == step_id:
            return step
    available = ", ".join(step.id for step in plan.steps) or "none"
    raise ValueError(
        f"Calculation step {step_id!r} does not exist; available: {available}."
    )


def calculation_state_by_id(plan: CalculationPlan, state_id: str) -> CalculationState:
    for state in plan.states:
        if state.id == state_id:
            return state
    raise ValueError(f"Calculation state {state_id!r} does not exist.")


def select_calculation_state(
    document_state: Mapping[str, object],
    state: CalculationState,
) -> CalculationStateSelection:
    return select_components(
        document_state,
        [
            member.component_atom_ids
            for member in state.members
            if member.inclusion == "included"
        ],
    )


def step_readiness(plan: CalculationPlan, step: CalculationStep) -> StepReadiness:
    reactant_state = calculation_state_by_id(plan, step.reactant.state_id)
    product_state = calculation_state_by_id(plan, step.product.state_id)
    return correspondence_readiness(
        reactant_state,
        product_state,
        step.atom_correspondence,
    )


def path_precheck(plan: CalculationPlan, step: CalculationStep) -> PathPrecheck:
    """Report whether a step's endpoints can be handed off for calculation.

    A drawing never determines how separate molecules sit against each other,
    so the component count does not block a handoff; placing components is
    left to the calculation that consumes it.
    """
    reactant_state = calculation_state_by_id(plan, step.reactant.state_id)
    product_state = calculation_state_by_id(plan, step.product.state_id)
    source_mapping_complete = step_readiness(plan, step).ready_for_step_pack
    charge_matches = reactant_state.charge == product_state.charge
    multiplicity_matches = reactant_state.multiplicity == product_state.multiplicity
    reactant_component_count = _included_component_count(reactant_state)
    product_component_count = _included_component_count(product_state)
    blocking_reasons: list[str] = []
    if not source_mapping_complete:
        blocking_reasons.append("source_atom_mapping_incomplete")
    if not charge_matches:
        blocking_reasons.append("endpoint_charge_mismatch")
    if not multiplicity_matches:
        blocking_reasons.append("endpoint_multiplicity_mismatch")
    return PathPrecheck(
        reactant_charge=reactant_state.charge,
        product_charge=product_state.charge,
        charge_matches=charge_matches,
        reactant_multiplicity=reactant_state.multiplicity,
        product_multiplicity=product_state.multiplicity,
        multiplicity_matches=multiplicity_matches,
        reactant_component_count=reactant_component_count,
        product_component_count=product_component_count,
        single_component_endpoints=(
            reactant_component_count == 1 and product_component_count == 1
        ),
        source_mapping_complete=source_mapping_complete,
        ready_for_path_endpoints=not blocking_reasons,
        blocking_reasons=tuple(blocking_reasons),
    )


def correspondence_readiness(
    reactant_state: CalculationState,
    product_state: CalculationState,
    correspondence: tuple[CalculationAtomCorrespondence, ...],
) -> StepReadiness:
    reactant_ids = included_atom_ids(reactant_state)
    product_ids = included_atom_ids(product_state)
    mapped_reactant = {entry.reactant_atom_id for entry in correspondence}
    mapped_product = {entry.product_atom_id for entry in correspondence}
    one_to_one = len(correspondence) == len(mapped_reactant) == len(mapped_product)
    complete = (
        bool(reactant_ids)
        and bool(product_ids)
        and one_to_one
        and mapped_reactant == reactant_ids
        and mapped_product == product_ids
    )
    return StepReadiness(
        reactant_atom_count=len(reactant_ids),
        product_atom_count=len(product_ids),
        mapped_atom_count=len(correspondence),
        mapping_complete=complete,
        ready_for_step_pack=complete and len(reactant_ids) == len(product_ids),
    )


def step_atom_correspondence(
    step: CalculationStep,
    *,
    reactant_artifacts: CalculationArtifacts,
    product_artifacts: CalculationArtifacts,
) -> dict[str, object]:
    """Extend the reviewed Chemvas atom mapping to every generated atom.

    Each reviewed pair must own the same symbol sequence on both endpoints
    (the drawn atom plus its generated hydrogens and alias expansion), and the
    result must cover every generated atom of both endpoints.
    """
    reactant_groups = _artifact_atom_groups(reactant_artifacts)
    product_groups = _artifact_atom_groups(product_artifacts)
    source_entries: list[dict[str, int]] = []
    geometry_entries: list[dict[str, object]] = []
    for entry in sorted(
        step.atom_correspondence,
        key=lambda item: item.reactant_atom_id,
    ):
        reactant_group = reactant_groups.get(entry.reactant_atom_id, ())
        product_group = product_groups.get(entry.product_atom_id, ())
        reactant_symbols = [item.symbol for item in reactant_group]
        product_symbols = [item.symbol for item in product_group]
        if not reactant_group or reactant_symbols != product_symbols:
            raise ValueError(
                f"Step {step.id} cannot produce a complete geometry atom mapping for "
                f"Chemvas atoms {entry.reactant_atom_id} -> {entry.product_atom_id}. "
                "Draw transferred hydrogens explicitly and keep abbreviation expansion "
                "consistent on both endpoints."
            )
        source_entries.append(asdict(entry))
        geometry_entries.extend(
            {
                "reactant_xyz_index": reactant_item.xyz_index,
                "product_xyz_index": product_item.xyz_index,
                "symbol": reactant_item.symbol,
                "reactant_chemvas_atom_id": entry.reactant_atom_id,
                "product_chemvas_atom_id": entry.product_atom_id,
                "origin": reactant_item.origin,
            }
            for reactant_item, product_item in zip(
                reactant_group, product_group, strict=True
            )
        )
    reactant_xyz = {entry["reactant_xyz_index"] for entry in geometry_entries}
    product_xyz = {entry["product_xyz_index"] for entry in geometry_entries}
    if reactant_xyz != set(range(1, reactant_artifacts.xyz_atom_count + 1)) or (
        product_xyz != set(range(1, product_artifacts.xyz_atom_count + 1))
    ):
        raise ValueError(
            f"Step {step.id} generated geometry atoms that are not covered by the "
            "validated atom correspondence."
        )
    return {
        "format": "chemvas-step-atom-correspondence",
        "version": 1,
        "step_id": step.id,
        "source_entries": source_entries,
        "geometry_entries": geometry_entries,
        "source_mapping": "complete_bijection",
        "geometry_mapping": "complete_bijection",
    }


def _artifact_atom_groups(
    artifacts: CalculationArtifacts,
) -> dict[int, tuple[AtomMapEntry, ...]]:
    groups: dict[int, list[AtomMapEntry]] = {}
    for entry in artifacts.atom_map:
        owner = (
            entry.chemvas_atom_id
            if entry.chemvas_atom_id is not None
            else entry.parent_chemvas_atom_id
        )
        if owner is None:
            raise ValueError(
                "A generated calculation atom has no Chemvas provenance owner."
            )
        groups.setdefault(owner, []).append(entry)
    return {owner: tuple(entries) for owner, entries in groups.items()}


def require_step_ready(plan: CalculationPlan, step: CalculationStep) -> None:
    readiness = step_readiness(plan, step)
    if not readiness.ready_for_step_pack:
        raise ValueError(
            f"Step {step.id} does not have a complete one-to-one correspondence "
            "for every included Chemvas atom. Add explicit atom_correspondence "
            "entries before calculation export."
        )


def _included_component_count(state: CalculationState) -> int:
    return sum(member.inclusion == "included" for member in state.members)


def calculate_bond_changes(
    document_state: Mapping[str, object],
    plan: CalculationPlan,
    step: CalculationStep,
) -> tuple[dict[str, object], ...]:
    require_step_ready(plan, step)
    model = document_model(document_state)
    return _calculate_bond_changes(model, plan, step)


def _calculate_bond_changes(
    model: MoleculeModel, plan: CalculationPlan, step: CalculationStep
) -> tuple[dict[str, object], ...]:
    reactant_state = calculation_state_by_id(plan, step.reactant.state_id)
    product_state = calculation_state_by_id(plan, step.product.state_id)
    reactant_ids = included_atom_ids(reactant_state)
    product_ids = included_atom_ids(product_state)
    forward = {
        entry.reactant_atom_id: entry.product_atom_id
        for entry in step.atom_correspondence
    }
    reverse = {product: reactant for reactant, product in forward.items()}
    reactant_bonds = _bond_orders(model, reactant_ids)
    product_native_bonds = _bond_orders(model, product_ids)
    product_bonds = {
        bond_pair_key(reverse[a], reverse[b]): order
        for (a, b), order in product_native_bonds.items()
    }
    changes: list[dict[str, object]] = []
    for reactant_pair in sorted(set(reactant_bonds) | set(product_bonds)):
        before = reactant_bonds.get(reactant_pair)
        after = product_bonds.get(reactant_pair)
        if before == after:
            continue
        if before is None:
            kind = "added"
        elif after is None:
            kind = "removed"
        else:
            kind = "order_changed"
        product_pair = bond_pair_key(
            forward[reactant_pair[0]],
            forward[reactant_pair[1]],
        )
        changes.append(
            {
                "kind": kind,
                "reactant_atom_ids": list(reactant_pair),
                "product_atom_ids": list(product_pair),
                "reactant_order": before,
                "product_order": after,
            }
        )
    return tuple(changes)


def plan_with_replaced_step(
    document_state: Mapping[str, object],
    *,
    current_plan_state: object | None,
    reactant_state: CalculationState,
    product_state: CalculationState,
    step: CalculationStep,
) -> CalculationPlan:
    if reactant_state.id == product_state.id:
        raise ValueError(f"Step {step.id} must connect two different states.")
    if current_plan_state is None:
        existing_plan = CalculationPlan(states=(), steps=())
    else:
        model = document_model(document_state)
        existing_plan = calculation_plan_from_state(
            current_plan_state,
            atom_ids=set(model.atoms),
            bond_pairs=model_bond_pairs(model),
        )
    retained_steps = tuple(item for item in existing_plan.steps if item.id != step.id)
    referenced_by_retained = {
        endpoint.state_id
        for item in retained_steps
        for endpoint in (item.reactant, item.product)
    }
    replacements = {
        reactant_state.id: reactant_state,
        product_state.id: product_state,
    }
    existing_states = {state.id: state for state in existing_plan.states}
    repaired_shared_charge = False
    for state_id, replacement in replacements.items():
        existing = existing_states.get(state_id)
        if existing is not None and _same_state(existing, replacement):
            replacements[state_id] = existing
            continue
        if existing is not None and state_id in referenced_by_retained:
            if not _same_state(existing, replace(replacement, charge=existing.charge)):
                raise ValueError(
                    f"State {state_id} is used by another step. Choose a new state id "
                    "instead of changing its structure or calculation settings."
                )
            # Charge is derived from the current drawing. Correcting it updates
            # the one shared state; whole-plan validation below still rejects
            # a charge that disagrees with that drawing.
            repaired_shared_charge = True
    retained_state_ids = referenced_by_retained | set(replacements)
    merged_states: list[CalculationState] = []
    for state in existing_plan.states:
        if state.id not in retained_state_ids:
            continue
        merged_states.append(replacements.get(state.id, state))
    for state_id in (reactant_state.id, product_state.id):
        if state_id not in {state.id for state in merged_states}:
            merged_states.append(replacements[state_id])
    merged_steps = tuple(
        step if item.id == step.id else item for item in existing_plan.steps
    )
    if all(item.id != step.id for item in existing_plan.steps):
        merged_steps += (step,)
    candidate = CalculationPlan(
        states=tuple(merged_states),
        steps=tuple(
            _without_precomplex(item) if repaired_shared_charge else item
            for item in merged_steps
        ),
        version=existing_plan.version,
    )
    return validate_calculation_plan(
        document_state,
        calculation_plan_to_state(candidate),
    )


def _same_state(left: CalculationState, right: CalculationState) -> bool:
    return (
        left.id == right.id
        and left.charge == right.charge
        and left.multiplicity == right.multiplicity
        and sorted(left.members, key=lambda member: member.component_atom_ids)
        == sorted(right.members, key=lambda member: member.component_atom_ids)
    )


def _without_precomplex(step: CalculationStep) -> CalculationStep:
    return replace(
        step,
        reactant=replace(step.reactant, precomplex=NO_PRECOMPLEX),
        product=replace(step.product, precomplex=NO_PRECOMPLEX),
    )


def apply_calculation_step_edit(
    document_state: Mapping[str, object],
    *,
    current_plan: CalculationPlan | None,
    selected_step_id: str | None,
    reactant_state: CalculationState,
    product_state: CalculationState,
    step: CalculationStep,
) -> CalculationPlan:
    """Validate an editor draft, retaining stored endpoint data only on a no-op edit."""
    if (
        selected_step_id is None
        and current_plan is not None
        and any(candidate.id == step.id for candidate in current_plan.steps)
    ):
        raise ValueError(
            f"Step {step.id} already exists. Select Edit {step.id} instead."
        )
    # An edited endpoint starts without stored precomplex data, even if a
    # caller built its draft by replacing fields on an existing step.
    step = _without_precomplex(step)
    existing_step = (
        next(
            (
                candidate
                for candidate in current_plan.steps
                if candidate.id == selected_step_id
            ),
            None,
        )
        if current_plan is not None and selected_step_id is not None
        else None
    )
    if existing_step is not None:
        assert current_plan is not None
        existing_reactant_state = calculation_state_by_id(
            current_plan, existing_step.reactant.state_id
        )
        existing_product_state = calculation_state_by_id(
            current_plan, existing_step.product.state_id
        )
        if (
            step.id == existing_step.id
            and _same_state(reactant_state, existing_reactant_state)
            and _same_state(product_state, existing_product_state)
            and step.reactant.state_id == existing_step.reactant.state_id
            and sorted(step.reactant.roles, key=lambda role: role.component_atom_ids)
            == sorted(
                existing_step.reactant.roles, key=lambda role: role.component_atom_ids
            )
            and step.product.state_id == existing_step.product.state_id
            and sorted(step.product.roles, key=lambda role: role.component_atom_ids)
            == sorted(
                existing_step.product.roles, key=lambda role: role.component_atom_ids
            )
            and sorted(
                step.atom_correspondence,
                key=lambda entry: (entry.reactant_atom_id, entry.product_atom_id),
            )
            == sorted(
                existing_step.atom_correspondence,
                key=lambda entry: (entry.reactant_atom_id, entry.product_atom_id),
            )
        ):
            # A no-op edit keeps the persisted plan exactly, including its
            # ordering and any precomplex data stored by an older release.
            return validate_calculation_plan(
                document_state, calculation_plan_to_state(current_plan)
            )
    return plan_with_replaced_step(
        document_state,
        current_plan_state=(
            calculation_plan_to_state(current_plan) if current_plan else None
        ),
        reactant_state=reactant_state,
        product_state=product_state,
        step=step,
    )


def identity_correspondence(
    reactant_state: CalculationState,
    product_state: CalculationState,
) -> tuple[CalculationAtomCorrespondence, ...]:
    common = sorted(
        included_atom_ids(reactant_state) & included_atom_ids(product_state)
    )
    return tuple(CalculationAtomCorrespondence(atom_id, atom_id) for atom_id in common)


def fill_correspondence_gaps(
    mapping_by_reactant: Mapping[int, int | None],
    candidates: Iterable[tuple[int, int]],
    *,
    active_reactant_ids: set[int],
    active_product_ids: set[int],
    replaceable_reactant_ids: set[int],
    atom_elements: Mapping[int, str] | None = None,
) -> tuple[dict[int, int | None], int]:
    """Fill safe active-endpoint gaps without mutating the supplied mapping."""

    filled = dict(mapping_by_reactant)
    used_product_ids = {
        product_atom_id
        for reactant_atom_id, product_atom_id in filled.items()
        if reactant_atom_id in active_reactant_ids and type(product_atom_id) is int
    }
    applied = 0
    for reactant_atom_id, product_atom_id in candidates:
        if (
            reactant_atom_id not in active_reactant_ids
            or product_atom_id not in active_product_ids
            or reactant_atom_id not in replaceable_reactant_ids
            or filled.get(reactant_atom_id) is not None
            or product_atom_id in used_product_ids
        ):
            continue
        if (
            atom_elements is not None
            and atom_elements[reactant_atom_id] != atom_elements[product_atom_id]
        ):
            continue
        filled[reactant_atom_id] = product_atom_id
        used_product_ids.add(product_atom_id)
        applied += 1
    return filled, applied


def member(
    component_atom_ids: tuple[int, ...], inclusion: str
) -> CalculationStateMember:
    return CalculationStateMember(component_atom_ids, inclusion)


def _bond_orders(
    model: MoleculeModel,
    atom_ids: set[int],
) -> dict[tuple[int, int], int]:
    return {
        bond_pair_key(bond.a, bond.b): bond.order
        for bond in model.bonds
        if bond is not None and bond.a in atom_ids and bond.b in atom_ids
    }


__all__ = [
    "PathPrecheck",
    "StepReadiness",
    "apply_calculation_step_edit",
    "calculate_bond_changes",
    "calculation_plan_for_document",
    "calculation_plan_report",
    "calculation_state_by_id",
    "calculation_step_by_id",
    "correspondence_readiness",
    "fill_correspondence_gaps",
    "identity_correspondence",
    "included_atom_ids",
    "member",
    "path_precheck",
    "plan_with_replaced_step",
    "prepare_calculation_step_editor",
    "require_step_ready",
    "select_calculation_state",
    "step_readiness",
    "structural_calculation_plan_for_document",
    "validate_calculation_plan",
]
