import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.model import Atom, Bond
    from ui.selection_hit_logic import StructureHit
    from ui.selection_hit_test_service import SelectionHitTestService
    from ui.selection_structure_service import SelectionStructureService

    from tests.test_selection_controller_additional import _FakeItem, _make_canvas


def _make_service(canvas, *, hit_testing_service=None, structure_service=None):
    if hit_testing_service is None:
        hit_testing_service = canvas.services.hit_testing_service
    graph_service = canvas.services.canvas_graph_service
    if structure_service is None:
        structure_service = SelectionStructureService(canvas, graph_service=graph_service)
    return SelectionHitTestService(
        canvas,
        hit_testing_service=hit_testing_service,
        structure_service=structure_service,
        graph_service=graph_service,
    )


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for selection hit-test service tests")
class SelectionHitTestServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_selection_rects_for_snapshot_uses_components_and_non_overlay_items(self) -> None:
        note_item = _FakeItem("note", rect=QRectF(5.0, 6.0, 7.0, 8.0))
        arrow_item = _FakeItem("arrow", rect=QRectF(9.0, 9.0, 2.0, 2.0))
        atom_item = _FakeItem("atom", data1=1)
        snapshot = SimpleNamespace(
            selected_atom_ids={1, 2},
            selected_bond_ids={0},
            selection_items=[note_item, arrow_item, atom_item],
        )
        canvas = _make_canvas(
            graph_connected_components=mock.Mock(return_value=[{1, 2}]),
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 2.0, 0.0)}, bonds=[Bond(1, 2, 1)]),
        )
        service = _make_service(canvas)

        rects = service.selection_rects_for_snapshot(snapshot)

        self.assertEqual(len(rects), 2)
        self.assertEqual((rects[0].left, rects[0].top, rects[0].right, rects[0].bottom), (0.0, 0.0, 2.0, 0.0))
        self.assertEqual((rects[1].left, rects[1].top, rects[1].right, rects[1].bottom), (5.0, 6.0, 12.0, 14.0))

    def test_selection_hit_test_builds_membership_request(self) -> None:
        selected_bond_item = _FakeItem("bond", data1=0, selected=True)
        outline = _FakeItem("selection_outline", data2={"kind": "component"}, contains=True)
        snapshot = SimpleNamespace(
            selected_atom_ids={1, 2},
            selected_bond_ids={0},
            selection_items=[],
        )
        canvas = _make_canvas(
            selection_outlines=[outline],
            hit_testing_service=SimpleNamespace(item_at_scene_pos=mock.Mock(return_value=selected_bond_item)),
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 2.0, 0.0)}, bonds=[Bond(1, 2, 1)]),
        )
        service = _make_service(canvas)

        with mock.patch("ui.selection_hit_test_service.selection_hit_matches", return_value=True) as matches:
            self.assertTrue(service.selection_hit_test(QPointF(4.0, 5.0), snapshot=snapshot))

        request = matches.call_args.args[0]
        self.assertTrue(request.outline_hit)
        self.assertEqual(request.hit, StructureHit(kind="bond", id=0))
        self.assertTrue(request.item_is_selected)
        self.assertEqual(request.selected_atom_ids, {1, 2})
        self.assertEqual(request.selected_bond_ids, {0})

    def test_selection_hit_test_returns_false_without_snapshot(self) -> None:
        service = _make_service(_make_canvas())

        self.assertFalse(service.selection_hit_test(QPointF(1.0, 2.0)))

    def test_item_lookup_uses_injected_hit_testing_service(self) -> None:
        hit_testing_service = SimpleNamespace(item_at_scene_pos=mock.Mock(return_value=None))
        canvas = _make_canvas(item_at_scene_pos=mock.Mock(side_effect=AssertionError("canvas facade should not be used")))
        service = _make_service(canvas, hit_testing_service=hit_testing_service)

        self.assertFalse(
            service.selection_hit_test(
                QPointF(1.0, 2.0),
                snapshot=SimpleNamespace(selected_atom_ids=set(), selected_bond_ids=set(), selection_items=[]),
            )
        )

        hit_testing_service.item_at_scene_pos.assert_called_once_with(QPointF(1.0, 2.0))
