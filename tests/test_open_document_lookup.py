from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from chemvas.ui import open_document_lookup
from chemvas.ui.open_document_lookup import find_open_document, normalized_path_key


def _window(canvases):
    return SimpleNamespace(
        tab_references=SimpleNamespace(all_canvases=lambda: canvases)
    )


def _paths(mapping):
    return lambda canvas: mapping.get(id(canvas))


def test_finds_the_window_and_canvas_showing_the_path():
    a, b = object(), object()
    window = _window([a, b])
    result = find_open_document(
        "/lab/y.chemvas",
        windows=[window],
        path_of=_paths({id(a): "/lab/x.chemvas", id(b): "/lab/y.chemvas"}),
    )
    assert result == (window, b)


def test_returns_none_when_no_window_has_the_path():
    a = object()
    window = _window([a])
    result = find_open_document(
        "/lab/z.chemvas", windows=[window], path_of=_paths({id(a): "/lab/x.chemvas"})
    )
    assert result is None


def test_matches_regardless_of_path_spelling():
    a = object()
    window = _window([a])
    result = find_open_document(
        "/lab/sub/../x.chemvas",
        windows=[window],
        path_of=_paths({id(a): "/lab/x.chemvas"}),
    )
    assert result == (window, a)


def test_ignores_unsaved_canvases_with_no_path():
    a = object()
    window = _window([a])
    result = find_open_document(
        "/lab/x.chemvas", windows=[window], path_of=_paths({})
    )  # path_of → None
    assert result is None


def test_scans_multiple_windows_and_returns_first_match():
    a, b = object(), object()
    first = _window([a])
    second = _window([b])
    result = find_open_document(
        "/lab/x.chemvas",
        windows=[first, second],
        path_of=_paths({id(a): "/other.chemvas", id(b): "/lab/x.chemvas"}),
    )
    assert result == (second, b)


def test_matches_an_existing_symlink_alias(tmp_path):
    source = tmp_path / "source.chemvas"
    alias = tmp_path / "alias.chemvas"
    source.write_text("document", encoding="utf-8")
    alias.symlink_to(source)
    canvas = object()
    window = _window([canvas])

    result = find_open_document(
        str(alias),
        windows=[window],
        path_of=_paths({id(canvas): str(source)}),
    )

    assert result == (window, canvas)


def test_matches_an_existing_hard_link_alias(tmp_path):
    source = tmp_path / "source.chemvas"
    alias = tmp_path / "alias.chemvas"
    source.write_text("document", encoding="utf-8")
    os.link(source, alias)
    canvas = object()
    window = _window([canvas])

    result = find_open_document(
        str(alias),
        windows=[window],
        path_of=_paths({id(canvas): str(source)}),
    )

    assert result == (window, canvas)


def test_can_exclude_the_canvas_being_saved(tmp_path):
    path = tmp_path / "source.chemvas"
    path.write_text("document", encoding="utf-8")
    canvas = object()
    window = _window([canvas])

    result = find_open_document(
        str(path),
        windows=[window],
        path_of=_paths({id(canvas): str(path)}),
        exclude_canvas=canvas,
    )

    assert result is None


def test_normalized_key_is_absolute_and_platform_normalized(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    key = normalized_path_key("a.chemvas")
    assert os.path.isabs(key)
    assert key == os.path.normcase(key)


def test_missing_path_case_folds_on_a_case_insensitive_macos_volume(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(
        "chemvas.ui.open_document_lookup._path_is_on_case_insensitive_volume",
        lambda _path: True,
    )

    assert normalized_path_key("/Lab/Foo.chemvas") == normalized_path_key(
        "/Lab/foo.chemvas"
    )


def test_missing_path_preserves_case_on_a_case_sensitive_macos_volume(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(
        "chemvas.ui.open_document_lookup._path_is_on_case_insensitive_volume",
        lambda _path: False,
    )

    assert normalized_path_key("/Lab/Foo.chemvas") != normalized_path_key(
        "/Lab/foo.chemvas"
    )


def test_case_probe_never_uses_the_parent_side_of_a_mount(monkeypatch):
    mount = "/Volumes/CaseSensitive"

    def exists(path):
        return str(path) == mount

    def stat(path):
        device = 2 if str(path) == mount else 1
        return SimpleNamespace(st_dev=device)

    monkeypatch.setattr("pathlib.Path.exists", exists)
    monkeypatch.setattr("pathlib.Path.stat", stat)
    samefile = mock.Mock(side_effect=AssertionError("crossed the mount boundary"))
    monkeypatch.setattr(os.path, "samefile", samefile)

    assert (
        open_document_lookup._path_is_on_case_insensitive_volume(f"{mount}/new.chemvas")
        is False
    )
    samefile.assert_not_called()


def test_case_probe_fails_closed_after_an_unconfirmed_same_device_probe(monkeypatch):
    project = "/Volumes/CaseSensitive/project"
    devices = {
        project: 2,
        "/Volumes/CaseSensitive": 2,
        "/Volumes": 1,
    }

    monkeypatch.setattr("pathlib.Path.exists", lambda path: str(path) == project)
    monkeypatch.setattr(
        "pathlib.Path.stat",
        lambda path: SimpleNamespace(st_dev=devices[str(path)]),
    )
    samefile = mock.Mock(side_effect=FileNotFoundError)
    monkeypatch.setattr(os.path, "samefile", samefile)

    assert (
        open_document_lookup._path_is_on_case_insensitive_volume(
            f"{project}/new.chemvas"
        )
        is False
    )
    samefile.assert_called_once_with(
        Path(project), Path("/Volumes/CaseSensitive/Project")
    )


def test_key_is_case_sensitive_on_linux():
    assert normalized_path_key("/Lab/Foo.chemvas") != normalized_path_key(
        "/Lab/foo.chemvas"
    )


def test_nonexistent_path_resolves_a_symlinked_parent(tmp_path):
    physical = tmp_path / "physical"
    physical.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(physical, target_is_directory=True)

    assert normalized_path_key(str(alias / "new.chemvas")) == normalized_path_key(
        str(physical / "new.chemvas")
    )
