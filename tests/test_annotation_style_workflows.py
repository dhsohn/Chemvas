import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QGraphicsEllipseItem,
    QSlider,
    QToolButton,
)

from chemvas.bootstrap.main_window import build_main_window
from chemvas.core.document_io import read_document
from chemvas.ui.canvas_callback_state import callback_state_for
from chemvas.ui.canvas_scene_items_state import arrow_items_for, orbital_items_for
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.main_window_ports import active_canvas_for_window, services_for_window
from chemvas.ui.move_access import move_item_for
from chemvas.ui.note_appearance_dialog import NoteAppearanceDialog
from chemvas.ui.scene_decoration_access import add_arrow_for, add_orbital_for
from chemvas.ui.scene_item_access import apply_scene_item_state
from chemvas.ui.scene_item_state import scene_item_state_for
from chemvas.ui.sheet_setup_state import sheet_setup_state_for
from chemvas.ui.transactions.document import DocumentSavepoint


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def drawing(app):
    window = build_main_window()
    window.show()
    assert QTest.qWaitForWindowExposed(window, 5000)
    canvas = active_canvas_for_window(window)
    yield window, canvas, canvas_services_for(canvas).input.tool_mode_controller
    services_for_window(window).canvas_document_service.mark_clean(canvas)
    window.close()
    app.processEvents()


@pytest.mark.parametrize(
    "kind", ["reaction", "curved_single", "curved_double", "equilibrium", "line"]
)
def test_document_arrow_style_restyles_existing_items_and_undo(drawing, kind):
    _window, canvas, controller = drawing
    item = add_arrow_for(canvas, QPointF(-60, 0), QPointF(60, 0), kind)
    before_state = scene_item_state_for(canvas, item)
    before_path, before_pen = item.path(), item.pen()
    history = canvas_services_for(canvas).history_service
    before_count = len(history.state.history)
    controller.set_arrow_line_width(4.2)
    assert item.pen().widthF() == pytest.approx(4.2)
    assert scene_item_state_for(canvas, item) == before_state
    assert len(history.state.history) == before_count + 1
    history.undo()
    assert item.path() == before_path
    assert item.pen() == before_pen
    history.redo()
    assert item.pen().widthF() == pytest.approx(4.2)
    controller.set_arrow_head_scale(0.6)
    state = canvas_services_for(
        canvas
    ).document.canvas_document_session_service.snapshot_state()
    expected = [(i.path(), i.pen()) for i in arrow_items_for(canvas)]
    canvas_services_for(canvas).document.canvas_document_session_service.apply_state(
        state
    )
    assert [(i.path(), i.pen()) for i in arrow_items_for(canvas)] == expected


@pytest.mark.parametrize("kind", ["p", "mo_bonding", "mo_antibonding"])
def test_orbital_phase_restyles_live_lobes_and_survives_undo(drawing, kind):
    _window, canvas, controller = drawing
    controller.set_orbital_type(kind)
    item = add_orbital_for(canvas, QPointF(0, 0))
    children = item.childItems()
    lobes = [child for child in children if isinstance(child, QGraphicsEllipseItem)]
    assert all(child.brush().style() == Qt.BrushStyle.NoBrush for child in lobes)
    before = scene_item_state_for(canvas, item)
    controller.set_orbital_phase_enabled(True)
    assert all(child.brush().style() == Qt.BrushStyle.SolidPattern for child in lobes)
    assert item.childItems() == children
    assert scene_item_state_for(canvas, item) == before
    history = canvas_services_for(canvas).history_service
    history.undo()
    assert all(child.brush().style() == Qt.BrushStyle.NoBrush for child in lobes)
    history.redo()
    brushes = [child.brush() for child in lobes]
    session = canvas_services_for(canvas).document.canvas_document_session_service
    session.apply_state(session.snapshot_state())
    assert [
        child.brush()
        for child in orbital_items_for(canvas)[0].childItems()
        if isinstance(child, QGraphicsEllipseItem)
    ] == brushes


def _slider(window, tooltip):
    button = next(
        button
        for button in window.findChildren(QToolButton)
        if button.toolTip() == tooltip
    )
    return button.menu().findChild(QSlider)


def test_arrow_presets_sliders_and_open_reflect_document_settings(drawing):
    window, canvas, controller = drawing
    controller.set_tool("arrow")
    width, head = [
        _slider(window, label) for label in ("Arrow line width", "Arrow head size")
    ]
    assert width.value() == 15
    assert head.value() == 30
    for label, expected in (
        ("Bold", (22, 40)),
        ("Default", (15, 30)),
        ("Fine", (8, 25)),
    ):
        button = next(
            button
            for button in window.findChildren(QToolButton)
            if button.toolTip() == f"{label} arrow preset"
        )
        count = len(canvas_services_for(canvas).history_service.state.history)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert (width.value(), head.value()) == expected
        assert (
            len(canvas_services_for(canvas).history_service.state.history) == count + 1
        )
    services_for_window(window).tool_state_service.set_arrow_preset(window, "ACS")
    assert (width.value(), head.value()) == (12, 30)
    session = canvas_services_for(canvas).document.canvas_document_session_service
    state = session.snapshot_state()
    state["settings"]["arrow_line_width"] = 5.1
    state["settings"]["arrow_head_scale"] = 0.7
    session.apply_state(state)
    services_for_window(window).context_bar_service.refresh_window(window)
    assert (width.value(), head.value()) == (51, 70)
    width.setValue(width.value() + 1)
    assert tool_settings_state_for(canvas).arrow_line_width == pytest.approx(5.2)


def test_minimum_arrow_and_note_controls_save_and_reopen(drawing, app, tmp_path):
    window, canvas, controller = drawing
    controller.set_tool("arrow")
    add_arrow_for(canvas, QPointF(-60, 0), QPointF(60, 0), "reaction")
    head = _slider(window, "Arrow head size")
    QTest.keyClick(head, Qt.Key.Key_Home)
    assert head.value() == head.minimum() == 10
    completed = []

    def edit():
        dialog = app.activeModalWidget()
        try:
            assert isinstance(dialog, NoteAppearanceDialog)
            spacing = dialog.numbers["text_line_spacing"]
            spacing.setFocus()
            spacing.selectAll()
            QTest.keyClicks(spacing, "0.8")
            buttons = dialog.findChild(QDialogButtonBox)
            QTest.mouseClick(
                buttons.button(QDialogButtonBox.StandardButton.Ok),
                Qt.MouseButton.LeftButton,
            )
            completed.append(True)
        finally:
            if dialog is not None and dialog.isVisible():
                dialog.reject()

    QTimer.singleShot(0, edit)
    services_for_window(window).text_style_service.edit_note_appearance(window)
    assert completed == [True]
    session = canvas_services_for(canvas).document.canvas_document_session_service
    before = session.snapshot_state()
    assert before["settings"]["arrow_head_scale"] == 0.1
    assert before["settings"]["text_line_spacing"] == 0.8
    path = tmp_path / "minimum-controls.chemvas"
    assert session.save_to_file(str(path)) == []
    reopened = read_document(path)
    session.apply_state(reopened.state)
    assert session.snapshot_state() == before


@pytest.mark.parametrize("phase", ["edit", "push", "undo", "redo"])
def test_style_failure_keeps_exact_settings_items_and_history(
    drawing, monkeypatch, phase
):
    from chemvas.ui import annotation_style_service

    _window, canvas, controller = drawing
    items = [
        add_arrow_for(canvas, QPointF(-60, y), QPointF(60, y), "reaction")
        for y in (0, 30)
    ]
    history = canvas_services_for(canvas).history_service
    if phase in {"undo", "redo"}:
        controller.set_arrow_style(4.2, 0.6)
        if phase == "redo":
            history.undo()
    session = canvas_services_for(canvas).document.canvas_document_session_service
    before_state = session.snapshot_state()
    before_graphics = [(item.path(), item.pen(), item.pos()) for item in items]
    before_history, before_redo = (
        tuple(history.state.history),
        tuple(history.state.redo_stack),
    )
    original_apply = annotation_style_service.apply_scene_item_state

    def fail_after_mutating(*args):
        original_apply(*args)
        raise RuntimeError("style failure")

    if phase == "push":
        original_push = history.push

        def fail_after_push(command):
            original_push(command)
            raise RuntimeError("style failure")

        monkeypatch.setattr(history, "push", fail_after_push)
    else:
        monkeypatch.setattr(
            annotation_style_service, "apply_scene_item_state", fail_after_mutating
        )
    with pytest.raises(RuntimeError, match="style failure"):
        if phase in {"undo", "redo"}:
            getattr(history, phase)()
        else:
            controller.set_arrow_style(4.2, 0.6)
    assert session.snapshot_state() == before_state
    assert arrow_items_for(canvas) == items
    assert [(item.path(), item.pen(), item.pos()) for item in items] == before_graphics
    assert tuple(history.state.history) == before_history
    assert tuple(history.state.redo_stack) == before_redo


def test_unchanged_annotation_style_preserves_redo(drawing):
    _window, canvas, controller = drawing
    add_arrow_for(canvas, QPointF(0, 0), QPointF(60, 0), "reaction")
    history = canvas_services_for(canvas).history_service
    history.undo()
    redo = tuple(history.state.redo_stack)
    settings = tool_settings_state_for(canvas)
    controller.set_arrow_style(settings.arrow_line_width, settings.arrow_head_scale)
    controller.set_orbital_phase_enabled(settings.orbital_phase_enabled)
    assert not history.state.history
    assert tuple(history.state.redo_stack) == redo


@pytest.mark.parametrize("kind", ["arrow", "orbital"])
def test_refused_style_publication_restores_settings_graphics_and_stacks(
    drawing, monkeypatch, kind
):
    window, canvas, controller = drawing
    arrow = add_arrow_for(canvas, QPointF(0, 0), QPointF(60, 0), "reaction")
    controller.set_orbital_type("p")
    orbital = add_orbital_for(canvas, QPointF(100, 0))
    controller.set_tool("arrow")
    history = canvas_services_for(canvas).history_service
    controller.set_arrow_style(2.1, 0.4)
    history.undo()
    arrow.setSelected(True)
    session = canvas_services_for(canvas).document.canvas_document_session_service
    before_state = session.snapshot_state()
    scene_items = set(canvas.scene().items())
    selection = set(canvas.scene().selectedItems())
    before_graphics = arrow.path(), arrow.pen()
    lobes = [
        child
        for child in orbital.childItems()
        if isinstance(child, QGraphicsEllipseItem)
    ]
    before_brushes = [child.brush() for child in lobes]
    stacks = history.capture_stack_snapshot()
    width, head = [
        _slider(window, label) for label in ("Arrow line width", "Arrow head size")
    ]
    before_sliders = width.value(), head.value()
    with monkeypatch.context() as patcher:
        patcher.setattr(history, "push", lambda _command: False)
        with pytest.raises(RuntimeError, match="history push did not commit"):
            if kind == "arrow":
                controller.set_arrow_style(4.2, 0.6)
            else:
                controller.set_orbital_phase_enabled(True)
    assert session.snapshot_state() == before_state
    assert set(canvas.scene().items()) == scene_items
    assert set(canvas.scene().selectedItems()) == selection
    assert (arrow.path(), arrow.pen()) == before_graphics
    assert [child.brush() for child in lobes] == before_brushes
    history.verify_stack_snapshot(stacks)
    assert (width.value(), head.value()) == before_sliders
    if kind == "arrow":
        controller.set_arrow_style(4.2, 0.6)
    else:
        controller.set_orbital_phase_enabled(True)
    assert session.snapshot_state() != before_state
    history.undo()
    assert session.snapshot_state() == before_state


@pytest.mark.parametrize("phase", ["edit", "undo", "redo"])
def test_failed_style_callback_resyncs_restored_sliders_in_only_its_window(
    drawing, monkeypatch, phase
):
    window, canvas, controller = drawing
    controller.set_tool("arrow")
    add_arrow_for(canvas, QPointF(), QPointF(60, 0), "reaction")
    history = canvas_services_for(canvas).history_service
    if phase in {"undo", "redo"}:
        controller.set_arrow_style(4.2, 0.6)
        if phase == "redo":
            history.undo()
    other_window = build_main_window()
    other_canvas = active_canvas_for_window(other_window)
    try:
        other_controller = canvas_services_for(other_canvas).input.tool_mode_controller
        other_controller.set_tool("arrow")
        other_controller.set_arrow_style(3.3, 0.55)
        sliders = [
            _slider(target, label)
            for target in (window, other_window)
            for label in ("Arrow line width", "Arrow head size")
        ]
        before_sliders = [slider.value() for slider in sliders]
        assert before_sliders[2:] == [33, 55]
        session = canvas_services_for(canvas).document.canvas_document_session_service
        before_state = session.snapshot_state()
        stacks = history.capture_stack_snapshot()
        original_callback = callback_state_for(canvas).tool_change
        assert original_callback is not None
        failure = RuntimeError("style callback failed after reflecting changed values")

        def fail_after_reflection():
            original_callback()
            raise failure

        monkeypatch.setattr(
            callback_state_for(canvas), "tool_change", fail_after_reflection
        )
        with pytest.raises(RuntimeError) as caught:
            if phase == "edit":
                controller.set_arrow_style(4.2, 0.6)
            else:
                getattr(history, phase)()
        assert caught.value is failure
        assert session.snapshot_state() == before_state
        history.verify_stack_snapshot(stacks)
        assert [slider.value() for slider in sliders] == before_sliders
    finally:
        services_for_window(other_window).canvas_document_service.mark_clean(
            other_canvas
        )
        other_window.close()


def test_style_change_preserves_moved_arrow_labels_colors_and_orbital_transform(
    drawing,
):
    _window, canvas, controller = drawing
    arrow = add_arrow_for(canvas, QPointF(0, 0), QPointF(60, 0), "dotted")
    state = scene_item_state_for(canvas, arrow)
    state.update(color="#195b90", labels={"above": "H2O", "below": "25 C"})
    apply_scene_item_state(canvas, arrow, state)
    move_item_for(canvas, arrow, 35, 45)
    arrow.setSelected(True)
    before_arrow = scene_item_state_for(canvas, arrow)
    controller.set_arrow_style(3.1, 0.5)
    assert scene_item_state_for(canvas, arrow) == before_arrow
    assert arrow.isSelected()
    assert arrow.pen().color().name() == "#195b90"
    assert arrow.pen().style() == Qt.PenStyle.DashLine
    assert [
        child.toPlainText()
        for child in arrow.childItems()
        if child.data(0) == "arrow_label"
    ] == ["H2O", "25 C"]
    controller.set_orbital_type("p")
    orbital = add_orbital_for(canvas, QPointF(0, 0))
    move_item_for(canvas, orbital, 37, 63)
    orbital.setScale(1.8)
    orbital.setRotation(53)
    before_orbital = scene_item_state_for(canvas, orbital)
    before_bounds = orbital.sceneBoundingRect()
    controller.set_orbital_phase_enabled(True)
    assert scene_item_state_for(canvas, orbital) == before_orbital
    assert orbital.sceneBoundingRect() == before_bounds


def test_document_savepoint_restores_sheet_and_annotation_settings(drawing):
    _window, canvas, _controller = drawing
    settings = tool_settings_state_for(canvas)
    sheet = sheet_setup_state_for(canvas)
    expected = (
        settings.arrow_line_width,
        settings.arrow_head_scale,
        settings.orbital_phase_enabled,
        sheet.size_name,
        sheet.orientation,
        sheet.rect,
    )
    snapshot = DocumentSavepoint.capture(canvas)
    settings.arrow_line_width, settings.arrow_head_scale = 5.1, 0.7
    settings.orbital_phase_enabled = True
    sheet.size_name, sheet.orientation = "A3", "Landscape"
    sheet.rect = sheet.rect.adjusted(-100, -50, 80, 40)
    result = snapshot.restore()
    assert result.authoritative and not result.errors
    assert tool_settings_state_for(canvas) is settings
    assert sheet_setup_state_for(canvas) is sheet
    assert (
        settings.arrow_line_width,
        settings.arrow_head_scale,
        settings.orbital_phase_enabled,
        sheet.size_name,
        sheet.orientation,
        sheet.rect,
    ) == expected


@pytest.mark.parametrize(
    "width,slider_value", [(0.2, 2), (8.1, 81), (1e308, 2**31 - 1)]
)
def test_reflecting_loaded_arrow_width_never_overflows_or_writes_settings(
    drawing, width, slider_value
):
    window, canvas, controller = drawing
    settings = tool_settings_state_for(canvas)
    settings.arrow_line_width = width
    count = len(canvas_services_for(canvas).history_service.state.history)
    controller.set_tool("arrow")
    slider = _slider(window, "Arrow line width")
    assert slider.value() == slider_value
    assert slider.toolTip() == f"{width:g}"
    assert settings.arrow_line_width == width
    assert len(canvas_services_for(canvas).history_service.state.history) == count


@pytest.mark.parametrize("wide_width", [8.1, 1e8, 1e308])
def test_opening_normal_document_restores_default_arrow_slider_range(
    drawing, wide_width
):
    window, canvas, controller = drawing
    controller.set_tool("arrow")
    slider = _slider(window, "Arrow line width")
    changed_values = []
    slider.valueChanged.connect(changed_values.append)
    session = canvas_services_for(canvas).document.canvas_document_session_service
    documents = services_for_window(window).canvas_document_service
    state = session.snapshot_state()
    for width, maximum in (
        (wide_width, round(min(wide_width * 10, 2**31 - 1))),
        (1.5, 60),
        (wide_width, round(min(wide_width * 10, 2**31 - 1))),
    ):
        state["settings"]["arrow_line_width"] = width
        documents.open_state(window, state=state, file_path=None)
        services_for_window(window).context_bar_service.refresh_window(window)
        assert (slider.minimum(), slider.maximum()) == (5, maximum)
        assert slider.value() == round(min(width * 10, 2**31 - 1))
        assert slider.toolTip() == f"{width:g}"
        assert session.snapshot_state()["settings"]["arrow_line_width"] == width
        assert not canvas_services_for(canvas).history_service.state.history
        assert not changed_values


@pytest.mark.parametrize("wide_width", [8.1, 1e8])
def test_arrow_slider_range_tracks_actual_style_undo_and_redo(drawing, wide_width):
    window, canvas, controller = drawing
    controller.set_tool("arrow")
    slider = _slider(window, "Arrow line width")
    history = canvas_services_for(canvas).history_service
    controller.set_arrow_line_width(wide_width)
    assert slider.maximum() == round(wide_width * 10)
    changed_values = []
    slider.valueChanged.connect(changed_values.append)

    history.undo()
    assert (slider.minimum(), slider.maximum(), slider.value()) == (5, 60, 15)
    assert tool_settings_state_for(canvas).arrow_line_width == 1.5
    history.redo()
    assert slider.maximum() == round(wide_width * 10)
    assert tool_settings_state_for(canvas).arrow_line_width == wide_width
    services_for_window(window).tool_state_service.set_arrow_preset(window, "Default")
    assert (slider.minimum(), slider.maximum(), slider.value()) == (5, 60, 15)
    assert not changed_values
