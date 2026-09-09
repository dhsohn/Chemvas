from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from chemvas.bootstrap import document_layout
from chemvas.bootstrap.document_cli_shared import json_text, offscreen_canvas
from chemvas.core.document_io import read_document
from chemvas.domain.document import CANVAS_FILE_VERSION, build_document_payload
from chemvas.features.document_composition import compose_document_state

if TYPE_CHECKING:
    from pathlib import Path


def _source_state() -> dict:
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {"id": 0, "element": "P", "x": 20, "y": 15, "formal_charge": 1},
                {"id": 1, "element": "C", "x": 60, "y": 15},
                {"id": 2, "element": "C", "x": 20, "y": 55},
                {"id": 3, "element": "O", "x": 10, "y": -35, "formal_charge": -1},
                {"id": 4, "element": "P", "x": 500, "y": 200},
                {"id": 5, "element": "C", "x": 540, "y": 200},
                {"id": 6, "element": "O", "x": 500, "y": 240},
            ],
            "bonds": [
                {"a": 0, "b": 1, "order": 1, "style": "wedge"},
                {"a": 0, "b": 2, "order": 1, "style": "hash"},
                {"a": 4, "b": 5, "order": 1},
                {"a": 4, "b": 6, "order": 1},
            ],
            "notes": [
                {"x": -100, "y": 90, "text": "R", "style": {"font_size": 10}},
                {
                    "x": 1200,
                    "y": 400,
                    "text": "Intermediate",
                    "style": {"font_size": 14},
                },
                {"x": -130, "y": 120, "text": "0.0", "style": {"font_size": 9}},
                {"x": 900, "y": 420, "text": "-12.5", "style": {"font_size": 9}},
            ],
            "arrows": [
                {
                    "kind": "arrow",
                    "start": [90, 50],
                    "end": [130, 50],
                    "labels": {"above": "test"},
                    "color": "#123456",
                }
            ],
            "ts_brackets": [
                {
                    "bracket_kind": "square_pair",
                    "left": 480,
                    "top": 180,
                    "right": 560,
                    "bottom": 265,
                }
            ],
        }
    )


def _files(tmp_path: Path) -> tuple[Path, Path, Path]:
    source, layout, output = (
        tmp_path / name
        for name in ("source.chemvas", "layout.json", "arranged.chemvas")
    )
    source.write_text(
        json_text(build_document_payload(_source_state(), CANVAS_FILE_VERSION)),
        encoding="utf-8",
    )
    request = {
        "format": "chemvas-scheme-layout",
        "version": 1,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "gap": 12,
        "caption_gap": 8,
        "line_gap": 4,
        "rows": [
            {
                "blocks": [
                    {"atoms": [0, 1, 2, 3], "captions": [0, 2], "anchor_atom": 0},
                    {
                        "atoms": [4, 5, 6],
                        "captions": [1, 3],
                        "anchor_atom": 4,
                        "items": [["ts_brackets", 0]],
                    },
                ],
                "arrows": [0],
            }
        ],
    }
    layout.write_text(json.dumps(request), encoding="utf-8")
    return source, layout, output


def _run(source: Path, layout: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "chemvas",
            "layout-document",
            str(source),
            "--layout",
            str(layout),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHONPATH": os.path.abspath("app")},
    )


def _baseline(item) -> float:
    from PyQt6.QtCore import QPointF

    item.boundingRect()
    layout = item.document().firstBlock().layout()
    line = layout.lineAt(0)
    return item.mapToScene(
        QPointF(0, layout.position().y() + line.y() + line.ascent())
    ).y()


def _align_files(tmp_path):
    source, layout, output = _files(tmp_path)
    request = json.loads(layout.read_text())
    for key in ("gap", "caption_gap", "line_gap"):
        request.pop(key)
    request["mode"] = "align-y"
    request["rows"][0]["reference_blocks"] = [1]
    for block in request["rows"][0]["blocks"]:
        block.pop("anchor_atom")
    request["rows"][0]["blocks"][0]["parts"] = [[0, 1, 2], [3]]
    layout.write_text(json.dumps(request), encoding="utf-8")
    return source, layout, output


def test_align_y_cli_preserves_source_notes_and_x_and_moves_explicit_parts(
    tmp_path,
) -> None:
    source, layout, output = _align_files(tmp_path)
    before_bytes = source.read_bytes()
    original = read_document(source).state
    result = _run(source, layout, output)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["mode"] == "align-y"
    assert report["part_count"] == 3
    assert report["rows"][0]["reference_blocks"] == [1]
    assert report["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert source.read_bytes() == before_bytes
    candidate = read_document(output).state
    assert candidate["notes"] == original["notes"]
    assert candidate["arrows"] == original["arrows"]
    assert candidate.get("groups") == original.get("groups")
    assert candidate["model"]["bonds"] == original["model"]["bonds"]
    for placement in report["placements"]:
        assert placement["dx"] == 0
        for atom in placement["atoms"]:
            before, after = (
                original["model"]["atoms"][str(atom)],
                candidate["model"]["atoms"][str(atom)],
            )
            assert {k: v for k, v in before.items() if k != "y"} == {
                k: v for k, v in after.items() if k != "y"
            }
            assert after["y"] - before["y"] == pytest.approx(placement["dy"])
    assert report["placements"][0]["dy"] != pytest.approx(report["placements"][1]["dy"])


def test_align_y_cli_partition_failure_publishes_nothing(tmp_path) -> None:
    source, layout, output = _align_files(tmp_path)
    original_bytes = source.read_bytes()
    request = json.loads(layout.read_text())
    request["rows"][0]["blocks"][0]["parts"] = [[0], [1, 2], [3]]
    layout.write_text(json.dumps(request), encoding="utf-8")
    result = _run(source, layout, output)
    assert result.returncode == 2
    assert "must not cut bonds" in result.stderr
    assert not output.exists()
    assert source.read_bytes() == original_bytes


def test_layout_cli_centers_captions_and_preserves_geometry_and_source(
    tmp_path: Path,
) -> None:
    source, layout, output = _files(tmp_path)
    original_bytes = source.read_bytes()
    original = read_document(source).state
    result = _run(source, layout, output)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["format"] == "chemvas-scheme-layout-report"
    assert report["block_count"] == 2
    assert report["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert source.read_bytes() == original_bytes
    arranged = read_document(output).state
    assert arranged["model"]["bonds"] == original["model"]["bonds"]
    assert (
        arranged["model"]["atom_annotations"] == original["model"]["atom_annotations"]
    )
    assert arranged["settings"] == original["settings"]
    assert len(arranged["groups"]) == 2
    assert arranged["groups"][0]["atoms"] == [0, 1, 2, 3]
    for before, after in zip(original["notes"], arranged["notes"], strict=True):
        assert {k: v for k, v in before.items() if k not in {"x", "y"}} == {
            k: v for k, v in after.items() if k not in {"x", "y"}
        }
    for ids in ((0, 1, 2, 3), (4, 5, 6)):
        for axis in ("x", "y"):
            deltas = [
                arranged["model"]["atoms"][str(a)][axis]
                - original["model"]["atoms"][str(a)][axis]
                for a in ids
            ]
            assert deltas == pytest.approx([deltas[0]] * len(ids))
    assert arranged["model"]["atoms"]["0"]["y"] == pytest.approx(
        arranged["model"]["atoms"]["4"]["y"]
    )
    assert arranged["arrows"][0]["end"][0] - arranged["arrows"][0]["start"][
        0
    ] == pytest.approx(40)
    for key in ("labels", "color"):
        assert arranged["arrows"][0][key] == original["arrows"][0][key]
    with offscreen_canvas(arranged, command="test-layout-reopen") as (canvas, _):
        from chemvas.ui.canvas_document_state import document_item_lists_for
        from chemvas.ui.canvas_group_state import group_state_for
        from chemvas.ui.layout_qa_service import note_paint_scene_path

        notes = document_item_lists_for(canvas)["notes"]
        assert len(group_state_for(canvas).groups) == 2
        for left, right in ((0, 1), (2, 3)):
            assert _baseline(notes[left]) == pytest.approx(_baseline(notes[right]))
        for index, column in ((0, 0), (2, 0), (1, 1), (3, 1)):
            assert note_paint_scene_path(
                notes[index]
            ).boundingRect().center().x() == pytest.approx(
                report["placements"][column]["center_x"]
            )


@pytest.mark.parametrize(
    "failure", ["stale", "duplicate", "partial", "overwrite", "json"]
)
def test_layout_cli_failures_preserve_inputs_and_write_nothing(
    tmp_path: Path, failure: str
) -> None:
    source, layout, output = _files(tmp_path)
    request = json.loads(layout.read_text())
    if failure == "stale":
        request["source_sha256"] = "0" * 64
    elif failure == "duplicate":
        request["rows"][0]["blocks"][1]["captions"].append(0)
    elif failure == "partial":
        request["rows"][0]["blocks"][0]["atoms"].remove(1)
    layout.write_text(json.dumps(request))
    if failure == "json":
        layout.write_text('{"format":1,"format":2}')
    if failure == "overwrite":
        output.write_bytes(b"keep this output")
    before = source.read_bytes(), layout.read_bytes()
    result = _run(source, layout, output)
    assert result.returncode == 2
    assert "chemvas: error:" in result.stderr
    assert result.stdout == ""
    assert (source.read_bytes(), layout.read_bytes()) == before
    if failure == "overwrite":
        assert output.read_bytes() == b"keep this output"
    else:
        assert not output.exists()


def test_layout_rejects_invalid_input_before_opening_qt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, layout, output = _files(tmp_path)
    request = json.loads(layout.read_text())
    request["source_sha256"] = "f" * 64
    layout.write_text(json.dumps(request))

    def unexpected(*args, **kwargs):
        pytest.fail("invalid input must not open a canvas")

    monkeypatch.setattr(document_layout, "offscreen_canvas", unexpected)
    with pytest.raises(SystemExit) as exc:
        document_layout.run(
            [
                "layout-document",
                str(source),
                "--layout",
                str(layout),
                "--output",
                str(output),
            ]
        )
    assert exc.value.code == 2
    assert not output.exists()


def test_comparison_caption_and_color_cli_options_preserve_source_and_graph(
    tmp_path: Path,
) -> None:
    source, layout, output = _files(tmp_path)
    request = json.loads(layout.read_text())
    request["rows"][0]["column_group"] = "controls"
    request.update(caption_alignment="structure", arrow_color="#000")
    layout.write_text(json.dumps(request))
    before = source.read_bytes(), layout.read_bytes()
    original = read_document(source).state

    result = _run(source, layout, output)

    assert result.returncode == 0, result.stderr
    assert (source.read_bytes(), layout.read_bytes()) == before
    report = json.loads(result.stdout)
    assert report["column_groups"] == ["controls"]
    assert report["caption_alignment"] == "structure"
    assert {item["note"] for item in report["caption_placements"]} == {0, 1, 2, 3}
    assert report["arrow_color_changes"] == [
        {"arrow": 0, "before": "#123456", "after": "#000"}
    ]
    candidate = read_document(output).state
    assert candidate["model"]["bonds"] == original["model"]["bonds"]
    assert (
        candidate["model"]["atom_annotations"] == original["model"]["atom_annotations"]
    )
    assert candidate["settings"] == original["settings"]
    assert candidate["arrows"][0]["color"] == "#000"
    assert candidate["arrows"][0]["labels"] == original["arrows"][0]["labels"]
    for prior, after in zip(original["notes"], candidate["notes"], strict=True):
        assert {k: v for k, v in prior.items() if k not in {"x", "y"}} == {
            k: v for k, v in after.items() if k not in {"x", "y"}
        }


def test_explicit_default_caption_policy_produces_identical_document_bytes(
    tmp_path: Path,
) -> None:
    source, layout, output = _files(tmp_path)
    assert _run(source, layout, output).returncode == 0
    request = json.loads(layout.read_text())
    request["caption_alignment"] = "row"
    layout.write_text(json.dumps(request))
    second = tmp_path / "explicit-default.chemvas"
    result = _run(source, layout, second)
    assert result.returncode == 0, result.stderr
    assert second.read_bytes() == output.read_bytes()


@pytest.mark.parametrize(
    "field,value",
    [("caption_alignment", "auto"), ("arrow_color", "black"), ("column_group", "")],
)
def test_invalid_semantic_options_fail_before_qt_and_publish_nothing(
    tmp_path: Path, monkeypatch, field, value
) -> None:
    source, layout, output = _files(tmp_path)
    request = json.loads(layout.read_text())
    target = request["rows"][0] if field == "column_group" else request
    target[field] = value
    layout.write_text(json.dumps(request))
    before = source.read_bytes(), layout.read_bytes()

    def unexpected(*_args, **_kwargs):
        pytest.fail("invalid arrangement policy must not open a canvas")

    monkeypatch.setattr(document_layout, "offscreen_canvas", unexpected)
    with pytest.raises(SystemExit) as exc:
        document_layout.run(
            [
                "layout-document",
                str(source),
                "--layout",
                str(layout),
                "--output",
                str(output),
            ]
        )
    assert exc.value.code == 2
    assert not output.exists()
    assert (source.read_bytes(), layout.read_bytes()) == before


def test_width_limited_cli_wraps_without_losing_the_connecting_arrow(
    tmp_path: Path,
) -> None:
    source, layout, baseline = _files(tmp_path)
    before = source.read_bytes()
    initial = _run(source, layout, baseline)
    assert initial.returncode == 0, initial.stderr
    request = json.loads(layout.read_text())
    request["max_row_width"] = json.loads(initial.stdout)["layout_width"] - 1
    layout.write_text(json.dumps(request))
    output = tmp_path / "wrapped.chemvas"

    result = _run(source, layout, output)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["row_count"] == 2
    assert report["block_count"] == 2
    assert report["layout_width"] <= request["max_row_width"]
    original = read_document(source).state
    arranged = read_document(output).state
    assert source.read_bytes() == before
    assert arranged["model"]["bonds"] == original["model"]["bonds"]
    assert len(arranged["arrows"]) == len(original["arrows"]) == 1
    arrow = arranged["arrows"][0]
    assert arrow["end"][0] - arrow["start"][0] == pytest.approx(40)
    assert arrow["start"][1] == pytest.approx(arrow["end"][1])
    assert arrow["start"][1] == pytest.approx(arranged["model"]["atoms"]["4"]["y"])
    assert arrow["end"][0] < arranged["model"]["atoms"]["4"]["x"]
    assert arranged["model"]["atoms"]["4"]["y"] > arranged["model"]["atoms"]["0"]["y"]
    for key in ("labels", "color", "kind"):
        assert arrow[key] == original["arrows"][0][key]
    assert len(arranged["groups"]) == 2


@pytest.mark.parametrize("width", [0, -1, True, "200", 100001, 1])
def test_invalid_or_impossible_row_width_publishes_nothing(
    tmp_path: Path, width: object
) -> None:
    source, layout, output = _files(tmp_path)
    request = json.loads(layout.read_text())
    request["max_row_width"] = width
    layout.write_text(json.dumps(request))
    before = source.read_bytes(), layout.read_bytes()

    result = _run(source, layout, output)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "chemvas: error:" in result.stderr
    assert not output.exists()
    assert (source.read_bytes(), layout.read_bytes()) == before


def test_layout_cli_accepts_fractional_distances_without_relaxing_integer_ids(
    tmp_path: Path,
) -> None:
    source, layout, output = _files(tmp_path)
    request = json.loads(layout.read_text())
    request.update(
        gap=12.25,
        row_gap=18.5,
        caption_gap=8.125,
        line_gap=4.75,
        max_row_width=220.25,
    )
    layout.write_text(json.dumps(request))
    result = _run(source, layout, output)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["layout_width"] <= 220.25

    request["rows"][0]["blocks"][0]["atoms"][0] = 0.0
    layout.write_text(json.dumps(request))
    refused = tmp_path / "fractional-id.chemvas"
    result = _run(source, layout, refused)
    assert result.returncode == 2
    assert not refused.exists()
