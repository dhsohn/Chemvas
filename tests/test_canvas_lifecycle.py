from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import chemvas.ui.canvas_lifecycle as lifecycle


class _FailingSignalBlocker:
    def __init__(self, failure_call: int | None) -> None:
        self.failure_call = failure_call
        self.calls = 0
        self.blocked = False

    def __call__(self, blocked: bool) -> None:
        self.calls += 1
        self.blocked = blocked
        if self.calls == self.failure_call:
            raise RuntimeError("signal block failed")


def test_schedule_canvas_deletion_survives_each_best_effort_cleanup_failure(
    monkeypatch,
) -> None:
    for failure_stage in ("scene", "initial_block", "clear", "final_block"):
        blocker = _FailingSignalBlocker(
            1
            if failure_stage == "initial_block"
            else 2
            if failure_stage == "final_block"
            else None
        )
        scene = SimpleNamespace(blockSignals=blocker)
        delete_later = mock.Mock()

        def scene_for_canvas(*, _failure_stage=failure_stage, _scene=scene):
            if _failure_stage == "scene":
                raise RuntimeError("scene lookup failed")
            return _scene

        canvas = SimpleNamespace(scene=scene_for_canvas, deleteLater=delete_later)
        clear_scene = mock.Mock(
            side_effect=RuntimeError("scene clear failed")
            if failure_stage == "clear"
            else None,
        )
        monkeypatch.setattr(lifecycle, "clear_scene_for", clear_scene)

        lifecycle.schedule_canvas_deletion_for(canvas)

        delete_later.assert_called_once_with()
        if failure_stage != "scene":
            assert blocker.blocked is True
