"""On-disk autosave session store: manifest + per-document snapshots.

Owns one directory per running instance under ``<app-data>/sessions/`` and, on
launch, reads back the directories left by other instances to decide what to
recover. Every write goes through the same atomic writer used for real saves;
every read tolerates a corrupt or half-written file (returns/skips rather than
raising), so a broken app-data dir can never take down the editor.
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from chemvas.core.document_io import atomic_write_text, create_document, read_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.domain.json_io import strict_json_loads
from chemvas.features.session import (
    DocDescriptor,
    DocEntry,
    RestoredDoc,
    SessionManifest,
    entries_to_restore,
    is_valid_process_identity,
    manifest_from_json,
    manifest_to_json,
    needs_snapshot,
    plan_restore,
    should_persist,
)
from chemvas.ui.canvas_document_metadata_state import canonical_document_digest
from chemvas.ui.main_window_path_logic import is_canonical_saved_document_path

MANIFEST_NAME = "session.json"
OWNER_NAME = "owner.json"

_OWNER_SCHEMA_VERSION = 1
_MAX_PID = 4_294_967_295
_MAX_POSIX_PID = 2_147_483_647
_MAX_MANIFEST_BYTES = 1024 * 1024
_MAX_OWNER_BYTES = 4096

_DARWIN_PROC_PIDTBSDINFO = 3
_DARWIN_MAXCOMLEN = 16

# Age is necessary but no longer sufficient to reap a directory with no readable
# manifest: its owner sidecar must also prove that the process is gone. A newly
# starting instance creates its dir before atomically writing session.json, and
# that transient window must never be mistaken for an orphan and deleted.
_ORPHAN_REAP_AGE_SECONDS = 60.0


class _DarwinProcBsdInfo(ctypes.Structure):
    """ctypes mirror of Darwin's public ``struct proc_bsdinfo``."""

    _fields_ = [
        ("pbi_flags", ctypes.c_uint32),
        ("pbi_status", ctypes.c_uint32),
        ("pbi_xstatus", ctypes.c_uint32),
        ("pbi_pid", ctypes.c_uint32),
        ("pbi_ppid", ctypes.c_uint32),
        ("pbi_uid", ctypes.c_uint32),
        ("pbi_gid", ctypes.c_uint32),
        ("pbi_ruid", ctypes.c_uint32),
        ("pbi_rgid", ctypes.c_uint32),
        ("pbi_svuid", ctypes.c_uint32),
        ("pbi_svgid", ctypes.c_uint32),
        ("rfu_1", ctypes.c_uint32),
        ("pbi_comm", ctypes.c_char * _DARWIN_MAXCOMLEN),
        ("pbi_name", ctypes.c_char * (2 * _DARWIN_MAXCOMLEN)),
        ("pbi_nfiles", ctypes.c_uint32),
        ("pbi_pgid", ctypes.c_uint32),
        ("pbi_pjobc", ctypes.c_uint32),
        ("e_tdev", ctypes.c_uint32),
        ("e_tpgid", ctypes.c_uint32),
        ("pbi_nice", ctypes.c_int32),
        ("pbi_start_tvsec", ctypes.c_uint64),
        ("pbi_start_tvusec", ctypes.c_uint64),
    ]


@dataclass(frozen=True)
class _OwnerRecord:
    exists: bool
    pid: int | None = None
    process_identity: str | None = None


def _read_bounded_json(path: Path, *, max_bytes: int) -> object:
    with path.open("rb") as stream:
        payload = stream.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError(f"JSON payload exceeds the {max_bytes}-byte limit")
    return strict_json_loads(payload)


def _bounded_json_text(value: object, *, max_bytes: int) -> str:
    text = json.dumps(value, indent=2)
    if len(text.encode("utf-8")) > max_bytes:
        raise ValueError(f"JSON payload exceeds the {max_bytes}-byte limit")
    return text


def _is_old_orphan(child: Path) -> bool:
    try:
        return (time.time() - child.stat().st_mtime) > _ORPHAN_REAP_AGE_SECONDS
    except OSError:
        return False


@dataclass
class RestoreResult:
    docs: list[RestoredDoc] = field(default_factory=list)
    recovered_unsaved: int = 0
    # Consumed session ids to delete only *after* the restored documents have
    # been re-snapshotted into the new session (see SessionRecoveryService).
    prune_ids: list[str] = field(default_factory=list)


def _pid_alive(pid: int) -> bool:
    """Best-effort liveness. Unknown → assume alive so we never restore (and
    delete) a session another running instance still owns."""
    if type(pid) is not int or pid <= 0:
        return False
    if pid > _MAX_PID:
        return True
    if sys.platform == "win32":
        return _pid_alive_windows(pid)
    return _pid_alive_posix(pid)


def _pid_alive_posix(pid: int) -> bool:
    if type(pid) is not int or pid <= 0:
        return False
    if pid > _MAX_POSIX_PID:
        return True
    # Signal 0 is a genuine no-op existence probe on POSIX.
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but owned by another user
    except (OverflowError, ValueError):
        return True
    except OSError:
        return True
    return True


def _pid_alive_windows(pid: int) -> bool:  # pragma: no cover - Windows-only
    # CRITICAL: os.kill(pid, 0) on Windows is not a probe — it routes to
    # TerminateProcess and would kill the target. Query existence via
    # OpenProcess instead. Access the platform-only loader through the module
    # dictionary so cross-platform type checkers do not need a stale ignore.
    if type(pid) is not int or pid <= 0:
        return False
    if pid > _MAX_PID:
        return True

    import ctypes
    from ctypes import wintypes

    kernel32 = vars(ctypes)["windll"].kernel32
    process_query_limited_information = 0x1000
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetLastError.argtypes = []
    kernel32.GetLastError.restype = wintypes.DWORD
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        # ERROR_INVALID_PARAMETER is how OpenProcess reports a nonexistent PID.
        # Access denied and every other uncertain failure must remain "alive" so
        # recovery never consumes a session that another instance may own.
        return kernel32.GetLastError() != 87
    kernel32.CloseHandle(handle)
    return True


def _process_identity(pid: int) -> str | None:
    """Return a stable creation identity for the process currently at ``pid``.

    Unknown is deliberately ``None``: recovery combines this with the separate
    liveness probe and treats an unidentifiable live process as the owner.
    """
    if type(pid) is not int or not 1 <= pid <= _MAX_PID:
        return None
    if sys.platform == "win32":
        return _process_identity_windows(pid)
    if sys.platform.startswith("linux"):
        return _process_identity_linux(pid)
    if sys.platform == "darwin":
        # Do not fall back to ``ps lstart`` here. Its one-second resolution can
        # collide under pid reuse, and switching token schemes between probes
        # would turn a transient libproc failure into a false owner mismatch.
        return _process_identity_darwin(pid)
    return _process_identity_posix(pid)


def _process_identity_linux(pid: int) -> str | None:
    """Linux boot id + /proc start ticks; together they survive pid reuse."""
    if type(pid) is not int or not 1 <= pid <= _MAX_POSIX_PID:
        return None
    try:
        boot_id = (
            Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        )
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    start_ticks = _linux_start_ticks(stat)
    if not boot_id or len(boot_id) > 128 or start_ticks is None:
        return None
    return f"linux:{boot_id}:{start_ticks}"


def _linux_start_ticks(stat: str) -> str | None:
    """Extract field 22 from ``/proc/<pid>/stat`` without splitting ``comm``."""
    # Field 2 (comm) is parenthesized and may itself contain spaces or ``)``.
    # Splitting after its final close paren makes index 19 field 22 (starttime).
    head, separator, tail = stat.rpartition(")")
    fields = tail.split()
    if not separator or "(" not in head or len(fields) <= 19:
        return None
    start_ticks = fields[19]
    return start_ticks if start_ticks.isdecimal() else None


def _load_darwin_libproc():
    return ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)


def _process_identity_darwin(pid: int) -> str | None:
    """Darwin process start time with microsecond precision via libproc."""
    if type(pid) is not int or not 1 <= pid <= _MAX_POSIX_PID:
        return None
    try:
        libproc = _load_darwin_libproc()
        proc_pidinfo = libproc.proc_pidinfo
    except (AttributeError, OSError):
        return None
    proc_pidinfo.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    proc_pidinfo.restype = ctypes.c_int
    info = _DarwinProcBsdInfo()
    size = ctypes.sizeof(info)
    try:
        received = proc_pidinfo(
            pid,
            _DARWIN_PROC_PIDTBSDINFO,
            0,
            ctypes.byref(info),
            size,
        )
    except (OSError, OverflowError, ValueError):
        return None
    if (
        received != size
        or info.pbi_pid != pid
        or info.pbi_start_tvsec <= 0
        or info.pbi_start_tvusec >= 1_000_000
    ):
        return None
    return f"darwin:{info.pbi_start_tvsec}:{info.pbi_start_tvusec}"


def _process_identity_posix(pid: int) -> str | None:
    """Portable fallback for non-Linux, non-Darwin POSIX systems."""
    if type(pid) is not int or not 1 <= pid <= _MAX_POSIX_PID:
        return None
    environment = dict(os.environ)
    environment["LC_ALL"] = "C"
    # ``ps lstart`` renders in the caller's timezone. Pin it so two Chemvas
    # instances with different environments derive the same creation identity.
    environment["TZ"] = "UTC0"
    try:
        completed = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    started_at = completed.stdout.strip()
    if completed.returncode != 0 or not started_at or "\n" in started_at:
        return None
    return f"posix:{started_at}"


def _process_identity_windows(pid: int) -> str | None:  # pragma: no cover
    """Windows process creation FILETIME, queried without signalling it."""
    if type(pid) is not int or not 1 <= pid <= _MAX_PID:
        return None

    import ctypes
    from ctypes import wintypes

    kernel32 = vars(ctypes)["windll"].kernel32
    process_query_limited_information = 0x1000
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return None
    creation = wintypes.FILETIME()
    exit_time = wintypes.FILETIME()
    kernel_time = wintypes.FILETIME()
    user_time = wintypes.FILETIME()
    try:
        ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        )
    finally:
        kernel32.CloseHandle(handle)
    if not ok:
        return None
    created_at = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
    return f"windows:{created_at}"


class SessionSnapshotStore:
    def __init__(
        self,
        sessions_root: Path,
        *,
        session_id: str,
        pid: int,
        process_identity: str | None = None,
    ) -> None:
        self._root = sessions_root
        self._id = session_id
        self._pid = pid
        identity = (
            process_identity if process_identity is not None else _process_identity(pid)
        )
        self._process_identity = (
            identity if is_valid_process_identity(identity) else None
        )
        self._dir = sessions_root / session_id
        self._last_signature: object = None
        self._generation = 0

    @property
    def session_dir(self) -> Path:
        return self._dir

    def begin(self) -> None:
        # Best-effort: a read-only or broken app-data dir must not prevent the
        # editor from opening. Autosave simply becomes a no-op in that case.
        with contextlib.suppress(OSError):
            self._dir.mkdir(parents=True, exist_ok=True)
            self._write_manifest(
                SessionManifest(
                    pid=self._pid,
                    clean_exit=False,
                    process_identity=self._process_identity,
                    docs=[],
                )
            )

    def save_documents(self, docs: list[DocDescriptor]) -> None:
        """Rewrite the manifest + dirty-doc snapshots for the current open set.

        A signature guard makes an unchanged (idle) tick a no-op, so a document
        left open but untouched does not churn the disk every interval.
        """
        persisted = [
            doc
            for doc in docs
            if should_persist(has_path=bool(doc.file_path), dirty=doc.dirty)
        ]
        signature = tuple(
            (
                doc.file_path,
                doc.display_name,
                doc.dirty,
                canonical_document_digest(doc.state),
            )
            for doc in persisted
        )
        if signature == self._last_signature:
            return

        # Each generation writes payloads under fresh, unique names and only
        # prunes the previous generation *after* the new manifest is committed.
        # A crash mid-write therefore always leaves the on-disk manifest pointing
        # at intact payloads — never at a name that has been overwritten with a
        # different document's state.
        self._generation += 1
        generation = self._generation
        entries: list[DocEntry] = []
        referenced: set[str] = set()
        for index, doc in enumerate(persisted):
            snapshot_name: str | None = None
            if needs_snapshot(dirty=doc.dirty):
                snapshot_name = f"doc-{generation}-{index}.json"
                self._write_snapshot(snapshot_name, doc.state)
                referenced.add(snapshot_name)
            entries.append(
                DocEntry(
                    file_path=doc.file_path,
                    display_name=doc.display_name,
                    dirty=doc.dirty,
                    snapshot=snapshot_name,
                )
            )
        self._write_manifest(
            SessionManifest(
                pid=self._pid,
                clean_exit=False,
                process_identity=self._process_identity,
                docs=entries,
            )
        )
        self._prune_snapshots(referenced)
        self._last_signature = signature

    def mark_clean_exit(self) -> None:
        manifest = self._read_manifest(self._dir)
        if manifest is None:
            return
        manifest.clean_exit = True
        self._write_manifest(manifest)

    def consume_previous_sessions(self) -> RestoreResult:
        """Reopen recoverable sibling sessions and delete every consumable one.

        Crashed sessions are always restored (unsaved work is never pruned
        unrecovered) and the newest clean session is reopened for last-session
        continuity. Live instances' sessions are untouched.
        """
        manifests: dict[str, SessionManifest] = {}
        order: dict[str, float] = {}
        for child in self._sibling_dirs():
            manifest = self._read_manifest(child)
            if manifest is None:
                # A corrupt manifest is not proof that its owner is gone. Reap
                # only an old directory whose independently readable sidecar
                # proves that the recorded process exited or its pid was reused.
                if _is_old_orphan(child) and self._owner_proves_orphan(child):
                    shutil.rmtree(child, ignore_errors=True)
                continue
            try:
                mtime = child.stat().st_mtime
            except OSError:
                # Another instance consumed this sibling between listing and now.
                continue
            manifests[child.name] = manifest
            order[child.name] = mtime

        candidates = [
            (session_id, manifests[session_id], order[session_id])
            for session_id in manifests
        ]
        identities: dict[int, str | None] = {}

        def process_identity_for(pid: int) -> str | None:
            if pid not in identities:
                identities[pid] = _process_identity(pid)
            return identities[pid]

        plan = plan_restore(
            candidates,
            is_alive=_pid_alive,
            process_identity_for=process_identity_for,
        )

        result = RestoreResult()
        for session_id in plan.restore:
            manifest = manifests[session_id]
            for entry in entries_to_restore(manifest):
                restored = self._restore_entry(
                    self._root / session_id, entry, clean_exit=manifest.clean_exit
                )
                if restored is None:
                    continue
                result.docs.append(restored)
                # Count only work actually reopened as unsaved: an entry whose
                # snapshot is missing/truncated (restored is None) or that fell
                # back to its on-disk file (restored.dirty is False) must not
                # inflate the "Recovered N unsaved" message.
                if restored.dirty:
                    result.recovered_unsaved += 1
        # Defer deletion: the caller prunes only after these documents are safely
        # snapshotted into the new session, so a crash mid-restore cannot destroy
        # the last on-disk copy of the recovered work.
        result.prune_ids = plan.prune
        return result

    def prune_sessions(self, session_ids: list[str]) -> None:
        for session_id in session_ids:
            shutil.rmtree(self._root / session_id, ignore_errors=True)

    # --- internals --------------------------------------------------------

    def _sibling_dirs(self) -> list[Path]:
        # Best-effort: the sessions root may be missing, or (if app-data is
        # broken) be a regular file — iterdir raises NotADirectoryError then.
        # Either way there are no recoverable sessions; never block startup.
        try:
            children = list(self._root.iterdir())
        except OSError:
            return []
        return [
            child for child in children if child.is_dir() and child.name != self._id
        ]

    def _restore_entry(
        self, session_dir: Path, entry: DocEntry, *, clean_exit: bool
    ) -> RestoredDoc | None:
        # A crash prefers the snapshot (it holds unsaved edits); a clean exit
        # only reopens saved paths from disk.
        file_path = (
            entry.file_path
            if entry.file_path and is_canonical_saved_document_path(entry.file_path)
            else None
        )
        if not clean_exit and entry.snapshot:
            state = self._read_state(session_dir / entry.snapshot)
            if state is not None:
                return RestoredDoc(
                    state=state,
                    file_path=file_path,
                    display_name=entry.display_name,
                    dirty=entry.dirty,
                )
        if file_path and Path(file_path).exists():
            state = self._read_state(Path(file_path))
            if state is not None:
                return RestoredDoc(
                    state=state,
                    file_path=file_path,
                    display_name=entry.display_name,
                    dirty=False,
                )
        return None

    def _read_state(self, path: Path) -> dict | None:
        # Same narrowing as _read_manifest: a missing or unreadable file raises
        # OSError, a corrupt or schema-invalid payload raises ValueError, and
        # either means this entry is not recoverable. A programming error must
        # not be mistaken for a corrupt document and drop it from the restore.
        try:
            return read_document(path).state
        except (OSError, ValueError):
            return None

    def _manifest_path(self, session_dir: Path) -> Path:
        return session_dir / MANIFEST_NAME

    def _owner_path(self, session_dir: Path) -> Path:
        return session_dir / OWNER_NAME

    def _read_manifest(self, session_dir: Path) -> SessionManifest | None:
        try:
            data = _read_bounded_json(
                self._manifest_path(session_dir), max_bytes=_MAX_MANIFEST_BYTES
            )
        except (OSError, RecursionError, UnicodeError, ValueError):
            return None
        manifest = manifest_from_json(data)
        if manifest is None:
            return None
        owner_exists, process_identity = self._read_owner_identity(
            session_dir, manifest.pid
        )
        if owner_exists:
            # A malformed/unreadable sidecar makes ownership uncertain. Clear
            # even a development-v2 embedded identity so recovery fails closed.
            manifest.process_identity = process_identity
        # With no sidecar, retain an identity embedded by the short-lived v2
        # development format; legacy v1 manifests remain identity-less.
        return manifest

    def _write_manifest(self, manifest: SessionManifest) -> None:
        atomic_write_text(
            self._manifest_path(self._dir),
            _bounded_json_text(
                manifest_to_json(manifest), max_bytes=_MAX_MANIFEST_BYTES
            ),
        )
        # Commit the old-version-readable manifest first. A sidecar failure is
        # safe: new readers fall back to conservative PID-only ownership.
        with contextlib.suppress(OSError):
            self._write_owner_identity()

    def _read_owner_identity(
        self, session_dir: Path, manifest_pid: int
    ) -> tuple[bool, str | None]:
        owner = self._read_owner_record(session_dir)
        if not owner.exists:
            return False, None
        if owner.pid != manifest_pid:
            return True, None
        return True, owner.process_identity

    def _read_owner_record(self, session_dir: Path) -> _OwnerRecord:
        try:
            data = _read_bounded_json(
                self._owner_path(session_dir), max_bytes=_MAX_OWNER_BYTES
            )
        except FileNotFoundError:
            return _OwnerRecord(exists=False)
        except (OSError, RecursionError, UnicodeError, ValueError):
            return _OwnerRecord(exists=True)
        if not isinstance(data, dict) or set(data) != {
            "version",
            "pid",
            "process_identity",
        }:
            return _OwnerRecord(exists=True)
        version = data.get("version")
        pid = data.get("pid")
        process_identity = data.get("process_identity")
        if (
            type(version) is not int
            or version != _OWNER_SCHEMA_VERSION
            or type(pid) is not int
            or not 1 <= pid <= _MAX_PID
            or not is_valid_process_identity(process_identity)
        ):
            return _OwnerRecord(exists=True)
        return _OwnerRecord(
            exists=True,
            pid=pid,
            process_identity=process_identity,
        )

    def _owner_proves_orphan(self, session_dir: Path) -> bool:
        owner = self._read_owner_record(session_dir)
        if owner.pid is None or owner.process_identity is None:
            return False
        if not _pid_alive(owner.pid):
            return True
        live_identity = _process_identity(owner.pid)
        return (
            is_valid_process_identity(live_identity)
            and live_identity != owner.process_identity
        )

    def _write_owner_identity(self) -> None:
        owner_path = self._owner_path(self._dir)
        if (
            not is_valid_process_identity(self._process_identity)
            or type(self._pid) is not int
            or not 1 <= self._pid <= _MAX_PID
        ):
            owner_path.unlink(missing_ok=True)
            return
        atomic_write_text(
            owner_path,
            _bounded_json_text(
                {
                    "version": _OWNER_SCHEMA_VERSION,
                    "pid": self._pid,
                    "process_identity": self._process_identity,
                },
                max_bytes=_MAX_OWNER_BYTES,
            ),
        )

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
