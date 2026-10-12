from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QPointF

from chemvas.domain.document import Atom, Bond
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
            "chemvas.ui.insert.template_geometry_resolver_service.TemplateGeometryResolverService.resolve_insert",
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

    assert plan_update.call_args.kwargs == {"aromatic": True, "bond_orders": None}


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


def test_ring_placement_repeats_with_undo_redo(
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
    after = rings
    history.undo()
    history.undo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == before
    for _ in range(2):
        history.redo()
    assert canvas.services.canvas_document_session_service.snapshot_state() == after
