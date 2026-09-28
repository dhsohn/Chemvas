"""Erase gestures preserve the document across rejection, cancellation and replay."""

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QPointF

from chemvas.ui.canvas.canvas_group_state import register_group_for
from chemvas.ui.canvas.canvas_lifecycle import schedule_canvas_deletion_for
from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id
from chemvas.ui.tools.delete_tool_logic import erase_delete_tool_item
from tests.canvas_factory import build_canvas_view


@pytest.fixture
def canvas(qt_application):
    view = build_canvas_view()
    yield view
    schedule_canvas_deletion_for(view)
    QCoreApplication.sendPostedEvents(view, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("cancel", [False, True])
def test_ring_erase_can_cancel_or_undo_and_redo_without_touching_the_graph(
    canvas, cancel
):
    ring = canvas.services.structure_build_service.add_benzene_ring(QPointF())
    assert ring is not None
    note = canvas.services.note_controller.create_text_note(QPointF(90, 0), "keep")
    group = register_group_for(
        canvas, set(canvas.model.atoms), [require_scene_record_id(note)]
    )
    document = canvas.services.canvas_document_session_service
    before = document.snapshot_state()
    history = canvas.services.history_service
    stack = history.capture_stack_snapshot()
    session = canvas.services.scene_delete_controller.begin_delete_tool_session()

    changed, command = erase_delete_tool_item(canvas, ring, delete_session=session)

    assert changed and command is not None
    assert ring.scene() is None
    assert len(canvas.model.atoms) == 6
    assert sum(bond is not None for bond in canvas.model.bonds) == 6
    assert group in canvas.runtime_state.group_state.groups
    if cancel:
        assert session.rollback() == []
        assert document.snapshot_state() == before
        assert ring.scene() is canvas.scene()
        history.verify_stack_snapshot(stack)
    else:
        session.commit(command)
        after = document.snapshot_state()
        assert after != before
        history.undo()
        assert document.snapshot_state() == before
        assert canvas.runtime_state.ring_items()
        history.redo()
        assert document.snapshot_state() == after
        assert not canvas.runtime_state.ring_items()


@pytest.mark.parametrize("kind", ["atom", "bond"])
def test_declined_erase_restores_group_and_graph_indexes_for_next_hit(
    canvas, monkeypatch, kind
):
    atom_a = canvas.services.canvas_atom_mutation_service.add_atom("C", 0, 0)
    atom_b = canvas.services.canvas_atom_mutation_service.add_atom("C", 20, 0)
    bond = canvas.services.canvas_bond_mutation_service.add_bond(atom_a, atom_b)
    canvas.bond_renderer.add_bond_graphics(bond)
    note = canvas.services.note_controller.create_text_note(QPointF(80, 0), "group")
    group_id = register_group_for(
        canvas, {atom_a, atom_b}, [require_scene_record_id(note)]
    )
    document = canvas.services.canvas_document_session_service
    before = document.snapshot_state()
    controller = canvas.services.scene_delete_controller
    history = canvas.services.history_service
    stack = history.capture_stack_snapshot()
    session = controller.begin_delete_tool_session()
    erase = session.delete_atom if kind == "atom" else session.delete_bond
    target = atom_a if kind == "atom" else bond

    with monkeypatch.context() as patch:
        patch.setattr(controller, f"_delete_{kind}", lambda *_args, **_kwargs: None)
        assert erase(target) is None

    assert document.snapshot_state() == before
    history.verify_stack_snapshot(stack)
    # Continue the same gesture: losing a reverse index would leave the group
    # with deleted atoms or skip an orphan on this second hit.
    command = erase(target)
    assert command is not None
    session.commit(command)
    assert not canvas.model.atoms
    assert canvas.model.bonds[bond] is None
    group = canvas.runtime_state.group_state.groups[group_id]
    assert group.atom_ids == set()
    assert group.item_ids == [require_scene_record_id(note)]
    after = document.snapshot_state()
    history.undo()
    assert document.snapshot_state() == before
    history.redo()
    assert document.snapshot_state() == after
