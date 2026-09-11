"""User-facing, undoable sheet setup above the low-level document setter."""

from chemvas.ui.canvas_service_ports import history_service_for_access
from chemvas.ui.canvas_window_access import notify_document_change_for
from chemvas.ui.history_commands import SetSheetSetupCommand
from chemvas.ui.sheet_setup_access import (
    _run_sheet_setup_transaction,
    set_sheet_setup_for,
    sheet_setup_for,
)
from chemvas.ui.sheet_setup_logic import normalize_sheet_setup


def change_sheet_setup_for(canvas, size_name: str, orientation: str) -> None:
    before = sheet_setup_for(canvas)
    after = normalize_sheet_setup(size_name, orientation)
    if before == after:
        return
    history = history_service_for_access(canvas)
    history_snapshot = history.capture_stack_snapshot()

    def apply() -> None:
        set_sheet_setup_for(canvas, *after)
        committed = history.push(
            SetSheetSetupCommand(before, after, set_sheet_setup_for)
        )
        if committed is False and history_snapshot.enabled:
            raise RuntimeError("Sheet setup history push did not commit")
        if not committed:
            notify_document_change_for(canvas)

    try:
        _run_sheet_setup_transaction(canvas, apply)
    except Exception as error:
        history.restore_stack_snapshot(
            history_snapshot, error, phase="restoring failed sheet-size history"
        )
        raise
