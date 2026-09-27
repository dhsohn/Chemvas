"""Canvas lookups for the scene, format versions, deletion and input controllers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

import chemvas.ui.canvas.canvas_lifecycle as lifecycle
from chemvas.domain.document import CANVAS_FILE_VERSION, CLIPBOARD_SELECTION_VERSION
from chemvas.ui.canvas.canvas_format_access import (
    clipboard_selection_version_for,
    file_format_version_for,
)
from chemvas.ui.canvas.canvas_scene_state import optional_canvas_scene_for
from chemvas.ui.canvas.canvas_view_ports import (
    input_controller_for_view,
    pointer_controller_for_view,
)
from tests.runtime_services import canvas_runtime_services


def test_canvas_scene_state_returns_canvas_scene() -> None:
    scene = object()
    canvas = mock.Mock()
    canvas.scene.return_value = scene

    assert canvas.scene() is scene
    assert optional_canvas_scene_for(canvas) is scene


def test_optional_canvas_scene_state_tolerates_deleted_qt_scene() -> None:
    canvas = mock.Mock()
    canvas.scene.side_effect = RuntimeError("deleted")

    assert optional_canvas_scene_for(canvas) is None


def test_canvas_format_accessors_return_canvas_format_constants() -> None:
    canvas = SimpleNamespace(
        FILE_FORMAT_VERSION=CANVAS_FILE_VERSION,
        CLIPBOARD_SELECTION_MIME="application/x-test-selection",
        CLIPBOARD_SELECTION_VERSION=CLIPBOARD_SELECTION_VERSION,
    )

    assert file_format_version_for(canvas) == CANVAS_FILE_VERSION
    assert str(canvas.CLIPBOARD_SELECTION_MIME) == "application/x-test-selection"
    assert clipboard_selection_version_for(canvas) == CLIPBOARD_SELECTION_VERSION


def test_canvas_format_version_accessors_do_not_coerce_non_integer_values() -> None:
    canvas = SimpleNamespace(FILE_FORMAT_VERSION=7.0, CLIPBOARD_SELECTION_VERSION=2.0)

    with pytest.raises(TypeError):
        file_format_version_for(canvas)
    with pytest.raises(TypeError):
        clipboard_selection_version_for(canvas)


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

        clear_scene = mock.Mock(
            side_effect=RuntimeError("scene clear failed")
            if failure_stage == "clear"
            else None,
        )
        canvas = SimpleNamespace(
            scene=scene_for_canvas,
            deleteLater=delete_later,
            services=SimpleNamespace(
                canvas_scene_reset_service=SimpleNamespace(clear_scene=clear_scene)
            ),
        )

        lifecycle.schedule_canvas_deletion_for(canvas)

        delete_later.assert_called_once_with()
        if failure_stage != "scene":
            assert blocker.blocked is True


def test_input_controller_for_view_returns_attached_input_controller() -> None:
    input_controller = object()
    canvas = SimpleNamespace(
        services=canvas_runtime_services(input_controller=input_controller)
    )

    assert input_controller_for_view(canvas) is input_controller


def test_input_controller_for_view_returns_none_when_services_are_missing() -> None:
    assert input_controller_for_view(SimpleNamespace()) is None


def test_pointer_controller_for_view_returns_attached_pointer_controller() -> None:
    pointer_controller = object()
    canvas = SimpleNamespace(
        services=canvas_runtime_services(pointer_controller=pointer_controller)
    )

    assert pointer_controller_for_view(canvas) is pointer_controller


def test_pointer_controller_for_view_returns_none_when_services_are_missing() -> None:
    assert pointer_controller_for_view(SimpleNamespace()) is None
