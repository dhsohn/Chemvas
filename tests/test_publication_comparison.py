from __future__ import annotations

import hashlib
import json
import math
import os
import runpy
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "examples" / "publication_comparison.py"


@pytest.fixture(autouse=True)
def _pin_recipe_child_source(monkeypatch):
    # runpy uses pytest's import path, but recipe subprocesses do not inherit it.
    monkeypatch.setenv("PYTHONPATH", str(ROOT / "app"))


@pytest.fixture(scope="module")
def comparison(tmp_path_factory):
    output = tmp_path_factory.mktemp("publication-comparison") / "new"
    result = subprocess.run(
        [sys.executable, str(RECIPE), "--output-dir", str(output)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env={
            **os.environ,
            "PYTHONPATH": str(ROOT / "app"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "QT_QPA_PLATFORM": "offscreen",
        },
    )
    assert result.returncode == 0, result.stderr
    return output, json.loads(result.stdout)


def read_state(directory, name):
    return json.loads((directory / name).read_text())["state"]


def test_comparison_has_two_complete_explicit_symbolic_rows(comparison):
    directory, manifest = comparison
    state = read_state(directory, manifest["document"])
    atoms = state["model"]["atoms"]
    assert manifest["synthetic_example_only"] is True
    assert len(atoms) == 16
    assert len(state["model"]["bonds"]) == 8
    assert len(state["arrows"]) == 2
    assert len(state["notes"]) == 8
    for start in (0, 4, 8, 12):
        assert Counter(atoms[str(i)]["element"] for i in range(start, start + 4)) == {
            "R1": 1,
            "R2": 1,
            "R3": 1,
            "R4": 1,
        }
    expected = (
        ("R1", "R2"),
        ("R3", "R4"),
        ("R1", "R3"),
        ("R2", "R4"),
        ("R1", "R2"),
        ("R3", "R4"),
        ("R1", "R4"),
        ("R2", "R3"),
    )
    assert (
        tuple(
            (atoms[str(b["a"])]["element"], atoms[str(b["b"])]["element"])
            for b in state["model"]["bonds"]
        )
        == expected
    )
    assert [note["text"] for note in state["notes"]] == [
        "+",
        "Input1",
        "+",
        "Output1",
        "+",
        "Input2",
        "+",
        "Output2",
    ]
    for index, arrow in enumerate(state["arrows"]):
        assert arrow["kind"] == "arrow"
        assert arrow["color"] == "#000000"
        assert arrow["labels"] == {
            "above": f"case {index + 1}",
            "below": "symbolic only",
        }
        assert arrow["start"][1] == arrow["end"][1]
        assert arrow["start"][0] < arrow["end"][0]


def test_comparison_layout_preserves_graph_and_native_typography(comparison):
    directory, manifest = comparison
    before = read_state(directory, "comparison-source.chemvas")
    after = read_state(directory, manifest["document"])
    assert before["model"]["bonds"] == after["model"]["bonds"]
    assert before["settings"] == after["settings"]
    assert len(after["groups"]) == 4
    for group in after["groups"]:
        first = str(group["atoms"][0])
        delta = {
            key: after["model"]["atoms"][first][key]
            - before["model"]["atoms"][first][key]
            for key in ("x", "y")
        }
        for atom_id in group["atoms"]:
            a, b = (s["model"]["atoms"][str(atom_id)] for s in (before, after))
            assert {k: v for k, v in a.items() if k not in ("x", "y")} == {
                k: v for k, v in b.items() if k not in ("x", "y")
            }
            for key in ("x", "y"):
                assert b[key] - a[key] == pytest.approx(delta[key])
        plus_index = group["items"][0][1]
        for key in ("x", "y"):
            assert after["notes"][plus_index][key] - before["notes"][plus_index][
                key
            ] == pytest.approx(delta[key])
    for index, (a, b) in enumerate(zip(before["notes"], after["notes"], strict=True)):
        assert a["text"] == b["text"]
        assert a["html"] == b["html"]
        if index % 2:
            assert "vertical-align:sub" in b["html"].replace(" ", "")
    for a, b in zip(before["arrows"], after["arrows"], strict=True):
        assert a["labels"] == b["labels"]
        assert a["color"] == b["color"]
        for axis in (0, 1):
            assert a["end"][axis] - a["start"][axis] == pytest.approx(
                b["end"][axis] - b["start"][axis]
            )


def test_comparison_ownership_columns_and_captions_are_explicit(comparison):
    directory, _ = comparison
    request = json.loads((directory / "comparison-layout.json").read_text())
    report = json.loads((directory / "comparison-layout-report.json").read_text())
    assert (
        request["source_sha256"]
        == hashlib.sha256(
            (directory / "comparison-source.chemvas").read_bytes()
        ).hexdigest()
    )
    assert request["caption_alignment"] == "structure"
    assert request["arrow_color"] == "#000000"
    assert "max_row_width" not in request
    assert report["row_count"] == 2 and report["block_count"] == 4
    assert report["column_groups"] == ["comparison", "comparison"]
    placements = report["placements"]
    assert placements[0]["center_x"] == placements[2]["center_x"]
    assert placements[1]["center_x"] == placements[3]["center_x"]
    for caption, block in zip(report["caption_placements"], placements, strict=True):
        assert caption["center_x"] == block["center_x"]
    state = read_state(directory, "comparison.chemvas")
    for index, group in enumerate(state["groups"]):
        assert group == {
            "atoms": list(range(index * 4, index * 4 + 4)),
            "items": [["notes", index * 2], ["notes", index * 2 + 1]],
        }


def test_comparison_is_readable_at_one_common_physical_scale(comparison):
    directory, manifest = comparison
    state = read_state(directory, manifest["document"])
    assert (
        manifest["source_sha256"]
        == hashlib.sha256((directory / manifest["document"]).read_bytes()).hexdigest()
    )
    assert manifest["embed_width_mm"] <= 85
    for bond in state["model"]["bonds"]:
        a, b = (state["model"]["atoms"][str(bond[k])] for k in ("a", "b"))
        assert math.hypot(a["x"] - b["x"], a["y"] - b["y"]) == pytest.approx(
            manifest["bond_units"]
        )
    for report in manifest["exports"].values():
        font = report["font_readability"]
        assert font["status"] == "passed" and font["minimum_font_pt"] >= 6
        assert report["width_points"] * 25.4 / 72 <= 85
        assert report["height_points"] * 25.4 / 72 <= 100
        assert font["coverage"]["note_script"]["runs"] > 0
        assert font["scene_to_output_pt"] * manifest[
            "bond_units"
        ] * 25.4 / 72 == pytest.approx(5, abs=0.04)
        assert Path(report["output"]).is_file()
    check = json.loads((directory / "comparison-check.json").read_text())
    assert check["ok"] and check["warning_count"] == 0
    receipt = manifest["layout_check"]
    assert receipt["report"] == "comparison-check.json"
    assert (
        receipt["sha256"]
        == hashlib.sha256((directory / receipt["report"]).read_bytes()).hexdigest()
    )
    assert check["source_sha256"] == manifest["source_sha256"]
    assert all(
        report["source_sha256"] == manifest["source_sha256"]
        for report in manifest["exports"].values()
    )
    inventory = json.loads((directory / "comparison-graph.json").read_text())
    assert inventory["atom_count"] == 16 and inventory["bond_count"] == 8


def test_comparison_fits_native_sheet(comparison):
    from PyQt6.QtWidgets import QApplication

    from chemvas.bootstrap.document_cli_shared import offscreen_canvas
    from chemvas.core.document_io import read_document
    from chemvas.features.export import collect_export_items, content_bounds
    from chemvas.ui.sheet_setup_access import sheet_rect_for

    application = QApplication.instance() or QApplication([])
    directory, manifest = comparison
    with offscreen_canvas(
        read_document(directory / manifest["document"]).state,
        command="comparison-sheet-test",
    ) as (canvas, _):
        application.processEvents()
        bounds = content_bounds(collect_export_items(canvas.scene()))
        assert bounds is not None
        assert sheet_rect_for(canvas).contains(bounds)


def test_comparison_refuses_existing_directory_without_changes(comparison):
    directory, _ = comparison
    before = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()
    }
    result = subprocess.run(
        [sys.executable, str(RECIPE), "--output-dir", str(directory)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 2 and "File exists" in result.stderr
    assert before == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()
    }


def test_comparison_rejects_outside_molecules_before_export(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "examples"))
    namespace = runpy.run_path(str(RECIPE))
    real_command = namespace["command"]
    called = []

    def displaced(*args):
        called.append(args[0])
        report = real_command(*args)
        if args[0] == "layout-document":
            path = Path(args[-1])
            native = json.loads(path.read_text())
            for atom in native["state"]["model"]["atoms"].values():
                atom["x"] += 1000
            path.write_text(json.dumps(native))
        return report

    monkeypatch.setitem(namespace["build"].__globals__, "command", displaced)
    directory = tmp_path / "new"
    with pytest.raises(RuntimeError, match="outside-sheet"):
        namespace["build"](directory)
    assert "render-document" not in called
    assert not (directory / "manifest.json").exists()


def test_comparison_stops_on_stale_native_source_report(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "examples"))
    import publication_scheme

    real_command = publication_scheme.command

    def stale(*args):
        report = real_command(*args)
        if args[0] == "check-layout":
            return {**report, "source_sha256": "0" * 64}
        return report

    monkeypatch.setattr(publication_scheme, "command", stale)
    namespace = runpy.run_path(str(RECIPE))
    directory = tmp_path / "new"
    with pytest.raises(ValueError, match="source SHA-256"):
        namespace["build"](directory)
    assert not (directory / "comparison-probe.svg").exists()
    assert not (directory / "manifest.json").exists()
