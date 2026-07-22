from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from chemvas.domain.document import Atom, Bond
from chemvas.features.insertion import (
    TemplateInsertRequest,
    TemplateInsertResolution,
    plan_template_commit,
    plan_template_preview,
)
from chemvas.ui.insert_mode_logic import InsertSessionState
from chemvas.ui.insert_template_service import InsertTemplateService
from PyQt6.QtCore import QPointF

from tests.test_insert_controller import _FakeCanvas


class _FakeStructureItem:
    def __init__(self, kind: str, item_id: int) -> None:
        self._data = {0: kind, 1: item_id}

    def data(self, key):
        return self._data.get(key)


def _session_state(canvas: _FakeCanvas) -> InsertSessionState:
    center = canvas.insert_state.smiles_preview_center
    return InsertSessionState(
        template_active=canvas.insert_state.template_active,
        template_ring_size=canvas.insert_state.template_ring_size,
        template_ring_style=canvas.insert_state.template_ring_style,
        smiles_active=canvas.insert_state.smiles_active,
        smiles_text=canvas.insert_state.smiles_preview_smiles,
        smiles_center=None if center is None else (center.x(), center.y()),
    )


def _apply_state(canvas: _FakeCanvas, state: InsertSessionState) -> None:
    canvas.insert_state.template_active = state.template_active
    canvas.insert_state.template_ring_size = state.template_ring_size
    canvas.insert_state.template_ring_style = state.template_ring_style
    canvas.insert_state.smiles_active = state.smiles_active
    canvas.insert_state.smiles_preview_smiles = state.smiles_text
    canvas.insert_state.smiles_preview_center = (
        None if state.smiles_center is None else QPointF(*state.smiles_center)
    )


def _service_for(canvas: _FakeCanvas, **overrides) -> InsertTemplateService:
    return InsertTemplateService(
        canvas,
        insert_state=canvas.insert_state,
        hit_testing_service=overrides.pop(
            "hit_testing_service", canvas.services.selection.hit_testing_service
        ),
        insert_commit_service=overrides.pop("insert_commit_service", mock.Mock()),
        session_state=lambda: _session_state(canvas),
        apply_session_state=lambda state: _apply_state(canvas, state),
        cancel_smiles_insert=overrides.pop("cancel_smiles_insert", mock.Mock()),
        **overrides,
    )


def test_insert_template_service_begin_template_activates_state_without_initial_preview() -> (
    None
):
    canvas = _FakeCanvas()
    canvas.insert_state.smiles_active = True
    cancel_smiles = mock.Mock()
    service = _service_for(canvas, cancel_smiles_insert=cancel_smiles)
    service.render_template_preview = mock.Mock()

    service.begin_ring_template_insert(6, "benzene")

    cancel_smiles.assert_called_once_with()
    assert canvas.insert_state.template_active
    assert canvas.insert_state.template_ring_size == 6
    assert canvas.insert_state.template_ring_style == "benzene"
    service.render_template_preview.assert_not_called()


def test_insert_template_service_template_request_uses_injected_hit_testing() -> None:
    canvas = _FakeCanvas()
    canvas.insert_state.template_active = True
    canvas.insert_state.template_ring_size = 5
    hit_testing = SimpleNamespace(find_bond_near=mock.Mock(return_value=7))
    service = _service_for(canvas, hit_testing_service=hit_testing)

    request = service.template_insert_request(QPointF(1.0, 2.0))

    assert request == TemplateInsertRequest(5, (1.0, 2.0), 7, "regular")
    hit_testing.find_bond_near.assert_called_once_with(QPointF(1.0, 2.0), 7.0)


def test_insert_template_service_template_request_uses_direct_atom_hit() -> None:
    canvas = _FakeCanvas()
    canvas.insert_state.template_active = True
    canvas.insert_state.template_ring_size = 5
    hit_testing = SimpleNamespace(
        item_at_scene_pos=mock.Mock(return_value=_FakeStructureItem("atom", 3)),
        find_bond_near=mock.Mock(return_value=7),
    )
    service = _service_for(canvas, hit_testing_service=hit_testing)

    request = service.template_insert_request(QPointF(1.0, 2.0))

    assert request == TemplateInsertRequest(5, (1.0, 2.0), None, "regular", 3)
    hit_testing.item_at_scene_pos.assert_called_once_with(QPointF(1.0, 2.0))
    hit_testing.find_bond_near.assert_not_called()


def test_insert_template_service_template_request_prefers_endpoint_atom_over_bond() -> (
    None
):
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
    service = _service_for(canvas, hit_testing_service=hit_testing)

    request = service.template_insert_request(QPointF(0.0, 0.0))

    assert request == TemplateInsertRequest(6, (0.0, 0.0), None, "regular", 1)
    hit_testing.find_bond_near.assert_called_once_with(QPointF(0.0, 0.0), 7.0)


def test_insert_template_service_commit_resolves_plan_and_keeps_session_active() -> (
    None
):
    canvas = _FakeCanvas()
    canvas.insert_state.template_active = True
    canvas.insert_state.template_ring_size = 5
    canvas.insert_state.template_ring_style = "regular"
    commit_service = mock.Mock()
    commit_service.apply_template_commit.return_value = True
    service = _service_for(canvas, insert_commit_service=commit_service)
    request = TemplateInsertRequest(5, (4.0, 5.0), ring_style="regular")
    plan = plan_template_commit(request)
    assert plan is not None
    resolution = TemplateInsertResolution(plan=plan, points=[(1.0, 2.0), (3.0, 4.0)])

    with mock.patch(
        "chemvas.ui.template_geometry_resolver_service.resolve_template_insert",
        return_value=resolution,
    ) as resolve:
        service.commit_template_request(QPointF(4.0, 5.0), request)

    resolve.assert_called_once()
    commit_service.apply_template_commit.assert_called_once_with(
        QPointF(4.0, 5.0),
        request=request,
        plan=plan,
        resolution=resolution,
    )
    assert canvas.insert_state.template_active
    assert canvas.insert_state.template_ring_size == 5
    assert canvas.insert_state.template_ring_style == "regular"


def test_insert_template_service_render_preview_routes_clear_and_apply_paths() -> None:
    canvas = _FakeCanvas()
    clear_preview = mock.Mock()
    service = _service_for(canvas)
    request = TemplateInsertRequest(5, (4.0, 5.0), ring_style="regular")
    plan = plan_template_preview(request)
    assert plan is not None

    with mock.patch(
        "chemvas.ui.insert_template_service.plan_template_preview", return_value=None
    ):
        service.render_template_request_preview(
            QPointF(4.0, 5.0),
            request,
            clear_template_preview=clear_preview,
        )

    clear_preview.assert_called_once_with()

    clear_preview.reset_mock()
    resolution = TemplateInsertResolution(plan=plan, points=[(1.0, 2.0), (3.0, 4.0)])
    with (
        mock.patch(
            "chemvas.ui.insert_template_service.plan_template_preview",
            return_value=plan,
        ),
        mock.patch(
            "chemvas.ui.template_geometry_resolver_service.resolve_template_insert",
            return_value=resolution,
        ),
        mock.patch(
            "chemvas.ui.insert_template_service.plan_template_preview_update",
            return_value=SimpleNamespace(action="update", geometry={"segments": 2}),
        ) as plan_update,
        mock.patch(
            "chemvas.ui.insert_template_service.apply_template_preview_geometry_helper",
            return_value=(["items"], ["lines"], ["dots"]),
        ) as apply_helper,
    ):
        service.render_template_request_preview(
            QPointF(4.0, 5.0),
            request,
            clear_template_preview=clear_preview,
        )

    clear_preview.assert_not_called()
    self_args = plan_update.call_args
    assert self_args.kwargs == {"aromatic": False}
    apply_helper.assert_called_once()
    assert canvas.insert_state.template_preview_items == ["items"]
    assert canvas.insert_state.template_preview_lines == ["lines"]
    assert canvas.insert_state.template_preview_dots == ["dots"]


def test_insert_template_service_render_benzene_preview_requests_aromatic_geometry() -> (
    None
):
    canvas = _FakeCanvas()
    service = _service_for(canvas)
    request = TemplateInsertRequest(6, (4.0, 5.0), ring_style="benzene")
    plan = plan_template_preview(request)
    assert plan is not None
    resolution = TemplateInsertResolution(
        plan=plan,
        points=[(1.0, 0.0), (2.0, 0.0), (3.0, 1.0), (2.0, 2.0), (1.0, 2.0), (0.0, 1.0)],
    )

    with (
        mock.patch(
            "chemvas.ui.insert_template_service.plan_template_preview",
            return_value=plan,
        ),
        mock.patch(
            "chemvas.ui.template_geometry_resolver_service.resolve_template_insert",
            return_value=resolution,
        ),
        mock.patch(
            "chemvas.ui.insert_template_service.plan_template_preview_update",
            return_value=SimpleNamespace(action="update", geometry={"segments": 9}),
        ) as plan_update,
        mock.patch(
            "chemvas.ui.insert_template_service.apply_template_preview_geometry_helper",
            return_value=(["items"], ["lines"], ["dots"]),
        ),
    ):
        service.render_template_request_preview(QPointF(4.0, 5.0), request)

    assert plan_update.call_args.kwargs == {"aromatic": True}
