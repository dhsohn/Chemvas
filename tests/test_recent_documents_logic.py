from __future__ import annotations

from chemvas.ui.window.recent_documents_logic import (
    MAX_RECENT,
    add_recent,
    from_json,
    prune_missing,
    recent_menu_entries,
    to_json,
)


def test_add_promotes_to_front():
    result = add_recent(["/a/x.cdxml", "/a/y.cdxml"], "/a/z.cdxml")
    assert result == ["/a/z.cdxml", "/a/x.cdxml", "/a/y.cdxml"]


def test_add_dedupes_existing_and_moves_it_to_front():
    result = add_recent(["/a/x.cdxml", "/a/y.cdxml"], "/a/y.cdxml")
    assert result == ["/a/y.cdxml", "/a/x.cdxml"]


def test_add_dedupes_by_normalized_path():
    # Lexical normalization collapses '..' and duplicate separators.
    result = add_recent(["/a/x.cdxml"], "/a/b/../x.cdxml")
    assert result == ["/a/b/../x.cdxml"]  # first spelling kept, no duplicate


def test_add_caps_at_max():
    seed = [f"/a/{i}.cdxml" for i in range(MAX_RECENT)]
    result = add_recent(seed, "/a/new.cdxml")
    assert len(result) == MAX_RECENT
    assert result[0] == "/a/new.cdxml"
    assert "/a/9.cdxml" not in result  # the oldest fell off the end


def test_prune_missing_keeps_only_existing_and_dedupes():
    present = {"/a/x.cdxml"}
    result = prune_missing(
        ["/a/x.cdxml", "/a/gone.cdxml", "/a/x.cdxml"],
        exists=lambda p: p in present,
    )
    assert result == ["/a/x.cdxml"]


def test_menu_entries_use_basename_as_label():
    assert recent_menu_entries(["/lab/aspirin.cdxml"]) == [
        ("aspirin.cdxml", "/lab/aspirin.cdxml")
    ]


def test_menu_entries_disambiguate_same_names_with_their_full_parent():
    paths = ["/lab/one/a.cdxml", "/other/one/a.cdxml", "/lab/b.cdxml"]
    assert recent_menu_entries(paths) == [
        ("a.cdxml — /lab/one", paths[0]),
        ("a.cdxml — /other/one", paths[1]),
        ("b.cdxml", paths[2]),
    ]


def test_json_round_trips():
    paths = ["/a/x.cdxml", "/a/y.cdxml"]
    assert from_json(to_json(paths)) == paths


def test_from_json_tolerates_garbage():
    assert from_json(None) == []
    assert from_json({"paths": "not-a-list"}) == []
    assert from_json({"version": 1, "paths": ["/a/x.cdxml", 5, None]}) == []


def test_from_json_rejects_unknown_or_non_integer_schema_versions():
    paths = ["/a/x.cdxml"]
    assert from_json({"version": 2, "paths": paths}) == []
    assert from_json({"version": 1.0, "paths": paths}) == []
    assert from_json({"version": True, "paths": paths}) == []
