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
    # Child CLIs must exercise this checkout too, even when the interpreter's
    # editable installation points at a different worktree.
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "app")
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
    atoms: list[dict[str, object]] | None = None,
    bonds: list[dict[str, object]] | None = None,
    arrows: list[dict[str, object]] | None = None,
) -> Path:
    request = tmp_path / "layout.json"
    request.write_text(
        json.dumps(
            {
                "format": "chemvas-document-composition",
                "version": 1,
                "atoms": atoms or [],
                "bonds": bonds or [],
                "notes": notes,
                "shapes": shapes or [],
                "arrows": arrows or [],
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
        "arrow-structure-overlap": 0,
        "atom-bond-overlap": 0,
        "charge-bond-overlap": 0,
        "outside-sheet": 0,
        "text-arrow-overlap": 0,
        "text-bond-overlap": 0,
        "text-shape-border-overlap": 0,
        "text-text-overlap": 1,
    }
    assert report["warnings"][0]["code"] == "text-text-overlap"
    assert report["warnings"][0]["items"] == [
        {"index": 0, "kind": "note"},
        {"index": 1, "kind": "note"},
    ]


def test_child_cli_uses_this_checkout_instead_of_ambient_pythonpath(tmp_path):
    source = _compose(tmp_path, notes=[])
    foreign = tmp_path / "foreign"
    package = foreign / "chemvas"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        'raise RuntimeError("imported the wrong checkout")\n'
    )
    result = _run("check-layout", str(source), env_updates={"PYTHONPATH": str(foreign)})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["coverage"]["ok_meaning"] == (
        "No warnings in the checked collision and sheet-boundary classes."
    )


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
    coverage = report["coverage"]
    assert (
        coverage["ok_meaning"]
        == "No warnings in the checked collision and sheet-boundary classes."
    )
    assert (
        "Aesthetic quality, semantic label ownership, chemical correctness or stereochemical meaning."
        in coverage["not_checked"]
    )
    assert (
        "Attached arrow-label ink against molecular bonds and own or other arrow strokes."
        in coverage["checked"]
    )


def test_check_layout_attached_label_overlap_preserves_native_source(
    tmp_path: Path,
) -> None:
    source = _compose(
        tmp_path,
        notes=[],
        arrows=[
            {
                "kind": "arrow",
                "start": [-40.0, 0.0],
                "end": [40.0, 0.0],
                "labels": {"above": "k_1^‡"},
            }
            for _ in range(2)
        ],
    )
    before = source.read_bytes()
    result = _run("check-layout", str(source))
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["warning_count"] == 1
    assert report["warnings"][0]["code"] == "text-text-overlap"
    assert report["warnings"][0]["items"] == [
        {"kind": "arrow-label", "index": 0, "side": "above"},
        {"kind": "arrow-label", "index": 1, "side": "above"},
    ]
    assert source.read_bytes() == before
    assert report["source_sha256"] == hashlib.sha256(before).hexdigest()


def test_check_layout_reports_attached_label_outside_sheet(tmp_path: Path) -> None:
    source = _compose(
        tmp_path,
        notes=[],
        arrows=[
            {
                "kind": "arrow",
                "start": [1000.0, 0.0],
                "end": [1080.0, 0.0],
                "labels": {"below": "k_1"},
            }
        ],
    )
    result = _run("check-layout", str(source))
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["warning_count"] == 1
    assert report["warnings"][0]["code"] == "outside-sheet"
    assert report["warnings"][0]["items"] == [
        {"kind": "arrow-label", "index": 0, "side": "below"}
    ]


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
        "arrow-structure-overlap": 0,
        "atom-bond-overlap": 0,
        "charge-bond-overlap": 0,
        "outside-sheet": 0,
        "text-arrow-overlap": 0,
        "text-bond-overlap": 0,
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
        "arrow-structure-overlap": 0,
        "atom-bond-overlap": 0,
        "charge-bond-overlap": 0,
        "outside-sheet": 1,
        "text-arrow-overlap": 0,
        "text-bond-overlap": 0,
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


@pytest.mark.parametrize("charged", [False, True])
def test_molecular_pair_budget_rejects_before_opening_qt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, charged: bool
) -> None:
    count = 111 if charged else 100
    atoms = [
        {
            "id": index,
            "element": "C" if charged else "N",
            "x": float(index * 30),
            "y": 0.0,
            **({"formal_charge": 1} if charged else {}),
        }
        for index in range(count)
    ]
    source = _compose(
        tmp_path,
        notes=[],
        atoms=atoms,
        bonds=[{"a": index, "b": index + 1, "order": 1} for index in range(count - 1)],
    )
    before = source.read_bytes()

    def forbidden(_state):
        raise AssertionError("Resource rejection must precede Qt")

    monkeypatch.setattr(document_layout_check, "_check_offscreen", forbidden)
    with pytest.raises(SystemExit) as error:
        document_layout_check.run(["check-layout", str(source)])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "layout work limit of 10000" in output.err
    assert source.read_bytes() == before


def test_check_layout_reports_atom_bond_ids_and_preserves_source(
    tmp_path: Path,
) -> None:
    source = _compose(
        tmp_path,
        notes=[],
        atoms=[
            {"id": 0, "element": "C", "x": -40.0, "y": 0.0},
            {"id": 1, "element": "C", "x": 40.0, "y": 0.0},
            {"id": 2, "element": "H", "x": 0.0, "y": 0.0},
        ],
        bonds=[{"a": 0, "b": 1, "order": 1}],
    )
    before = source.read_bytes()
    first = _run("check-layout", str(source))
    second = _run("check-layout", str(source))
    assert first.returncode == second.returncode == 1
    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    report = json.loads(first.stdout)
    assert report["counts"]["atom-bond-overlap"] == 1
    assert report["warnings"][0]["items"] == [
        {"kind": "atom", "id": 2},
        {"kind": "bond", "atom_ids": [0, 1]},
    ]
    assert report["source_sha256"] == hashlib.sha256(before).hexdigest()
    assert source.read_bytes() == before


def test_check_layout_reports_attached_charge_index_without_mutation(
    tmp_path: Path,
) -> None:
    from chemvas.core.document_io import read_exact_document, write_document

    composed = _compose(
        tmp_path,
        notes=[],
        atoms=[
            {"id": 0, "element": "C", "x": -40.0, "y": 0.0},
            {"id": 1, "element": "C", "x": 40.0, "y": 0.0},
            {"id": 2, "element": "C", "x": 0.0, "y": 80.0, "formal_charge": -1},
        ],
        bonds=[{"a": 0, "b": 1, "order": 1}],
    )
    _, document = read_exact_document(composed, max_bytes=1024 * 1024)
    document.state["marks"][0].update(x=0.0, y=0.0, dx=0.0, dy=-80.0)
    source = tmp_path / "charged.chemvas"
    write_document(source, document.state, document.payload["version"])
    before = source.read_bytes()

    result = _run("check-layout", str(source))

    assert result.returncode == 1
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["counts"]["charge-bond-overlap"] == 1
    assert report["warnings"][0]["items"] == [
        {"kind": "mark", "index": 0, "atom_id": 2},
        {"kind": "bond", "atom_ids": [0, 1]},
    ]
    assert report["source_sha256"] == hashlib.sha256(before).hexdigest()
    assert source.read_bytes() == before
