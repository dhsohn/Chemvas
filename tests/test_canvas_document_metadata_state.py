from types import SimpleNamespace

import pytest
from chemvas.ui.canvas_document_metadata_state import (
    CanvasDocumentMetadataState,
    document_metadata_state_for,
)

from tests.runtime_state import canvas_runtime_state


def test_document_metadata_state_reads_the_runtime_container_identity() -> None:
    state = CanvasDocumentMetadataState(display_name="Runtime canvas")
    canvas = SimpleNamespace(
        runtime_state=canvas_runtime_state(document_metadata_state=state),
    )

    assert document_metadata_state_for(canvas) is state
    assert not hasattr(canvas, "document_metadata_state")


def test_document_metadata_state_does_not_create_a_plain_canvas_fallback() -> None:
    canvas = SimpleNamespace()

    with pytest.raises(AttributeError):
        document_metadata_state_for(canvas)

    assert not hasattr(canvas, "document_metadata_state")
