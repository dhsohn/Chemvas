"""Calculation operations are optional to the document lifecycle, not its data."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_LIFECYCLE = r"""
import hashlib
import importlib.abc
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
root.mkdir()
blocked = sys.argv[2] == "blocked"
operations = (
    "chemvas.features.calculation_bundle",
    "chemvas.bootstrap.calculation_bundle",
    "chemvas.ui.calculation_step_dialog",
    "chemvas.ui.calculation_mapping_highlight",
)
attempts = []
class WithoutCalculation(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + ".") for name in operations):
            attempts.append(fullname)
            raise AssertionError("Calculation operation imported by core: " + fullname)
if blocked:
    sys.meta_path.insert(0, WithoutCalculation())

from PyQt6.QtWidgets import QApplication
from chemvas.ui import app_data_paths
app_data_paths._candidate_dirs = lambda: [root / "app-data"]
from chemvas.bootstrap.main_window import build_main_window
from chemvas.bootstrap import document_render
from chemvas.core.document_io import read_exact_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.ui.main_window_ports import active_canvas_for_window
from chemvas.ui.canvas_service_access import canvas_services_for
from tests.calculation_plan_support import _document_state, _plan
app = QApplication([])
window = build_main_window()
canvas = active_canvas_for_window(window)
services = canvas_services_for(canvas)
session = services.document.canvas_document_session_service
state = _document_state()
state["calculation_plan"] = _plan(complete_mapping=False)
write_document(root / "input.chemvas", state, CANVAS_FILE_VERSION)
_, opened = read_exact_document(root / "input.chemvas")
session.apply_state(opened.state)
services.interaction.move_controller.move_atoms({0, 1}, 20, 10)
snapshot = session.snapshot_state()
assert snapshot["calculation_plan"] == state["calculation_plan"]
assert canvas.model.atoms[0].x == 20
write_document(root / "output.chemvas", snapshot, CANVAS_FILE_VERSION)
_, reopened = read_exact_document(root / "output.chemvas")
assert reopened.state["calculation_plan"] == state["calculation_plan"]
result = document_render._render_offscreen(
    reopened.state, output_format="png", background="white", dpi=150,
    width_mm=None, max_height_mm=None, min_font_pt=None,
)
assert result.content.startswith(b"\x89PNG")
assert not attempts
print(json.dumps({
    "document": hashlib.sha256((root / "output.chemvas").read_bytes()).hexdigest(),
    "png": hashlib.sha256(result.content).hexdigest(),
}))
window.deleteLater()
"""


def test_drawing_lifecycle_preserves_plan_without_calculation_operations(tmp_path):
    outputs = []
    for name, mode in (
        ("baseline1", "normal"),
        ("baseline2", "normal"),
        ("isolated", "blocked"),
    ):
        result = subprocess.run(
            [sys.executable, "-c", _LIFECYCLE, str(tmp_path / name), mode],
            cwd=ROOT,
            env={
                **os.environ,
                "PYTHONPATH": str(ROOT / "app"),
                "QT_QPA_PLATFORM": "offscreen",
            },
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        outputs.append(json.loads(result.stdout.strip().splitlines()[-1]))
    # Two normal runs establish repeatability before the unavailable-feature
    # run is compared: both saved document bytes and rendered pixels agree.
    assert outputs[0] == outputs[1] == outputs[2]


@pytest.mark.usefixtures("qt_application")
def test_calculation_menu_still_dispatches_to_its_editor(monkeypatch):
    from PyQt6.QtWidgets import QMainWindow

    from chemvas.ui import calculation_step_dialog, main_window_menu_bar

    window = QMainWindow()
    calls = []
    monkeypatch.setattr(
        calculation_step_dialog, "edit_calculation_plan_for_window", calls.append
    )
    main_window_menu_bar._build_calculation_menu(window.menuBar(), window)
    window.menuBar().actions()[0].menu().actions()[0].trigger()
    assert calls == [window]
    window.deleteLater()
