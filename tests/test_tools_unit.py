import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    import core.tools as tools_module
    from core.model import Atom, Bond
    from core.tools import ArrowTool, BondTool, MoveTool, RotateTool, SelectTool, TSBracketTool, _independent_selection_items
    from core.history import CompositeCommand, MoveAtomsCommand, MoveItemsCommand, UpdateSceneItemCommand


class _FakeItem:
    def __init__(self, kind=None, item_id=None, extra=None) -> None:
        self._data = {0: kind, 1: item_id}
        if extra is not None:
            self._data[2] = extra
        self.selected = False

    def data(self, key):
        return self._data.get(key)

    def setData(self, key, value) -> None:
        self._data[key] = value

    def setSelected(self, selected: bool) -> None:
        self.selected = selected


class _FakeScene:
    def __init__(self) -> None:
        self.clear_selection_calls = 0
        self.selected_items = []

    def clearSelection(self) -> None:
        self.clear_selection_calls += 1
        for item in self.selected_items:
            item.setSelected(False)
        self.selected_items = []

    def selectedItems(self):
        return list(self.selected_items)


class _FakeEvent:
    def __init__(
        self,
        pos: QPointF | None = None,
        *,
        button=Qt.MouseButton.LeftButton,
        modifiers=Qt.KeyboardModifier.NoModifier,
    ) -> None:
        self._pos = QPointF(pos or QPointF())
        self._button = button
        self._modifiers = modifiers

    def button(self):
        return self._button

    def modifiers(self):
        return self._modifiers

    def position(self):
        return QPointF(self._pos)


class _FakeSelectCanvas:
    DragMode = SimpleNamespace(RubberBandDrag="rubber", NoDrag="none")

    def __init__(self) -> None:
        self.drag_mode = None
        self.scene_obj = _FakeScene()
        self.atom_items = {}
        self.atom_dots = {}
        self.bond_items = {}
        self.snapshot = None
        self.bond_sets = ({1}, {2})
        self.item = None
        self.toggle_result = False
        self.handle_states = {}
        self.curved_handles_shown = []
        self.clear_handles_calls = 0
        self.preferred_item = None
        self.selection_hit = False
        self.suspend_calls = []
        self.moved_atoms = []
        self.moved_items = []
        self.shift_calls = []
        self.pushed_commands = []
        self.handle_drags = []
        self.updated_outline = 0

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def scene(self):
        return self.scene_obj

    def _selection_snapshot(self):
        return self.snapshot

    def bond_sets_for_atoms(self, atom_ids):
        return self.bond_sets

    def item_at_event(self, event):
        return self.item

    def toggle_item_selection(self, item):
        return self.toggle_result

    def scene_item_state(self, item):
        return self.handle_states.get(item, {"id": id(item)})

    def show_curved_handles(self, item) -> None:
        self.curved_handles_shown.append(item)

    def clear_handles(self) -> None:
        self.clear_handles_calls += 1

    def scene_pos_from_event(self, event):
        return event.position()

    def preferred_structure_item_at_scene_pos(self, pos):
        return self.preferred_item

    def selection_hit_test(self, pos, snapshot=None):
        return self.selection_hit

    def suspend_selection_outline(self, suspended: bool) -> None:
        self.suspend_calls.append(suspended)

    def move_atoms(self, atom_ids, dx, dy, bond_ids=None, redraw_bond_ids=None, update_selection=True) -> None:
        self.moved_atoms.append((set(atom_ids), dx, dy, bond_ids, redraw_bond_ids, update_selection))

    def move_item(self, item, dx, dy, update_selection=True) -> None:
        self.moved_items.append((item, dx, dy, update_selection))

    def shift_selection_outlines(self, dx, dy) -> None:
        self.shift_calls.append((dx, dy))

    def _push_command(self, command) -> None:
        self.pushed_commands.append(command)

    def update_handle_drag(self, handle, pos) -> None:
        self.handle_drags.append((handle, pos))

    def _update_selection_outline(self) -> None:
        self.updated_outline += 1


class _FakeBondCanvas:
    DragMode = SimpleNamespace(NoDrag="none")

    def __init__(self) -> None:
        self.drag_mode = None
        self.scene_obj = object()
        self.active_bond_style = "single"
        self.active_bond_order = 1
        self.snap_angle_step = 30
        self.renderer = SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0))
        self.preview_update_result = False
        self.preview_build_items = ["new-preview"]
        self.atom_near = None
        self.item = None
        self.preferred_item = None
        self.hover_bond_id = None
        self.model = SimpleNamespace(
            atoms={
                1: Atom("C", 10.0, 0.0),
                2: Atom("C", 0.0, 10.0),
            },
            bonds=[Bond(1, 2, 2, style="bold_in")],
        )
        self.bond_style_calls = []
        self.cycle_calls = []
        self.bond_preview_updates = []
        self.preview_build_calls = []
        self.bond_near = None
        self.default_endpoint = QPointF(15.0, 0.0)
        self.added_bonds = []
        self.scene_positions = []

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def scene(self):
        return self.scene_obj

    def update_bond_preview_items(self, preview_items, start, end, a_id, b_id, style, order):
        self.bond_preview_updates.append((list(preview_items), QPointF(start), QPointF(end), a_id, b_id, style, order))
        return self.preview_update_result

    def _build_bond_preview_items(self, start, end, a_id, b_id):
        self.preview_build_calls.append((QPointF(start), QPointF(end), a_id, b_id))
        return list(self.preview_build_items)

    def scene_pos_from_event(self, event):
        pos = event.position()
        self.scene_positions.append(pos)
        return pos

    def find_atom_near(self, x, y, radius):
        return self.atom_near

    def item_at_event(self, event):
        return self.item

    def preferred_structure_item_at_scene_pos(self, pos):
        return self.preferred_item

    def apply_bond_style(self, bond_id, style, order) -> None:
        self.bond_style_calls.append((bond_id, style, order))

    def cycle_bond_style(self, bond_id) -> None:
        self.cycle_calls.append(bond_id)

    def _find_bond_near(self, pos, radius):
        return self.bond_near

    def _default_bond_endpoint(self, start_pos, start_atom_id):
        return QPointF(self.default_endpoint)

    def add_bond_from_points(self, start, end) -> None:
        self.added_bonds.append((QPointF(start), QPointF(end)))


class _FakeMoveCanvas(_FakeSelectCanvas):
    DragMode = SimpleNamespace(NoDrag="none")

    def __init__(self) -> None:
        super().__init__()
        self.selected_items_for_transform = []
        self.selected_atom_ids = set()
        self.selected_bond_ids = set()
        self.model = SimpleNamespace(
            bonds=[
                Bond(1, 2, 1),
                Bond(2, 3, 1),
            ]
        )

    def _selected_items_for_transform(self):
        return list(self.selected_items_for_transform)

    def _selected_ids(self):
        return set(self.selected_atom_ids), set(self.selected_bond_ids)


class _FakePreviewItem:
    def __init__(self, scene_obj) -> None:
        self._scene = scene_obj

    def scene(self):
        return self._scene


class _FakePreviewScene:
    def __init__(self) -> None:
        self.removed_items = []

    def removeItem(self, item) -> None:
        self.removed_items.append(item)


class _FakePreviewCanvas:
    DragMode = SimpleNamespace(NoDrag="none")

    def __init__(self) -> None:
        self.drag_mode = None
        self.scene_obj = _FakePreviewScene()
        self.active_arrow_type = "reaction"
        self.preview_arrow_calls = []
        self.preview_ts_bracket_calls = []
        self.add_arrow_calls = []
        self.add_ts_bracket_calls = []

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def scene(self):
        return self.scene_obj

    def scene_pos_from_event(self, event):
        return event.position()

    def preview_arrow(self, start, end, arrow_type):
        self.preview_arrow_calls.append((QPointF(start), QPointF(end), arrow_type))
        return _FakePreviewItem(self.scene_obj)

    def add_arrow(self, start, end, arrow_type) -> None:
        self.add_arrow_calls.append((QPointF(start), QPointF(end), arrow_type))

    def preview_ts_bracket(self, start, end):
        self.preview_ts_bracket_calls.append((QPointF(start), QPointF(end)))
        return _FakePreviewItem(self.scene_obj)

    def add_ts_bracket_from_points(self, start, end) -> None:
        self.add_ts_bracket_calls.append((QPointF(start), QPointF(end)))


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for tools tests")
class ToolsUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_independent_selection_items_filters_duplicates_structures_and_attached_marks(self) -> None:
        mark_attached = _FakeItem("mark")
        mark_attached.setData(1, {"atom_id": 3})
        mark_free = _FakeItem("mark")
        mark_free.setData(1, {"atom_id": 9})
        kept = _FakeItem("note")
        items = [
            None,
            _FakeItem("atom"),
            _FakeItem("bond"),
            _FakeItem("ring"),
            mark_attached,
            mark_free,
            kept,
            kept,
        ]

        filtered = _independent_selection_items(items, {3})

        self.assertEqual(filtered, [mark_free, kept])

    def test_select_tool_context_begin_and_structure_selection_helpers(self) -> None:
        canvas = _FakeSelectCanvas()
        tool = SelectTool(canvas)
        tool.activate()

        self.assertEqual(canvas.drag_mode, canvas.DragMode.RubberBandDrag)
        self.assertEqual(tool._selection_drag_context(None), (set(), []))

        snapshot = SimpleNamespace(selected_atom_ids={1, 2}, selection_items=[_FakeItem("note")])
        atom_item = _FakeItem("atom", 5)
        bond_item_a = _FakeItem("bond", 7)
        bond_item_b = _FakeItem("bond", 7)
        ring_item = _FakeItem("ring")
        canvas.atom_items[5] = atom_item
        canvas.bond_items[7] = [bond_item_a, bond_item_b]

        self.assertEqual(tool._selection_drag_context(snapshot), ({1, 2}, list(snapshot.selection_items)))
        self.assertTrue(tool._select_structure_item(atom_item))
        self.assertTrue(atom_item.selected)
        self.assertTrue(tool._select_structure_item(_FakeItem("bond", 7)))
        self.assertTrue(bond_item_a.selected and bond_item_b.selected)
        self.assertTrue(tool._select_structure_item(ring_item))
        self.assertTrue(ring_item.selected)
        self.assertFalse(tool._select_structure_item(_FakeItem("atom", "bad")))
        self.assertFalse(tool._begin_selection_drag(set(), [], QPointF()))

        selection_items = [_FakeItem("note"), _FakeItem("mark")]
        selection_items[1].setData(1, {"atom_id": 1})
        self.assertTrue(tool._begin_selection_drag({1}, selection_items, QPointF(3.0, 4.0)))
        self.assertEqual(tool._selection_atom_ids, {1})
        self.assertEqual(len(tool._selection_items), 1)
        self.assertEqual(tool._drag_bond_ids, {1})
        self.assertEqual(tool._drag_boundary_bond_ids, {2})

    def test_select_tool_mouse_press_handles_shift_handle_curve_and_drag_paths(self) -> None:
        canvas = _FakeSelectCanvas()
        tool = SelectTool(canvas)
        event = _FakeEvent(QPointF(1.0, 2.0), modifiers=Qt.KeyboardModifier.ShiftModifier)
        canvas.item = _FakeItem("note")
        canvas.toggle_result = True

        self.assertTrue(tool.on_mouse_press(event))

        handle_target = object()
        handle = _FakeItem("handle", extra=handle_target)
        canvas.item = handle
        canvas.toggle_result = False
        handle_event = _FakeEvent(QPointF(3.0, 4.0))
        self.assertTrue(tool.on_mouse_press(handle_event))
        self.assertIs(tool._active_handle, handle)
        self.assertIs(tool._handle_target, handle_target)

        curved = _FakeItem("curved_double")
        canvas.item = curved
        tool._active_handle = None
        self.assertFalse(tool.on_mouse_press(_FakeEvent(QPointF(4.0, 5.0))))
        self.assertEqual(canvas.curved_handles_shown, [curved])

        preferred = _FakeItem("atom", 4)
        atom_item = _FakeItem("atom", 4)
        canvas.preferred_item = preferred
        canvas.atom_items[4] = atom_item
        canvas.item = None
        canvas.scene_obj.selected_items = []
        canvas.snapshot = SimpleNamespace(selected_atom_ids={4}, selection_items=[_FakeItem("note")])
        canvas.selection_hit = False
        drag_event = _FakeEvent(QPointF(8.0, 9.0))
        self.assertTrue(tool.on_mouse_press(drag_event))
        self.assertTrue(tool._drag_selection)
        self.assertEqual(tool._start_pos, drag_event.position())

    def test_select_tool_drag_move_and_release_build_commands(self) -> None:
        canvas = _FakeSelectCanvas()
        tool = SelectTool(canvas)
        moved_item = _FakeItem("note")
        tool._drag_selection = True
        tool._selection_atom_ids = {1, 2}
        tool._selection_items = [moved_item]
        tool._drag_bond_ids = {8}
        tool._drag_boundary_bond_ids = {9}
        tool._start_pos = QPointF(1.0, 1.0)

        tool._apply_drag_delta(QPointF(2.0, -1.0))
        self.assertEqual(canvas.suspend_calls, [True])
        self.assertEqual(canvas.moved_atoms[0][:3], ({1, 2}, 2.0, -1.0))
        self.assertEqual(canvas.moved_items[0][1:3], (2.0, -1.0))
        self.assertEqual(tool._total_delta, QPointF(2.0, -1.0))

        move_command = tool._build_move_command()
        self.assertIsInstance(move_command, CompositeCommand)
        self.assertIsInstance(move_command.commands[0], MoveAtomsCommand)
        self.assertIsInstance(move_command.commands[1], MoveItemsCommand)

        handle = _FakeItem("handle")
        target = object()
        before_state = {"x": 1}
        after_state = {"x": 2}
        tool._active_handle = handle
        tool._handle_target = target
        tool._handle_before_state = before_state
        canvas.handle_states[target] = after_state
        self.assertTrue(tool.on_mouse_release(_FakeEvent(QPointF(0.0, 0.0))))
        self.assertIsInstance(canvas.pushed_commands[-1], UpdateSceneItemCommand)

        tool._drag_selection = True
        tool._selection_atom_ids = {1}
        tool._selection_items = []
        tool._drag_bond_ids = {8}
        tool._drag_boundary_bond_ids = {9}
        tool._start_pos = QPointF(1.0, 1.0)
        tool._moved = True
        tool._suspended_outline = True
        tool._total_delta = QPointF(3.0, 4.0)
        self.assertTrue(tool.on_mouse_release(_FakeEvent(QPointF(2.0, 3.0))))
        self.assertEqual(canvas.suspend_calls[-1], False)
        self.assertGreaterEqual(canvas.updated_outline, 1)
        self.assertFalse(tool._drag_selection)
        self.assertIsNone(tool._start_pos)

    def test_select_tool_mouse_move_handles_active_handle_and_drag_throttling(self) -> None:
        canvas = _FakeSelectCanvas()
        tool = SelectTool(canvas)
        handle = _FakeItem("handle")
        tool._active_handle = handle
        event = _FakeEvent(QPointF(5.0, 6.0))
        self.assertTrue(tool.on_mouse_move(event))
        self.assertEqual(canvas.handle_drags[0][0], handle)

        tool._active_handle = None
        tool._start_pos = QPointF(1.0, 1.0)
        tool._drag_selection = True
        tool._last_drag_time = 100.0
        with mock.patch.object(tools_module.time, "monotonic", return_value=100.0 + tool._drag_interval / 2.0):
            self.assertTrue(tool.on_mouse_move(_FakeEvent(QPointF(3.0, 4.0))))
        self.assertEqual(canvas.shift_calls, [])

        with mock.patch.object(tools_module.time, "monotonic", return_value=100.0 + tool._drag_interval * 2.0):
            self.assertTrue(tool.on_mouse_move(_FakeEvent(QPointF(4.0, 5.0))))
        self.assertTrue(canvas.shift_calls)

    def test_rotate_tool_activate_press_move_and_release(self) -> None:
        canvas = SimpleNamespace(
            DragMode=SimpleNamespace(NoDrag="none"),
            drag_mode=None,
            rotations=[],
            setDragMode=lambda mode: setattr(canvas, "drag_mode", mode),
            rotate_view=lambda amount: canvas.rotations.append(amount),
        )
        tool = RotateTool(canvas)
        tool.activate()

        self.assertEqual(canvas.drag_mode, canvas.DragMode.NoDrag)
        self.assertFalse(tool.on_mouse_press(_FakeEvent(button=Qt.MouseButton.RightButton)))
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        self.assertTrue(tool.on_mouse_move(_FakeEvent(QPointF(6.0, 1.0))))
        self.assertEqual(canvas.rotations, [1.5])
        self.assertFalse(tool.on_mouse_release(_FakeEvent()))
        self.assertFalse(tool.on_mouse_move(_FakeEvent(QPointF(8.0, 1.0))))

    def test_move_tool_selection_drag_builds_composite_move_command(self) -> None:
        canvas = _FakeMoveCanvas()
        tool = MoveTool(canvas)
        tool.activate()

        selected_note = _FakeItem("note")
        canvas.selected_items_for_transform = [selected_note]
        canvas.selected_atom_ids = {1}
        canvas.selected_bond_ids = {1}

        press_event = _FakeEvent(QPointF(10.0, 20.0))
        self.assertTrue(tool.on_mouse_press(press_event))
        self.assertEqual(canvas.drag_mode, canvas.DragMode.NoDrag)
        self.assertTrue(tool._drag_selection)
        self.assertEqual(tool._selection_atom_ids, {1, 2, 3})

        tool._apply_drag_delta(QPointF(6.0, -4.0))
        self.assertEqual(canvas.suspend_calls, [True])
        self.assertEqual(canvas.moved_atoms[0][:3], ({1, 2, 3}, 6.0, -4.0))
        self.assertEqual(canvas.moved_items[0][1:3], (6.0, -4.0))

        self.assertTrue(tool.on_mouse_release(_FakeEvent(QPointF(16.0, 16.0))))
        self.assertEqual(canvas.suspend_calls[-1], False)
        self.assertIsInstance(canvas.pushed_commands[-1], CompositeCommand)
        self.assertFalse(tool._drag_selection)
        self.assertIsNone(tool._drag_item)

    def test_move_tool_item_drag_pushes_move_items_command(self) -> None:
        canvas = _FakeMoveCanvas()
        tool = MoveTool(canvas)
        moved_item = _FakeItem("arrow")
        canvas.item = moved_item

        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        self.assertIs(tool._drag_item, moved_item)

        tool._apply_drag_delta(QPointF(5.0, 3.0))
        self.assertEqual(canvas.moved_items[0], (moved_item, 5.0, 3.0, True))

        self.assertTrue(tool.on_mouse_release(_FakeEvent(QPointF(6.0, 4.0))))
        self.assertIsInstance(canvas.pushed_commands[-1], MoveItemsCommand)
        self.assertEqual(canvas.updated_outline, 1)
        self.assertIsNone(tool._drag_item)

    def test_move_tool_covers_noop_invalid_and_throttled_wrapper_paths(self) -> None:
        canvas = _FakeMoveCanvas()
        tool = MoveTool(canvas)

        self.assertFalse(tool.on_mouse_press(_FakeEvent(button=Qt.MouseButton.RightButton)))
        self.assertFalse(tool.on_mouse_move(_FakeEvent(QPointF(1.0, 1.0))))
        tool._apply_drag_delta(QPointF(2.0, 3.0))
        self.assertEqual(canvas.moved_items, [])

        selected_note = _FakeItem("note")
        canvas.selected_items_for_transform = [selected_note]
        canvas.selected_atom_ids = set()
        canvas.selected_bond_ids = {1, 99}
        canvas.model.bonds[1] = None
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(2.0, 2.0))))
        self.assertTrue(tool._drag_selection)
        self.assertEqual(tool._selection_atom_ids, set())

        tool = MoveTool(_FakeMoveCanvas())
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        self.assertIsNone(tool._drag_item)

        canvas = _FakeMoveCanvas()
        tool = MoveTool(canvas)
        canvas.item = _FakeItem("note")
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        self.assertIsNone(tool._drag_item)

        moved_item = _FakeItem("arrow")
        canvas.item = moved_item
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        tool._last_drag_time = 100.0
        with mock.patch.object(tools_module.time, "monotonic", return_value=100.0 + tool._drag_interval / 2.0):
            self.assertTrue(tool.on_mouse_move(_FakeEvent(QPointF(4.0, 5.0))))
        self.assertEqual(canvas.moved_items, [])

        with mock.patch.object(tools_module.time, "monotonic", return_value=100.0 + tool._drag_interval * 2.0):
            self.assertTrue(tool.on_mouse_move(_FakeEvent(QPointF(4.0, 5.0))))
        self.assertEqual(canvas.moved_items[-1][1:3], (3.0, 4.0))

        tool._start_pos = QPointF(4.0, 5.0)
        tool._moved = False
        self.assertTrue(tool.on_mouse_release(_FakeEvent(QPointF(4.0, 5.0))))
        self.assertEqual(len(canvas.pushed_commands), 0)

    def test_bond_tool_preview_management_and_snap_helpers(self) -> None:
        canvas = _FakeBondCanvas()
        tool = BondTool(canvas)

        with mock.patch.object(tools_module, "clear_bond_preview_items_helper", return_value=[]) as clear_helper:
            tool._preview_items = ["old"]
            tool._preview_signature = "single:1"
            tool._clear_preview_items()
            clear_helper.assert_called_once_with(canvas.scene(), ["old"])
            self.assertEqual(tool._preview_items, [])
            self.assertIsNone(tool._preview_signature)

        tool.activate()
        self.assertEqual(canvas.drag_mode, canvas.DragMode.NoDrag)

        tool._preview_items = ["existing"]
        tool._preview_signature = "single:1"
        tool._start_atom_id = 5
        canvas.preview_update_result = True
        tool._set_preview_items(QPointF(0.0, 0.0), QPointF(10.0, 0.0))
        self.assertEqual(canvas.bond_preview_updates[-1][3], 5)

        canvas.preview_update_result = False
        with mock.patch.object(tools_module, "add_bond_preview_items_helper", return_value=["added"]) as add_helper:
            with mock.patch.object(tools_module, "clear_bond_preview_items_helper", return_value=[]):
                tool._set_preview_items(QPointF(0.0, 0.0), QPointF(10.0, 0.0))
            add_helper.assert_called_once()
        self.assertEqual(tool._preview_items, ["added"])
        self.assertEqual(tool._preview_signature, "single:1")

        canvas.atom_near = 1
        snapped = tool._snap_to_atom(QPointF(2.0, 3.0))
        self.assertEqual((snapped.x(), snapped.y()), (10.0, 0.0))
        self.assertEqual(tool._start_atom_id, 1)

        unsnapped = tool._snap_to_atom(QPointF(2.0, 3.0), ignore_start=True)
        self.assertEqual((unsnapped.x(), unsnapped.y()), (2.0, 3.0))

        canvas.atom_near = None
        canvas.bond_near = 0
        bond_snap = tool._snap_to_atom(QPointF(8.0, 1.0))
        self.assertEqual((bond_snap.x(), bond_snap.y()), (10.0, 0.0))
        endpoint = tool._snap_endpoint(QPointF(0.0, 0.0), QPointF(8.0, 4.0))
        self.assertAlmostEqual(endpoint.x(), 17.320508075688775)
        self.assertAlmostEqual(endpoint.y(), 10.0)

    def test_bond_tool_mouse_press_move_release_and_style_dispatch(self) -> None:
        canvas = _FakeBondCanvas()
        tool = BondTool(canvas)

        canvas.item = _FakeItem("bond", 0)
        canvas.active_bond_style = "wedge"
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        self.assertEqual(canvas.bond_style_calls[-1], (0, "wedge", 1))

        canvas.active_bond_style = "bold"
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        self.assertEqual(canvas.bond_style_calls[-1], (0, "bold_out", 2))

        canvas.active_bond_style = "single"
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        self.assertEqual(canvas.cycle_calls[-1], 0)

        canvas.model.bonds[0] = Bond(1, 2, 2, style="double")
        canvas.active_bond_style = "dotted"
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        self.assertEqual(canvas.bond_style_calls[-1], (0, "dotted_double", 2))

        canvas.model.bonds[0] = Bond(1, 2, 2, style="bold_in")
        canvas.item = None
        canvas.hover_bond_id = 0
        canvas.active_bond_style = "bold"
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        self.assertEqual(canvas.bond_style_calls[-1], (0, "bold_out", 2))

        canvas.hover_bond_id = None
        canvas.atom_near = 1
        with mock.patch.object(tool, "_set_preview_items") as preview:
            self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(2.0, 2.0))))
            preview.assert_called_once()

        canvas.atom_near = None
        canvas.item = None
        canvas.preferred_item = _FakeItem("bond", 0)
        canvas.active_bond_style = "single"
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(3.0, 3.0))))
        self.assertEqual(canvas.cycle_calls[-1], 0)
        canvas.preferred_item = None

        with mock.patch.object(tool, "_set_preview_items") as preview:
            self.assertTrue(tool.on_mouse_move(_FakeEvent(QPointF(4.0, 4.0))))
            preview.assert_called_once()

        with mock.patch.object(tool, "_clear_preview_items") as clear_preview:
            tool._press_scene_pos = QPointF(2.0, 2.0)
            tool._start_pos = QPointF(10.0, 0.0)
            tool._start_atom_id = 1
            self.assertTrue(tool.on_mouse_release(_FakeEvent(QPointF(2.5, 2.5))))
            clear_preview.assert_called_once()
        start, end = canvas.added_bonds[-1]
        self.assertEqual((start.x(), start.y()), (10.0, 0.0))
        self.assertEqual((end.x(), end.y()), (15.0, 0.0))

        tool._start_pos = None
        self.assertFalse(tool.on_mouse_move(_FakeEvent(QPointF(0.0, 0.0))))
        self.assertFalse(tool.on_mouse_release(_FakeEvent(QPointF(0.0, 0.0))))

    def test_arrow_tool_preview_drag_and_deactivate_cleanup(self) -> None:
        canvas = _FakePreviewCanvas()
        tool = ArrowTool(canvas, mode="auto")
        tool.activate()

        self.assertEqual(canvas.drag_mode, canvas.DragMode.NoDrag)
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 2.0))))
        self.assertTrue(tool.on_mouse_move(_FakeEvent(QPointF(5.0, 6.0))))
        self.assertEqual(canvas.preview_arrow_calls[-1][2], "reaction")

        self.assertTrue(tool.on_mouse_release(_FakeEvent(QPointF(8.0, 9.0))))
        start, end, arrow_type = canvas.add_arrow_calls[-1]
        self.assertEqual((start.x(), start.y()), (1.0, 2.0))
        self.assertEqual((end.x(), end.y()), (8.0, 9.0))
        self.assertEqual(arrow_type, "reaction")
        self.assertTrue(canvas.scene_obj.removed_items)

        tool.on_mouse_press(_FakeEvent(QPointF(2.0, 3.0)))
        tool.on_mouse_move(_FakeEvent(QPointF(4.0, 7.0)))
        tool.deactivate()
        self.assertIsNone(tool._start_pos)
        self.assertIsNone(tool._preview_item)

    def test_ts_bracket_tool_preview_drag_and_deactivate_cleanup(self) -> None:
        canvas = _FakePreviewCanvas()
        tool = TSBracketTool(canvas)
        tool.activate()

        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(3.0, 4.0))))
        self.assertTrue(tool.on_mouse_move(_FakeEvent(QPointF(9.0, 10.0))))
        self.assertEqual(len(canvas.preview_ts_bracket_calls), 1)

        self.assertTrue(tool.on_mouse_release(_FakeEvent(QPointF(12.0, 13.0))))
        start, end = canvas.add_ts_bracket_calls[-1]
        self.assertEqual((start.x(), start.y()), (3.0, 4.0))
        self.assertEqual((end.x(), end.y()), (12.0, 13.0))

        tool.on_mouse_press(_FakeEvent(QPointF(0.0, 1.0)))
        tool.on_mouse_move(_FakeEvent(QPointF(2.0, 3.0)))
        tool.deactivate()
        self.assertIsNone(tool._start_pos)
        self.assertIsNone(tool._preview_item)

    def test_preview_drag_base_and_inherited_false_paths(self) -> None:
        canvas = _FakePreviewCanvas()
        preview_tool = tools_module._PreviewDragTool("preview", canvas)
        with self.assertRaises(NotImplementedError):
            preview_tool._build_preview(QPointF(1.0, 2.0))
        with self.assertRaises(NotImplementedError):
            preview_tool._commit_drag(QPointF(3.0, 4.0))

        tool = ArrowTool(canvas)
        self.assertFalse(tool.on_mouse_press(_FakeEvent(button=Qt.MouseButton.RightButton)))
        self.assertFalse(tool.on_mouse_move(_FakeEvent(QPointF(1.0, 2.0))))
        self.assertFalse(tool.on_mouse_release(_FakeEvent(QPointF(1.0, 2.0))))


if __name__ == "__main__":
    unittest.main()
