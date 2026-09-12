"""Document text changes agree with arrow-label history and reconstruction."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QTextCharFormat, QTextCursor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.main_window import build_main_window
from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.ui.canvas_scene_items_state import arrow_items_for
from chemvas.ui.canvas_window_access import (
    restore_canvas_state_for,
    snapshot_canvas_state_for,
)
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    redo_action_for_window,
    services_for_window,
)
from chemvas.ui.move_access import move_item_for
from chemvas.ui.scene_decoration_access import add_arrow_for
from chemvas.ui.scene_item_access import apply_scene_item_state
from chemvas.ui.scene_item_state import scene_item_state_for
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvases(app):
    opened = []

    def create():
        canvas = build_canvas_view()
        canvas.services.input.tool_mode_controller.set_tool("select")
        opened.append(canvas)
        return canvas

    yield create
    for canvas in reversed(opened):
        canvas.services.document.canvas_scene_reset_service.clear_scene()
        canvas.close()
        canvas.deleteLater()
    app.processEvents()


def _style(canvas):
    return canvas.services.scene_operations.style_controller


def _arrow(canvas, *, kind="arrow", color=None, vertical=False):
    start, end = (
        (QPointF(0, -60), QPointF(0, 60))
        if vertical
        else (QPointF(-60, 0), QPointF(60, 0))
    )
    item = add_arrow_for(canvas, start, end, kind)
    state = scene_item_state_for(canvas, item)
    state["labels"] = {"above": "k_1\nA", "below": "k_-1"}
    if color is not None:
        state["color"] = color
    apply_scene_item_state(canvas, item, state)
    move_item_for(canvas, item, 23.75, 41.5)
    item.setSelected(True)
    return item


def _labels(item):
    return [child for child in item.childItems() if child.data(0) == "arrow_label"]


def _appearance(item):
    return [
        (
            child.data(1),
            child.font(),
            child.defaultTextColor(),
            child.toHtml(),
            child.sceneBoundingRect(),
        )
        for child in _labels(item)
    ]


def _change(canvas, change):
    controller = _style(canvas)
    if change == "family":
        controller.set_text_font_family_default("DejaVu Serif")
    elif change == "color":
        controller.set_text_color(QColor("#604090"))
    else:
        getattr(controller, f"apply_text_preset_{change}")()


@pytest.mark.parametrize(
    "change,expected",
    [
        ("paper_bold", ("Arial", 14, 600, "#111111")),
        ("paper_thin", ("Arial", 11, 400, "#222222")),
        ("acs", ("Arial", 12, 400, "#000000")),
        ("family", ("DejaVu Serif", 12, 400, "#222222")),
        ("color", ("Arial", 12, 400, "#604090")),
    ],
)
@pytest.mark.parametrize("color", [None, "#bA2040"])
def test_existing_labels_follow_document_text_settings_and_exact_history(
    canvases, change, expected, color
):
    canvas = canvases()
    if change == "acs":
        _style(canvas).apply_text_preset_paper_bold()
    item = _arrow(canvas, color=color)
    history = canvas.services.history_service
    history.clear()
    before = snapshot_canvas_state_for(canvas)
    original = _appearance(item)
    geometry = item.path(), item.pen(), item.pos()
    _change(canvas, change)
    family, size, weight, text_color = expected
    for child in _labels(item):
        assert child.font().family() == family
        assert child.font().pointSizeF() == size
        assert int(child.font().weight()) == weight
        assert not child.font().italic()
        assert child.defaultTextColor() == QColor(color or text_color)
    after = snapshot_canvas_state_for(canvas)
    appearance = _appearance(item)
    assert after["arrows"] == before["arrows"]
    assert after["model"] == before["model"]
    assert (item.path(), item.pen(), item.pos()) == geometry
    assert item.isSelected()
    assert len(history.state.history) == 1
    history.undo()
    assert snapshot_canvas_state_for(canvas) == before
    assert _appearance(item) == original
    history.redo()
    assert snapshot_canvas_state_for(canvas) == after
    assert _appearance(item) == appearance


def _pixels(path):
    image = QImage(str(path)).convertToFormat(QImage.Format.Format_RGBA8888)
    assert not image.isNull()
    return image.size(), image.constBits().asstring(image.sizeInBytes())


@pytest.mark.parametrize(
    "kind,vertical",
    [
        ("arrow", False),
        ("arrow", True),
        ("equilibrium", False),
        ("curved_single", False),
        ("arc_270_left", False),
        ("line", False),
    ],
)
def test_nudge_undo_and_saved_reopen_preserve_current_label_paint(
    canvases, tmp_path, kind, vertical
):
    canvas = canvases()
    item = _arrow(canvas, kind=kind, vertical=vertical)
    _style(canvas).apply_text_preset_paper_bold()
    before = snapshot_canvas_state_for(canvas)
    appearance = _appearance(item)
    session = canvas.services.document.canvas_document_session_service
    first = tmp_path / "before.png"
    session.export_figure(str(first), fmt="png", dpi=120, scope="sheet")
    QTest.keyClick(
        canvas.viewport(), Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier
    )
    moved = snapshot_canvas_state_for(canvas)
    assert moved != before
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    assert _appearance(item) == appearance
    canvas.services.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == moved
    canvas.services.history_service.undo()
    path = tmp_path / "labels.chemvas"
    write_document(path, before, CANVAS_FILE_VERSION)
    saved_bytes = path.read_bytes()
    reopened = canvases()
    restore_canvas_state_for(reopened, read_document(path).state)
    assert _appearance(arrow_items_for(reopened)[0]) == appearance
    last = tmp_path / "reopened.png"
    reopened.services.document.canvas_document_session_service.export_figure(
        str(last), fmt="png", dpi=120, scope="sheet"
    )
    assert _pixels(first) == _pixels(last)
    assert path.read_bytes() == saved_bytes


def test_shown_window_text_preset_nudge_undo_and_reopen_agree(app, tmp_path):
    window = build_main_window()
    window.resize(1050, 720)
    window.show()
    assert QTest.qWaitForWindowExposed(window, 5000)
    canvas = active_canvas_for_window(window)
    services = services_for_window(window)
    try:
        canvas.services.input.tool_mode_controller.set_tool("select")
        item = _arrow(canvas)
        history = canvas.services.history_service
        history.clear()
        original = _appearance(item)
        services.text_style_service.set_text_preset(window, "Paper Bold")
        assert all(child.font().pointSizeF() == 14 for child in _labels(item))
        appearance = _appearance(item)
        before = snapshot_canvas_state_for(canvas)
        QTest.keyClick(
            canvas.viewport(), Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier
        )
        assert snapshot_canvas_state_for(canvas) != before
        QTest.keyClick(
            canvas.viewport(), Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier
        )
        assert snapshot_canvas_state_for(canvas) == before
        assert _appearance(item) == appearance
        QTest.keyClick(
            canvas.viewport(), Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier
        )
        assert _appearance(item) == original
        redo = redo_action_for_window(window)
        assert redo is not None and redo.isEnabled()
        QTest.keySequence(canvas.viewport(), redo.shortcut())
        assert _appearance(item) == appearance
        path = tmp_path / "shown-labels.chemvas"
        session = canvas.services.document.canvas_document_session_service
        assert session.save_to_file(str(path)) == []
        session.apply_state(read_document(path).state)
        assert _appearance(arrow_items_for(canvas)[0]) == appearance
    finally:
        services.canvas_document_service.mark_clean(canvas)
        window.close()
        app.processEvents()


def test_font_default_changes_labels_but_not_existing_note_character_runs(canvases):
    canvas = canvases()
    item = _arrow(canvas)
    note = canvas.services.interaction.note_controller.create_text_note(
        QPointF(0, 100), "caption"
    )
    cursor = QTextCursor(note.document())
    cursor.select(QTextCursor.SelectionType.Document)
    form = QTextCharFormat()
    form.setFontPointSize(20)
    form.setFontFamilies(["DejaVu Sans"])
    cursor.mergeCharFormat(form)
    old_html, old_font = note.toHtml(), note.font()
    _style(canvas).set_text_font_family_default("DejaVu Serif")
    assert all(child.font().family() == "DejaVu Serif" for child in _labels(item))
    assert note.toHtml() == old_html
    assert note.font() == old_font
    _style(canvas).apply_text_preset_paper_bold()
    fragment = note.document().begin().begin().fragment().charFormat()
    assert fragment.fontPointSize() == 20
    assert fragment.fontFamilies() == ["DejaVu Sans"]


def test_note_appearance_and_unchanged_font_do_not_rebuild_labels_or_discard_redo(
    canvases,
):
    canvas = canvases()
    item = _arrow(canvas)
    history = canvas.services.history_service
    _style(canvas).set_note_appearance({"note_padding": 9.0})
    history.undo()
    stack = history.capture_stack_snapshot()
    children = _labels(item)
    _style(canvas).set_text_font_family_default("Arial")
    assert _labels(item) == children
    history.verify_stack_snapshot(stack)
    _style(canvas).set_note_appearance({"note_padding": 10.0})
    assert _labels(item) == children


@pytest.mark.parametrize("phase", ["apply", "undo", "redo", "push"])
def test_partial_label_rebuild_failure_restores_exact_scene_and_history(
    canvases, monkeypatch, phase
):
    from chemvas.ui.canvas_arrow_build_service import CanvasArrowBuildService

    canvas = canvases()
    first = _arrow(canvas)
    second = _arrow(canvas, kind="curved_single", color="#a52277")
    history = canvas.services.history_service
    history.clear()
    if phase in {"undo", "redo"}:
        _style(canvas).apply_text_preset_paper_bold()
        if phase == "redo":
            history.undo()
    before = snapshot_canvas_state_for(canvas)
    appearances = [_appearance(item) for item in (first, second)]
    children = [_labels(item) for item in (first, second)]
    stack = history.capture_stack_snapshot()
    original = CanvasArrowBuildService.apply_arrow_labels
    calls = 0

    def fail_on_second(builder, item, labels):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("label rebuild failed")
        return original(builder, item, labels)

    with monkeypatch.context() as patch:
        if phase == "push":
            patch.setattr(history, "push", lambda _command: False)
        else:
            patch.setattr(CanvasArrowBuildService, "apply_arrow_labels", fail_on_second)
        with pytest.raises(RuntimeError):
            if phase in {"undo", "redo"}:
                getattr(history, phase)()
            else:
                _style(canvas).apply_text_preset_paper_bold()
    assert snapshot_canvas_state_for(canvas) == before
    assert [_appearance(item) for item in (first, second)] == appearances
    assert [_labels(item) for item in (first, second)] == children
    history.verify_stack_snapshot(stack)
    if phase in {"undo", "redo"}:
        getattr(history, phase)()
    else:
        _style(canvas).apply_text_preset_paper_bold()
