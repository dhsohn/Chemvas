from __future__ import annotations

import os
from copy import deepcopy

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QComboBox, QDialog, QDialogButtonBox

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.features.document_composition import compose_document_state
from chemvas.ui.canvas_document_state import (
    snapshot_canvas_document_state_with_warnings,
)
from chemvas.ui.canvas_group_state import group_state_for
from chemvas.ui.canvas_service_ports import history_service_for_access
from chemvas.ui.scheme_layout_dialog import (
    GroupLayoutChoice,
    SchemeLayoutDialog,
    arrange_grouped_canvas,
    grouped_layout_request,
)
from chemvas.ui.scheme_layout_service import plan_canvas_layout


@pytest.fixture(scope="module", autouse=True)
def application() -> QApplication:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    app.setQuitOnLastWindowClosed(False)
    return app


def _source():
    source = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {"id": 0, "element": "C", "x": 80, "y": 60},
                {"id": 1, "element": "O", "x": 110, "y": 60},
                {"id": 2, "element": "C", "x": 400, "y": 150},
                {"id": 3, "element": "N", "x": 430, "y": 150},
            ],
            "bonds": [{"a": 0, "b": 1, "order": 1}, {"a": 2, "b": 3, "order": 2}],
            "notes": [
                {"text": "Reactant", "x": 160, "y": 240},
                {"text": "Product", "x": 490, "y": 100},
                {"text": "Unassigned", "x": 700, "y": 80},
            ],
            "arrows": [{"kind": "arrow", "start": [240, 120], "end": [290, 120]}],
        }
    )
    source["groups"] = [
        {"atoms": [0, 1], "items": [["notes", 0]]},
        {"atoms": [2, 3], "items": [["notes", 1]]},
    ]
    return source


def _choices():
    return [GroupLayoutChoice(0, 1, 1, (0,), 0), GroupLayoutChoice(1, 1, 2, (1,))]


def _snapshot(canvas):
    source, warnings = snapshot_canvas_document_state_with_warnings(canvas)
    assert not warnings
    return source


def _assert_equal_coordinates(actual, expected):
    actual, expected = deepcopy(actual), deepcopy(expected)
    for atom_id, atom in actual["model"]["atoms"].items():
        target = expected["model"]["atoms"][atom_id]
        for axis in ("x", "y"):
            assert atom[axis] == pytest.approx(target[axis], abs=1e-8)
            atom[axis] = target[axis]
    for category, keys in (("notes", ("x", "y")), ("arrows", ("start", "end"))):
        for item, target in zip(actual[category], expected[category], strict=True):
            for key in keys:
                assert item[key] == pytest.approx(target[key], abs=1e-8)
                item[key] = target[key]
    assert actual == expected


def test_layout_is_one_undoable_edit_preserving_groups_and_unassigned_items():
    with offscreen_canvas(_source(), command="test-scheme-gui") as (canvas, _):
        before = _snapshot(canvas)
        groups = dict(group_state_for(canvas).groups)
        request = grouped_layout_request(before, _choices())
        plan = plan_canvas_layout(canvas, before, request)
        assert _snapshot(canvas) == before
        report = arrange_grouped_canvas(canvas, before, request)
        after = _snapshot(canvas)
        assert report == plan.report
        assert report["block_count"] == 2
        assert after != before
        assert after["groups"] == before["groups"]
        assert group_state_for(canvas).groups == groups
        assert after["notes"][2] == before["notes"][2]
        history = history_service_for_access(canvas)
        assert len(history.state.history) == 1
        history.undo()
        _assert_equal_coordinates(_snapshot(canvas), before)
        history.redo()
        _assert_equal_coordinates(_snapshot(canvas), after)


def test_too_narrow_layout_and_stale_source_leave_canvas_and_history_unchanged():
    with offscreen_canvas(_source(), command="test-scheme-gui") as (canvas, _):
        source = _snapshot(canvas)
        request = grouped_layout_request(source, _choices(), max_row_width=1)
        with pytest.raises(ValueError, match="max_row_width"):
            arrange_grouped_canvas(canvas, source, request)
        assert _snapshot(canvas) == source
        stale = deepcopy(source)
        stale["notes"][0]["x"] += 1
        with pytest.raises(ValueError, match="drawing changed"):
            arrange_grouped_canvas(canvas, stale, request)
        assert not history_service_for_access(canvas).state.history


def test_disabled_history_rolls_back_initial_edit():
    with offscreen_canvas(_source(), command="test-scheme-gui") as (canvas, _):
        source = _snapshot(canvas)
        history = history_service_for_access(canvas)
        history.state.enabled = False
        with pytest.raises(ValueError, match="History is disabled"):
            arrange_grouped_canvas(
                canvas, source, grouped_layout_request(source, _choices())
            )
        assert _snapshot(canvas) == source
        assert not history.state.history


@pytest.mark.parametrize(
    ("choices", "message"),
    [
        ([GroupLayoutChoice(0, 1, 1, (1,))], "own group"),
        (
            [GroupLayoutChoice(0, 1, 1, (0,)), GroupLayoutChoice(1, 1, 1, (1,))],
            "duplicate order",
        ),
        ([GroupLayoutChoice(0, 1, 1, (0,), 0)], "last group"),
        ([GroupLayoutChoice(0, 1, 1, (0,)), GroupLayoutChoice(0, 2, 1, (0,))], "once"),
        ([GroupLayoutChoice(0, 0, 1, ())], "non-empty"),
        ([GroupLayoutChoice(0, 1, 1, (0, 0))], "duplicate"),
    ],
)
def test_bad_explicit_choices_reject(choices, message):
    with pytest.raises(ValueError, match=message):
        grouped_layout_request(_source(), choices)


def test_row_order_and_caption_roles_are_explicit():
    request = grouped_layout_request(
        _source(), [GroupLayoutChoice(0, 2, 1, ()), GroupLayoutChoice(1, 1, 1, (1,))]
    )
    assert request.rows[0].blocks[0].atoms == (2, 3)
    assert request.rows[1].blocks[0].items == (("notes", 0),)
    assert not request.rows[1].blocks[0].captions


def test_two_groups_without_arrows_use_the_supported_gallery_layout():
    source = _source()
    choices = [GroupLayoutChoice(0, 1, 1, (0,)), GroupLayoutChoice(1, 1, 2, (1,))]
    request = grouped_layout_request(source, choices)
    assert len(request.rows[0].blocks) == 2
    assert request.rows[0].arrows == ()
    with offscreen_canvas(source, command="test-scheme-gallery") as (canvas, _):
        current = _snapshot(canvas)
        report = arrange_grouped_canvas(
            canvas, current, grouped_layout_request(current, choices)
        )
        assert report["block_count"] == 2
        assert _snapshot(canvas)["arrows"] == current["arrows"]


@pytest.mark.parametrize("tag", ["ol", "ul"])
def test_automatic_list_cannot_be_a_caption_but_can_move_as_a_group_item(tag):
    source = _source()
    source["notes"][0]["html"] = f"<{tag}><li>H</li></{tag}>"
    with offscreen_canvas(source, command="test-list-caption") as (canvas, _):
        source = _snapshot(canvas)
        request = grouped_layout_request(source, [GroupLayoutChoice(0, 1, 1, (0,))])
        with pytest.raises(ValueError, match="list.*caption"):
            arrange_grouped_canvas(canvas, source, request)
        assert _snapshot(canvas) == source
        request = grouped_layout_request(source, [GroupLayoutChoice(0, 1, 1, ())])
        arrange_grouped_canvas(canvas, source, request)
        assert _snapshot(canvas)["notes"][0]["html"] == source["notes"][0]["html"]


def test_mid_operation_failure_restores_document_and_history(monkeypatch):
    from chemvas.ui.history_commands import MoveItemsCommand

    with offscreen_canvas(_source(), command="test-scheme-failure") as (canvas, _):
        source = _snapshot(canvas)

        def fail_note_move(self, canvas):
            raise RuntimeError("injected note movement error")

        monkeypatch.setattr(MoveItemsCommand, "redo", fail_note_move)
        with pytest.raises(RuntimeError, match="injected note movement"):
            arrange_grouped_canvas(
                canvas, source, grouped_layout_request(source, _choices())
            )
        assert _snapshot(canvas) == source
        assert not history_service_for_access(canvas).state.history


def test_dialog_cancel_and_validation_do_not_call_mutator():
    calls = []
    dialog = SchemeLayoutDialog(
        _source(), arrange=lambda request: calls.append(request) or {}
    )
    dialog.group_widgets[0].captions.setText("not a number")
    dialog._apply()
    assert not calls
    assert dialog.error_label.text()
    dialog.reject()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert not calls
    dialog.deleteLater()


def test_dialog_apply_uses_native_grouped_arrangement():
    with offscreen_canvas(_source(), command="test-scheme-gui") as (canvas, _):
        source = _snapshot(canvas)
        dialog = SchemeLayoutDialog(
            source,
            arrange=lambda request: arrange_grouped_canvas(canvas, source, request),
        )
        dialog.group_widgets[0].arrow.setCurrentIndex(1)
        buttons = dialog.findChild(QDialogButtonBox)
        assert buttons is not None
        buttons.button(QDialogButtonBox.StandardButton.Ok).click()
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.result_report["block_count"] == 2
        assert len(history_service_for_access(canvas).state.history) == 1
        dialog.deleteLater()


def test_dialog_does_not_guess_caption_roles_from_position():
    source = _source()
    source["groups"][0]["items"].append(["notes", 2])
    dialog = SchemeLayoutDialog(source, arrange=lambda request: {})
    assert all(not group.captions.text() for group in dialog.group_widgets)
    assert dialog.caption_alignment.currentData() == "row"
    assert not dialog.arrow_color.text()
    dialog.deleteLater()


def test_named_note_role_picker_preserves_caption_order_and_cancel(monkeypatch):
    source = _source()
    source["groups"][0]["items"].append(["notes", 2])
    dialog = SchemeLayoutDialog(source, arrange=lambda request: {})
    group = dialog.group_widgets[0]
    group.captions.setText("3, 1")

    def choose(roles_dialog):
        roles_dialog.findChild(QComboBox, "schemeNoteRole0").setCurrentIndex(0)
        assert (
            roles_dialog.findChild(QComboBox, "schemeNoteRole2").currentData()
            == "caption"
        )
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", choose)
    dialog._choose_note_roles(group)
    assert group.captions.text() == "3"
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    dialog._choose_note_roles(group)
    assert group.captions.text() == "3"
    dialog.deleteLater()


def test_comparison_controls_use_shared_validator_and_explicit_arrow_owner():
    calls = []
    dialog = SchemeLayoutDialog(
        _source(), arrange=lambda request: calls.append(request) or {}
    )
    first, second = dialog.group_widgets
    first.captions.setText("1")
    second.captions.setText("2")
    first.arrow.setCurrentIndex(1)
    first.column_group.setText("comparison")
    dialog.caption_alignment.setCurrentIndex(1)
    dialog.arrow_color.setText("#000000")
    dialog._apply()
    assert len(calls) == 1
    request = calls[0]
    assert request.rows[0].column_group == "comparison"
    assert request.rows[0].blocks[0].captions == (0,)
    assert request.rows[0].arrows == (0,)
    assert request.caption_alignment == "structure"
    assert request.arrow_color == "#000000"
    dialog.deleteLater()


def test_conflicting_comparison_groups_and_invalid_color_reject():
    choices = [
        GroupLayoutChoice(0, 1, 1, (0,), 0, "a"),
        GroupLayoutChoice(1, 1, 2, (1,), None, "b"),
    ]
    with pytest.raises(ValueError, match="conflicting alignment groups"):
        grouped_layout_request(_source(), choices)
    with pytest.raises(ValueError, match="arrow_color"):
        grouped_layout_request(_source(), _choices(), arrow_color="blue")


def test_arrow_color_and_geometry_are_one_edit_with_exact_undo_and_reopen():
    source = _source()
    source["arrows"][0].update(
        color="#0055aa", labels={"above": "H_2O", "below": "condition"}
    )
    source["arrows"].append(
        {"kind": "arrow", "start": [640, 260], "end": [710, 260], "color": "#cc0000"}
    )
    with offscreen_canvas(source, command="test-scheme-gui-color") as (canvas, _):
        before = _snapshot(canvas)
        request = grouped_layout_request(before, _choices(), arrow_color="#000000")
        arrange_grouped_canvas(canvas, before, request)
        after = _snapshot(canvas)
        assert after["arrows"][0]["color"] == "#000000"
        assert after["arrows"][0]["labels"] == before["arrows"][0]["labels"]
        assert after["arrows"][1] == before["arrows"][1]
        assert after["settings"] == before["settings"]
        assert after["groups"] == before["groups"]
        history = history_service_for_access(canvas)
        assert len(history.state.history) == 1
        history.undo()
        _assert_equal_coordinates(_snapshot(canvas), before)
        history.redo()
        _assert_equal_coordinates(_snapshot(canvas), after)
    with offscreen_canvas(after, command="test-scheme-gui-reopen") as (canvas, _):
        _assert_equal_coordinates(_snapshot(canvas), after)


def test_failed_movement_rolls_back_prior_color_change(monkeypatch):
    from chemvas.core.history import MoveAtomsCommand

    source = _source()
    source["arrows"][0]["color"] = "#0055aa"
    with offscreen_canvas(source, command="test-scheme-gui-color-rollback") as (
        canvas,
        _,
    ):
        before = _snapshot(canvas)

        def fail(self, canvas):
            raise RuntimeError("injected movement after recoloring")

        monkeypatch.setattr(MoveAtomsCommand, "redo", fail)
        with pytest.raises(RuntimeError, match="injected movement"):
            arrange_grouped_canvas(
                canvas,
                before,
                grouped_layout_request(before, _choices(), arrow_color="#000000"),
            )
        assert _snapshot(canvas) == before
        assert not history_service_for_access(canvas).state.history
