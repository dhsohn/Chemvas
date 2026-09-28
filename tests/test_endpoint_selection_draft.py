from chemvas.features.calculation_bundle import (
    EndpointSelectionDraft,
    inspect_component_inventory,
)
from tests.calculation_plan_support import _document_state


def test_endpoint_lock_preserves_values_and_context_remains_independent():
    draft = EndpointSelectionDraft(
        inspect_component_inventory(_document_state()).components
    )
    draft.set_inclusion("reactant", 0, "included")
    draft.set_inclusion("product", 0, "included")
    draft.choices["product", 0].role = "catalyst"
    assert draft.side_locked("product", 0)
    assert draft.members_and_roles("product") == ((), ())
    draft.choices["reactant", 0].role = "catalyst"
    assert not draft.side_locked("product", 0)
    members, roles = draft.members_and_roles("product")
    assert members[0].inclusion == "included"
    assert roles[0].role == "catalyst"
    draft.choices["reactant", 0].role = "reactant"
    draft.set_inclusion("product", 0, "context_only")
    assert not draft.side_locked("product", 0)
    assert draft.modeled_charge("product") == 0


def test_context_selection_changes_reactive_role_to_spectator():
    draft = EndpointSelectionDraft(
        inspect_component_inventory(_document_state()).components
    )
    draft.set_inclusion("product", 0, "context_only")
    assert draft.choices["product", 0].role == "spectator"
    draft.set_inclusion("product", 0, "unused")
    assert draft.members_and_roles("product") == ((), ())


def test_modeled_charge_uses_only_included_unlocked_components():
    from dataclasses import replace

    component = inspect_component_inventory(_document_state()).components[0]
    draft = EndpointSelectionDraft((replace(component, formal_charge=2),))
    draft.set_inclusion("product", 0, "included")
    draft.choices["product", 0].role = "spectator"
    assert draft.modeled_charge("product") == 2
    draft.set_inclusion("reactant", 0, "included")
    assert draft.modeled_charge("product") == 0
    draft.choices["reactant", 0].role = "catalyst"
    assert draft.modeled_charge("product") == 2
    draft.set_inclusion("product", 0, "context_only")
    assert draft.modeled_charge("product") == 0
