from __future__ import annotations


def add_history_rollback_error_note(
    original_error: BaseException,
    rollback_error: BaseException,
    *,
    phase: str,
) -> None:
    """Attach a secondary UI-history failure without replacing the primary."""

    try:
        add_note = getattr(original_error, "add_note", None)
        if not callable(add_note):
            return
        add_note(
            "UI history rollback also encountered an error during "
            f"{phase}: {type(rollback_error).__name__}: {rollback_error}"
        )
    except BaseException:
        # Reporting a rollback failure must never replace the primary control-
        # flow exception that triggered the rollback.
        return


__all__ = ["add_history_rollback_error_note"]
