"""Runtime ids that tie a graphics item to its document record.

An id is handed out once per process and never again. The counter is
deliberately not part of the canvas runtime state: a rollback puts records
back, but an item that history still holds keeps the id it was given, so a
counter that went back with the records would hand that id to the next item
and the two would share a record.
"""

from __future__ import annotations

from itertools import count

_record_ids = count(1)


def new_scene_record_id() -> int:
    return next(_record_ids)


__all__ = ["new_scene_record_id"]
