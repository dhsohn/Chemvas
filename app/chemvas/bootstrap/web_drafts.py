"""Durable drafts of unsaved browser documents, owned by one browser server.

The browser server listens on a new loopback port with a new launch credential
each time it starts, so the browser's own storage, which belongs to that
origin, cannot outlive a server restart. Drafts are therefore files in a
per-user folder that the server writes after each accepted change.

One running server owns the folder. It proves this with an operating-system
lock on ``owner.lock`` that ends with its process, including after a crash. A
second server started meanwhile works without drafts and says so, so two
processes never write or recover the same draft.

Each unsaved document has exactly one draft file, named by a random id. A window
keeps its draft claimed while it is open; closing the window releases the
claim and leaves the file for explicit recovery. Recovering claims that same
file for the recovering window instead of copying it, so repeated recovery,
reloads and restarts never multiply drafts. Files are only deleted when their
document is clean again, when the user replaces or discards it, never because
of age or a download.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import secrets
import stat
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from threading import RLock
from typing import IO, Any

from chemvas.core.document_io import atomic_write_text
from chemvas.domain.document import MAX_DOCUMENT_BYTES
from chemvas.domain.json_io import strict_json_loads

DRAFT_FORMAT = "chemvas-browser-draft"
DRAFT_VERSION = 1
# The same bound as the browser server's in-memory sessions.
MAX_DRAFTS = 16
MAX_DRAFT_NAME_CHARS = 1024
# One complete document, embedded images included, plus its small envelope.
MAX_DRAFT_BYTES = MAX_DOCUMENT_BYTES + 64 * 1024
LOCK_NAME = "owner.lock"
_DRAFT_ID = re.compile(r"[A-Za-z0-9_-]{16,64}")
_DRAFT_KEYS = frozenset(("format", "version", "name", "saved_at", "document"))
DAMAGED_DRAFT = "This draft is damaged and cannot be recovered. Its file has been kept."


class DraftError(ValueError):
    """A draft could not be written, read or changed; existing files are intact."""


def default_drafts_root() -> Path:
    """The per-user folder for browser drafts, resolved without Qt."""
    home = Path.home()
    if sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", ""))
        if not base.is_absolute():
            base = home / ".local" / "share"
    return base / "Chemvas" / "browser-drafts"


def new_draft_id() -> str:
    return secrets.token_urlsafe(18)


def valid_draft_id(value: object) -> str:
    """A draft id from a request; it names a file, so nothing else passes."""
    if not isinstance(value, str) or _DRAFT_ID.fullmatch(value) is None:
        raise DraftError("This recovery draft does not exist.")
    return value


@dataclass(frozen=True)
class DraftEntry:
    """One draft file; ``problem`` says why it cannot be recovered."""

    draft_id: str
    name: str | None
    saved_at: float | None
    problem: str | None
    owner: object | None


def _hold_lock(handle: IO[bytes]) -> None:
    if sys.platform == "win32":
        import msvcrt

        # Every server locks the same first byte of the empty lock file.
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _drop_lock(handle: IO[bytes]) -> None:
    if sys.platform == "win32":
        import msvcrt

        with contextlib.suppress(OSError):
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    handle.close()


def _reason(error: OSError) -> str:
    return error.strerror or str(error) or type(error).__name__


class BrowserDraftStore:
    """The draft folder of one running browser server and its window claims."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.lock = RLock()
        self.problem: str | None = None
        self._claims: dict[str, object] = {}
        self._lock_handle: IO[bytes] | None = None
        try:
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            handle = (root / LOCK_NAME).open("a+b")
        except OSError as error:
            self.problem = f"Automatic recovery is unavailable: {_reason(error)}."
            return
        try:
            _hold_lock(handle)
        except OSError:
            handle.close()
            self.problem = (
                "Automatic recovery is off: another running Chemvas browser "
                "server keeps the recovery drafts. Save copies of your work here, "
                "or close the other server and start this one again."
            )
            return
        # Staging files left by interrupted writes are kept: another program's
        # save into a chosen --drafts-dir uses the same names without this lock.
        self._lock_handle = handle

    @property
    def available(self) -> bool:
        return self._lock_handle is not None

    def close(self) -> None:
        """Stop owning the folder; drafts stay for the next server."""
        with self.lock:
            handle, self._lock_handle = self._lock_handle, None
            self._claims.clear()
        if handle is not None:
            _drop_lock(handle)

    def owner_of(self, draft_id: str) -> object | None:
        with self.lock:
            return self._claims.get(draft_id)

    def write(
        self, draft_id: str, owner: object, *, name: str, document: dict[str, Any]
    ) -> None:
        """Replace the owner's draft with the document it now holds."""
        with self.lock:
            self._require()
            path = self._path(draft_id)
            holder = self._claims.get(draft_id)
            if holder is not owner and (holder is not None or self._present(path)):
                raise DraftError(
                    "Another window now holds this drawing's recovery draft."
                )
            if holder is None and len(self._draft_paths()) >= MAX_DRAFTS:
                raise DraftError(
                    f"Recovery storage already holds {MAX_DRAFTS} drafts. Recover "
                    "or discard earlier work with File > Recover Unsaved Work… to "
                    "protect this drawing."
                )
            text = json.dumps(
                {
                    "format": DRAFT_FORMAT,
                    "version": DRAFT_VERSION,
                    "name": name[:MAX_DRAFT_NAME_CHARS],
                    "saved_at": time.time(),
                    "document": document,
                },
                ensure_ascii=False,
                allow_nan=False,
            )
            if len(text.encode()) > MAX_DRAFT_BYTES:
                raise DraftError(
                    "This drawing is too large for automatic recovery. Save a copy."
                )
            try:
                atomic_write_text(path, text)
            except OSError as error:
                raise DraftError(
                    f"The recovery draft could not be written ({_reason(error)}). "
                    "Its previous version, if any, is unchanged. Save a copy."
                ) from error
            self._claims[draft_id] = owner

    def discard(self, draft_id: str, owner: object) -> bool:
        """Delete the owner's draft: its document is clean or was replaced.

        Returns whether the owner held a draft to delete.
        """
        with self.lock:
            if self._claims.get(draft_id) is not owner:
                return False
            if self.available:
                try:
                    self._path(draft_id).unlink(missing_ok=True)
                except OSError as error:
                    raise DraftError(
                        "An outdated recovery draft could not be removed "
                        f"({_reason(error)})."
                    ) from error
            del self._claims[draft_id]
            return True

    def release(
        self, draft_id: str, owner: object, *, to: object | None = None
    ) -> None:
        """The owner's window closed; its draft stays for explicit recovery.

        With ``to``, a refused takeover returns the claim to its holder.
        """
        with self.lock:
            if self._claims.get(draft_id) is owner:
                if to is None:
                    del self._claims[draft_id]
                else:
                    self._claims[draft_id] = to

    def take(
        self, draft_id: str, owner: object, *, holder: object | None = None
    ) -> tuple[str, dict[str, Any]]:
        """Move the claim from ``holder`` (None: released) to ``owner``.

        Returns the draft's name and document. Nothing changes unless the
        claim is still ``holder``'s and the file reads as a draft; a caller
        that then rejects the document gives the claim back with ``release``.
        """
        with self.lock:
            self._require()
            current = self._claims.get(draft_id)
            if current is owner:
                raise DraftError("This drawing is already open in this window.")
            if current is not holder:
                raise DraftError(
                    "This drawing is still open in another window. Switch to it, "
                    "or recover it here to close it there."
                    if holder is None
                    else "This drawing moved to another window meanwhile. Open "
                    "File > Recover Unsaved Work… again."
                )
            path = self._path(draft_id)
            if not self._is_draft_file(path):
                raise DraftError("This recovery draft no longer exists.")
            envelope = self._read(path)
            self._claims[draft_id] = owner
            return envelope["name"], envelope["document"]

    def remove(self, draft_id: str) -> None:
        """Discard a draft that no open window holds."""
        with self.lock:
            self._require()
            if draft_id in self._claims:
                raise DraftError(
                    "This drawing is open in a window. Close it there first."
                )
            try:
                self._path(draft_id).unlink()
            except FileNotFoundError:
                return
            except OSError as error:
                raise DraftError(
                    f"The recovery draft could not be discarded ({_reason(error)})."
                ) from error

    def entries(self) -> list[DraftEntry]:
        """Every draft in the folder, newest first; unreadable ones are kept."""
        with self.lock:
            if not self.available:
                return []
            entries: list[DraftEntry] = []
            for path in self._draft_paths():
                owner = self._claims.get(path.stem)
                try:
                    envelope = self._read(path)
                except DraftError as error:
                    entries.append(DraftEntry(path.stem, None, None, str(error), owner))
                    continue
                entries.append(
                    DraftEntry(
                        path.stem, envelope["name"], envelope["saved_at"], None, owner
                    )
                )
        return sorted(entries, key=lambda entry: -(entry.saved_at or 0.0))

    def _require(self) -> None:
        if not self.available:
            raise DraftError(self.problem or "Automatic recovery has stopped.")

    def _path(self, draft_id: str) -> Path:
        return self.root / f"{valid_draft_id(draft_id)}.json"

    def _draft_paths(self) -> list[Path]:
        """The folder's draft files; an unreadable folder is an error, not empty."""
        try:
            children = list(self.root.iterdir())
        except OSError as error:
            raise DraftError(
                f"The recovery folder could not be read ({_reason(error)}). "
                "Its drafts are kept; save copies of your work."
            ) from error
        return [
            path
            for path in children
            if path.suffix == ".json"
            and _DRAFT_ID.fullmatch(path.stem) is not None
            and self._is_draft_file(path)
        ]

    @staticmethod
    def _present(path: Path) -> bool:
        try:
            path.lstat()
        except FileNotFoundError:
            return False
        except OSError as error:
            raise DraftError(
                f"The recovery folder could not be read ({_reason(error)})."
            ) from error
        return True

    @staticmethod
    def _is_draft_file(path: Path) -> bool:
        # Path.is_file reads some stat errors as "not a file"; those are errors.
        try:
            return stat.S_ISREG(os.lstat(path).st_mode)
        except FileNotFoundError:
            return False
        except OSError as error:
            raise DraftError(
                f"The recovery folder could not be read ({_reason(error)})."
            ) from error

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        try:
            with path.open("rb") as stream:
                data = stream.read(MAX_DRAFT_BYTES + 1)
        except OSError as error:
            raise DraftError(
                f"This draft could not be read ({_reason(error)}). Its file has been kept."
            ) from error
        if len(data) > MAX_DRAFT_BYTES:
            raise DraftError(DAMAGED_DRAFT)
        try:
            envelope = strict_json_loads(data)
        except (ValueError, RecursionError, UnicodeError):
            raise DraftError(DAMAGED_DRAFT) from None
        if not isinstance(envelope, dict) or envelope.get("format") != DRAFT_FORMAT:
            raise DraftError(DAMAGED_DRAFT)
        if type(envelope.get("version")) is not int:
            raise DraftError(DAMAGED_DRAFT)
        if envelope["version"] != DRAFT_VERSION:
            raise DraftError(
                "This draft was written by another Chemvas version and cannot be "
                "recovered here. Its file has been kept."
            )
        saved_at = envelope.get("saved_at")
        name = envelope.get("name")
        if isinstance(saved_at, bool) or not isinstance(saved_at, (int, Decimal)):
            raise DraftError(DAMAGED_DRAFT)
        if (
            set(envelope) != _DRAFT_KEYS
            or not isinstance(name, str)
            or len(name) > MAX_DRAFT_NAME_CHARS
            or not math.isfinite(saved_at)
            or not isinstance(envelope.get("document"), dict)
        ):
            raise DraftError(DAMAGED_DRAFT)
        return {**envelope, "saved_at": float(saved_at)}


__all__ = [
    "DAMAGED_DRAFT",
    "DRAFT_FORMAT",
    "DRAFT_VERSION",
    "MAX_DRAFTS",
    "MAX_DRAFT_BYTES",
    "BrowserDraftStore",
    "DraftEntry",
    "DraftError",
    "default_drafts_root",
    "new_draft_id",
    "valid_draft_id",
]
