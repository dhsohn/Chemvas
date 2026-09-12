from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from chemvas.bootstrap.main_window_services import build_main_window_services
from chemvas.ui.main_window_action_availability_service import (
    MainWindowActionAvailabilityService,
)
from chemvas.ui.main_window_context_page_state_service import (
    MainWindowContextPageStateService,
)
from chemvas.ui.main_window_ports import (
    active_tool_name_for_window,
    align_selection_for_window,
    color_mutation_service_for_window,
    color_tool_for_window,
    copy_selection_for_window,
    cut_selection_for_window,
    distribute_selection_for_window,
    document_session_service_for_window,
    flip_selection_for_window,
    geometry_controller_for_window,
    insert_controller_for_window,
    paste_selection_for_window,
    scene_clipboard_controller_for_window,
    scene_delete_controller_for_window,
    scene_transform_controller_for_window,
    select_all_for_window,
    style_controller_for_window,
    tool_mode_controller_for_window,
)
from tests.runtime_services import canvas_runtime_services


def _window_with_active_canvas(canvas):
    return SimpleNamespace(
        runtime_state=SimpleNamespace(last_canvas_tab_index=0),
        tab_references=SimpleNamespace(
            active_canvas_or_none=lambda _last_canvas_tab_index: canvas,
        ),
    )


def test_active_tool_name_for_window_handles_missing_active_canvas() -> None:
    window = _window_with_active_canvas(None)

    assert active_tool_name_for_window(window) is None


def test_active_tool_name_for_window_reads_active_canvas_services() -> None:
    canvas = SimpleNamespace(
        services=canvas_runtime_services(
            tool_controller=SimpleNamespace(active=SimpleNamespace(name="perspective")),
        ),
    )
    window = _window_with_active_canvas(canvas)

    assert active_tool_name_for_window(window) == "perspective"


def test_active_canvas_service_ports_share_active_canvas_services_lookup() -> None:
    services = canvas_runtime_services(
        style_controller=object(),
        tool_mode_controller=object(),
        insert_controller=object(),
        canvas_color_mutation_service=object(),
        scene_transform_controller=object(),
        canvas_document_session_service=object(),
        geometry_controller=object(),
        tool_controller=SimpleNamespace(tools={"color": object()}),
    )
    window = _window_with_active_canvas(SimpleNamespace(services=services))

    assert style_controller_for_window(window) is services.style_controller
    assert tool_mode_controller_for_window(window) is services.tool_mode_controller
    assert insert_controller_for_window(window) is services.insert_controller
    assert (
        color_mutation_service_for_window(window)
        is services.canvas_color_mutation_service
    )
    assert (
        scene_transform_controller_for_window(window)
        is services.scene_transform_controller
    )
    assert (
        document_session_service_for_window(window)
        is services.canvas_document_session_service
    )
    assert geometry_controller_for_window(window) is services.geometry_controller
    assert color_tool_for_window(window) is services.tool_controller.tools["color"]


def _clipboard_window(*, copy_result: bool):
    from unittest import mock

    clipboard = SimpleNamespace(
        copy_selection_to_clipboard=mock.Mock(return_value=copy_result),
        paste_selection_from_clipboard=mock.Mock(return_value=True),
    )
    delete = SimpleNamespace(delete_selected_items=mock.Mock())
    services = canvas_runtime_services(
        scene_clipboard_controller=clipboard,
        scene_delete_controller=delete,
        tool_controller=SimpleNamespace(prepare_for_document_edit=mock.Mock()),
    )
    window = _window_with_active_canvas(SimpleNamespace(services=services))
    return window, clipboard, delete


def test_clipboard_ports_resolve_active_canvas_controllers() -> None:
    window, clipboard, delete = _clipboard_window(copy_result=True)

    assert scene_clipboard_controller_for_window(window) is clipboard
    assert scene_delete_controller_for_window(window) is delete


def test_copy_and_paste_selection_ports_call_clipboard_controller() -> None:
    window, clipboard, _delete = _clipboard_window(copy_result=True)

    assert copy_selection_for_window(window) is True
    clipboard.copy_selection_to_clipboard.assert_called_once_with()

    paste_selection_for_window(window)
    clipboard.paste_selection_from_clipboard.assert_called_once_with()


def test_cut_selection_port_deletes_only_after_a_successful_copy() -> None:
    window, clipboard, delete = _clipboard_window(copy_result=True)
    cut_selection_for_window(window)
    clipboard.copy_selection_to_clipboard.assert_called_once_with()
    delete.delete_selected_items.assert_called_once_with()

    window, clipboard, delete = _clipboard_window(copy_result=False)
    cut_selection_for_window(window)
    delete.delete_selected_items.assert_not_called()


def test_clipboard_ports_are_noops_without_an_active_canvas() -> None:
    window = _window_with_active_canvas(None)

    assert copy_selection_for_window(window) is False
    cut_selection_for_window(window)
    paste_selection_for_window(window)
    select_all_for_window(window)


_TRANSFORM_PORTS = [
    (flip_selection_for_window, "flip_selected_items", (), {"horizontal": True}),
    (align_selection_for_window, "align_selected_items", ("left",), {}),
    (distribute_selection_for_window, "distribute_selected_items", ("vertical",), {}),
]


@pytest.mark.parametrize("port,operation,args,kwargs", _TRANSFORM_PORTS)
@pytest.mark.parametrize("cancel_fails", [False, True])
def test_transform_ports_prepare_before_edit_and_stop_on_cancel_failure(
    port, operation, args, kwargs, cancel_fails
) -> None:
    calls = mock.Mock()
    cancellation_error = RuntimeError("pending gesture rollback failed")
    if cancel_fails:
        calls.prepare.side_effect = cancellation_error
    transform = SimpleNamespace(**{operation: calls.transform})
    services = canvas_runtime_services(
        scene_transform_controller=transform,
        tool_controller=SimpleNamespace(prepare_for_document_edit=calls.prepare),
    )
    window = _window_with_active_canvas(SimpleNamespace(services=services))

    if cancel_fails:
        with pytest.raises(RuntimeError) as error:
            port(window, *args, **kwargs)
        assert error.value is cancellation_error
        assert calls.mock_calls == [mock.call.prepare()]
    else:
        port(window, *args, **kwargs)
        assert calls.mock_calls == [
            mock.call.prepare(),
            mock.call.transform(*args, **kwargs),
        ]


@pytest.mark.parametrize("port,operation,args,kwargs", _TRANSFORM_PORTS)
def test_transform_ports_are_noops_without_an_active_canvas(
    port, operation, args, kwargs
) -> None:
    port(_window_with_active_canvas(None), *args, **kwargs)


def test_build_main_window_services_includes_action_availability_service() -> None:
    services = build_main_window_services()

    assert isinstance(
        services.action_availability_service, MainWindowActionAvailabilityService
    )


def test_build_main_window_services_includes_context_page_state_service() -> None:
    services = build_main_window_services()

    assert isinstance(
        services.context_page_state_service, MainWindowContextPageStateService
    )
