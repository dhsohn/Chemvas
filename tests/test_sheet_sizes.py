"""Paper size contracts across authoring, scene state, history and files."""

import gc
import json
import weakref
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication, QComboBox, QDialog, QDoubleSpinBox

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION, build_document_payload
from chemvas.domain.document.sheet import POINTS_PER_MM, SHEET_SIZES_MM
from chemvas.features.document_composition import compose_document_state
from chemvas.ui.canvas.sheet_setup_access import sheet_rect_for
from chemvas.ui.canvas.sheet_setup_logic import sheet_dimensions_px
from chemvas.ui.canvas.sheet_setup_service import change_sheet_setup_for
from chemvas.ui.window.main_window_document_dialogs import prompt_sheet_setup
from tests.canvas_factory import build_canvas_view

pytestmark = pytest.mark.usefixtures("qt_application")

# Weak references only: the guard observes this file's application, never owns it.
_applications = []


def state_with_sheet(size, custom=None):
    settings = {"sheet_size": size, "sheet_orientation": "portrait"}
    if custom is not None:
        settings["sheet_custom_size_mm"] = custom
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 2,
            "atoms": [{"id": 0, "element": "C", "x": 700, "y": 0}],
            "bonds": [],
            "settings": settings,
        }
    )


@contextmanager
def borrowed_canvas(state, *, command):
    """Open a headless canvas that borrows an application something else owns.

    If each case created its own application, objects left by one case's canvas
    could be destroyed while the next case's application is running.
    """
    existing = QApplication.instance()
    assert existing is not None, "no application owns this file's canvases"
    application = weakref.ref(existing)
    del existing
    assert all(reference() is application() for reference in _applications)
    _applications.append(application)
    with offscreen_canvas(state, command=command) as (canvas, service):
        assert QApplication.instance() is application()
        yield canvas, service
    assert sip.isdeleted(canvas)
    gc.collect()
    assert application() is not None and not sip.isdeleted(application())
    assert QApplication.instance() is application()


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("size", SHEET_SIZES_MM)
def test_standard_sizes_reach_scene_and_file(size, tmp_path):
    state = state_with_sheet(size)
    path = tmp_path / "paper.chemvas"
    write_document(path, state, CANVAS_FILE_VERSION)
    restored = read_document(path)
    assert restored.state == json.loads(json.dumps(state))
    assert restored.payload["version"] == 9
    expected = sheet_dimensions_px(size, "portrait")
    with borrowed_canvas(restored.state, command="test-sheet") as (canvas, _):
        rect = sheet_rect_for(canvas)
        assert (rect.width(), rect.height()) == expected
        assert canvas.model.atoms[0].x == 700
    assert sheet_dimensions_px(size, "landscape") == expected[::-1]


@pytest.mark.parametrize("dimensions", [[600, 400], [10, 2000], [333.33, 222.22]])
def test_custom_dimensions_roundtrip_and_headless_scene(dimensions, tmp_path):
    state = state_with_sheet("Custom", dimensions)
    path = tmp_path / "custom.chemvas"
    write_document(path, state, CANVAS_FILE_VERSION)
    restored = read_document(path)
    assert restored.state == json.loads(json.dumps(state))
    with borrowed_canvas(restored.state, command="test-custom") as (canvas, _):
        rect = sheet_rect_for(canvas)
        assert (rect.width(), rect.height()) == pytest.approx(
            tuple(d * POINTS_PER_MM for d in dimensions)
        )
        assert canvas.model.atoms[0].x == 700


@pytest.mark.parametrize(
    "dimensions",
    [
        None,
        [],
        [0, 100],
        [2001, 100],
        [True, 100],
        [float("nan"), 100],
        [float("inf"), 100],
        [Decimal("NaN"), 100],
        [10**1000, 100],
        ["200", 100],
        [200, 100, 50],
    ],
)
def test_invalid_custom_dimensions_are_rejected(dimensions):
    with pytest.raises(ValueError):
        state_with_sheet("Custom", dimensions)


def test_custom_dimensions_cannot_be_hidden_in_preset_or_legacy_format():
    with pytest.raises(ValueError, match="only valid for Custom"):
        state_with_sheet("A4", [300, 400])
    for size, custom in [("A3", None), ("Custom", [600, 400])]:
        state = state_with_sheet(size, custom)
        for version in (7, 8):
            with pytest.raises(ValueError, match="require.*v9"):
                build_document_payload(state, version)


def test_custom_resize_history_and_failure_preserve_content(app, tmp_path):
    canvas = build_canvas_view()
    try:
        canvas.services.structure_build_service.add_benzene_ring(QPointF(250, 80))
        session = canvas.services.canvas_document_session_service
        before = session.snapshot_state()
        history = canvas.services.history_service
        change_sheet_setup_for(canvas, "Custom", "landscape", (600, 400))
        custom = session.snapshot_state()
        assert custom["model"] == before["model"]
        assert sheet_rect_for(canvas).width() == pytest.approx(600 * POINTS_PER_MM)
        history.undo()
        assert session.snapshot_state() == before
        history.redo()
        assert session.snapshot_state() == custom
        change_sheet_setup_for(canvas, "A3", "portrait")
        assert "sheet_custom_size_mm" not in session.snapshot_state()["settings"]
        history.undo()
        assert session.snapshot_state() == custom
        with patch.object(history, "push", side_effect=RuntimeError("failed history")):
            with pytest.raises(RuntimeError, match="failed history"):
                change_sheet_setup_for(canvas, "Custom", "portrait", (1000, 700))
        assert session.snapshot_state() == custom
        path = tmp_path / "custom.chemvas"
        write_document(path, custom, CANVAS_FILE_VERSION)
        session.apply_state(read_document(path).state)
        assert session.snapshot_state() == custom
    finally:
        canvas.close()
        canvas.deleteLater()
        app.processEvents()


def test_custom_dialog_dimensions_and_cancel(app):
    from chemvas.bootstrap.main_window import build_main_window

    window = build_main_window()
    try:

        def accept(dialog):
            sizes = dialog.findChild(QComboBox, "sheetSizeCombo")
            width = dialog.findChild(QDoubleSpinBox, "sheetWidthSpin")
            height = dialog.findChild(QDoubleSpinBox, "sheetHeightSpin")
            sizes.setCurrentText("A3")
            assert (width.value(), height.value()) == (420, 297)
            assert not width.isEnabled()
            sizes.setCurrentText("Custom")
            assert width.isEnabled() and height.isEnabled()
            width.setValue(600)
            height.setValue(400)
            return QDialog.DialogCode.Accepted

        with patch.object(QDialog, "exec", accept):
            result = prompt_sheet_setup(
                window, current_size="A4", current_orientation="landscape"
            )
        assert result.size == "Custom" and result.custom_size_mm == (600, 400)

        def reopen(dialog):
            assert dialog.findChild(QDoubleSpinBox, "sheetWidthSpin").value() == 600
            assert dialog.findChild(QDoubleSpinBox, "sheetHeightSpin").value() == 400
            return QDialog.DialogCode.Rejected

        with patch.object(QDialog, "exec", reopen):
            assert (
                prompt_sheet_setup(
                    window,
                    current_size="Custom",
                    current_orientation="landscape",
                    current_custom_size_mm=(600, 400),
                )
                is None
            )
    finally:
        window.deleteLater()
        app.processEvents()
