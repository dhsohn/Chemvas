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
    from chemvas.domain.document import Atom, Bond
    from chemvas.ui.canvas_bond_graphics_state import set_bond_items_for
    from chemvas.ui.selection_outline_service import SelectionOutlineService
    from chemvas.ui.selection_outline_state import (
        selection_outlines_for,
        set_selection_outlines_for,
    )
    from chemvas.ui.selection_style_state import SelectionStyleState

    from tests.test_selection_controller_additional import (
        _FakeCanvas,
        _FakeItem,
        _FakeScene,
        _FakeShapeItem,
        _make_canvas,
    )


def _outline_service(canvas):
    graph_service = getattr(
        getattr(canvas, "services", None), "canvas_graph_service", None
    )
    if graph_service is None:
        graph_service = SimpleNamespace(
            graph=SimpleNamespace(atom_bond_ids={}),
            connected_components=lambda atom_ids: [set(atom_ids)] if atom_ids else [],
        )
    elif getattr(graph_service, "graph", None) is None:
        graph_service.graph = SimpleNamespace(atom_bond_ids={})

    def active_tool_name() -> str | None:
        active_tool = getattr(getattr(canvas.services, "tools", None), "active", None)
        name = getattr(active_tool, "name", None)
        return str(name) if name else None

    return SelectionOutlineService(
        canvas,
        graph_service=graph_service,
        active_tool_name_provider=active_tool_name,
    )


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for selection outline service tests"
)
class SelectionOutlineServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_update_selection_outline_draws_group_box_for_notes_only_selection(
        self,
    ) -> None:
        # A notes-only group has no QGraphicsScene-selected items, but its
        # dashed group box must still be drawn after Ctrl+G.
        scene = _FakeScene([])
        canvas = _make_canvas(scene=scene)
        service = _outline_service(canvas)
        service.add_selection_group_overlay = mock.Mock()
        group_rect = QRectF(0.0, 0.0, 30.0, 20.0)
        with mock.patch(
            "chemvas.ui.selection_outline_service.selected_group_rects_for",
            return_value=[group_rect],
        ):
            service.update_selection_outline()

        service.add_selection_group_overlay.assert_called_once_with(group_rect)
        canvas.selection_info_callback.assert_called_once()

    def test_update_selection_outline_handles_suspend_clear_and_overlay_dispatch(
        self,
    ) -> None:
        suspended_canvas = _make_canvas(
            selection_style_state=SelectionStyleState(suspend_outline=True)
        )
        _outline_service(suspended_canvas).update_selection_outline()
        suspended_canvas.selection_info_callback.assert_not_called()

        empty_outline = _FakeItem("selection_outline")
        empty_scene = _FakeScene([])
        empty_canvas = _make_canvas(
            scene=empty_scene, selection_outlines=[empty_outline]
        )
        _outline_service(empty_canvas).update_selection_outline()
        self.assertEqual(empty_scene.removed_items, [empty_outline])
        self.assertEqual(selection_outlines_for(empty_canvas), [])
        empty_canvas.selection_info_callback.assert_called_once_with("", "")

        atom_item = _FakeItem("atom", data1=1)
        bond_item = _FakeItem("bond", data1=0)
        object_item = _FakeItem("arrow")
        old_outline = _FakeItem("selection_outline")
        active_scene = _FakeScene([atom_item, bond_item, object_item])
        graph_connected_components = mock.Mock(return_value=[{1, 2}])
        canvas = _make_canvas(
            scene=active_scene,
            selection_outlines=[old_outline],
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 2.0, 0.0)},
                bonds=[Bond(1, 2, 1)],
            ),
            canvas_graph_service=SimpleNamespace(
                graph=SimpleNamespace(atom_bond_ids={1: {0}, 2: {0}}),
                connected_components=graph_connected_components,
            ),
        )
        service = _outline_service(canvas)
        service.add_selection_component_overlay = mock.Mock()
        service.selection_center_for_atoms = mock.Mock(return_value=QPointF(1.0, 0.0))
        service.selection_center_marker_enabled = mock.Mock(return_value=True)
        service.add_selection_center_marker = mock.Mock()
        service.add_selection_object_overlay = mock.Mock()

        service.update_selection_outline()

        self.assertEqual(active_scene.removed_items, [old_outline])
        service.add_selection_component_overlay.assert_called_once()
        self.assertEqual(
            service.add_selection_component_overlay.call_args.args[0], {1, 2}
        )
        self.assertEqual(service.add_selection_component_overlay.call_args.args[1], {0})
        service.add_selection_center_marker.assert_called_once_with(QPointF(1.0, 0.0))
        service.add_selection_object_overlay.assert_called_once_with(
            object_item, mock.ANY
        )
        canvas.selection_info_callback.assert_called_once_with("", "")

    def test_update_selection_outline_uses_adjacency_without_iterating_all_bonds(
        self,
    ) -> None:
        class IndexOnlyBonds:
            def __init__(self, bonds) -> None:
                self._bonds = bonds

            def __getitem__(self, bond_id: int):
                return self._bonds[bond_id]

            def __iter__(self):
                raise AssertionError(
                    "selection outline must not scan the full bond collection"
                )

        atom_items = [_FakeItem("atom", data1=1), _FakeItem("atom", data1=2)]
        bonds = IndexOnlyBonds(
            [
                Bond(1, 2, 1),
                Bond(2, 3, 1),
                None,
                Bond(4, 5, 1),
            ]
        )
        connected_components = mock.Mock(return_value=[{1, 2}])
        canvas = _make_canvas(
            scene=_FakeScene(atom_items),
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 2.0, 0.0),
                    3: Atom("C", 4.0, 0.0),
                },
                bonds=bonds,
            ),
            canvas_graph_service=SimpleNamespace(
                graph=SimpleNamespace(
                    atom_bond_ids={
                        1: {-1, 0, 2, 3, 99},
                        2: {0, 1},
                    }
                ),
                connected_components=connected_components,
            ),
        )
        service = _outline_service(canvas)
        service.add_selection_component_overlay = mock.Mock()
        service.selection_center_for_atoms = mock.Mock(return_value=None)

        service.update_selection_outline()

        connected_components.assert_called_once_with({1, 2})
        service.add_selection_component_overlay.assert_called_once()
        self.assertEqual(
            service.add_selection_component_overlay.call_args.args[0], {1, 2}
        )
        self.assertEqual(service.add_selection_component_overlay.call_args.args[1], {0})

    def test_shift_selection_outlines_and_center_helpers(self) -> None:
        outline = _FakeItem("selection_outline")
        canvas = _make_canvas(
            selection_outlines=[outline],
            tools=SimpleNamespace(active=SimpleNamespace(name="perspective")),
            model=SimpleNamespace(
                atoms={1: Atom("C", 2.0, 3.0), 2: Atom("C", 8.0, 9.0)},
                bonds=[],
            ),
        )
        service = _outline_service(canvas)

        service.shift_selection_outlines(3.0, -2.0)
        self.assertEqual(outline.moves, [(3.0, -2.0)])
        self.assertIsNone(service.selection_center_for_atoms({1}))
        self.assertEqual(service.selection_center_for_atoms({1, 2}), QPointF(5.0, 6.0))
        self.assertTrue(service.selection_center_marker_enabled())

        canvas.services.tools = SimpleNamespace(active=SimpleNamespace(name="select"))
        self.assertFalse(service.selection_center_marker_enabled())

    def test_selection_path_helpers_cover_bond_and_object_paths(self) -> None:
        scene = QGraphicsScene()
        canvas = _FakeCanvas(
            renderer=SimpleNamespace(
                style=SimpleNamespace(
                    bond_line_width=1.0, bond_length_px=20.0, bond_spacing_px=4.0
                )
            ),
            scene=lambda: scene,
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 10.0, 0.0)},
                bonds=[Bond(1, 2, 2), None],
            ),
            services=SimpleNamespace(
                scene_decoration_build_service=SimpleNamespace(
                    mark_center=lambda item: QPointF(4.0, 5.0)
                ),
                geometry_controller=SimpleNamespace(
                    ring_center_for_bond=lambda bond: None,
                    trim_line_for_labels=lambda *_args: (0.0, 1.0),
                ),
                tools=SimpleNamespace(active=SimpleNamespace(name="perspective")),
            ),
        )
        set_bond_items_for(canvas, {})
        set_selection_outlines_for(canvas, [])
        service = _outline_service(canvas)

        line_item = QGraphicsLineItem(0.0, 0.0, 10.0, 0.0)
        polygon_item = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(5.0, 2.0)])
        )
        filled_path = QPainterPath()
        filled_path.addRect(0.0, 0.0, 10.0, 2.0)
        filled_path_item = QGraphicsPathItem(filled_path)
        filled_path_item.setPen(QPen(Qt.PenStyle.NoPen))
        filled_path_item.setBrush(QBrush(QColor("#445566")))
        stroked_path_item = QGraphicsPathItem(filled_path)
        stroked_path_item.setPen(QPen(QColor("#112233"), 1.2))
        text_item = QGraphicsTextItem("note")
        empty_shape_item = _FakeShapeItem("orbital", rect=QRectF(1.0, 2.0, 4.0, 5.0))

        self.assertFalse(
            service.selection_line_stroke_path(
                QPointF(0.0, 0.0), QPointF(10.0, 0.0), 4.0
            ).isEmpty()
        )
        self.assertFalse(
            service.selection_path_for_bond_item(line_item, width=4.0).isEmpty()
        )
        self.assertFalse(service.selection_path_for_bond_item(polygon_item).isEmpty())
        self.assertFalse(
            service.selection_path_for_bond_item(filled_path_item).isEmpty()
        )
        self.assertFalse(
            service.selection_path_for_bond_item(stroked_path_item).isEmpty()
        )
        self.assertTrue(service.selection_path_for_bond_item(object()).isEmpty())
        self.assertTrue(service.selection_path_for_bond(-1).isEmpty())
        self.assertTrue(service.selection_path_for_bond(1).isEmpty())

        canvas.bond_items[0] = [
            QGraphicsLineItem(0.0, -2.0, 10.0, -2.0),
            QGraphicsLineItem(0.0, 2.0, 10.0, 2.0),
        ]
        self.assertFalse(service.selection_path_for_bond(0).isEmpty())

        self.assertFalse(
            service.selection_path_for_object_item(_FakeItem("mark")).isEmpty()
        )
        arrow_path_item = QGraphicsPathItem(filled_path)
        arrow_path_item.setData(0, "arrow")
        arrow_path_item.setPen(QPen(QColor("#112233"), 1.2))
        self.assertFalse(
            service.selection_path_for_object_item(arrow_path_item).isEmpty()
        )
        self.assertFalse(service.selection_path_for_object_item(text_item).isEmpty())
        self.assertFalse(
            service.selection_path_for_object_item(empty_shape_item).isEmpty()
        )

    def test_overlay_adders_append_scene_outlines(self) -> None:
        scene = QGraphicsScene()
        canvas = _FakeCanvas(
            renderer=SimpleNamespace(
                style=SimpleNamespace(
                    bond_line_width=1.0, bond_length_px=20.0, bond_spacing_px=4.0
                )
            ),
            scene=lambda: scene,
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0)}, bonds=[Bond(1, 1, 1)]
            ),
            services=SimpleNamespace(
                geometry_controller=SimpleNamespace(
                    ring_center_for_bond=lambda bond: None,
                    trim_line_for_labels=lambda *_args: (0.0, 1.0),
                ),
                tools=SimpleNamespace(active=SimpleNamespace(name="perspective")),
            ),
        )
        set_bond_items_for(canvas, {0: [QGraphicsLineItem(0.0, 0.0, 10.0, 0.0)]})
        set_selection_outlines_for(canvas, [])
        service = _outline_service(canvas)
        service.selection_path_for_object_item = mock.Mock(
            return_value=service.selection_line_stroke_path(
                QPointF(0.0, 0.0), QPointF(5.0, 0.0), 3.0
            )
        )

        service.add_selection_object_overlay(_FakeItem("arrow"), QColor("#abcdef"))
        service.add_selection_component_overlay({1}, {0}, QColor("#334455"), 1.0)
        service.add_selection_center_marker(QPointF(5.0, 5.0))

        self.assertEqual(len(selection_outlines_for(canvas)), 4)
