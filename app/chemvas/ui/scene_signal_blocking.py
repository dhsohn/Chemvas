from __future__ import annotations

from contextlib import contextmanager

_USE_LIVE_SCENE_PORT = object()


@contextmanager
def blocked_scene_signals(
    scene,
    *,
    block_signals=_USE_LIVE_SCENE_PORT,
    signals_blocked=_USE_LIVE_SCENE_PORT,
):
    """Temporarily block a scene's signals, restoring the prior state.

    Callers that already captured scene ports may inject them; omitting the
    keyword arguments uses the scene's live ``blockSignals``/``signalsBlocked``.
    Ports are captured once for the whole context. Without a usable state
    getter, the prior state comes from the setter's return value.
    """
    if block_signals is _USE_LIVE_SCENE_PORT:
        block_signals = getattr(scene, "blockSignals", None)
    if not callable(block_signals):
        raise RuntimeError("scene does not expose a signal-blocking setter")
    if signals_blocked is _USE_LIVE_SCENE_PORT:
        signals_blocked = getattr(scene, "signalsBlocked", None)
    if callable(signals_blocked):
        previous = bool(signals_blocked())
        block_signals(True)
    else:
        previous = bool(block_signals(True))
    try:
        yield
    finally:
        block_signals(previous)


__all__ = ["blocked_scene_signals"]
