from __future__ import annotations

import os

import pytest
from ui import app_data_paths


def test_falls_back_to_the_next_candidate_when_one_cannot_be_created(tmp_path, monkeypatch):
    # A path *under a regular file* cannot be mkdir'd (NotADirectoryError).
    (tmp_path / "blocker").write_text("x")
    unusable = tmp_path / "blocker" / "nope"
    good = tmp_path / "good"
    monkeypatch.setattr(app_data_paths, "_candidate_dirs", lambda: [unusable, good])

    result = app_data_paths.app_data_dir()

    assert result == good
    assert good.is_dir()


def test_never_raises_even_if_every_candidate_fails(tmp_path, monkeypatch):
    (tmp_path / "blocker").write_text("x")
    unusable = tmp_path / "blocker" / "nope"
    monkeypatch.setattr(app_data_paths, "_candidate_dirs", lambda: [unusable])

    # Autosave/recents are best-effort: resolving the dir must never raise, even
    # when nothing is writable. Callers tolerate the dir not existing.
    result = app_data_paths.app_data_dir()

    assert result == unusable


def test_skips_an_existing_read_only_directory(tmp_path, monkeypatch):
    # mkdir(exist_ok=True) "succeeds" on an existing read-only dir; only a write
    # probe reveals it is unusable, so we must fall through to a writable one.
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root bypasses directory write permissions")
    readonly = tmp_path / "readonly"
    readonly.mkdir()
    readonly.chmod(0o500)  # r-x: exists but not writable
    good = tmp_path / "good"
    monkeypatch.setattr(app_data_paths, "_candidate_dirs", lambda: [readonly, good])

    try:
        result = app_data_paths.app_data_dir()
    finally:
        readonly.chmod(0o700)  # restore so tmp cleanup can remove it

    assert result == good
    assert list(good.iterdir()) == []  # the write probe cleaned up after itself


def test_sessions_dir_is_best_effort(tmp_path, monkeypatch):
    (tmp_path / "blocker").write_text("x")
    unusable = tmp_path / "blocker" / "nope"
    monkeypatch.setattr(app_data_paths, "_candidate_dirs", lambda: [unusable])

    # Must not raise even though the parent cannot be created.
    assert app_data_paths.sessions_dir() == unusable / "sessions"
