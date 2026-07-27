from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from chemvas.ui.main_window_action_availability_service import (
    MainWindowActionAvailabilityService,
)


def _action():
    return SimpleNamespace(setEnabled=mock.Mock())


def test_update_action_availability_sets_history_actions() -> None:
    undo_action = _action()
    redo_action = _action()
    canvas = object()
    history = SimpleNamespace(
        can_undo=mock.Mock(return_value=True), can_redo=mock.Mock(return_value=False)
    )
    history_service_for_window = mock.Mock(return_value=history)
    active_canvas_or_none_for_window = mock.Mock(return_value=canvas)
    undo_action_for_window = mock.Mock(return_value=undo_action)
    redo_action_for_window = mock.Mock(return_value=redo_action)
    window = SimpleNamespace()
    service = MainWindowActionAvailabilityService(
        history_service_for_window=history_service_for_window,
        active_canvas_or_none_for_window=active_canvas_or_none_for_window,
        undo_action_for_window=undo_action_for_window,
        redo_action_for_window=redo_action_for_window,
    )

    service.update_action_availability(window)

    active_canvas_or_none_for_window.assert_called_once_with(window)
    undo_action_for_window.assert_called_once_with(window)
    redo_action_for_window.assert_called_once_with(window)
    history_service_for_window.assert_called_once_with(window)
    undo_action.setEnabled.assert_called_once_with(True)
    redo_action.setEnabled.assert_called_once_with(False)


def test_update_action_availability_handles_missing_canvas_and_actions() -> None:
    history_service_for_window = mock.Mock()
    active_canvas_or_none_for_window = mock.Mock(return_value=None)
    undo_action_for_window = mock.Mock(return_value=None)
    redo_action_for_window = mock.Mock(return_value=None)
    window = SimpleNamespace()
    service = MainWindowActionAvailabilityService(
        history_service_for_window=history_service_for_window,
        active_canvas_or_none_for_window=active_canvas_or_none_for_window,
        undo_action_for_window=undo_action_for_window,
        redo_action_for_window=redo_action_for_window,
    )

    service.update_action_availability(window)

    active_canvas_or_none_for_window.assert_called_once_with(window)
    undo_action_for_window.assert_called_once_with(window)
    redo_action_for_window.assert_called_once_with(window)
    history_service_for_window.assert_not_called()
