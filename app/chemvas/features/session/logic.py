"""Pure model + policy for autosave sessions.

A *session* is the set of documents a running Chemvas instance has open. Every
few seconds the recovery service snapshots that set to disk (manifest + per-doc
payloads); on the next launch the store reads back sibling sessions and this
module decides which to restore and which to discard.

Policy summary (see :func:`should_persist` / :func:`entries_to_restore`):

* Only *dirty* docs get a payload snapshot; clean saved docs are represented by
  their path alone (reopened from disk). Blank untitled canvases are ignored.
* A **clean exit** means the close prompts already resolved every unsaved doc
  (saved → has a path, or discarded → gone), so on restore we reopen only the
  saved *paths* — discarded work never resurrects.
* An **unclean exit** (crash) resolved nothing, so we restore everything,
  including unsaved snapshots, and the caller surfaces a "recovered" note.

No Qt and no filesystem here — the store injects ``pid`` liveness and process
identity predicates and does all IO, which keeps every rule below unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

SESSION_SCHEMA_VERSION = 1
_DEVELOPMENT_SESSION_SCHEMA_VERSION = 2
_MAX_PID = 4_294_967_295
_MAX_PROCESS_IDENTITY_LENGTH = 256
JsonObject = dict[str, Any]


@dataclass(frozen=True)
class DocDescriptor:
    """A live document the service hands to the store each autosave tick."""

    state: JsonObject
    file_path: str | None
    display_name: str
    dirty: bool


@dataclass
class DocEntry:
    """One document as recorded in a session manifest on disk."""

    file_path: str | None
    display_name: str
    dirty: bool
    snapshot: str | None  # payload filename, or None for a clean saved doc


@dataclass
class SessionManifest:
    pid: int
    clean_exit: bool
    docs: list[DocEntry] = field(default_factory=list)
    process_identity: str | None = None


@dataclass(frozen=True)
class RestoredDoc:
    """A document reconstructed from a previous session, ready to reopen."""

    state: JsonObject | None  # None means "reopen from file_path"
    file_path: str | None
    display_name: str
    dirty: bool


def should_persist(*, has_path: bool, dirty: bool) -> bool:
    """A doc is worth remembering if it is saved (reopen it) or has unsaved
    changes (protect it). A pristine untitled canvas is not."""
    return has_path or dirty


def needs_snapshot(*, dirty: bool) -> bool:
    """Only dirty docs need a payload; clean saved docs reopen from disk."""
    return dirty


def _unknown_process_identity(_pid: int) -> str | None:
    return None


def is_valid_process_identity(value: object) -> bool:
    """Whether ``value`` is safe to use as an ownership comparison token."""
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and value.isprintable()
        and len(value) <= _MAX_PROCESS_IDENTITY_LENGTH
    )


def is_consumable(
    manifest: SessionManifest,
    *,
    is_alive: Callable[[int], bool],
    process_identity_for: Callable[[int], str | None] = _unknown_process_identity,
) -> bool:
    """Whether a *previous* session may be restored and then deleted.

    True when it exited cleanly, when its process is gone (a crash), or when
    the live process at its pid has a different creation identity (pid reuse).
    An identity-less legacy manifest or an identity lookup failure is treated
    as still owned while the pid is live, so uncertainty never consumes
    another instance's work.
    """
    if manifest.clean_exit or not is_alive(manifest.pid):
        return True
    if not is_valid_process_identity(manifest.process_identity):
        return False
    live_identity = process_identity_for(manifest.pid)
    return (
        is_valid_process_identity(live_identity)
        and live_identity != manifest.process_identity
    )


@dataclass(frozen=True)
class RestorePlan:
    restore: list[str]  # session ids to reopen, newest-first
    prune: list[str]  # session ids to delete (a superset of `restore`)


def plan_restore(
    candidates: Iterable[tuple[str, SessionManifest, float]],
    *,
    is_alive: Callable[[int], bool],
    process_identity_for: Callable[[int], str | None] = _unknown_process_identity,
) -> RestorePlan:
    """Decide which previous sessions to reopen and which to delete.

    ``candidates`` is an iterable of ``(session_id, manifest, order_key)`` for
    sessions other than our own (``order_key`` sorts most-recent-last).

    *Every* crashed session (unclean + dead pid) is restored so unsaved work is
    never pruned unrecovered, and at most one *clean* session is reopened (the
    newest, for last-session continuity) — on every launch, including one that
    opens a startup file on top of the restored workspace. Every consumable
    session is pruned; a live instance's session is untouched.
    """
    consumable = [
        (sid, manifest, key)
        for (sid, manifest, key) in candidates
        if is_consumable(
            manifest,
            is_alive=is_alive,
            process_identity_for=process_identity_for,
        )
    ]
    prune = [sid for (sid, _manifest, _key) in consumable]
    restore_items = [
        (sid, key) for (sid, manifest, key) in consumable if not manifest.clean_exit
    ]
    clean = [
        (sid, manifest, key)
        for (sid, manifest, key) in consumable
        if manifest.clean_exit
    ]
    if clean:
        sid, _manifest, key = max(clean, key=lambda item: item[2])
        restore_items.append((sid, key))
    restore_items.sort(key=lambda item: item[1], reverse=True)
    return RestorePlan(restore=[sid for (sid, _key) in restore_items], prune=prune)


def entries_to_restore(manifest: SessionManifest) -> list[DocEntry]:
    """Which manifest docs to reopen. Clean exit → saved paths only; crash →
    every persisted doc."""
    if manifest.clean_exit:
        return [entry for entry in manifest.docs if entry.file_path]
    return list(manifest.docs)


def manifest_to_json(manifest: SessionManifest) -> JsonObject:
    """Serialize the manifest in the v1 shape understood by older Chemvas.

    Process identity is persisted by the store in a separate owner sidecar.
    Keeping this file strictly v1-readable prevents an older concurrently
    running binary from treating a live newer session as an unreadable orphan.
    """
    return {
        "version": SESSION_SCHEMA_VERSION,
        "pid": manifest.pid,
        "clean_exit": manifest.clean_exit,
        "docs": [
            {
                "file_path": entry.file_path,
                "display_name": entry.display_name,
                "dirty": entry.dirty,
                "snapshot": entry.snapshot,
            }
            for entry in manifest.docs
        ],
    }


def manifest_from_json(data: object) -> SessionManifest | None:
    if not isinstance(data, dict) or type(data.get("version")) is not int:
        return None
    version = data.get("version")
    if version == SESSION_SCHEMA_VERSION:
        if set(data) != {"version", "pid", "clean_exit", "docs"}:
            return None
        process_identity = None
    elif version == _DEVELOPMENT_SESSION_SCHEMA_VERSION:
        if set(data) != {
            "version",
            "pid",
            "process_identity",
            "clean_exit",
            "docs",
        }:
            return None
        process_identity = data.get("process_identity")
        if process_identity is not None and not is_valid_process_identity(
            process_identity
        ):
            return None
    else:
        return None
    pid = data.get("pid")
    clean_exit = data.get("clean_exit")
    raw_docs = data.get("docs")
    if (
        type(pid) is not int
        or not 1 <= pid <= _MAX_PID
        or type(clean_exit) is not bool
        or not isinstance(raw_docs, list)
    ):
        return None
    docs: list[DocEntry] = []
    for raw in raw_docs:
        if not isinstance(raw, dict) or set(raw) != {
            "file_path",
            "display_name",
            "dirty",
            "snapshot",
        }:
            return None
        display_name = raw.get("display_name")
        file_path = raw.get("file_path")
        dirty = raw.get("dirty")
        snapshot = raw.get("snapshot")
        if (
            not isinstance(display_name, str)
            or (file_path is not None and not isinstance(file_path, str))
            or type(dirty) is not bool
            or (snapshot is not None and not isinstance(snapshot, str))
        ):
            return None
        docs.append(
            DocEntry(
                file_path=file_path,
                display_name=display_name,
                dirty=dirty,
                snapshot=snapshot,
            )
        )
    return SessionManifest(
        pid=pid,
        clean_exit=clean_exit,
        process_identity=process_identity,
        docs=docs,
    )


__all__ = [
    "SESSION_SCHEMA_VERSION",
    "DocDescriptor",
    "DocEntry",
    "RestorePlan",
    "RestoredDoc",
    "SessionManifest",
    "entries_to_restore",
    "is_consumable",
    "is_valid_process_identity",
    "manifest_from_json",
    "manifest_to_json",
    "needs_snapshot",
    "plan_restore",
    "should_persist",
]
