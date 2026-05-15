import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.history import SetAtomPositionsCommand
    from ui.history_commands import UpdateSceneItemCommand
    from tests.test_scene_ops_controller import _make_rect_item
    from ui.scene_transform_apply_logic import (
        apply_component_flip_transform,
        apply_standalone_flip_transform,
    )
    from ui.scene_transform_logic import FlipAtomPositionMaps


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene transform apply logic tests")
class SceneTransformApplyLogicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_apply_component_flip_transform_adds_atom_and_scene_item_commands_when_changed(self) -> None:
        changed_item = _make_rect_item("mark", state={"kind": "mark", "x": 1.0})
        same_item = _make_rect_item("note", state={"kind": "note", "x": 2.0})
        empty_item = _make_rect_item("arrow", state={})
        applied_states: list[tuple[object, dict]] = []
        set_positions_calls: list[tuple[dict[int, tuple[float, float]], bool]] = []

        commands = apply_component_flip_transform(
            component_items=[changed_item, same_item, empty_item],
            scene_item_state_getter=lambda item: dict(item.data(9) or {}),
            position_maps=FlipAtomPositionMaps(
                before_positions={1: (1.0, 2.0)},
                after_positions={1: (5.0, 2.0)},
                transformed_atom_positions={1: (5.0, 2.0)},
            ),
            center=QPointF(3.0, 0.0),
            horizontal=True,
            flip_state_getter=lambda item, before_state, center, horizontal, transformed: (
                {}
                if item is empty_item
                else dict(before_state, x=9.0)
                if item is changed_item
                else dict(before_state)
            ),
            set_atom_positions=lambda positions, update_selection=False: set_positions_calls.append(
                (dict(positions), update_selection)
            ),
            apply_scene_item_state=lambda item, state: applied_states.append((item, dict(state))),
        )

        self.assertEqual(set_positions_calls, [({1: (5.0, 2.0)}, False)])
        self.assertEqual(applied_states, [(changed_item, {"kind": "mark", "x": 9.0})])
        self.assertEqual(len(commands), 2)
        self.assertIsInstance(commands[0], SetAtomPositionsCommand)
        self.assertIsInstance(commands[1], UpdateSceneItemCommand)
        self.assertEqual(commands[1].before_state, {"kind": "mark", "x": 1.0})
        self.assertEqual(commands[1].after_state, {"kind": "mark", "x": 9.0})

    def test_apply_component_flip_transform_skips_noop_atom_and_item_changes(self) -> None:
        item = _make_rect_item("mark", state={"kind": "mark", "x": 1.0})
        applied_states: list[tuple[object, dict]] = []
        set_positions_calls: list[tuple[dict[int, tuple[float, float]], bool]] = []

        commands = apply_component_flip_transform(
            component_items=[item],
            scene_item_state_getter=lambda current: dict(current.data(9) or {}),
            position_maps=FlipAtomPositionMaps(
                before_positions={1: (1.0, 2.0)},
                after_positions={1: (1.0, 2.0)},
                transformed_atom_positions={1: (1.0, 2.0)},
            ),
            center=QPointF(0.0, 0.0),
            horizontal=True,
            flip_state_getter=lambda item, before_state, center, horizontal, transformed: dict(before_state),
            set_atom_positions=lambda positions, update_selection=False: set_positions_calls.append(
                (dict(positions), update_selection)
            ),
            apply_scene_item_state=lambda item, state: applied_states.append((item, dict(state))),
        )

        self.assertEqual(commands, [])
        self.assertEqual(set_positions_calls, [])
        self.assertEqual(applied_states, [])

    def test_apply_standalone_flip_transform_returns_command_only_for_changed_state(self) -> None:
        changed_item = _make_rect_item("note", state={"kind": "note", "x": 1.0})
        unchanged_item = _make_rect_item("note", state={"kind": "note", "x": 3.0})
        applied_states: list[tuple[object, dict]] = []

        changed_command = apply_standalone_flip_transform(
            changed_item,
            scene_item_state_getter=lambda item: dict(item.data(9) or {}),
            center=QPointF(4.0, 0.0),
            horizontal=False,
            flip_state_getter=lambda item, before_state, center, horizontal, transformed: dict(before_state, x=7.0),
            apply_scene_item_state=lambda item, state: applied_states.append((item, dict(state))),
        )
        unchanged_command = apply_standalone_flip_transform(
            unchanged_item,
            scene_item_state_getter=lambda item: dict(item.data(9) or {}),
            center=QPointF(4.0, 0.0),
            horizontal=False,
            flip_state_getter=lambda item, before_state, center, horizontal, transformed: dict(before_state),
            apply_scene_item_state=lambda item, state: applied_states.append((item, dict(state))),
        )

        self.assertIsInstance(changed_command, UpdateSceneItemCommand)
        self.assertEqual(changed_command.before_state, {"kind": "note", "x": 1.0})
        self.assertEqual(changed_command.after_state, {"kind": "note", "x": 7.0})
        self.assertIsNone(unchanged_command)
        self.assertEqual(applied_states, [(changed_item, {"kind": "note", "x": 7.0})])


if __name__ == "__main__":
    unittest.main()
