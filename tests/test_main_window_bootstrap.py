from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from ui.main_window_bootstrap import bootstrap_main_window, build_main_window_runtime
from ui.main_window_preview_ports import preview_for_window
from ui.main_window_service_ports import services_for_window
from ui.main_window_state import MainWindowState
from ui.main_window_tab_references import MainWindowTabReferences
from ui.main_window_ui_references import MainWindowUiReferences


class _FakeWindow:
    def __init__(self) -> None:
        self.show_canvas_tab_context_menu = mock.Mock()
        self.on_canvas_tab_moved = mock.Mock()
        self.on_canvas_tab_changed = mock.Mock()
        self.setWindowTitle = mock.Mock()
        self.resize = mock.Mock()
        self.setCentralWidget = mock.Mock()
        self.next_canvas_sheet_name = mock.Mock(return_value="Sheet 1")
        self.canvas = object()

    @property
    def ui_references(self):
        return self._ui_refs

    @property
    def tab_references(self):
        return SimpleNamespace(active_canvas_or_none=mock.Mock(return_value=self.canvas))

    @property
    def runtime_state(self):
        return self._state


def test_bootstrap_main_window_initializes_runtime_references_and_services() -> None:
    window = _FakeWindow()
    canvas_tabs = object()
    sheet_add_tab = object()
    sheet_tab_bar = object()
    tab_assembly = SimpleNamespace(
        canvas_tabs=canvas_tabs,
        sheet_add_tab=sheet_add_tab,
        sheet_tab_bar=sheet_tab_bar,
    )
    toolbar_assembly = SimpleNamespace(
        tool_actions={"bond": object()},
        atom_input=object(),
        load_action=object(),
        export_xyz_button=object(),
        preview_panel_button=object(),
        undo_button=object(),
        redo_button=object(),
    )
    services = SimpleNamespace(
        ui_assembly_service=SimpleNamespace(
            init_toolbars=mock.Mock(return_value=toolbar_assembly),
            apply_theme=mock.Mock(),
        ),
        context_bar_service=SimpleNamespace(
            init_context_bar=mock.Mock(),
            refresh_window=mock.Mock(),
        ),
        panel_service=SimpleNamespace(init_panels=mock.Mock()),
        status_service=SimpleNamespace(init_status_bar=mock.Mock()),
        action_availability_service=SimpleNamespace(
            update_action_availability=mock.Mock(),
        ),
        active_canvas_ui_service=SimpleNamespace(
            bind_active_canvas=mock.Mock(),
            on_canvas_tab_changed=mock.Mock(),
        ),
        canvas_sheet_service=SimpleNamespace(
            add_canvas_sheet=mock.Mock(),
        ),
        canvas_tab_ui_service=SimpleNamespace(
            ensure_add_sheet_tab=mock.Mock(),
            on_canvas_tab_moved=mock.Mock(),
            show_canvas_tab_context_menu=mock.Mock(),
        ),
    )
    preview = SimpleNamespace(refresh_from_canvas=mock.Mock())
    icon_factory_instance = object()
    build_tabs = mock.Mock(return_value=tab_assembly)
    build_services = mock.Mock(return_value=services)
    preview_factory = mock.Mock(return_value=preview)
    icon_factory = mock.Mock(return_value=icon_factory_instance)

    runtime = build_main_window_runtime(
        window,
        build_tabs=build_tabs,
        build_services=build_services,
        preview_factory=preview_factory,
        icon_factory=icon_factory,
    )

    window.setWindowTitle.assert_called_once_with("Chemvas")
    window.resize.assert_called_once_with(1100, 760)
    build_tabs.assert_called_once()
    assert build_tabs.call_args.args == (window,)
    tab_callbacks = build_tabs.call_args.kwargs
    tab_callbacks["show_canvas_tab_context_menu"]("pos")
    tab_callbacks["on_canvas_tab_moved"](2, 1)
    tab_callbacks["on_canvas_tab_changed"](3)
    services.canvas_tab_ui_service.show_canvas_tab_context_menu.assert_called_once_with(window, "pos")
    services.canvas_tab_ui_service.on_canvas_tab_moved.assert_called_once_with(window, 2, 1)
    services.active_canvas_ui_service.on_canvas_tab_changed.assert_called_once_with(window, 3)
    window.show_canvas_tab_context_menu.assert_not_called()
    window.on_canvas_tab_moved.assert_not_called()
    window.on_canvas_tab_changed.assert_not_called()
    assert isinstance(runtime.state, MainWindowState)
    assert isinstance(runtime.ui_refs, MainWindowUiReferences)
    assert isinstance(runtime.tab_refs, MainWindowTabReferences)
    assert not hasattr(window, "_state")
    assert not hasattr(window, "_ui_refs")
    assert not hasattr(window, "_tab_refs")
    assert not hasattr(window, "canvas_tabs")
    assert runtime.tab_refs.canvas_tabs is canvas_tabs
    window.setCentralWidget.assert_called_once_with(canvas_tabs)
    build_services.assert_called_once_with()
    preview_factory.assert_called_once_with()
    assert not hasattr(window, "services")
    assert not hasattr(window, "preview_3d")

    window._state = runtime.state
    window._ui_refs = runtime.ui_refs
    window._tab_refs = runtime.tab_refs
    window._services = runtime.services
    window._preview_3d = runtime.preview_3d
    assert services_for_window(window) is services
    assert preview_for_window(window) is preview

    bootstrap_main_window(window, runtime)

    window.next_canvas_sheet_name.assert_not_called()
    services.canvas_sheet_service.add_canvas_sheet.assert_called_once_with(
        window,
        name="Sheet 1",
        select=True,
    )
    icon_factory.assert_called_once_with(window)
    assert window.ui_references.require_icon_factory() is icon_factory_instance
    assert window.ui_references.tool_actions == toolbar_assembly.tool_actions
    services.canvas_tab_ui_service.ensure_add_sheet_tab.assert_called_once_with(window)
    services.ui_assembly_service.init_toolbars.assert_called_once_with(window)
    services.action_availability_service.update_action_availability.assert_called_once_with(window)
    services.context_bar_service.init_context_bar.assert_called_once_with(window)
    services.panel_service.init_panels.assert_called_once_with(window)
    services.ui_assembly_service.apply_theme.assert_called_once_with(window)
    services.active_canvas_ui_service.bind_active_canvas.assert_called_once_with(window)
    preview.refresh_from_canvas.assert_called_once_with(window.canvas)
    services.status_service.init_status_bar.assert_called_once_with(window)
    services.context_bar_service.refresh_window.assert_called_once_with(window)
