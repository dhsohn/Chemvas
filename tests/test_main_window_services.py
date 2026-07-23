from __future__ import annotations

from types import SimpleNamespace

from chemvas.bootstrap.main_window_services import build_main_window_services
from chemvas.ui.main_window_action_availability_service import (
    MainWindowActionAvailabilityService,
)
from chemvas.ui.main_window_context_page_state_service import (
    MainWindowContextPageStateService,
)
from chemvas.ui.main_window_ports import (
    active_tool_name_for_window,
    color_mutation_service_for_window,
    color_tool_for_window,
    document_session_service_for_window,
    geometry_controller_for_window,
    has_exportable_atoms_for_window,
    insert_controller_for_window,
    scene_transform_controller_for_window,
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


def test_has_exportable_atoms_for_window_handles_missing_and_populated_canvas() -> None:
    assert has_exportable_atoms_for_window(_window_with_active_canvas(None)) is False

    canvas = SimpleNamespace(model=SimpleNamespace(atoms={1: object()}))
    window = _window_with_active_canvas(canvas)

    assert has_exportable_atoms_for_window(window) is True


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
