from types import SimpleNamespace

from chemvas.ui.canvas_format_access import (
    clipboard_selection_mime_for,
    clipboard_selection_version_for,
    file_format_version_for,
)


def test_canvas_format_accessors_return_canvas_format_constants() -> None:
    canvas = SimpleNamespace(
        FILE_FORMAT_VERSION=3,
        CLIPBOARD_SELECTION_MIME="application/x-test-selection",
        CLIPBOARD_SELECTION_VERSION=4,
    )

    assert file_format_version_for(canvas) == 3
    assert clipboard_selection_mime_for(canvas) == "application/x-test-selection"
    assert clipboard_selection_version_for(canvas) == 4
