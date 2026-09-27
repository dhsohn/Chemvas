from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication
from scripts import benchmark_editor


@pytest.mark.parametrize("operation", ["move", "delete", "paste"])
def test_benchmark_varies_edit_size_independently_of_document(operation, monkeypatch):
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    created = []
    snapshots = []
    create = benchmark_editor.CanvasView
    measure = benchmark_editor.measure

    def create_canvas(**kwargs):
        canvas = create(**kwargs)
        created.append(canvas)
        return canvas

    def measure_and_snapshot(action):
        result = measure(action)
        snapshots.append(
            created[0].services.canvas_document_session_service.snapshot_state()
        )
        return result

    monkeypatch.setattr(benchmark_editor, "CanvasView", create_canvas)
    monkeypatch.setattr(benchmark_editor, "measure", measure_and_snapshot)
    state = benchmark_editor.document_state(20)
    result = benchmark_editor.exercise(
        app, state, operation, edited_atoms=3, paste_atoms=2
    )
    assert len(result) == 3
    assert all(captures == 1 for _, captures in result.values())
    edited = snapshots[0]["model"]["atoms"]
    original = snapshots[1]["model"]["atoms"]
    assert len(original) == 20
    if operation == "paste":
        assert len(edited) == 22
        assert sum(atom["element"] == "N" for atom in edited.values()) == 2
    elif operation == "delete":
        assert set(original) - set(edited) == {0, 1, 2}
    else:
        assert {
            atom_id for atom_id in original if original[atom_id] != edited[atom_id]
        } == {0, 1, 2}
