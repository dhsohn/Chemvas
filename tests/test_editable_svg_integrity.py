from __future__ import annotations

import json
from copy import deepcopy
from unittest.mock import Mock, patch

import pytest
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QLabel,
    QMessageBox,
)

from chemvas.bootstrap.main_window import build_main_window
from chemvas.core.svg_roundtrip import extract_chemvas_document_from_svg
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    CLIPBOARD_SELECTION_VERSION,
    build_document_payload,
    extract_document_state,
    image_state_from_bytes,
    selection_payload_to_canvas_state,
)
from chemvas.ui.canvas_calculation_plan_state import (
    calculation_plan_for,
    set_calculation_plan_for,
)
from chemvas.ui.canvas_document_metadata_state import document_file_path_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.main_window_document_dialogs import (
    FigureExportOptions,
    prompt_export_options,
)
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    history_service_for_window,
    services_for_window,
)
from chemvas.ui.structure_mutation_access import add_bond_for
from tests.test_calculation_plan import _document_state, _plan
from tests.test_calculation_step_dialog import _reviewed_precomplex_state
from tests.test_document_images import _raster


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def window(application):
    window = build_main_window()
    window.show()
    application.processEvents()
    try:
        yield window
    finally:
        services = services_for_window(window)
        services.canvas_document_service.mark_clean(active_canvas_for_window(window))
        window.close()
        application.processEvents()


def _install(window, state):
    canvas = active_canvas_for_window(window)
    services_for_window(window).canvas_document_service.replace_canvas_with_state(
        window, canvas, state=state, file_path=None, display_name="Synthetic drawing"
    )
    return canvas


def _options(*, editable=True, scope="sheet"):
    return FigureExportOptions(
        fmt="svg",
        sizing="bond",
        scope=scope,
        dpi=300,
        background="transparent",
        editable_svg=editable,
    )


def _export(window, destination, message_box, options=None):
    picker = Mock()
    picker.getSaveFileName.return_value = (str(destination), "SVG (*.svg)")
    with patch(
        "chemvas.ui.main_window_document_action_service.prompt_export_options",
        return_value=options or _options(),
    ):
        services_for_window(window).document_action_service.export_figure(
            window, file_dialog=picker, message_box=message_box
        )


def _problem(window, kind, tmp_path, monkeypatch, capsys):
    if kind == "review":
        state = _reviewed_precomplex_state(tmp_path, monkeypatch, capsys)
        canvas = _install(window, state)
        canvas.setFocus()
        QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.SelectAll))
        QTest.keyClick(canvas, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    else:
        canvas = _install(window, _document_state())
        plan = _plan()
        if kind == "charge":
            plan["states"][0]["charge"] = 1
        set_calculation_plan_for(canvas, plan)
        if kind == "stale":
            add_bond_for(canvas, 0, 2)
        services_for_window(window).canvas_document_service.mark_dirty(canvas)
    return canvas


@pytest.mark.parametrize("kind", ["stale", "charge", "review"])
def test_editable_whole_svg_requires_same_default_no_draft_consent_as_save(
    window, tmp_path, monkeypatch, capsys, kind
):
    canvas = _problem(window, kind, tmp_path, monkeypatch, capsys)
    before = snapshot_canvas_state_for(canvas)
    raw_plan = deepcopy(calculation_plan_for(canvas))
    history = history_service_for_window(window)
    stacks = history.capture_stack_snapshot()
    output = tmp_path / "drawing.svg"
    output.write_bytes(b"existing destination")
    message_box = Mock()
    message_box.question.return_value = QMessageBox.StandardButton.No

    with patch(
        "chemvas.ui.canvas_document_session_service.export_canvas_scene_for",
        side_effect=AssertionError("rendering must not start after No"),
    ) as render:
        _export(window, output, message_box)
    message_box.question.assert_called_once()
    args = message_box.question.call_args.args
    assert args[1] == "Calculation Plan Needs Attention"
    assert args[-1] == QMessageBox.StandardButton.No
    assert "Export anyway?" in args[2]
    assert ("omit" if kind == "stale" else "draft") in args[2]
    if kind == "review":
        assert "reviewed precomplex" in args[2]
    render.assert_not_called()
    message_box.warning.assert_not_called()
    assert output.read_bytes() == b"existing destination"
    assert snapshot_canvas_state_for(canvas) == before
    assert calculation_plan_for(canvas) == raw_plan
    assert document_file_path_for(canvas) is None
    assert services_for_window(window).canvas_document_service.is_dirty(canvas)
    history.verify_stack_snapshot(stacks)

    message_box.question.return_value = QMessageBox.StandardButton.Yes
    _export(window, output, message_box)
    message_box.warning.assert_not_called()
    restored = extract_chemvas_document_from_svg(output).state
    assert restored == json.loads(json.dumps(before))
    if kind == "stale":
        assert "calculation_plan" not in restored
    else:
        assert restored["calculation_plan"] == raw_plan
    assert snapshot_canvas_state_for(canvas) == before
    assert calculation_plan_for(canvas) == raw_plan
    assert document_file_path_for(canvas) is None
    assert services_for_window(window).canvas_document_service.is_dirty(canvas)
    history.verify_stack_snapshot(stacks)


@pytest.mark.parametrize("kind", ["stale", "charge", "review"])
def test_real_export_draft_notice_escape_preserves_destination(
    window, tmp_path, monkeypatch, capsys, kind
):
    canvas = _problem(window, kind, tmp_path, monkeypatch, capsys)
    before = snapshot_canvas_state_for(canvas)
    raw_plan = deepcopy(calculation_plan_for(canvas))
    output = tmp_path / "cancelled.svg"
    output.write_bytes(b"original SVG destination")
    observed = []

    def dismiss():
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, QMessageBox):
            observed.append(
                (
                    dialog.windowTitle(),
                    dialog.text(),
                    dialog.standardButton(dialog.defaultButton()),
                )
            )
            QTest.keyClick(dialog, Qt.Key.Key_Escape)

    QTimer.singleShot(0, dismiss)
    _export(window, output, QMessageBox)
    assert len(observed) == 1
    assert observed[0][0] == "Calculation Plan Needs Attention"
    assert observed[0][2] == QMessageBox.StandardButton.No
    assert "Export anyway?" in observed[0][1]
    assert output.read_bytes() == b"original SVG destination"
    assert snapshot_canvas_state_for(canvas) == before
    assert calculation_plan_for(canvas) == raw_plan


def test_accepted_draft_export_failure_keeps_destination_and_live_drawing(
    window, tmp_path, monkeypatch, capsys
):
    canvas = _problem(window, "charge", tmp_path, monkeypatch, capsys)
    before = snapshot_canvas_state_for(canvas)
    history = history_service_for_window(window)
    stacks = history.capture_stack_snapshot()
    output = tmp_path / "drawing.svg"
    output.write_bytes(b"existing destination")
    message_box = Mock()
    message_box.question.return_value = QMessageBox.StandardButton.Yes
    with patch(
        "chemvas.ui.canvas_document_session_service.embed_chemvas_document_in_svg",
        side_effect=OSError("synthetic metadata failure"),
    ):
        _export(window, output, message_box)
    message_box.question.assert_called_once()
    message_box.warning.assert_called_once()
    assert "synthetic metadata failure" in message_box.warning.call_args.args[2]
    assert output.read_bytes() == b"existing destination"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["drawing.svg"]
    assert snapshot_canvas_state_for(canvas) == before
    history.verify_stack_snapshot(stacks)


@pytest.mark.parametrize("stage", ["options", "destination"])
def test_cancelled_export_never_checks_or_warns_about_a_plan(window, stage):
    canvas = _install(window, _document_state())
    set_calculation_plan_for(canvas, _plan())
    message_box = Mock()
    picker = Mock()
    picker.getSaveFileName.return_value = ("", "")
    with (
        patch(
            "chemvas.ui.main_window_document_action_service.prompt_export_options",
            return_value=None if stage == "options" else _options(),
        ),
        patch(
            "chemvas.ui.main_window_document_action_service.snapshot_canvas_state_for",
            side_effect=AssertionError("cancel must not snapshot"),
        ) as snapshot,
    ):
        services_for_window(window).document_action_service.export_figure(
            window, file_dialog=picker, message_box=message_box
        )
    snapshot.assert_not_called()
    message_box.question.assert_not_called()
    message_box.warning.assert_not_called()


@pytest.mark.parametrize("kind", ["plain", "valid", "absent", "selection"])
def test_exports_without_whole_document_draft_consent(window, tmp_path, kind):
    canvas = _install(window, _document_state())
    if kind != "absent":
        plan = _plan()
        if kind in {"plain", "selection"}:
            plan["states"][0]["charge"] = 1
        set_calculation_plan_for(canvas, plan)
    if kind == "selection":
        canvas.setFocus()
        QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.SelectAll))
    message_box = Mock()
    output = tmp_path / "drawing.svg"
    _export(
        window,
        output,
        message_box,
        _options(
            editable=kind != "plain",
            scope="selection" if kind == "selection" else "sheet",
        ),
    )
    message_box.question.assert_not_called()
    message_box.warning.assert_not_called()
    assert output.stat().st_size > 0
    if kind != "plain":
        state = extract_chemvas_document_from_svg(output).state
        assert ("calculation_plan" in state) == (kind == "valid")


def test_selection_converter_remaps_every_group_item_kind_without_mutating_payload():
    items = [
        {"kind": "note", "text": "first", "x": 0.0, "y": 0.0},
        {
            "kind": "arrow",
            "start": [1.0, 2.0],
            "end": [3.0, 4.0],
            "control": None,
            "double": False,
        },
        image_state_from_bytes(_raster()),
        {"kind": "note", "text": "second", "x": 5.0, "y": 6.0},
        {
            "kind": "shape",
            "left": 0.0,
            "top": 0.0,
            "right": 20.0,
            "bottom": 20.0,
            "shape_kind": "rect",
            "stroke_style": "solid",
        },
        {
            "kind": "orbital",
            "orbital_kind": "p",
            "center": [8.0, 9.0],
            "scale": 1.2,
            "rotation": 30.0,
        },
        {
            "kind": "ts_bracket",
            "left": 1.0,
            "top": 2.0,
            "right": 3.0,
            "bottom": 4.0,
            "bracket_kind": "square_pair",
        },
        {
            "kind": "arrow",
            "start": [10.0, 20.0],
            "end": [30.0, 40.0],
            "control": None,
            "double": False,
        },
    ]
    payload = {
        "format": "chemvas-selection",
        "version": CLIPBOARD_SELECTION_VERSION,
        "atoms": [
            {
                "id": 7,
                "element": "C",
                "x": 0.0,
                "y": 0.0,
                "color": "#000000",
                "explicit_label": False,
            }
        ],
        "bonds": [],
        "rings": [],
        "marks": [
            {
                "kind": "mark",
                "mark_kind": "plus",
                "text": "+",
                "atom_id": None,
                "dx": None,
                "dy": None,
                "x": 0.0,
                "y": 20.0,
            }
        ],
        "scene_items": items,
        "groups": [
            {"atoms": [7], "items": [["scene_items", i] for i in (3, 2, 0, 7)]},
            {
                "atoms": [],
                "items": [["marks", 0]] + [["scene_items", i] for i in (1, 4, 5, 6)],
            },
        ],
    }
    before = deepcopy(payload)
    state = selection_payload_to_canvas_state(payload, _document_state()["settings"])
    expected = [
        {
            "atoms": [7],
            "items": [["notes", 1], ["images", 0], ["notes", 0], ["arrows", 1]],
        },
        {
            "atoms": [],
            "items": [
                ["marks", 0],
                ["arrows", 0],
                ["shapes", 0],
                ["orbitals", 0],
                ["ts_brackets", 0],
            ],
        },
    ]
    assert state["groups"] == expected
    assert (
        extract_document_state(build_document_payload(state, CANVAS_FILE_VERSION))[
            "groups"
        ]
        == expected
    )
    assert payload == before
    state["groups"][0]["atoms"].clear()
    state["groups"][0]["items"][0][1] = 99
    assert payload == before


def test_selected_group_survives_actual_svg_export_and_gui_reopen(window, tmp_path):
    state = _document_state()
    state["settings"]["sheet_size"] = "A3"
    state["settings"]["sheet_orientation"] = "portrait"
    state["notes"] = [{"text": "Grouped note", "x": 20.0, "y": 30.0}]
    state["groups"] = [{"atoms": [0, 1], "items": [["notes", 0]]}]
    canvas = _install(window, state)
    canvas.setFocus()
    QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.SelectAll))
    before = snapshot_canvas_state_for(canvas)
    message_box = Mock()
    output = tmp_path / "selected.svg"
    _export(window, output, message_box, _options(scope="selection"))
    message_box.warning.assert_not_called()
    restored = extract_chemvas_document_from_svg(output).state
    assert restored["groups"] == before["groups"]
    assert restored["settings"] == before["settings"]
    assert snapshot_canvas_state_for(canvas) == before
    assert services_for_window(window).document_action_service.load_canvas_from_path(
        window, str(output), message_box=message_box
    )
    canvas = active_canvas_for_window(window)
    reopened = snapshot_canvas_state_for(canvas)
    assert reopened["groups"] == before["groups"]
    assert reopened["settings"] == before["settings"]
    canvas.setFocus()
    QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.SelectAll))
    QTest.keyClick(canvas, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    moved = snapshot_canvas_state_for(canvas)
    assert moved["notes"][0]["x"] > reopened["notes"][0]["x"]
    assert moved["model"]["atoms"][0]["x"] > reopened["model"]["atoms"][0]["x"]
    assert moved["groups"] == reopened["groups"]
    QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.Undo))
    assert snapshot_canvas_state_for(canvas) == reopened
    QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.Redo))
    assert snapshot_canvas_state_for(canvas) == moved
    saved = tmp_path / "edited.chemvas"
    actions = services_for_window(window).document_action_service
    assert actions.save_canvas_to_path(window, str(saved), message_box=message_box)
    assert actions.load_canvas_from_path(window, str(saved), message_box=message_box)
    assert snapshot_canvas_state_for(active_canvas_for_window(window)) == moved
    message_box.warning.assert_not_called()


def test_editable_selection_notice_explains_subset_before_export(window):
    def inspect(dialog):
        fmt = dialog.findChild(QComboBox, "exportFormatCombo")
        scope = dialog.findChild(QComboBox, "exportScopeCombo")
        editable = dialog.findChild(QCheckBox, "exportEditableSvgCheck")
        notice = dialog.findChild(QLabel, "exportEditableSvgWarning")
        fmt.setCurrentIndex(fmt.findData("svg"))
        editable.setChecked(True)
        scope.setCurrentIndex(scope.findData("selection"))
        assert not notice.isHidden()
        assert "selected objects" in notice.text()
        assert "fully selected groups" in notice.text()
        assert "not the Calculation Plan or the whole sheet" in notice.text()
        assert "sheet settings" in notice.text()
        scope.setCurrentIndex(scope.findData("sheet"))
        assert "whole drawing" in notice.text()
        assert "not the Calculation Plan" not in notice.text()
        editable.setChecked(False)
        assert notice.isHidden()
        return QDialog.DialogCode.Rejected

    with patch("chemvas.ui.main_window_document_dialogs.QDialog.exec", new=inspect):
        assert prompt_export_options(window) is None
