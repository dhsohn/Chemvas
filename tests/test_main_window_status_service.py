from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from ui.main_window_status_service import MainWindowStatusService


def _service(
    *,
    active_tool_name_for_window=None,
    current_zoom_percent_for_window=None,
    active_canvas_or_none_for_window=None,
    canvas_sheet_count_for_window=None,
    active_canvas_sheet_name_for_window=None,
    active_canvas_sheet_index_for_window=None,
    context_bar_page_override_for_window=None,
):
    return MainWindowStatusService(
        active_tool_name_for_window=active_tool_name_for_window or mock.Mock(),
        current_zoom_percent_for_window=current_zoom_percent_for_window or mock.Mock(return_value=100),
        active_canvas_or_none_for_window=active_canvas_or_none_for_window or mock.Mock(return_value=object()),
        canvas_sheet_count_for_window=canvas_sheet_count_for_window or mock.Mock(return_value=1),
        active_canvas_sheet_name_for_window=active_canvas_sheet_name_for_window or mock.Mock(return_value="Sheet 1"),
        active_canvas_sheet_index_for_window=active_canvas_sheet_index_for_window or mock.Mock(return_value=0),
        context_bar_page_override_for_window=context_bar_page_override_for_window or mock.Mock(return_value=None),
    )


def test_active_tool_status_text_uses_injected_active_tool_port() -> None:
    active_tool_name_for_window = mock.Mock(return_value="perspective")
    active_canvas_or_none_for_window = mock.Mock(return_value=object())
    context_bar_page_override_for_window = mock.Mock(return_value=None)
    service = _service(
        active_tool_name_for_window=active_tool_name_for_window,
        active_canvas_or_none_for_window=active_canvas_or_none_for_window,
        context_bar_page_override_for_window=context_bar_page_override_for_window,
    )
    window = SimpleNamespace()

    assert service.active_tool_status_text(window) == "Tool: Perspective"
    context_bar_page_override_for_window.assert_called_once_with(window)
    active_canvas_or_none_for_window.assert_called_once_with(window)
    active_tool_name_for_window.assert_called_once_with(window)


def test_active_tool_status_text_ignores_unknown_override_and_handles_missing_canvas() -> None:
    active_tool_name_for_window = mock.Mock(return_value="bond")
    context_bar_page_override_for_window = mock.Mock(side_effect=["template", None])
    active_canvas_or_none_for_window = mock.Mock(side_effect=[object(), None])
    service = _service(
        active_tool_name_for_window=active_tool_name_for_window,
        active_canvas_or_none_for_window=active_canvas_or_none_for_window,
        context_bar_page_override_for_window=context_bar_page_override_for_window,
    )
    template_window = SimpleNamespace()
    canvasless_window = SimpleNamespace()

    assert service.active_tool_status_text(template_window) == "Tool: Bond"
    assert service.active_tool_status_text(canvasless_window) == "Tool: None"
    assert active_canvas_or_none_for_window.call_args_list == [
        mock.call(template_window),
        mock.call(canvasless_window),
    ]
    active_tool_name_for_window.assert_called_once_with(template_window)


def test_active_tool_status_text_respects_ring_fill_override() -> None:
    active_tool_name_for_window = mock.Mock(return_value="select")
    active_canvas_or_none_for_window = mock.Mock(return_value=object())
    service = _service(
        active_tool_name_for_window=active_tool_name_for_window,
        active_canvas_or_none_for_window=active_canvas_or_none_for_window,
        context_bar_page_override_for_window=mock.Mock(return_value="ring_fill"),
    )

    assert service.active_tool_status_text(SimpleNamespace()) == "Tool: Ring Fill"
    active_canvas_or_none_for_window.assert_not_called()
    active_tool_name_for_window.assert_not_called()


def test_active_tool_hint_text_describes_visible_status_message() -> None:
    service = _service(
        active_tool_name_for_window=mock.Mock(return_value="bond"),
        active_canvas_or_none_for_window=mock.Mock(return_value=object()),
        context_bar_page_override_for_window=mock.Mock(return_value=None),
    )

    assert service.active_tool_hint_text(SimpleNamespace()) == "Bond: click-drag to draw"


def test_active_tool_hint_text_respects_ring_fill_override_without_canvas_lookup() -> None:
    active_tool_name_for_window = mock.Mock(return_value="select")
    active_canvas_or_none_for_window = mock.Mock(return_value=object())
    service = _service(
        active_tool_name_for_window=active_tool_name_for_window,
        active_canvas_or_none_for_window=active_canvas_or_none_for_window,
        context_bar_page_override_for_window=mock.Mock(return_value="ring_fill"),
    )

    assert service.active_tool_hint_text(SimpleNamespace()) == "Ring Fill: choose fill color"
    active_canvas_or_none_for_window.assert_not_called()
    active_tool_name_for_window.assert_not_called()


def test_show_active_tool_hint_updates_status_bar_message() -> None:
    service = _service(
        active_tool_name_for_window=mock.Mock(return_value="select"),
        active_canvas_or_none_for_window=mock.Mock(return_value=object()),
        context_bar_page_override_for_window=mock.Mock(return_value=None),
    )
    bar = mock.Mock()
    window = SimpleNamespace(statusBar=mock.Mock(return_value=bar))

    service.show_active_tool_hint(window)

    bar.showMessage.assert_called_once_with("Select: click or drag marquee")


def test_show_error_message_uses_timer_default_inside_status_service() -> None:
    service = _service()
    bar = mock.Mock()
    window = SimpleNamespace(statusBar=mock.Mock(return_value=bar))

    with mock.patch("ui.main_window_status_service.QTimer.singleShot") as single_shot:
        service.show_error_message(window, "Invalid molecule", timeout=500)

    bar.setProperty.assert_called_once_with("statusState", "error")
    bar.showMessage.assert_called_once_with("Invalid molecule", 500)
    single_shot.assert_called_once()
    assert single_shot.call_args.args[0] == 500


def test_refresh_status_context_uses_injected_zoom_port() -> None:
    current_zoom_percent_for_window = mock.Mock(return_value=175)
    service = _service(current_zoom_percent_for_window=current_zoom_percent_for_window)
    service.update_tool_status_label = mock.Mock()
    service.update_sheet_status_label = mock.Mock()
    service.update_selection_status_label = mock.Mock()
    service.update_zoom_label = mock.Mock()
    window = object()

    service.refresh_status_context(window)

    current_zoom_percent_for_window.assert_called_once_with(window)
    service.update_zoom_label.assert_called_once_with(175)
