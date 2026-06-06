import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen, QPolygonF
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsLineItem,
        QGraphicsPathItem,
        QGraphicsPolygonItem,
        QGraphicsScene,
        QGraphicsTextItem,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.model import Atom, Bond
    from ui.canvas_atom_graphics_state import (
        atom_dots_for,
        atom_items_for,
        set_atom_dots_for,
        set_atom_items_for,
    )
    from ui.canvas_bond_graphics_state import bond_items_for, set_bond_items_for
    from ui.canvas_scene_items_state import (
        selected_notes_for,
        set_scene_item_collection_for,
        set_selected_notes_for,
    )
    from ui.selection_hit_logic import StructureHit
    from ui.selection_info_state import SelectionInfoState
    from ui.selection_outline_state import (
        selection_outlines_for,
        set_selection_outlines_for,
    )
    from ui.selection_service_bundle import build_selection_services
    from ui.selection_style_state import SelectionStyleState


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
        self.clear_selection_calls = 0

    def selectedItems(self):
        return list(self._selected_items)

    def blockSignals(self, enabled: bool) -> None:
        self.block_signal_calls.append(enabled)

    def removeItem(self, item) -> None:
        self.removed_items.append(item)

    def clearSelection(self) -> None:
        self.clear_selection_calls += 1
        for item in self._selected_items:
            item.setSelected(False)


class _FakeShapeItem:
    def __init__(self, kind=None, *, rect: QRectF | None = None, shape: QPainterPath | None = None) -> None:
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


class _FakeCanvas(SimpleNamespace):
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
        renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=1.0, bond_length_px=20.0)),
        ring_items=[],
        selected_notes=[],
        selection_outlines=[],
        selection_style_state=SelectionStyleState(color=QColor("#1f5eff")),
        selection_info_callback=mock.Mock(),
        scene=lambda: scene,
        item_at_scene_pos=mock.Mock(return_value=None),
        _find_bond_near=mock.Mock(return_value=None),
        find_atom_near=mock.Mock(return_value=None),
        _distance_point_to_segment=mock.Mock(return_value=1.5),
        graph_expand_connected_atoms=mock.Mock(side_effect=lambda atom_ids: set(atom_ids)),
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
    defaults["selection_info_state"] = SelectionInfoState(callback=selection_info_callback)
    hit_testing_service = defaults.pop("hit_testing_service", None)
    graph_service = defaults.pop("canvas_graph_service", None)
    graph_expand_connected_atoms = defaults.pop("graph_expand_connected_atoms")
    graph_connected_components = defaults.pop("graph_connected_components")
    tool_controller = defaults.pop("tools", SimpleNamespace(active=None))
    services = defaults.pop("services", SimpleNamespace())
    canvas = _FakeCanvas(**defaults)
    set_atom_items_for(canvas, atom_items)
    set_atom_dots_for(canvas, atom_dots)
    set_bond_items_for(canvas, bond_items)
    set_scene_item_collection_for(canvas, "ring_items", ring_items)
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
    services.canvas_graph_service = graph_service
    services.hit_testing_service = hit_testing_service
    services.tools = tool_controller
    canvas.services = services
    canvas.selection_info_callback = selection_info_callback
    return canvas


def _make_selection_controller(canvas, *, hit_testing_service=None):
    services = getattr(canvas, "services", None)
    if services is None:
        services = SimpleNamespace()
        canvas.services = services
    graph_service = getattr(services, "canvas_graph_service", None)
    if graph_service is None:
        graph_service = SimpleNamespace(
            expand_connected_atoms=lambda atom_ids: set(atom_ids),
            connected_components=lambda atom_ids: [set(atom_ids)] if atom_ids else [],
        )
        services.canvas_graph_service = graph_service
    if hit_testing_service is None:
        hit_testing_service = getattr(services, "hit_testing_service", None)

    def active_tool_name() -> str | None:
        active_tool = getattr(getattr(services, "tools", None), "active", None)
        name = getattr(active_tool, "name", None)
        return str(name) if name else None

    return build_selection_services(
        canvas,
        graph_service=graph_service,
        hit_testing_service=hit_testing_service,
        active_tool_name_provider=active_tool_name,
    ).selection_controller


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for selection controller tests")
class SelectionControllerAdditionalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_structure_hit_and_item_helpers_cover_atom_bond_ring_and_other(self) -> None:
        atom_item = _FakeItem("atom", data1=1)
        bad_atom_item = _FakeItem("atom", data1="x")
        bond_item = _FakeItem("bond", data1=0)
        deleted_bond_item = _FakeItem("bond", data1=1)
        bad_bond_item = _FakeItem("bond", data1=9)
        ring_item = _FakeItem("ring", data2=[1, 2, 3])
        bare_ring_item = _FakeItem("ring", data2="bad")
        other_item = _FakeItem("note")
        canvas = _make_canvas(
            atom_items={1: atom_item},
            atom_dots={2: _FakeItem("atom", data1=2)},
            bond_items={0: [bond_item]},
            model=SimpleNamespace(atoms={}, bonds=[Bond(1, 2, 1), None]),
        )
        controller = _make_selection_controller(canvas)

        self.assertEqual(controller.structure_hit_from_item(None), (None, None, None))
        self.assertEqual(controller.structure_hit_from_item(atom_item)[0], StructureHit(kind="atom", id=1))
        self.assertEqual(controller.structure_hit_from_item(bad_atom_item), (None, None, None))
        self.assertEqual(controller.structure_hit_from_item(bond_item)[0], StructureHit(kind="bond", id=0))
        self.assertEqual(controller.structure_hit_from_item(bond_item)[1], (1, 2))
        self.assertEqual(controller.structure_hit_from_item(deleted_bond_item), (None, None, None))
        self.assertEqual(controller.structure_hit_from_item(bad_bond_item), (None, None, None))
        self.assertEqual(controller.structure_hit_from_item(ring_item)[0], StructureHit(kind="ring"))
        self.assertEqual(controller.structure_hit_from_item(ring_item)[2], [1, 2, 3])
        self.assertEqual(controller.structure_hit_from_item(bare_ring_item)[0], StructureHit(kind="ring"))
        self.assertEqual(controller.structure_hit_from_item(other_item)[0], StructureHit(kind="other"))

        self.assertIs(controller.structure_item_for_hit(StructureHit(kind="atom", id=1)), atom_item)
        self.assertIs(controller.structure_item_for_hit(StructureHit(kind="atom", id=2)), canvas.atom_dots[2])
        self.assertIs(controller.structure_item_for_hit(StructureHit(kind="bond", id=0)), bond_item)
        self.assertIsNone(controller.structure_item_for_hit(StructureHit(kind="bond", id=5)))
        self.assertIsNone(controller.structure_item_for_hit(StructureHit(kind="ring")))

    def test_selection_targets_and_toggle_item_selection_cover_target_resolution(self) -> None:
        scene = _FakeScene()
        atom_target = _FakeItem("atom", data1=1, selected=False)
        bond_target = _FakeItem("bond", data1=0, selected=True)
        overlay_item = _FakeItem("orbital")
        canvas = _make_canvas(
            scene=scene,
            atom_items={1: atom_target},
            bond_items={0: [bond_target, None]},
        )
        controller = _make_selection_controller(canvas)
        controller.update_selection_outline = mock.Mock()

        self.assertEqual(controller.selection_targets_for_item(_FakeItem("atom", data1=1)), [atom_target])
        self.assertEqual(controller.selection_targets_for_item(_FakeItem("bond", data1=0)), [bond_target])
        self.assertEqual(controller.selection_targets_for_item(overlay_item), [overlay_item])
        self.assertEqual(controller.selection_targets_for_item(None), [])
        self.assertEqual(controller.selection_targets_for_item(_FakeItem("atom", data1="bad")), [])
        self.assertEqual(controller.selection_targets_for_item(_FakeItem("bond", data1="bad")), [])
        self.assertEqual(controller.selection_targets_for_item(_FakeItem("unknown")), [])

        self.assertTrue(controller.toggle_item_selection(_FakeItem("atom", data1=1)))
        self.assertTrue(atom_target.isSelected())
        self.assertEqual(scene.block_signal_calls[:2], [True, False])

        self.assertTrue(controller.toggle_item_selection(_FakeItem("bond", data1=0)))
        self.assertFalse(bond_target.isSelected())
        self.assertEqual(controller.update_selection_outline.call_count, 2)

        self.assertFalse(controller.toggle_item_selection(_FakeItem("atom", data1="bad")))

    def test_nearest_hit_helpers_delegate_to_hit_testing_service(self) -> None:
        service = SimpleNamespace(
            scene_pos_from_event=mock.Mock(),
            item_at_scene_pos=mock.Mock(),
            item_at_event=mock.Mock(),
            grid_cell_size=mock.Mock(),
            cell_coords=mock.Mock(),
            ensure_spatial_index=mock.Mock(),
            rebuild_spatial_index=mock.Mock(),
            find_atom_near=mock.Mock(),
            find_bond_near=mock.Mock(),
            distance_point_to_segment=mock.Mock(),
            nearest_atom_hit=mock.Mock(return_value=(1, 1.25)),
            nearest_bond_hit=mock.Mock(return_value=(2, 2.5)),
            bond_id_from_event=mock.Mock(),
        )
        canvas = _make_canvas(hit_testing_service=service)
        controller = _make_selection_controller(canvas)
        pos = QPointF(3.0, 4.0)

        self.assertEqual(controller.preference_service.nearest_atom_hit(pos), (1, 1.25))
        self.assertEqual(controller.preference_service.nearest_bond_hit(pos), (2, 2.5))
        service.nearest_atom_hit.assert_called_once_with(pos)
        service.nearest_bond_hit.assert_called_once_with(pos)

    def test_item_lookup_delegates_to_hit_testing_service_when_available(self) -> None:
        service = SimpleNamespace(item_at_scene_pos=mock.Mock(return_value="hit-item"))
        canvas = _FakeCanvas(
            atom_items={},
            atom_dots={},
            item_at_scene_pos=mock.Mock(side_effect=AssertionError("canvas facade should not be used")),
        )
        controller = _make_selection_controller(canvas, hit_testing_service=service)
        pos = QPointF(3.0, 4.0)

        self.assertEqual(controller.preference_service.item_at_scene_pos(pos), "hit-item")

        service.item_at_scene_pos.assert_called_once_with(pos)
        canvas.item_at_scene_pos.assert_not_called()

    def test_item_lookup_delegates_to_services_hit_testing_service_when_available(self) -> None:
        service = SimpleNamespace(item_at_scene_pos=mock.Mock(return_value="hit-item"))
        canvas = SimpleNamespace(
            atom_items={},
            atom_dots={},
            services=SimpleNamespace(hit_testing_service=service),
            item_at_scene_pos=mock.Mock(side_effect=AssertionError("canvas facade should not be used")),
        )
        controller = _make_selection_controller(canvas)
        pos = QPointF(3.0, 4.0)

        self.assertEqual(controller.preference_service.item_at_scene_pos(pos), "hit-item")

        service.item_at_scene_pos.assert_called_once_with(pos)
        canvas.item_at_scene_pos.assert_not_called()

    def test_preferred_structure_hit_at_scene_pos_prefers_atom_hit_ring_atom_and_fallback(self) -> None:
        atom_item = _FakeItem("atom", data1=1)
        ring_item = _FakeItem("ring", data2=[1, 2, 3])
        bare_ring_item = _FakeItem("ring", data2="bad")
        fallback_item = _FakeItem("note")
        canvas = _make_canvas(
            atom_items={1: atom_item},
            item_at_scene_pos=mock.Mock(return_value=atom_item),
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0)}, bonds=[]),
        )
        controller = _make_selection_controller(canvas)
        self.assertEqual(controller.preferred_structure_hit_at_scene_pos(QPointF(0.0, 0.0)), StructureHit(kind="atom", id=1))

        ring_canvas = _make_canvas(
            atom_items={2: _FakeItem("atom", data1=2)},
            item_at_scene_pos=mock.Mock(return_value=ring_item),
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 2.0, 0.0),
                    3: Atom("C", 1.0, 2.0),
                },
                bonds=[],
            ),
        )
        ring_controller = _make_selection_controller(ring_canvas)
        with (
            mock.patch("ui.selection_preference_service.choose_preferred_structure_hit", return_value=None),
            mock.patch("ui.selection_preference_service.nearest_ring_atom_id", return_value=2),
        ):
            self.assertEqual(
                ring_controller.preferred_structure_hit_at_scene_pos(QPointF(1.5, 0.2)),
                StructureHit(kind="atom", id=2),
            )

        no_item_ring_canvas = _make_canvas(
            atom_items={},
            atom_dots={},
            item_at_scene_pos=mock.Mock(return_value=ring_item),
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 2.0, 0.0),
                    3: Atom("C", 1.0, 2.0),
                },
                bonds=[],
            ),
        )
        no_item_ring_controller = _make_selection_controller(no_item_ring_canvas)
        with (
            mock.patch("ui.selection_preference_service.choose_preferred_structure_hit", return_value=None),
            mock.patch("ui.selection_preference_service.nearest_ring_atom_id", return_value=2),
        ):
            self.assertEqual(
                no_item_ring_controller.preferred_structure_hit_at_scene_pos(QPointF(1.5, 0.2)),
                StructureHit(kind="ring"),
            )

        fallback_canvas = _make_canvas(
            item_at_scene_pos=mock.Mock(return_value=fallback_item),
            model=SimpleNamespace(atoms={}, bonds=[]),
        )
        fallback_controller = _make_selection_controller(fallback_canvas)
        with mock.patch("ui.selection_preference_service.choose_preferred_structure_hit", return_value=None):
            self.assertEqual(
                fallback_controller.preferred_structure_hit_at_scene_pos(QPointF(0.0, 0.0)),
                StructureHit(kind="other"),
            )

        bare_ring_canvas = _make_canvas(
            atom_items={},
            atom_dots={},
            item_at_scene_pos=mock.Mock(return_value=bare_ring_item),
            model=SimpleNamespace(atoms={}, bonds=[]),
        )
        bare_ring_controller = _make_selection_controller(bare_ring_canvas)
        with mock.patch("ui.selection_preference_service.choose_preferred_structure_hit", return_value=None):
            self.assertEqual(
                bare_ring_controller.preferred_structure_hit_at_scene_pos(QPointF(0.0, 0.0)),
                StructureHit(kind="ring"),
            )

        ring_fallback_canvas = _make_canvas(
            atom_items={},
            atom_dots={},
            item_at_scene_pos=mock.Mock(return_value=ring_item),
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 2.0, 0.0),
                    3: Atom("C", 1.0, 2.0),
                },
                bonds=[],
            ),
        )
        ring_fallback_controller = _make_selection_controller(ring_fallback_canvas)
        with (
            mock.patch("ui.selection_preference_service.choose_preferred_structure_hit", return_value=None),
            mock.patch("ui.selection_preference_service.nearest_ring_atom_id", return_value=None),
        ):
            self.assertEqual(
                ring_fallback_controller.preferred_structure_hit_at_scene_pos(QPointF(1.5, 0.2)),
                StructureHit(kind="ring"),
            )

        missing_preferred_item_canvas = _make_canvas(
            item_at_scene_pos=mock.Mock(return_value=fallback_item),
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0)}, bonds=[]),
        )
        missing_preferred_item_controller = _make_selection_controller(missing_preferred_item_canvas)
        with mock.patch(
            "ui.selection_preference_service.choose_preferred_structure_hit",
            return_value=StructureHit(kind="atom", id=1),
        ):
            self.assertEqual(
                missing_preferred_item_controller.preferred_structure_hit_at_scene_pos(QPointF(0.0, 0.0)),
                StructureHit(kind="other"),
            )

    def test_preferred_structure_item_at_scene_pos_returns_hit_item_or_original_item(self) -> None:
        ring_item = _FakeItem("ring")
        canvas = _make_canvas(item_at_scene_pos=mock.Mock(return_value=ring_item))
        controller = _make_selection_controller(canvas)
        controller.preference_service.preferred_structure_item_at_scene_pos = mock.Mock(return_value="atom-item")
        self.assertEqual(controller.preferred_structure_item_at_scene_pos(QPointF(0.0, 0.0)), "atom-item")

        controller.preference_service.preferred_structure_item_at_scene_pos = mock.Mock(return_value=ring_item)
        self.assertIs(controller.preferred_structure_item_at_scene_pos(QPointF(1.0, 1.0)), ring_item)

        controller.preference_service.preferred_structure_item_at_scene_pos = mock.Mock(return_value=None)
        self.assertIsNone(controller.preferred_structure_item_at_scene_pos(QPointF(2.0, 2.0)))

    def test_select_structure_for_item_selects_structure_and_overlay_items(self) -> None:
        atom_item = _FakeItem("atom", data1=1)
        atom_item_2 = _FakeItem("atom", data1=2)
        bond_item = _FakeItem("bond", data1=0)
        deleted_bond_item = _FakeItem("bond", data1=1)
        bond_graphic = _FakeItem("bond")
        ring_item = _FakeItem("ring", data2=[1, 2])
        unrelated_ring_item = _FakeItem("ring", data2=[1, 3])
        note_item = _FakeItem("note")
        scene = _FakeScene([atom_item, bond_item, ring_item, unrelated_ring_item, note_item])
        canvas = _make_canvas(
            scene=scene,
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 2.0, 0.0), 3: Atom("N", 4.0, 0.0)},
                bonds=[Bond(1, 2, 1), None, Bond(1, 3, 1)],
            ),
            atom_items={1: atom_item, 2: atom_item_2},
            atom_dots={},
            bond_items={0: [bond_graphic], 2: [_FakeItem("bond")]},
            ring_items=[ring_item, unrelated_ring_item],
            graph_expand_connected_atoms=mock.Mock(return_value={1, 2}),
            _update_selection_outline=mock.Mock(),
        )
        controller = _make_selection_controller(canvas)
        controller.update_selection_outline = mock.Mock()

        self.assertTrue(controller.select_structure_for_item(atom_item))
        self.assertEqual(scene.clear_selection_calls, 1)
        self.assertTrue(atom_item.isSelected())
        self.assertTrue(atom_item_2.isSelected())
        self.assertTrue(bond_graphic.isSelected())
        self.assertTrue(ring_item.isSelected())
        self.assertFalse(unrelated_ring_item.isSelected())
        controller.update_selection_outline.assert_called_once_with()

        scene.clear_selection_calls = 0
        controller.update_selection_outline.reset_mock()
        self.assertTrue(controller.select_structure_for_item(note_item))
        self.assertEqual(scene.clear_selection_calls, 1)
        self.assertTrue(note_item.isSelected())
        controller.update_selection_outline.assert_not_called()

        invalid_atom = _FakeItem("atom", data1="bad")
        self.assertFalse(controller.select_structure_for_item(invalid_atom))
        self.assertFalse(controller.select_structure_for_item(_FakeItem("bond", data1=99)))
        self.assertFalse(controller.select_structure_for_item(deleted_bond_item))
        self.assertFalse(controller.select_structure_for_item(_FakeItem("ring", data2="bad")))
        self.assertFalse(controller.select_structure_for_item(_FakeItem("unknown")))
        self.assertFalse(controller.select_structure_for_item(None))

        empty_ring_canvas = _make_canvas(
            scene=_FakeScene(),
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0)}, bonds=[]),
            atom_items={1: atom_item},
            atom_dots={},
            bond_items={},
            ring_items=[],
            graph_expand_connected_atoms=lambda atom_ids: atom_ids,
            _update_selection_outline=mock.Mock(),
        )
        empty_ring_controller = _make_selection_controller(empty_ring_canvas)
        self.assertFalse(empty_ring_controller.select_structure_for_item(_FakeItem("ring", data2=[9, "bad"])))

        sparse_canvas = _make_canvas(
            scene=_FakeScene(),
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 2.0, 0.0)}, bonds=[Bond(1, 2, 1)]),
            atom_items={1: atom_item},
            atom_dots={},
            bond_items={0: [bond_graphic]},
            ring_items=[],
            graph_expand_connected_atoms=mock.Mock(return_value={1, 2}),
            _update_selection_outline=mock.Mock(),
        )
        sparse_controller = _make_selection_controller(sparse_canvas)
        self.assertTrue(sparse_controller.select_structure_for_item(_FakeItem("atom", data1=1)))
        self.assertTrue(atom_item.isSelected())

    def test_public_selection_helper_methods_cover_overlay_and_geometry_paths(self) -> None:
        atom_target = _FakeItem("atom", data1=1)
        controller = _make_selection_controller(_make_canvas(atom_items={1: atom_target}))
        center = QPointF(6.0, 7.0)
        color = QColor("#123456")
        empty_snapshot = SimpleNamespace(selected_atom_ids=set(), selected_bond_ids=set(), selection_items=[])

        controller.structure_service.structure_hit_from_item = mock.Mock(return_value=("hit", None, None))
        controller.structure_service.structure_item_for_hit = mock.Mock(return_value="item")
        controller.structure_service.selection_targets_for_item = mock.Mock(return_value=[atom_target])
        controller.hit_test_service.selection_rects_for_snapshot = mock.Mock(return_value=())
        controller.outline_service.selection_line_stroke_path = mock.Mock(return_value="line-path")
        controller.outline_service.selection_path_for_bond_item = mock.Mock(return_value="bond-item-path")
        controller.outline_service.selection_path_for_bond = mock.Mock(return_value="bond-path")
        controller.outline_service.selection_path_for_object_item = mock.Mock(return_value="object-path")
        controller.outline_service.add_selection_object_overlay = mock.Mock()
        controller.outline_service.add_selection_component_overlay = mock.Mock()
        controller.outline_service.selection_center_for_atoms = mock.Mock(return_value=center)
        controller.outline_service.selection_center_marker_enabled = mock.Mock(return_value=True)
        controller.outline_service.add_selection_center_marker = mock.Mock()
        target_item = _FakeItem("atom", data1=1)

        self.assertEqual(controller.structure_hit_from_item("item"), ("hit", None, None))
        self.assertEqual(controller.structure_item_for_hit("hit"), "item")
        self.assertEqual(controller.selection_targets_for_item(target_item), [atom_target])
        self.assertEqual(controller.selection_rects_for_snapshot(empty_snapshot), ())
        self.assertEqual(controller.selection_line_stroke_path(QPointF(), QPointF(1.0, 1.0), 2.0), "line-path")
        self.assertEqual(controller.selection_path_for_bond_item("bond-item", width=3.0), "bond-item-path")
        self.assertEqual(controller.selection_path_for_bond(4), "bond-path")
        self.assertEqual(controller.selection_path_for_object_item("object"), "object-path")
        controller.add_selection_object_overlay("object", color)
        controller.add_selection_component_overlay({1}, {2}, color, 1.5)
        self.assertEqual(controller.selection_center_for_atoms({1, 2}), center)
        self.assertTrue(controller.selection_center_marker_enabled())
        controller.add_selection_center_marker(center)

        controller.structure_service.structure_hit_from_item.assert_called_once_with("item")
        controller.structure_service.structure_item_for_hit.assert_called_once_with("hit")
        controller.structure_service.selection_targets_for_item.assert_called_once_with(target_item)
        controller.hit_test_service.selection_rects_for_snapshot.assert_called_once_with(empty_snapshot)
        controller.outline_service.selection_line_stroke_path.assert_called_once_with(QPointF(), QPointF(1.0, 1.0), 2.0)
        controller.outline_service.selection_path_for_bond_item.assert_called_once_with("bond-item", width=3.0)
        controller.outline_service.selection_path_for_bond.assert_called_once_with(4)
        controller.outline_service.selection_path_for_object_item.assert_called_once_with("object")
        controller.outline_service.add_selection_object_overlay.assert_called_once_with("object", color)
        controller.outline_service.add_selection_component_overlay.assert_called_once_with({1}, {2}, color, 1.5)
        controller.outline_service.selection_center_for_atoms.assert_called_once_with({1, 2})
        controller.outline_service.selection_center_marker_enabled.assert_called_once_with()
        controller.outline_service.add_selection_center_marker.assert_called_once_with(center)

    def test_note_selection_helpers_manage_selected_notes_and_selection_boxes(self) -> None:
        scene = QGraphicsScene()
        note_a = QGraphicsTextItem("A")
        note_b = QGraphicsTextItem("B")
        scene.addItem(note_a)
        scene.addItem(note_b)
        canvas = SimpleNamespace(
            note_padding=6.0,
            selection_style_state=SelectionStyleState(
                color=QColor("#1f5eff"),
                stroke_delta=0.8,
            ),
            clear_note_selection=None,
        )
        set_selected_notes_for(canvas, [note_a])
        controller = _make_selection_controller(canvas)
        canvas.clear_note_selection = controller.clear_note_selection
        canvas.services = SimpleNamespace(selection_controller=controller)

        controller.select_note(note_b, additive=False)
        self.assertEqual(selected_notes_for(canvas), [note_b])
        self.assertTrue(note_a.data(21) is None or not note_a.data(21).isVisible())
        self.assertTrue(note_b.data(21).isVisible())

        controller.select_note(note_a, additive=True)
        self.assertEqual(selected_notes_for(canvas), [note_b, note_a])

        controller.select_note(note_a, additive=True)
        self.assertEqual(selected_notes_for(canvas), [note_b, note_a])

        controller.toggle_note_selection(note_b)
        self.assertEqual(selected_notes_for(canvas), [note_a])
        self.assertFalse(note_b.data(21).isVisible())

        controller.toggle_note_selection(note_b)
        self.assertEqual(selected_notes_for(canvas), [note_a, note_b])
        self.assertTrue(note_b.data(21).isVisible())

        controller.clear_note_selection()
        self.assertEqual(selected_notes_for(canvas), [])
        self.assertFalse(note_a.data(21).isVisible())

    def test_selection_rects_and_hit_test_build_request_from_snapshot(self) -> None:
        note_item = _FakeItem("note", rect=QRectF(5.0, 6.0, 7.0, 8.0))
        arrow_item = _FakeItem("arrow", rect=QRectF(9.0, 9.0, 2.0, 2.0))
        atom_item = _FakeItem("atom", data1=1)
        selected_bond_item = _FakeItem("bond", data1=0, selected=True)
        outline = _FakeItem("selection_outline", data2={"kind": "component"}, contains=True)
        snapshot = SimpleNamespace(
            selected_atom_ids={1, 2},
            selected_bond_ids={0},
            selection_items=[note_item, arrow_item, atom_item],
        )
        canvas = _make_canvas(
            selection_outlines=[outline],
            item_at_scene_pos=mock.Mock(return_value=selected_bond_item),
            graph_connected_components=mock.Mock(return_value=[{1, 2}]),
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 2.0, 0.0)}, bonds=[Bond(1, 2, 1)]),
        )
        controller = _make_selection_controller(canvas)

        rects = controller.selection_rects_for_snapshot(snapshot)
        self.assertEqual(len(rects), 2)
        self.assertEqual((rects[0].left, rects[0].top, rects[0].right, rects[0].bottom), (0.0, 0.0, 2.0, 0.0))
        self.assertEqual((rects[1].left, rects[1].top, rects[1].right, rects[1].bottom), (5.0, 6.0, 12.0, 14.0))

        with mock.patch("ui.selection_hit_test_service.selection_hit_matches", return_value=True) as matches:
            self.assertTrue(controller.selection_hit_test(QPointF(4.0, 5.0), snapshot=snapshot))

        request = matches.call_args.args[0]
        self.assertTrue(request.outline_hit)
        self.assertEqual(request.hit, StructureHit(kind="bond", id=0))
        self.assertTrue(request.item_is_selected)
        self.assertEqual(request.selected_atom_ids, {1, 2})
        self.assertEqual(request.selected_bond_ids, {0})

        none_bounds_canvas = _make_canvas(
            graph_connected_components=mock.Mock(return_value=[{1, 2}]),
            model=SimpleNamespace(atoms={}, bonds=[], bounds=mock.Mock(return_value=None)),
        )
        none_bounds_controller = _make_selection_controller(none_bounds_canvas)
        self.assertEqual(
            none_bounds_controller.selection_rects_for_snapshot(
                SimpleNamespace(selected_atom_ids={1, 2}, selected_bond_ids=set(), selection_items=[])
            ),
            (),
        )

        none_snapshot_canvas = _make_canvas()
        none_snapshot_controller = _make_selection_controller(none_snapshot_canvas)
        self.assertFalse(none_snapshot_controller.selection_hit_test(QPointF(1.0, 2.0)))

    def test_update_selection_outline_covers_suspend_clear_filtered_and_overlay_paths(self) -> None:
        suspended_canvas = _make_canvas(selection_style_state=SelectionStyleState(suspend_outline=True))
        _make_selection_controller(suspended_canvas).update_selection_outline()
        suspended_canvas.selection_info_callback.assert_not_called()

        empty_outline = _FakeItem("selection_outline")
        empty_scene = _FakeScene([])
        empty_canvas = _make_canvas(scene=empty_scene, selection_outlines=[empty_outline])
        _make_selection_controller(empty_canvas).update_selection_outline()
        self.assertEqual(empty_scene.removed_items, [empty_outline])
        self.assertEqual(selection_outlines_for(empty_canvas), [])
        empty_canvas.selection_info_callback.assert_called_once_with("", "")

        filtered_scene = _FakeScene([_FakeItem("handle")])
        filtered_canvas = _make_canvas(scene=filtered_scene, selection_outlines=[_FakeItem("selection_outline")])
        _make_selection_controller(filtered_canvas).update_selection_outline()
        filtered_canvas.selection_info_callback.assert_not_called()

        atom_item = _FakeItem("atom", data1=1)
        bond_item = _FakeItem("bond", data1=0)
        object_item = _FakeItem("arrow")
        old_outline = _FakeItem("selection_outline")
        active_scene = _FakeScene([atom_item, bond_item, object_item])
        active_canvas = _make_canvas(
            scene=active_scene,
            selection_outlines=[old_outline],
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 2.0, 0.0)}, bonds=[Bond(1, 2, 1)]),
            graph_connected_components=mock.Mock(return_value=[{1, 2}]),
        )
        controller = _make_selection_controller(active_canvas)
        controller.outline_service.add_selection_component_overlay = mock.Mock()
        controller.outline_service.selection_center_for_atoms = mock.Mock(return_value=QPointF(1.0, 0.0))
        controller.outline_service.selection_center_marker_enabled = mock.Mock(return_value=True)
        controller.outline_service.add_selection_center_marker = mock.Mock()
        controller.outline_service.add_selection_object_overlay = mock.Mock()

        controller.update_selection_outline()

        self.assertEqual(active_scene.removed_items, [old_outline])
        controller.outline_service.add_selection_component_overlay.assert_called_once()
        self.assertEqual(controller.outline_service.add_selection_component_overlay.call_args.args[0], {1, 2})
        self.assertEqual(controller.outline_service.add_selection_component_overlay.call_args.args[1], {0})
        controller.outline_service.add_selection_center_marker.assert_called_once_with(QPointF(1.0, 0.0))
        controller.outline_service.add_selection_object_overlay.assert_called_once_with(object_item, mock.ANY)
        active_canvas.selection_info_callback.assert_called_once_with("", "")

        deleted_bond_scene = _FakeScene([_FakeItem("bond", data1=-1), _FakeItem("bond", data1=1), _FakeItem("arrow")])
        deleted_bond_canvas = _make_canvas(
            scene=deleted_bond_scene,
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 2.0, 0.0)}, bonds=[Bond(1, 2, 1), None]),
            graph_connected_components=mock.Mock(return_value=[]),
        )
        deleted_bond_controller = _make_selection_controller(deleted_bond_canvas)
        deleted_bond_controller.outline_service.add_selection_component_overlay = mock.Mock()
        deleted_bond_controller.outline_service.selection_center_for_atoms = mock.Mock(return_value=None)
        deleted_bond_controller.outline_service.selection_center_marker_enabled = mock.Mock(return_value=False)
        deleted_bond_controller.outline_service.add_selection_object_overlay = mock.Mock()
        deleted_bond_controller.update_selection_outline()
        deleted_bond_controller.outline_service.add_selection_component_overlay.assert_not_called()
        deleted_bond_controller.outline_service.add_selection_object_overlay.assert_called_once()

    def test_shift_selection_outlines_and_center_helpers_cover_simple_branches(self) -> None:
        outline = _FakeItem("selection_outline")
        canvas = _make_canvas(
            selection_outlines=[outline],
            tools=SimpleNamespace(active=SimpleNamespace(name="perspective")),
            model=SimpleNamespace(
                atoms={1: Atom("C", 2.0, 3.0), 2: Atom("C", 8.0, 9.0)},
                bonds=[],
            ),
        )
        controller = _make_selection_controller(canvas)

        controller.shift_selection_outlines(3.0, -2.0)
        self.assertEqual(outline.moves, [(3.0, -2.0)])

        self.assertIsNone(controller.selection_center_for_atoms({1}))
        self.assertEqual(controller.selection_center_for_atoms({1, 2}), QPointF(5.0, 6.0))
        self.assertTrue(controller.selection_center_marker_enabled())

        canvas.services.tools = SimpleNamespace(active=SimpleNamespace(name="select"))
        self.assertFalse(controller.selection_center_marker_enabled())

        empty_controller = _make_selection_controller(_make_canvas(selection_outlines=[]))
        empty_controller.shift_selection_outlines(1.0, 2.0)

    def test_selection_path_and_overlay_helpers_cover_guard_and_shape_fallback_paths(self) -> None:
        scene = QGraphicsScene()
        canvas = _FakeCanvas(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=1.0, bond_length_px=20.0, bond_spacing_px=4.0)),
            scene=lambda: scene,
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 10.0, 0.0)},
                bonds=[Bond(1, 2, 2), None],
            ),
            services=SimpleNamespace(
                scene_decoration_build_service=SimpleNamespace(mark_center=lambda item: QPointF(4.0, 5.0)),
                geometry_controller=SimpleNamespace(
                    ring_center_for_bond=lambda bond: None,
                    trim_line_for_labels=lambda *_args: (0.0, 1.0),
                ),
                tools=SimpleNamespace(active=SimpleNamespace(name="perspective")),
            ),
        )
        set_bond_items_for(canvas, {})
        set_selection_outlines_for(canvas, [])
        controller = _make_selection_controller(canvas)

        line_item = QGraphicsLineItem(0.0, 0.0, 10.0, 0.0)
        polygon_item = QGraphicsPolygonItem(QPolygonF([QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(5.0, 2.0)]))
        filled_path = QPainterPath()
        filled_path.addRect(0.0, 0.0, 10.0, 2.0)
        path_item = QGraphicsPathItem(filled_path)
        path_item.setPen(QPen(Qt.PenStyle.NoPen))
        path_item.setBrush(QBrush(QColor("#445566")))
        stroked_path = QGraphicsPathItem(filled_path)
        stroked_path.setPen(QPen(QColor("#112233"), 1.2))
        text_item = QGraphicsTextItem("note")
        empty_shape_item = _FakeShapeItem("orbital", rect=QRectF(1.0, 2.0, 4.0, 5.0))

        self.assertFalse(controller.selection_line_stroke_path(QPointF(0.0, 0.0), QPointF(10.0, 0.0), 4.0).isEmpty())
        self.assertFalse(controller.selection_path_for_bond_item(line_item, width=4.0).isEmpty())
        self.assertFalse(controller.selection_path_for_bond_item(polygon_item).isEmpty())
        self.assertFalse(controller.selection_path_for_bond_item(path_item).isEmpty())
        self.assertFalse(controller.selection_path_for_bond_item(stroked_path).isEmpty())
        self.assertTrue(controller.selection_path_for_bond_item(object()).isEmpty())
        self.assertTrue(controller.selection_path_for_bond(-1).isEmpty())
        self.assertTrue(controller.selection_path_for_bond(1).isEmpty())

        line_item_a = QGraphicsLineItem(0.0, -2.0, 10.0, -2.0)
        line_item_b = QGraphicsLineItem(0.0, 2.0, 10.0, 2.0)
        canvas.bond_items[0] = [line_item_a, line_item_b]
        self.assertFalse(controller.selection_path_for_bond(0).isEmpty())

        canvas.services.geometry_controller.ring_center_for_bond = lambda bond: QPointF(5.0, 0.0)
        canvas.bond_items[0] = [object()]
        self.assertTrue(controller.selection_path_for_bond(0).isEmpty())

        canvas.model = SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0)}, bonds=[Bond(1, 2, 2)])
        canvas.bond_items[0] = [QGraphicsLineItem(0.0, 0.0, 10.0, 0.0), QGraphicsLineItem(0.0, 2.0, 10.0, 2.0)]
        canvas.services.geometry_controller.ring_center_for_bond = lambda bond: None
        self.assertFalse(controller.selection_path_for_bond(0).isEmpty())

        canvas.model = SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 0.0, 0.0)}, bonds=[Bond(1, 2, 2)])
        canvas.bond_items[0] = [QGraphicsLineItem(0.0, 0.0, 10.0, 0.0), QGraphicsLineItem(0.0, 2.0, 10.0, 2.0)]
        self.assertFalse(controller.selection_path_for_bond(0).isEmpty())

        self.assertFalse(controller.selection_path_for_object_item(_FakeItem("mark")).isEmpty())
        arrow_path_item = QGraphicsPathItem(filled_path)
        arrow_path_item.setData(0, "arrow")
        arrow_path_item.setPen(QPen(QColor("#112233"), 1.2))
        self.assertFalse(controller.selection_path_for_object_item(arrow_path_item).isEmpty())
        self.assertFalse(controller.selection_path_for_object_item(text_item).isEmpty())
        self.assertFalse(controller.selection_path_for_object_item(empty_shape_item).isEmpty())

        controller.outline_service.selection_path_for_object_item = mock.Mock(return_value=QPainterPath())
        controller.add_selection_object_overlay(_FakeItem("arrow"), QColor("#abcdef"))
        self.assertEqual(selection_outlines_for(canvas), [])

        controller.outline_service.selection_path_for_object_item = mock.Mock(
            return_value=controller.selection_line_stroke_path(QPointF(0.0, 0.0), QPointF(5.0, 0.0), 3.0)
        )
        controller.add_selection_object_overlay(_FakeItem("arrow"), QColor("#abcdef"))
        self.assertEqual(len(selection_outlines_for(canvas)), 1)

        controller.outline_service.selection_path_for_bond = mock.Mock(return_value=QPainterPath())
        controller.add_selection_component_overlay({1}, {0}, QColor("#334455"), 1.0)
        self.assertEqual(len(selection_outlines_for(canvas)), 2)

        non_empty_bond_path = controller.selection_line_stroke_path(QPointF(0.0, 0.0), QPointF(10.0, 0.0), 4.0)
        controller.outline_service.selection_path_for_bond = mock.Mock(return_value=non_empty_bond_path)
        controller.add_selection_component_overlay({1}, {0}, QColor("#334455"), 1.0)
        self.assertEqual(len(selection_outlines_for(canvas)), 3)

        self.assertEqual(controller.selection_center_for_atoms({1, 2}), QPointF(0.0, 0.0))
        self.assertTrue(controller.selection_center_marker_enabled())
        controller.add_selection_center_marker(QPointF(5.0, 5.0))
        self.assertEqual(len(selection_outlines_for(canvas)), 5)


if __name__ == "__main__":
    unittest.main()
