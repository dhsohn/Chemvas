from __future__ import annotations

import os
from dataclasses import dataclass
from types import SimpleNamespace
from unittest import mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chemvas.domain.document import MoleculeModel
from chemvas.features.hover import HoverState
from chemvas.features.selection import StructureHit
from chemvas.ui.canvas_insert_state import CanvasInsertState
from chemvas.ui.canvas_tool_settings_state import CanvasToolSettingsState
from chemvas.ui.hover import HoverController, build_hover_controller
from chemvas.ui.sheet_setup_state import SheetSetupState
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
)


@pytest.fixture(scope="module", autouse=True)
def _application() -> QApplication:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@dataclass(slots=True)
class _HoverHarness:
    canvas: SimpleNamespace
    controller: HoverController
    state: HoverState
    scene: QGraphicsScene
    active_tool: SimpleNamespace
    selection_controller: mock.Mock
    hit_testing_service: mock.Mock
    insert_controller: mock.Mock
    scene_decoration_build_service: mock.Mock
    mark_scene_service: mock.Mock


def _build_harness(
    *,
    model: MoleculeModel | None = None,
    active_tool_name: str | None = "bond",
    active_bond_style: str = "single",
    active_bond_order: int = 1,
    mark_kind: str = "plus",
) -> _HoverHarness:
    scene = QGraphicsScene()
    state = HoverState()
    active_tool = SimpleNamespace(name=active_tool_name)
    selection_controller = mock.Mock()
    selection_controller.preferred_structure_hit_at_scene_pos.return_value = None
    hit_testing_service = mock.Mock()
    hit_testing_service.find_atom_near.return_value = None
    insert_controller = mock.Mock()
    scene_decoration_build_service = mock.Mock()
    scene_decoration_build_service.build_mark_item.side_effect = lambda kind: (
        QGraphicsTextItem(kind)
    )
    mark_scene_service = mock.Mock()
    mark_scene_service.mark_center_for_pointer.side_effect = (
        lambda pos, _atom_id=None, *, kind=None: QPointF(pos)
    )
    canvas = SimpleNamespace(
        scene=lambda: scene,
        model=model or MoleculeModel(),
        renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
        runtime_state=SimpleNamespace(
            hover_preview_state=state,
            insert_state=CanvasInsertState(),
            sheet_setup_state=SheetSetupState(),
            tool_settings_state=CanvasToolSettingsState(
                active_bond_style=active_bond_style,
                active_bond_order=active_bond_order,
                mark_kind=mark_kind,
            ),
        ),
    )
    controller = build_hover_controller(
        canvas,
        selection_controller=selection_controller,
        hit_testing_service=hit_testing_service,
        insert_controller=insert_controller,
        scene_decoration_build_service=scene_decoration_build_service,
        mark_scene_service=mark_scene_service,
        active_tool_name_provider=lambda: active_tool.name,
    )
    return _HoverHarness(
        canvas=canvas,
        controller=controller,
        state=state,
        scene=scene,
        active_tool=active_tool,
        selection_controller=selection_controller,
        hit_testing_service=hit_testing_service,
        insert_controller=insert_controller,
        scene_decoration_build_service=scene_decoration_build_service,
        mark_scene_service=mark_scene_service,
    )


def test_controller_requires_canonical_runtime_hover_state() -> None:
    harness = _build_harness()
    del harness.canvas.runtime_state.hover_preview_state

    with pytest.raises(AttributeError):
        harness.controller.clear_hover_highlight()

    assert not hasattr(harness.canvas, "hover_preview_state")
    assert not hasattr(harness.canvas, "hover_items")
    assert not hasattr(harness.canvas, "hover_atom_id")
    assert not hasattr(harness.canvas, "hover_bond_id")


def test_clear_removes_only_tracked_items_and_resets_hover_state() -> None:
    harness = _build_harness()
    keep = QGraphicsRectItem(0.0, 0.0, 2.0, 2.0)
    tracked_text = QGraphicsTextItem("hover")
    tracked_dot = QGraphicsEllipseItem(1.0, 2.0, 3.0, 4.0)
    for item in (keep, tracked_text, tracked_dot):
        harness.scene.addItem(item)
    harness.state.items.extend((tracked_text, tracked_dot))
    harness.state.atom_id = 7
    harness.state.bond_id = 3
    harness.state.style = "hash"

    harness.controller.clear_hover_highlight()

    assert harness.state == HoverState()
    assert keep.scene() is harness.scene
    assert tracked_text.scene() is None
    assert tracked_dot.scene() is None
    assert harness.scene.items() == [keep]


def test_indicator_methods_track_valid_atom_and_bond_geometry_only() -> None:
    model = MoleculeModel()
    first = model.add_atom("C", 0.0, 0.0)
    second = model.add_atom("C", 20.0, 10.0)
    bond_id = model.add_bond(first, second)
    model.bonds.extend((None,))
    harness = _build_harness(model=model)

    harness.controller.add_atom_hover_indicator(second)
    harness.controller.add_bond_hover_indicator(bond_id)
    harness.controller.add_atom_hover_indicator(99)
    harness.controller.add_bond_hover_indicator(None)
    harness.controller.add_bond_hover_indicator(99)
    harness.controller.add_bond_hover_indicator(1)

    assert len(harness.state.items) == 2
    atom_indicator, bond_indicator = harness.state.items
    assert isinstance(atom_indicator, QGraphicsEllipseItem)
    assert isinstance(bond_indicator, QGraphicsEllipseItem)
    assert atom_indicator.scene() is harness.scene
    assert bond_indicator.scene() is harness.scene
    assert atom_indicator.rect() == QRectF(15.0, 5.0, 10.0, 10.0)
    assert bond_indicator.rect() == QRectF(5.6, 0.6, 8.8, 8.8)


def test_mark_preview_uses_required_collaborators_and_skips_duplicate() -> None:
    model = MoleculeModel()
    atom_id = model.add_atom("C", 10.0, 20.0)
    harness = _build_harness(
        model=model,
        active_tool_name="mark",
        mark_kind="plus",
    )
    harness.hit_testing_service.find_atom_near.return_value = atom_id
    harness.mark_scene_service.mark_center_for_pointer.side_effect = None
    harness.mark_scene_service.mark_center_for_pointer.return_value = QPointF(
        12.0, 18.0
    )
    pos = QPointF(4.0, 5.0)

    harness.controller.update_hover_highlight(pos)
    harness.controller.update_hover_highlight(pos)

    harness.hit_testing_service.find_atom_near.assert_has_calls(
        [mock.call(4.0, 5.0, 7.0), mock.call(4.0, 5.0, 7.0)]
    )
    harness.mark_scene_service.mark_center_for_pointer.assert_has_calls(
        [
            mock.call(pos, atom_id, kind="plus"),
            mock.call(pos, atom_id, kind="plus"),
        ]
    )
    harness.scene_decoration_build_service.build_mark_item.assert_called_once_with(
        "plus"
    )
    harness.scene_decoration_build_service.set_mark_center.assert_called_once_with(
        harness.state.items[1], QPointF(12.0, 18.0)
    )
    assert harness.state.atom_id == atom_id
    assert harness.state.bond_id is None
    assert harness.state.style == "mark:plus:atom:0:12.0:18.0"
    assert len(harness.state.items) == 2
    assert len(harness.scene.items()) == 2


def test_mark_preview_with_missing_item_leaves_cleared_free_hover_state() -> None:
    harness = _build_harness(active_tool_name="mark")
    harness.scene_decoration_build_service.build_mark_item.return_value = None
    harness.scene_decoration_build_service.build_mark_item.side_effect = None

    harness.controller.update_hover_highlight(QPointF(3.5, 7.5))

    assert harness.state == HoverState()
    assert harness.scene.items() == []
    harness.scene_decoration_build_service.set_mark_center.assert_not_called()


def test_update_outside_sheet_clears_without_running_mark_hit_test() -> None:
    harness = _build_harness(active_tool_name="mark")
    harness.canvas.runtime_state.sheet_setup_state.rect = QRectF(
        -10.0, -10.0, 20.0, 20.0
    )
    tracked = QGraphicsRectItem(0.0, 0.0, 1.0, 1.0)
    harness.scene.addItem(tracked)
    harness.state.items.append(tracked)
    harness.state.style = "old-preview"

    harness.controller.update_hover_highlight(QPointF(999.0, 999.0))

    assert harness.state == HoverState()
    assert harness.scene.items() == []
    harness.hit_testing_service.find_atom_near.assert_not_called()


def test_empty_canvas_free_bond_preview_uses_horizontal_segment_and_deduplicates() -> (
    None
):
    harness = _build_harness(
        active_tool_name="bond",
        active_bond_style="wedge",
        active_bond_order=1,
    )
    preview = QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)
    pos = QPointF(8.0, 9.0)

    with mock.patch(
        "chemvas.ui.hover.build_bond_preview_items_for",
        return_value=[preview],
    ) as build_preview:
        harness.controller.update_hover_highlight(pos)
        harness.controller.update_hover_highlight(pos)

    build_preview.assert_called_once_with(
        harness.canvas,
        QPointF(8.0, 9.0),
        QPointF(28.0, 9.0),
    )
    harness.selection_controller.preferred_structure_hit_at_scene_pos.assert_not_called()
    assert harness.state.style == "wedge:1:8.0:9.0"
    assert harness.state.items == [preview]
    assert preview.scene() is harness.scene


def test_atom_hit_adds_indicator_and_endpoint_preview() -> None:
    model = MoleculeModel()
    atom_id = model.add_atom("C", 10.0, 20.0)
    harness = _build_harness(
        model=model,
        active_tool_name="bond",
        active_bond_style="wedge",
    )
    harness.selection_controller.preferred_structure_hit_at_scene_pos.return_value = (
        StructureHit(kind="atom", id=atom_id)
    )
    preview = QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)
    pos = QPointF(11.0, 12.0)

    with (
        mock.patch(
            "chemvas.ui.hover.bond_hover_endpoint_for",
            return_value=QPointF(17.0, 18.0),
        ) as endpoint,
        mock.patch(
            "chemvas.ui.hover.build_bond_preview_items_for",
            return_value=[preview],
        ) as build_preview,
    ):
        harness.controller.update_hover_highlight(pos)

    harness.selection_controller.preferred_structure_hit_at_scene_pos.assert_called_once_with(
        pos
    )
    endpoint.assert_has_calls(
        [
            mock.call(
                harness.canvas,
                QPointF(10.0, 20.0),
                pos,
                atom_id,
            ),
            mock.call(
                harness.canvas,
                QPointF(10.0, 20.0),
                pos,
                atom_id,
            ),
        ]
    )
    build_preview.assert_called_once_with(
        harness.canvas,
        QPointF(10.0, 20.0),
        QPointF(17.0, 18.0),
        atom_id,
        None,
    )
    assert harness.state.atom_id == atom_id
    assert harness.state.bond_id is None
    assert harness.state.style == "wedge:1:17.0:18.0"
    assert len(harness.state.items) == 2
    assert preview in harness.state.items


@pytest.mark.parametrize(
    ("active_tool_name", "active_bond_style", "expected_style", "item_count"),
    [
        ("bond", "wedge", "wedge", 2),
        ("bond", "hash", "hash", 2),
        ("select", "wedge", None, 1),
    ],
)
def test_bond_hit_adds_indicator_and_supported_style_preview(
    active_tool_name: str,
    active_bond_style: str,
    expected_style: str | None,
    item_count: int,
) -> None:
    model = MoleculeModel()
    first = model.add_atom("C", 10.0, 20.0)
    second = model.add_atom("C", 30.0, 20.0)
    bond_id = model.add_bond(first, second)
    harness = _build_harness(
        model=model,
        active_tool_name=active_tool_name,
        active_bond_style=active_bond_style,
    )
    harness.selection_controller.preferred_structure_hit_at_scene_pos.return_value = (
        StructureHit(kind="bond", id=bond_id)
    )
    preview = QGraphicsLineItem(0.0, 0.0, 1.0, 0.0)

    with mock.patch(
        "chemvas.ui.hover.build_bond_preview_items_for",
        return_value=[preview],
    ) as build_preview:
        harness.controller.update_hover_highlight(QPointF(4.0, 5.0))

    assert harness.state.atom_id is None
    assert harness.state.bond_id == bond_id
    assert harness.state.style == expected_style
    assert len(harness.state.items) == item_count
    if expected_style is None:
        build_preview.assert_not_called()
        assert preview.scene() is None
    else:
        build_preview.assert_called_once_with(
            harness.canvas,
            QPointF(10.0, 20.0),
            QPointF(30.0, 20.0),
            first,
            second,
        )
        assert preview.scene() is harness.scene


@pytest.mark.parametrize(
    ("template_active", "smiles_active", "expected_method"),
    [
        (True, False, "render_template_preview"),
        (False, True, "render_smiles_preview"),
    ],
)
def test_refresh_routes_active_insert_preview_and_clears_structure_hover(
    template_active: bool,
    smiles_active: bool,
    expected_method: str,
) -> None:
    harness = _build_harness()
    harness.canvas.runtime_state.insert_state.template_active = template_active
    harness.canvas.runtime_state.insert_state.smiles_active = smiles_active
    tracked = QGraphicsRectItem(0.0, 0.0, 1.0, 1.0)
    harness.scene.addItem(tracked)
    harness.state.items.append(tracked)
    harness.state.style = "old-preview"
    pos = QPointF(12.0, 13.0)

    with mock.patch(
        "chemvas.ui.hover.scene_pos_from_global_pos_for",
        return_value=pos,
    ):
        harness.controller.refresh(render_insert_preview=True)

    assert harness.state == HoverState()
    expected = getattr(harness.insert_controller, expected_method)
    expected.assert_called_once_with(pos)
    other_method = (
        harness.insert_controller.render_smiles_preview
        if expected_method == "render_template_preview"
        else harness.insert_controller.render_template_preview
    )
    other_method.assert_not_called()


def test_refresh_updates_at_cursor_or_clears_when_cursor_is_outside_view() -> None:
    harness = _build_harness()
    pos = QPointF(7.0, 8.0)

    with (
        mock.patch(
            "chemvas.ui.hover.scene_pos_from_global_pos_for",
            return_value=pos,
        ),
        mock.patch.object(harness.controller, "update_hover_highlight") as update,
    ):
        harness.controller.refresh()

    update.assert_called_once_with(pos)

    tracked = QGraphicsRectItem(0.0, 0.0, 1.0, 1.0)
    harness.scene.addItem(tracked)
    harness.state.items.append(tracked)
    harness.state.style = "old-preview"
    with mock.patch(
        "chemvas.ui.hover.scene_pos_from_global_pos_for",
        return_value=None,
    ):
        harness.controller.refresh()

    assert harness.state == HoverState()
    assert harness.scene.items() == []


def test_scene_reset_clears_preview_key_so_same_position_preview_reappears() -> None:
    from chemvas.ui.canvas_view import CanvasView

    canvas = CanvasView()
    try:
        services = canvas.services
        services.input.tool_mode_controller.set_bond_style("single", 1)
        controller = services.hover
        state = canvas.runtime_state.hover_preview_state
        pos = QPointF(10.0, 10.0)

        controller.update_hover_highlight(pos)
        assert state.style == "single:1:10.0:10.0"
        assert state.items

        services.document.canvas_scene_reset_service.clear_scene()

        assert state == HoverState()
        controller.update_hover_highlight(pos)
        assert state.style == "single:1:10.0:10.0"
        assert state.items
    finally:
        canvas.close()
