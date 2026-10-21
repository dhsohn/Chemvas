"""Bind native object identities to live annotation record identities."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from chemvas.ui.canvas.canvas_document_state import GROUP_COLLECTION_STATES


def restore_cdxml_source(canvas: Any, state: dict) -> None:
    metadata = canvas.runtime_state.document_metadata_state
    metadata.cdxml_source = deepcopy(state.get("cdxml_source"))
    metadata.cdxml_item_bindings = {}
    if metadata.cdxml_source is None:
        return
    for kind, identities in metadata.cdxml_source["items"].items():
        collection = canvas.runtime_state.document_collection(
            GROUP_COLLECTION_STATES[kind]
        )
        metadata.cdxml_item_bindings[kind] = dict(
            zip(collection.order, identities, strict=True)
        )


def snapshot_cdxml_source(canvas: Any, state: dict) -> None:
    metadata = canvas.runtime_state.document_metadata_state
    if metadata.cdxml_source is None:
        return
    source = deepcopy(metadata.cdxml_source)
    source["items"] = {}
    for kind, name in GROUP_COLLECTION_STATES.items():
        collection = canvas.runtime_state.document_collection(name)
        bindings = metadata.cdxml_item_bindings.get(kind, {})
        source["items"][kind] = [
            bindings.get(record_id) for record_id in collection.order
        ]
    state["cdxml_source"] = source


def normalize_initial_cdxml_projection(canvas: Any, state: dict) -> None:
    metadata = canvas.runtime_state.document_metadata_state
    source = metadata.cdxml_source
    if source is None:
        return
    input_projection = {k: v for k, v in state.items() if k != "cdxml_source"}
    if json.dumps(input_projection, sort_keys=True) != json.dumps(
        source["baseline"], sort_keys=True
    ):
        return
    from chemvas.ui.canvas.canvas_document_state import snapshot_canvas_document_state

    normalized = snapshot_canvas_document_state(canvas)
    normalized.pop("cdxml_source", None)
    source["baseline"] = normalized
