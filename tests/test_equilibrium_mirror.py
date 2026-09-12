"""Equilibrium flips preserve the drawn harpoons and readable label pairing."""

import json
import os
from copy import deepcopy
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QImage, QTransform
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.main_window import build_main_window
from chemvas.core.document_io import read_document, write_document
from chemvas.core.svg_roundtrip import extract_chemvas_document_from_svg
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    build_document_payload,
    extract_document_state,
    validate_clipboard_selection_payload,
)
from chemvas.ui.canvas_document_metadata_state import (
    document_is_dirty_for,
    mark_document_clean_for,
)
from chemvas.ui.canvas_scene_items_state import arrow_items_for
from chemvas.ui.canvas_service_ports import arrow_build_service_for_access
from chemvas.ui.canvas_window_access import (
    restore_canvas_state_for,
    set_error_callback_for,
    snapshot_canvas_state_for,
)
from chemvas.ui.main_window_ports import active_canvas_for_window, services_for_window
from chemvas.ui.move_access import move_item_for
from chemvas.ui.scene_decoration_access import add_arrow_for
from chemvas.ui.scene_flip_geometry import flip_center_for_selection
from chemvas.ui.scene_item_access import (
    apply_scene_item_state,
    restore_arrow_from_state,
)
from chemvas.ui.scene_item_state import scene_item_state_for
from tests.canvas_factory import build_canvas_view

KINDS = ("equilibrium", "equilibrium_forward", "equilibrium_reverse")


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvases(app):
    opened = []

    def create():
        view = build_canvas_view()
        view.services.input.tool_mode_controller.set_tool("select")
        opened.append(view)
        return view

    yield create
    for view in reversed(opened):
        view.services.document.canvas_scene_reset_service.clear_scene()
        view.close()
        view.deleteLater()
    app.processEvents()


@pytest.fixture
def canvas(canvases):
    return canvases()


def _segments(path):
    """Independent undirected shaft/barb line oracle, ignoring path ordering."""
    result = []
    last = None
    for index in range(path.elementCount()):
        element = path.elementAt(index)
        point = (round(element.x, 8), round(element.y, 8))
        if element.isLineTo():
            result.append(tuple(sorted((last, point))))
        last = point
    return sorted(result)


def _labels(item):
    return {
        child.toPlainText(): child.sceneBoundingRect().center()
        for child in item.childItems()
        if child.data(0) == "arrow_label"
    }


def _arrow(canvas, kind, end=(60, 0)):
    item = add_arrow_for(canvas, QPointF(-end[0], -end[1]), QPointF(*end), kind)
    state = scene_item_state_for(canvas, item)
    state["labels"] = {"above": "k_1", "below": "k_-1"}
    state["color"] = "#Ab2374"
    apply_scene_item_state(canvas, item, state)
    move_item_for(canvas, item, 23.75, 41.5)
    item.setSelected(True)
    canvas.services.history_service.clear()
    return item


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("end", [(60, 0), (0, 60), (52, 30)])
@pytest.mark.parametrize("horizontal", [True, False])
def test_flip_matches_path_mirror_and_readable_label_centres(
    canvas, kind, end, horizontal
):
    item = _arrow(canvas, kind, end)
    controller = canvas.services.scene_operations.scene_transform_controller
    center = flip_center_for_selection(
        set(), [item], atoms={}, flip_bounds_getter=controller._flip_bounds_for_item
    )
    transform = QTransform()
    transform.translate(center.x(), center.y())
    transform.scale(-1 if horizontal else 1, 1 if horizontal else -1)
    transform.translate(-center.x(), -center.y())
    before = snapshot_canvas_state_for(canvas)
    original_path = item.mapToScene(item.path())
    original_labels = _labels(item)
    controller.flip_selected_items(horizontal)
    assert _segments(item.mapToScene(item.path())) == _segments(
        transform.map(original_path)
    )
    assert scene_item_state_for(canvas, item)["mirrored"] is True
    assert item.pen().color().name() == "#ab2374"
    for text, position in _labels(item).items():
        expected = transform.map(original_labels[text])
        assert (position.x(), position.y()) == pytest.approx(
            (expected.x(), expected.y()), abs=1e-10
        )
    for child in item.childItems():
        if child.data(0) == "arrow_label":
            assert child.rotation() == 0
            assert child.transform().isIdentity()
    after = snapshot_canvas_state_for(canvas)
    assert len(canvas.services.history_service.state.history) == 1
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    canvas.services.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == after
    controller.flip_selected_items(horizontal)
    assert snapshot_canvas_state_for(canvas) == before


@pytest.mark.parametrize("kind", KINDS)
def test_mirror_survives_native_and_clipboard_roundtrip_with_same_ink(
    canvases, kind, tmp_path
):
    canvas = canvases()
    item = _arrow(canvas, kind)
    canvas.services.scene_operations.scene_transform_controller.flip_selected_items(
        False
    )
    state = snapshot_canvas_state_for(canvas)
    document = tmp_path / "equilibrium.chemvas"
    write_document(document, state, version=CANVAS_FILE_VERSION)
    serialized = json.loads(document.read_text())
    assert serialized["version"] == CANVAS_FILE_VERSION == 7
    assert serialized["state"]["arrows"][0]["mirrored"] is True
    before_bytes = document.read_bytes()
    restored = canvases()
    restore_canvas_state_for(restored, read_document(document).state)
    assert snapshot_canvas_state_for(restored) == state
    rebuilt = arrow_items_for(restored)[0]
    assert _segments(rebuilt.mapToScene(rebuilt.path())) == _segments(
        item.mapToScene(item.path())
    )
    assert _labels(rebuilt) == _labels(item)
    for view, name in ((canvas, "live"), (restored, "restored")):
        view.services.document.canvas_document_session_service.export_figure(
            str(tmp_path / f"{name}.png"), fmt="png"
        )
    svg = tmp_path / "editable.svg"
    canvas.services.document.canvas_document_session_service.export_figure(
        str(svg), fmt="svg", editable_svg=True
    )
    svg_canvas = canvases()
    restore_canvas_state_for(svg_canvas, extract_chemvas_document_from_svg(svg).state)
    assert snapshot_canvas_state_for(svg_canvas) == state
    assert _segments(arrow_items_for(svg_canvas)[0].path()) == _segments(
        item.mapToScene(item.path())
    )
    assert QImage(str(tmp_path / "live.png")) == QImage(str(tmp_path / "restored.png"))
    assert not QImage(str(tmp_path / "live.png")).isNull()
    payload = canvas.services.scene_operations.scene_clipboard_controller.selection_payload_for_clipboard()
    assert validate_clipboard_selection_payload(payload)
    assert payload["version"] == 2
    assert payload["scene_items"][0]["mirrored"] is True
    target = canvases()
    clip = target.services.scene_operations.scene_clipboard_controller
    assert clip.paste_selection_from_clipboard(
        payload_provider=lambda: (payload, json.dumps(payload))
    )
    pasted = arrow_items_for(target)[0]
    pasted_state = scene_item_state_for(target, pasted)
    for key in ("kind", "mirrored", "labels", "color"):
        assert pasted_state[key] == state["arrows"][0][key]
    pasted_after = snapshot_canvas_state_for(target)
    target.services.history_service.undo()
    assert not arrow_items_for(target)
    target.services.history_service.redo()
    assert snapshot_canvas_state_for(target) == pasted_after
    assert document.read_bytes() == before_bytes
    assert snapshot_canvas_state_for(canvas) == state


@pytest.mark.parametrize("kind", KINDS)
def test_endpoint_and_rotation_rebuilds_keep_mirrored_ink(canvas, kind):
    item = _arrow(canvas, kind)
    controller = canvas.services.scene_operations.scene_transform_controller
    controller.flip_selected_items(True)
    canvas.services.handles.handle_mutation_service.update_arrow_endpoint(
        item, QPointF(90, 80), "end"
    )
    state = scene_item_state_for(canvas, item)
    assert state["mirrored"] is True
    # Compare against an independently reflected unmirrored chord: the builder
    # must not merely retain metadata while repainting its original handedness.
    start, end = QPointF(*state["start"]), QPointF(*state["end"])
    plain = arrow_build_service_for_access(canvas).build_arrow_item(
        QPointF(start.x(), -start.y()), QPointF(end.x(), -end.y()), kind
    )
    expected = QTransform().scale(1, -1).map(plain.path())
    assert _segments(item.mapToScene(item.path())) == _segments(expected)
    before = snapshot_canvas_state_for(canvas)
    controller.rotate_selected_items(30)
    assert scene_item_state_for(canvas, item)["mirrored"] is True
    after = snapshot_canvas_state_for(canvas)
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    canvas.services.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize("value", [None, 0, 1, "true", [], {}])
def test_mirrored_requires_real_boolean_at_native_and_clipboard_boundaries(
    canvas, value
):
    _arrow(canvas, "equilibrium")
    state = snapshot_canvas_state_for(canvas)
    state["arrows"][0]["mirrored"] = value
    with pytest.raises(ValueError, match="mirrored"):
        extract_document_state(build_document_payload(state, CANVAS_FILE_VERSION))
    payload = canvas.services.scene_operations.scene_clipboard_controller.selection_payload_for_clipboard()
    payload["scene_items"][0]["mirrored"] = value
    assert not validate_clipboard_selection_payload(payload)


@pytest.mark.parametrize("kind", ["arrow", "resonance", "arc_90_left", "line"])
@pytest.mark.parametrize("value", [False, True])
def test_mirrored_is_not_a_generic_arrow_transform(canvas, kind, value):
    _arrow(canvas, kind)
    state = snapshot_canvas_state_for(canvas)
    state["arrows"][0]["mirrored"] = value
    with pytest.raises(ValueError, match="mirrored"):
        extract_document_state(build_document_payload(state, CANVAS_FILE_VERSION))


def test_old_default_is_unchanged_and_explicit_false_writes_canonically(canvas):
    item = _arrow(canvas, "equilibrium")
    before = snapshot_canvas_state_for(canvas)
    assert "mirrored" not in before["arrows"][0]
    with_false = deepcopy(before)
    with_false["arrows"][0]["mirrored"] = False
    extract_document_state(build_document_payload(with_false, CANVAS_FILE_VERSION))
    apply_scene_item_state(canvas, item, with_false["arrows"][0])
    assert snapshot_canvas_state_for(canvas) == before


@pytest.mark.parametrize("phase", ["flip", "undo", "redo"])
def test_failed_second_arrow_rebuild_rolls_back_same_history_owner(
    canvas, monkeypatch, phase
):
    first = _arrow(canvas, "equilibrium_forward")
    second = _arrow(canvas, "equilibrium_reverse", (0, 60))
    first.setSelected(True)
    second.setSelected(True)
    controller = canvas.services.scene_operations.scene_transform_controller
    history = canvas.services.history_service
    if phase != "flip":
        controller.flip_selected_items(True)
    if phase == "redo":
        history.undo()
    before = snapshot_canvas_state_for(canvas)
    stacks = (tuple(history.state.history), tuple(history.state.redo_stack))
    paths = [_segments(item.mapToScene(item.path())) for item in (first, second)]
    builder = arrow_build_service_for_access(canvas)
    original = builder.build_arrow_item
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second equilibrium rebuild failed")
        return original(*args, **kwargs)

    monkeypatch.setattr(builder, "build_arrow_item", fail_once)
    action = (
        (lambda: controller.flip_selected_items(True))
        if phase == "flip"
        else getattr(history, phase)
    )
    with pytest.raises(RuntimeError, match="second equilibrium"):
        action()
    assert snapshot_canvas_state_for(canvas) == before
    assert (tuple(history.state.history), tuple(history.state.redo_stack)) == stacks
    assert [
        _segments(item.mapToScene(item.path())) for item in (first, second)
    ] == paths
    action()
    assert snapshot_canvas_state_for(canvas) != before


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("horizontal", [True, False])
def test_shown_window_flip_menu_undo_save_reopen(app, kind, horizontal, tmp_path):
    window = build_main_window()
    window.resize(1050, 720)
    window.show()
    assert QTest.qWaitForWindowExposed(window, 5000)
    canvas = active_canvas_for_window(window)
    services = services_for_window(window)
    try:
        canvas.services.input.tool_mode_controller.set_tool("select")
        item = _arrow(canvas, kind, (52, 30))
        before = snapshot_canvas_state_for(canvas)
        edit = next(
            action
            for action in window.menuBar().actions()
            if action.text().replace("&", "") == "Edit"
        )
        QTest.mouseClick(
            window.menuBar(),
            Qt.MouseButton.LeftButton,
            pos=window.menuBar().actionGeometry(edit).center(),
        )
        menu = edit.menu()
        action = next(
            action
            for action in menu.actions()
            if action.text() == ("Flip Horizontal" if horizontal else "Flip Vertical")
        )
        assert action.isEnabled()
        QTest.mouseClick(
            menu, Qt.MouseButton.LeftButton, pos=menu.actionGeometry(action).center()
        )
        app.processEvents()
        assert scene_item_state_for(canvas, item)["mirrored"] is True
        after = snapshot_canvas_state_for(canvas)
        assert len(canvas.services.history_service.state.history) == 1
        QTest.keyClick(
            canvas.viewport(), Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier
        )
        assert snapshot_canvas_state_for(canvas) == before
        canvas.services.history_service.redo()
        assert snapshot_canvas_state_for(canvas) == after
        session = canvas.services.document.canvas_document_session_service
        path = tmp_path / "menu-mirrored.chemvas"
        session.save_to_file(str(path))
        session.apply_state(read_document(path).state)
        assert snapshot_canvas_state_for(canvas) == after
        assert (
            scene_item_state_for(canvas, arrow_items_for(canvas)[0])["mirrored"] is True
        )
    finally:
        services.canvas_document_service.mark_clean(canvas)
        window.close()
        app.processEvents()


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("horizontal", [True, False])
def test_zero_chord_refuses_whole_flip_without_repairing_native_input(
    canvas, kind, horizontal
):
    item = _arrow(canvas, "equilibrium_forward")
    point_arrow = restore_arrow_from_state(
        canvas, {"kind": kind, "start": (10, 20), "end": (10, 20)}
    )
    point_arrow.setSelected(True)
    item.setSelected(True)
    canvas.services.history_service.clear()
    before = snapshot_canvas_state_for(canvas)
    extract_document_state(build_document_payload(before, CANVAS_FILE_VERSION))
    mark_document_clean_for(canvas, before)
    assert not document_is_dirty_for(canvas, before)
    notice = Mock()
    set_error_callback_for(canvas, notice)
    canvas.services.scene_operations.scene_transform_controller.flip_selected_items(
        horizontal
    )
    assert snapshot_canvas_state_for(canvas) == before
    assert not document_is_dirty_for(canvas, snapshot_canvas_state_for(canvas))
    assert canvas.services.history_service.state.history == []
    assert canvas.services.history_service.state.redo_stack == []
    notice.assert_called_once()
    assert "zero-length equilibrium" in notice.call_args.args[0]
    assert "endpoint" in notice.call_args.args[0]
