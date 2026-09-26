"""Large immutable image bytes must not be re-encoded on each dirty check."""

from collections import OrderedDict
from copy import deepcopy
from unittest.mock import Mock

import pytest

from chemvas.ui.canvas import canvas_document_metadata_state as metadata


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setattr(metadata, "_image_digests", OrderedDict())
    monkeypatch.setattr(metadata, "_image_digest_chars", 0)


def test_repeated_image_digest_does_not_hash_payload_again(monkeypatch):
    state = {"images": [{"data_base64": "A" * 4_000_000, "x": 0}]}
    original = deepcopy(state)
    digest = metadata.canonical_document_digest(state)
    sha = Mock(wraps=metadata.hashlib.sha256)
    monkeypatch.setattr(metadata.hashlib, "sha256", sha)
    for x in (1, 0, 10, 0):
        state["images"][0]["x"] = x
        current = metadata.canonical_document_digest(state)
        assert (current == digest) is (x == 0)
    assert max(len(call.args[0]) for call in sha.call_args_list) < 1000
    assert state == original


def test_equal_reallocated_payload_and_replacement_remain_content_based():
    state = {"images": [{"data_base64": "A" * 1000, "x": 0}]}
    digest = metadata.canonical_document_digest(state)
    old = state["images"][0]["data_base64"]
    state["images"][0]["data_base64"] = (" " + old)[1:]
    assert state["images"][0]["data_base64"] is not old
    assert metadata.canonical_document_digest(state) == digest
    state["images"][0]["data_base64"] = "B" + old[1:]
    assert metadata.canonical_document_digest(state) != digest
    state["images"][0]["data_base64"] = old
    assert metadata.canonical_document_digest(state) == digest


def test_image_cache_is_bounded_and_eviction_keeps_digest(monkeypatch):
    monkeypatch.setattr(metadata, "_IMAGE_DIGEST_BUDGET", 100)
    monkeypatch.setattr(metadata, "_IMAGE_DIGEST_LIMIT", 2)
    original = {"images": [{"data_base64": "A" * 60}]}
    digest = metadata.canonical_document_digest(original)
    for n in range(20):
        metadata.canonical_document_digest({"images": [{"data_base64": str(n) * 30}]})
        assert metadata._image_digest_chars <= 100
        assert len(metadata._image_digests) <= 2
    assert metadata.canonical_document_digest(original) == digest


@pytest.mark.parametrize("change", ["notes", "settings", "model", "image_metadata"])
def test_image_optimization_does_not_hide_mutable_content(change):
    state = {
        "images": [{"data_base64": "AAA=", "opacity": 1}],
        "notes": [{"text": "live"}],
        "settings": {"width": 1},
        "model": {"atoms": []},
    }
    digest = metadata.canonical_document_digest(state)
    if change == "image_metadata":
        state["images"][0]["opacity"] = 0.5
    else:
        state[change] = {"changed": True}
    assert metadata.canonical_document_digest(state) != digest
