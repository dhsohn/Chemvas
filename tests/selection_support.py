from tests.ring_support import seed_ring_items

"""Shared canvas doubles for selection-service tests."""

import os
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QPainterPath

from chemvas.ui.canvas_atom_graphics_state import (
    CanvasAtomGraphicsState,
    atom_dots_for,
    atom_items_for,
    set_atom_dots_for,
    set_atom_items_for,
)
from chemvas.ui.canvas_bond_graphics_state import (
    CanvasBondGraphicsState,
    bond_items_for,
    set_bond_items_for,
)
from chemvas.ui.canvas_group_state import CanvasGroupState
from chemvas.ui.canvas_rotation_state import CanvasRotationState
from chemvas.ui.canvas_scene_items_state import (
    CanvasSceneItemsState,
)
from chemvas.ui.canvas_text_style_state import CanvasTextStyleState
from chemvas.ui.selection_info_state import SelectionInfoState
from chemvas.ui.selection_state import (
    SelectionState,
    set_selected_notes_for,
    set_selection_outlines_for,
)


class _FakeItem:
    def __init__(
        self,
        kind=None,
        *,
        data1=None,
        data2=None,
        selected=False,
        rect: QRectF | None = None,
        contains=False,
    ) -> None:
        self._data = {0: kind, 1: data1, 2: data2}
        self._selected = bool(selected)
        self._rect = QRectF(rect or QRectF(0.0, 0.0, 10.0, 6.0))
        self._contains = contains
        self.moves = []

    def data(self, key):
        return self._data.get(key)

    def setSelected(self, selected: bool) -> None:
        self._selected = bool(selected)

    def isSelected(self) -> bool:
        return self._selected

    def sceneBoundingRect(self) -> QRectF:
        return QRectF(self._rect)

    def childrenBoundingRect(self) -> QRectF:
        return QRectF()

    def mapRectToScene(self, rect: QRectF) -> QRectF:
        return QRectF(rect)

    def contains(self, _pos) -> bool:
        return self._contains

    def mapFromScene(self, pos):
        return pos

    def moveBy(self, dx: float, dy: float) -> None:
        self.moves.append((dx, dy))


class _FakeScene:
    def __init__(self, selected_items=None) -> None:
        self._selected_items = list(selected_items or [])
        self.block_signal_calls = []
        self.removed_items = []
        self.added_items = []
        self.clear_selection_calls = 0

    def selectedItems(self):
        return list(self._selected_items)

    def blockSignals(self, enabled: bool) -> None:
        self.block_signal_calls.append(enabled)

    def removeItem(self, item) -> None:
        self.removed_items.append(item)

    def addItem(self, item) -> None:
        self.added_items.append(item)

    def clearSelection(self) -> None:
        self.clear_selection_calls += 1
        for item in self._selected_items:
            item.setSelected(False)


class _FakeShapeItem:
    def __init__(
        self,
        kind=None,
        *,
        rect: QRectF | None = None,
        shape: QPainterPath | None = None,
    ) -> None:
        self._kind = kind
        self._rect = QRectF(rect or QRectF(0.0, 0.0, 10.0, 6.0))
        self._shape = QPainterPath() if shape is None else QPainterPath(shape)

    def data(self, key):
        if key == 0:
            return self._kind
        return None

    def mapToScene(self, value):
        return value

    def shape(self) -> QPainterPath:
        return QPainterPath(self._shape)

    def sceneBoundingRect(self) -> QRectF:
        return QRectF(self._rect)


def _canvas_runtime_state():
    """Canonical state container the accessors read through."""

    return canvas_runtime_state(
        atom_graphics_state=CanvasAtomGraphicsState(),
        bond_graphics_state=CanvasBondGraphicsState(),
        group_state=CanvasGroupState(),
        rotation_state=CanvasRotationState(),
        scene_items_state=CanvasSceneItemsState(),
        selection_info_state=SelectionInfoState.create(),
        selection_state=SelectionState(),
        text_style_state=CanvasTextStyleState(),
    )


class _FakeCanvas(SimpleNamespace):
    def __init__(self, **attributes) -> None:
        # The runtime state must exist before the property setters below run:
        # they write through the state accessors, which read it off the canvas.
        super().__init__(runtime_state=_canvas_runtime_state())
        for name, value in attributes.items():
            setattr(self, name, value)

    @property
    def atom_items(self):
        return atom_items_for(self)

    @atom_items.setter
    def atom_items(self, value) -> None:
        set_atom_items_for(self, value)

    @property
    def atom_dots(self):
        return atom_dots_for(self)

    @atom_dots.setter
    def atom_dots(self, value) -> None:
        set_atom_dots_for(self, value)

    @property
    def bond_items(self):
        return bond_items_for(self)

    @bond_items.setter
    def bond_items(self, value) -> None:
        set_bond_items_for(self, value)


def _make_canvas(**overrides):
    scene = overrides.pop("scene", _FakeScene())
    defaults = dict(
        atom_items={},
        atom_dots={},
        bond_items={},
        model=SimpleNamespace(atoms={}, bonds=[]),
        rdkit=SimpleNamespace(
            is_unavailable=mock.Mock(return_value=True),
            is_loaded=mock.Mock(return_value=False),
        ),
        renderer=SimpleNamespace(
            style=SimpleNamespace(bond_line_width=1.0, bond_length_px=20.0)
        ),
        ring_items=[],
        selected_notes=[],
        selection_outlines=[],
        selection_state=SelectionState(color=QColor("#1f5eff")),
        selection_info_callback=mock.Mock(),
        scene=lambda: scene,
        item_at_scene_pos=mock.Mock(return_value=None),
        _find_bond_near=mock.Mock(return_value=None),
        find_atom_near=mock.Mock(return_value=None),
        _distance_point_to_segment=mock.Mock(return_value=1.5),
        graph_expand_connected_atoms=mock.Mock(
            side_effect=lambda atom_ids: set(atom_ids)
        ),
        graph_connected_components=mock.Mock(return_value=[]),
        _bounding_box_center_for_atoms=mock.Mock(return_value=QPointF(5.0, 6.0)),
    )
    defaults.update(overrides)
    atom_items = defaults.pop("atom_items")
    atom_dots = defaults.pop("atom_dots")
    bond_items = defaults.pop("bond_items")
    ring_items = defaults.pop("ring_items")
    selected_notes = defaults.pop("selected_notes")
    selection_outlines = defaults.pop("selection_outlines")
    selection_info_callback = defaults.pop("selection_info_callback")
    selection_state = defaults.pop("selection_state")
    hit_testing_service = defaults.pop("hit_testing_service", None)
    graph_service = defaults.pop("graph_service", None)
    graph_expand_connected_atoms = defaults.pop("graph_expand_connected_atoms")
    graph_connected_components = defaults.pop("graph_connected_components")
    tool_controller = defaults.pop("tool_controller", SimpleNamespace(active=None))
    services = defaults.pop("services", canvas_runtime_services())
    canvas = _FakeCanvas(**defaults)
    canvas.runtime_state.selection_state = selection_state
    canvas.runtime_state.selection_info_state = SelectionInfoState(
        callback=selection_info_callback
    )
    set_atom_items_for(canvas, atom_items)
    set_atom_dots_for(canvas, atom_dots)
    set_bond_items_for(canvas, bond_items)
    seed_ring_items(canvas, ring_items)
    set_selected_notes_for(canvas, selected_notes)
    set_selection_outlines_for(canvas, selection_outlines)
    if graph_service is None:
        graph_service = SimpleNamespace(
            expand_connected_atoms=graph_expand_connected_atoms,
            connected_components=graph_connected_components,
        )
    if hit_testing_service is None:
        hit_testing_service = SimpleNamespace(
            item_at_scene_pos=canvas.item_at_scene_pos,
            nearest_atom_hit=mock.Mock(return_value=None),
            nearest_bond_hit=mock.Mock(return_value=None),
        )
    services.graph_service = graph_service
    services.hit_testing_service = hit_testing_service
    services.tool_controller = tool_controller
    if not hasattr(services, "selection"):
        # The structure service clears note selection through this port; the
        # controller under test is created after the canvas, so stand in for it.
        services.selection = SimpleNamespace(clear_note_selection=mock.Mock())
    canvas.services = services
    canvas.selection_info_callback = selection_info_callback
    return canvas


def build_selection_controller(
    canvas,
    *,
    graph_service=None,
    hit_testing_service=None,
    active_tool_name_provider=None,
    render=True,
):
    """Build the real selection owner with explicit focused-test collaborators."""
    from chemvas.ui.canvas_hit_testing_service import CanvasHitTestingService
    from chemvas.ui.canvas_view_ports import scene_pos_from_event_for_view
    from chemvas.ui.selection_controller import SelectionController

    if not hasattr(canvas, "services"):
        canvas.services = canvas_runtime_services()
    if graph_service is None:
        graph_service = getattr(canvas.services, "graph_service", None)
    if graph_service is None:
        graph_service = SimpleNamespace(
            expand_connected_atoms=lambda ids: set(ids),
            connected_components=lambda ids: [set(ids)] if ids else [],
        )
    if hit_testing_service is None:
        hit_testing_service = getattr(canvas.services, "hit_testing_service", None)
    if hit_testing_service is None:
        hit_testing_service = CanvasHitTestingService(
            canvas,
            scene_pos_mapper=lambda event: scene_pos_from_event_for_view(canvas, event),
            viewport_transform=lambda: canvas.viewportTransform(),
        )
    controller = SelectionController(
        canvas,
        graph_service=graph_service,
        hit_testing_service=hit_testing_service,
        active_tool_name_provider=active_tool_name_provider,
    )
    if not render:
        controller.outline_service = mock.Mock()
    canvas.services.selection = controller
    return controller
