from __future__ import annotations

from ui.recent_documents_logic import (
    MAX_RECENT,
    add_recent,
    from_json,
    prune_missing,
    recent_menu_entries,
    to_json,
)


def test_add_promotes_to_front():
    result = add_recent(["/a/x.chemvas", "/a/y.chemvas"], "/a/z.chemvas")
    assert result == ["/a/z.chemvas", "/a/x.chemvas", "/a/y.chemvas"]


def test_add_dedupes_existing_and_moves_it_to_front():
    result = add_recent(["/a/x.chemvas", "/a/y.chemvas"], "/a/y.chemvas")
    assert result == ["/a/y.chemvas", "/a/x.chemvas"]


def test_add_dedupes_by_normalized_path():
    # Lexical normalization collapses '..' and duplicate separators.
    result = add_recent(["/a/x.chemvas"], "/a/b/../x.chemvas")
    assert result == ["/a/b/../x.chemvas"]  # first spelling kept, no duplicate


def test_add_caps_at_max():
    seed = [f"/a/{i}.chemvas" for i in range(MAX_RECENT)]
    result = add_recent(seed, "/a/new.chemvas")
    assert len(result) == MAX_RECENT
    assert result[0] == "/a/new.chemvas"
    assert "/a/9.chemvas" not in result  # the oldest fell off the end


def test_prune_missing_keeps_only_existing_and_dedupes():
    present = {"/a/x.chemvas"}
    result = prune_missing(
        ["/a/x.chemvas", "/a/gone.chemvas", "/a/x.chemvas"],
        exists=lambda p: p in present,
    )
    assert result == ["/a/x.chemvas"]


def test_menu_entries_use_basename_as_label():
    assert recent_menu_entries(["/lab/aspirin.chemvas"]) == [("aspirin.chemvas", "/lab/aspirin.chemvas")]


def test_json_round_trips():
    paths = ["/a/x.chemvas", "/a/y.chemvas"]
    assert from_json(to_json(paths)) == paths


def test_from_json_tolerates_garbage():
    assert from_json(None) == []
    assert from_json({"paths": "not-a-list"}) == []
    assert from_json({"paths": ["/a/x.chemvas", 5, None]}) == ["/a/x.chemvas"]
