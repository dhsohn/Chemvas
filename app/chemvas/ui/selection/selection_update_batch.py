from __future__ import annotations

from contextlib import contextmanager

from chemvas.ui.scene.scene_signal_blocking import blocked_scene_signals
from chemvas.ui.selection.selection_state import selection_for, selection_state_for


@contextmanager
def batch_selection_updates(canvas):
    """Coalesce intermediate selection paint; do not own document recovery.

    A failed operation leaves recovery to its existing caller/savepoint. In
    particular, do not repaint over the exact outline objects restored there.
    """
    state = selection_state_for(canvas)
    was_suspended = state.suspend_outline
    with blocked_scene_signals(canvas.scene()):
        state.suspend_outline = True
        try:
            yield
        finally:
            state.suspend_outline = was_suspended
    if not was_suspended:
        selection_for(canvas).update_selection_outline()


__all__ = ["batch_selection_updates"]
