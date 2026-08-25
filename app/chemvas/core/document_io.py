from __future__ import annotations

import contextlib
import json
import os
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Any, cast

from chemvas.domain.document import (
    build_document_payload,
    extract_document_state,
    normalize_json_numbers,
)
from chemvas.domain.json_io import strict_json_loads

PathType = str | PathLike[str]


@dataclass(frozen=True)
class ChemvasDocument:
    payload: dict[str, Any]
    state: dict[str, Any]


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
    normalized_payload = cast(dict[str, Any], normalize_json_numbers(payload))
    normalized_state = cast(dict[str, Any], normalized_payload["state"])
    return ChemvasDocument(payload=normalized_payload, state=normalized_state)


def parse_document(payload: object) -> ChemvasDocument:
    state = extract_document_state(payload)
    normalized_payload = cast(dict[str, Any], normalize_json_numbers(payload))
    normalized_state = cast(dict[str, Any], normalize_json_numbers(state))
    return ChemvasDocument(payload=normalized_payload, state=normalized_state)


def write_document(
    path: PathType, state: dict[str, Any], version: int
) -> ChemvasDocument:
    document = create_document(state, version)
    atomic_write_via_temp(
        path,
        lambda tmp: _write_document_payload(tmp, document.payload),
    )
    return document


def _write_document_payload(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def atomic_write_text(path: PathType, text: str, *, encoding: str = "utf-8") -> None:
    atomic_write_via_temp(
        path, lambda tmp: _write_text_payload(tmp, text, encoding=encoding)
    )


def _write_text_payload(path: Path, text: str, *, encoding: str) -> None:
    with path.open("w", encoding=encoding) as handle:
        handle.write(text)


def atomic_write_via_temp(path: PathType, writer: Callable[[Path], None]) -> None:
    target = Path(path)
    try:
        target_mode = stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        target_mode = None
    # Atomic write: render/write to a sibling temp file, flush to disk, then
    # replace. A crash/IO error mid-write leaves the previous file intact.
    with tempfile.NamedTemporaryFile(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
        delete=False,
    ) as tmp_handle:
        tmp = Path(tmp_handle.name)
    try:
        writer(tmp)
        if target_mode is not None:
            os.chmod(tmp, target_mode)
        with tmp.open("rb+") as handle:
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        # Never leave a stray temp file behind on failure.
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def read_document(path: PathType) -> ChemvasDocument:
    _source_bytes, document = read_exact_document(path)
    return document


def read_exact_document(path: PathType) -> tuple[bytes, ChemvasDocument]:
    """Read once so callers can hash the exact bytes that were parsed."""
    source_bytes = Path(path).read_bytes()
    try:
        payload = strict_json_loads(source_bytes)
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid Chemvas file.") from exc
    return source_bytes, parse_document(payload)


def atomic_create_bytes(path: PathType, content: bytes) -> None:
    """Atomically publish a new file without ever replacing an existing path."""
    output = Path(path)
    fd, raw_staging = tempfile.mkstemp(
        prefix=f".{output.name}.staging-",
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
