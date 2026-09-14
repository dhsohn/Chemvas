"""Core history executes bound operations without discovering a UI or canvas."""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest

from chemvas.core import history
from chemvas.domain.transactions import RestoreOutcome
from tests.subprocess_support import source_subprocess_env

FAMILIES = (
    "move",
    "positions",
    "rings",
    "length",
    "smiles",
    "add-atoms",
    "delete-atoms",
    "atom-color",
    "add-bond",
    "delete-bond",
    "update-bond",
)
ATOMS = {
    4: {"element": "N", "x": 3.0, "y": 7.0},
    2: {"element": "C", "x": 8.0, "y": 5.0},
}
COORDS = {4: (3.0, 7.0, 1.25), 2: (8.0, 5.0, -2.5)}
FRAME = ((1.0, 2.0, 3.0), (4.0, 5.0))
BEFORE_BOND = {"a": 4, "b": 2, "order": 1, "style": "single", "color": "#123456"}
AFTER_BOND = {**BEFORE_BOND, "order": 2, "style": "double"}


def _call(name, *args, **kwargs):
    return name + "_for_history", args, kwargs


def _family_case(kind):
    """Literal payloads and expected calls, independent of command execution."""
    before_smiles = _call("set_last_smiles_input", "before")
    after_smiles = _call("set_last_smiles_input", "after")
    if kind == "move":
        command = history.MoveAtomsCommand(
            atom_ids={4, 2}, dx=1.25, dy=-2.5, bond_ids={3}, redraw_bond_ids={8}
        )
        kwargs = dict(bond_ids={3}, redraw_bond_ids={8}, update_selection=True)
        return (
            command,
            [_call("move_atoms", {4, 2}, 1.25, -2.5, **kwargs)],
            [_call("move_atoms", {4, 2}, -1.25, 2.5, **kwargs)],
        )
    if kind == "positions":
        before, after = {4: (3.0, 7.0)}, {4: (10.0, 11.0)}
        target_coords = {4: (10.0, 11.0, 1.25)}
        command = history.SetAtomPositionsCommand(
            before_positions=before,
            after_positions=after,
            before_coords_3d={4: COORDS[4]},
            after_coords_3d=target_coords,
            update_selection=False,
            restore_projection_state=True,
            before_projection_center_3d=FRAME[0],
            before_projection_anchor_2d=FRAME[1],
            after_projection_center_3d=None,
            after_projection_anchor_2d=None,
        )
        return (
            command,
            [
                _call("restore_projection_state", None, None),
                _call(
                    "set_atom_positions",
                    after,
                    update_selection=False,
                    coords_3d=target_coords,
                ),
            ],
            [
                _call("restore_projection_state", *FRAME),
                _call(
                    "set_atom_positions",
                    before,
                    update_selection=False,
                    coords_3d={4: COORDS[4]},
                ),
            ],
        )
    if kind == "rings":
        handles, before, after = (
            ["opaque-ring"],
            [[(1.0, 2.0), (3.0, 4.0)]],
            [[(5.0, 6.0), (7.0, 8.0)]],
        )
        return (
            history.SetRingPolygonsCommand(handles, before, after),
            [_call("set_ring_polygons", handles, after)],
            [_call("set_ring_polygons", handles, before)],
        )
    if kind == "length":
        return (
            history.UpdateBondLengthCommand(18.0, 36.0),
            [_call("restore_bond_length", 36.0)],
            [_call("restore_bond_length", 18.0)],
        )
    if kind == "smiles":
        return (
            history.SetSmilesInputCommand("before", "after"),
            [after_smiles],
            [before_smiles],
        )
    if kind in {"add-atoms", "delete-atoms"}:
        restore = [
            _call("restore_atom_from_state", atom_id, state)
            for atom_id, state in ATOMS.items()
        ]
        restore.append(
            _call("set_atom_positions", {}, update_selection=False, coords_3d=COORDS)
        )
        remove = [_call("remove_atom", atom_id) for atom_id in ATOMS]
        present = [_call("set_next_atom_id", 8), after_smiles]
        absent = [_call("set_next_atom_id", 1), before_smiles]
        common = dict(atom_states=deepcopy(ATOMS), atom_coords_3d=deepcopy(COORDS))
        if kind == "add-atoms":
            command = history.AddAtomsCommand(
                **common,
                before_next_atom_id=1,
                after_next_atom_id=8,
                before_smiles_input="before",
                after_smiles_input="after",
            )
            return command, [*restore, *present], [*remove, *absent]
        mark = {"kind": "plus", "atom_id": 4, "color": "#234567"}
        command = history.DeleteAtomsCommand(
            **common,
            mark_states=[mark],
            before_next_atom_id=8,
            after_next_atom_id=1,
            before_smiles_input="after",
            after_smiles_input="before",
            restore_projection_state=True,
            before_projection_center_3d=FRAME[0],
            before_projection_anchor_2d=FRAME[1],
        )
        return (
            command,
            [
                *[
                    _call("remove_atom", atom_id, remove_marks=True)
                    for atom_id in ATOMS
                ],
                _call("restore_projection_state", None, None),
                *absent,
            ],
            [
                _call("restore_projection_state", *FRAME),
                *restore,
                _call("restore_mark_from_state", mark),
                *present,
            ],
        )
    if kind == "atom-color":
        return (
            history.UpdateAtomColorCommand(4, "#123456", "#654321"),
            [_call("apply_atom_color", 4, "#654321")],
            [_call("apply_atom_color", 4, "#123456")],
        )
    if kind == "add-bond":
        return (
            history.AddBondCommand(3, BEFORE_BOND, 3, "before", "after"),
            [_call("restore_bond_from_state", 3, BEFORE_BOND), after_smiles],
            [_call("remove_bond", 3), _call("trim_bonds", 3), before_smiles],
        )
    if kind == "delete-bond":
        return (
            history.DeleteBondCommand(3, BEFORE_BOND, "before", "after"),
            [_call("remove_bond", 3), after_smiles],
            [_call("restore_bond_from_state", 3, BEFORE_BOND), before_smiles],
        )
    assert kind == "update-bond"
    return (
        history.UpdateBondCommand(3, BEFORE_BOND, AFTER_BOND, "before", "after"),
        [_call("restore_bond_from_state", 3, AFTER_BOND), after_smiles],
        [_call("restore_bond_from_state", 3, BEFORE_BOND), before_smiles],
    )


def _recording_operations(expected):
    calls = []

    def record(name, *args, **kwargs):
        calls.append((name, deepcopy(args), deepcopy(kwargs)))

    # Expose only the operations this family actually invokes. There is no
    # catch-all lookup, canvas/model attribute, runtime bundle, or UI resolver.
    operations = SimpleNamespace(
        **{name: partial(record, name) for name, _args, _kwargs in expected}
    )
    return operations, calls


def _run_family(kind, direction):
    command, redo, undo = _family_case(kind)
    expected = redo if direction == "redo" else undo
    operations, calls = _recording_operations(expected)
    payload = deepcopy(vars(command))
    getattr(command, direction)(operations)
    assert calls == expected
    assert vars(command) == payload
    return calls


@pytest.mark.parametrize("kind", FAMILIES)
@pytest.mark.parametrize("direction", ["undo", "redo"])
def test_each_core_family_uses_only_its_bound_operations(kind, direction):
    _run_family(kind, direction)


def test_every_core_family_executes_with_ui_and_qt_imports_blocked():
    script = """
import importlib.abc
import json
import runpy
import sys
class BlockUI(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('chemvas.ui', 'chemvas.bootstrap', 'PyQt6', 'rdkit')):
            raise AssertionError('forbidden dependency: ' + fullname)
sys.meta_path.insert(0, BlockUI())
namespace = runpy.run_path(sys.argv[1])
for kind in namespace['FAMILIES']:
    for direction in ('undo', 'redo'):
        namespace['_run_family'](kind, direction)
assert not any(name.startswith(('chemvas.ui', 'PyQt6', 'rdkit')) for name in sys.modules)
print(json.dumps({'cases': len(namespace['FAMILIES']) * 2, 'source': namespace['history'].__file__}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(Path(__file__).resolve())],
        env=source_subprocess_env({"PYTHONDONTWRITEBYTECODE": "1"}),
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "cases": 22,
        "source": str(Path(history.__file__).resolve()),
    }


def _exact_operations():
    state = {"bond": deepcopy(BEFORE_BOND), "smiles": "before"}
    events = []

    def capture():
        events.append("capture")
        return deepcopy(state)

    def restore(snapshot):
        events.append("restore")
        state.clear()
        state.update(deepcopy(snapshot))
        return RestoreOutcome(authoritative=True)

    def release(snapshot):
        assert snapshot == {"bond": BEFORE_BOND, "smiles": "before"} or snapshot == {
            "bond": AFTER_BOND,
            "smiles": "after",
        }
        events.append("release")

    def bond_state(bond_id, value):
        assert bond_id == 3
        events.append("bond")
        state["bond"] = deepcopy(value)

    def smiles(value):
        events.append("smiles")
        state["smiles"] = value

    operations = SimpleNamespace(
        capture_history_transaction_for_history=capture,
        restore_history_transaction_for_history=restore,
        release_history_transaction_for_history=release,
        restore_bond_from_state_for_history=bond_state,
        set_last_smiles_input_for_history=smiles,
    )
    return operations, state, events


def test_nested_composite_captures_once_per_bound_receiver():
    operations, state, events = _exact_operations()
    command, _redo, _undo = _family_case("update-bond")
    composite = history.CompositeCommand([history.CompositeCommand([command])])
    composite.redo(operations)
    assert state == {"bond": AFTER_BOND, "smiles": "after"}
    assert events == ["capture", "bond", "smiles", "release"]
    events.clear()
    composite.undo(operations)
    assert state == {"bond": BEFORE_BOND, "smiles": "before"}
    assert events == ["capture", "bond", "smiles", "release"]


def test_transaction_scope_is_receiver_local_and_resets_after_exception():
    first, first_state, first_events = _exact_operations()
    second, second_state, second_events = _exact_operations()
    command, _redo, _undo = _family_case("update-bond")
    with pytest.raises(RuntimeError, match="end scope"):
        with history.history_transaction_scope(first):
            command.redo(first)
            command.redo(second)
            raise RuntimeError("end scope")
    assert first_state == second_state == {"bond": AFTER_BOND, "smiles": "after"}
    assert first_events == ["bond", "smiles"]
    assert second_events == ["capture", "bond", "smiles", "release"]
    first_events.clear()
    command.undo(first)
    assert first_state == {"bond": BEFORE_BOND, "smiles": "before"}
    assert first_events == ["capture", "bond", "smiles", "release"]


def test_mixed_composite_compensates_external_state_before_exact_restore():
    operations, state, events = _exact_operations()
    outside = []
    primary = RuntimeError("SMILES operation failed after bond mutation")

    class ExternalCommand(history.HistoryCommand):
        def redo(self, receiver):
            assert receiver is operations
            outside.append("external")
            events.append("external-redo")

        def undo(self, receiver):
            assert receiver is operations
            outside.pop()
            events.append("external-undo")

    def fail_smiles(value):
        assert value == "after"
        events.append("smiles-failure")
        raise primary

    operations.set_last_smiles_input_for_history = fail_smiles
    child, _redo, _undo = _family_case("update-bond")
    composite = history.CompositeCommand([ExternalCommand(), child])
    with pytest.raises(RuntimeError) as caught:
        composite.redo(operations)
    assert caught.value is primary
    assert outside == []
    assert state == {"bond": BEFORE_BOND, "smiles": "before"}
    assert events == [
        "capture",
        "external-redo",
        "bond",
        "smiles-failure",
        "external-undo",
        "restore",
    ]
    assert not getattr(primary, "__notes__", [])
