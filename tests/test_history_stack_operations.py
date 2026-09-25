"""Stack policy needs bound operations and state, not a canvas fixture."""

from __future__ import annotations

import json
import subprocess
import sys
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from chemvas.core.model_commands import UpdateAtomColorCommand, UpdateBondCommand
from chemvas.domain.transactions import RestoreOutcome
from chemvas.ui.canvas.canvas_history_service import CanvasHistoryService
from chemvas.ui.canvas.canvas_history_state import CanvasHistoryState
from tests.subprocess_support import source_subprocess_env


def test_relative_stack_replay_needs_only_one_bound_operation():
    values = []
    operations = SimpleNamespace(
        apply_atom_color_for_history=lambda atom, color: values.append(color)
    )
    state = CanvasHistoryState()
    service = CanvasHistoryService(operations, state, replay_context=nullcontext)
    command = UpdateAtomColorCommand(1, "red", "blue")
    command.redo(operations)
    assert service.push(command)
    service.undo()
    assert state.history == []
    assert state.redo_stack == [command]
    service.redo()
    assert state.history == [command]
    assert state.redo_stack == []
    assert values == ["blue", "red", "blue"]
    assert service.operations is operations
    assert not hasattr(service, "canvas")


@pytest.mark.parametrize("direction", ["undo", "redo"])
@pytest.mark.parametrize("authoritative", [True, False])
def test_exact_stack_failure_keeps_its_policy_without_a_canvas(
    direction, authoritative
):
    command = UpdateBondCommand(
        3,
        {"order": 1},
        {"order": 2},
    )
    initial = {"bond": {"order": 2}} if direction == "undo" else {"bond": {"order": 1}}
    document = deepcopy(initial)
    events = []
    primary = RuntimeError("failed after bond mutation")

    def capture(*, history_service, guard_scene_rect):
        assert history_service is None
        assert guard_scene_rect is True
        events.append("capture")
        return deepcopy(document)

    def bond(bond_id, value):
        assert bond_id == 3
        document["bond"] = deepcopy(value)
        events.append("bond")
        raise primary

    def restore(snapshot):
        document.clear()
        document.update(snapshot)
        events.append("restore")
        return RestoreOutcome(authoritative=authoritative)

    operations = SimpleNamespace(
        capture_history_transaction_for_history=capture,
        restore_history_transaction_for_history=restore,
        restore_bond_from_state_for_history=bond,
    )
    state = CanvasHistoryState(
        history=[command] if direction == "undo" else [],
        redo_stack=[command] if direction == "redo" else [],
    )
    original_history, original_redo = tuple(state.history), tuple(state.redo_stack)
    service = CanvasHistoryService(operations, state, replay_context=nullcontext)
    with pytest.raises(RuntimeError) as caught:
        getattr(service, direction)()
    assert caught.value is primary
    assert document == initial
    assert events == ["capture", "bond", "restore"]
    assert tuple(state.history) == (original_history if authoritative else ())
    assert tuple(state.redo_stack) == (original_redo if authoritative else ())


def test_stack_policy_runs_with_all_qt_and_ui_implementations_blocked():
    script = """
import importlib.abc
import json
import runpy
import sys
allowed_ui = {'chemvas.ui', 'chemvas.ui.canvas', 'chemvas.ui.canvas.canvas_history_service', 'chemvas.ui.canvas.canvas_history_state'}
class BlockImplementation(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (fullname.startswith('chemvas.ui') and fullname not in allowed_ui) or fullname.startswith(('PyQt6', 'rdkit', 'chemvas.bootstrap', 'chemvas.adapters')):
            raise AssertionError('forbidden dependency: ' + fullname)
sys.meta_path.insert(0, BlockImplementation())
namespace = runpy.run_path(sys.argv[1])
namespace['test_relative_stack_replay_needs_only_one_bound_operation']()
for direction in ('undo', 'redo'):
    for authoritative in (True, False):
        namespace['test_exact_stack_failure_keeps_its_policy_without_a_canvas'](direction, authoritative)
assert not any(name.startswith(('PyQt6', 'rdkit', 'chemvas.adapters')) for name in sys.modules)
print(json.dumps({'cases': 5, 'source': namespace['CanvasHistoryService'].__module__}))
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
        "cases": 5,
        "source": "chemvas.ui.canvas.canvas_history_service",
    }
