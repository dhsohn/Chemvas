from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from chemvas.ui import canvas_document_metadata_state as metadata
from chemvas.ui.canvas_document_metadata_state import (
    CanvasDocumentMetadataState,
    document_is_dirty_for,
    document_metadata_state_for,
    mark_document_clean_for,
    mark_document_dirty_for,
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


def test_recovered_dirty_state_does_not_hash_until_marked_clean(monkeypatch):
    canvas = SimpleNamespace(
        runtime_state=canvas_runtime_state(
            document_metadata_state=CanvasDocumentMetadataState()
        )
    )
    state = {"notes": [{"text": "Recovered draft"}]}
    mark_document_dirty_for(canvas)
    digest = Mock(wraps=metadata.canonical_document_digest)
    monkeypatch.setattr(metadata, "canonical_document_digest", digest)

    assert document_is_dirty_for(canvas, state)
    state["notes"][0]["text"] = "Still unsaved"
    assert document_is_dirty_for(canvas, state)
    assert digest.call_count == 0

    mark_document_clean_for(canvas, state)
    assert digest.call_count == 1
    assert not document_is_dirty_for(canvas, state)
    assert digest.call_count == 2
    state["notes"][0]["text"] = "Edited after save"
    assert document_is_dirty_for(canvas, state)
    assert digest.call_count == 3
    state["notes"][0]["text"] = "Still unsaved"
    assert not document_is_dirty_for(canvas, state)
    assert digest.call_count == 4


def test_uninitialized_clean_baseline_still_does_not_hash(monkeypatch):
    canvas = SimpleNamespace(
        runtime_state=canvas_runtime_state(
            document_metadata_state=CanvasDocumentMetadataState()
        )
    )
    digest = Mock(wraps=metadata.canonical_document_digest)
    monkeypatch.setattr(metadata, "canonical_document_digest", digest)

    assert not document_is_dirty_for(canvas, {"notes": []})
    digest.assert_not_called()


@pytest.mark.parametrize("field", ["notes", "settings", "model", "images"])
def test_saved_baseline_rechecks_direct_state_changes_without_history(
    monkeypatch, field
):
    canvas = SimpleNamespace(
        runtime_state=canvas_runtime_state(
            document_metadata_state=CanvasDocumentMetadataState()
        )
    )
    state = {field: {"value": "before"}}
    mark_document_clean_for(canvas, state)
    canvas.runtime_state.document_metadata_state.source_sha256 = "saved-file-hash"
    digest = Mock(wraps=metadata.canonical_document_digest)
    monkeypatch.setattr(metadata, "canonical_document_digest", digest)

    assert not document_is_dirty_for(canvas, state)
    state[field]["value"] = "after"
    assert document_is_dirty_for(canvas, state)
    state[field]["value"] = "before"
    assert not document_is_dirty_for(canvas, state)
    assert digest.call_count == 3
    assert (
        canvas.runtime_state.document_metadata_state.source_sha256 == "saved-file-hash"
    )
