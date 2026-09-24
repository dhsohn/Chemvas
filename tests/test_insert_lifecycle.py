from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QPointF

from chemvas.domain.document import Atom, Bond, MoleculeModel
from chemvas.features.insertion import (
    TemplateInsertRequest,
    TemplateInsertResolution,
    plan_template_preview,
)
from tests.canvas_factory import build_canvas_view
from tests.test_insert_controller import _controller_for, _FakeCanvas


class _FakeStructureItem:
    def __init__(self, kind: str, item_id: int) -> None:
        self._data = {0: kind, 1: item_id}

    def data(self, key):
        return self._data.get(key)


def test_insert_controller_render_preview_replaces_a_stale_ghost() -> None:
    # A second Insert while the first ghost is still up swaps the picture; the
    # item built from the old picture must go, or the ghost and the commit
    # would disagree again.
    canvas = _FakeCanvas()
    canvas.insert_state.smiles_preview_model = MoleculeModel(
        atoms={0: Atom("C", 0.0, 0.0)}
    )
    canvas.insert_state.smiles_preview_center = QPointF(0.0, 0.0)
    canvas.insert_state.smiles_preview_picture = "new-picture"
    stale_item = mock.Mock()
    stale_item.picture.return_value = "old-picture"
    canvas.insert_state.smiles_preview_items = [stale_item]
    controller = _controller_for(canvas)
    fresh_item = mock.Mock()
    fresh_item.picture.return_value = "new-picture"

    with (
        mock.patch(
            "chemvas.ui.insert.insert_controller.clear_scene_items",
            return_value=[],
        ) as clear_helper,
        mock.patch(
            "chemvas.ui.insert.insert_controller.add_smiles_preview_item",
            return_value=fresh_item,
        ) as add_item,
    ):
        controller.render_smiles_preview(QPointF(7.0, 8.0))
        controller.render_smiles_preview(QPointF(9.0, 10.0))

    clear_helper.assert_called_once_with(canvas.scene(), [stale_item])
    add_item.assert_called_once_with(canvas.scene(), "new-picture")
    stale_item.setPos.assert_not_called()
    assert canvas.insert_state.smiles_preview_items == [fresh_item]
    assert [call.args for call in fresh_item.setPos.call_args_list] == [
        (7.0, 8.0),
        (9.0, 10.0),
    ]


def test_insert_controller_template_request_uses_direct_atom_hit() -> None:
    canvas = _FakeCanvas()
    canvas.insert_state.template_active = True
    canvas.insert_state.template_ring_size = 5
    hit_testing = SimpleNamespace(
        item_at_scene_pos=mock.Mock(return_value=_FakeStructureItem("atom", 3)),
        find_bond_near=mock.Mock(return_value=7),
    )
    controller = _controller_for(canvas, hit_testing_service=hit_testing)

    request = controller.template_insert_request(QPointF(1.0, 2.0))

    assert request == TemplateInsertRequest(5, (1.0, 2.0), None, "regular", 3)
    hit_testing.item_at_scene_pos.assert_called_once_with(QPointF(1.0, 2.0))
    hit_testing.find_bond_near.assert_not_called()


def test_insert_controller_template_request_prefers_endpoint_atom_over_bond() -> None:
    canvas = _FakeCanvas()
    canvas.model.atoms = {1: Atom("N", 0.0, 0.0), 2: Atom("C", 10.0, 0.0)}
    canvas.model.bonds = [Bond(1, 2)]
    canvas.insert_state.template_active = True
    canvas.insert_state.template_ring_size = 6
    hit_testing = SimpleNamespace(
        item_at_scene_pos=mock.Mock(return_value=None),
        nearest_atom_hit=mock.Mock(return_value=(1, 0.0)),
        nearest_bond_hit=mock.Mock(return_value=(0, 0.0)),
        find_bond_near=mock.Mock(return_value=0),
    )
    controller = _controller_for(canvas, hit_testing_service=hit_testing)

    request = controller.template_insert_request(QPointF(0.0, 0.0))

    assert request == TemplateInsertRequest(6, (0.0, 0.0), None, "regular", 1)
    hit_testing.find_bond_near.assert_called_once_with(QPointF(0.0, 0.0), 7.0)


def test_insert_controller_render_benzene_preview_requests_aromatic_geometry() -> None:
    canvas = _FakeCanvas()
    controller = _controller_for(canvas)
    request = TemplateInsertRequest(6, (4.0, 5.0), ring_style="benzene")
    plan = plan_template_preview(request)
    assert plan is not None
    resolution = TemplateInsertResolution(
        plan=plan,
        points=[(1.0, 0.0), (2.0, 0.0), (3.0, 1.0), (2.0, 2.0), (1.0, 2.0), (0.0, 1.0)],
    )

    with (
        mock.patch(
            "chemvas.ui.insert.insert_controller.plan_template_preview",
            return_value=plan,
        ),
        mock.patch(
            "chemvas.ui.insert.template_geometry_resolver_service.resolve_template_insert",
            return_value=resolution,
        ),
        mock.patch(
            "chemvas.ui.insert.insert_controller.plan_template_preview_update",
            return_value=SimpleNamespace(action="update", geometry={"segments": 9}),
        ) as plan_update,
        mock.patch(
            "chemvas.ui.insert.insert_controller.apply_template_preview_geometry",
            return_value=(["items"], ["lines"], ["dots"]),
        ),
    ):
        controller.template_insert_request = mock.Mock(return_value=request)
        controller.render_template_preview(QPointF(4.0, 5.0))

    assert plan_update.call_args.kwargs == {"aromatic": True}


@pytest.fixture
def canvas(qt_application):
    view = build_canvas_view()
    try:
        yield view
    finally:
        view.services.canvas_scene_reset_service.clear_scene()
        view.close()
        view.deleteLater()
        QCoreApplication.sendPostedEvents(view, QEvent.Type.DeferredDelete)


def test_switching_insert_modes_removes_previous_preview(canvas) -> None:
    controller = canvas.services.insert_controller
    state = canvas.runtime_state.insert_state
    controller.begin_ring_template_insert(5)
    controller.render_template_preview(QPointF(0.0, 0.0))
    ring_items = list(state.template_preview_items)
    assert ring_items
    model = MoleculeModel(atoms={0: Atom("O", 0.0, 0.0)})

    with mock.patch.object(canvas.rdkit, "smiles_to_2d", return_value=model):
        controller.begin_smiles_insert("O")

    assert not state.template_active and state.smiles_active
    assert not state.template_preview_items
    assert all(item.scene() is None for item in ring_items)
    smiles_item = state.smiles_preview_items[0]

    controller.begin_ring_template_insert(6, "benzene")

    assert state.template_active and not state.smiles_active
    assert state.smiles_preview_model is None
    assert state.smiles_preview_picture is None
    assert not state.smiles_preview_items
    assert smiles_item.scene() is None
    assert not canvas.model.atoms


@pytest.mark.parametrize("smiles", ["", " ", "broken", "C" * 1025])
def test_invalid_smiles_still_cancels_active_ring_preview(canvas, smiles) -> None:
    controller = canvas.services.insert_controller
    state = canvas.runtime_state.insert_state
    controller.begin_ring_template_insert(5)
    controller.render_template_preview(QPointF(0.0, 0.0))
    items = list(state.template_preview_items)
    assert items

    with (
        mock.patch.object(canvas.rdkit, "smiles_to_2d", return_value=None),
        mock.patch("chemvas.ui.insert.insert_controller.QMessageBox.warning"),
    ):
        controller.begin_smiles_insert(smiles)

    assert not state.template_active and not state.smiles_active
    assert not state.template_preview_items
    assert all(item.scene() is None for item in items)
    assert not canvas.model.atoms


def test_ring_placement_repeats_and_smiles_placement_ends_with_undo_redo(
    canvas,
) -> None:

    controller = canvas.services.insert_controller
    history = canvas.services.history_service
    state = canvas.runtime_state.insert_state
    before = canvas.services.canvas_document_session_service.snapshot_state()
    controller.begin_ring_template_insert(5)
    for pos in (QPointF(-150.0, 0.0), QPointF(150.0, 0.0)):
        controller.render_template_preview(pos)
        assert state.template_preview_items
        controller.commit_template_insert(pos)
        assert state.template_active
        assert not state.template_preview_items
    assert len(canvas.model.atoms) == 10
    rings = canvas.services.canvas_document_session_service.snapshot_state()
    model = MoleculeModel(atoms={0: Atom("O", 0.0, 0.0)})
    with mock.patch.object(canvas.rdkit, "smiles_to_2d", return_value=model):
        controller.begin_smiles_insert("O")
    controller.commit_smiles_insert(QPointF(0.0, 100.0))
    assert not state.smiles_active and not state.template_active
    assert not state.smiles_preview_items
    assert state.smiles_preview_picture is None
    assert len(canvas.model.atoms) == 11
    after = canvas.services.canvas_document_session_service.snapshot_state()
    history.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == rings
    history.undo()
    history.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    for _ in range(3):
        history.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after
