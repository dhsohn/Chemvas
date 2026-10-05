"""Consistency rules between a retained Calculation Plan and its drawing.

Chemvas no longer creates, edits or runs calculation plans. A document saved by
an earlier release may still carry one, and Chemvas keeps it unchanged as
document data. These rules exist only to preserve that data: an edit or save
must never drop or rewrite the plan, so a caller that learns the drawing no
longer matches the plan's references refuses to write instead. Structural
validity — that the plan references existing atoms and complete components —
is checked by document validation through ``calculation_plan_from_state``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .calculation_plan import (
    CalculationPlanGraphMismatchError,
    calculation_plan_from_state,
)
from .inspection import component_inventory, document_model
from .state_values import model_bond_pairs

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .calculation_plan import CalculationPlan
    from .model import MoleculeModel


def validate_calculation_plan(
    document_state: Mapping[str, object],
    plan_state: object,
) -> CalculationPlan:
    """Parse ``plan_state`` and check it agrees with ``document_state``.

    Every included state must declare the charge its components carry, and
    every mapped pair of atoms must share an element label.
    """
    model = document_model(document_state)
    plan = calculation_plan_from_state(
        plan_state,
        atom_ids=set(model.atoms),
        bond_pairs=model_bond_pairs(model),
    )
    # Structural errors precede mark/alias and semantic errors, as they do at
    # the public validation boundary. Reuse this parsed model after that gate.
    inventory = component_inventory(document_state, model)
    components = {summary.atom_ids: summary for summary in inventory.components}
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


CALCULATION_PLAN_GRAPH_MISMATCH_WARNING = (
    "The calculation plan was not saved because the molecular graph "
    "no longer matches its component references. Undo the graph edit "
    "to recover those references, or reopen a previously saved copy."
)


def calculation_plan_save_warning(
    model: MoleculeModel, plan_state: object
) -> str | None:
    """Why a document snapshot cannot carry its plan, or None when it can.

    A snapshot that cannot carry the plan must not be written over a document:
    the caller refuses the save or edit instead of dropping the plan.
    """
    if plan_state is None:
        return None
    try:
        calculation_plan_from_state(
            plan_state,
            atom_ids=set(model.atoms),
            bond_pairs=model_bond_pairs(model),
        )
    except CalculationPlanGraphMismatchError:
        return CALCULATION_PLAN_GRAPH_MISMATCH_WARNING
    except ValueError as exc:
        return (
            f"The calculation plan was not saved because it no longer matches "
            f"the drawing: {exc} Undo the graph edit to recover its "
            "references, or reopen a previously saved copy."
        )
    return None


__all__ = [
    "CALCULATION_PLAN_GRAPH_MISMATCH_WARNING",
    "calculation_plan_save_warning",
    "validate_calculation_plan",
]
