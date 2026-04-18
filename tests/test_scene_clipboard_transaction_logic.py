import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QRectF
    from PyQt6.QtWidgets import QApplication, QGraphicsItem
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from ui.scene_clipboard_transaction_logic import (
        build_clipboard_copy_plan,
        build_clipboard_paste_plan,
        clipboard_copy_cache_values,
        visible_items_to_hide_for_copy,
    )


class _BoundsItem(QGraphicsItem):
    def __init__(self, rect: QRectF, *, visible: bool = True) -> None:
        super().__init__()
        self._rect = QRectF(rect)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setVisible(visible)

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(self._rect)

    def paint(self, painter, option, widget=None) -> None:  # type: ignore[override]
        return None


def _make_rect_item(rect: QRectF, *, visible: bool = True) -> QGraphicsItem:
    return _BoundsItem(rect, visible=visible)


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene clipboard transaction logic tests")
class SceneClipboardTransactionLogicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_build_clipboard_copy_plan_returns_none_when_items_have_no_valid_bounds(self) -> None:
        flat = _make_rect_item(QRectF(0.0, 0.0, 0.0, 0.0))

        plan = build_clipboard_copy_plan(
            [flat],
            payload={"format": "lightdraw-selection", "version": 1},
            bond_line_width=1.5,
            device_pixel_ratio=2.0,
        )

        self.assertIsNone(plan)

    def test_build_clipboard_copy_plan_computes_padded_source_scale_image_size_and_payload_json(self) -> None:
        first = _make_rect_item(QRectF(10.0, 20.0, 30.0, 15.0))
        second = _make_rect_item(QRectF(60.0, 25.0, 10.0, 20.0))

        plan = build_clipboard_copy_plan(
            [first, second],
            payload={"scene_items": [{"kind": "note"}], "format": "lightdraw-selection", "version": 1},
            bond_line_width=2.0,
            device_pixel_ratio=1.5,
        )

        assert plan is not None
        self.assertEqual(plan.source, QRectF(6.0, 16.0, 68.0, 33.0))
        self.assertEqual(plan.scale, 1.5)
        self.assertEqual(plan.image_width, 102)
        self.assertEqual(plan.image_height, 50)
        self.assertEqual(
            plan.payload_json,
            '{"format":"lightdraw-selection","scene_items":[{"kind":"note"}],"version":1}',
        )
        self.assertEqual(
            clipboard_copy_cache_values(plan.payload_json),
            (
                '{"format":"lightdraw-selection","scene_items":[{"kind":"note"}],"version":1}',
                '{"format":"lightdraw-selection","scene_items":[{"kind":"note"}],"version":1}',
                0,
            ),
        )
        self.assertEqual(clipboard_copy_cache_values(None), (None, None, 0))

    def test_visible_items_to_hide_for_copy_skips_selected_and_invisible_items(self) -> None:
        selected = _make_rect_item(QRectF(0.0, 0.0, 10.0, 10.0))
        visible_other = _make_rect_item(QRectF(12.0, 0.0, 10.0, 10.0))
        hidden_other = _make_rect_item(QRectF(24.0, 0.0, 10.0, 10.0), visible=False)

        items_to_hide = visible_items_to_hide_for_copy(
            [selected, visible_other, hidden_other],
            selected_items={selected},
        )

        self.assertEqual(items_to_hide, [visible_other])

    def test_build_clipboard_paste_plan_resets_or_advances_count_and_captures_snapshots(self) -> None:
        calls: list[tuple[int, float]] = []

        def paste_offset(step: int, bond_length_px: float) -> tuple[float, float]:
            calls.append((step, bond_length_px))
            return float(step) * 3.0, float(step) * 4.0

        plan = build_clipboard_paste_plan(
            payload={
                "atoms": [{"id": 1, "element": "C", "x": 1.0, "y": 2.0}],
                "scene_items": [{"kind": "note", "text": "copy", "x": 5.0, "y": 6.0}],
            },
            payload_json="source-a",
            previous_source_json="older-source",
            previous_paste_count=7,
            bond_length_px=40.0,
            clipboard_paste_offset=paste_offset,
            before_next_atom_id=9,
            before_bond_count=3,
            before_smiles_input="C=C",
        )

        assert plan is not None
        self.assertEqual(plan.paste_source_json, "source-a")
        self.assertEqual(plan.paste_count, 1)
        self.assertEqual((plan.dx, plan.dy), (3.0, 4.0))
        self.assertEqual(plan.atoms, [{"id": 1, "element": "C", "x": 1.0, "y": 2.0}])
        self.assertEqual(plan.scene_items, [{"kind": "note", "text": "copy", "x": 5.0, "y": 6.0}])
        self.assertEqual(plan.before_next_atom_id, 9)
        self.assertEqual(plan.before_bond_count, 3)
        self.assertEqual(plan.before_smiles_input, "C=C")
        self.assertTrue(plan.has_payload_content())
        self.assertEqual(calls, [(1, 40.0)])

        repeated = build_clipboard_paste_plan(
            payload={"atoms": [], "bonds": [], "rings": [], "marks": [], "scene_items": []},
            payload_json="source-a",
            previous_source_json="source-a",
            previous_paste_count=1,
            bond_length_px=40.0,
            clipboard_paste_offset=paste_offset,
            before_next_atom_id=11,
            before_bond_count=4,
            before_smiles_input=None,
        )

        assert repeated is not None
        self.assertEqual(repeated.paste_count, 2)
        self.assertEqual((repeated.dx, repeated.dy), (6.0, 8.0))
        self.assertFalse(repeated.has_payload_content())
        self.assertEqual(calls, [(1, 40.0), (2, 40.0)])

    def test_build_clipboard_paste_plan_returns_none_without_payload_or_json(self) -> None:
        self.assertIsNone(
            build_clipboard_paste_plan(
                payload=None,
                payload_json="source-a",
                previous_source_json=None,
                previous_paste_count=0,
                bond_length_px=40.0,
                clipboard_paste_offset=lambda step, bond_length_px: (0.0, 0.0),
                before_next_atom_id=1,
                before_bond_count=0,
                before_smiles_input=None,
            )
        )
        self.assertIsNone(
            build_clipboard_paste_plan(
                payload={},
                payload_json=None,
                previous_source_json=None,
                previous_paste_count=0,
                bond_length_px=40.0,
                clipboard_paste_offset=lambda step, bond_length_px: (0.0, 0.0),
                before_next_atom_id=1,
                before_bond_count=0,
                before_smiles_input=None,
            )
        )


if __name__ == "__main__":
    unittest.main()
