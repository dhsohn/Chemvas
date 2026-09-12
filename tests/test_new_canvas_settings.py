from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.window_registry import open_new_window, open_windows
from chemvas.ui.canvas_document_metadata_state import document_file_path_for
from chemvas.ui.canvas_text_style_state import set_text_style_for, text_style_state_for
from chemvas.ui.canvas_tool_settings_state import set_tool_setting_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.main_window_ports import active_canvas_for_window, services_for_window
from chemvas.ui.renderer_style_access import set_bond_length_for
from chemvas.ui.sheet_setup_access import set_sheet_setup_for
from chemvas.ui.structure_mutation_access import add_atom_for


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def source(app):
    window = open_new_window()
    assert QTest.qWaitForWindowExposed(window, 5000)
    canvas = active_canvas_for_window(window)
    yield window, canvas
    for item in reversed(open_windows()):
        services_for_window(item).canvas_document_service.mark_clean(
            active_canvas_for_window(item)
        )
        item.close()
    app.processEvents()


def _customize(canvas):
    set_bond_length_for(canvas, 47.5)
    set_sheet_setup_for(canvas, "Letter", "portrait")
    set_tool_setting_for(canvas, "arrow_line_width", 2.5)
    set_tool_setting_for(canvas, "arrow_head_scale", 0.7)
    set_tool_setting_for(canvas, "orbital_phase_enabled", True)
    values = {
        "text_font_family": "DejaVu Sans",
        "text_font_size": 17,
        "text_font_weight": 600,
        "text_italic": True,
        "text_color": QColor("#13579b"),
        "text_alignment": Qt.AlignmentFlag.AlignRight,
        "text_line_spacing": 1.7,
        "note_box_enabled": True,
        "note_box_color": QColor("#2468ac"),
        "note_box_alpha": 0.4,
        "note_border_enabled": True,
        "note_border_color": QColor("#975321"),
        "note_border_width": 2.0,
        "note_padding": 9.0,
    }
    for name, value in values.items():
        set_text_style_for(canvas, name, value)


def _new_canvas(window):
    action = next(
        action
        for action in window.findChildren(QAction)
        if action.text() == "New Canvas"
    )
    before = open_windows()
    action.trigger()
    QApplication.processEvents()
    created = [item for item in open_windows() if item not in before]
    assert len(created) == 1
    assert QTest.qWaitForWindowExposed(created[0], 5000)
    return created[0], active_canvas_for_window(created[0])


def test_new_canvas_inherits_all_document_settings_without_content(source, tmp_path):
    window, canvas = source
    _customize(canvas)
    add_atom_for(canvas, "O", 0, 0)
    services = services_for_window(window)
    services.document_action_service.save_canvas_to_path(
        window, str(tmp_path / "source.chemvas")
    )
    before = snapshot_canvas_state_for(canvas)
    history = tuple(canvas.services.history_service.state.history)

    created_window, created = _new_canvas(window)
    after = snapshot_canvas_state_for(created)
    assert after["settings"] == before["settings"]
    assert not created.model.atoms and not created.model.bonds
    assert not created.services.history_service.state.history
    assert not created.services.history_service.state.redo_stack
    assert document_file_path_for(created) is None
    assert not services_for_window(created_window).canvas_document_service.is_dirty(
        created
    )
    assert snapshot_canvas_state_for(canvas) == before
    assert tuple(canvas.services.history_service.state.history) == history
    assert created_window is not window

    path = tmp_path / "inherited.chemvas"
    services_for_window(created_window).document_action_service.save_canvas_to_path(
        created_window, str(path)
    )
    from chemvas.core.document_io import read_document

    assert read_document(path).state["settings"] == before["settings"]


def test_new_canvas_text_colors_are_independent_and_inheritance_is_transitive(source):
    window, canvas = source
    _customize(canvas)
    created_window, created = _new_canvas(window)
    assert (
        snapshot_canvas_state_for(created)["settings"]
        == snapshot_canvas_state_for(canvas)["settings"]
    )
    source_colors = text_style_state_for(canvas)
    created_colors = text_style_state_for(created)
    for field in ("text_color", "note_box_color", "note_border_color"):
        original = QColor(getattr(source_colors, field))
        getattr(created_colors, field).setNamedColor("#abcdef")
        assert getattr(source_colors, field) == original
    set_bond_length_for(created, 31.0)
    _, third = _new_canvas(created_window)
    assert (
        snapshot_canvas_state_for(third)["settings"]
        == snapshot_canvas_state_for(created)["settings"]
    )


def test_plain_window_creation_does_not_inherit_reference_settings(source):
    window, canvas = source
    defaults = snapshot_canvas_state_for(canvas)["settings"]
    _customize(canvas)
    created = active_canvas_for_window(open_new_window(window))
    assert snapshot_canvas_state_for(created)["settings"] == defaults
