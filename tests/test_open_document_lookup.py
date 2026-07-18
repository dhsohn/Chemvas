from __future__ import annotations

import os
from types import SimpleNamespace

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


def test_normalized_key_is_absolute_and_case_folded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    key = normalized_path_key("a.chemvas")
    assert os.path.isabs(key)
    assert key == os.path.normcase(key)


def test_key_is_case_insensitive_on_macos(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    # macOS default volumes are case-insensitive; different spellings must match.
    assert normalized_path_key("/Lab/Foo.chemvas") == normalized_path_key(
        "/Lab/foo.chemvas"
    )


def test_key_is_case_sensitive_on_linux(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    assert normalized_path_key("/Lab/Foo.chemvas") != normalized_path_key(
        "/Lab/foo.chemvas"
    )
