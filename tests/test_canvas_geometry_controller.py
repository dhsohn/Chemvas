import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.model import Atom, Bond
    from ui.canvas_geometry_controller import CanvasGeometryController


class _FakeRingItem:
    def __init__(self, atom_ids) -> None:
        self._atom_ids = atom_ids

    def data(self, key):
        if key == 2:
            return self._atom_ids
        return None


class _FakeLabelItem:
    def __init__(self, rect: QRectF) -> None:
        self._rect = QRectF(rect)

    def sceneBoundingRect(self) -> QRectF:
        return QRectF(self._rect)


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas geometry controller tests")
class CanvasGeometryControllerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_ring_for_bond_handles_invalid_none_missing_and_matching_cases(self) -> None:
        ring_item = _FakeRingItem([1, 2, 3])
        controller = CanvasGeometryController(
            SimpleNamespace(
                model=SimpleNamespace(bonds=[Bond(1, 2, 1), None]),
                ring_items=[_FakeRingItem("bad"), ring_item],
            )
        )

        self.assertIsNone(controller.ring_for_bond(-1))
        self.assertIsNone(controller.ring_for_bond(1))
        self.assertIsNone(controller.ring_for_bond(9))
        self.assertIs(controller.ring_for_bond(0), ring_item)

    def test_label_rect_helpers_return_none_for_missing_items(self) -> None:
        controller = CanvasGeometryController(
            SimpleNamespace(
                atom_items={},
                renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=2.0)),
                model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0)}),
            )
        )

        self.assertIsNone(controller.label_rect_for_atom(1))
        self.assertIsNone(controller.visible_label_rect_for_atom(1))
        self.assertIsNone(controller.label_cut_radius_for_atom(1))

    def test_mark_clearance_for_kind_covers_radical_plus_minus_and_default(self) -> None:
        style = SimpleNamespace(bond_length_px=20.0, bond_line_width=2.0)
        controller = CanvasGeometryController(
            SimpleNamespace(renderer=SimpleNamespace(style=style, atom_font=lambda: QFont()))
        )

        default_gap = max(0.6, style.bond_length_px * 0.05)
        self.assertEqual(controller.mark_clearance_for_kind("unknown"), default_gap)
        self.assertGreater(controller.mark_clearance_for_kind("radical"), default_gap)
        self.assertGreater(controller.mark_clearance_for_kind("plus"), default_gap)
        self.assertGreater(controller.mark_clearance_for_kind("minus"), default_gap)

    def test_trim_line_for_labels_handles_none_radii_and_min_span_clamp(self) -> None:
        canvas = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=5.0)),
            _label_cut_radius_for_atom=lambda atom_id: {1: None, 2: 49.6}.get(atom_id),
        )
        controller = CanvasGeometryController(canvas)

        self.assertEqual(controller.trim_line_for_labels(1, None, 0.0, 0.0, 100.0, 0.0), (0.0, 1.0))
        self.assertEqual(controller.trim_line_for_labels(None, 1, 0.0, 0.0, 100.0, 0.0), (0.0, 1.0))

        tight = controller.trim_line_for_labels(1, 2, 0.0, 0.0, 100.0, 0.0)
        self.assertAlmostEqual(tight[0], 0.0)
        self.assertAlmostEqual(tight[1], 0.503)


if __name__ == "__main__":
    unittest.main()
