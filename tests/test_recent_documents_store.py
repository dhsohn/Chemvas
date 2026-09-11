from __future__ import annotations

import json
from pathlib import Path

from chemvas.ui.recent_documents_store import (
    clear_recent,
    load_recent,
    record_recent,
    save_recent,
)


def test_load_prunes_legacy_document_paths(tmp_path):
    recent = tmp_path / "recent.json"
    canonical = tmp_path / "drawing.chemvas"
    legacy = tmp_path / "legacy-document.json"
    canonical.write_text("{}")
    legacy.write_text("{}")
    recent.write_text(
        json.dumps(
            {
                "version": 1,
                "paths": [str(legacy), str(canonical)],
            }
        )
    )

    assert load_recent(path=recent) == [str(canonical)]


def test_record_ignores_legacy_document_paths(tmp_path):
    recent = tmp_path / "recent.json"
    legacy = tmp_path / "legacy-document.json"
    legacy.write_text("{}")

    assert record_recent(str(legacy), path=recent) == []
    assert not recent.exists()


def test_record_stores_absolute_paths(tmp_path, monkeypatch):
    recent = tmp_path / "recent.json"
    monkeypatch.chdir(tmp_path)
    (tmp_path / "rel.chemvas").write_text("{}")

    record_recent("rel.chemvas", path=recent)

    stored = load_recent(path=recent)
    assert stored == [str(tmp_path / "rel.chemvas")]


def test_load_prunes_entries_whose_files_vanished(tmp_path):
    recent = tmp_path / "recent.json"
    present = tmp_path / "here.chemvas"
    present.write_text("{}")
    save_recent([str(present), str(tmp_path / "gone.chemvas")], path=recent)

    assert load_recent(path=recent) == [str(present)]


def test_load_is_forgiving_of_a_missing_or_broken_file(tmp_path):
    missing = tmp_path / "nope.json"
    assert load_recent(path=missing) == []

    broken = tmp_path / "broken.json"
    broken.write_text("{ not json")
    assert load_recent(path=broken) == []


def test_clear_empties_the_list(tmp_path):
    recent = tmp_path / "recent.json"
    present = tmp_path / "a.chemvas"
    present.write_text("{}")
    record_recent(str(present), path=recent)

    clear_recent(path=recent)

    assert load_recent(path=recent) == []
    assert json.loads(recent.read_text(encoding="utf-8"))["paths"] == []


def test_most_recent_first_ordering(tmp_path):
    recent = tmp_path / "recent.json"
    for name in ("a", "b", "c"):
        target = tmp_path / f"{name}.chemvas"
        target.write_text("{}")
        record_recent(str(target), path=recent)

    loaded = load_recent(path=recent)
    assert [Path(p).name for p in loaded] == [
        "c.chemvas",
        "b.chemvas",
        "a.chemvas",
    ]


def test_record_dedupes_symlinks_preserving_the_latest_spelling(tmp_path):
    recent = tmp_path / "recent.json"
    target = tmp_path / "target.chemvas"
    target.write_text("{}")
    link = tmp_path / "link.chemvas"
    link.symlink_to(target)
    record_recent(str(link), path=recent)
    assert record_recent(str(target), path=recent) == [str(target)]
    assert record_recent(str(link), path=recent) == [str(link)]


def test_load_dedupes_existing_symlink_entries_without_rewriting(tmp_path):
    recent = tmp_path / "recent.json"
    target = tmp_path / "target.chemvas"
    target.write_text("{}")
    link = tmp_path / "link.chemvas"
    link.symlink_to(target)
    save_recent([str(link), str(target)], path=recent)
    before = recent.read_bytes()
    assert load_recent(path=recent) == [str(link)]
    assert recent.read_bytes() == before


def test_invalid_recent_path_does_not_block_other_entries(tmp_path):
    recent = tmp_path / "recent.json"
    target = tmp_path / "target.chemvas"
    target.write_text("{}")
    save_recent(["invalid\0.chemvas", str(target)], path=recent)
    assert load_recent(path=recent) == [str(target)]
