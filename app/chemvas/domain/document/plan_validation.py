"""Consistency rules between a Calculation Plan and the drawing it describes.

A plan is part of the document, so whether it still agrees with the drawing
is a document question: every included state must declare the charge its
components carry, and every mapped pair of atoms must share an element label.
General editing (the desktop's save prompt, the headless Graph Patch) asks
this before publishing a document; the calculation feature asks it too, and
then goes on to decide what it can compute. Structural validity — that the
plan references existing atoms and bonds — is checked earlier by document
validation and again here through ``calculation_plan_from_state``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .calculation_plan import calculation_plan_from_state
from .inspection import component_inventory, document_model
from .state import model_bond_pairs

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .calculation_plan import CalculationPlan
    from .inspection import ComponentInventory


def validate_calculation_plan(
    document_state: Mapping[str, object],
    plan_state: object,
) -> CalculationPlan:
    """Parse ``plan_state`` and check it agrees with ``document_state``."""
    plan, _inventory = validated_plan_and_inventory(document_state, plan_state)
    return plan


def validated_plan_and_inventory(
    document_state: Mapping[str, object], plan_state: object
) -> tuple[CalculationPlan, ComponentInventory]:
    """Validate the plan and hand back the inventory it was checked against.

    Callers that go on to inspect components reuse that inventory instead of
    computing it a second time.
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
    return plan, inventory


__all__ = ["validate_calculation_plan", "validated_plan_and_inventory"]
