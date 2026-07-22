from __future__ import annotations

import pytest
from chemvas.features.hover import (
    HoverState,
    HoverUpdatePlan,
    plan_structure_hover_update,
)
from chemvas.features.selection import StructureHit


def test_hover_state_defaults_are_independent() -> None:
    first = HoverState()
    second = HoverState()

    first.items.append("preview")

    assert first == HoverState(items=["preview"])
    assert second == HoverState()


@pytest.mark.parametrize(
    ("current_preview_key", "free_preview_key", "expected"),
    [
        (None, None, HoverUpdatePlan(action="clear")),
        (
            "wedge:1:8.0:9.0",
            "wedge:1:8.0:9.0",
            HoverUpdatePlan(action="noop"),
        ),
        (
            None,
            "wedge:1:8.0:9.0",
            HoverUpdatePlan(
                action="free_bond_preview",
                preview_key="wedge:1:8.0:9.0",
            ),
        ),
    ],
)
def test_plan_without_atoms_clears_deduplicates_or_previews(
    current_preview_key: str | None,
    free_preview_key: str | None,
    expected: HoverUpdatePlan,
) -> None:
    assert (
        plan_structure_hover_update(
            has_atoms=False,
            current_hover_atom_id=None,
            current_hover_bond_id=None,
            current_preview_key=current_preview_key,
            preferred_hit=None,
            free_preview_key=free_preview_key,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("hit", "current_preview_key", "free_preview_key", "expected"),
    [
        (None, None, None, HoverUpdatePlan(action="clear")),
        (
            StructureHit(kind="other", id=None),
            None,
            "single:1:8.0:9.0",
            HoverUpdatePlan(
                action="free_bond_preview",
                preview_key="single:1:8.0:9.0",
            ),
        ),
        (
            StructureHit(kind="ring", id=None),
            "single:1:8.0:9.0",
            "single:1:8.0:9.0",
            HoverUpdatePlan(action="noop"),
        ),
        (
            StructureHit(kind="other", id=None),
            None,
            None,
            HoverUpdatePlan(action="clear"),
        ),
    ],
)
def test_plan_for_missing_or_invalid_hit_uses_free_preview_policy(
    hit: StructureHit | None,
    current_preview_key: str | None,
    free_preview_key: str | None,
    expected: HoverUpdatePlan,
) -> None:
    assert (
        plan_structure_hover_update(
            has_atoms=True,
            current_hover_atom_id=None,
            current_hover_bond_id=None,
            current_preview_key=current_preview_key,
            preferred_hit=hit,
            free_preview_key=free_preview_key,
        )
        == expected
    )


@pytest.mark.parametrize(
    (
        "current_atom_id",
        "current_preview_key",
        "signature",
        "preview_key",
        "expected",
    ),
    [
        (
            1,
            "wedge:1:13.0:14.0",
            "wedge:1",
            "wedge:1:13.0:14.0",
            HoverUpdatePlan(action="noop"),
        ),
        (
            None,
            None,
            "wedge:1",
            None,
            HoverUpdatePlan(action="clear"),
        ),
        (
            None,
            None,
            "wedge:1",
            "wedge:1:13.0:14.0",
            HoverUpdatePlan(
                action="atom_hit",
                hover_atom_id=1,
                preview_key="wedge:1:13.0:14.0",
            ),
        ),
        (
            None,
            None,
            None,
            None,
            HoverUpdatePlan(action="atom_hit", hover_atom_id=1),
        ),
    ],
)
def test_plan_for_atom_hit_handles_preview_and_deduplication(
    current_atom_id: int | None,
    current_preview_key: str | None,
    signature: str | None,
    preview_key: str | None,
    expected: HoverUpdatePlan,
) -> None:
    assert (
        plan_structure_hover_update(
            has_atoms=True,
            current_hover_atom_id=current_atom_id,
            current_hover_bond_id=None,
            current_preview_key=current_preview_key,
            preferred_hit=StructureHit(kind="atom", id=1),
            atom_preview_signature=signature,
            atom_preview_key=preview_key,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("current_bond_id", "current_preview_key", "preview_key", "expected"),
    [
        (3, "hash", "hash", HoverUpdatePlan(action="noop")),
        (
            None,
            None,
            "wedge",
            HoverUpdatePlan(
                action="bond_hit",
                hover_bond_id=3,
                preview_key="wedge",
            ),
        ),
        (
            None,
            None,
            None,
            HoverUpdatePlan(action="bond_hit", hover_bond_id=3),
        ),
    ],
)
def test_plan_for_bond_hit_handles_preview_and_deduplication(
    current_bond_id: int | None,
    current_preview_key: str | None,
    preview_key: str | None,
    expected: HoverUpdatePlan,
) -> None:
    assert (
        plan_structure_hover_update(
            has_atoms=True,
            current_hover_atom_id=None,
            current_hover_bond_id=current_bond_id,
            current_preview_key=current_preview_key,
            preferred_hit=StructureHit(kind="bond", id=3),
            bond_preview_key=preview_key,
        )
        == expected
    )
