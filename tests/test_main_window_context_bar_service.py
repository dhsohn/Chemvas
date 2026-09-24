from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest import mock

from chemvas.ui.window import main_window_context_bar_service as module
from chemvas.ui.window.main_window_context_bar_service import (
    MainWindowContextBarService,
)

if TYPE_CHECKING:
    import pytest


def _context_bar_service(
    monkeypatch: pytest.MonkeyPatch,
    *,
    page_builder=None,
    active_tool_name_for_window=None,
    active_canvas_or_none_for_window=None,
    bond_length_px_for_window=None,
) -> MainWindowContextBarService:
    """Build the service with the window ports patched on its module."""
    ports = {
        "color_tool_for_window": lambda _window: None,
        "active_tool_name_for_window": active_tool_name_for_window
        or mock.Mock(return_value=None),
        "active_canvas_or_none_for_window": active_canvas_or_none_for_window
        or mock.Mock(return_value=None),
        "bond_length_px_for_window": bond_length_px_for_window
        or mock.Mock(return_value=20.0),
    }
    for name, port in ports.items():
        monkeypatch.setattr(module, name, port)
    return MainWindowContextBarService(page_builder=page_builder or object())


def test_active_tool_name_uses_injected_window_port(monkeypatch) -> None:
    active_tool_name_for_window = mock.Mock(return_value="arrow")
    service = _context_bar_service(
        monkeypatch,
        active_tool_name_for_window=active_tool_name_for_window,
    )
    window = object()

    assert service.active_tool_name(window) == "arrow"
    active_tool_name_for_window.assert_called_once_with(window)


def test_refresh_window_uses_injected_active_tool_name(monkeypatch) -> None:
    active_tool_name_for_window = mock.Mock(return_value="bond")
    service = _context_bar_service(
        monkeypatch,
        active_tool_name_for_window=active_tool_name_for_window,
    )
    service.refresh = mock.Mock()
    window = SimpleNamespace(
        runtime_state=SimpleNamespace(context_bar_page_override="ring_fill")
    )

    service.refresh_window(window)

    active_tool_name_for_window.assert_called_once_with(window)
    service.refresh.assert_called_once_with(window, "bond", page_key="ring_fill")


def test_reflect_bond_length_syncs_spin_from_active_canvas_preserving_fraction(
    monkeypatch,
) -> None:
    bond_length_px_for_window = mock.Mock(return_value=33.4)
    service = _context_bar_service(
        monkeypatch,
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


def test_reflect_bond_length_skips_when_no_active_canvas(monkeypatch) -> None:
    bond_length_px_for_window = mock.Mock(return_value=33.4)
    service = _context_bar_service(
        monkeypatch,
        active_canvas_or_none_for_window=mock.Mock(return_value=None),
        bond_length_px_for_window=bond_length_px_for_window,
    )
    spin = mock.Mock()
    service._bond_length_spin = spin

    service.reflect_bond_length(object())

    spin.sync_value.assert_not_called()
    bond_length_px_for_window.assert_not_called()
