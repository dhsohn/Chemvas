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

from dataclasses import dataclass, field

SESSION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DocDescriptor:
    """A live document the service hands to the store each autosave tick."""

    state: dict
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

    state: dict | None  # None means "reopen from file_path"
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


def is_consumable(manifest: SessionManifest, *, is_alive) -> bool:
    """Whether a *previous* session may be restored and then deleted.

    True when it exited cleanly, or when its process is gone (a crash). A
    not-clean session whose pid is still alive belongs to another running
    instance — leave it be.
    """
    return manifest.clean_exit or not is_alive(manifest.pid)


def select_restorable(candidates, *, is_alive):
    """Pick which previous session to restore and which to prune.

    ``candidates`` is an iterable of ``(session_id, manifest, order_key)`` for
    sessions other than our own; ``order_key`` sorts most-recent-last. Returns
    ``((session_id, manifest) | None, prune_ids)`` — the newest consumable
    session to restore, plus every consumable session id to delete (including
    the restored one). Live instances' sessions are neither restored nor pruned.
    """
    consumable = [(sid, manifest, key) for (sid, manifest, key) in candidates if is_consumable(manifest, is_alive=is_alive)]
    prune_ids = [sid for (sid, _manifest, _key) in consumable]
    if not consumable:
        return None, prune_ids
    sid, manifest, _key = max(consumable, key=lambda item: item[2])
    return (sid, manifest), prune_ids


def entries_to_restore(manifest: SessionManifest) -> list[DocEntry]:
    """Which manifest docs to reopen. Clean exit → saved paths only; crash →
    every persisted doc."""
    if manifest.clean_exit:
        return [entry for entry in manifest.docs if entry.file_path]
    return list(manifest.docs)


def count_recovered_unsaved(manifest: SessionManifest) -> int:
    """Unsaved docs a crash restore brings back (0 for a clean exit)."""
    if manifest.clean_exit:
        return 0
    return sum(1 for entry in manifest.docs if entry.dirty)


def manifest_to_json(manifest: SessionManifest) -> dict:
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
    if not isinstance(data, dict):
        return None
    pid = data.get("pid")
    if not isinstance(pid, int):
        return None
    raw_docs = data.get("docs")
    docs: list[DocEntry] = []
    if isinstance(raw_docs, list):
        for raw in raw_docs:
            if not isinstance(raw, dict):
                continue
            display_name = raw.get("display_name")
            if not isinstance(display_name, str):
                continue
            file_path = raw.get("file_path")
            snapshot = raw.get("snapshot")
            docs.append(
                DocEntry(
                    file_path=file_path if isinstance(file_path, str) else None,
                    display_name=display_name,
                    dirty=bool(raw.get("dirty")),
                    snapshot=snapshot if isinstance(snapshot, str) else None,
                )
            )
    return SessionManifest(pid=pid, clean_exit=bool(data.get("clean_exit")), docs=docs)


__all__ = [
    "SESSION_SCHEMA_VERSION",
    "DocDescriptor",
    "DocEntry",
    "RestoredDoc",
    "SessionManifest",
    "count_recovered_unsaved",
    "entries_to_restore",
    "is_consumable",
    "manifest_from_json",
    "manifest_to_json",
    "needs_snapshot",
    "select_restorable",
    "should_persist",
]
