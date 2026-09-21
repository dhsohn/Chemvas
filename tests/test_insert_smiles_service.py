from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


from PyQt6.QtCore import QPointF

from chemvas.domain.document import Atom, MoleculeModel
from chemvas.ui.insert_mode_logic import InsertSessionState
from chemvas.ui.insert_smiles_service import (
    InsertSmilesService,
)
from tests.test_insert_controller import _FakeCanvas


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


def _service_for(canvas: _FakeCanvas, **overrides) -> InsertSmilesService:
    return InsertSmilesService(
        canvas,
        insert_state=canvas.insert_state,
        insert_commit_service=overrides.pop("insert_commit_service", mock.Mock()),
        session_state=lambda: _session_state(canvas),
        apply_session_state=lambda state: _apply_state(canvas, state),
        cancel_template_insert=overrides.pop("cancel_template_insert", mock.Mock()),
        cancel_smiles_insert=overrides.pop("cancel_smiles_insert", None),
        clear_smiles_preview=overrides.pop("clear_smiles_preview", None),
        render_smiles_preview=overrides.pop("render_smiles_preview", None),
    )


def test_insert_smiles_service_begin_smiles_insert_uses_callbacks_and_preview_state() -> (
    None
):
    canvas = _FakeCanvas()
    canvas.insert_state.template_active = True
    canvas.rdkit.smiles_to_2d.return_value = MoleculeModel(
        atoms={
            0: Atom("C", 0.0, 0.0),
            1: Atom("O", 10.0, 0.0),
        }
    )
    cancel_template = mock.Mock()
    render_preview = mock.Mock()
    service = _service_for(
        canvas,
        cancel_template_insert=cancel_template,
        render_smiles_preview=render_preview,
    )

    with mock.patch(
        "chemvas.ui.insert_smiles_service.render_smiles_preview_picture",
        return_value="picture",
    ):
        service.begin_smiles_insert(" CO ")

    assert canvas.insert_state.smiles_preview_picture == "picture"
    cancel_template.assert_called_once_with()
    assert canvas.insert_state.smiles_active
    assert canvas.insert_state.smiles_preview_smiles == "CO"
    assert (
        canvas.insert_state.smiles_preview_center.x(),
        canvas.insert_state.smiles_preview_center.y(),
    ) == (5.0, 0.0)
    assert (
        render_preview.call_args.args[0].x(),
        render_preview.call_args.args[0].y(),
    ) == (60.0, 40.0)


def test_insert_smiles_service_commit_uses_commit_service_and_cancel_callback() -> None:
    canvas = _FakeCanvas()
    canvas.insert_state.smiles_preview_smiles = "CO"
    canvas.insert_state.smiles_preview_center = QPointF(5.0, 0.0)
    canvas.insert_state.smiles_preview_model = MoleculeModel(
        atoms={0: Atom("C", 0.0, 0.0)}
    )
    commit_service = mock.Mock()
    commit_service.apply_smiles_commit.return_value = True
    cancel_smiles = mock.Mock()
    service = _service_for(
        canvas, insert_commit_service=commit_service, cancel_smiles_insert=cancel_smiles
    )

    service.commit_smiles_insert(QPointF(40.0, 20.0))

    commit_service.apply_smiles_commit.assert_called_once()
    assert commit_service.apply_smiles_commit.call_args.kwargs == {
        "after_smiles_input": "CO"
    }
    cancel_smiles.assert_called_once_with()


def test_insert_smiles_service_render_preview_routes_clear_and_move_paths() -> None:
    canvas = _FakeCanvas()
    canvas.insert_state.smiles_preview_model = MoleculeModel(
        atoms={0: Atom("C", 0.0, 0.0)}
    )
    canvas.insert_state.smiles_preview_center = QPointF(1.0, 1.0)
    clear_smiles_preview = mock.Mock()
    service = _service_for(canvas, clear_smiles_preview=clear_smiles_preview)

    # No rendered picture yet: nothing to show, so the stale ghost goes.
    service.render_smiles_preview(QPointF(1.0, 2.0))

    clear_smiles_preview.assert_called_once_with()

    clear_smiles_preview.reset_mock()
    canvas.insert_state.smiles_preview_picture = "picture"
    item = mock.Mock()
    item.picture.return_value = "picture"
    with mock.patch(
        "chemvas.ui.insert_smiles_service.add_smiles_preview_item_for",
        return_value=item,
    ) as add_item:
        service.render_smiles_preview(QPointF(3.0, 4.0))
        service.render_smiles_preview(QPointF(5.0, 6.0))

    clear_smiles_preview.assert_not_called()
    add_item.assert_called_once_with(canvas, "picture")
    assert canvas.insert_state.smiles_preview_items == [item]
    assert [call.args for call in item.setPos.call_args_list] == [
        (2.0, 3.0),
        (4.0, 5.0),
    ]


def test_insert_smiles_service_render_preview_replaces_a_stale_ghost() -> None:
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
    service = _service_for(canvas)
    fresh_item = mock.Mock()
    fresh_item.picture.return_value = "new-picture"

    with (
        mock.patch(
            "chemvas.ui.insert_smiles_service.clear_smiles_preview_helper",
            return_value=[],
        ) as clear_helper,
        mock.patch(
            "chemvas.ui.insert_smiles_service.add_smiles_preview_item_for",
            return_value=fresh_item,
        ) as add_item,
    ):
        service.render_smiles_preview(QPointF(7.0, 8.0))
        service.render_smiles_preview(QPointF(9.0, 10.0))

    clear_helper.assert_called_once_with(canvas, [stale_item])
    add_item.assert_called_once_with(canvas, "new-picture")
    stale_item.setPos.assert_not_called()
    assert canvas.insert_state.smiles_preview_items == [fresh_item]
    assert [call.args for call in fresh_item.setPos.call_args_list] == [
        (7.0, 8.0),
        (9.0, 10.0),
    ]
