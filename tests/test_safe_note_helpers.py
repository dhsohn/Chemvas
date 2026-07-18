from __future__ import annotations

from collections.abc import Callable

import pytest
from chemvas.ui import (
    canvas_color_mutation_service,
    insert_commit_rollback,
    insert_smiles_commit_service,
    insert_smiles_service,
    insert_template_commit_service,
    scene_clipboard_paste_service,
    selection_rotation_controller,
    selection_rotation_preview_transaction,
    structure_bond_build_service,
    structure_build_committer,
    structure_build_service,
    structure_insert_service,
)


class _BrokenAddNoteLookupInterrupt(KeyboardInterrupt):
    def __getattribute__(self, name: str):
        if name == "add_note":
            raise SystemExit("add_note lookup failed")
        return super().__getattribute__(name)


class _BrokenAddNoteLookupSystemExit(SystemExit):
    def __getattribute__(self, name: str):
        if name == "add_note":
            raise KeyboardInterrupt("add_note lookup failed")
        return super().__getattribute__(name)


_SECONDARY_ERROR = RuntimeError("secondary rollback failure")


def _note_helpers() -> tuple[tuple[str, Callable[[BaseException], None]], ...]:
    return (
        (
            "rotation_preview",
            lambda error: selection_rotation_preview_transaction._add_rollback_note(
                error,
                _SECONDARY_ERROR,
                phase="test",
            ),
        ),
        (
            "rotation_finalization",
            lambda error: (
                selection_rotation_controller._add_rotation_finalization_rollback_note(
                    error,
                    _SECONDARY_ERROR,
                )
            ),
        ),
        (
            "color",
            lambda error: canvas_color_mutation_service._add_color_rollback_note(
                error,
                _SECONDARY_ERROR,
                phase="test",
            ),
        ),
        (
            "insert",
            lambda error: insert_commit_rollback._add_insert_rollback_note(
                error,
                _SECONDARY_ERROR,
            ),
        ),
        (
            "smiles_load",
            lambda error: insert_smiles_service._add_smiles_load_rollback_note(
                error,
                _SECONDARY_ERROR,
                phase="test",
            ),
        ),
        (
            "smiles_commit",
            lambda error: insert_smiles_commit_service._add_insert_commit_rollback_note(
                error,
                "test",
            ),
        ),
        (
            "template_commit",
            lambda error: insert_template_commit_service._add_template_rollback_note(
                error,
                _SECONDARY_ERROR,
            ),
        ),
        (
            "bond_build",
            lambda error: structure_bond_build_service._add_bond_build_rollback_note(
                error,
                "test",
            ),
        ),
        (
            "recorded_build",
            lambda error: structure_build_service._add_recorded_build_rollback_note(
                error,
                _SECONDARY_ERROR,
            ),
        ),
        (
            "build_committer",
            lambda error: structure_build_committer._add_build_rollback_note(
                error,
                _SECONDARY_ERROR,
                phase="test",
            ),
        ),
        (
            "structure_insert",
            lambda error: structure_insert_service._add_structure_insert_rollback_note(
                error,
                "test",
            ),
        ),
        (
            "clipboard_paste",
            lambda error: scene_clipboard_paste_service._add_clipboard_rollback_note(
                error,
                _SECONDARY_ERROR,
                phase="test",
            ),
        ),
    )


@pytest.mark.parametrize(
    "primary_type",
    (_BrokenAddNoteLookupInterrupt, _BrokenAddNoteLookupSystemExit),
)
@pytest.mark.parametrize(
    ("_name", "invoke"), _note_helpers(), ids=lambda value: str(value)
)
def test_note_helper_contains_broken_add_note_lookup(
    _name: str,
    invoke: Callable[[BaseException], None],
    primary_type: type[BaseException],
) -> None:
    primary_error = primary_type("primary control-flow error")

    invoke(primary_error)

    assert isinstance(primary_error, primary_type)
