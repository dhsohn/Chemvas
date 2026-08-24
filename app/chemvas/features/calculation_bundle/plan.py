from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import cast

from chemvas.domain.document import (
    CalculationAtomCorrespondence,
    CalculationPlan,
    CalculationState,
    CalculationStateMember,
    CalculationStep,
    CalculationStepEndpoint,
    MoleculeModel,
    calculation_plan_from_state,
    calculation_plan_to_state,
    deserialize_model_state,
    included_atom_ids,
    model_bond_pairs,
)
from chemvas.domain.document.precomplex import precomplex_state_from_json

from .model import CalculationStateSelection, ComponentSummary
from .service import inspect_components, select_components


@dataclass(frozen=True)
class StepReadiness:
    reactant_atom_count: int
    product_atom_count: int
    mapped_atom_count: int
    mapping_complete: bool
    ready_for_step_pack: bool


@dataclass(frozen=True)
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


def validate_calculation_plan(
    document_state: Mapping[str, object],
    plan_state: object,
) -> CalculationPlan:
    model = _document_model(document_state)
    plan = calculation_plan_from_state(
        plan_state,
        atom_ids=set(model.atoms),
        bond_pairs=model_bond_pairs(model),
    )
    components = {
        summary.atom_ids: summary for summary in inspect_components(document_state)
    }
    for state in plan.states:
        modeled_charge = sum(
            components[member.component_atom_ids].formal_charge
            for member in state.members
            if member.inclusion == "included"
        )
        if state.charge != modeled_charge:
            raise ValueError(
                f"State {state.id} declares charge {state.charge}, but its included "
                f"components have modeled formal charge {modeled_charge}."
            )
    for step in plan.steps:
        for entry in step.atom_correspondence:
            reactant_label = model.atoms[entry.reactant_atom_id].element
            product_label = model.atoms[entry.product_atom_id].element
            if reactant_label != product_label:
                raise ValueError(
                    f"Step {step.id} maps {reactant_label} atom "
                    f"{entry.reactant_atom_id} to {product_label} atom "
                    f"{entry.product_atom_id}; mapped atom labels must match."
                )
    return plan


def calculation_plan_for_document(
    document_state: Mapping[str, object],
) -> CalculationPlan:
    raw_plan = document_state.get("calculation_plan")
    if raw_plan is None:
        raise ValueError("The Chemvas document does not contain a calculation plan.")
    return validate_calculation_plan(document_state, raw_plan)


def structural_calculation_plan_for_document(
    document_state: Mapping[str, object],
) -> CalculationPlan:
    raw_plan = document_state.get("calculation_plan")
    if raw_plan is None:
        raise ValueError("The Chemvas document does not contain a calculation plan.")
    model = _document_model(document_state)
    return calculation_plan_from_state(
        raw_plan,
        atom_ids=set(model.atoms),
        bond_pairs=model_bond_pairs(model),
    )


def calculation_plan_report(
    document_state: Mapping[str, object],
) -> dict[str, object]:
    plan = calculation_plan_for_document(document_state)
    components = {
        summary.atom_ids: summary for summary in inspect_components(document_state)
    }
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
    reactant_state = calculation_state_by_id(plan, step.reactant.state_id)
    product_state = calculation_state_by_id(plan, step.product.state_id)
    source_mapping_complete = step_readiness(plan, step).ready_for_step_pack
    charge_matches = reactant_state.charge == product_state.charge
    multiplicity_matches = reactant_state.multiplicity == product_state.multiplicity
    reactant_component_count = _included_component_count(reactant_state)
    product_component_count = _included_component_count(product_state)
    single_component_endpoints = (
        reactant_component_count == 1 and product_component_count == 1
    )
    reviewed_precomplex_endpoints = all(
        _endpoint_has_reviewed_precomplex(endpoint)
        for endpoint in (step.reactant, step.product)
    )
    blocking_reasons: list[str] = []
    if not source_mapping_complete:
        blocking_reasons.append("source_atom_mapping_incomplete")
    if not charge_matches:
        blocking_reasons.append("endpoint_charge_mismatch")
    if not multiplicity_matches:
        blocking_reasons.append("endpoint_multiplicity_mismatch")
    if not single_component_endpoints and not reviewed_precomplex_endpoints:
        blocking_reasons.append("multicomponent_precomplex_geometry_not_provided")
    return PathPrecheck(
        reactant_charge=reactant_state.charge,
        product_charge=product_state.charge,
        charge_matches=charge_matches,
        reactant_multiplicity=reactant_state.multiplicity,
        product_multiplicity=product_state.multiplicity,
        multiplicity_matches=multiplicity_matches,
        reactant_component_count=reactant_component_count,
        product_component_count=product_component_count,
        single_component_endpoints=single_component_endpoints,
        source_mapping_complete=source_mapping_complete,
        ready_for_path_endpoints=not blocking_reasons,
        blocking_reasons=tuple(blocking_reasons),
    )


def _endpoint_has_reviewed_precomplex(
    endpoint: CalculationStepEndpoint,
) -> bool:
    if endpoint.precomplex.kind != "candidate_ensemble":
        return False
    state = precomplex_state_from_json(endpoint.precomplex.payload_json)
    return isinstance(state.get("selection"), Mapping)


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
    model = _document_model(document_state)
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
        _pair(reverse[a], reverse[b]): order
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
        product_pair = _pair(
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
    if current_plan_state is None:
        existing_plan = CalculationPlan(states=(), steps=())
    else:
        model = _document_model(document_state)
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
    for state_id, replacement in replacements.items():
        existing = existing_states.get(state_id)
        if (
            existing is not None
            and existing != replacement
            and state_id in referenced_by_retained
        ):
            raise ValueError(
                f"State {state_id} is used by another step. Choose a new state id "
                "instead of changing its structure or calculation settings."
            )
    retained_state_ids = referenced_by_retained | set(replacements)
    merged_states: list[CalculationState] = []
    for state in existing_plan.states:
        if state.id not in retained_state_ids or state.id in replacements:
            continue
        merged_states.append(state)
    for state_id in (reactant_state.id, product_state.id):
        if state_id not in {state.id for state in merged_states}:
            merged_states.append(replacements[state_id])
    candidate = CalculationPlan(
        states=tuple(merged_states),
        steps=retained_steps + (step,),
        version=existing_plan.version,
    )
    return validate_calculation_plan(
        document_state,
        calculation_plan_to_state(candidate),
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


def _document_model(document_state: Mapping[str, object]) -> MoleculeModel:
    model_state = document_state.get("model")
    if not isinstance(model_state, Mapping):
        raise ValueError("Invalid Chemvas document state: model is missing.")
    return deserialize_model_state(cast(Mapping[str, object], model_state))


def _bond_orders(
    model: MoleculeModel,
    atom_ids: set[int],
) -> dict[tuple[int, int], int]:
    return {
        _pair(bond.a, bond.b): bond.order
        for bond in model.bonds
        if bond is not None and bond.a in atom_ids and bond.b in atom_ids
    }


def _pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


__all__ = [
    "PathPrecheck",
    "StepReadiness",
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
    "require_step_ready",
    "select_calculation_state",
    "step_readiness",
    "structural_calculation_plan_for_document",
    "validate_calculation_plan",
]
