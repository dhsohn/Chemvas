from types import SimpleNamespace

from chemvas.domain.document import MoleculeModel
from chemvas.ui.canvas.canvas_rotation_state import CanvasRotationState
from chemvas.ui.molecule.atom_coords_access import (
    CanvasAtomCoords3DState,
    clear_atom_coords_3d_for,
    current_atom_coords_3d_for,
    pop_atom_coords_3d_for,
    set_atom_coords_3d_for,
    set_atom_coords_3d_for_id,
)
from tests.runtime_state import canvas_runtime_state


def _canvas_with_atom(x: float = 1.0, y: float = 2.0):
    atom = SimpleNamespace(x=x, y=y)
    return SimpleNamespace(
        model=MoleculeModel(atoms={1: atom}),
        renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
        runtime_state=canvas_runtime_state(
            atom_coords_3d_state=CanvasAtomCoords3DState(),
            rotation_state=CanvasRotationState(),
        ),
    )


def test_atom_coords_3d_state_for_uses_runtime_state() -> None:
    runtime_state = canvas_runtime_state(
        atom_coords_3d_state=CanvasAtomCoords3DState(
            atom_coords_3d={1: (1.0, 2.0, 3.0)}
        )
    )
    canvas = SimpleNamespace(runtime_state=runtime_state)

    assert (
        canvas.runtime_state.atom_coords_3d_state is runtime_state.atom_coords_3d_state
    )
    assert canvas.runtime_state.atom_coords_3d_state.atom_coords_3d == {
        1: (1.0, 2.0, 3.0)
    }


def test_atom_coords_3d_state_for_does_not_read_legacy_fake_canvas_attrs() -> None:
    coords = {1: (1.0, 2.0, 3.0)}
    canvas = SimpleNamespace(
        atom_coords_3d=coords,
        runtime_state=canvas_runtime_state(
            atom_coords_3d_state=CanvasAtomCoords3DState()
        ),
    )

    state = canvas.runtime_state.atom_coords_3d_state

    assert state.atom_coords_3d == {}
    assert canvas.runtime_state.atom_coords_3d_state.atom_coords_3d == {}
    assert canvas.runtime_state.atom_coords_3d_state.atom_coords_3d.get(1) is None


def test_atom_coords_3d_setters_update_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace(
        runtime_state=canvas_runtime_state(
            atom_coords_3d_state=CanvasAtomCoords3DState()
        )
    )

    set_atom_coords_3d_for(canvas, {1: (1.0, 2.0, 3.0)})
    set_atom_coords_3d_for_id(canvas, 2, (4.0, 5.0, 6.0))

    assert canvas.runtime_state.atom_coords_3d_state.atom_coords_3d == {
        1: (1.0, 2.0, 3.0),
        2: (4.0, 5.0, 6.0),
    }
    assert not hasattr(canvas, "atom_coords_3d")

    assert pop_atom_coords_3d_for(canvas, 1) == (1.0, 2.0, 3.0)
    assert canvas.runtime_state.atom_coords_3d_state.atom_coords_3d == {
        2: (4.0, 5.0, 6.0)
    }


def test_clear_atom_coords_3d_for_updates_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace(
        atom_coords_3d={1: (1.0, 2.0, 3.0)},
        runtime_state=canvas_runtime_state(
            atom_coords_3d_state=CanvasAtomCoords3DState(
                atom_coords_3d={1: (1.0, 2.0, 3.0)}
            )
        ),
    )

    clear_atom_coords_3d_for(canvas)

    assert canvas.runtime_state.atom_coords_3d_state.atom_coords_3d == {}
    assert canvas.atom_coords_3d == {1: (1.0, 2.0, 3.0)}


def test_current_atom_coords_3d_uses_stored_coords_when_projection_matches() -> None:
    canvas = _canvas_with_atom()
    set_atom_coords_3d_for_id(canvas, 1, (1.0, 2.0, 3.0))

    assert current_atom_coords_3d_for(canvas, 1) == (1.0, 2.0, 3.0)


def test_current_atom_coords_3d_falls_back_when_projection_is_stale() -> None:
    canvas = _canvas_with_atom()
    set_atom_coords_3d_for_id(canvas, 1, (40.0, 50.0, 3.0))

    assert current_atom_coords_3d_for(canvas, 1) == (1.0, 2.0, 0.0)
