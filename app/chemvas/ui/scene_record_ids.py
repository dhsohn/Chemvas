"""Runtime ids that tie a graphics item to its document record.

An id is handed out once per process and never again. The counter is
deliberately not part of the canvas runtime state: a rollback puts records
back, but history values and surviving projections retain their assigned IDs.
Rolling back the counter would let an unrelated new annotation share that ID.
"""

from __future__ import annotations

from itertools import count
from typing import TYPE_CHECKING, Any
from weakref import finalize

if TYPE_CHECKING:
    from chemvas.domain.document.annotation_collection import AnnotationCollection

_record_ids = count(1)


def new_scene_record_id() -> int:
    return next(_record_ids)


# Finalizers never retain a projection. One lease per ID prevents an old
# wrapper (including one held by a failed operation's traceback) from deleting
# a detached record now used by its replacement.
_projection_leases: dict[int, finalize] = {}


def release_scene_record_lease(record_id: int) -> None:
    previous = _projection_leases.pop(record_id, None)
    if previous is not None:
        previous.detach()


def bind_scene_record(
    item: Any, document: AnnotationCollection[Any], record_id: int
) -> None:
    release_scene_record_lease(record_id)

    def release() -> None:
        document.discard_detached(record_id)
        _projection_leases.pop(record_id, None)

    _projection_leases[record_id] = finalize(item, release)


__all__ = ["bind_scene_record", "new_scene_record_id", "release_scene_record_lease"]
