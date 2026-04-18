import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtWidgets import QApplication, QGraphicsTextItem
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.history import AddSceneItemsCommand
    from ui.scene_decoration_service import SceneDecorationService


class _FakeScene:
    def __init__(self) -> None:
        self.items = []

    def addItem(self, item) -> None:
        self.items.append(item)


class _FakeItem:
    def __init__(self) -> None:
        self._data = {}

    def setData(self, key, value) -> None:
        self._data[key] = value

    def data(self, key):
        return self._data.get(key)


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene decoration tests")
class SceneDecorationServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_add_mark_tracks_registry_and_optional_history(self) -> None:
        scene = _FakeScene()
        pushed = []
        text_mark = QGraphicsTextItem("-")
        canvas = SimpleNamespace(
            mark_kind="plus",
            mark_items=[],
            _marks_by_atom={},
            _build_mark_item=mock.Mock(side_effect=[text_mark, None]),
            _make_selectable=mock.Mock(),
            scene=lambda: scene,
            _set_mark_center=mock.Mock(),
            _mark_state_dict=mock.Mock(return_value={"kind": "mark", "atom_id": 7}),
            _push_command=pushed.append,
        )
        service = SceneDecorationService(canvas)

        item = service.add_mark(
            QPointF(4.0, 5.0),
            kind="minus",
            atom_id=7,
            offset=QPointF(1.5, -2.5),
            record=True,
        )

        self.assertIs(item, text_mark)
        self.assertEqual(item.data(0), "mark")
        self.assertEqual(
            item.data(1),
            {"kind": "minus", "atom_id": 7, "dx": 1.5, "dy": -2.5, "text": "-"},
        )
        self.assertEqual(canvas.mark_items, [item])
        self.assertEqual(canvas._marks_by_atom, {7: [item]})
        self.assertEqual(scene.items, [item])
        canvas._make_selectable.assert_called_once_with(item)
        canvas._set_mark_center.assert_called_once_with(item, QPointF(4.0, 5.0))
        self.assertEqual(len(pushed), 1)
        self.assertIsInstance(pushed[0], AddSceneItemsCommand)
        self.assertEqual(pushed[0].item_states, [{"kind": "mark", "atom_id": 7}])

        self.assertIsNone(service.add_mark(QPointF(0.0, 0.0), kind="unsupported"))

    def test_add_arrow_and_ts_bracket_register_items_and_push_history(self) -> None:
        scene = _FakeScene()
        pushed = []
        arrow_item = _FakeItem()
        arrow_item.setData(2, {"control": QPointF(2.0, 3.0)})
        ts_item = _FakeItem()
        canvas = SimpleNamespace(
            arrow_items=[],
            ts_bracket_items=[],
            _build_arrow_item=mock.Mock(return_value=arrow_item),
            _build_ts_bracket_item=mock.Mock(return_value=ts_item),
            _make_selectable=mock.Mock(),
            scene=lambda: scene,
            _arrow_state_dict=mock.Mock(return_value={"kind": "arrow"}),
            _ts_bracket_state_dict=mock.Mock(return_value={"kind": "ts_bracket"}),
            _push_command=pushed.append,
        )
        service = SceneDecorationService(canvas)

        arrow = service.add_arrow(QPointF(1.0, 2.0), QPointF(6.0, 7.0), "curved_double")
        ts_bracket = service.add_ts_bracket(QRectF(QPointF(0.0, 0.0), QPointF(4.0, 8.0)))

        self.assertIs(arrow, arrow_item)
        self.assertEqual(arrow.data(0), "curved_double")
        self.assertEqual(arrow.data(2)["start"], QPointF(1.0, 2.0))
        self.assertEqual(arrow.data(2)["end"], QPointF(6.0, 7.0))
        self.assertTrue(arrow.data(2)["double"])
        self.assertIs(ts_bracket, ts_item)
        self.assertEqual(canvas.arrow_items, [arrow_item])
        self.assertEqual(canvas.ts_bracket_items, [ts_item])
        self.assertEqual(scene.items, [arrow_item, ts_item])
        self.assertEqual(len(pushed), 2)
        self.assertTrue(all(isinstance(command, AddSceneItemsCommand) for command in pushed))

    def test_add_orbital_uses_restore_and_skips_none_builds(self) -> None:
        pushed = []
        restored = []
        group = object()
        canvas = SimpleNamespace(
            active_orbital_type="p",
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            _build_orbital_items=mock.Mock(),
            _scene_item_controller=SimpleNamespace(restore_scene_item=restored.append),
            _orbital_state_dict=mock.Mock(return_value={"kind": "orbital"}),
            _push_command=pushed.append,
        )
        service = SceneDecorationService(canvas)

        with mock.patch(
            "ui.scene_decoration_service.create_orbital_item_from_state_helper",
            side_effect=[None, group],
        ) as build_orbital:
            self.assertIsNone(service.add_orbital(QPointF(1.0, 2.0)))
            result = service.add_orbital(QPointF(3.0, 4.0))

        self.assertIs(result, group)
        self.assertEqual(restored, [group])
        self.assertEqual(len(pushed), 1)
        self.assertIsInstance(pushed[0], AddSceneItemsCommand)
        self.assertEqual(pushed[0].item_states, [{"kind": "orbital"}])
        self.assertEqual(build_orbital.call_count, 2)


if __name__ == "__main__":
    unittest.main()
