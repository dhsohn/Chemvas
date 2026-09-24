import json

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from chemvas.adapters.qt.renderer import Renderer
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    VALID_ARROW_KINDS,
    build_document_payload,
    extract_document_state,
    serialize_settings,
)
from chemvas.ui.annotations.state import arrow_state_dict_for
from chemvas.ui.canvas.canvas_note_controller import CanvasNoteController
from chemvas.ui.canvas.canvas_scene_items_state import (
    arrow_items_for,
    require_scene_record_id,
)
from chemvas.ui.canvas.canvas_view import CanvasView


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    yield application


@pytest.fixture
def canvas(app):
    view = CanvasView(renderer=Renderer())
    yield view
    view.close()
    view.deleteLater()
    app.processEvents()


def _arrow(kind="arrow", **extra):
    state = {"kind": kind, "start": [0.0, 0.0], "end": [80.0, 0.0]}
    if kind in {"curved_single", "curved_double"}:
        state.update(control=[40.0, -30.0], double=kind == "curved_double")
    return {**state, **extra}


def _document(arrows):
    return {
        "model": {"atoms": {}, "bonds": [], "next_atom_id": 0},
        "ring_fills": [],
        "notes": [],
        "marks": [],
        "arrows": arrows,
        "ts_brackets": [],
        "shapes": [],
        "orbitals": [],
        "settings": serialize_settings(
            bond_length_px=20.0,
            arrow_line_width=1.5,
            arrow_head_scale=0.3,
            orbital_phase_enabled=False,
            text_font_size=12,
            text_font_weight=400,
            text_italic=False,
            sheet_size="A4",
            sheet_orientation="portrait",
        ),
        "last_smiles_input": None,
    }


@pytest.mark.parametrize("kind", sorted(VALID_ARROW_KINDS))
@pytest.mark.parametrize("color", ["#aBc", "#A1b2C3"])
def test_v7_arrow_color_round_trips_as_optional_hex(kind, color):
    state = _document([_arrow(kind, color=color), _arrow(kind)])
    payload = build_document_payload(state, 7)
    restored = extract_document_state(json.loads(json.dumps(payload)))
    assert payload["version"] == 7
    assert restored["arrows"] == state["arrows"]


@pytest.mark.parametrize("kind", sorted(VALID_ARROW_KINDS))
def test_native_document_restore_preserves_arrow_color_and_pen_style(canvas, kind):
    canvas.services.canvas_document_session_service.restore_state(
        _document([_arrow(kind)])
    )
    (default,) = arrow_items_for(canvas)
    default_pen = default.pen()
    default_path = default.path()
    assert "color" not in arrow_state_dict_for(canvas, default)

    canvas.services.canvas_document_session_service.restore_state(
        _document([_arrow(kind, color="#A1b2C3")])
    )
    (colored,) = arrow_items_for(canvas)
    expected_pen = default_pen
    expected_pen.setColor(QColor("#A1b2C3"))
    assert colored.pen() == expected_pen
    assert colored.path() == default_path
    snapshot = canvas.services.canvas_document_session_service.snapshot_state()
    assert snapshot["arrows"][0]["color"] == "#A1b2C3"
    payload = json.loads(
        json.dumps(build_document_payload(snapshot, CANVAS_FILE_VERSION))
    )
    canvas.services.canvas_document_session_service.restore_state(
        extract_document_state(payload)
    )
    (restored,) = arrow_items_for(canvas)
    assert restored.pen() == expected_pen
    assert arrow_state_dict_for(canvas, restored)["color"] == "#A1b2C3"


@pytest.mark.parametrize(
    "kind", ["arrow", "equilibrium", "curved_single", "curved_double", "dotted"]
)
def test_arrow_labels_render_in_explicit_color_but_keep_default_text_style(
    canvas, kind
):
    from chemvas.ui.export.export_render_service import render_scene_to_svg_bytes
    from chemvas.ui.export.export_scope import collect_export_items, content_bounds

    state = _document([_arrow(kind, labels={"above": "k_{1}", "below": "fast"})])
    state["settings"]["text_color"] = "#654321"
    canvas.services.canvas_document_session_service.restore_state(state)
    (default,) = arrow_items_for(canvas)
    assert all(
        child.defaultTextColor() == QColor("#654321") for child in default.childItems()
    )

    state["arrows"][0]["color"] = "#A1b"
    canvas.services.canvas_document_session_service.restore_state(state)
    (colored,) = arrow_items_for(canvas)
    assert len(colored.childItems()) == 2
    assert all(
        child.defaultTextColor() == QColor("#A1b") for child in colored.childItems()
    )
    source = content_bounds(collect_export_items(canvas.scene())).adjusted(-4, -4, 4, 4)
    svg = render_scene_to_svg_bytes(canvas.scene(), source=source, items=[colored])
    assert b'stroke="#aa11bb"' in svg
    assert b'fill="#aa11bb"' in svg
    assert b"<text" not in svg


@pytest.mark.parametrize("kind", sorted(VALID_ARROW_KINDS))
def test_arrow_state_edit_and_history_restore_color_including_default(canvas, kind):
    operations = canvas.services.history_service.operations
    from chemvas.ui.history.history_commands import UpdateSceneItemCommand

    canvas.services.canvas_document_session_service.restore_state(
        _document([_arrow(kind, labels={"above": "k_1"})])
    )
    (item,) = arrow_items_for(canvas)
    default_pen = item.pen()
    default_label_color = item.childItems()[0].defaultTextColor()
    before = arrow_state_dict_for(canvas, item)
    after = {**before, "end": (100.0, 20.0), "color": "#123abc"}
    command = UpdateSceneItemCommand(require_scene_record_id(item), before, after)
    command.redo(operations)
    assert arrow_state_dict_for(canvas, item) == after
    assert item.pen().color() == QColor("#123abc")
    assert item.childItems()[0].defaultTextColor() == QColor("#123abc")
    history = canvas.runtime_state.history_service
    history.push(command)
    history.undo()
    assert arrow_state_dict_for(canvas, item) == before
    assert item.pen() == default_pen
    assert item.childItems()[0].defaultTextColor() == default_label_color
    history.redo()
    assert arrow_state_dict_for(canvas, item) == after
    assert item.pen().color() == QColor("#123abc")
    assert item.childItems()[0].defaultTextColor() == QColor("#123abc")


@pytest.mark.parametrize("kind", sorted(VALID_ARROW_KINDS))
def test_arrow_handle_edit_preserves_color_and_labels(canvas, kind):

    canvas.services.canvas_document_session_service.restore_state(
        _document([_arrow(kind, color="#2468ac", labels={"above": "k_1"})])
    )
    (item,) = arrow_items_for(canvas)
    pen = item.pen()
    canvas.services.move_controller.move_item(item, 10.0, 20.0)
    handles = canvas.services.handle_mutation_service
    if kind in {"curved_single", "curved_double"}:
        handles.update_curved_control(item, QPointF(40.0, -50.0))
        handles.update_arrow_endpoint(item, QPointF(110.0, 25.0), "end")
    else:
        handles.update_arrow_endpoint(item, QPointF(110.0, 25.0), "end")
    assert item.pen() == pen
    state = arrow_state_dict_for(canvas, item)
    assert state["end"] != (90.0, 20.0)
    assert state["color"] == "#2468ac"
    assert state["labels"] == {"above": "k_1"}
    assert item.childItems()[0].defaultTextColor() == QColor("#2468ac")
    assert item.pos() == QPointF()


@pytest.mark.parametrize("kind", sorted(VALID_ARROW_KINDS))
def test_color_operation_recolors_arrows_with_one_undo_step(canvas, kind):
    from chemvas.ui.canvas.canvas_color_mutation_service import (
        CanvasColorMutationService,
    )

    canvas.services.canvas_document_session_service.restore_state(
        _document(
            [
                _arrow(kind, labels={"above": "k_1"}),
                _arrow(kind, start=[0.0, 70.0], end=[80.0, 70.0], color="#f80"),
            ]
        )
    )
    items = list(arrow_items_for(canvas))
    before = [arrow_state_dict_for(canvas, item) for item in items]
    pens = [item.pen() for item in items]
    history = canvas.runtime_state.history_service
    colors = CanvasColorMutationService(
        canvas,
        note_controller=CanvasNoteController(canvas),
        graph_service=canvas.services.graph_service,
        history_service=history,
    )
    colors.apply_color_to_items(items, QColor("#135ace"))
    assert all(
        arrow_state_dict_for(canvas, item).get("color") == "#135ace" for item in items
    )
    assert all(item.pen().color() == QColor("#135ace") for item in items)
    assert items[0].childItems()[0].defaultTextColor() == QColor("#135ace")
    history.undo()
    assert [arrow_state_dict_for(canvas, item) for item in items] == before
    assert [item.pen() for item in items] == pens
    history.redo()
    assert all(item.pen().color() == QColor("#135ace") for item in items)


def test_existing_palette_recolors_selected_arrow(app):
    from chemvas.bootstrap.main_window import build_main_window
    from chemvas.ui.window.main_window_ports import active_canvas_for_window

    window = build_main_window()
    view = active_canvas_for_window(window)
    services = window.services
    try:
        view.services.canvas_document_session_service.restore_state(
            _document([_arrow("equilibrium", labels={"above": "k_1"})])
        )
        (item,) = arrow_items_for(view)
        item.setSelected(True)
        services.tool_routing_service.apply_color_preset(window, "#123abc")
        app.processEvents()
        assert item.pen().color() == QColor("#123abc")
        assert item.childItems()[0].defaultTextColor() == QColor("#123abc")
        view.runtime_state.history_service.undo()
        assert "color" not in arrow_state_dict_for(view, item)
    finally:
        services.canvas_document_service.mark_clean(view)
        window.close()
        window.deleteLater()
        app.processEvents()


def test_color_tool_empty_space_click_recolors_selected_arrow(canvas):
    from types import SimpleNamespace

    from chemvas.ui.canvas.canvas_color_mutation_service import (
        CanvasColorMutationService,
    )
    from chemvas.ui.tools.edit_tools import ColorTool

    canvas.services.canvas_document_session_service.restore_state(
        _document([_arrow("dotted")])
    )
    (item,) = arrow_items_for(canvas)
    item.setSelected(True)
    colors = CanvasColorMutationService(
        canvas,
        note_controller=CanvasNoteController(canvas),
        graph_service=canvas.services.graph_service,
        history_service=canvas.runtime_state.history_service,
    )
    tool = ColorTool(
        canvas,
        context=SimpleNamespace(
            item_at_event=lambda event: None,
            selected_scene_items=lambda **kwargs: canvas.scene().selectedItems(),
            apply_color_to_items=colors.apply_color_to_items,
        ),
    )
    tool.set_color("#abc123")
    assert tool.on_mouse_press(
        SimpleNamespace(button=lambda: Qt.MouseButton.LeftButton)
    )
    assert item.pen().color() == QColor("#abc123")
    assert item.pen().style() == Qt.PenStyle.DashLine


@pytest.mark.parametrize("kind", sorted(VALID_ARROW_KINDS))
def test_native_clipboard_copy_paste_round_trips_colored_arrow(canvas, kind):
    from chemvas.domain.document import validate_clipboard_selection_payload
    from chemvas.ui.scene.scene_clipboard_controller import SceneClipboardController

    canvas.services.canvas_document_session_service.restore_state(
        _document([_arrow(kind, color="#bCd", labels={"above": "k_1"})])
    )
    (item,) = arrow_items_for(canvas)
    item.setSelected(True)
    clipboard = SceneClipboardController(canvas)
    assert clipboard.copy_selection_to_clipboard()
    payload, _ = clipboard.clipboard_selection_payload()
    assert validate_clipboard_selection_payload(payload)
    assert payload["scene_items"][0]["color"] == "#bCd"
    assert clipboard.paste_selection_from_clipboard()
    pasted = [arrow for arrow in arrow_items_for(canvas) if arrow is not item]
    assert len(pasted) == 1
    pasted = pasted[0]
    state = arrow_state_dict_for(canvas, pasted)
    assert state["color"] == "#bCd"
    assert state["labels"] == {"above": "k_1"}
    assert state["start"] != arrow_state_dict_for(canvas, item)["start"]
    assert pasted.pen() == item.pen()
    assert pasted.childItems()[0].defaultTextColor() == QColor("#bCd")
    history = canvas.runtime_state.history_service
    history.undo()
    assert list(arrow_items_for(canvas)) == [item]
    history.redo()
    assert pasted.scene() is canvas.scene()
    assert arrow_state_dict_for(canvas, pasted) == state
    assert pasted.pen().color() == QColor("#bCd")


@pytest.mark.parametrize("failure", ["history", "second_arrow"])
def test_failed_arrow_color_batch_restores_document(canvas, monkeypatch, failure):
    from chemvas.ui.canvas.canvas_color_mutation_service import (
        CanvasColorMutationService,
    )

    canvas.services.canvas_document_session_service.restore_state(
        _document(
            [
                _arrow("curved_double", labels={"above": "k_1"}),
                _arrow("dotted", start=[0.0, 70.0], end=[80.0, 70.0], color="#f80"),
            ]
        )
    )
    items = list(arrow_items_for(canvas))
    before = canvas.services.canvas_document_session_service.snapshot_state()
    pens = [item.pen() for item in items]
    paths = [item.path() for item in items]
    history = canvas.runtime_state.history_service
    colors = CanvasColorMutationService(
        canvas,
        note_controller=CanvasNoteController(canvas),
        graph_service=canvas.services.graph_service,
        history_service=history,
    )
    if failure == "history":

        def reject(command):
            raise RuntimeError("synthetic history failure")

        monkeypatch.setattr(history, "push", reject)
    else:
        set_pen = items[1].setPen

        def reject_once(pen):
            monkeypatch.setattr(items[1], "setPen", set_pen)
            set_pen(pen)
            raise RuntimeError("synthetic pen failure")

        monkeypatch.setattr(items[1], "setPen", reject_once)
    with pytest.raises(RuntimeError, match="synthetic"):
        colors.apply_color_to_items(items, QColor("#135ace"))
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    assert [item.pen() for item in items] == pens
    assert [item.path() for item in items] == paths
    assert items[0].childItems()[0].defaultTextColor() != QColor("#135ace")


@pytest.mark.parametrize(
    "color", [None, "red", "", "#1234", "#12345678", "#ggg", 4, [], {}]
)
def test_document_rejects_non_hex_arrow_color(color):
    with pytest.raises(ValueError, match="Invalid Chemvas file"):
        build_document_payload(_document([_arrow(color=color)]), CANVAS_FILE_VERSION)
