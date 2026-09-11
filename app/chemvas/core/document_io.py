from __future__ import annotations

import contextlib
import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass, field, replace
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from chemvas.domain.document import (
    MAX_DOCUMENT_BYTES,
    build_document_payload,
    extract_document_state,
    normalize_json_numbers,
)
from chemvas.domain.json_io import strict_json_loads

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

PathType = str | PathLike[str]


@dataclass(frozen=True)
class ChemvasDocument:
    payload: dict[str, Any]
    state: dict[str, Any]
    source_sha256: str | None = field(default=None, compare=False)


def create_document(state: dict[str, Any], version: int) -> ChemvasDocument:
    try:
        payload = build_document_payload(state, version)
    except ValueError as exc:
        # This is the save/export side: the state came from our own snapshot,
        # not from a file, so "Invalid Chemvas file." would mislead the user.
        raise ValueError(
            "Failed to save: the document state did not pass validation. "
            "This is a Chemvas bug — please report it."
        ) from exc
    normalized_payload = cast("dict[str, Any]", normalize_json_numbers(payload))
    normalized_state = cast("dict[str, Any]", normalized_payload["state"])
    return ChemvasDocument(payload=normalized_payload, state=normalized_state)


def parse_document(payload: object) -> ChemvasDocument:
    state = extract_document_state(payload)
    normalized_payload = cast("dict[str, Any]", normalize_json_numbers(payload))
    normalized_state = cast("dict[str, Any]", normalize_json_numbers(state))
    return ChemvasDocument(payload=normalized_payload, state=normalized_state)


def write_document(
    path: PathType, state: dict[str, Any], version: int
) -> ChemvasDocument:
    document = create_document(state, version)
    source_sha256: str | None = None

    def write_payload(tmp: Path) -> None:
        nonlocal source_sha256
        _write_document_payload(tmp, document.payload)
        # Bind the baseline to our exact staged bytes, never a later writer's
        # replacement of the destination after the atomic publication.
        with tmp.open("rb") as source:
            source_sha256 = hashlib.file_digest(source, "sha256").hexdigest()

    atomic_write_via_temp(path, write_payload)
    return replace(document, source_sha256=source_sha256)


def _write_document_payload(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError(f"output document exceeds the {MAX_DOCUMENT_BYTES}-byte limit")


def atomic_write_text(path: PathType, text: str, *, encoding: str = "utf-8") -> None:
    atomic_write_via_temp(
        path, lambda tmp: _write_text_payload(tmp, text, encoding=encoding)
    )


def _write_text_payload(path: Path, text: str, *, encoding: str) -> None:
    with path.open("w", encoding=encoding) as handle:
        handle.write(text)


def output_error_for(error: OSError, path: PathType) -> OSError:
    """Keep the OS reason, but report the user's destination, never staging names."""
    reason = error.strerror or str(error) or "Failed to write the output file"
    return OSError(error.errno, reason, os.fspath(path))


@contextlib.contextmanager
def _output_errors(path: PathType) -> Iterator[None]:
    try:
        yield
    except OSError as exc:
        raise output_error_for(exc, path) from exc


def resolved_output_path(path: PathType) -> Path:
    """Use the same resolved-leaf/parent policy as document Save."""
    return Path(os.path.realpath(os.path.abspath(path)))


def _output_mode(target: Path) -> int | None:
    try:
        metadata = target.stat()
    except FileNotFoundError:
        return None
    if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink > 1:
        raise ValueError(
            "The destination has multiple hard links. "
            "Choose another output file to avoid splitting the linked copies."
        )
    return stat.S_IMODE(metadata.st_mode)


def atomic_write_via_temp(path: PathType, writer: Callable[[Path], None]) -> None:
    with _output_errors(path):
        target = resolved_output_path(path)
        target_mode = _output_mode(target)
        # A short ASCII basename avoids both NAME_MAX truncation and Qt's
        # replacement of surrogate-escaped bytes in a user-chosen basename.
        with tempfile.NamedTemporaryFile(
            prefix=".chemvas-", suffix=".tmp", dir=target.parent, delete=False
        ) as tmp_handle:
            tmp = Path(tmp_handle.name)
        try:
            writer(tmp)
            # Refuse a hard link introduced while the writer was running too.
            _output_mode(target)
            if target_mode is not None:
                tmp.chmod(target_mode)
            with tmp.open("rb+") as handle:
                os.fsync(handle.fileno())
            tmp.replace(target)
        except BaseException:
            with contextlib.suppress(OSError):
                tmp.unlink()
            raise


def read_document(path: PathType) -> ChemvasDocument:
    _source_bytes, document = read_exact_document(path)
    return document


def read_exact_document(
    path: PathType, *, max_bytes: int = MAX_DOCUMENT_BYTES
) -> tuple[bytes, ChemvasDocument]:
    """Read once so callers can hash the exact bytes that were parsed.

    ``max_bytes`` bounds the read itself rather than a prior size check, so a
    file that grows past the limit while it is being read is still rejected.
    """
    with Path(path).open("rb") as stream:
        source_bytes = stream.read(max_bytes + 1)
    if len(source_bytes) > max_bytes:
        raise ValueError(f"input document exceeds the {max_bytes}-byte limit")
    try:
        payload = strict_json_loads(source_bytes)
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid Chemvas file.") from exc
    return source_bytes, replace(
        parse_document(payload),
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
    )


def atomic_create_bytes(path: PathType, content: bytes) -> None:
    """Atomically publish a new file without ever replacing an existing path."""
    with _output_errors(path):
        _create_bytes(path, content)


def _create_bytes(path: PathType, content: bytes) -> None:
    output = Path(path)
    fd, raw_staging = tempfile.mkstemp(
        prefix=".chemvas-create-",
        dir=output.parent,
    )
    staging = Path(raw_staging)
    # Handing the descriptor to os.fdopen transfers ownership: from here the
    # file object closes it on both the normal and the exceptional exit, so
    # nothing below may close it again. Only the handover itself can leave the
    # descriptor ours to close.
    try:
        handle = os.fdopen(fd, "wb")
    except BaseException:
        os.close(fd)
        with contextlib.suppress(OSError):
            staging.unlink()
        raise

    published = False
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(staging, output)
        except FileExistsError as exc:
            raise ValueError(f"output path already exists: {output}") from exc
        published = True
        # Once link() succeeds the requested file is committed. A best-effort
        # staging cleanup must not invert that success into a false failure.
        with contextlib.suppress(OSError):
            staging.unlink()
        _fsync_directory(output.parent)
    except BaseException:
        if not published:
            with contextlib.suppress(OSError):
                staging.unlink()
        raise


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        with contextlib.suppress(OSError):
            os.fsync(fd)
    finally:
        os.close(fd)
