import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.model import Atom
    from ui.selection_hit_logic import StructureHit
    from ui.selection_preference_service import SelectionPreferenceService
    from ui.selection_structure_service import SelectionStructureService

    from tests.test_selection_controller_additional import _FakeItem, _make_canvas


def _make_service(canvas, *, hit_testing_service=None, structure_service=None):
    if hit_testing_service is None:
        hit_testing_service = canvas.services.hit_testing_service
    if structure_service is None:
        structure_service = SelectionStructureService(
            canvas,
            graph_service=canvas.services.canvas_graph_service,
        )
    return SelectionPreferenceService(
        canvas,
        hit_testing_service=hit_testing_service,
        structure_service=structure_service,
    )


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for selection preference service tests")
class SelectionPreferenceServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_hit_lookup_delegates_to_injected_hit_testing_service(self) -> None:
        hit_testing = SimpleNamespace(
            item_at_scene_pos=mock.Mock(return_value="hit-item"),
            nearest_atom_hit=mock.Mock(return_value=(1, 1.25)),
            nearest_bond_hit=mock.Mock(return_value=(2, 2.5)),
        )
        service = _make_service(_make_canvas(), hit_testing_service=hit_testing)
        pos = QPointF(3.0, 4.0)

        self.assertEqual(service.item_at_scene_pos(pos), "hit-item")
        self.assertEqual(service.nearest_atom_hit(pos), (1, 1.25))
        self.assertEqual(service.nearest_bond_hit(pos), (2, 2.5))
        hit_testing.item_at_scene_pos.assert_called_once_with(pos)
        hit_testing.nearest_atom_hit.assert_called_once_with(pos)
        hit_testing.nearest_bond_hit.assert_called_once_with(pos)

    def test_preferred_structure_hit_returns_item_atom_before_nearby_hits(self) -> None:
        atom_item = _FakeItem("atom", data1=1)
        service = _make_service(
            _make_canvas(
                atom_items={1: atom_item},
                item_at_scene_pos=mock.Mock(return_value=atom_item),
                model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0)}, bonds=[]),
            ),
        )

        self.assertEqual(service.preferred_structure_hit_at_scene_pos(QPointF(0.0, 0.0)), StructureHit(kind="atom", id=1))

    def test_preferred_structure_hit_handles_ring_atom_and_ring_fallback(self) -> None:
        ring_item = _FakeItem("ring", data2=[1, 2, 3])
        canvas = _make_canvas(
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
        service = _make_service(canvas)

        with (
            mock.patch("ui.selection_preference_service.choose_preferred_structure_hit", return_value=None),
            mock.patch("ui.selection_preference_service.nearest_ring_atom_id", return_value=2),
        ):
            self.assertEqual(
                service.preferred_structure_hit_at_scene_pos(QPointF(1.5, 0.2)),
                StructureHit(kind="atom", id=2),
            )

        canvas.atom_items = {}
        with (
            mock.patch("ui.selection_preference_service.choose_preferred_structure_hit", return_value=None),
            mock.patch("ui.selection_preference_service.nearest_ring_atom_id", return_value=2),
        ):
            self.assertEqual(
                service.preferred_structure_hit_at_scene_pos(QPointF(1.5, 0.2)),
                StructureHit(kind="ring"),
            )

    def test_preferred_structure_hit_uses_nearby_preferred_hit_only_when_graphic_exists(self) -> None:
        fallback_item = _FakeItem("note")
        service = _make_service(
            _make_canvas(
                item_at_scene_pos=mock.Mock(return_value=fallback_item),
                model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0)}, bonds=[]),
            ),
        )

        with mock.patch(
            "ui.selection_preference_service.choose_preferred_structure_hit",
            return_value=StructureHit(kind="atom", id=1),
        ):
            self.assertEqual(
                service.preferred_structure_hit_at_scene_pos(QPointF(0.0, 0.0)),
                StructureHit(kind="other"),
            )

    def test_preferred_structure_item_returns_hit_item_or_original_item(self) -> None:
        ring_item = _FakeItem("ring")
        atom_item = _FakeItem("atom", data1=1)
        service = _make_service(
            _make_canvas(atom_items={1: atom_item}, item_at_scene_pos=mock.Mock(return_value=ring_item))
        )

        service.preferred_structure_hit_at_scene_pos = mock.Mock(return_value=StructureHit(kind="atom", id=1))
        self.assertIs(service.preferred_structure_item_at_scene_pos(QPointF(0.0, 0.0)), atom_item)

        service.preferred_structure_hit_at_scene_pos = mock.Mock(return_value=StructureHit(kind="ring"))
        self.assertIs(service.preferred_structure_item_at_scene_pos(QPointF(1.0, 1.0)), ring_item)

        service.preferred_structure_hit_at_scene_pos = mock.Mock(return_value=None)
        self.assertIsNone(service.preferred_structure_item_at_scene_pos(QPointF(2.0, 2.0)))
