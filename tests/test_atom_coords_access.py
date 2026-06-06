from types import SimpleNamespace

from ui.atom_coords_access import (
    CanvasAtomCoords3DState,
    atom_coords_3d_for,
    atom_coords_3d_for_id,
    atom_coords_3d_state_for,
    clear_atom_coords_3d_for,
    current_atom_coords_3d_for,
    pop_atom_coords_3d_for,
    set_atom_coords_3d_for,
    set_atom_coords_3d_for_id,
)


def _canvas_with_atom(x: float = 1.0, y: float = 2.0):
    atom = SimpleNamespace(x=x, y=y)
    return SimpleNamespace(
        model=SimpleNamespace(atoms={1: atom}),
        renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
    )


def test_atom_coords_3d_state_for_uses_runtime_state() -> None:
    runtime_state = SimpleNamespace(
        atom_coords_3d_state=CanvasAtomCoords3DState(atom_coords_3d={1: (1.0, 2.0, 3.0)})
    )
    canvas = SimpleNamespace(runtime_state=runtime_state)

    assert atom_coords_3d_state_for(canvas) is runtime_state.atom_coords_3d_state
    assert atom_coords_3d_for(canvas) == {1: (1.0, 2.0, 3.0)}


def test_atom_coords_3d_state_for_does_not_read_legacy_fake_canvas_attrs() -> None:
    coords = {1: (1.0, 2.0, 3.0)}
    canvas = SimpleNamespace(atom_coords_3d=coords)

    state = atom_coords_3d_state_for(canvas)

    assert state.atom_coords_3d == {}
    assert atom_coords_3d_for(canvas) == {}
    assert atom_coords_3d_for_id(canvas, 1) is None


def test_atom_coords_3d_setters_update_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace()

    set_atom_coords_3d_for(canvas, {1: (1.0, 2.0, 3.0)})
    set_atom_coords_3d_for_id(canvas, 2, (4.0, 5.0, 6.0))

    assert atom_coords_3d_for(canvas) == {1: (1.0, 2.0, 3.0), 2: (4.0, 5.0, 6.0)}
    assert not hasattr(canvas, "atom_coords_3d")

    assert pop_atom_coords_3d_for(canvas, 1) == (1.0, 2.0, 3.0)
    assert atom_coords_3d_for(canvas) == {2: (4.0, 5.0, 6.0)}


def test_clear_atom_coords_3d_for_updates_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace(atom_coords_3d={1: (1.0, 2.0, 3.0)})

    clear_atom_coords_3d_for(canvas)

    assert atom_coords_3d_for(canvas) == {}
    assert canvas.atom_coords_3d == {1: (1.0, 2.0, 3.0)}


def test_current_atom_coords_3d_uses_stored_coords_when_projection_matches() -> None:
    canvas = _canvas_with_atom()
    set_atom_coords_3d_for_id(canvas, 1, (1.0, 2.0, 3.0))

    assert current_atom_coords_3d_for(canvas, 1) == (1.0, 2.0, 3.0)


def test_current_atom_coords_3d_falls_back_when_projection_is_stale() -> None:
    canvas = _canvas_with_atom()
    set_atom_coords_3d_for_id(canvas, 1, (40.0, 50.0, 3.0))

    assert current_atom_coords_3d_for(canvas, 1) == (1.0, 2.0, 0.0)
