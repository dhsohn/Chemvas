from unittest import mock

from chemvas.ui.main_window_canvas_tab_ui_service import MainWindowCanvasTabUIService


def test_canvas_tab_ui_service_delegates_close_requests() -> None:
    close_canvas_tab_for_window = mock.Mock()
    service = MainWindowCanvasTabUIService(
        close_canvas_tab_for_window=close_canvas_tab_for_window,
    )
    window = object()

    service.close_canvas_tab(window, 2)
    service.on_canvas_tab_moved(window, 1, 0)

    close_canvas_tab_for_window.assert_called_once_with(window, 2)
