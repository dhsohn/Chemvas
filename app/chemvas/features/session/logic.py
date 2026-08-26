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

No Qt and no filesystem here — the store injects a ``pid`` liveness predicate
and does all IO, which keeps every rule below unit-testable.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

SESSION_SCHEMA_VERSION = 1
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


def is_consumable(
    manifest: SessionManifest, *, is_alive: Callable[[int], bool]
) -> bool:
    """Whether a *previous* session may be restored and then deleted.

    True when it exited cleanly, or when its process is gone (a crash). A
    not-clean session whose pid is still alive belongs to another running
    instance — leave it be.
    """
    return manifest.clean_exit or not is_alive(manifest.pid)


@dataclass(frozen=True)
class RestorePlan:
    restore: list[str]  # session ids to reopen, newest-first
    prune: list[str]  # session ids to delete (a superset of `restore`)


def plan_restore(
    candidates: Iterable[tuple[str, SessionManifest, float]],
    *,
    is_alive: Callable[[int], bool],
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
        if is_consumable(manifest, is_alive=is_alive)
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
    if (
        not isinstance(data, dict)
        or set(data) != {"version", "pid", "clean_exit", "docs"}
        or type(data.get("version")) is not int
        or data.get("version") != SESSION_SCHEMA_VERSION
    ):
        return None
    pid = data.get("pid")
    clean_exit = data.get("clean_exit")
    raw_docs = data.get("docs")
    if (
        type(pid) is not int
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
    return SessionManifest(pid=pid, clean_exit=clean_exit, docs=docs)


__all__ = [
    "SESSION_SCHEMA_VERSION",
    "DocDescriptor",
    "DocEntry",
    "RestorePlan",
    "RestoredDoc",
    "SessionManifest",
    "entries_to_restore",
    "is_consumable",
    "manifest_from_json",
    "manifest_to_json",
    "needs_snapshot",
    "plan_restore",
    "should_persist",
]
