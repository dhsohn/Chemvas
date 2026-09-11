"""The same drawing uses the same scene typography on 72/96-DPI screens."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_scene_fonts_and_glyph_paths_do_not_depend_on_screen_logical_dpi():
    code = """
import json
from chemvas.features.document_composition import compose_document_state
from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.ui.canvas_document_state import document_item_lists_for
from chemvas.ui.canvas_atom_graphics_state import atom_items_for
s = compose_document_state({
    "format": "chemvas-document-composition", "version": 1,
    "atoms": [{"id": 0, "element": "NH2", "x": 0, "y": 0},
              {"id": 1, "element": "C", "x": 20, "y": 0}],
    "bonds": [{"a": 0, "b": 1, "order": 1}],
    "notes": [{"text": "12 pt note", "x": 40, "y": 40, "style": {"font_size": 12}}],
    "arrows": [{"kind": "arrow", "start": [0, 100], "end": [60, 100], "labels": {"above": "k_1"}}],
})
def rect(r):
    return [r.x(), r.y(), r.width(), r.height()]
with offscreen_canvas(s, command="dpi-regression") as (canvas, service):
    items = document_item_lists_for(canvas)
    atom = atom_items_for(canvas)[0]
    print(json.dumps({
        "note": rect(items["notes"][0].boundingRect()),
        "arrow_label": [rect(i.boundingRect()) for i in items["arrows"][0].childItems()],
        "atom": rect(atom.boundingRect()), "atom_ink": rect(atom.glyph_path().boundingRect()),
        "snapshot": service.snapshot_state(),
    }))
"""
    results = []
    for dpi in (72, 96):
        env = dict(
            os.environ,
            QT_QPA_PLATFORM="offscreen",
            QT_FONT_DPI=str(dpi),
            PYTHONPATH=str(Path(__file__).resolve().parents[1] / "app"),
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        results.append(json.loads(result.stdout))
    assert results[0] == results[1]


@pytest.mark.parametrize("output_format", ["png", "svg"])
def test_public_render_bytes_and_readability_are_dpi_independent(
    tmp_path, output_format
):
    from chemvas.domain.document import build_document_payload
    from chemvas.features.document_composition import compose_document_state

    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {"id": 0, "element": "N", "x": 0, "y": 0},
                {"id": 1, "element": "C", "x": 20, "y": 0},
            ],
            "bonds": [{"a": 0, "b": 1, "order": 1}],
            "notes": [
                {"text": "A 12 pt note", "x": 0, "y": 25, "style": {"font_size": 12}}
            ],
            "arrows": [
                {
                    "kind": "arrow",
                    "start": [0, 70],
                    "end": [60, 70],
                    "labels": {"above": "k_1"},
                }
            ],
        }
    )
    source = tmp_path / "source.chemvas"
    source.write_text(json.dumps(build_document_payload(state, 7)), encoding="utf-8")
    results = []
    for dpi in (72, 96, 144):
        output = tmp_path / f"dpi-{dpi}.{output_format}"
        env = dict(
            os.environ,
            QT_QPA_PLATFORM="offscreen",
            QT_FONT_DPI=str(dpi),
            PYTHONPATH=str(Path(__file__).resolve().parents[1] / "app"),
        )
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from chemvas.bootstrap.application import main; main()",
                "render-document",
                str(source),
                "--output",
                str(output),
                "--min-font-pt",
                "0.1",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        report.pop("output")
        results.append((output.read_bytes(), report))
    assert results[0] == results[1] == results[2]
