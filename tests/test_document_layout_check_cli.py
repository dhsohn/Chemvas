from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from chemvas.bootstrap import document_layout_check


def _run(
    *args: str, env_updates: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    if env_updates is not None:
        env.update(env_updates)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from chemvas.bootstrap.application import main; main()",
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


def _compose(
    tmp_path: Path,
    *,
    notes: list[dict[str, object]],
    shapes: list[dict[str, object]] | None = None,
) -> Path:
    request = tmp_path / "layout.json"
    request.write_text(
        json.dumps(
            {
                "format": "chemvas-document-composition",
                "version": 1,
                "atoms": [],
                "bonds": [],
                "notes": notes,
                "shapes": shapes or [],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "layout.chemvas"
    result = _run("compose-document", str(request), "--output", str(output))
    assert result.returncode == 0, result.stderr
    return output


def test_check_layout_reports_overlapping_notes_without_mutating_source(
    tmp_path: Path,
) -> None:
    source = _compose(
        tmp_path,
        notes=[
            {"text": "same place", "x": 0.0, "y": 0.0},
            {"text": "same place", "x": 0.0, "y": 0.0},
        ],
    )
    before = source.read_bytes()

    result = _run("check-layout", str(source))

    assert result.returncode == 1, result.stderr
    assert result.stderr == ""
    assert source.read_bytes() == before
    report = json.loads(result.stdout)
    assert report["format"] == "chemvas-layout-check-report"
    assert report["version"] == 1
    assert report["source_sha256"] == hashlib.sha256(before).hexdigest()
    assert report["chemvas_document_version"] == 7
    assert report["ok"] is False
    assert report["warning_count"] == 1
    assert report["counts"] == {
        "outside-sheet": 0,
        "text-shape-border-overlap": 0,
        "text-text-overlap": 1,
    }
    assert report["warnings"][0]["code"] == "text-text-overlap"
    assert report["warnings"][0]["items"] == [
        {"index": 0, "kind": "note"},
        {"index": 1, "kind": "note"},
    ]


def test_check_layout_enforces_size_limit_during_the_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "growing.chemvas"
    source.write_bytes(b"0" * (document_layout_check.MAX_DOCUMENT_BYTES + 1))
    real_stat = Path.stat

    def stale_stat(path: Path, *args: object, **kwargs: object) -> object:
        result = real_stat(path, *args, **kwargs)
        if path == source:
            return SimpleNamespace(st_mode=result.st_mode, st_size=0)
        return result

    def reject_unbounded_read(_path: Path) -> bytes:
        raise AssertionError("unbounded document read")

    monkeypatch.setattr(Path, "stat", stale_stat)
    monkeypatch.setattr(Path, "read_bytes", reject_unbounded_read)

    with pytest.raises(SystemExit) as exit_info:
        document_layout_check.run(["check-layout", str(source)])

    assert exit_info.value.code == 2


def test_check_layout_keeps_stderr_empty_under_factory_c_locale(
    tmp_path: Path,
) -> None:
    source = _compose(tmp_path, notes=[])

    result = _run(
        "check-layout",
        str(source),
        env_updates={"LC_ALL": "C", "LANG": "C"},
    )

    assert result.returncode == 0
    assert result.stderr == ""


def test_check_layout_ignores_notes_without_visible_glyphs(tmp_path: Path) -> None:
    source = _compose(
        tmp_path,
        notes=[
            {"text": "", "x": 100.0, "y": 100.0},
            {"text": "   ", "x": 100.0, "y": 100.0},
        ],
    )

    result = _run("check-layout", str(source))

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["warning_count"] == 0


def test_check_layout_rejects_documents_above_the_work_budget(tmp_path: Path) -> None:
    source = _compose(
        tmp_path,
        notes=[{"text": "same place", "x": 0.0, "y": 0.0} for _index in range(142)],
    )

    result = _run("check-layout", str(source))

    assert result.returncode == 2
    assert result.stdout == ""
    assert "layout work limit of 10000" in result.stderr


def test_check_layout_reports_text_crossing_shape_border(tmp_path: Path) -> None:
    source = _compose(
        tmp_path,
        notes=[{"text": "border crossing", "x": -5.0, "y": 0.0}],
        shapes=[
            {
                "shape_kind": "rect",
                "left": 0.0,
                "top": -20.0,
                "right": 100.0,
                "bottom": 50.0,
                "stroke_style": "solid",
            }
        ],
    )

    result = _run("check-layout", str(source))

    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["counts"] == {
        "outside-sheet": 0,
        "text-shape-border-overlap": 1,
        "text-text-overlap": 0,
    }
    assert report["warnings"][0]["code"] == "text-shape-border-overlap"
    assert report["warnings"][0]["items"] == [
        {"index": 0, "kind": "note"},
        {"index": 0, "kind": "shape"},
    ]


def test_check_layout_reports_note_outside_sheet(tmp_path: Path) -> None:
    source = _compose(
        tmp_path,
        notes=[{"text": "outside", "x": 1000.0, "y": 0.0}],
    )

    result = _run("check-layout", str(source))

    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["counts"] == {
        "outside-sheet": 1,
        "text-shape-border-overlap": 0,
        "text-text-overlap": 0,
    }
    assert report["warnings"][0]["code"] == "outside-sheet"
    assert report["warnings"][0]["items"] == [{"index": 0, "kind": "note"}]


def test_check_layout_refuses_a_document_whose_number_cannot_be_parsed(
    tmp_path: Path,
) -> None:
    source = _compose(tmp_path, notes=[])
    poisoned = source.read_text(encoding="utf-8").replace(
        "{", '{"scale": 1e99999999999999999999,', 1
    )
    source.write_text(poisoned, encoding="utf-8")

    result = _run("check-layout", str(source))

    assert result.returncode == 2
    assert result.stdout == ""
    assert "Traceback" not in result.stderr
    assert "Invalid Chemvas file." in result.stderr
