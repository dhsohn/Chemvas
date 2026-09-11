import pytest
from PyQt6.QtCore import QPointF, QRect, QRectF
from PyQt6.QtGui import QPicture
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QGraphicsRectItem

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.canvas_service_ports import history_service_for_access
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    set_sheet_setup_for_window,
)
from chemvas.ui.preview_scene_renderer import SmilesPreviewItem
from chemvas.ui.scene_decoration_access import add_arrow_for
from chemvas.ui.sheet_setup_access import sheet_setup_for

_APP = QApplication.instance() or QApplication([])
_APP.setQuitOnLastWindowClosed(False)


def test_sheet_change_is_one_undoable_edit_without_removing_content():
    window = build_main_window()
    canvas = active_canvas_for_window(window)
    arrow = add_arrow_for(canvas, QPointF(330, 0), QPointF(410, 0), "arrow")
    history = history_service_for_access(canvas)
    count = len(history.state.history)
    set_sheet_setup_for_window(window, "A4", "portrait")
    assert len(history.state.history) == count + 1
    assert sheet_setup_for(canvas) == ("A4", "portrait")
    history.undo()
    assert sheet_setup_for(canvas) == ("A4", "landscape")
    assert arrow.scene() is canvas.scene()
    history.redo()
    assert sheet_setup_for(canvas) == ("A4", "portrait")
    assert canvas.sceneRect().contains(arrow.sceneBoundingRect())
    set_sheet_setup_for_window(window, "A4", "portrait")
    assert len(history.state.history) == count + 1
    window.deleteLater()


@pytest.mark.parametrize("rejected", [False, True])
def test_failed_sheet_history_push_restores_sheet_and_rect(monkeypatch, rejected):
    window = build_main_window()
    canvas = active_canvas_for_window(window)
    history = history_service_for_access(canvas)
    before = (sheet_setup_for(canvas), canvas.sceneRect(), list(history.state.history))

    def fail(_command):
        if rejected:
            return False
        raise RuntimeError("injected push failure")

    monkeypatch.setattr(history, "push", fail)
    with pytest.raises(RuntimeError, match="injected push failure|did not commit"):
        set_sheet_setup_for_window(window, "A4", "portrait")
    assert (
        sheet_setup_for(canvas),
        canvas.sceneRect(),
        list(history.state.history),
    ) == before
    window.deleteLater()


def test_sheet_change_with_explicitly_disabled_history_is_allowed():
    window = build_main_window()
    canvas = active_canvas_for_window(window)
    history = history_service_for_access(canvas)
    history.state.enabled = False
    set_sheet_setup_for_window(window, "A4", "portrait")
    assert sheet_setup_for(canvas) == ("A4", "portrait")
    assert not history.state.history
    window.deleteLater()


def test_reopened_portrait_document_keeps_outside_content_reachable():
    from chemvas.bootstrap.document_cli_shared import offscreen_canvas
    from chemvas.features.document_composition import compose_document_state

    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [],
            "bonds": [],
            "arrows": [{"kind": "arrow", "start": [330, 0], "end": [410, 0]}],
            "settings": {"sheet_orientation": "portrait"},
        }
    )
    with offscreen_canvas(state, command="sheet-reopen-regression") as (
        canvas,
        _service,
    ):
        assert canvas.sceneRect().contains(QPointF(410, 0))


@pytest.mark.parametrize("preview_kind", ["smiles", "roleless", "selection_outline"])
@pytest.mark.parametrize("off_sheet_content", [False, True])
def test_sheet_bounds_ignore_transient_previews_but_keep_real_content(
    preview_kind, off_sheet_content
):
    window = build_main_window()
    window.show()
    assert QTest.qWaitForWindowExposed(window, 5000)
    canvas = active_canvas_for_window(window)
    if off_sheet_content:
        arrow = add_arrow_for(canvas, QPointF(1400, 0), QPointF(1500, 0), "arrow")
        # Real content's role-less descendants (e.g. painted label parts)
        # must still contribute through the retained parent's closure.
        child = QGraphicsRectItem(QRectF(1600, 0, 40, 40), arrow)
    history = history_service_for_access(canvas)
    set_sheet_setup_for_window(window, "A4", "portrait")
    expected = canvas.sceneRect()
    history.undo()
    if preview_kind == "smiles":
        picture = QPicture()
        picture.setBoundingRect(QRect(5000, 0, 500, 500))
        preview = SmilesPreviewItem(picture)
    else:
        preview = QGraphicsRectItem(QRectF(5000, 0, 500, 500))
        if preview_kind != "roleless":
            preview.setData(0, preview_kind)
    canvas.scene().addItem(preview)
    set_sheet_setup_for_window(window, "A4", "portrait")
    assert canvas.sceneRect() == expected
    assert canvas.scene().sceneRect() == expected
    if off_sheet_content:
        assert expected.contains(arrow.sceneBoundingRect())
        assert expected.contains(child.sceneBoundingRect())
    preview.setPos(5000, 0)
    canvas.scene().removeItem(preview)
    assert canvas.sceneRect() == expected
    history.undo()
    history.redo()
    assert canvas.sceneRect() == expected
    window.deleteLater()
