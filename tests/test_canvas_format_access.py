from types import SimpleNamespace

import pytest

from chemvas.domain.document import CANVAS_FILE_VERSION, CLIPBOARD_SELECTION_VERSION
from chemvas.ui.canvas_format_access import (
    clipboard_selection_mime_for,
    clipboard_selection_version_for,
    file_format_version_for,
)


def test_canvas_format_accessors_return_canvas_format_constants() -> None:
    canvas = SimpleNamespace(
        FILE_FORMAT_VERSION=CANVAS_FILE_VERSION,
        CLIPBOARD_SELECTION_MIME="application/x-test-selection",
        CLIPBOARD_SELECTION_VERSION=CLIPBOARD_SELECTION_VERSION,
    )

    assert file_format_version_for(canvas) == CANVAS_FILE_VERSION
    assert clipboard_selection_mime_for(canvas) == "application/x-test-selection"
    assert clipboard_selection_version_for(canvas) == CLIPBOARD_SELECTION_VERSION


def test_canvas_format_version_accessors_do_not_coerce_non_integer_values() -> None:
    canvas = SimpleNamespace(FILE_FORMAT_VERSION=7.0, CLIPBOARD_SELECTION_VERSION=2.0)

    with pytest.raises(TypeError):
        file_format_version_for(canvas)
    with pytest.raises(TypeError):
        clipboard_selection_version_for(canvas)
