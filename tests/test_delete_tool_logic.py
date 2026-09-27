import os
import unittest
from types import SimpleNamespace

from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

from chemvas.core.history import (
    CompositeCommand,
    HistoryCommand,
)
from chemvas.ui.annotations.items import NoteItem
from chemvas.ui.canvas.canvas_scene_items_state import CanvasSceneItemsState
from chemvas.ui.tools.delete_tool_logic import (
    build_delete_tool_history_command,
    erase_delete_tool_item,
)


class _Command(HistoryCommand):
    def __init__(self, name: str) -> None:
        self.name = name

    def undo(self, canvas) -> None:
        return None

    def redo(self, canvas) -> None:
        return None


class _Point:
    def __init__(self, x: float = 0.0, y: float = 0.0) -> None:
        self._x = x
        self._y = y

    def x(self) -> float:
        return self._x

    def y(self) -> float:
        return self._y


class _Item:
    def __init__(self, kind=None, item_id=None) -> None:
        self._data = {0: kind, 1: item_id}
        self._pos = _Point()

    def data(self, key):
        if key == 3:
            return id(self)
        return self._data.get(key)

    def pos(self):
        return self._pos


class _Canvas:
    def __init__(self) -> None:
        self.runtime_state = canvas_runtime_state(
            scene_items_state=CanvasSceneItemsState()
        )
        self.services = canvas_runtime_services(
            # Serializing a mark's state asks the build service where its
            # centre is; for a non-text item the real one answers item.pos().
            scene_decoration_build_service=SimpleNamespace(
                mark_center=lambda item: item.pos()
            ),
        )


class _DeleteSession:
    def __init__(self) -> None:
        self.calls = []

    def delete_atom(self, atom_id: int):
        self.calls.append(("atom", atom_id))
        return f"atom-{atom_id}"

    def delete_bond(self, bond_id: int):
        self.calls.append(("bond", bond_id))
        return f"bond-{bond_id}"

    def delete_ring(self, item):
        self.calls.append(("ring", item))
        return "ring"

    def delete_scene_item(self, item, state: dict):
        self.calls.append(("scene_item", item, state))
        return f"scene-item-{state['kind']}"


class DeleteToolLogicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_erase_delete_tool_item_dispatches_atom_bond_ring_and_scene_items(
        self,
    ) -> None:
        canvas = _Canvas()
        session = _DeleteSession()

        changed, command = erase_delete_tool_item(
            canvas, _Item("atom", 3), delete_session=session
        )
        self.assertEqual((changed, command), (True, "atom-3"))

        changed, command = erase_delete_tool_item(
            canvas, _Item("bond", 7), delete_session=session
        )
        self.assertEqual((changed, command), (True, "bond-7"))

        ring_item = _Item("ring", 1)
        changed, command = erase_delete_tool_item(
            canvas, ring_item, delete_session=session
        )
        self.assertEqual((changed, command), (True, "ring"))

        note_item = NoteItem(canvas.runtime_state.note_state)
        note_item.setPlainText("erase me")
        note_state = note_item.note_state()
        changed, command = erase_delete_tool_item(
            canvas, note_item, delete_session=session
        )
        self.assertEqual((changed, command), (True, "scene-item-note"))

        mark_item = _Item(
            "mark",
            {"kind": "plus", "text": "+", "atom_id": 3, "dx": 1.0, "dy": -2.0},
        )
        changed, command = erase_delete_tool_item(
            canvas, mark_item, delete_session=session
        )
        self.assertEqual((changed, command), (True, "scene-item-mark"))

        weird_item = _Item("weird", 11)
        self.assertEqual(
            erase_delete_tool_item(canvas, weird_item, delete_session=session),
            (False, None),
        )
        self.assertEqual(
            session.calls,
            [
                ("atom", 3),
                ("bond", 7),
                ("ring", ring_item),
                ("scene_item", note_item, note_state),
                (
                    "scene_item",
                    mark_item,
                    {
                        "kind": "mark",
                        "mark_kind": "plus",
                        "text": "+",
                        "atom_id": 3,
                        "dx": 1.0,
                        "dy": -2.0,
                        "x": 0.0,
                        "y": 0.0,
                    },
                ),
            ],
        )

    def test_erase_delete_tool_item_rejects_non_integer_atom_and_bond_ids(self) -> None:
        canvas = _Canvas()
        session = _DeleteSession()

        self.assertEqual(
            erase_delete_tool_item(
                canvas, _Item("atom", "bad"), delete_session=session
            ),
            (False, None),
        )
        self.assertEqual(
            erase_delete_tool_item(canvas, _Item("bond", None), delete_session=session),
            (False, None),
        )
        self.assertEqual(session.calls, [])

    def test_build_delete_tool_history_command_wraps_single_command_and_multiple(
        self,
    ) -> None:
        single = _Command("single")
        single_command = build_delete_tool_history_command(
            [single],
        )
        self.assertIs(single_command, single)

        first = _Command("first")
        second = _Command("second")
        command = build_delete_tool_history_command(
            [first, second],
        )

        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual(command.commands, [first, second])

    def test_build_delete_tool_history_command_returns_none_for_empty_input(
        self,
    ) -> None:
        self.assertIsNone(
            build_delete_tool_history_command(
                [],
            )
        )
