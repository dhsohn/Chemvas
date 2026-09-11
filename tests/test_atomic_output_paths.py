from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QObject
from PyQt6.QtGui import QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.core.document_io import (
    atomic_create_bytes,
    atomic_write_text,
    atomic_write_via_temp,
    read_document,
    write_document,
)
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.features.document_composition import compose_document_state
from chemvas.features.insertion import RDKitResult
from chemvas.ui.rdkit_async_jobs import export_xyz_in_thread
from chemvas.ui.rdkit_export_job_state import active_rdkit_export_jobs


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def _state():
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [{"id": 0, "element": "O", "x": 0, "y": 0}],
            "bonds": [],
        }
    )


def _write(kind, path):
    if kind == "text":
        atomic_write_text(path, "new text")
    elif kind == "create":
        atomic_create_bytes(path, b"new bytes")
    elif kind == "save":
        document = write_document(path, _state(), CANVAS_FILE_VERSION)
        assert document.source_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
        assert read_document(path).state == json.loads(json.dumps(document.state))
    elif kind == "xyz":
        owner = QObject()
        successes, errors = [], []
        export_xyz_in_thread(
            owner,
            rdkit_adapter=SimpleNamespace(
                model_to_xyz_block_result=lambda *a, **kw: RDKitResult(
                    "1\nsynthetic XYZ\nO 0 0 0\n"
                )
            ),
            model=None,
            atom_annotations={},
            path=str(path),
            on_success=successes.append,
            on_error=errors.append,
        )
        for _ in range(300):
            QTest.qWait(10)
            if not active_rdkit_export_jobs():
                break
        assert not active_rdkit_export_jobs(), "XYZ worker did not finish"
        if errors:
            assert not successes
            raise ValueError(errors[0])
        assert successes == [str(path)]
    else:
        with offscreen_canvas(_state(), command="atomic-output-test") as (_, service):
            if kind == "mol":
                service.export_mol(str(path))
            else:
                service.export_figure(str(path), fmt=kind, scope="sheet")


@pytest.mark.skipif(os.name != "posix", reason="POSIX byte filename semantics")
@pytest.mark.parametrize("kind", ["save", "create", "mol", "xyz", "svg", "png", "pdf"])
@pytest.mark.parametrize("basename", ["korean", "ascii"])
def test_full_length_multibyte_basename_is_usable(tmp_path, kind, basename):
    # 80 Korean syllables + extension fits a 255-byte filesystem component.
    suffix = ".chemvas" if kind == "save" else "." + kind
    prefix = "가" * 80 if basename == "korean" else "a" * (255 - len(suffix))
    path = tmp_path / (prefix + suffix)
    assert len(os.fsencode(path.name)) <= os.pathconf(tmp_path, "PC_NAME_MAX")
    _write(kind, path)
    assert path.stat().st_size > 0
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.skipif(os.name != "posix", reason="POSIX byte filename semantics")
@pytest.mark.parametrize("kind", ["svg", "png", "pdf"])
@pytest.mark.parametrize("existing", [False, True])
def test_qt_export_to_surrogate_basename_writes_exact_requested_file(
    tmp_path, kind, existing
):
    path = tmp_path / os.fsdecode(b"figure\xe9." + kind.encode())
    if existing:
        path.write_bytes(b"previous figure")
    _write(kind, path)
    data = path.read_bytes()
    assert len(data) > 100
    assert data != b"previous figure"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.skipif(os.name != "posix", reason="POSIX byte filename semantics")
@pytest.mark.parametrize("kind", ["svg", "png", "pdf"])
@pytest.mark.parametrize("via_link", [False, True])
def test_qt_export_rejects_surrogate_parent_before_render(
    tmp_path, monkeypatch, kind, via_link
):
    parent = tmp_path / os.fsdecode(b"folder\xe9")
    parent.mkdir()
    # If Qt silently rewrites the path, this is where the output would land.
    lookalike = tmp_path / "folder\ufffd"
    lookalike.mkdir()
    target = parent / ("figure." + kind)
    target.write_bytes(b"original")
    path = tmp_path / ("link." + kind) if via_link else target
    if via_link:
        path.symlink_to(target)
    monkeypatch.setattr(
        "chemvas.ui.canvas_document_session_service.export_canvas_scene_for",
        lambda *a, **kw: pytest.fail("unsafe filename reached Qt renderer"),
    )
    with pytest.raises(ValueError, match="UTF-8"):
        _write(kind, path)
    assert target.read_bytes() == b"original"
    assert list(parent.iterdir()) == [target]
    assert not list(lookalike.iterdir())
    if via_link:
        assert path.is_symlink()


@pytest.mark.skipif(os.name != "posix", reason="POSIX link and permission semantics")
@pytest.mark.parametrize("kind", ["save", "mol", "xyz", "svg", "png", "pdf"])
@pytest.mark.parametrize("link_kind", ["symlink", "hardlink"])
def test_exports_preserve_link_identity_and_target_mode(tmp_path, kind, link_kind):
    target = tmp_path / "original"
    target.write_bytes(b"original bytes")
    target.chmod(0o640)
    link = tmp_path / ("export." + kind)
    if link_kind == "symlink":
        link.symlink_to(target.name)
        _write(kind, link)
        assert link.is_symlink()
        assert target.read_bytes() != b"original bytes"
        assert target.read_bytes() == link.read_bytes()
        assert stat.S_IMODE(target.stat().st_mode) == 0o640
    else:
        os.link(target, link)
        with pytest.raises(ValueError, match="hard link"):
            _write(kind, link)
        assert target.read_bytes() == link.read_bytes() == b"original bytes"
        assert os.path.samefile(target, link)
    assert set(tmp_path.iterdir()) == {target, link}


@pytest.mark.parametrize("kind", ["text", "create"])
@pytest.mark.parametrize("phase", ["temp", "flush", "publish"])
def test_filesystem_error_identifies_user_output_not_private_staging(
    tmp_path, monkeypatch, kind, phase
):
    path = tmp_path / "requested.output"
    if kind == "text":
        path.write_bytes(b"original")
    function = {
        ("text", "temp"): "tempfile.NamedTemporaryFile",
        ("create", "temp"): "tempfile.mkstemp",
        ("text", "flush"): "os.fsync",
        ("create", "flush"): "os.fsync",
        ("text", "publish"): "pathlib.Path.replace",
        ("create", "publish"): "os.link",
    }[kind, phase]

    def fail(*a, **kw):
        raise OSError(
            errno.ENOSPC, "No space left on device", "/private/.hidden-staging"
        )

    monkeypatch.setattr(function, fail)
    with pytest.raises(OSError) as failure:
        _write(kind, path)
    assert failure.value.errno == errno.ENOSPC
    assert failure.value.filename == str(path)
    assert "hidden-staging" not in str(failure.value)
    assert "requested.output" in str(failure.value)
    assert path.read_bytes() == b"original" if kind == "text" else not path.exists()
    assert list(tmp_path.iterdir()) == ([path] if kind == "text" else [])


@pytest.mark.parametrize("kind", ["svg", "png", "pdf"])
def test_silent_empty_renderer_does_not_replace_existing_output(
    tmp_path, monkeypatch, kind
):
    path = tmp_path / ("figure." + kind)
    path.write_bytes(b"original")
    monkeypatch.setattr(
        "chemvas.ui.canvas_document_session_service.export_canvas_scene_for",
        lambda *a, **kw: None,
    )
    with pytest.raises(ValueError, match="empty|produce"):
        _write(kind, path)
    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("kind", ["text", "create"])
def test_generic_writer_can_intentionally_publish_empty_bytes(tmp_path, kind):
    path = tmp_path / "empty"
    if kind == "text":
        atomic_write_text(path, "")
    else:
        atomic_create_bytes(path, b"")
    assert path.read_bytes() == b""


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
@pytest.mark.parametrize("dangling", [False, True])
def test_atomic_create_does_not_follow_or_replace_existing_symlink(tmp_path, dangling):
    target = tmp_path / "target"
    if not dangling:
        target.write_bytes(b"original")
    link = tmp_path / "requested"
    link.symlink_to(target.name)
    with pytest.raises(ValueError, match="already exists"):
        atomic_create_bytes(link, b"replacement")
    assert link.is_symlink()
    assert target.read_bytes() == b"original" if not dangling else not target.exists()


def test_atomic_create_preserves_a_destination_created_during_staging(
    tmp_path, monkeypatch
):
    target = tmp_path / "requested"
    real_link = os.link

    def competing_link(source, destination):
        target.write_bytes(b"another writer")
        real_link(source, destination)

    monkeypatch.setattr(os, "link", competing_link)
    with pytest.raises(ValueError, match="already exists"):
        atomic_create_bytes(target, b"our output")
    assert target.read_bytes() == b"another writer"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.skipif(os.name != "posix", reason="POSIX link semantics")
def test_atomic_write_rechecks_hard_links_before_publication(tmp_path):
    target = tmp_path / "requested"
    target.write_bytes(b"original")
    alias = tmp_path / "created-while-rendering"

    def writer(staging):
        staging.write_bytes(b"new")
        os.link(target, alias)

    with pytest.raises(ValueError, match="hard link"):
        atomic_write_via_temp(target, writer)
    assert target.read_bytes() == alias.read_bytes() == b"original"
    assert os.path.samefile(target, alias)
    assert set(tmp_path.iterdir()) == {target, alias}


@pytest.mark.parametrize("phase", ["worker", "publication"])
def test_async_xyz_error_uses_public_destination_and_preserves_original(
    tmp_path, monkeypatch, phase
):
    target = tmp_path / "requested.xyz"
    target.write_bytes(b"original")
    real_fsync = os.fsync
    calls = 0

    def fail_at_phase(fd):
        nonlocal calls
        calls += 1
        if calls == (1 if phase == "worker" else 2):
            raise OSError(
                errno.ENOSPC, "No space left on device", "/private/.hidden-staging"
            )
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_at_phase)
    with pytest.raises(ValueError, match="requested.xyz") as failure:
        _write("xyz", target)
    assert "hidden-staging" not in str(failure.value)
    assert ".chemvas-" not in str(failure.value)
    assert target.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [target]


def test_raster_encoder_failure_does_not_expose_staging_name(tmp_path, monkeypatch):
    target = tmp_path / "requested.png"
    target.write_bytes(b"original")
    monkeypatch.setattr(QImage, "save", lambda *a, **kw: False)
    with pytest.raises(ValueError, match="Failed to write PNG") as failure:
        _write("png", target)
    assert ".chemvas-" not in str(failure.value)
    assert ".tmp" not in str(failure.value)
    assert target.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [target]
