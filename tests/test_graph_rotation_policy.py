from types import SimpleNamespace

from chemvas.ui.graph_rotation_policy import (
    axis_from_rotation_hint_policy,
    preferred_rotation_side_for_bond_policy,
    rotatable_axis_from_selection_policy,
    rotation_side_for_bond_policy,
)


class _Point:
    def __init__(self, x: float, y: float) -> None:
        self._x = x
        self._y = y

    def x(self) -> float:
        return self._x

    def y(self) -> float:
        return self._y


def test_rotation_side_policy_prefers_selected_side_then_fallback_size() -> None:
    bond = SimpleNamespace(a=1, b=2)

    assert rotation_side_for_bond_policy(
        bond,
        {1, 3, 4},
        {2, 5},
        {3},
        allow_fallback=False,
    ) == {1, 3, 4}
    assert rotation_side_for_bond_policy(
        bond,
        {1, 3},
        {2, 5, 6},
        set(),
        allow_fallback=True,
    ) == {2, 5, 6}
    assert (
        rotation_side_for_bond_policy(
            bond,
            {1, 3},
            {2, 5},
            set(),
            allow_fallback=False,
        )
        is None
    )


def test_preferred_rotation_side_policy_uses_coverage_distance_and_deterministic_fallback() -> (
    None
):
    bond = SimpleNamespace(a=1, b=2)
    atom_a = SimpleNamespace(x=0.0, y=0.0)
    atom_b = SimpleNamespace(x=10.0, y=0.0)

    assert preferred_rotation_side_for_bond_policy(
        bond,
        {1, 3, 4},
        {2, 5, 6},
        {3},
        atom_a=atom_a,
        atom_b=atom_b,
        allow_fallback=True,
    ) == {1, 3, 4}
    assert preferred_rotation_side_for_bond_policy(
        bond,
        {1, 3},
        {2, 4},
        {3, 4},
        atom_a=atom_a,
        atom_b=atom_b,
        press_pos=_Point(9.0, 0.0),
        bond_length_px=20.0,
        allow_fallback=True,
    ) == {2, 4}
    assert (
        preferred_rotation_side_for_bond_policy(
            bond,
            {1, 3},
            {2, 4},
            {3, 4},
            atom_a=atom_a,
            atom_b=atom_b,
            press_pos=_Point(5.0, 0.0),
            bond_length_px=20.0,
            allow_fallback=False,
        )
        is None
    )
    assert preferred_rotation_side_for_bond_policy(
        SimpleNamespace(a=2, b=1),
        {2, 4},
        {1, 3},
        set(),
        atom_a=atom_b,
        atom_b=atom_a,
        allow_fallback=True,
    ) == {1, 3}


def test_rotatable_axis_policy_preserves_single_bond_leaf_boundary_and_candidate_rules() -> (
    None
):
    bonds = [
        SimpleNamespace(a=1, b=2),
        SimpleNamespace(a=2, b=3),
        SimpleNamespace(a=1, b=4),
    ]

    assert rotatable_axis_from_selection_policy(
        set(),
        {0},
        bonds=bonds,
        bond_for_id=lambda bond_id: bonds[bond_id],
        bond_is_rotatable=lambda bond_id: bond_id == 0,
        preferred_rotation_side_for_bond=lambda *args, **kwargs: {2},
        rotation_side_for_bond=lambda *args, **kwargs: None,
    ) == (0, {2})
    assert rotatable_axis_from_selection_policy(
        set(),
        {0, 1},
        bonds=bonds,
        bond_for_id=lambda bond_id: bonds[bond_id],
        bond_is_rotatable=lambda bond_id: True,
        preferred_rotation_side_for_bond=lambda *args, **kwargs: None,
        rotation_side_for_bond=lambda bond_id, *args, **kwargs: (
            {1, 4} if bond_id == 0 else None
        ),
    ) == (0, {1, 4})
    assert rotatable_axis_from_selection_policy(
        {1},
        set(),
        bonds=bonds[:1],
        bond_for_id=lambda bond_id: bonds[bond_id],
        bond_is_rotatable=lambda bond_id: True,
        preferred_rotation_side_for_bond=lambda *args, **kwargs: None,
        rotation_side_for_bond=lambda *args, **kwargs: {2},
    ) == (0, {2})
    assert (
        rotatable_axis_from_selection_policy(
            set(),
            set(),
            bonds=bonds,
            bond_for_id=lambda bond_id: bonds[bond_id],
            bond_is_rotatable=lambda bond_id: True,
            preferred_rotation_side_for_bond=lambda *args, **kwargs: None,
            rotation_side_for_bond=lambda *args, **kwargs: None,
        )
        is None
    )


def test_axis_from_rotation_hint_policy_validates_rotatable_component_and_side() -> (
    None
):
    assert (
        axis_from_rotation_hint_policy(
            4,
            {1},
            bond_is_rotatable=lambda bond_id: False,
            bond_component_atoms=lambda bond_id: {1, 2},
            preferred_rotation_side_for_bond=lambda *args, **kwargs: {2},
        )
        is None
    )
    assert (
        axis_from_rotation_hint_policy(
            4,
            {9},
            bond_is_rotatable=lambda bond_id: True,
            bond_component_atoms=lambda bond_id: {1, 2},
            preferred_rotation_side_for_bond=lambda *args, **kwargs: {2},
        )
        is None
    )
    assert axis_from_rotation_hint_policy(
        4,
        {2, 9},
        bond_is_rotatable=lambda bond_id: True,
        bond_component_atoms=lambda bond_id: {1, 2, 3},
        preferred_rotation_side_for_bond=lambda *args, **kwargs: {2, 3},
    ) == (4, {2, 3})
