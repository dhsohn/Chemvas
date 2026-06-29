from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from ui.main_window_context_bar_service import MainWindowContextBarService


def _context_bar_service(
    *,
    page_builder=None,
    active_tool_name_for_window=None,
    active_canvas_or_none_for_window=None,
    context_bar_page_override_for_window=None,
    insert_controller_for_window=None,
    set_atom_input_for_window=None,
    bond_length_px_for_window=None,
) -> MainWindowContextBarService:
    return MainWindowContextBarService(
        page_builder=page_builder or object(),
        active_tool_name_for_window=active_tool_name_for_window or mock.Mock(return_value=None),
        active_canvas_or_none_for_window=active_canvas_or_none_for_window or mock.Mock(return_value=None),
        context_bar_page_override_for_window=context_bar_page_override_for_window or mock.Mock(return_value=None),
        insert_controller_for_window=insert_controller_for_window or mock.Mock(),
        set_atom_input_for_window=set_atom_input_for_window or mock.Mock(),
        bond_length_px_for_window=bond_length_px_for_window or mock.Mock(return_value=20.0),
    )


def test_active_tool_name_uses_injected_window_port() -> None:
    active_tool_name_for_window = mock.Mock(return_value="arrow")
    service = _context_bar_service(
        active_tool_name_for_window=active_tool_name_for_window,
    )
    window = object()

    assert service.active_tool_name(window) == "arrow"
    active_tool_name_for_window.assert_called_once_with(window)


def test_refresh_window_uses_injected_active_tool_name() -> None:
    active_tool_name_for_window = mock.Mock(return_value="bond")
    context_bar_page_override_for_window = mock.Mock(return_value="ring_fill")
    service = _context_bar_service(
        active_tool_name_for_window=active_tool_name_for_window,
        context_bar_page_override_for_window=context_bar_page_override_for_window,
    )
    service.refresh = mock.Mock()
    window = SimpleNamespace()

    service.refresh_window(window)

    active_tool_name_for_window.assert_called_once_with(window)
    context_bar_page_override_for_window.assert_called_once_with(window)
    service.refresh.assert_called_once_with(window, "bond", page_key="ring_fill")


def test_reflect_bond_length_syncs_spin_from_active_canvas_preserving_fraction() -> None:
    bond_length_px_for_window = mock.Mock(return_value=33.4)
    service = _context_bar_service(
        active_canvas_or_none_for_window=mock.Mock(return_value=object()),
        bond_length_px_for_window=bond_length_px_for_window,
    )
    spin = mock.Mock()
    service._bond_length_spin = spin
    window = object()

    service.reflect_bond_length(window)

    bond_length_px_for_window.assert_called_once_with(window)
    # The fractional value is passed through unrounded; sync_value records the
    # baseline so a later focus/blur won't commit it.
    spin.sync_value.assert_called_once_with(33.4)


def test_reflect_bond_length_skips_when_no_active_canvas() -> None:
    bond_length_px_for_window = mock.Mock(return_value=33.4)
    service = _context_bar_service(
        active_canvas_or_none_for_window=mock.Mock(return_value=None),
        bond_length_px_for_window=bond_length_px_for_window,
    )
    spin = mock.Mock()
    service._bond_length_spin = spin

    service.reflect_bond_length(object())

    spin.sync_value.assert_not_called()
    bond_length_px_for_window.assert_not_called()
