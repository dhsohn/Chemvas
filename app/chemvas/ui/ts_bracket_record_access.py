"""Keep the TS bracket store in step with the graphics items that still own brackets.

Until reads move to the store, the item is the source of truth and the record is
derived from it. Every site that changes what a bracket is calls
``sync_ts_bracket_record_for`` afterwards, so the store never lags an edit.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PyQt6 import sip

from chemvas.domain.document import normalized_ts_bracket, ts_bracket_from_state
from chemvas.ui.canvas_ts_bracket_state import ts_bracket_state_for
from chemvas.ui.scene_item_state_serialization import ts_bracket_state_dict
from chemvas.ui.scene_record_ids import new_scene_record_id

if TYPE_CHECKING:
    from collections.abc import Callable

    from chemvas.domain.document import TSBracket

logger = logging.getLogger(__name__)

# Roles 0-2 carry an item's kind and payloads; the bracket id has its own. A
# shape keeps its id under the same role: role 0 says which store an id is for.
TS_BRACKET_ID_ROLE = 3


def _is_deleted(item: Any) -> bool:
    try:
        return sip.isdeleted(item)
    except TypeError:
        # Not a Qt wrapper at all; nothing Qt could have destroyed.
        return False


def ts_bracket_id_for_item(item: Any) -> int | None:
    ts_bracket_id = item.data(TS_BRACKET_ID_ROLE)
    return ts_bracket_id if type(ts_bracket_id) is int else None


def ts_bracket_record_for(canvas: Any, item: Any) -> TSBracket | None:
    ts_bracket_id = ts_bracket_id_for_item(item)
    if ts_bracket_id is None:
        return None
    return ts_bracket_state_for(canvas).records.get(ts_bracket_id)


def sync_ts_bracket_record_for(canvas: Any, item: Any) -> None:
    if item is None or _is_deleted(item) or item.data(0) != "ts_bracket":
        return
    state = ts_bracket_state_for(canvas)
    ts_bracket_id = ts_bracket_id_for_item(item)
    if ts_bracket_id is None:
        ts_bracket_id = new_scene_record_id()
        item.setData(TS_BRACKET_ID_ROLE, ts_bracket_id)
    try:
        record = normalized_ts_bracket(
            ts_bracket_from_state(ts_bracket_state_dict(item))
        )
    except ValueError:
        # An item whose geometry no document would accept has no record; the
        # edit itself must not fail because the mirror could not follow it.
        logger.warning("TS bracket %s has no valid record; dropping it", ts_bracket_id)
        state.records.pop(ts_bracket_id, None)
        return
    state.records[ts_bracket_id] = record


def clear_ts_bracket_records_for(canvas: Any) -> None:
    """Forget every record. Ids are never reused, so a stray item cannot alias."""
    ts_bracket_state_for(canvas).records = {}


def ts_bracket_store_checkpoint_for(canvas: Any) -> Callable[[], None]:
    """Return a callable that puts the store back as it is now."""
    state = ts_bracket_state_for(canvas)
    records = dict(state.records)

    def restore() -> None:
        state.records = dict(records)

    return restore


__all__ = [
    "TS_BRACKET_ID_ROLE",
    "clear_ts_bracket_records_for",
    "sync_ts_bracket_record_for",
    "ts_bracket_id_for_item",
    "ts_bracket_record_for",
    "ts_bracket_store_checkpoint_for",
]
