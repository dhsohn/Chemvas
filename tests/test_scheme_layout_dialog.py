from __future__ import annotations

import json
import math
import os
from copy import deepcopy

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QMessageBox,
)

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.bootstrap.main_window import build_main_window
from chemvas.features.document_composition import compose_document_state
from chemvas.ui.canvas_document_metadata_state import (
    document_is_dirty_for,
    mark_document_clean_for,
)
from chemvas.ui.canvas_document_state import (
    snapshot_canvas_document_state_with_warnings,
)
from chemvas.ui.canvas_group_state import group_state_for
from chemvas.ui.canvas_service_ports import history_service_for_access
from chemvas.ui.main_window_ports import active_canvas_for_window, services_for_window
from chemvas.ui.scene_decoration_access import add_mark_for_atom_for
from chemvas.ui.scene_item_access import restore_ring_from_state
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


def _fractional_source():
    atoms, bonds, notes, groups = [], [], [], []
    for column, size in enumerate((3, 6, 4)):
        start = len(atoms)
        center = (-300, 0, 300)[column]
        for vertex in range(size):
            angle = 2 * math.pi * vertex / size + math.pi / 2
            atoms.append(
                {
                    "id": start + vertex,
                    "element": "C",
                    "x": center + 20 * math.cos(angle),
                    "y": 20 * math.sin(angle),
                }
            )
            bonds.append(
                {"a": start + vertex, "b": start + (vertex + 1) % size, "order": 1}
            )
        notes.append({"text": f"Compound {column + 1}", "x": center + 0.1, "y": 60.3})
        groups.append(
            {"atoms": list(range(start, start + size)), "items": [["notes", column]]}
        )
    source = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": atoms,
            "bonds": bonds,
            "notes": notes,
            "arrows": [
                {
                    "kind": "arrow",
                    "start": [-210.1, 13.3],
                    "end": [-90.7, 13.3],
                    "color": "#0055aa",
                    "labels": {"above": "H_2O", "below": "heat"},
                },
                {"kind": "arrow", "start": [90.1, 13.3], "end": [210.7, 13.3]},
            ],
        }
    )
    source["groups"] = groups
    return source


def _fractional_choices():
    return [
        GroupLayoutChoice(i, 1, i + 1, (i,), i if i < 2 else None) for i in range(3)
    ]


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "circled_plus", "circled_minus", "radical"]
)
def test_fractional_layout_undo_restores_exact_raw_state_and_clean_marker(kind):
    with offscreen_canvas(_fractional_source(), command="test-arrange-exact") as (
        canvas,
        _,
    ):
        atom = canvas.model.atoms[4]
        mark = add_mark_for_atom_for(
            canvas, 4, QPointF(atom.x + 7.1, atom.y - 3.4), kind=kind
        )
        restore_ring_from_state(
            canvas,
            {
                "kind": "ring",
                "atom_ids": [0, 1, 2],
                "points": [
                    (canvas.model.atoms[i].x, canvas.model.atoms[i].y) for i in range(3)
                ],
                "color": "#ffeeaa",
                "alpha": 0.3,
            },
        )
        history = history_service_for_access(canvas)
        history.clear()
        before = _snapshot(canvas)
        mark_position = mark.pos()
        groups = dict(group_state_for(canvas).groups)
        mark_document_clean_for(canvas, before)
        assert not document_is_dirty_for(canvas, before)
        request = grouped_layout_request(
            before, _fractional_choices(), arrow_color="#000000"
        )
        arrange_grouped_canvas(canvas, before, request)
        after = _snapshot(canvas)
        assert "item_pos" not in json.dumps(after)
        assert document_is_dirty_for(canvas, after)
        assert len(history.state.history) == 1
        for _ in range(3):
            history.undo()
            assert _snapshot(canvas) == before
            assert mark.pos() == mark_position
            assert not document_is_dirty_for(canvas, _snapshot(canvas))
            assert group_state_for(canvas).groups == groups
            history.redo()
            assert _snapshot(canvas) == after
            assert document_is_dirty_for(canvas, _snapshot(canvas))
            assert group_state_for(canvas).groups == groups


def test_already_arranged_layout_preserves_existing_redo_and_raw_state():
    with offscreen_canvas(_fractional_source(), command="test-arrange-noop") as (
        canvas,
        _,
    ):
        before = _snapshot(canvas)
        arrange_grouped_canvas(
            canvas, before, grouped_layout_request(before, _fractional_choices())
        )
        arranged = _snapshot(canvas)
        history = history_service_for_access(canvas)
        from chemvas.ui.scene_decoration_access import add_arrow_for

        extra = add_arrow_for(canvas, QPointF(500, 100), QPointF(540, 100), "arrow")
        history.undo()
        assert extra.scene() is None
        assert _snapshot(canvas) == arranged
        stacks = history.capture_stack_snapshot()
        assert history.can_redo()
        arrange_grouped_canvas(
            canvas, arranged, grouped_layout_request(arranged, _fractional_choices())
        )
        assert _snapshot(canvas) == arranged
        assert history.capture_stack_snapshot() == stacks


@pytest.mark.parametrize("phase", ["push_false", "push_raise", "undo", "redo"])
def test_failed_layout_history_restores_exact_geometry_and_existing_stacks(
    monkeypatch, phase
):
    from chemvas.ui import history_commands

    with offscreen_canvas(
        _fractional_source(), command="test-arrange-history-failure"
    ) as (canvas, _):
        history = history_service_for_access(canvas)
        original = _snapshot(canvas)
        arrange_grouped_canvas(
            canvas,
            original,
            grouped_layout_request(
                original, _fractional_choices(), arrow_color="#000000"
            ),
        )
        if phase != "undo":
            history.undo()
        before = _snapshot(canvas)
        stacks = history.capture_stack_snapshot()
        groups = dict(group_state_for(canvas).groups)

        def fail(*args, **kwargs):
            raise RuntimeError("injected layout history error")

        with monkeypatch.context() as injected:
            if phase.startswith("push"):
                injected.setattr(
                    history,
                    "push",
                    (lambda command: False) if phase == "push_false" else fail,
                )
                with pytest.raises(
                    (ValueError, RuntimeError),
                    match="History is disabled|injected layout",
                ):
                    arrange_grouped_canvas(
                        canvas,
                        before,
                        grouped_layout_request(
                            before, _fractional_choices(), arrow_color="#000000"
                        ),
                    )
            else:
                # The command has already restored atoms when item application
                # fails: only the existing exact savepoint may recover it.
                injected.setattr(history_commands, "_apply_scene_item_state", fail)
                with pytest.raises(RuntimeError, match="injected layout"):
                    (history.undo if phase == "undo" else history.redo)()
        assert _snapshot(canvas) == before
        assert history.capture_stack_snapshot() == stacks
        assert group_state_for(canvas).groups == groups
        if phase == "undo":
            history.undo()
            assert _snapshot(canvas) == original
        elif phase == "redo":
            history.redo()
            assert _snapshot(canvas) != original


def test_saved_window_arrange_button_and_shortcut_undo_clear_modified_title(
    application, tmp_path, monkeypatch
):
    questions = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: questions.append(args) or QMessageBox.StandardButton.Cancel,
    )
    window = build_main_window()
    windows = [window]
    try:
        canvas = active_canvas_for_window(window)
        services = services_for_window(window)
        canvas.services.document.canvas_document_session_service.apply_state(
            _fractional_source()
        )
        path = tmp_path / "fractional-scheme.chemvas"
        assert services.document_action_service.save_canvas_to_path(window, str(path))
        original_bytes = path.read_bytes()
        assert "item_pos" not in original_bytes.decode("utf-8")
        assert window.close()
        windows.remove(window)
        application.processEvents()
        window = build_main_window()
        windows.append(window)
        services = services_for_window(window)
        assert services.document_action_service.load_canvas_from_path(window, str(path))
        canvas = active_canvas_for_window(window)
        window.show()
        assert QTest.qWaitForWindowExposed(window, 5000)
        before = _snapshot(canvas)
        clean_title = window.windowTitle()
        clean_tab = window.tab_references.canvas_tabs.tabText(0)
        assert not window.isWindowModified()
        dialog = SchemeLayoutDialog(
            before,
            parent=window,
            arrange=lambda request: arrange_grouped_canvas(canvas, before, request),
        )
        for i, entry in enumerate(dialog.group_widgets):
            entry.captions.setText(str(i + 1))
            if i < 2:
                entry.arrow.setCurrentIndex(i + 1)
        dialog.arrow_color.setText("#000000")
        dialog.show()
        application.processEvents()
        buttons = dialog.findChild(QDialogButtonBox)
        QTest.mouseClick(
            buttons.button(QDialogButtonBox.StandardButton.Ok),
            Qt.MouseButton.LeftButton,
        )
        assert dialog.result() == QDialog.DialogCode.Accepted, dialog.error_label.text()
        assert window.isWindowModified()
        arranged = _snapshot(canvas)
        canvas.setFocus()
        for _ in range(2):
            QTest.keySequence(canvas, QKeySequence.StandardKey.Undo)
            application.processEvents()
            assert _snapshot(canvas) == before
            assert not services.canvas_document_service.is_dirty(canvas)
            assert not window.isWindowModified()
            assert window.windowTitle() == clean_title
            assert window.tab_references.canvas_tabs.tabText(0) == clean_tab
            QTest.keySequence(canvas, QKeySequence.StandardKey.Redo)
            application.processEvents()
            assert _snapshot(canvas) == arranged
            assert window.isWindowModified()
        QTest.keySequence(canvas, QKeySequence.StandardKey.Undo)
        application.processEvents()
        assert window.close()
        windows.remove(window)
        assert questions == []
        assert path.read_bytes() == original_bytes
    finally:
        for window in windows:
            services = services_for_window(window)
            services.canvas_document_service.mark_clean(
                active_canvas_for_window(window)
            )
            window.close()
        application.processEvents()


def test_unsupported_group_image_error_uses_dialog_row_and_group_numbers():
    from io import BytesIO

    from PIL import Image

    from chemvas.domain.document import image_state_from_bytes

    source = _source()
    stream = BytesIO()
    Image.new("RGB", (1, 1), "white").save(stream, format="PNG")
    source["images"] = [image_state_from_bytes(stream.getvalue())]
    source["groups"][0]["items"].append(["images", 0])
    with pytest.raises(ValueError, match=r"Row 1, group 1 contains images.*Remove"):
        grouped_layout_request(source, _choices())


def _snapshot(canvas):
    source, warnings = snapshot_canvas_document_state_with_warnings(canvas)
    assert not warnings
    return source


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
        assert _snapshot(canvas) == before
        history.redo()
        assert _snapshot(canvas) == after


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
    from chemvas.ui import scene_transform_controller

    with offscreen_canvas(_source(), command="test-scheme-failure") as (canvas, _):
        source = _snapshot(canvas)

        def fail_note_move(*args, **kwargs):
            raise RuntimeError("injected note movement error")

        monkeypatch.setattr(scene_transform_controller, "move_item_for", fail_note_move)
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
        assert _snapshot(canvas) == before
        history.redo()
        assert _snapshot(canvas) == after
    with offscreen_canvas(after, command="test-scheme-gui-reopen") as (canvas, _):
        assert _snapshot(canvas) == after


def test_failed_movement_rolls_back_prior_color_change(monkeypatch):
    from chemvas.ui import scene_transform_controller

    source = _source()
    source["arrows"][0]["color"] = "#0055aa"
    with offscreen_canvas(source, command="test-scheme-gui-color-rollback") as (
        canvas,
        _,
    ):
        before = _snapshot(canvas)

        def fail(*args, **kwargs):
            raise RuntimeError("injected movement after recoloring")

        monkeypatch.setattr(scene_transform_controller, "move_atoms_for", fail)
        with pytest.raises(RuntimeError, match="injected movement"):
            arrange_grouped_canvas(
                canvas,
                before,
                grouped_layout_request(before, _choices(), arrow_color="#000000"),
            )
        assert _snapshot(canvas) == before
        assert not history_service_for_access(canvas).state.history
