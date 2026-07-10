from __future__ import annotations

import contextlib
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import count
from pathlib import Path
from typing import Any
from uuid import uuid4
from weakref import WeakKeyDictionary


@dataclass(slots=True)
class RDKitExportOwnerState:
    callbacks_enabled: bool = True
    job_ids: set[int] = field(default_factory=set)


@dataclass(slots=True)
class RDKitExportJob:
    job_id: int
    owner_state: RDKitExportOwnerState
    target_path: Path
    callback_path: str
    normalized_target_path: str
    staging_path: Path
    generation: int
    on_success: Callable[[str], None] | None
    on_error: Callable[[str], None] | None
    thread: Any | None = None
    worker: Any | None = None
    result_handled: bool = False
    thread_finished: bool = False


def normalized_export_target_path(path: str | os.PathLike[str]) -> str:
    expanded = os.path.expanduser(os.fspath(path))
    absolute = os.path.abspath(expanded)
    return os.path.normcase(os.path.realpath(absolute))


def _absolute_target_path(path: str | os.PathLike[str]) -> Path:
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    return target


def _staging_path_for(target: Path) -> Path:
    target_name = target.name or "xyz-export"
    return target.with_name(f".{target_name}.{uuid4().hex}.stage")


class RDKitExportJobRegistry:
    def __init__(self) -> None:
        self._owner_states: WeakKeyDictionary[Any, RDKitExportOwnerState] = WeakKeyDictionary()
        self._jobs: dict[int, RDKitExportJob] = {}
        self._latest_generation_by_path: dict[str, int] = {}
        self._job_ids = count(1)

    def _owner_state_for(self, owner: Any) -> RDKitExportOwnerState:
        state = self._owner_states.get(owner)
        if state is not None:
            return state
        state = RDKitExportOwnerState()
        self._owner_states[owner] = state
        destroyed = getattr(owner, "destroyed", None)
        if destroyed is not None:
            destroyed.connect(
                lambda *_args, state=state, registry=self: registry.disable_owner_callbacks(state)
            )
        return state

    def reserve(
        self,
        owner: Any,
        path: str | os.PathLike[str],
        *,
        on_success: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> RDKitExportJob:
        owner_state = self._owner_state_for(owner)
        normalized_target = normalized_export_target_path(path)
        generation = self._latest_generation_by_path.get(normalized_target, 0) + 1
        self._latest_generation_by_path[normalized_target] = generation
        job_id = next(self._job_ids)
        target_path = _absolute_target_path(path)
        job = RDKitExportJob(
            job_id=job_id,
            owner_state=owner_state,
            target_path=target_path,
            callback_path=os.fspath(path),
            normalized_target_path=normalized_target,
            staging_path=_staging_path_for(target_path),
            generation=generation,
            on_success=on_success,
            on_error=on_error,
        )
        self._jobs[job_id] = job
        owner_state.job_ids.add(job_id)
        return job

    def attach(self, job_id: int, *, thread: Any, worker: Any) -> None:
        job = self._jobs[job_id]
        job.thread = thread
        job.worker = worker

    def job(self, job_id: int) -> RDKitExportJob | None:
        return self._jobs.get(job_id)

    def active_jobs(self) -> tuple[RDKitExportJob, ...]:
        return tuple(self._jobs.values())

    def jobs_for_owner(self, owner: Any) -> list[tuple[Any, Any]]:
        state = self._owner_states.get(owner)
        if state is None:
            return []
        return [
            (job.thread, job.worker)
            for job_id in state.job_ids
            if (job := self._jobs.get(job_id)) is not None
            and job.thread is not None
            and job.worker is not None
        ]

    def is_latest(self, job: RDKitExportJob) -> bool:
        return self._latest_generation_by_path.get(job.normalized_target_path) == job.generation

    def disable_owner_callbacks(self, state: RDKitExportOwnerState) -> None:
        state.callbacks_enabled = False
        for job_id in tuple(state.job_ids):
            job = self._jobs.get(job_id)
            if job is None:
                continue
            job.on_success = None
            job.on_error = None

    def release_if_complete(self, job_id: int) -> RDKitExportJob | None:
        job = self._jobs.get(job_id)
        if job is None or not (job.result_handled and job.thread_finished):
            return None
        self._jobs.pop(job_id, None)
        job.owner_state.job_ids.discard(job_id)
        if not any(
            active.normalized_target_path == job.normalized_target_path
            for active in self._jobs.values()
        ):
            self._latest_generation_by_path.pop(job.normalized_target_path, None)
        job.on_success = None
        job.on_error = None
        return job

    def discard(self, job_id: int) -> None:
        job = self._jobs.pop(job_id, None)
        if job is None:
            return
        job.owner_state.job_ids.discard(job_id)
        with contextlib.suppress(OSError):
            job.staging_path.unlink()
        if not any(
            active.normalized_target_path == job.normalized_target_path
            for active in self._jobs.values()
        ):
            self._latest_generation_by_path.pop(job.normalized_target_path, None)

    def reset_for_tests(self) -> None:
        for job in self._jobs.values():
            with contextlib.suppress(OSError):
                job.staging_path.unlink()
        self._owner_states = WeakKeyDictionary()
        self._jobs = {}
        self._latest_generation_by_path = {}
        self._job_ids = count(1)


_EXPORT_JOB_REGISTRY = RDKitExportJobRegistry()


def rdkit_export_job_registry() -> RDKitExportJobRegistry:
    return _EXPORT_JOB_REGISTRY


def rdkit_export_jobs_for(owner: Any) -> list[tuple[Any, Any]]:
    return _EXPORT_JOB_REGISTRY.jobs_for_owner(owner)


def active_rdkit_export_jobs() -> tuple[RDKitExportJob, ...]:
    return _EXPORT_JOB_REGISTRY.active_jobs()


def reset_rdkit_export_job_state_for_tests() -> None:
    _EXPORT_JOB_REGISTRY.reset_for_tests()


__all__ = [
    "RDKitExportJob",
    "RDKitExportJobRegistry",
    "RDKitExportOwnerState",
    "active_rdkit_export_jobs",
    "normalized_export_target_path",
    "rdkit_export_job_registry",
    "rdkit_export_jobs_for",
    "reset_rdkit_export_job_state_for_tests",
]
