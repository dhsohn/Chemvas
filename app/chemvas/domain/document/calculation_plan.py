from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from .graph import connected_atom_components
from .precomplex import (
    NO_PRECOMPLEX_JSON,
    canonicalize_precomplex_state,
    precomplex_state_from_json,
)

CALCULATION_PLAN_FORMAT = "chemvas-calculation-plan"
CALCULATION_PLAN_VERSION = 2
CALCULATION_INCLUSIONS = frozenset(("included", "context_only"))
CALCULATION_ROLES = frozenset(("reactant", "product", "catalyst", "spectator"))

_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


@dataclass(frozen=True)
class CalculationStateMember:
    component_atom_ids: tuple[int, ...]
    inclusion: str


@dataclass(frozen=True)
class CalculationState:
    id: str
    charge: int
    multiplicity: int
    members: tuple[CalculationStateMember, ...]


@dataclass(frozen=True)
class CalculationEndpointRole:
    component_atom_ids: tuple[int, ...]
    role: str


@dataclass(frozen=True)
class CalculationEndpointPrecomplex:
    kind: str
    payload_json: str


NO_PRECOMPLEX = CalculationEndpointPrecomplex(
    kind="none",
    payload_json=NO_PRECOMPLEX_JSON,
)


@dataclass(frozen=True)
class CalculationStepEndpoint:
    state_id: str
    roles: tuple[CalculationEndpointRole, ...]
    precomplex: CalculationEndpointPrecomplex = NO_PRECOMPLEX


@dataclass(frozen=True)
class CalculationAtomCorrespondence:
    reactant_atom_id: int
    product_atom_id: int


@dataclass(frozen=True)
class CalculationStep:
    id: str
    reactant: CalculationStepEndpoint
    product: CalculationStepEndpoint
    atom_correspondence: tuple[CalculationAtomCorrespondence, ...]


@dataclass(frozen=True)
class CalculationPlan:
    states: tuple[CalculationState, ...]
    steps: tuple[CalculationStep, ...]
    version: int = CALCULATION_PLAN_VERSION


def calculation_plan_from_state(
    value: object,
    *,
    atom_ids: set[int],
    bond_pairs: set[tuple[int, int]],
) -> CalculationPlan:
    if not isinstance(value, Mapping) or set(value) != {
        "format",
        "version",
        "states",
        "steps",
    }:
        raise ValueError("Invalid Chemvas calculation plan.")
    version = value.get("version")
    if (
        value.get("format") != CALCULATION_PLAN_FORMAT
        or type(version) is not int
        or version != CALCULATION_PLAN_VERSION
    ):
        raise ValueError("Invalid Chemvas calculation plan.")

    components = {
        frozenset(component)
        for component in connected_atom_components(atom_ids, bond_pairs)
    }
    states = _parse_states(value.get("states"), components)
    steps = _parse_steps(value.get("steps"), states, atom_ids)
    referenced_state_ids = {
        endpoint.state_id
        for step in steps
        for endpoint in (step.reactant, step.product)
    }
    if referenced_state_ids != set(states):
        raise ValueError("Every calculation state must be referenced by a step.")
    return CalculationPlan(
        states=tuple(states.values()),
        steps=tuple(steps),
        version=version,
    )


def calculation_plan_to_state(plan: CalculationPlan) -> dict[str, object]:
    if type(plan.version) is not int or plan.version != CALCULATION_PLAN_VERSION:
        raise ValueError("Invalid Chemvas calculation plan version.")
    return {
        "format": CALCULATION_PLAN_FORMAT,
        "version": CALCULATION_PLAN_VERSION,
        "states": [
            {
                "id": state.id,
                "charge": state.charge,
                "multiplicity": state.multiplicity,
                "members": [
                    {
                        "component_atom_ids": list(member.component_atom_ids),
                        "inclusion": member.inclusion,
                    }
                    for member in state.members
                ],
            }
            for state in plan.states
        ],
        "steps": [
            {
                "id": step.id,
                "reactant": _endpoint_to_state(step.reactant),
                "product": _endpoint_to_state(step.product),
                "atom_correspondence": [
                    {
                        "reactant_atom_id": entry.reactant_atom_id,
                        "product_atom_id": entry.product_atom_id,
                    }
                    for entry in step.atom_correspondence
                ],
            }
            for step in plan.steps
        ],
    }


def _endpoint_to_state(
    endpoint: CalculationStepEndpoint,
) -> dict[str, object]:
    state: dict[str, object] = {
        "state_id": endpoint.state_id,
        "roles": [
            {
                "component_atom_ids": list(role.component_atom_ids),
                "role": role.role,
            }
            for role in endpoint.roles
        ],
    }
    state["precomplex"] = precomplex_state_from_json(endpoint.precomplex.payload_json)
    return state


def _parse_states(
    value: object,
    components: set[frozenset[int]],
) -> dict[str, CalculationState]:
    if not isinstance(value, list) or not value:
        raise ValueError("A calculation plan must contain at least one state.")
    states: dict[str, CalculationState] = {}
    for raw_state in value:
        if not isinstance(raw_state, Mapping) or set(raw_state) != {
            "id",
            "charge",
            "multiplicity",
            "members",
        }:
            raise ValueError("Invalid calculation state.")
        state_id = _identifier(raw_state.get("id"), "state")
        if state_id in states:
            raise ValueError(f"Duplicate calculation state id: {state_id}")
        charge = raw_state.get("charge")
        multiplicity = raw_state.get("multiplicity")
        if type(charge) is not int:
            raise ValueError(f"State {state_id} charge must be an integer.")
        if type(multiplicity) is not int or multiplicity < 1:
            raise ValueError(f"State {state_id} multiplicity must be positive.")
        members = _parse_members(raw_state.get("members"), components, state_id)
        if not any(member.inclusion == "included" for member in members):
            raise ValueError(f"State {state_id} has no included structure.")
        states[state_id] = CalculationState(
            id=state_id,
            charge=charge,
            multiplicity=multiplicity,
            members=tuple(members),
        )
    return states


def _parse_members(
    value: object,
    components: set[frozenset[int]],
    state_id: str,
) -> list[CalculationStateMember]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"State {state_id} must contain at least one member.")
    members: list[CalculationStateMember] = []
    seen: set[tuple[int, ...]] = set()
    for raw_member in value:
        if not isinstance(raw_member, Mapping) or set(raw_member) != {
            "component_atom_ids",
            "inclusion",
        }:
            raise ValueError(f"State {state_id} contains an invalid member.")
        component_atom_ids = _component_atom_ids(
            raw_member.get("component_atom_ids"), components
        )
        if component_atom_ids in seen:
            raise ValueError(f"State {state_id} repeats a component.")
        seen.add(component_atom_ids)
        inclusion = raw_member.get("inclusion")
        if not isinstance(inclusion, str) or inclusion not in CALCULATION_INCLUSIONS:
            raise ValueError(f"State {state_id} contains an invalid inclusion.")
        members.append(
            CalculationStateMember(
                component_atom_ids=component_atom_ids,
                inclusion=inclusion,
            )
        )
    return members


def _parse_steps(
    value: object,
    states: Mapping[str, CalculationState],
    atom_ids: set[int],
) -> list[CalculationStep]:
    if not isinstance(value, list) or not value:
        raise ValueError("A calculation plan must contain at least one step.")
    steps: list[CalculationStep] = []
    seen_step_ids: set[str] = set()
    for raw_step in value:
        if not isinstance(raw_step, Mapping) or set(raw_step) != {
            "id",
            "reactant",
            "product",
            "atom_correspondence",
        }:
            raise ValueError("Invalid calculation step.")
        step_id = _identifier(raw_step.get("id"), "step")
        if step_id in seen_step_ids:
            raise ValueError(f"Duplicate calculation step id: {step_id}")
        seen_step_ids.add(step_id)
        reactant = _parse_endpoint(
            raw_step.get("reactant"),
            states,
            side="reactant",
            step_id=step_id,
        )
        product = _parse_endpoint(
            raw_step.get("product"),
            states,
            side="product",
            step_id=step_id,
        )
        if reactant.state_id == product.state_id:
            raise ValueError(f"Step {step_id} must connect two different states.")
        correspondence = _parse_correspondence(
            raw_step.get("atom_correspondence"),
            reactant_state=states[reactant.state_id],
            product_state=states[product.state_id],
            atom_ids=atom_ids,
            step_id=step_id,
        )
        steps.append(
            CalculationStep(
                id=step_id,
                reactant=reactant,
                product=product,
                atom_correspondence=tuple(correspondence),
            )
        )
    return steps


def _parse_endpoint(
    value: object,
    states: Mapping[str, CalculationState],
    *,
    side: str,
    step_id: str,
) -> CalculationStepEndpoint:
    expected_keys = {"state_id", "roles", "precomplex"}
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        raise ValueError(f"Step {step_id} has an invalid {side} endpoint.")
    state_id = _identifier(value.get("state_id"), "state")
    state = states.get(state_id)
    if state is None:
        raise ValueError(f"Step {step_id} references missing state {state_id}.")
    raw_roles = value.get("roles")
    if not isinstance(raw_roles, list) or not raw_roles:
        raise ValueError(f"Step {step_id} {side} endpoint has no roles.")
    member_by_ids = {member.component_atom_ids: member for member in state.members}
    roles: list[CalculationEndpointRole] = []
    seen: set[tuple[int, ...]] = set()
    permitted_roles = {side, "catalyst", "spectator"}
    for raw_role in raw_roles:
        if not isinstance(raw_role, Mapping) or set(raw_role) != {
            "component_atom_ids",
            "role",
        }:
            raise ValueError(f"Step {step_id} {side} endpoint has an invalid role.")
        component_ids = _sorted_atom_ids(raw_role.get("component_atom_ids"))
        member = member_by_ids.get(component_ids)
        role = raw_role.get("role")
        if member is None or component_ids in seen:
            raise ValueError(
                f"Step {step_id} {side} roles do not match state {state_id}."
            )
        if not isinstance(role, str) or role not in permitted_roles:
            raise ValueError(f"Step {step_id} {side} endpoint has an invalid role.")
        if member.inclusion == "context_only" and role == side:
            raise ValueError(
                f"Step {step_id} cannot mark a context-only component as {side}."
            )
        seen.add(component_ids)
        roles.append(
            CalculationEndpointRole(component_atom_ids=component_ids, role=role)
        )
    if seen != set(member_by_ids):
        raise ValueError(f"Step {step_id} {side} roles must cover state {state_id}.")
    if not any(
        role.role in {side, "catalyst"}
        and member_by_ids[role.component_atom_ids].inclusion == "included"
        for role in roles
    ):
        raise ValueError(f"Step {step_id} {side} endpoint has no reactive structure.")
    included_components = tuple(
        sorted(
            component_ids
            for component_ids, member in member_by_ids.items()
            if member.inclusion == "included"
        )
    )
    try:
        kind, payload_json = canonicalize_precomplex_state(
            value.get("precomplex"),
            side=side,
            included_components=included_components,
        )
    except ValueError as exc:
        raise ValueError(
            f"Step {step_id} has an invalid {side} precomplex: {exc}"
        ) from exc
    precomplex = CalculationEndpointPrecomplex(
        kind=kind,
        payload_json=payload_json,
    )
    return CalculationStepEndpoint(
        state_id=state_id,
        roles=tuple(roles),
        precomplex=precomplex,
    )


def _parse_correspondence(
    value: object,
    *,
    reactant_state: CalculationState,
    product_state: CalculationState,
    atom_ids: set[int],
    step_id: str,
) -> list[CalculationAtomCorrespondence]:
    if not isinstance(value, list):
        raise ValueError(f"Step {step_id} atom correspondence must be a list.")
    reactant_included = included_atom_ids(reactant_state)
    product_included = included_atom_ids(product_state)
    seen_reactant: set[int] = set()
    seen_product: set[int] = set()
    entries: list[CalculationAtomCorrespondence] = []
    for raw_entry in value:
        if not isinstance(raw_entry, Mapping) or set(raw_entry) != {
            "reactant_atom_id",
            "product_atom_id",
        }:
            raise ValueError(f"Step {step_id} has an invalid atom correspondence.")
        reactant_atom_id = raw_entry.get("reactant_atom_id")
        product_atom_id = raw_entry.get("product_atom_id")
        if (
            type(reactant_atom_id) is not int
            or type(product_atom_id) is not int
            or reactant_atom_id not in atom_ids
            or product_atom_id not in atom_ids
            or reactant_atom_id not in reactant_included
            or product_atom_id not in product_included
            or reactant_atom_id in seen_reactant
            or product_atom_id in seen_product
        ):
            raise ValueError(f"Step {step_id} has an invalid atom correspondence.")
        seen_reactant.add(reactant_atom_id)
        seen_product.add(product_atom_id)
        entries.append(
            CalculationAtomCorrespondence(
                reactant_atom_id=reactant_atom_id,
                product_atom_id=product_atom_id,
            )
        )
    return entries


def included_atom_ids(state: CalculationState) -> set[int]:
    return {
        atom_id
        for member in state.members
        if member.inclusion == "included"
        for atom_id in member.component_atom_ids
    }


def _identifier(value: object, kind: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(
            f"Calculation {kind} id must be 1-64 ASCII letters, digits, '.', '_' "
            "or '-', and start with a letter or digit."
        )
    return value


def _component_atom_ids(
    value: object,
    components: set[frozenset[int]],
) -> tuple[int, ...]:
    parsed = _sorted_atom_ids(value)
    if frozenset(parsed) not in components:
        raise ValueError(
            "Calculation members must reference one complete connected component."
        )
    return parsed


def _sorted_atom_ids(value: object) -> tuple[int, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(type(atom_id) is not int or atom_id < 0 for atom_id in value)
        or len(set(value)) != len(value)
        or value != sorted(value)
    ):
        raise ValueError(
            "Calculation component atom ids must be sorted unique integers."
        )
    return tuple(value)


__all__ = [
    "CALCULATION_INCLUSIONS",
    "CALCULATION_PLAN_FORMAT",
    "CALCULATION_PLAN_VERSION",
    "CALCULATION_ROLES",
    "CalculationAtomCorrespondence",
    "CalculationEndpointPrecomplex",
    "CalculationEndpointRole",
    "CalculationPlan",
    "CalculationState",
    "CalculationStateMember",
    "CalculationStep",
    "CalculationStepEndpoint",
    "calculation_plan_from_state",
    "calculation_plan_to_state",
    "included_atom_ids",
]
