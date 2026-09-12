from __future__ import annotations

from contextlib import contextmanager

from chemvas.ui.scene_signal_blocking import blocked_scene_signals
from chemvas.ui.selection_service_access import refresh_selection_outline_for
from chemvas.ui.selection_style_state import selection_style_state_for


@contextmanager
def batch_selection_updates(canvas):
    """Coalesce intermediate selection paint; do not own document recovery.

    A failed operation leaves recovery to its existing caller/savepoint. In
    particular, do not repaint over the exact outline objects restored there.
    """
    state = selection_style_state_for(canvas)
    was_suspended = state.suspend_outline
    with blocked_scene_signals(canvas.scene()):
        state.suspend_outline = True
        try:
            yield
        finally:
            state.suspend_outline = was_suspended
    if not was_suspended:
        refresh_selection_outline_for(canvas)


__all__ = ["batch_selection_updates"]
