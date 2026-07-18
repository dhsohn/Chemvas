from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from chemvas.ui.main_window_action_availability_service import (
    MainWindowActionAvailabilityService,
)


def _button():
    return SimpleNamespace(setEnabled=mock.Mock())


def test_update_action_availability_sets_history_and_export_buttons() -> None:
    undo_button = _button()
    redo_button = _button()
    export_button = _button()
    canvas = object()
    history = SimpleNamespace(
        can_undo=mock.Mock(return_value=True), can_redo=mock.Mock(return_value=False)
    )
    history_service_for_window = mock.Mock(return_value=history)
    has_exportable_atoms_for_window = mock.Mock(return_value=True)
    active_canvas_or_none_for_window = mock.Mock(return_value=canvas)
    undo_button_for_window = mock.Mock(return_value=undo_button)
    redo_button_for_window = mock.Mock(return_value=redo_button)
    export_xyz_button_for_window = mock.Mock(return_value=export_button)
    window = SimpleNamespace()
    service = MainWindowActionAvailabilityService(
        history_service_for_window=history_service_for_window,
        has_exportable_atoms_for_window=has_exportable_atoms_for_window,
        active_canvas_or_none_for_window=active_canvas_or_none_for_window,
        undo_button_for_window=undo_button_for_window,
        redo_button_for_window=redo_button_for_window,
        export_xyz_button_for_window=export_xyz_button_for_window,
    )

    service.update_action_availability(window)

    active_canvas_or_none_for_window.assert_called_once_with(window)
    undo_button_for_window.assert_called_once_with(window)
    redo_button_for_window.assert_called_once_with(window)
    export_xyz_button_for_window.assert_called_once_with(window)
    history_service_for_window.assert_called_once_with(window)
    has_exportable_atoms_for_window.assert_called_once_with(window)
    undo_button.setEnabled.assert_called_once_with(True)
    redo_button.setEnabled.assert_called_once_with(False)
    export_button.setEnabled.assert_called_once_with(True)


def test_update_action_availability_handles_missing_canvas_and_buttons() -> None:
    history_service_for_window = mock.Mock()
    has_exportable_atoms_for_window = mock.Mock(return_value=False)
    active_canvas_or_none_for_window = mock.Mock(return_value=None)
    undo_button_for_window = mock.Mock(return_value=None)
    redo_button_for_window = mock.Mock(return_value=None)
    export_xyz_button_for_window = mock.Mock(return_value=None)
    window = SimpleNamespace()
    service = MainWindowActionAvailabilityService(
        history_service_for_window=history_service_for_window,
        has_exportable_atoms_for_window=has_exportable_atoms_for_window,
        active_canvas_or_none_for_window=active_canvas_or_none_for_window,
        undo_button_for_window=undo_button_for_window,
        redo_button_for_window=redo_button_for_window,
        export_xyz_button_for_window=export_xyz_button_for_window,
    )

    service.update_action_availability(window)

    active_canvas_or_none_for_window.assert_called_once_with(window)
    undo_button_for_window.assert_called_once_with(window)
    redo_button_for_window.assert_called_once_with(window)
    export_xyz_button_for_window.assert_called_once_with(window)
    history_service_for_window.assert_not_called()
    has_exportable_atoms_for_window.assert_called_once_with(window)
