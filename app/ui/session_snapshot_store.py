"""On-disk autosave session store: manifest + per-document snapshots.

Owns one directory per running instance under ``<app-data>/sessions/`` and, on
launch, reads back the directories left by other instances to decide what to
recover. Every write goes through the same atomic writer used for real saves;
every read tolerates a corrupt or half-written file (returns/skips rather than
raising), so a broken app-data dir can never take down the editor.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from core.document_io import atomic_write_text, create_document, read_document
from core.document_state import CANVAS_FILE_VERSION

from ui.canvas_document_metadata_state import canonical_document_digest
from ui.session_snapshot_logic import (
    DocDescriptor,
    DocEntry,
    RestoredDoc,
    SessionManifest,
    count_recovered_unsaved,
    entries_to_restore,
    manifest_from_json,
    manifest_to_json,
    needs_snapshot,
    select_restorable,
    should_persist,
)

MANIFEST_NAME = "session.json"


@dataclass
class RestoreResult:
    docs: list[RestoredDoc] = field(default_factory=list)
    recovered_unsaved: int = 0


def _pid_alive(pid: int) -> bool:
    """Best-effort liveness. Unknown → assume alive so we never restore (and
    delete) a session another running instance still owns."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


class SessionSnapshotStore:
    def __init__(self, sessions_root: Path, *, session_id: str, pid: int) -> None:
        self._root = sessions_root
        self._id = session_id
        self._pid = pid
        self._dir = sessions_root / session_id
        self._last_signature: object = None

    @property
    def session_dir(self) -> Path:
        return self._dir

    def begin(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._write_manifest(SessionManifest(pid=self._pid, clean_exit=False, docs=[]))

    def save_documents(self, docs: list[DocDescriptor]) -> None:
        """Rewrite the manifest + dirty-doc snapshots for the current open set.

        A signature guard makes an unchanged (idle) tick a no-op, so a document
        left open but untouched does not churn the disk every interval.
        """
        persisted = [doc for doc in docs if should_persist(has_path=bool(doc.file_path), dirty=doc.dirty)]
        signature = tuple(
            (doc.file_path, doc.display_name, doc.dirty, canonical_document_digest(doc.state)) for doc in persisted
        )
        if signature == self._last_signature:
            return

        entries: list[DocEntry] = []
        keep: set[str] = set()
        for index, doc in enumerate(persisted):
            snapshot_name: str | None = None
            if needs_snapshot(dirty=doc.dirty):
                snapshot_name = f"doc-{index}.json"
                self._write_snapshot(snapshot_name, doc.state)
                keep.add(snapshot_name)
            entries.append(
                DocEntry(
                    file_path=doc.file_path,
                    display_name=doc.display_name,
                    dirty=doc.dirty,
                    snapshot=snapshot_name,
                )
            )
        self._prune_snapshots(keep)
        self._write_manifest(SessionManifest(pid=self._pid, clean_exit=False, docs=entries))
        self._last_signature = signature

    def mark_clean_exit(self) -> None:
        manifest = self._read_manifest(self._dir)
        if manifest is None:
            return
        manifest.clean_exit = True
        self._write_manifest(manifest)

    def consume_previous_sessions(self) -> RestoreResult:
        """Restore the newest recoverable sibling session and delete every
        consumable one. Live instances' sessions are left untouched."""
        candidates = []
        for child in self._sibling_dirs():
            manifest = self._read_manifest(child)
            if manifest is None:
                shutil.rmtree(child, ignore_errors=True)  # orphan / corrupt dir
                continue
            candidates.append((child.name, manifest, child.stat().st_mtime))

        chosen, prune_ids = select_restorable(candidates, is_alive=_pid_alive)
        result = RestoreResult()
        if chosen is not None:
            session_id, manifest = chosen
            result.recovered_unsaved = count_recovered_unsaved(manifest)
            for entry in entries_to_restore(manifest):
                restored = self._restore_entry(self._root / session_id, entry, clean_exit=manifest.clean_exit)
                if restored is not None:
                    result.docs.append(restored)
        for session_id in prune_ids:
            shutil.rmtree(self._root / session_id, ignore_errors=True)
        return result

    # --- internals --------------------------------------------------------

    def _sibling_dirs(self) -> list[Path]:
        if not self._root.exists():
            return []
        return [child for child in self._root.iterdir() if child.is_dir() and child.name != self._id]

    def _restore_entry(self, session_dir: Path, entry: DocEntry, *, clean_exit: bool) -> RestoredDoc | None:
        # A crash prefers the snapshot (it holds unsaved edits); a clean exit
        # only reopens saved paths from disk.
        if not clean_exit and entry.snapshot:
            state = self._read_state(session_dir / entry.snapshot)
            if state is not None:
                return RestoredDoc(
                    state=state,
                    file_path=entry.file_path,
                    display_name=entry.display_name,
                    dirty=entry.dirty,
                )
        if entry.file_path and os.path.exists(entry.file_path):
            state = self._read_state(Path(entry.file_path))
            if state is not None:
                return RestoredDoc(
                    state=state,
                    file_path=entry.file_path,
                    display_name=entry.display_name,
                    dirty=False,
                )
        return None

    def _read_state(self, path: Path) -> dict | None:
        try:
            return read_document(path).state
        except Exception:
            return None

    def _manifest_path(self, session_dir: Path) -> Path:
        return session_dir / MANIFEST_NAME

    def _read_manifest(self, session_dir: Path) -> SessionManifest | None:
        try:
            data = json.loads(self._manifest_path(session_dir).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return manifest_from_json(data)

    def _write_manifest(self, manifest: SessionManifest) -> None:
        atomic_write_text(self._manifest_path(self._dir), json.dumps(manifest_to_json(manifest), indent=2))

    def _write_snapshot(self, name: str, state: dict) -> None:
        document = create_document(state, CANVAS_FILE_VERSION)
        atomic_write_text(self._dir / name, json.dumps(document.payload, indent=2))

    def _prune_snapshots(self, keep: set[str]) -> None:
        for child in self._dir.glob("doc-*.json"):
            if child.name not in keep:
                child.unlink(missing_ok=True)


def new_session_store(sessions_root: Path) -> SessionSnapshotStore:
    pid = os.getpid()
    session_id = f"{pid}-{uuid.uuid4().hex}"
    return SessionSnapshotStore(sessions_root, session_id=session_id, pid=pid)


__all__ = ["RestoreResult", "SessionSnapshotStore", "new_session_store"]
