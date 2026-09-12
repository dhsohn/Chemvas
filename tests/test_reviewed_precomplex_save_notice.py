from __future__ import annotations

from copy import deepcopy
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

from chemvas.bootstrap.main_window import build_main_window
from chemvas.core.document_io import read_document
from chemvas.features.calculation_bundle import (
    validate_calculation_plan,
    validate_reviewed_precomplex_pairs,
)
from chemvas.ui.canvas_calculation_plan_state import set_calculation_plan_for
from chemvas.ui.canvas_document_metadata_state import document_file_path_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.main_window_ports import active_canvas_for_window, services_for_window
from tests.test_calculation_step_dialog import _reviewed_precomplex_state


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def reviewed_window(tmp_path, monkeypatch, capsys, application):
    state = _reviewed_precomplex_state(tmp_path, monkeypatch, capsys)
    window = build_main_window()
    window.show()
    canvas = active_canvas_for_window(window)
    services = services_for_window(window)
    services.canvas_document_service.replace_canvas_with_state(
        window, canvas, state=state, file_path=None, display_name="Reviewed drawing"
    )
    canvas.setFocus()
    application.processEvents()
    try:
        yield window, canvas, services
    finally:
        services.canvas_document_service.mark_clean(canvas)
        window.close()
        application.processEvents()


def validate_review(state):
    plan = validate_calculation_plan(state, state["calculation_plan"])
    validate_reviewed_precomplex_pairs(state, plan)


def test_stale_review_notice_preserves_cancel_draft_and_undo(
    tmp_path, monkeypatch, reviewed_window
):
    window, canvas, services = reviewed_window
    monkeypatch.setattr(
        "chemvas.ui.main_window_document_action_service.record_recent", lambda _: None
    )
    monkeypatch.setattr(
        "chemvas.ui.main_window_document_action_service.request_snapshot", lambda: None
    )
    before = snapshot_canvas_state_for(canvas)
    validate_review(before)
    QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.SelectAll))
    QTest.keyClick(canvas, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    after = deepcopy(snapshot_canvas_state_for(canvas))
    with pytest.raises(ValueError, match="stale"):
        validate_review(after)
    assert after["calculation_plan"] == before["calculation_plan"]
    message_box = Mock()
    message_box.question.return_value = QMessageBox.StandardButton.No
    destination = tmp_path / "draft.chemvas"
    destination.write_bytes(b"keep existing destination")
    actions = services.document_action_service

    assert not actions.save_canvas_to_path(
        window, str(destination), message_box=message_box
    )
    assert destination.read_bytes() == b"keep existing destination"
    assert snapshot_canvas_state_for(canvas) == after
    assert document_file_path_for(canvas) is None
    assert services.canvas_document_service.is_dirty(canvas)
    message_box.question.assert_called_once()
    args = message_box.question.call_args.args
    assert args[1] == "Calculation Plan Needs Attention"
    assert "reviewed precomplex" in args[2]
    assert "draft" in args[2]
    assert "Undo" in args[2]
    assert args[-1] == QMessageBox.StandardButton.No
    message_box.warning.assert_not_called()

    message_box.question.return_value = QMessageBox.StandardButton.Yes
    assert actions.save_canvas_to_path(
        window, str(destination), message_box=message_box
    )
    saved = read_document(destination).state
    assert saved["calculation_plan"] == before["calculation_plan"]
    with pytest.raises(ValueError, match="stale"):
        validate_review(saved)
    message_box.warning.assert_not_called()

    QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.Undo))
    restored = snapshot_canvas_state_for(canvas)
    validate_review(restored)
    assert restored["model"] == before["model"]
    message_box.reset_mock()
    assert actions.save_canvas_to_path(
        window, str(destination), message_box=message_box
    )
    message_box.question.assert_not_called()
    validate_review(read_document(destination).state)


def test_current_review_saves_without_a_notice(tmp_path, monkeypatch, reviewed_window):
    window, canvas, services = reviewed_window
    monkeypatch.setattr(
        "chemvas.ui.main_window_document_action_service.record_recent", lambda _: None
    )
    monkeypatch.setattr(
        "chemvas.ui.main_window_document_action_service.request_snapshot", lambda: None
    )
    message_box = Mock()
    output = tmp_path / "current.chemvas"
    assert services.document_action_service.save_canvas_to_path(
        window, str(output), message_box=message_box
    )
    message_box.question.assert_not_called()
    message_box.warning.assert_not_called()
    validate_review(read_document(output).state)


def test_real_save_notice_defaults_to_no_and_escape_keeps_draft(
    tmp_path, reviewed_window
):
    window, canvas, services = reviewed_window
    QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.SelectAll))
    QTest.keyClick(canvas, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    before = snapshot_canvas_state_for(canvas)
    output = tmp_path / "cancelled.chemvas"
    observed = []

    def dismiss_notice():
        dialog = QApplication.activeModalWidget()
        if not isinstance(dialog, QMessageBox):
            observed.append("no save notice")
            return
        observed.append(
            (
                dialog.windowTitle(),
                dialog.text(),
                dialog.standardButton(dialog.defaultButton()),
            )
        )
        QTest.keyClick(dialog, Qt.Key.Key_Escape)

    QTimer.singleShot(50, dismiss_notice)
    assert not services.document_action_service.save_canvas_to_path(window, str(output))
    assert len(observed) == 1 and isinstance(observed[0], tuple)
    title, text, default = observed[0]
    assert title == "Calculation Plan Needs Attention"
    assert "reviewed precomplex" in text
    assert default == QMessageBox.StandardButton.No
    assert not output.exists()
    assert snapshot_canvas_state_for(canvas) == before


@pytest.mark.parametrize("review", ["unreviewed", "one-sided"])
def test_save_distinguishes_no_review_from_an_invalid_review_pair(
    tmp_path, monkeypatch, reviewed_window, review
):
    window, canvas, services = reviewed_window
    monkeypatch.setattr(
        "chemvas.ui.main_window_document_action_service.record_recent", lambda _: None
    )
    monkeypatch.setattr(
        "chemvas.ui.main_window_document_action_service.request_snapshot", lambda: None
    )
    plan = deepcopy(snapshot_canvas_state_for(canvas)["calculation_plan"])
    step = plan["steps"][0]
    sides = ("reactant", "product") if review == "unreviewed" else ("product",)
    for side in sides:
        step[side]["precomplex"]["selection"] = None
    set_calculation_plan_for(canvas, plan)
    message_box = Mock()
    message_box.question.return_value = QMessageBox.StandardButton.No
    output = tmp_path / "review-draft.chemvas"
    saved = services.document_action_service.save_canvas_to_path(
        window, str(output), message_box=message_box
    )
    assert saved == (review == "unreviewed")
    if review == "unreviewed":
        message_box.question.assert_not_called()
        assert read_document(output).state["calculation_plan"] == plan
    else:
        message_box.question.assert_called_once()
        assert not output.exists()
    assert snapshot_canvas_state_for(canvas)["calculation_plan"] == plan
    message_box.warning.assert_not_called()
