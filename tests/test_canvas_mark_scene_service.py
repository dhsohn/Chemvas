import math
import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
except ModuleNotFoundError:
    QPointF = None

if QPointF is not None:
    from core.model import Atom
    from ui.canvas_mark_registry import CanvasMarkRegistry
    from ui.canvas_mark_scene_service import CanvasMarkSceneService
    from ui.canvas_scene_items_state import (
        mark_items_for,
        set_scene_item_collection_for,
    )
    from ui.canvas_tool_settings_state import CanvasToolSettingsState


@unittest.skipUnless(QPointF is not None, "PyQt6 is required for canvas mark scene service tests")
class CanvasMarkSceneServiceTest(unittest.TestCase):
    def test_missing_atom_paths(self) -> None:
        scene_decoration_service = SimpleNamespace(add_mark=mock.Mock())
        canvas = SimpleNamespace(
            services=SimpleNamespace(scene_decoration_service=scene_decoration_service),
            model=SimpleNamespace(atoms={}),
            tool_settings_state=CanvasToolSettingsState(mark_kind="plus"),
        )
        service = CanvasMarkSceneService(canvas)

        self.assertIsNone(service.add_mark_for_atom(7, QPointF(1.0, 2.0)))
        self.assertEqual(service.mark_offset_from_click(7, QPointF(1.0, 2.0)), QPointF(0.0, 0.0))
        scene_decoration_service.add_mark.assert_not_called()

    def test_add_mark_for_atom_uses_offset_and_forwards_to_add_mark(self) -> None:
        scene_decoration_service = SimpleNamespace(add_mark=mock.Mock(return_value="mark-item"))
        canvas = SimpleNamespace(
            services=SimpleNamespace(scene_decoration_service=scene_decoration_service),
            model=SimpleNamespace(atoms={7: Atom("C", 10.0, 20.0)}),
            tool_settings_state=CanvasToolSettingsState(mark_kind="plus"),
        )
        service = CanvasMarkSceneService(canvas, scene_decoration_service=scene_decoration_service)
        service.mark_offset_from_click = mock.Mock(return_value=QPointF(1.5, -2.5))

        item = service.add_mark_for_atom(7, QPointF(12.0, 14.0), kind="minus", record=False)

        self.assertEqual(item, "mark-item")
        service.mark_offset_from_click.assert_called_once_with(7, QPointF(12.0, 14.0), kind="minus")
        scene_decoration_service.add_mark.assert_called_once_with(
            QPointF(11.5, 17.5),
            kind="minus",
            atom_id=7,
            offset=QPointF(1.5, -2.5),
            record=False,
        )

    def test_mark_offset_from_click_handles_zero_length_and_kind_fallback(self) -> None:
        canvas = SimpleNamespace(
            model=SimpleNamespace(atoms={7: Atom("C", 10.0, 20.0)}),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=50.0)),
            tool_settings_state=CanvasToolSettingsState(mark_kind="radical"),
        )
        mark_target_distance = mock.Mock(return_value=20.0)
        canvas.services = SimpleNamespace(
            geometry_controller=SimpleNamespace(mark_target_distance_for_atom=mark_target_distance)
        )

        offset = CanvasMarkSceneService(canvas).mark_offset_from_click(7, QPointF(10.0, 20.0))

        expected = 12.5 / math.sqrt(2.0)
        self.assertAlmostEqual(offset.x(), expected)
        self.assertAlmostEqual(offset.y(), -expected)
        mark_target_distance.assert_called_once_with(
            7,
            1.0 / math.sqrt(2.0),
            -1.0 / math.sqrt(2.0),
            "radical",
        )

    def test_remove_mark_item_and_remove_marks_for_atom_update_registries(self) -> None:
        scene = SimpleNamespace(removeItem=mock.Mock())
        atom_mark = SimpleNamespace(data=lambda key: {1: {"atom_id": 4}}.get(key))
        atom_mark_2 = SimpleNamespace(data=lambda key: {1: {"atom_id": 9}}.get(key))
        free_mark = SimpleNamespace(data=lambda key: {1: {"atom_id": None}}.get(key))
        canvas = SimpleNamespace(
            mark_registry=CanvasMarkRegistry({4: [atom_mark], 9: [atom_mark_2]}),
            scene=lambda: scene,
        )
        set_scene_item_collection_for(canvas, "mark_items", [atom_mark, atom_mark_2, free_mark])
        service = CanvasMarkSceneService(canvas)

        service.remove_mark_item(atom_mark)
        service.remove_marks_for_atom(9)

        self.assertEqual(mark_items_for(canvas), [free_mark])
        self.assertEqual(canvas.mark_registry.by_atom, {})
        self.assertEqual(scene.removeItem.call_args_list, [mock.call(atom_mark), mock.call(atom_mark_2)])

    def test_remove_mark_item_and_remove_marks_for_atom_cover_no_registry_matches(self) -> None:
        scene = SimpleNamespace(removeItem=mock.Mock())
        loose_mark = SimpleNamespace(data=lambda key: None)
        foreign_mark = SimpleNamespace(data=lambda key: {1: {"atom_id": 5}}.get(key))
        canvas = SimpleNamespace(
            mark_registry=CanvasMarkRegistry({5: [foreign_mark]}),
            scene=lambda: scene,
        )
        set_scene_item_collection_for(canvas, "mark_items", [])
        service = CanvasMarkSceneService(canvas)

        service.remove_mark_item(loose_mark)
        service.remove_mark_item(SimpleNamespace(data=lambda key: {1: {"atom_id": 6}}.get(key)))
        set_scene_item_collection_for(canvas, "mark_items", [])
        service.remove_marks_for_atom(5)

        self.assertEqual(canvas.mark_registry.by_atom, {})
        self.assertEqual(scene.removeItem.call_args_list, [mock.call(loose_mark), mock.call(mock.ANY), mock.call(foreign_mark)])

    def test_mark_center_for_pointer_returns_pointer_for_missing_atom(self) -> None:
        canvas = SimpleNamespace(
            model=SimpleNamespace(atoms={7: Atom("C", 10.0, 20.0)}),
        )
        service = CanvasMarkSceneService(canvas)
        service.mark_offset_from_click = mock.Mock(return_value=QPointF(1.5, -2.5))

        self.assertEqual(service.mark_center_for_pointer(QPointF(2.0, 3.0)).toPoint(), QPointF(2.0, 3.0).toPoint())
        self.assertEqual(
            service.mark_center_for_pointer(QPointF(2.0, 3.0), atom_id=99).toPoint(),
            QPointF(2.0, 3.0).toPoint(),
        )
        self.assertEqual(
            service.mark_center_for_pointer(QPointF(2.0, 3.0), atom_id=7, kind="minus"),
            QPointF(11.5, 17.5),
        )
        service.mark_offset_from_click.assert_called_once_with(7, QPointF(2.0, 3.0), kind="minus")


if __name__ == "__main__":
    unittest.main()
