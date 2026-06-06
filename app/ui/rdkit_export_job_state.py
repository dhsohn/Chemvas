from __future__ import annotations

from typing import Any
from weakref import WeakKeyDictionary

_EXPORT_JOBS_BY_OWNER: WeakKeyDictionary[Any, list[tuple[Any, Any]]] = WeakKeyDictionary()


def rdkit_export_jobs_for(owner: Any) -> list[tuple[Any, Any]]:
    jobs = _EXPORT_JOBS_BY_OWNER.get(owner)
    if jobs is None:
        jobs = []
        _EXPORT_JOBS_BY_OWNER[owner] = jobs
    return jobs


__all__ = ["rdkit_export_jobs_for"]
