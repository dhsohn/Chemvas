import math
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QFont
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.model import Atom
    from ui.canvas_view import CanvasView
    from ui.graphics_items import AtomDotItem, AtomLabelItem


class _FakeScene:
    def __init__(self) -> None:
        self.items = []

    def addItem(self, item) -> None:
        self.items.append(item)


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewMarkHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _renderer(self, bond_line_width: float = 2.0, bond_length_px: float = 50.0) -> SimpleNamespace:
        font = QFont("DejaVu Sans", 11)
        return SimpleNamespace(
            style=SimpleNamespace(
                bond_line_width=bond_line_width,
                bond_length_px=bond_length_px,
                atom_color=QColor(16, 32, 48),
            ),
            atom_font=lambda: font,
        )

    def test_build_mark_item_returns_kind_specific_items_and_hit_metadata(self) -> None:
        view = SimpleNamespace(
            renderer=self._renderer(),
            _mark_selection_radius=lambda: 7.5,
        )

        radical = CanvasView._build_mark_item(view, "radical")
        self.assertIsInstance(radical, AtomDotItem)
        self.assertAlmostEqual(radical.rect().left(), -1.4)
        self.assertAlmostEqual(radical.rect().width(), 2.8)
        self.assertEqual(radical.brush().color(), QColor(16, 32, 48))
        self.assertEqual(radical.pen().style(), Qt.PenStyle.NoPen)

        plus = CanvasView._build_mark_item(view, "plus")
        self.assertIsInstance(plus, AtomLabelItem)
        self.assertEqual(plus.toPlainText(), "+")
        self.assertEqual(plus.defaultTextColor(), QColor(16, 32, 48))
        self.assertEqual(plus.font().family(), view.renderer.atom_font().family())
        self.assertEqual(plus._hit_radius, 7.5)

        minus = CanvasView._build_mark_item(view, "minus")
        self.assertIsInstance(minus, AtomLabelItem)
        self.assertEqual(minus.toPlainText(), "-")
        self.assertEqual(minus._hit_radius, 7.5)

        self.assertIsNone(CanvasView._build_mark_item(view, "unsupported"))

    def test_mark_offset_from_click_handles_zero_length_and_label_aware_target(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(atoms={7: Atom("C", 10.0, 20.0)}),
            renderer=self._renderer(bond_length_px=50.0),
            mark_kind="plus",
            _mark_target_distance_for_atom=mock.Mock(return_value=20.0),
        )

        offset = CanvasView._mark_offset_from_click(view, 7, QPointF(10.0, 20.0), kind="minus")

        expected = 12.5 / math.sqrt(2.0)
        self.assertAlmostEqual(offset.x(), expected)
        self.assertAlmostEqual(offset.y(), -expected)

        call = view._mark_target_distance_for_atom.call_args
        self.assertEqual(call.args[0], 7)
        self.assertAlmostEqual(call.args[1], 1.0 / math.sqrt(2.0))
        self.assertAlmostEqual(call.args[2], -1.0 / math.sqrt(2.0))
        self.assertEqual(call.args[3], "minus")

    def test_mark_offset_from_click_uses_view_mark_kind_when_kind_is_missing(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(atoms={7: Atom("C", 10.0, 20.0)}),
            renderer=self._renderer(bond_length_px=50.0),
            mark_kind="radical",
            _mark_target_distance_for_atom=mock.Mock(return_value=0.0),
        )

        offset = CanvasView._mark_offset_from_click(view, 7, QPointF(13.0, 24.0))

        self.assertAlmostEqual(offset.x(), 6.0)
        self.assertAlmostEqual(offset.y(), 8.0)
        view._mark_target_distance_for_atom.assert_called_once_with(7, 0.6, 0.8, "radical")

    def test_add_mark_attaches_metadata_tracks_registry_and_uses_kind_specific_item(self) -> None:
        scene = _FakeScene()
        view = SimpleNamespace(
            renderer=self._renderer(),
            scene=lambda: scene,
            _mark_selection_radius=lambda: 7.5,
            _build_mark_item=lambda kind: CanvasView._build_mark_item(view, kind),
            _make_selectable=mock.Mock(),
            _set_mark_center=mock.Mock(),
            _push_command=mock.Mock(),
            mark_items=[],
            _marks_by_atom={},
            mark_kind="plus",
        )

        item = CanvasView.add_mark(
            view,
            QPointF(4.0, 5.0),
            kind="minus",
            atom_id=7,
            offset=QPointF(1.5, -2.5),
            record=False,
        )

        self.assertIsInstance(item, AtomLabelItem)
        self.assertEqual(item.toPlainText(), "-")
        self.assertEqual(item.data(0), "mark")
        self.assertEqual(
            item.data(1),
            {"kind": "minus", "atom_id": 7, "dx": 1.5, "dy": -2.5, "text": "-"},
        )
        self.assertEqual(view.mark_items, [item])
        self.assertEqual(view._marks_by_atom, {7: [item]})
        self.assertEqual(scene.items, [item])
        view._make_selectable.assert_called_once_with(item)
        view._set_mark_center.assert_called_once_with(item, QPointF(4.0, 5.0))
        view._push_command.assert_not_called()
