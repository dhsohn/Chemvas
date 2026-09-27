"""History refuses every edit while it is disabled.

Document replacement is the only owner that disables history, and no editor
runs while it builds the replacement. A push in that window raises, and the
editor's transaction restores the document, so an edit is never applied
without an Undo entry.
"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QApplication

from chemvas.core.document_io import read_document
from chemvas.ui.canvas import canvas_document_session_service
from chemvas.ui.canvas.sheet_setup_access import sheet_setup_for
from chemvas.ui.canvas.sheet_setup_service import change_sheet_setup_for
from chemvas.ui.history.history_commands import AddSceneItemsCommand
from chemvas.ui.scene.image_actions import insert_image_bytes
from tests.canvas_factory import build_canvas_view

EXTENDED_DOCUMENT = (
    Path(__file__).parent / "fixtures" / "document-v8" / "extended.chemvas"
)


@pytest.fixture(scope="module")
def app() -> QApplication:
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app: QApplication):
    view = build_canvas_view()
    view.services.structure_build_service.add_benzene_ring(QPointF(0, 0))
    note = view.services.note_controller.create_text_note(QPointF(-70, -20), "Note")
    view.services.selection.select_note(note, additive=False)
    view.services.scene_decoration_service.add_shape(QRectF(80, 80, 40, 30))
    yield view
    view.services.canvas_scene_reset_service.clear_scene()
    view.close()


def _snapshot(canvas) -> dict:
    return canvas.services.canvas_document_session_service.snapshot_state()


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGBA", (8, 4), (20, 80, 160, 255)).save(output, format="PNG")
    return output.getvalue()


def _other_sheet(canvas) -> tuple[str, str]:
    size, orientation = sheet_setup_for(canvas)
    return size, "portrait" if orientation == "landscape" else "landscape"


def _first_atom(canvas) -> int:
    return min(canvas.model.atoms)


EDITS = {
    "structure": lambda canvas: (
        canvas.services.structure_build_service.add_benzene_ring(QPointF(200, 200))
    ),
    "atom label": lambda canvas: (
        canvas.services.atom_label_service.add_or_update_atom_label(
            _first_atom(canvas), "N"
        )
    ),
    "delete": lambda canvas: canvas.services.scene_delete_controller.delete_atom(
        _first_atom(canvas)
    ),
    "note formatting": lambda canvas: (
        canvas.services.note_controller.toggle_text_bold()
    ),
    "shape": lambda canvas: canvas.services.scene_decoration_service.add_shape(
        QRectF(-120, 60, 30, 30)
    ),
    "bond length": lambda canvas: canvas.services.geometry_controller.set_bond_length(
        60
    ),
    "sheet setup": lambda canvas: change_sheet_setup_for(canvas, *_other_sheet(canvas)),
    "image": lambda canvas: insert_image_bytes(canvas, _png()),
}


def test_disabled_history_refuses_a_push_without_touching_either_stack(canvas):
    history = canvas.services.history_service
    history.undo()
    history.set_enabled(False)
    stacks = history.capture_stack_snapshot()
    notified = []
    history.set_change_callback(lambda: notified.append(True))

    with pytest.raises(RuntimeError, match="History is disabled"):
        history.push(AddSceneItemsCommand(item_states=[]))

    history.verify_stack_snapshot(stacks)
    assert notified == []


@pytest.mark.parametrize("edit", EDITS.values(), ids=EDITS.keys())
def test_every_editor_refuses_an_edit_and_restores_the_document(canvas, edit):
    history = canvas.services.history_service
    history.set_enabled(False)
    before = _snapshot(canvas)
    stacks = history.capture_stack_snapshot()
    published = []
    canvas.runtime_state.callback_state.document_change = lambda **change: (
        published.append(change)
    )

    with pytest.raises(RuntimeError, match="History is disabled"):
        edit(canvas)

    assert _snapshot(canvas) == before
    history.verify_stack_snapshot(stacks)
    assert published == []
    history.set_enabled(True)
    edit(canvas)
    assert _snapshot(canvas) != before
    assert len(history.state.history) == len(stacks.history) + 1


def test_document_replacement_loads_every_family_without_an_edit(canvas):
    history = canvas.services.history_service
    state = read_document(EXTENDED_DOCUMENT).state

    with mock.patch.object(history, "push", wraps=history.push) as push:
        canvas.services.canvas_document_session_service.apply_state(state)

    push.assert_not_called()
    assert history.is_enabled()
    assert not history.can_undo()


def test_an_edit_during_document_replacement_restores_the_previous_document(canvas):
    history = canvas.services.history_service
    session = canvas.services.canvas_document_session_service
    before = _snapshot(canvas)
    stacks = history.capture_stack_snapshot()
    populate = canvas_document_session_service.populate_document_scene

    def populate_then_edit(*args, **kwargs):
        populate(*args, **kwargs)
        canvas.services.scene_decoration_service.add_shape(QRectF(0, 0, 10, 10))

    with (
        mock.patch.object(
            canvas_document_session_service,
            "populate_document_scene",
            side_effect=populate_then_edit,
        ),
        pytest.raises(RuntimeError, match="History is disabled"),
    ):
        session.apply_state(read_document(EXTENDED_DOCUMENT).state)

    assert _snapshot(canvas) == before
    history.verify_stack_snapshot(stacks)
    assert history.is_enabled()
