"""Bind native object identities to live annotation record identities."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from chemvas.domain.document.cdxml_source import CdxmlSource, native_ids_for_collection
from chemvas.ui.canvas.canvas_document_state import GROUP_COLLECTION_STATES


def restore_cdxml_source(canvas: Any, state: dict) -> None:
    metadata = canvas.runtime_state.document_metadata_state
    source_obj = state.get("cdxml_source")
    if source_obj is None:
        metadata.cdxml_source = None
        metadata.cdxml_item_bindings = {}
        return
    source: CdxmlSource = deepcopy(source_obj)
    bindings: dict[str, dict[int, str | None]] = {}
    for kind, identities in source["items"].items():
        collection = canvas.runtime_state.document_collection(
            GROUP_COLLECTION_STATES[kind]
        )
        links = native_ids_for_collection(
            {kind: identities}, kind, len(collection.order)
        )
        bindings[kind] = dict(zip(collection.order, links, strict=True))
    metadata.cdxml_source = source
    metadata.cdxml_item_bindings = bindings


def snapshot_cdxml_source(canvas: Any, state: dict) -> None:
    metadata = canvas.runtime_state.document_metadata_state
    if metadata.cdxml_source is None:
        return
    source: CdxmlSource = deepcopy(metadata.cdxml_source)
    source["items"] = {}
    for kind, name in GROUP_COLLECTION_STATES.items():
        collection = canvas.runtime_state.document_collection(name)
        runtime_bindings = metadata.cdxml_item_bindings.get(kind, {})
        source["items"][kind] = [
            runtime_bindings.get(record_id) for record_id in collection.order
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
    for kind, identities in source["baseline_items"].items():
        records = normalized.get(kind, [])
        if not isinstance(records, list):
            raise ValueError(f"Invalid CDXML {kind} bindings.")
        native_ids_for_collection({kind: identities}, kind, len(records))
    source["baseline"] = normalized
