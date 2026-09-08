from __future__ import annotations

import hashlib
import json
import math
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "examples" / "publication_scheme.py"


@pytest.fixture(scope="module")
def publication(tmp_path_factory):
    output = tmp_path_factory.mktemp("publication") / "new"
    result = subprocess.run(
        [sys.executable, str(RECIPE), "--output-dir", str(output)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env={**os.environ, "PYTHONPATH": str(ROOT / "app")},
    )
    assert result.returncode == 0, result.stderr
    return output, json.loads(result.stdout)


def test_publication_recipe_preserves_common_physical_scale_and_real_scripts(
    publication,
):
    directory, manifest = publication
    assert manifest["synthetic_example_only"] is True
    widths = []
    for figure in manifest["figures"]:
        widths.append(figure["embed_width_mm"])
        path = directory / figure["document"]
        assert figure["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        state = json.loads(path.read_text())["state"]
        assert len(state["notes"]) == 2  # captions only, no duplicate heading
        for note in state["notes"]:
            assert "vertical-align:sub" in note["html"].replace(" ", "")
            assert "vertical-align:super" in note["html"].replace(" ", "")
            assert "_" not in note["text"]
        for report in figure["exports"].values():
            font = report["font_readability"]
            assert font["status"] == "passed"
            assert font["minimum_font_pt"] >= 6
            assert font["coverage"]["atom"]["minimum_pt"] == pytest.approx(
                8.15, abs=0.08
            )
            assert font["coverage"]["note"]["minimum_pt"] == pytest.approx(
                8.15, abs=0.08
            )
            assert font["coverage"]["note_script"]["minimum_pt"] < 7
            bond_mm = font["scene_to_output_pt"] * manifest["bond_units"] * 25.4 / 72
            assert bond_mm == pytest.approx(5, abs=0.04)
            assert report["height_points"] * 25.4 / 72 < 105
            assert Path(report["output"]).is_file()
    assert widths[1] > widths[0]  # longer figure, never per-figure fit-to-width


def test_publication_template_and_terminal_angle_are_native_and_regular(publication):
    directory, _ = publication
    state = json.loads((directory / "methoxy.chemvas").read_text())["state"]
    atoms = state["model"]["atoms"]
    assert len(state["ring_fills"]) == 1
    ring = state["ring_fills"][0]
    assert len(set(ring["atom_ids"])) == 6
    assert ring["alpha"] == 0
    for bond in state["model"]["bonds"]:
        a, b = atoms[str(bond["a"])], atoms[str(bond["b"])]
        assert math.hypot(a["x"] - b["x"], a["y"] - b["y"]) == pytest.approx(40)
    pivot, terminal = atoms["6"], atoms["7"]
    ring_neighbor = next(b for b in state["model"]["bonds"] if b["b"] == 6)
    reference = atoms[str(ring_neighbor["a"])]

    def direction(atom):
        return math.atan2(atom["y"] - pivot["y"], atom["x"] - pivot["x"])

    angle = math.degrees(direction(terminal) - direction(reference))
    assert (angle + 180) % 360 - 180 == pytest.approx(120)


def test_publication_alignment_does_not_move_captions_or_x(publication):
    directory, manifest = publication
    for figure in manifest["figures"]:
        name = Path(figure["document"]).stem
        before = json.loads((directory / f"{name}-arranged.chemvas").read_text())[
            "state"
        ]
        after = json.loads((directory / figure["document"]).read_text())["state"]
        assert before["notes"] == after["notes"]
        assert before["groups"] == after["groups"]
        assert before["model"]["bonds"] == after["model"]["bonds"]
        for atom_id, atom in before["model"]["atoms"].items():
            assert atom["x"] == after["model"]["atoms"][atom_id]["x"]
        report = json.loads((directory / f"{name}-alignment-report.json").read_text())
        assert report["mode"] == "align-y"
        assert report["part_count"] == (3 if name == "independent-parts" else 2)


def test_publication_recipe_refuses_existing_directory_without_changes(publication):
    directory, _ = publication
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
    assert result.returncode == 2
    assert "File exists" in result.stderr
    assert before == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()
    }


def test_publication_recipe_stops_on_layout_warning(monkeypatch):
    namespace = runpy.run_path(str(RECIPE))

    def warned(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, '{"ok": false}', "")

    monkeypatch.setattr(subprocess, "run", warned)
    with pytest.raises(RuntimeError, match="check-layout"):
        namespace["command"]("check-layout", "synthetic.chemvas")


def test_publication_examples_fit_native_sheet_without_scaling(publication):
    from PyQt6.QtWidgets import QApplication

    from chemvas.bootstrap.document_cli_shared import offscreen_canvas
    from chemvas.core.document_io import read_document
    from chemvas.features.export import collect_export_items, content_bounds
    from chemvas.ui.sheet_setup_access import sheet_rect_for

    application = QApplication.instance() or QApplication([])
    directory, manifest = publication
    for figure in manifest["figures"]:
        state = read_document(directory / figure["document"]).state
        with offscreen_canvas(state, command="publication-sheet-test") as (canvas, _):
            application.processEvents()
            bounds = content_bounds(collect_export_items(canvas.scene()))
            assert bounds is not None
            assert sheet_rect_for(canvas).contains(bounds)
