"""Atom lifecycle commands use bound operations, not a concrete canvas model."""

from copy import deepcopy

import pytest

from chemvas.core import model_commands

ATOMS = {
    4: {"element": "N", "x": 1.25, "y": -2.5, "color": "#123456"},
    2: {"element": "C", "x": -3.5, "y": 4.25, "explicit_label": True},
}
COORDS = {4: (1.25, -2.5, 6.0), 2: (-3.5, 4.25, -8.0)}
MARK = {"kind": "plus", "atom_id": 4, "color": "#654321", "dx": 2.5, "dy": -4.0}
FRAME = ((2.0, 3.0, 4.0), (5.0, 6.0))


class _AtomOperations:
    """No runtime/savepoint capability: exercise the existing inverse path."""

    def __init__(self, state, id_errors):
        self.state = deepcopy(state)
        self.calls = []
        self.id_errors = list(id_errors)

    def remove_atom_for_history(self, atom_id, *, remove_marks=True):
        self.calls.append(("remove", atom_id, remove_marks))
        self.state["atoms"].pop(atom_id, None)
        self.state["coords"].pop(atom_id, None)
        if remove_marks:
            self.state["marks"] = [
                mark for mark in self.state["marks"] if mark["atom_id"] != atom_id
            ]

    def restore_atom_from_state_for_history(self, atom_id, state):
        self.calls.append(("restore", atom_id, deepcopy(state)))
        self.state["atoms"][atom_id] = deepcopy(state)

    def set_atom_positions_for_history(self, positions, *, update_selection, coords_3d):
        self.calls.append(("coords", positions, update_selection, deepcopy(coords_3d)))
        assert positions == {} and update_selection is False
        self.state["coords"].update(deepcopy(coords_3d))

    def restore_projection_state_for_history(self, center, anchor):
        self.calls.append(("projection", center, anchor))
        self.state["projection"] = (center, anchor)

    def restore_mark_from_state_for_history(self, mark):
        self.calls.append(("mark", deepcopy(mark)))
        self.state["marks"].append(deepcopy(mark))

    def set_next_atom_id_for_history(self, atom_id):
        self.calls.append(("next", atom_id))
        self.state["next_id"] = atom_id
        # A real operation can mutate before failing. The second injected
        # failure also occurs after restoration; it must still be reported.
        if self.id_errors:
            raise self.id_errors.pop(0)

    def set_last_smiles_input_for_history(self, value):
        self.calls.append(("smiles", value))
        self.state["smiles"] = value


def _state(kind, present):
    state = {
        "atoms": {0: {"element": "O", "x": 100.5, "y": -80.25}},
        "coords": {0: (100.5, -80.25, 9.0)},
        "marks": [{"kind": "minus", "atom_id": None, "x": 75.0, "y": 83.0}],
        "projection": FRAME if kind == "add" or present else (None, None),
        "next_id": 8 if present else 3,
        "smiles": "occupied" if present else "empty",
    }
    if present:
        state["atoms"].update(deepcopy(ATOMS))
        state["coords"].update(COORDS)
        if kind == "delete":
            state["marks"].append(deepcopy(MARK))
    return state


def _command(kind):
    common = {"atom_states": deepcopy(ATOMS), "atom_coords_3d": dict(COORDS)}
    if kind == "add":
        return model_commands.AddAtomsCommand(
            **common,
            before_next_atom_id=3,
            after_next_atom_id=8,
            before_smiles_input="empty",
            after_smiles_input="occupied",
        )
    return model_commands.DeleteAtomsCommand(
        **common,
        mark_states=[deepcopy(MARK)],
        before_next_atom_id=8,
        after_next_atom_id=3,
        before_smiles_input="occupied",
        after_smiles_input="empty",
        restore_projection_state=True,
        before_projection_center_3d=FRAME[0],
        before_projection_anchor_2d=FRAME[1],
        after_projection_center_3d=None,
        after_projection_anchor_2d=None,
    )


def _expected_calls(kind, restoring):
    # These lists encode the operation contract independently of the command.
    restore = [
        ("restore", 4, ATOMS[4]),
        ("restore", 2, ATOMS[2]),
        ("coords", {}, False, COORDS),
    ]
    remove = [("remove", 4, True), ("remove", 2, True)]
    normalize = [("remove", 2, True), ("remove", 4, True)]
    if kind == "delete":
        restore = [("projection", *FRAME), *restore, ("mark", MARK)]
        remove.append(("projection", None, None))
    present_tail = [("next", 8), ("smiles", "occupied")]
    absent_tail = [("next", 3), ("smiles", "empty")]
    if restoring:
        compensation = normalize
        if kind == "delete":
            compensation = [*compensation, ("projection", None, None)]
        return [*restore, *present_tail], [*compensation, *absent_tail]
    return [*remove, *absent_tail], [*normalize, *restore, *present_tail]


@pytest.mark.parametrize(
    "kind,direction",
    [("add", "undo"), ("add", "redo"), ("delete", "undo"), ("delete", "redo")],
)
@pytest.mark.parametrize("failure", ["none", "id-setter", "compensation-note"])
def test_atom_lifecycle_uses_only_operations_and_preserves_failure(
    kind, direction, failure
):
    restoring = (kind, direction) in {("add", "redo"), ("delete", "undo")}
    before, after = _state(kind, not restoring), _state(kind, restoring)
    primary = RuntimeError("next id failed after mutation")
    secondary = RuntimeError("next id compensation also failed after mutation")
    errors = [] if failure == "none" else [primary]
    if failure == "compensation-note":
        errors.append(secondary)
    port = _AtomOperations(before, errors)
    command = _command(kind)
    original_command = deepcopy(vars(command))
    operation = getattr(command, direction)
    forward, compensation = _expected_calls(kind, restoring)

    if failure == "none":
        operation(port)
        assert port.calls == forward
        assert port.state == after
    else:
        with pytest.raises(RuntimeError) as caught:
            operation(port)
        assert caught.value is primary
        assert port.calls == [*forward[:-1], *compensation]
        assert port.state == before
        notes = getattr(primary, "__notes__", [])
        if failure == "compensation-note":
            assert len(notes) == 1
            assert "restoring the next atom id" in notes[0]
            assert str(secondary) in notes[0]
        else:
            assert notes == []
        # Retry after the one-shot errors have been consumed. This does not
        # claim that an operation whose recovery still fails is safe to retry.
        assert port.id_errors == []
        port.calls.clear()
        operation(port)
        assert port.calls == forward
        assert port.state == after
        assert caught.value is primary
    assert vars(command) == original_command
