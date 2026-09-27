from __future__ import annotations

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from chemvas.core.history import history_transaction_scope
from chemvas.domain.transactions import RestoreOutcome
from chemvas.ui.canvas.canvas_style_controller import TextStyleChange
from chemvas.ui.history.history_commands import (
    SetAnnotationSettingsCommand,
    SetNoteTextCommand,
    SetTextStyleCommand,
)
from chemvas.ui.scene.note_item_access import NoteTextState


def _note_state(text):
    return NoteTextState(
        html=text,
        cursor_anchor=0,
        cursor_position=0,
        interaction_flags=Qt.TextInteractionFlag.NoTextInteraction,
        default_text_color=QColor("black"),
        committed_text=text,
        committed_html=text,
    )


@pytest.fixture(params=["note", "text", "annotation"])
def style_command(request):
    if request.param == "note":
        return (
            SetNoteTextCommand(_note_state("before"), _note_state("after"), 17),
            "restore_note_text",
            (17,),
        )
    if request.param == "text":
        return (
            SetTextStyleCommand(
                TextStyleChange({"text_font_size": 10}, ()),
                TextStyleChange({"text_font_size": 12}, ()),
            ),
            "restore_text_style",
            (),
        )
    return (
        SetAnnotationSettingsCommand(
            {"arrow_line_width": 1.0}, {"arrow_line_width": 2.0}
        ),
        "restore_annotation_settings",
        (),
    )


def test_style_command_roundtrip_keeps_payload_and_note_id(style_command):
    command, method, prefix = style_command
    calls = []
    operations = SimpleNamespace(**{method: lambda *args: calls.append(args)})
    command.undo(operations)
    command.redo(operations)
    assert calls == [(*prefix, command.before_state), (*prefix, command.after_state)]


@pytest.mark.parametrize("direction", ["undo", "redo"])
@pytest.mark.parametrize("owner", ["headless", "exact", "outer", "failed_restore"])
def test_style_failure_preserves_rollback_owner(style_command, direction, owner):
    command, method, prefix = style_command
    original_error = RuntimeError("style application failed after mutation")
    calls = []
    restored = []
    released = []

    def mutate(*args):
        calls.append(args)
        if len(calls) == 1:
            raise original_error

    operations = SimpleNamespace(**{method: mutate})
    if owner in {"exact", "failed_restore"}:
        snapshot = object()

        def restore(value):
            restored.append(value)
            if owner == "failed_restore":
                raise RuntimeError("restore failed after partial mutation")
            return RestoreOutcome(authoritative=True)

        operations.capture_history_transaction_for_history = lambda: snapshot
        operations.restore_history_transaction_for_history = restore
        operations.release_history_transaction_for_history = released.append

    with pytest.raises(RuntimeError) as caught:
        if owner == "outer":
            with history_transaction_scope(operations):
                getattr(command, direction)(operations)
        else:
            getattr(command, direction)(operations)
    assert caught.value is original_error
    attempted, inverse = (
        (command.before_state, command.after_state)
        if direction == "undo"
        else (command.after_state, command.before_state)
    )
    assert calls == [(*prefix, attempted)] + (
        [(*prefix, inverse)] if owner == "headless" else []
    )
    assert restored == ([snapshot] if owner in {"exact", "failed_restore"} else [])
    assert released == []
    if owner == "failed_restore":
        assert "restore failed" in " ".join(original_error.__notes__)
