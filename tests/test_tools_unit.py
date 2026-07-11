import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QPolygonF
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsEllipseItem,
        QGraphicsPolygonItem,
        QGraphicsScene,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    import ui.bond_tool as bond_tool_module
    import ui.canvas_move_controller as canvas_move_controller_module
    import ui.move_tool as move_tool_module
    import ui.rotate_tool as rotate_tool_module
    import ui.select_tool as select_tool_module
    import ui.selection_drag_tool as selection_drag_tool_module
    from core.history import (
        CompositeCommand,
        HistoryTransactionRestoreResult,
        MoveAtomsCommand,
    )
    from core.model import Atom, Bond
    from ui.canvas_atom_graphics_state import (
        atom_dots_for,
        atom_items_for,
        set_atom_dots_for,
        set_atom_items_for,
    )
    from ui.canvas_bond_graphics_state import bond_items_for, set_bond_items_for
    from ui.canvas_hover_state import set_hover_bond_id_for
    from ui.canvas_scene_items_state import (
        selected_notes_for,
        set_scene_item_collection_for,
        set_selected_notes_for,
    )
    from ui.canvas_tool_settings_state import set_tool_setting_for
    from ui.canvas_view import CanvasView
    from ui.graphics_items import AtomLabelItem
    from ui.handle_state import CanvasHandleState
    from ui.history_commands import MoveItemsCommand, UpdateSceneItemCommand
    from ui.preview_tools import PreviewDragTool
    from ui.scene_item_state import scene_item_state_for
    from ui.selection_drag_tool import independent_selection_items
    from ui.selection_style_state import selection_style_state_for
    from ui.tool_context import ToolContext
    from ui.tools import (
        ArrowTool,
        BondTool,
        MoveTool,
        RotateTool,
        SelectTool,
        Tool,
        TSBracketTool,
    )


def _tool_context_for(canvas):
    services = getattr(canvas, "services", None)
    graph_service = getattr(services, "canvas_graph_service", None)
    color_mutation_service = getattr(services, "canvas_color_mutation_service", None)
    tool_mode_controller = getattr(services, "tool_mode_controller", None)

    def selected_items(*, excluded_kinds):
        scene = getattr(canvas, "scene", None)
        if not callable(scene):
            return []
        return [item for item in scene().selectedItems() if item.data(0) not in excluded_kinds]

    return ToolContext(
        canvas,
        hit_testing_service=getattr(services, "hit_testing_service", None),
        selection_controller=getattr(services, "selection_controller", None),
        note_controller=getattr(
            services,
            "note_controller",
            SimpleNamespace(create_text_note=mock.Mock(), begin_note_edit=mock.Mock()),
        ),
        handle_controller=getattr(
            services,
            "handle_controller",
            SimpleNamespace(update_handle_drag=mock.Mock()),
        ),
        selection_rotation_controller=getattr(
            services,
            "selection_rotation_controller",
            SimpleNamespace(
                begin_selection_3d_rotation=mock.Mock(return_value=False),
                update_selection_3d_rotation=mock.Mock(),
                end_selection_3d_rotation=mock.Mock(),
            ),
        ),
        scene_delete_controller=getattr(
            services,
            "scene_delete_controller",
            SimpleNamespace(
                delete_atom=mock.Mock(),
                delete_bond=mock.Mock(),
                delete_ring=mock.Mock(),
            ),
        ),
        scene_transform_controller=getattr(
            services,
            "scene_transform_controller",
            SimpleNamespace(
                apply_bond_style=mock.Mock(),
                cycle_bond_style=mock.Mock(),
                flip_bond_direction=mock.Mock(),
            ),
        ),
        style_controller=getattr(
            services,
            "style_controller",
            SimpleNamespace(suspend_selection_outline=mock.Mock()),
        ),
        bond_sets_for_atoms=getattr(graph_service, "bond_sets_for_atoms", None),
        color_mutation_service=color_mutation_service,
        selected_scene_items=selected_items,
        select_single_structure_item=getattr(canvas, "select_structure_for_item", None),
        atom_symbol_provider=getattr(tool_mode_controller, "get_atom_symbol", None),
        history_service=getattr(services, "history_service", None),
        set_drag_mode=getattr(canvas, "setDragMode", None),
        rubber_band_drag_mode=getattr(getattr(canvas, "DragMode", None), "RubberBandDrag", None),
    )


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


class _FakeHistoryService:
    def __init__(self, *, history=None, redo_stack=None) -> None:
        self.state = SimpleNamespace(
            history=list(history or ()),
            redo_stack=list(redo_stack or ()),
            enabled=True,
            limit=100,
            change_callback=None,
        )
        self.push_calls = []

    def push(self, command) -> None:
        self.push_calls.append(command)
        if not self.state.enabled:
            return
        self.state.history.append(command)
        if len(self.state.history) > self.state.limit:
            self.state.history.pop(0)
        self.state.redo_stack.clear()

    def notify_change(self) -> None:
        return


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
        set_atom_items_for(self, {})
        set_atom_dots_for(self, {})
        set_bond_items_for(self, {})
        self.snapshot = None
        self.bond_sets = ({1}, {2})
        self.item = None
        self.toggle_result = False
        self.curved_handles_shown = []
        self.clear_handles_calls = 0
        self.handle_state = CanvasHandleState()
        self.preferred_item = None
        self.selection_hit = False
        self.suspend_calls = []
        self.moved_atoms = []
        self.moved_items = []
        self.shift_calls = []
        self.pushed_commands = []
        self.history_service = SimpleNamespace(
            state=SimpleNamespace(
                history=[],
                redo_stack=[],
                enabled=True,
                limit=100,
                change_callback=None,
            ),
            push=self.push_command,
            notify_change=lambda: None,
        )
        self.handle_drags = []
        self.updated_outline = 0
        self.services = SimpleNamespace(
            history_service=self.history_service,
            canvas_graph_service=SimpleNamespace(bond_sets_for_atoms=self.bond_sets_for_atoms),
            hit_testing_service=SimpleNamespace(
                scene_pos_from_event=self.scene_pos_from_event,
                item_at_event=self.item_at_event,
            ),
            selection_controller=SimpleNamespace(
                toggle_item_selection=self.toggle_item_selection,
                preferred_structure_item_at_scene_pos=self.preferred_structure_item_at_scene_pos,
                selection_hit_test=self.selection_hit_test,
                select_structure_for_item=self.select_structure_for_item,
                update_selection_outline=self.refresh_selection_outline,
                shift_selection_outlines=self.shift_selection_outlines,
            ),
            move_controller=SimpleNamespace(
                move_atoms=self.move_atoms,
                move_item=self.move_item,
            ),
            style_controller=SimpleNamespace(suspend_selection_outline=self.suspend_selection_outline),
            handle_overlay_service=SimpleNamespace(
                clear_handles=self.clear_handles,
                show_curved_handles=self.show_curved_handles,
            ),
            handle_controller=SimpleNamespace(update_handle_drag=self.update_handle_drag),
        )

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def scene(self):
        return self.scene_obj

    @property
    def atom_items(self):
        return atom_items_for(self)

    @atom_items.setter
    def atom_items(self, value) -> None:
        set_atom_items_for(self, value)

    @property
    def atom_dots(self):
        return atom_dots_for(self)

    @atom_dots.setter
    def atom_dots(self, value) -> None:
        set_atom_dots_for(self, value)

    @property
    def bond_items(self):
        return bond_items_for(self)

    @bond_items.setter
    def bond_items(self, value) -> None:
        set_bond_items_for(self, value)

    def bond_sets_for_atoms(self, atom_ids):
        return self.bond_sets

    def item_at_event(self, event):
        return self.item

    def toggle_item_selection(self, item):
        return self.toggle_result

    def select_structure_for_item(self, item) -> bool:
        kind = item.data(0)
        item_id = item.data(1)
        self.scene_obj.clearSelection()
        if kind == "atom" and isinstance(item_id, int):
            atom_item = self.atom_items.get(item_id)
            if atom_item is None:
                return False
            atom_item.setSelected(True)
            self.scene_obj.selected_items = [atom_item]
            return True
        if kind == "bond" and isinstance(item_id, int):
            bond_items = self.bond_items.get(item_id, [])
            if not bond_items:
                return False
            for bond_item in bond_items:
                bond_item.setSelected(True)
            self.scene_obj.selected_items = list(bond_items)
            return True
        if kind == "ring":
            item.setSelected(True)
            self.scene_obj.selected_items = [item]
            return True
        return False

    def show_curved_handles(self, item) -> None:
        self.curved_handles_shown.append(item)

    def clear_handles(self) -> None:
        self.clear_handles_calls += 1
        self.handle_state.active_handles = []
        self.handle_state.target = None

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

    def push_command(self, command) -> None:
        if not self.history_service.state.enabled:
            return
        self.history_service.state.history.append(command)
        if (
            len(self.history_service.state.history)
            > self.history_service.state.limit
        ):
            self.history_service.state.history.pop(0)
        self.history_service.state.redo_stack.clear()
        self.pushed_commands.append(command)

    def update_handle_drag(self, handle, pos) -> None:
        self.handle_drags.append((handle, pos))

    def refresh_selection_outline(self) -> None:
        self.updated_outline += 1


class _FakeBondCanvas:
    DragMode = SimpleNamespace(NoDrag="none")

    def __init__(self) -> None:
        self.drag_mode = None
        self.scene_obj = _FakeScene()
        self.active_bond_style = "single"
        self.active_bond_order = 1
        self.snap_angle_step = 30
        self.renderer = SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0))
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
        self.services = SimpleNamespace(
            scene_transform_controller=SimpleNamespace(
                apply_bond_style=self.apply_bond_style,
                cycle_bond_style=self.cycle_bond_style,
            ),
            hit_testing_service=SimpleNamespace(
                scene_pos_from_event=self.scene_pos_from_event,
                item_at_event=self.item_at_event,
                find_atom_near=self.find_atom_near,
                find_bond_near=self.find_bond_near,
            ),
            selection_controller=SimpleNamespace(
                preferred_structure_item_at_scene_pos=self.preferred_structure_item_at_scene_pos,
                clear_note_selection=self.clear_note_selection,
            ),
            structure_build_service=SimpleNamespace(add_bond_between_points=self.add_bond_between_points),
        )
        self.preview_build_calls = []
        self.bond_near = None
        self.default_endpoint = QPointF(15.0, 0.0)
        self.added_bonds = []
        self.scene_positions = []
        set_selected_notes_for(self, [])
        self.clear_note_selection_calls = 0
    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def scene(self):
        return self.scene_obj

    def clear_note_selection(self) -> None:
        self.clear_note_selection_calls += 1
        set_selected_notes_for(self, [])

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

    def find_bond_near(self, pos, radius):
        return self.bond_near

    def add_bond_between_points(self, start, end, style, order) -> None:
        self.added_bonds.append((QPointF(start), QPointF(end)))

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
        self.services = SimpleNamespace(
            hit_testing_service=SimpleNamespace(scene_pos_from_event=self.scene_pos_from_event),
            scene_decoration_service=SimpleNamespace(
                add_arrow=self.add_arrow,
                add_ts_bracket=lambda rect: self.add_ts_bracket_from_points(rect.topLeft(), rect.bottomRight()),
            ),
            scene_decoration_build_service=SimpleNamespace(
                preview_arrow=self.preview_arrow,
                preview_ts_bracket=self.preview_ts_bracket,
                ts_bracket_rect_from_points=lambda start, end: QRectF(start, end).normalized(),
            ),
        )

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

        filtered = independent_selection_items(items, {3})

        self.assertEqual(filtered, [mark_free, kept])

    def test_base_tool_and_selection_drag_helpers_cover_item_only_and_noop_paths(self) -> None:
        base_tool = Tool("base")
        base_tool.activate()
        base_tool.deactivate()
        self.assertFalse(base_tool.on_mouse_press(_FakeEvent()))
        self.assertFalse(base_tool.on_mouse_move(_FakeEvent()))
        self.assertFalse(base_tool.on_mouse_release(_FakeEvent()))

        canvas = _FakeSelectCanvas()
        tool = SelectTool(canvas, context=_tool_context_for(canvas))
        tool._apply_drag_delta(QPointF(1.0, 2.0))
        self.assertEqual(canvas.moved_atoms, [])
        self.assertEqual(canvas.moved_items, [])

        selection_item = _FakeItem("note")
        self.assertTrue(tool._begin_selection_drag(set(), [selection_item], QPointF(0.0, 0.0)))
        self.assertEqual(tool._drag_bond_ids, set())
        self.assertEqual(tool._drag_boundary_bond_ids, set())
        self.assertIsNone(tool._build_move_command())
        tool._total_delta = QPointF(1.0, 0.0)
        item_only_command = tool._build_move_command()
        self.assertIsInstance(item_only_command, MoveItemsCommand)

        tool._selection_atom_ids = set()
        tool._selection_items = []
        self.assertIsNone(tool._build_move_command())
        tool._moved = True
        tool._suspended_outline = False
        tool._commit_selection_drag()
        self.assertEqual(canvas.updated_outline, 1)
        self.assertEqual(canvas.pushed_commands, [])

    def test_select_tool_begin_and_structure_selection_helpers(self) -> None:
        canvas = _FakeSelectCanvas()
        tool = SelectTool(canvas, context=_tool_context_for(canvas))
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

    def test_select_tool_additional_guard_paths_cover_invalid_targets_and_decisions(self) -> None:
        canvas = _FakeSelectCanvas()
        tool = SelectTool(canvas, context=_tool_context_for(canvas))

        self.assertFalse(tool._select_structure_item(None))
        self.assertFalse(tool._select_structure_item(_FakeItem("atom", 4)))
        self.assertFalse(tool._select_structure_item(_FakeItem("bond", "bad")))
        self.assertFalse(tool._select_structure_item(_FakeItem("bond", 8)))
        self.assertFalse(tool._select_structure_item(_FakeItem("other", 1)))
        self.assertFalse(tool.on_mouse_press(_FakeEvent(button=Qt.MouseButton.RightButton)))

        canvas.item = _FakeItem("note")
        canvas.toggle_result = False
        canvas.preferred_item = None
        self.assertFalse(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 2.0), modifiers=Qt.KeyboardModifier.ShiftModifier)))

        canvas.scene_obj.selected_items = [_FakeItem("note")]
        canvas.snapshot = SimpleNamespace(selected_atom_ids={1}, selection_items=[_FakeItem("note")])
        canvas.atom_items[1] = _FakeItem("atom", 1)
        canvas.preferred_item = _FakeItem("atom", 1)
        canvas.item = None
        with mock.patch.object(select_tool_module, "plan_selection_press", return_value=SimpleNamespace(action="ignore")):
            self.assertFalse(tool.on_mouse_press(_FakeEvent(QPointF(2.0, 3.0))))

        with mock.patch.object(
            select_tool_module,
            "plan_selection_press",
            return_value=SimpleNamespace(action="reselect_preferred_and_drag"),
        ):
            canvas.preferred_item = None
            self.assertFalse(tool.on_mouse_press(_FakeEvent(QPointF(2.0, 3.0))))

        with mock.patch.object(
            select_tool_module,
            "plan_selection_press",
            return_value=SimpleNamespace(action="reselect_preferred_and_drag"),
        ):
            canvas.preferred_item = _FakeItem("atom", 4)
            self.assertFalse(tool.on_mouse_press(_FakeEvent(QPointF(2.0, 3.0))))

        with mock.patch.object(
            select_tool_module,
            "plan_selection_press",
            return_value=SimpleNamespace(action="reselect_preferred_and_drag"),
        ):
            canvas.preferred_item = _FakeItem("atom", 5)
            canvas.atom_items[5] = _FakeItem("atom", 5)
            canvas.snapshot = SimpleNamespace(selected_atom_ids=set(), selection_items=[])
            self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(2.0, 3.0))))

        tool._reset_selection_drag_state()
        tool._start_pos = None
        self.assertFalse(tool.on_mouse_move(_FakeEvent(QPointF(9.0, 9.0))))

    def test_select_tool_mouse_press_handles_shift_handle_curve_and_drag_paths(self) -> None:
        canvas = _FakeSelectCanvas()
        tool = SelectTool(canvas, context=_tool_context_for(canvas))
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
        canvas.scene_obj.selected_items = []
        self.assertFalse(tool.on_mouse_press(_FakeEvent(QPointF(4.0, 5.0))))
        self.assertEqual(canvas.curved_handles_shown, [])

        canvas.scene_obj.selected_items = [curved]
        canvas.snapshot = SimpleNamespace(selected_atom_ids=set(), selection_items=[curved])
        second_click = _FakeEvent(QPointF(4.0, 5.0))
        self.assertTrue(tool.on_mouse_press(second_click))
        self.assertTrue(tool.on_mouse_release(second_click))
        self.assertEqual(canvas.curved_handles_shown, [curved])
        self.assertIsNone(tool._pending_curved_handle_item)

        canvas.item = None
        canvas.selection_hit = True
        overlay_click = _FakeEvent(QPointF(4.0, 5.0))
        self.assertTrue(tool.on_mouse_press(overlay_click))
        self.assertTrue(tool.on_mouse_release(overlay_click))
        self.assertEqual(canvas.curved_handles_shown, [curved, curved])
        canvas.selection_hit = False

        canvas.handle_state.target = curved
        canvas.handle_state.active_handles = [object()]
        canvas.item = None
        canvas.selection_hit = True
        third_click = _FakeEvent(QPointF(4.0, 5.0))
        self.assertTrue(tool.on_mouse_press(third_click))
        self.assertTrue(tool.on_mouse_release(third_click))
        self.assertEqual(canvas.clear_handles_calls, 2)
        canvas.selection_hit = False

        preferred = _FakeItem("atom", 4)
        atom_item = _FakeItem("atom", 4)
        canvas.preferred_item = preferred
        canvas.atom_items[4] = atom_item
        canvas.item = None
        canvas.scene_obj.selected_items = [atom_item]
        canvas.selection_hit = True
        drag_event = _FakeEvent(QPointF(8.0, 9.0))
        self.assertTrue(tool.on_mouse_press(drag_event))
        self.assertTrue(tool._drag_selection)
        self.assertEqual(tool._start_pos, drag_event.position())

    def test_select_tool_drag_move_and_release_build_commands(self) -> None:
        canvas = _FakeSelectCanvas()
        tool = SelectTool(canvas, context=_tool_context_for(canvas))
        moved_item = _FakeItem("note")
        canvas.bond_sets = ({8}, {9})
        self.assertTrue(
            tool._begin_selection_drag(
                {1, 2},
                [moved_item],
                QPointF(1.0, 1.0),
            )
        )

        tool._apply_drag_delta(QPointF(2.0, -1.0))
        self.assertEqual(canvas.suspend_calls, [True])
        self.assertEqual(canvas.moved_atoms[0][:3], ({1, 2}, 2.0, -1.0))
        self.assertEqual(canvas.moved_items[0][1:3], (2.0, -1.0))
        self.assertEqual(tool._total_delta, QPointF(2.0, -1.0))

        move_command = tool._build_move_command()
        self.assertIsInstance(move_command, CompositeCommand)
        self.assertIsInstance(move_command.commands[0], MoveAtomsCommand)
        self.assertIsInstance(move_command.commands[1], MoveItemsCommand)
        tool._cancel_selection_drag()

        handle = _FakeItem("handle")
        target = _FakeItem("curved_single")
        before_state = {"x": 1}
        after_state = {"x": 2}
        tool._begin_drag_transaction()
        tool._active_handle = handle
        tool._handle_target = target
        tool._handle_before_state = before_state
        target.setData(9, after_state)
        self.assertTrue(tool.on_mouse_release(_FakeEvent(QPointF(0.0, 0.0))))
        self.assertIsInstance(canvas.pushed_commands[-1], UpdateSceneItemCommand)

        self.assertTrue(
            tool._begin_selection_drag(
                {1},
                [],
                QPointF(1.0, 1.0),
            )
        )
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
        tool = SelectTool(canvas, context=_tool_context_for(canvas))
        handle = _FakeItem("handle")
        tool._begin_drag_transaction()
        tool._active_handle = handle
        event = _FakeEvent(QPointF(5.0, 6.0))
        self.assertTrue(tool.on_mouse_move(event))
        self.assertEqual(canvas.handle_drags[0][0], handle)

        tool._cancel_handle_drag()
        self.assertTrue(
            tool._begin_selection_drag(
                set(),
                [_FakeItem("note")],
                QPointF(1.0, 1.0),
            )
        )
        tool._last_drag_time = 100.0
        tool._pending_curved_handle_item = object()
        tool._pending_curved_handle_action = "show"
        with mock.patch.object(select_tool_module.time, "monotonic", return_value=100.0 + tool._drag_interval / 2.0):
            self.assertTrue(tool.on_mouse_move(_FakeEvent(QPointF(3.0, 4.0))))
        self.assertEqual(canvas.shift_calls, [])
        self.assertIsNotNone(tool._pending_curved_handle_item)

        with mock.patch.object(select_tool_module.time, "monotonic", return_value=100.0 + tool._drag_interval * 2.0):
            self.assertTrue(tool.on_mouse_move(_FakeEvent(QPointF(4.0, 5.0))))
        self.assertTrue(canvas.shift_calls)
        self.assertIsNone(tool._pending_curved_handle_item)

    def test_rotate_tool_activate_press_move_and_release(self) -> None:
        canvas = SimpleNamespace(
            DragMode=SimpleNamespace(NoDrag="none"),
            drag_mode=None,
            rotations=[],
            setDragMode=lambda mode: setattr(canvas, "drag_mode", mode),
        )
        tool = RotateTool(canvas, context=_tool_context_for(canvas))
        tool.activate()

        self.assertEqual(canvas.drag_mode, canvas.DragMode.NoDrag)
        self.assertFalse(tool.on_mouse_press(_FakeEvent(button=Qt.MouseButton.RightButton)))
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        with mock.patch.object(
            rotate_tool_module,
            "rotate_view_for",
            side_effect=lambda _canvas, amount: canvas.rotations.append(amount),
        ):
            self.assertTrue(tool.on_mouse_move(_FakeEvent(QPointF(6.0, 1.0))))
        self.assertEqual(canvas.rotations, [1.5])
        self.assertFalse(tool.on_mouse_release(_FakeEvent()))
        self.assertFalse(tool.on_mouse_move(_FakeEvent(QPointF(8.0, 1.0))))

    def test_move_tool_selection_drag_builds_composite_move_command(self) -> None:
        canvas = _FakeMoveCanvas()
        tool = MoveTool(canvas, context=_tool_context_for(canvas))
        tool.activate()

        selected_note = _FakeItem("note")
        canvas.selected_items_for_transform = [selected_note]
        canvas.scene_obj.selected_items = [selected_note, _FakeItem("atom", 1), _FakeItem("bond", 1)]
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
        tool = MoveTool(canvas, context=_tool_context_for(canvas))
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
        tool = MoveTool(canvas, context=_tool_context_for(canvas))

        self.assertFalse(tool.on_mouse_press(_FakeEvent(button=Qt.MouseButton.RightButton)))
        self.assertFalse(tool.on_mouse_move(_FakeEvent(QPointF(1.0, 1.0))))
        tool._apply_drag_delta(QPointF(2.0, 3.0))
        self.assertEqual(canvas.moved_items, [])

        selected_note = _FakeItem("note")
        canvas.selected_items_for_transform = [selected_note]
        canvas.scene_obj.selected_items = [selected_note, _FakeItem("bond", 1), _FakeItem("bond", 99)]
        canvas.selected_atom_ids = set()
        canvas.selected_bond_ids = {1, 99}
        canvas.model.bonds[1] = None
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(2.0, 2.0))))
        self.assertTrue(tool._drag_selection)
        self.assertEqual(tool._selection_atom_ids, set())

        standalone_canvas = _FakeMoveCanvas()
        tool = MoveTool(standalone_canvas, context=_tool_context_for(standalone_canvas))
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        self.assertIsNone(tool._drag_item)

        canvas = _FakeMoveCanvas()
        tool = MoveTool(canvas, context=_tool_context_for(canvas))
        canvas.item = _FakeItem("note")
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        self.assertIsNone(tool._drag_item)

        moved_item = _FakeItem("arrow")
        canvas.item = moved_item
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        tool._last_drag_time = 100.0
        with mock.patch.object(move_tool_module.time, "monotonic", return_value=100.0 + tool._drag_interval / 2.0):
            self.assertTrue(tool.on_mouse_move(_FakeEvent(QPointF(4.0, 5.0))))
        self.assertEqual(canvas.moved_items, [])

        with mock.patch.object(move_tool_module.time, "monotonic", return_value=100.0 + tool._drag_interval * 2.0):
            self.assertTrue(tool.on_mouse_move(_FakeEvent(QPointF(4.0, 5.0))))
        self.assertEqual(canvas.moved_items[-1][1:3], (3.0, 4.0))

        tool._start_pos = QPointF(4.0, 5.0)
        tool._moved = False
        self.assertTrue(tool.on_mouse_release(_FakeEvent(QPointF(4.0, 5.0))))
        self.assertEqual(len(canvas.pushed_commands), 0)

    def _canvas_with_shapes(self, count: int = 2):
        canvas = CanvasView()
        shapes = [
            canvas.services.scene_decoration_service.add_shape(
                QRectF(float(index * 30), 0.0, 20.0, 16.0),
                shape_kind="rectangle",
                stroke_style="solid",
            )
            for index in range(count)
        ]
        self.assertTrue(all(shape is not None for shape in shapes))
        canvas.services.history_service.clear()
        return canvas, shapes

    def _dispose_canvas(self, canvas) -> None:
        canvas.close()
        canvas.deleteLater()
        self.app.processEvents()

    def test_trusted_drag_begin_is_selection_sized_for_large_actual_scenes(self) -> None:
        affected_counts: list[int] = []
        for unrelated_count in (100, 1000, 5000):
            with self.subTest(unrelated_count=unrelated_count):
                canvas, shapes = self._canvas_with_shapes(count=1)
                shape = shapes[0]
                shape.setSelected(True)
                scene = canvas.scene()
                for index in range(unrelated_count):
                    scene.addRect(
                        QRectF(
                            float(index % 100),
                            float(index // 100),
                            1.0,
                            1.0,
                        )
                    )
                tool = MoveTool(canvas, context=canvas.services.tools.context)
                try:
                    with (
                        mock.patch.object(
                            selection_drag_tool_module,
                            "capture_history_transaction_for_history",
                            side_effect=AssertionError(
                                "trusted begin captured the full canvas"
                            ),
                        ) as full_capture,
                        mock.patch.object(
                            QGraphicsScene,
                            "items",
                            side_effect=AssertionError(
                                "trusted begin enumerated the full scene"
                            ),
                        ) as scene_items_port,
                    ):
                        self.assertTrue(
                            tool._begin_selection_drag(
                                set(),
                                [shape],
                                QPointF(),
                            )
                        )
                        snapshot = tool._require_drag_token().canvas_snapshot
                        self.assertIsInstance(
                            snapshot,
                            selection_drag_tool_module._TrustedSelectionDragSnapshot,
                        )
                        affected_counts.append(len(snapshot.affected_items))
                        self.assertIn(shape, snapshot.affected_items)
                        self.assertEqual(snapshot.affected_ring_items, ())
                        self.assertIsNone(snapshot.fallback_snapshot)
                        tool.deactivate()

                    full_capture.assert_not_called()
                    scene_items_port.assert_not_called()
                finally:
                    self._dispose_canvas(canvas)
        self.assertEqual(len(set(affected_counts)), 1)

    def test_actual_true_zero_click_releases_cow_without_full_capture(self) -> None:
        canvas, shapes = self._canvas_with_shapes(count=200)
        shape = shapes[0]
        shape.setSelected(True)
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        history = canvas.services.history_service
        before_state = scene_item_state_for(canvas, shape)
        original_capture = (
            selection_drag_tool_module.capture_history_transaction_for_history
        )
        try:
            with mock.patch.object(
                selection_drag_tool_module,
                "capture_history_transaction_for_history",
                wraps=original_capture,
            ) as full_capture:
                self.assertTrue(
                    tool._begin_selection_drag(set(), [shape], QPointF())
                )
                snapshot = tool._drag_transaction_authority.canvas_snapshot
                self.assertIsInstance(
                    snapshot,
                    selection_drag_tool_module._TrustedSelectionDragSnapshot,
                )
                self.assertIsNone(snapshot.fallback_snapshot)
                tool._commit_selection_drag()

                full_capture.assert_not_called()
                self.assertIsNone(snapshot.fallback_snapshot)

            self.assertEqual(scene_item_state_for(canvas, shape), before_state)
            self.assertEqual(history.state.history, [])
            self.assertEqual(history.state.redo_stack, [])
            self.assertIsNone(tool._drag_transaction)
            self.assertIsNone(tool._drag_transaction_authority)

            with mock.patch.object(
                selection_drag_tool_module,
                "capture_history_transaction_for_history",
                wraps=original_capture,
            ) as full_capture:
                self.assertTrue(
                    tool._begin_selection_drag(set(), [shape], QPointF())
                )
                tool._apply_drag_delta(QPointF(6.0, 2.0))
                tool._apply_drag_delta(QPointF(-6.0, -2.0))
                tool._commit_selection_drag()

                full_capture.assert_called_once()

            self.assertEqual(scene_item_state_for(canvas, shape), before_state)
            self.assertEqual(history.state.history, [])
            self.assertEqual(history.state.redo_stack, [])
            self.assertIsNone(tool._drag_transaction)
        finally:
            self._dispose_canvas(canvas)

    def test_actual_drag_rejects_mutating_custom_history_policy_before_getter(
        self,
    ) -> None:
        for drag_kind in ("true_zero", "moved"):
            with self.subTest(drag_kind=drag_kind):
                canvas, shapes = self._canvas_with_shapes(count=2)
                shape, unrelated_shape = shapes
                shape.setSelected(True)
                tool = MoveTool(canvas, context=canvas.services.tools.context)
                history = canvas.services.history_service
                original_state = history.state
                baseline = MoveItemsCommand(items=[], dx=0.0, dy=0.0)
                redo_entry = MoveItemsCommand(items=[], dx=1.0, dy=1.0)
                getter_calls: list[str] = []
                unrelated_z = unrelated_shape.zValue()

                class MutatingPolicyState:
                    def __init__(
                        self,
                        history_entry,
                        redo_stack_entry,
                        calls,
                        mutation_target,
                    ) -> None:
                        self.history = [history_entry]
                        self.redo_stack = [redo_stack_entry]
                        self._enabled = True
                        self._limit = 100
                        self.change_callback = None
                        self._getter_calls = calls
                        self._mutation_target = mutation_target

                    @property
                    def enabled(self) -> bool:
                        self._getter_calls.append("enabled")
                        self._mutation_target.setZValue(
                            self._mutation_target.zValue() + 10.0
                        )
                        return self._enabled

                    @enabled.setter
                    def enabled(self, value: bool) -> None:
                        self._enabled = value

                    @property
                    def limit(self) -> int:
                        self._getter_calls.append("limit")
                        self._mutation_target.setZValue(
                            self._mutation_target.zValue() + 10.0
                        )
                        return self._limit

                    @limit.setter
                    def limit(self, value: int) -> None:
                        self._limit = value

                custom_state = MutatingPolicyState(
                    baseline,
                    redo_entry,
                    getter_calls,
                    unrelated_shape,
                )
                history_list = custom_state.history
                redo_list = custom_state.redo_stack
                history.state = custom_state
                try:
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "exact callback-free production history state",
                    ):
                        started = tool._begin_selection_drag(
                            set(),
                            [shape],
                            QPointF(),
                        )
                        if drag_kind == "moved" and started:
                            tool._apply_drag_delta(QPointF(5.0, -2.0))
                        tool._commit_selection_drag()

                    self.assertEqual(getter_calls, [])
                    self.assertEqual(unrelated_shape.zValue(), unrelated_z)
                    self.assertIs(tool.context.history_service, history)
                    self.assertIs(canvas.services.history_service, history)
                    self.assertIs(history.state, custom_state)
                    self.assertIs(custom_state.history, history_list)
                    self.assertIs(custom_state.redo_stack, redo_list)
                    self.assertEqual(len(history_list), 1)
                    self.assertEqual(len(redo_list), 1)
                    self.assertIs(history_list[0], baseline)
                    self.assertIs(redo_list[0], redo_entry)
                    self.assertTrue(custom_state._enabled)
                    self.assertEqual(custom_state._limit, 100)
                    self.assertIsNone(tool._drag_transaction)
                    self.assertIsNone(tool._drag_history_authority)
                    self.assertIsNone(tool._drag_transaction_authority)
                finally:
                    history.state = original_state
                    self._dispose_canvas(canvas)

    def test_actual_drag_preflights_runtime_roots_before_nested_getters(self) -> None:
        canvas, shapes = self._canvas_with_shapes(count=1)
        shape = shapes[0]
        unrelated = canvas.scene().addRect(QRectF(40.0, 20.0, 5.0, 7.0))
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        original_services = canvas.services
        before_unrelated_pos = QPointF(unrelated.pos())
        getter_calls: list[str] = []

        class PoisonServices:
            def __getattribute__(self, name: str):
                if name == "move_controller":
                    getter_calls.append(name)
                    unrelated.moveBy(17.0, -9.0)
                    raise RuntimeError("nested services getter was invoked")
                return object.__getattribute__(self, name)

        canvas.services = PoisonServices()
        try:
            self.assertTrue(
                tool._begin_selection_drag(set(), [shape], QPointF())
            )
            snapshot = tool._require_drag_token().canvas_snapshot
            self.assertNotIsInstance(
                snapshot,
                selection_drag_tool_module._TrustedSelectionDragSnapshot,
            )
            self.assertEqual(getter_calls, [])
            self.assertEqual(unrelated.pos(), before_unrelated_pos)
        finally:
            canvas.services = original_services
            if tool._drag_transaction is not None:
                tool.deactivate()
            self._dispose_canvas(canvas)

    def test_actual_drag_rejects_custom_primitive_getter_before_invocation(
        self,
    ) -> None:
        canvas = CanvasView()
        unrelated = canvas.scene().addRect(QRectF(40.0, 20.0, 5.0, 7.0))
        before_unrelated_pos = QPointF(unrelated.pos())
        getter_calls: list[str] = []

        class PoisonPrimitiveItem(QGraphicsEllipseItem):
            def transform(self):
                getter_calls.append("transform")
                unrelated.moveBy(13.0, -7.0)
                raise RuntimeError("custom primitive getter was invoked")

        item = PoisonPrimitiveItem(QRectF(0.0, 0.0, 10.0, 10.0))
        item.setData(0, "note")
        item.setData(2, {})
        canvas.scene().addItem(item)
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        try:
            with self.assertRaisesRegex(
                RuntimeError,
                "callback-free Qt snapshot ports",
            ):
                tool._begin_selection_drag(set(), [item], QPointF())

            self.assertEqual(getter_calls, [])
            self.assertEqual(unrelated.pos(), before_unrelated_pos)
            self.assertIsNone(tool._drag_transaction)
            self.assertIsNone(tool._drag_transaction_authority)
        finally:
            self._dispose_canvas(canvas)

    def test_actual_drag_rejects_dynamic_qt_attribute_hooks_before_invocation(
        self,
    ) -> None:
        for hook_kind in ("getattribute", "getattr", "setattr"):
            with self.subTest(hook_kind=hook_kind):
                canvas = CanvasView()
                unrelated = canvas.scene().addRect(
                    QRectF(40.0, 20.0, 5.0, 7.0)
                )
                before_unrelated_pos = QPointF(unrelated.pos())
                hook_calls: list[str] = []
                setter_state = {"armed": False}

                class PoisonGetattributeItem(QGraphicsEllipseItem):
                    def __getattribute__(
                        self,
                        name: str,
                        _calls=hook_calls,
                        _unrelated=unrelated,
                    ):
                        if name == "transform":
                            _calls.append(name)
                            _unrelated.moveBy(13.0, -7.0)
                            raise RuntimeError("custom __getattribute__ was invoked")
                        return super().__getattribute__(name)

                class PoisonGetattrItem(QGraphicsEllipseItem):
                    def __getattr__(
                        self,
                        name: str,
                        _calls=hook_calls,
                        _unrelated=unrelated,
                    ):
                        if name == "line":
                            _calls.append(name)
                            _unrelated.moveBy(13.0, -7.0)
                            raise RuntimeError("custom __getattr__ was invoked")
                        raise AttributeError(name)

                class PoisonSetattrItem(QGraphicsEllipseItem):
                    def __setattr__(
                        self,
                        name: str,
                        value,
                        _state=setter_state,
                        _calls=hook_calls,
                        _unrelated=unrelated,
                    ) -> None:
                        if _state["armed"] and name == "_hit_padding":
                            _calls.append(name)
                            _unrelated.moveBy(13.0, -7.0)
                            raise RuntimeError("custom __setattr__ was invoked")
                        super().__setattr__(name, value)

                item_type = {
                    "getattribute": PoisonGetattributeItem,
                    "getattr": PoisonGetattrItem,
                    "setattr": PoisonSetattrItem,
                }[hook_kind]
                item = item_type(QRectF(0.0, 0.0, 10.0, 10.0))
                if hook_kind == "setattr":
                    item._hit_padding = 2.0
                    setter_state["armed"] = True
                item.setData(0, "note")
                item.setData(2, {})
                canvas.scene().addItem(item)
                tool = MoveTool(canvas, context=canvas.services.tools.context)
                try:
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "callback-free Qt snapshot ports",
                    ):
                        tool._begin_selection_drag(set(), [item], QPointF())

                    self.assertEqual(hook_calls, [])
                    self.assertEqual(unrelated.pos(), before_unrelated_pos)
                    self.assertIsNone(tool._drag_transaction)
                    self.assertIsNone(tool._drag_transaction_authority)
                finally:
                    self._dispose_canvas(canvas)

    def test_actual_drag_allows_trusted_atom_label_font_override(self) -> None:
        canvas = CanvasView()
        label = AtomLabelItem()
        label.setData(0, "note")
        label.setData(2, {})
        label.setPlainText("CH3")
        canvas.scene().addItem(label)
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        try:
            self.assertTrue(
                tool._begin_selection_drag(set(), [label], QPointF())
            )
            snapshot = tool._require_drag_token().canvas_snapshot
            self.assertIsInstance(
                snapshot,
                selection_drag_tool_module._TrustedSelectionDragSnapshot,
            )
            self.assertIsNone(snapshot.fallback_snapshot)

            tool._commit_selection_drag()

            self.assertIsNone(tool._drag_transaction)
        finally:
            self._dispose_canvas(canvas)

    def test_actual_drag_rejects_canvas_poison_after_successful_history_push(
        self,
    ) -> None:
        canvas, shapes = self._canvas_with_shapes(count=1)
        shape = shapes[0]
        shape.setSelected(True)
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        history = canvas.services.history_service
        redo_entry = MoveItemsCommand(items=[], dx=1.0, dy=1.0)
        history.state.redo_stack[:] = [redo_entry]
        history_list = history.state.history
        redo_list = history.state.redo_stack
        before_rect = QRectF(shape.sceneBoundingRect())
        before_pos = QPointF(shape.pos())
        callback_calls = 0

        def poison_canvas() -> None:
            nonlocal callback_calls
            callback_calls += 1
            shape.moveBy(100.0, 0.0)

        try:
            self.assertTrue(
                tool._begin_selection_drag(set(), [shape], QPointF())
            )
            tool._apply_drag_delta(QPointF(5.0, 0.0))
            history.state.change_callback = poison_canvas

            with self.assertRaisesRegex(
                BaseExceptionGroup,
                "canvas authority changed during history publication",
            ):
                tool._commit_selection_drag()

            self.assertGreaterEqual(callback_calls, 1)
            self.assertEqual(shape.sceneBoundingRect(), before_rect)
            self.assertEqual(shape.pos(), before_pos)
            self.assertIs(history.state.history, history_list)
            self.assertIs(history.state.redo_stack, redo_list)
            self.assertEqual(history_list, [])
            self.assertEqual(redo_list, [redo_entry])
            self.assertIsNone(tool._drag_transaction)
            self.assertFalse(tool._drag_selection)
        finally:
            history.state.change_callback = None
            self._dispose_canvas(canvas)

    def test_actual_drag_rejects_successful_push_command_payload_mutation(
        self,
    ) -> None:
        canvas, shapes = self._canvas_with_shapes(count=1)
        shape = shapes[0]
        shape.setSelected(True)
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        history = canvas.services.history_service
        redo_entry = MoveItemsCommand(items=[], dx=1.0, dy=1.0)
        history.state.redo_stack[:] = [redo_entry]
        before_state = scene_item_state_for(canvas, shape)
        published: list[MoveItemsCommand] = []

        def poison_command() -> None:
            command = history.state.history[-1]
            assert isinstance(command, MoveItemsCommand)
            published.append(command)
            command.dx = 999.0

        try:
            self.assertTrue(tool._begin_selection_drag(set(), [shape], QPointF()))
            tool._apply_drag_delta(QPointF(5.0, 0.0))
            history.state.change_callback = poison_command

            with self.assertRaisesRegex(RuntimeError, "history command field"):
                tool._commit_selection_drag()

            self.assertEqual(scene_item_state_for(canvas, shape), before_state)
            self.assertEqual(published[0].dx, 5.0)
            self.assertEqual(history.state.history, [])
            self.assertEqual(history.state.redo_stack, [redo_entry])
            self.assertIsNone(tool._drag_transaction)
        finally:
            history.state.change_callback = None
            self._dispose_canvas(canvas)

    def test_actual_sub_epsilon_net_drag_publishes_exact_history(self) -> None:
        canvas, shapes = self._canvas_with_shapes(count=1)
        shape = shapes[0]
        shape.setSelected(True)
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        history = canvas.services.history_service
        redo_entry = MoveItemsCommand(items=[], dx=3.0, dy=-2.0)
        history.state.redo_stack[:] = [redo_entry]
        before_state = scene_item_state_for(canvas, shape)
        expected_dx = 1.0 - 0.9999995
        try:
            self.assertTrue(
                tool._begin_selection_drag(set(), [shape], QPointF())
            )
            tool._apply_drag_delta(QPointF(1.0, 0.0))
            tool._apply_drag_delta(QPointF(-0.9999995, 0.0))

            self.assertEqual(tool._total_delta, QPointF(expected_dx, 0.0))
            moved_state = scene_item_state_for(canvas, shape)
            self.assertNotEqual(moved_state, before_state)

            tool._commit_selection_drag()

            self.assertEqual(scene_item_state_for(canvas, shape), moved_state)
            self.assertEqual(len(history.state.history), 1)
            command = history.state.history[0]
            self.assertIsInstance(command, MoveItemsCommand)
            self.assertEqual(command.dx, expected_dx)
            self.assertEqual(command.dy, 0.0)
            self.assertEqual(history.state.redo_stack, [])
            self.assertIsNone(tool._drag_transaction)

            history.undo()
            self.assertEqual(scene_item_state_for(canvas, shape), before_state)
            history.redo()
            self.assertEqual(scene_item_state_for(canvas, shape), moved_state)
        finally:
            self._dispose_canvas(canvas)

    def test_custom_qt_item_uses_full_drag_snapshot_at_begin(self) -> None:
        class _CustomItem(QGraphicsEllipseItem):
            def itemChange(self, change, value):
                return super().itemChange(change, value)

        canvas = CanvasView()
        item = _CustomItem(-2.0, -2.0, 4.0, 4.0)
        item.setData(0, "note")
        canvas.scene().addItem(item)
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        original_capture = (
            selection_drag_tool_module.capture_history_transaction_for_history
        )
        try:
            with mock.patch.object(
                selection_drag_tool_module,
                "capture_history_transaction_for_history",
                wraps=original_capture,
            ) as full_capture:
                self.assertTrue(
                    tool._begin_selection_drag(
                        set(),
                        [item],
                        QPointF(),
                    )
                )
                snapshot = tool._require_drag_token().canvas_snapshot
                self.assertNotIsInstance(
                    snapshot,
                    selection_drag_tool_module._TrustedSelectionDragSnapshot,
                )
                full_capture.assert_called_once()
                tool.deactivate()
        finally:
            self._dispose_canvas(canvas)

    def test_apply_failure_uses_frozen_authority_after_field_corruption(
        self,
    ) -> None:
        for corruption in ("delete", "replace"):
            with self.subTest(corruption=corruption):
                canvas, shapes = self._canvas_with_shapes(count=1)
                shape = shapes[0]
                shape.setSelected(True)
                tool = MoveTool(
                    canvas,
                    context=canvas.services.tools.context,
                )
                history = canvas.services.history_service
                baseline = MoveItemsCommand(items=[], dx=0.0, dy=0.0)
                redo_entry = MoveItemsCommand(items=[], dx=2.0, dy=1.0)
                history.state.history[:] = [baseline]
                history.state.redo_stack[:] = [redo_entry]
                history_list = history.state.history
                redo_list = history.state.redo_stack
                before_state = scene_item_state_for(canvas, shape)
                original_move = selection_drag_tool_module.move_item_for
                primary = KeyboardInterrupt(
                    f"move failed after authority field {corruption}"
                )

                def move_then_corrupt(
                    *args,
                    mode=corruption,
                    active_tool=tool,
                    move_port=original_move,
                    failure=primary,
                    **kwargs,
                ) -> None:
                    move_port(*args, **kwargs)
                    if mode == "delete":
                        delattr(active_tool, "_drag_transaction_authority")
                        delattr(active_tool, "_drag_history_authority")
                    else:
                        active_tool._drag_transaction_authority = object()
                        active_tool._drag_history_authority = object()
                    raise failure

                try:
                    self.assertTrue(
                        tool._begin_selection_drag(
                            set(),
                            [shape],
                            QPointF(),
                        )
                    )
                    token = tool._require_drag_token()
                    frozen_authority = tool._drag_transaction_authority

                    with mock.patch.object(
                        selection_drag_tool_module,
                        "move_item_for",
                        side_effect=move_then_corrupt,
                    ):
                        try:
                            tool._apply_drag_delta(QPointF(9.0, -4.0))
                        except KeyboardInterrupt as error:
                            self.assertIs(error, primary)
                        else:
                            self.fail("move callback failure was not propagated")

                    self.assertIs(frozen_authority.token, token)
                    self.assertEqual(
                        scene_item_state_for(canvas, shape),
                        before_state,
                    )
                    self.assertIs(history.state.history, history_list)
                    self.assertIs(history.state.redo_stack, redo_list)
                    self.assertEqual(history_list, [baseline])
                    self.assertEqual(redo_list, [redo_entry])
                    self.assertIsNone(tool._drag_transaction)
                    self.assertIsNone(tool._drag_transaction_authority)
                    self.assertIsNone(tool._drag_history_authority)
                    self.assertFalse(tool._drag_selection)
                finally:
                    self._dispose_canvas(canvas)

    def test_untrusted_move_port_promotes_before_unrelated_poison(self) -> None:
        canvas, shapes = self._canvas_with_shapes(count=1)
        shape = shapes[0]
        shape.setSelected(True)
        scene = canvas.scene()
        unrelated = scene.addRect(QRectF(80.0, 40.0, 8.0, 6.0))
        unrelated.setPos(QPointF(3.0, -2.0))
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        before_shape = scene_item_state_for(canvas, shape)
        before_unrelated_pos = QPointF(unrelated.pos())
        before_scene_items = list(scene.items())
        primary = RuntimeError("custom move poisoned an unrelated item")
        order: list[str] = []
        original_capture = (
            selection_drag_tool_module.capture_history_transaction_for_history
        )

        def capture_full(*args, **kwargs):
            order.append("capture")
            return original_capture(*args, **kwargs)

        def poison_then_raise(*_args, **_kwargs) -> None:
            order.append("move")
            shape.moveBy(13.0, -7.0)
            unrelated.moveBy(-9.0, 11.0)
            scene.removeItem(unrelated)
            raise primary

        try:
            with mock.patch.object(
                selection_drag_tool_module,
                "capture_history_transaction_for_history",
                side_effect=capture_full,
            ) as full_capture:
                self.assertTrue(
                    tool._begin_selection_drag(
                        set(),
                        [shape],
                        QPointF(),
                    )
                )
                snapshot = tool._require_drag_token().canvas_snapshot
                self.assertIsInstance(
                    snapshot,
                    selection_drag_tool_module._TrustedSelectionDragSnapshot,
                )

                with mock.patch.object(
                    selection_drag_tool_module,
                    "move_item_for",
                    side_effect=poison_then_raise,
                ):
                    try:
                        tool._apply_drag_delta(QPointF(4.0, 5.0))
                    except RuntimeError as error:
                        self.assertIs(error, primary)
                    else:
                        self.fail("custom move failure was not propagated")

                full_capture.assert_called_once()

            self.assertEqual(order, ["capture", "move"])
            self.assertIsNotNone(snapshot.fallback_snapshot)
            self.assertEqual(scene_item_state_for(canvas, shape), before_shape)
            self.assertIs(unrelated.scene(), scene)
            self.assertEqual(unrelated.pos(), before_unrelated_pos)
            self.assertEqual(list(scene.items()), before_scene_items)
            self.assertIsNone(tool._drag_transaction)
            self.assertFalse(tool._drag_selection)
        finally:
            self._dispose_canvas(canvas)

    def test_nested_shape_port_promotes_before_unrelated_poison(self) -> None:
        canvas, shapes = self._canvas_with_shapes(count=1)
        shape = shapes[0]
        shape.setSelected(True)
        unrelated = canvas.scene().addRect(
            QRectF(90.0, 45.0, 7.0, 5.0)
        )
        unrelated.setPos(QPointF(-4.0, 6.0))
        before_shape = scene_item_state_for(canvas, shape)
        before_unrelated_pos = QPointF(unrelated.pos())
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        primary = KeyboardInterrupt("nested shape port poisoned unrelated state")
        order: list[str] = []
        original_capture = (
            selection_drag_tool_module.capture_history_transaction_for_history
        )

        def capture_full(*args, **kwargs):
            order.append("capture")
            return original_capture(*args, **kwargs)

        def poison_shape_path(*_args, **_kwargs):
            order.append("shape_path")
            unrelated.moveBy(17.0, -12.0)
            raise primary

        try:
            with mock.patch.object(
                selection_drag_tool_module,
                "capture_history_transaction_for_history",
                side_effect=capture_full,
            ) as full_capture:
                self.assertTrue(
                    tool._begin_selection_drag(
                        set(),
                        [shape],
                        QPointF(),
                    )
                )
                with mock.patch.object(
                    canvas_move_controller_module,
                    "shape_path",
                    side_effect=poison_shape_path,
                ):
                    try:
                        tool._apply_drag_delta(QPointF(3.0, 2.0))
                    except KeyboardInterrupt as error:
                        self.assertIs(error, primary)
                    else:
                        self.fail("nested shape-port failure was not propagated")

                full_capture.assert_called_once()

            self.assertEqual(order, ["capture", "shape_path"])
            self.assertEqual(scene_item_state_for(canvas, shape), before_shape)
            self.assertEqual(unrelated.pos(), before_unrelated_pos)
            self.assertIsNone(tool._drag_transaction)
        finally:
            self._dispose_canvas(canvas)

    def test_trusted_drag_rejects_target_swap_before_first_mutation(self) -> None:
        canvas, shapes = self._canvas_with_shapes(count=2)
        selected, replacement = shapes
        selected.setSelected(True)
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        selected_before = scene_item_state_for(canvas, selected)
        replacement_before = scene_item_state_for(canvas, replacement)
        try:
            self.assertTrue(
                tool._begin_selection_drag(
                    set(),
                    [selected],
                    QPointF(),
                )
            )
            tool._selection_items[:] = [replacement]

            with self.assertRaisesRegex(
                RuntimeError,
                "targets changed after capture",
            ):
                tool._apply_drag_delta(QPointF(5.0, 3.0))

            self.assertEqual(
                scene_item_state_for(canvas, selected),
                selected_before,
            )
            self.assertEqual(
                scene_item_state_for(canvas, replacement),
                replacement_before,
            )
            self.assertIsNone(tool._drag_transaction)
            self.assertFalse(tool._drag_selection)
        finally:
            self._dispose_canvas(canvas)

    def test_atom_drag_reuses_capture_bound_rings_across_actual_frames(self) -> None:
        canvas = CanvasView()
        atom_ids = [
            canvas.model.add_atom("C", 0.0, 0.0),
            canvas.model.add_atom("C", 2.0, 0.0),
            canvas.model.add_atom("C", 1.0, 2.0),
        ]
        scene = canvas.scene()
        polygon = QPolygonF(
            [QPointF(0.0, 0.0), QPointF(2.0, 0.0), QPointF(1.0, 2.0)]
        )
        matching_ring = QGraphicsPolygonItem(polygon)
        matching_ring.setData(0, "ring")
        matching_ring.setData(2, list(atom_ids))
        scene.addItem(matching_ring)
        unrelated_rings = []
        for index in range(256):
            ring = QGraphicsPolygonItem(polygon)
            ring.setData(0, "ring")
            base = 10_000 + index * 3
            ring.setData(2, [base, base + 1, base + 2])
            scene.addItem(ring)
            unrelated_rings.append(ring)
        set_scene_item_collection_for(
            canvas,
            "ring_items",
            [matching_ring, *unrelated_rings],
        )
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        selected_atom = canvas.model.atoms[atom_ids[0]]
        before_atom_pos = (selected_atom.x, selected_atom.y)
        before_polygon = QPolygonF(matching_ring.polygon())
        try:
            with mock.patch.object(
                selection_drag_tool_module,
                "capture_history_transaction_for_history",
                side_effect=AssertionError(
                    "trusted atom drag captured the full canvas"
                ),
            ) as full_capture:
                self.assertTrue(
                    tool._begin_selection_drag(
                        {atom_ids[0]},
                        [],
                        QPointF(),
                    )
                )
                snapshot = tool._require_drag_token().canvas_snapshot
                self.assertIsInstance(
                    snapshot,
                    selection_drag_tool_module._TrustedSelectionDragSnapshot,
                )
                self.assertEqual(
                    snapshot.affected_ring_items,
                    (matching_ring,),
                )

                with mock.patch.object(
                    canvas_move_controller_module,
                    "ring_items_for",
                    side_effect=AssertionError(
                        "drag frame rescanned the ring registry"
                    ),
                ) as ring_registry_port:
                    for _ in range(5):
                        tool._apply_drag_delta(QPointF(1.0, 0.5))
                    tool.deactivate()

                ring_registry_port.assert_not_called()
                full_capture.assert_not_called()

            self.assertEqual(
                (selected_atom.x, selected_atom.y),
                before_atom_pos,
            )
            self.assertEqual(matching_ring.polygon(), before_polygon)
            self.assertIsNone(tool._drag_transaction)
        finally:
            self._dispose_canvas(canvas)

    def test_selection_drag_partial_item_interrupt_restores_exact_start_state(self) -> None:
        for primary in (
            KeyboardInterrupt("selection item loop interrupted"),
            SystemExit("selection item loop terminated"),
        ):
            with self.subTest(primary=type(primary).__name__):
                canvas, shapes = self._canvas_with_shapes()
                first, second = shapes
                first.setSelected(True)
                second.setSelected(True)
                tool = MoveTool(canvas, context=canvas.services.tools.context)
                history = canvas.services.history_service
                history_list = history.state.history
                redo_list = history.state.redo_stack
                before_states = [scene_item_state_for(canvas, item) for item in shapes]
                original_move = canvas.services.move_controller.move_item

                def move_then_interrupt(
                    item,
                    dx,
                    dy,
                    *,
                    update_selection=True,
                    _original_move=original_move,
                    _second=second,
                    _primary=primary,
                ):
                    _original_move(
                        item,
                        dx,
                        dy,
                        update_selection=update_selection,
                    )
                    if item is _second:
                        raise _primary

                try:
                    self.assertTrue(
                        tool._begin_selection_drag(
                            set(),
                            shapes,
                            QPointF(0.0, 0.0),
                        )
                    )
                    with mock.patch.object(
                        canvas.services.move_controller,
                        "move_item",
                        side_effect=move_then_interrupt,
                    ):
                        try:
                            tool._apply_drag_delta(QPointF(12.0, -7.0))
                        except BaseException as error:
                            self.assertIs(error, primary)
                        else:
                            self.fail("control-flow interruption was not propagated")

                    self.assertEqual(
                        [scene_item_state_for(canvas, item) for item in shapes],
                        before_states,
                    )
                    self.assertTrue(first.isSelected())
                    self.assertTrue(second.isSelected())
                    self.assertFalse(selection_style_state_for(canvas).suspend_outline)
                    self.assertIs(history.state.history, history_list)
                    self.assertIs(history.state.redo_stack, redo_list)
                    self.assertEqual(history_list, [])
                    self.assertEqual(redo_list, [])
                    self.assertIsNone(tool._drag_transaction)
                    self.assertFalse(tool._drag_selection)
                    self.assertIsNone(tool._start_pos)
                finally:
                    self._dispose_canvas(canvas)

    def test_selection_drag_deactivate_and_new_press_cancel_to_exact_start(self) -> None:
        for cancel_mode in ("deactivate", "new_press"):
            with self.subTest(cancel_mode=cancel_mode):
                canvas, shapes = self._canvas_with_shapes(count=1)
                shape = shapes[0]
                shape.setSelected(True)
                tool = MoveTool(canvas, context=canvas.services.tools.context)
                before_state = scene_item_state_for(canvas, shape)
                try:
                    self.assertTrue(
                        tool._begin_selection_drag(
                            set(),
                            [shape],
                            QPointF(0.0, 0.0),
                        )
                    )
                    tool._apply_drag_delta(QPointF(9.0, 4.0))
                    self.assertNotEqual(scene_item_state_for(canvas, shape), before_state)
                    self.assertTrue(selection_style_state_for(canvas).suspend_outline)

                    if cancel_mode == "deactivate":
                        tool.deactivate()
                    else:
                        with (
                            mock.patch.object(
                                move_tool_module,
                                "selection_snapshot_for",
                                return_value=None,
                            ),
                            mock.patch.object(
                                tool.context,
                                "item_at_event",
                                return_value=None,
                            ),
                        ):
                            self.assertTrue(
                                tool.on_mouse_press(_FakeEvent(QPointF(3.0, 3.0)))
                            )

                    self.assertEqual(scene_item_state_for(canvas, shape), before_state)
                    self.assertTrue(shape.isSelected())
                    self.assertFalse(selection_style_state_for(canvas).suspend_outline)
                    self.assertEqual(canvas.services.history_service.state.history, [])
                    self.assertIsNone(tool._drag_transaction)
                    self.assertFalse(tool._drag_selection)
                finally:
                    self._dispose_canvas(canvas)

    def test_selection_drag_append_then_raise_restores_history_and_geometry(self) -> None:
        canvas, shapes = self._canvas_with_shapes(count=1)
        shape = shapes[0]
        shape.setSelected(True)
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        history = canvas.services.history_service
        baseline = MoveItemsCommand(items=[], dx=0.0, dy=0.0)
        redo_entry = MoveItemsCommand(items=[], dx=1.0, dy=1.0)
        history.state.history[:] = [baseline]
        history.state.redo_stack[:] = [redo_entry]
        history_list = history.state.history
        redo_list = history.state.redo_stack
        before_state = scene_item_state_for(canvas, shape)
        primary = RuntimeError("history append then raise")
        original_push = history.push

        def append_then_raise(command) -> None:
            original_push(command)
            raise primary

        history.push = append_then_raise
        try:
            self.assertTrue(
                tool._begin_selection_drag(
                    set(),
                    [shape],
                    QPointF(0.0, 0.0),
                )
            )
            tool._apply_drag_delta(QPointF(14.0, 2.0))
            try:
                tool._commit_selection_drag()
            except RuntimeError as error:
                self.assertIs(error, primary)
            else:
                self.fail("append-then-raise history failure was not propagated")

            self.assertEqual(scene_item_state_for(canvas, shape), before_state)
            self.assertTrue(shape.isSelected())
            self.assertFalse(selection_style_state_for(canvas).suspend_outline)
            self.assertIs(history.state.history, history_list)
            self.assertIs(history.state.redo_stack, redo_list)
            self.assertEqual(history_list, [baseline])
            self.assertEqual(redo_list, [redo_entry])
            self.assertIsNone(tool._drag_transaction)
            self.assertFalse(tool._drag_selection)
        finally:
            history.push = original_push
            self._dispose_canvas(canvas)

    def test_actual_drag_rejects_inexact_history_publications_and_token_tampering(
        self,
    ) -> None:
        for failure_kind in (
            "false",
            "none_noop",
            "wrong_command",
            "extra_command",
            "state_root",
            "policy",
            "token_fields",
        ):
            with self.subTest(failure_kind=failure_kind):
                canvas, shapes = self._canvas_with_shapes(count=1)
                shape = shapes[0]
                shape.setSelected(True)
                tool = MoveTool(canvas, context=canvas.services.tools.context)
                history = canvas.services.history_service
                original_push = history.push
                baseline = MoveItemsCommand(items=[], dx=0.0, dy=0.0)
                redo_entry = MoveItemsCommand(items=[], dx=1.0, dy=1.0)
                old_state = history.state
                old_state.history[:] = [baseline]
                old_state.redo_stack[:] = [redo_entry]
                history_list = old_state.history
                redo_list = old_state.redo_stack
                enabled = old_state.enabled
                limit = old_state.limit
                before_state = scene_item_state_for(canvas, shape)
                wrong_entry = object()

                def publish_inexact(
                    command,
                    *,
                    kind=failure_kind,
                    bound_history=history,
                    bound_history_list=history_list,
                    bound_redo_list=redo_list,
                    bound_old_state=old_state,
                    bound_tool=tool,
                    bound_wrong_entry=wrong_entry,
                ):
                    if kind == "false":
                        return False
                    if kind == "none_noop":
                        return None
                    if kind == "wrong_command":
                        bound_history_list.append(bound_wrong_entry)
                        bound_redo_list.clear()
                        return None
                    bound_history_list.append(command)
                    bound_redo_list.clear()
                    if kind == "extra_command":
                        bound_history_list.append(bound_wrong_entry)
                    elif kind == "state_root":
                        bound_history.state = SimpleNamespace(
                            history=[bound_wrong_entry],
                            redo_stack=[bound_wrong_entry],
                            enabled=True,
                            limit=100,
                            change_callback=None,
                        )
                    elif kind == "policy":
                        bound_old_state.enabled = False
                        bound_old_state.limit = 1
                    elif kind == "token_fields":
                        token = bound_tool._require_drag_token()
                        token.history_service = object()
                        token.history_push = lambda _command: None
                        token.history_stacks = None
                        token.begin_history_checkpoint = None
                        token.history_policy_ports = ()
                        token.history_authority = None
                    return None

                history.push = publish_inexact
                try:
                    self.assertTrue(
                        tool._begin_selection_drag(
                            set(),
                            [shape],
                            QPointF(),
                        )
                    )
                    tool._apply_drag_delta(QPointF(11.0, -4.0))
                    with self.assertRaises(RuntimeError):
                        tool._commit_selection_drag()

                    self.assertIs(history.state, old_state)
                    self.assertIs(old_state.history, history_list)
                    self.assertIs(old_state.redo_stack, redo_list)
                    self.assertEqual(history_list, [baseline])
                    self.assertEqual(redo_list, [redo_entry])
                    self.assertIs(old_state.enabled, enabled)
                    self.assertEqual(old_state.limit, limit)
                    self.assertEqual(
                        scene_item_state_for(canvas, shape),
                        before_state,
                    )
                    self.assertTrue(shape.isSelected())
                    self.assertIsNone(tool._drag_transaction)
                    self.assertIsNone(tool._drag_history_authority)
                finally:
                    history.push = original_push
                    self._dispose_canvas(canvas)

    def test_actual_drag_rollback_uses_frozen_canvas_snapshot_after_push(self) -> None:
        canvas, shapes = self._canvas_with_shapes(count=1)
        shape = shapes[0]
        shape.setSelected(True)
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        history = canvas.services.history_service
        original_push = history.push
        baseline = MoveItemsCommand(items=[], dx=0.0, dy=0.0)
        redo_entry = MoveItemsCommand(items=[], dx=1.0, dy=1.0)
        history.state.history[:] = [baseline]
        history.state.redo_stack[:] = [redo_entry]
        history_list = history.state.history
        redo_list = history.state.redo_stack
        before_state = scene_item_state_for(canvas, shape)

        def push_then_drop_token_snapshot(command):
            result = original_push(command)
            tool._require_drag_token().canvas_snapshot = None
            return result

        history.push = push_then_drop_token_snapshot
        try:
            self.assertTrue(
                tool._begin_selection_drag(set(), [shape], QPointF())
            )
            token = tool._require_drag_token()
            transaction_authority = tool._drag_transaction_authority
            self.assertIsNotNone(transaction_authority)
            frozen_snapshot = transaction_authority.canvas_snapshot
            tool._apply_drag_delta(QPointF(9.0, -3.0))

            with self.assertRaisesRegex(RuntimeError, "canvas authority changed"):
                tool._commit_selection_drag()

            self.assertIsNotNone(frozen_snapshot)
            self.assertEqual(scene_item_state_for(canvas, shape), before_state)
            self.assertIs(history.state.history, history_list)
            self.assertIs(history.state.redo_stack, redo_list)
            self.assertEqual(history_list, [baseline])
            self.assertEqual(redo_list, [redo_entry])
            self.assertIsNone(token.canvas_snapshot)
            self.assertIsNone(tool._drag_transaction)
            self.assertIsNone(tool._drag_transaction_authority)
            self.assertIsNone(tool._drag_history_authority)
        finally:
            history.push = original_push
            self._dispose_canvas(canvas)

    def test_actual_drag_rejects_false_push_while_history_is_disabled(self) -> None:
        canvas, shapes = self._canvas_with_shapes(count=1)
        shape = shapes[0]
        shape.setSelected(True)
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        history = canvas.services.history_service
        baseline = MoveItemsCommand(items=[], dx=0.0, dy=0.0)
        redo_entry = MoveItemsCommand(items=[], dx=1.0, dy=1.0)
        history.state.history[:] = [baseline]
        history.state.redo_stack[:] = [redo_entry]
        history.state.enabled = False
        history_list = history.state.history
        redo_list = history.state.redo_stack
        before_state = scene_item_state_for(canvas, shape)
        try:
            self.assertTrue(
                tool._begin_selection_drag(set(), [shape], QPointF())
            )
            tool._apply_drag_delta(QPointF(7.0, 3.0))
            with self.assertRaisesRegex(RuntimeError, "did not commit"):
                tool._commit_selection_drag()

            self.assertEqual(scene_item_state_for(canvas, shape), before_state)
            self.assertIs(history.state.history, history_list)
            self.assertIs(history.state.redo_stack, redo_list)
            self.assertEqual(history_list, [baseline])
            self.assertEqual(redo_list, [redo_entry])
            self.assertFalse(history.state.enabled)
            self.assertIsNone(tool._drag_transaction)
        finally:
            self._dispose_canvas(canvas)

    def test_none_returning_history_push_commits_exact_limit_eviction(self) -> None:
        baseline = object()
        redo_entry = object()
        history = _FakeHistoryService(
            history=[baseline],
            redo_stack=[redo_entry],
        )
        history.state.limit = 1
        history_list = history.state.history
        redo_list = history.state.redo_stack
        canvas = _FakeMoveCanvas()
        canvas.services.history_service = history
        tool = MoveTool(canvas, context=_tool_context_for(canvas))
        item = _FakeItem("note")

        self.assertTrue(
            tool._begin_selection_drag(set(), [item], QPointF())
        )
        tool._apply_drag_delta(QPointF(4.0, -2.0))
        tool._commit_selection_drag()

        self.assertIs(history.state.history, history_list)
        self.assertIs(history.state.redo_stack, redo_list)
        self.assertEqual(len(history_list), 1)
        self.assertIsInstance(history_list[0], MoveItemsCommand)
        self.assertEqual(history_list[0].dx, 4.0)
        self.assertEqual(history_list[0].dy, -2.0)
        self.assertEqual(redo_list, [])
        self.assertEqual(history.push_calls, history_list)
        self.assertIsNone(tool._drag_transaction)

    def test_actual_drag_failure_restores_parent_topology_and_z_value(self) -> None:
        canvas, shapes = self._canvas_with_shapes(count=3)
        parent, child, peer = shapes
        child.setParentItem(parent)
        parent.setZValue(2.0)
        child.setZValue(3.0)
        peer.setZValue(2.0)
        expected_order = list(canvas.scene().items())
        tool = MoveTool(canvas, context=canvas.services.tools.context)

        def corrupt_topology_then_fail(*_args, **_kwargs) -> None:
            child.setParentItem(peer)
            parent.setZValue(9.0)
            child.setZValue(-4.0)
            peer.setZValue(-2.0)
            raise RuntimeError("drag damaged scene topology")

        try:
            self.assertTrue(
                tool._begin_selection_drag(
                    set(),
                    [child],
                    QPointF(),
                )
            )
            with (
                mock.patch.object(
                    selection_drag_tool_module,
                    "move_item_for",
                    side_effect=corrupt_topology_then_fail,
                ),
                self.assertRaisesRegex(RuntimeError, "drag damaged scene topology"),
            ):
                tool._apply_drag_delta(QPointF(4.0, 5.0))

            self.assertIs(child.parentItem(), parent)
            self.assertEqual(parent.zValue(), 2.0)
            self.assertEqual(child.zValue(), 3.0)
            self.assertEqual(peer.zValue(), 2.0)
            self.assertEqual(list(canvas.scene().items()), expected_order)
            self.assertIsNone(tool._drag_transaction)
            self.assertFalse(tool._drag_selection)
        finally:
            self._dispose_canvas(canvas)

    def test_selection_drag_normal_release_preserves_prior_outline_suspension(self) -> None:
        canvas, shapes = self._canvas_with_shapes(count=1)
        shape = shapes[0]
        shape.setSelected(True)
        selection_style_state_for(canvas).suspend_outline = True
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        try:
            self.assertTrue(
                tool._begin_selection_drag(
                    set(),
                    [shape],
                    QPointF(0.0, 0.0),
                )
            )
            tool._apply_drag_delta(QPointF(3.0, 2.0))
            tool._commit_selection_drag()

            self.assertTrue(selection_style_state_for(canvas).suspend_outline)
            self.assertEqual(len(canvas.services.history_service.state.history), 1)
            self.assertIsNone(tool._drag_transaction)
        finally:
            self._dispose_canvas(canvas)

    def test_actual_drag_preserves_bound_history_root_and_zero_redo_authority(self) -> None:
        canvas, shapes = self._canvas_with_shapes(count=1)
        shape = shapes[0]
        shape.setSelected(True)
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        history = canvas.services.history_service
        before_state = scene_item_state_for(canvas, shape)
        baseline = MoveItemsCommand(items=[], dx=0.0, dy=0.0)
        redo_entry = MoveItemsCommand(items=[], dx=1.0, dy=1.0)
        old_state = history.state
        old_state.history[:] = [baseline]
        old_state.redo_stack[:] = [redo_entry]
        history_list = old_state.history
        redo_list = old_state.redo_stack

        try:
            self.assertTrue(
                tool._begin_selection_drag(
                    set(),
                    [shape],
                    QPointF(),
                )
            )
            replacement_entry = object()
            replacement_state = SimpleNamespace(
                history=[replacement_entry],
                redo_stack=[replacement_entry],
                enabled=True,
                limit=100,
                change_callback=None,
            )
            history.state = replacement_state

            tool.deactivate()

            self.assertIs(history.state, old_state)
            self.assertIs(old_state.history, history_list)
            self.assertIs(old_state.redo_stack, redo_list)
            self.assertEqual(history_list, [baseline])
            self.assertEqual(redo_list, [redo_entry])
            self.assertEqual(replacement_state.history, [replacement_entry])
            self.assertEqual(replacement_state.redo_stack, [replacement_entry])
            self.assertEqual(scene_item_state_for(canvas, shape), before_state)

            self.assertTrue(
                tool._begin_selection_drag(
                    set(),
                    [shape],
                    QPointF(),
                )
            )
            tool._apply_drag_delta(QPointF(7.0, -2.0))
            history_b_entry = object()
            history_b = _FakeHistoryService(
                history=[history_b_entry],
                redo_stack=[history_b_entry],
            )
            tool.context.history_service = history_b

            with self.assertRaisesRegex(RuntimeError, "history owner changed"):
                tool._commit_selection_drag()

            self.assertEqual(scene_item_state_for(canvas, shape), before_state)
            self.assertEqual(history_list, [baseline])
            self.assertEqual(redo_list, [redo_entry])
            self.assertEqual(history_b.state.history, [history_b_entry])
            self.assertEqual(history_b.state.redo_stack, [history_b_entry])

            tool.context.history_service = history
            self.assertTrue(
                tool._begin_selection_drag(
                    set(),
                    [shape],
                    QPointF(),
                )
            )
            tool._apply_drag_delta(QPointF())
            tool._commit_selection_drag()
            self.assertEqual(scene_item_state_for(canvas, shape), before_state)
            self.assertEqual(history_list, [baseline])
            self.assertEqual(redo_list, [redo_entry])

            self.assertTrue(
                tool._begin_selection_drag(
                    set(),
                    [shape],
                    QPointF(),
                )
            )
            tool._apply_drag_delta(QPointF(5.0, 3.0))
            tool._apply_drag_delta(QPointF(-5.0, -3.0))
            tool._commit_selection_drag()
            self.assertEqual(scene_item_state_for(canvas, shape), before_state)
            self.assertEqual(history_list, [baseline])
            self.assertEqual(redo_list, [redo_entry])
        finally:
            tool.context.history_service = history
            self._dispose_canvas(canvas)

    def test_direct_item_drag_deactivate_and_append_failure_restore_exact_state(self) -> None:
        canvas, shapes = self._canvas_with_shapes(count=1)
        shape = shapes[0]
        shape.setSelected(False)
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        history = canvas.services.history_service
        original_push = history.push
        before_state = scene_item_state_for(canvas, shape)

        def press_shape() -> None:
            with (
                mock.patch.object(
                    move_tool_module,
                    "selection_snapshot_for",
                    return_value=None,
                ),
                mock.patch.object(
                    tool.context,
                    "item_at_event",
                    return_value=shape,
                ),
                mock.patch.object(
                    tool.context,
                    "scene_pos_from_event",
                    return_value=QPointF(0.0, 0.0),
                ),
            ):
                self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF())))

        try:
            press_shape()
            tool._apply_drag_delta(QPointF(5.0, 3.0))
            tool.deactivate()
            self.assertEqual(scene_item_state_for(canvas, shape), before_state)
            self.assertIsNone(tool._drag_item)
            self.assertIsNone(tool._drag_transaction)
            self.assertEqual(history.state.history, [])

            baseline = MoveItemsCommand(items=[], dx=0.0, dy=0.0)
            redo_entry = MoveItemsCommand(items=[], dx=1.0, dy=1.0)
            history.state.history[:] = [baseline]
            history.state.redo_stack[:] = [redo_entry]
            history_list = history.state.history
            redo_list = history.state.redo_stack
            primary = KeyboardInterrupt("direct item history append interrupted")

            def append_then_interrupt(command) -> None:
                original_push(command)
                raise primary

            history.push = append_then_interrupt
            press_shape()
            tool._apply_drag_delta(QPointF(-4.0, 6.0))
            try:
                tool._commit_direct_item_drag()
            except KeyboardInterrupt as error:
                self.assertIs(error, primary)
            else:
                self.fail("direct item append-then-raise was not propagated")

            self.assertEqual(scene_item_state_for(canvas, shape), before_state)
            self.assertIs(history.state.history, history_list)
            self.assertIs(history.state.redo_stack, redo_list)
            self.assertEqual(history_list, [baseline])
            self.assertEqual(redo_list, [redo_entry])
            self.assertIsNone(tool._drag_item)
            self.assertIsNone(tool._drag_transaction)
        finally:
            history.push = original_push
            self._dispose_canvas(canvas)

    def test_handle_drag_cancel_retry_and_append_failure_restore_exact_state(self) -> None:
        canvas, shapes = self._canvas_with_shapes(count=1)
        shape = shapes[0]
        handle = QGraphicsEllipseItem(-2.0, -2.0, 4.0, 4.0)
        handle.setData(0, "handle")
        handle.setData(2, shape)
        canvas.scene().addItem(handle)
        tool = SelectTool(canvas, context=canvas.services.tools.context)
        history = canvas.services.history_service
        original_push = history.push
        before_state = scene_item_state_for(canvas, shape)

        def press_handle() -> None:
            with mock.patch.object(
                tool.context,
                "item_at_event",
                return_value=handle,
            ):
                self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF())))

        try:
            press_handle()
            canvas.services.move_controller.move_item(shape, 8.0, -3.0)
            self.assertNotEqual(scene_item_state_for(canvas, shape), before_state)
            tool.deactivate()
            self.assertEqual(scene_item_state_for(canvas, shape), before_state)
            self.assertIsNone(tool._active_handle)
            self.assertIsNone(tool._drag_transaction)

            # A canceled handle interaction can start and finish again without
            # inheriting the previous savepoint or manufacturing history.
            press_handle()
            self.assertTrue(tool.on_mouse_release(_FakeEvent(QPointF())))
            self.assertIsNone(tool._drag_transaction)
            self.assertEqual(history.state.history, [])

            baseline = MoveItemsCommand(items=[], dx=0.0, dy=0.0)
            redo_entry = MoveItemsCommand(items=[], dx=1.0, dy=1.0)
            history.state.history[:] = [baseline]
            history.state.redo_stack[:] = [redo_entry]
            history_list = history.state.history
            redo_list = history.state.redo_stack
            primary = SystemExit("handle history append terminated")

            def append_then_terminate(command) -> None:
                original_push(command)
                raise primary

            history.push = append_then_terminate
            press_handle()
            canvas.services.move_controller.move_item(shape, -6.0, 5.0)
            try:
                tool.on_mouse_release(_FakeEvent(QPointF()))
            except SystemExit as error:
                self.assertIs(error, primary)
            else:
                self.fail("handle append-then-raise was not propagated")

            self.assertEqual(scene_item_state_for(canvas, shape), before_state)
            self.assertIs(history.state.history, history_list)
            self.assertIs(history.state.redo_stack, redo_list)
            self.assertEqual(history_list, [baseline])
            self.assertEqual(redo_list, [redo_entry])
            self.assertIsNone(tool._active_handle)
            self.assertIsNone(tool._drag_transaction)
        finally:
            history.push = original_push
            self._dispose_canvas(canvas)

    def test_fail_once_drag_cancel_retry_is_successful(self) -> None:
        canvas = _FakeSelectCanvas()
        tool = SelectTool(canvas, context=_tool_context_for(canvas))
        item = _FakeItem("note")
        self.assertTrue(
            tool._begin_selection_drag(set(), [item], QPointF(0.0, 0.0))
        )
        transient = RuntimeError("first exact cancel failed")
        first = HistoryTransactionRestoreResult(
            authoritative=False,
            fallback_to_inverse=False,
            errors=(transient,),
        )
        second = HistoryTransactionRestoreResult(
            authoritative=True,
            fallback_to_inverse=False,
            errors=(),
        )

        with mock.patch.object(
            selection_drag_tool_module,
            "restore_history_transaction_for_history",
            side_effect=(first, second),
        ) as restore:
            tool.deactivate()

        self.assertEqual(restore.call_count, 2)
        self.assertIsNone(tool._drag_transaction)
        self.assertFalse(tool._drag_selection)
        self.assertIsNone(tool._start_pos)

    def test_drag_owner_cas_restores_only_outer_token_after_reentrant_replacement(self) -> None:
        for replacement_phase in ("commit", "release"):
            with self.subTest(replacement_phase=replacement_phase):
                canvas = _FakeSelectCanvas()
                tool = SelectTool(canvas, context=_tool_context_for(canvas))
                self.assertTrue(
                    tool._begin_selection_drag(
                        set(),
                        [_FakeItem("note")],
                        QPointF(),
                    )
                )
                outer = tool._require_drag_token()
                replacement = object()
                authoritative = HistoryTransactionRestoreResult(
                    authoritative=True,
                )

                def operation(
                    _owner,
                    *,
                    phase=replacement_phase,
                    active_tool=tool,
                    next_owner=replacement,
                ) -> None:
                    if phase == "commit":
                        active_tool._drag_transaction = next_owner

                def release(
                    _canvas,
                    snapshot,
                    *,
                    expected_snapshot=outer.canvas_snapshot,
                    phase=replacement_phase,
                    active_tool=tool,
                    next_owner=replacement,
                ) -> None:
                    self.assertIs(snapshot, expected_snapshot)
                    if phase == "release":
                        active_tool._drag_transaction = next_owner

                with (
                    mock.patch.object(
                        selection_drag_tool_module,
                        "release_history_transaction_for_history",
                        side_effect=release,
                    ) as release_port,
                    mock.patch.object(
                        selection_drag_tool_module,
                        "restore_history_transaction_for_history",
                        return_value=authoritative,
                    ) as restore_port,
                ):
                    with self.assertRaisesRegex(RuntimeError, "owner changed"):
                        tool._commit_drag_transaction(operation)

                self.assertIs(tool._drag_transaction, replacement)
                restore_port.assert_called_once_with(
                    canvas,
                    outer.canvas_snapshot,
                )
                if replacement_phase == "commit":
                    release_port.assert_not_called()
                else:
                    release_port.assert_called_once()

    def test_actual_reentrant_drag_reapplies_replacement_geometry_and_delta(
        self,
    ) -> None:
        canvas, shapes = self._canvas_with_shapes(count=1)
        shape = shapes[0]
        shape.setSelected(True)
        tool = MoveTool(canvas, context=canvas.services.tools.context)
        history_service = canvas.services.history_service
        original_push = history_service.push
        replacement: dict[str, object] = {}

        def publish_replacement(_command) -> None:
            # Owner B must capture the real service port; only owner A is
            # supposed to encounter this re-entrant publication callback.
            history_service.push = original_push
            self.assertTrue(
                tool._begin_selection_drag(
                    set(),
                    [shape],
                    QPointF(),
                )
            )
            replacement["token"] = tool._require_drag_token()
            tool._apply_drag_delta(QPointF(5.0, 0.0))
            replacement["state"] = scene_item_state_for(canvas, shape)

        history_service.push = publish_replacement
        try:
            self.assertTrue(
                tool._begin_selection_drag(
                    set(),
                    [shape],
                    QPointF(),
                )
            )
            tool._apply_drag_delta(QPointF(10.0, 0.0))
            with self.assertRaisesRegex(RuntimeError, "owner changed"):
                tool._commit_selection_drag()

            self.assertIs(tool._drag_transaction, replacement["token"])
            self.assertEqual(tool._total_delta, QPointF(5.0, 0.0))
            self.assertEqual(
                scene_item_state_for(canvas, shape),
                replacement["state"],
            )
            self.assertEqual(
                canvas.services.history_service.state.history,
                [],
            )

            tool._commit_selection_drag()

            history = canvas.services.history_service.state.history
            self.assertEqual(len(history), 1)
            self.assertIsInstance(history[0], MoveItemsCommand)
            self.assertEqual(history[0].dx, 5.0)
            self.assertEqual(history[0].dy, 0.0)
            self.assertEqual(
                scene_item_state_for(canvas, shape),
                replacement["state"],
            )
            self.assertIsNone(tool._drag_transaction)
        finally:
            history_service.push = original_push
            self._dispose_canvas(canvas)

    def test_drag_history_authority_restores_state_root_and_rejects_context_b(self) -> None:
        old_history_entry = object()
        old_redo_entry = object()
        history_a = _FakeHistoryService(
            history=[old_history_entry],
            redo_stack=[old_redo_entry],
        )
        canvas = _FakeSelectCanvas()
        canvas.services.history_service = history_a
        tool = SelectTool(canvas, context=_tool_context_for(canvas))
        self.assertTrue(
            tool._begin_selection_drag(
                set(),
                [_FakeItem("note")],
                QPointF(),
            )
        )
        old_state = history_a.state
        old_history = old_state.history
        old_redo = old_state.redo_stack
        replacement_entry = object()
        replacement_state = SimpleNamespace(
            history=[replacement_entry],
            redo_stack=[replacement_entry],
            enabled=True,
            limit=100,
            change_callback=None,
        )
        history_a.state = replacement_state

        tool.deactivate()

        self.assertIs(history_a.state, old_state)
        self.assertIs(old_state.history, old_history)
        self.assertIs(old_state.redo_stack, old_redo)
        self.assertEqual(old_history, [old_history_entry])
        self.assertEqual(old_redo, [old_redo_entry])
        self.assertEqual(replacement_state.history, [replacement_entry])
        self.assertEqual(replacement_state.redo_stack, [replacement_entry])

        self.assertTrue(
            tool._begin_selection_drag(
                set(),
                [_FakeItem("note")],
                QPointF(),
            )
        )
        history_b_entry = object()
        history_b = _FakeHistoryService(
            history=[history_b_entry],
            redo_stack=[history_b_entry],
        )
        tool.context.history_service = history_b

        with self.assertRaisesRegex(RuntimeError, "history owner changed"):
            tool._commit_selection_drag()

        self.assertIsNone(tool._drag_transaction)
        self.assertIs(tool.context.history_service, history_b)
        self.assertEqual(history_b.state.history, [history_b_entry])
        self.assertEqual(history_b.state.redo_stack, [history_b_entry])
        self.assertEqual(old_history, [old_history_entry])
        self.assertEqual(old_redo, [old_redo_entry])

    def test_zero_and_net_zero_drags_preserve_redo_without_move_or_history_callbacks(self) -> None:
        redo_entry = object()
        history = _FakeHistoryService(redo_stack=[redo_entry])
        canvas = _FakeMoveCanvas()
        canvas.services.history_service = history
        tool = MoveTool(canvas, context=_tool_context_for(canvas))
        item = _FakeItem("note")

        self.assertTrue(
            tool._begin_selection_drag(set(), [item], QPointF(4.0, 5.0))
        )
        tool._apply_drag_delta(QPointF())
        tool._commit_selection_drag()

        self.assertEqual(canvas.moved_items, [])
        self.assertEqual(history.state.history, [])
        self.assertEqual(history.state.redo_stack, [redo_entry])
        self.assertEqual(history.push_calls, [])

        self.assertTrue(
            tool._begin_selection_drag(set(), [item], QPointF(4.0, 5.0))
        )
        tool._apply_drag_delta(QPointF(8.0, -3.0))
        tool._apply_drag_delta(QPointF(-8.0, 3.0))
        tool._commit_selection_drag()

        self.assertEqual(
            [(call[1], call[2]) for call in canvas.moved_items],
            [(8.0, -3.0), (-8.0, 3.0)],
        )
        self.assertEqual(history.state.history, [])
        self.assertEqual(history.state.redo_stack, [redo_entry])
        self.assertEqual(history.push_calls, [])

    def test_move_press_uses_one_immutable_selection_generation(self) -> None:
        canvas = _FakeMoveCanvas()
        canvas.services.history_service = _FakeHistoryService()
        note = _FakeItem("note")
        atom = _FakeItem("atom", 1)
        unrelated = _FakeItem("atom", 99)
        selection_reads = 0

        def selected_items():
            nonlocal selection_reads
            selection_reads += 1
            if selection_reads == 1:
                return [note, atom]
            return [unrelated]

        canvas.scene_obj.selectedItems = selected_items
        tool = MoveTool(canvas, context=_tool_context_for(canvas))

        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(2.0, 3.0))))

        self.assertEqual(selection_reads, 1)
        self.assertEqual(tool._selection_atom_ids, {1})
        self.assertEqual(tool._selection_items, [note])
        tool.deactivate()

        select_canvas = _FakeSelectCanvas()
        select_canvas.services.history_service = _FakeHistoryService()
        selected_note = _FakeItem("note")
        select_reads = 0

        def select_items():
            nonlocal select_reads
            select_reads += 1
            return [selected_note]

        select_canvas.scene_obj.selectedItems = select_items
        select_canvas.selection_hit = True
        select_tool = SelectTool(
            select_canvas,
            context=_tool_context_for(select_canvas),
        )

        self.assertTrue(
            select_tool.on_mouse_press(_FakeEvent(QPointF(6.0, 7.0)))
        )

        self.assertEqual(select_reads, 1)
        self.assertEqual(select_tool._selection_items, [selected_note])
        select_tool.deactivate()

    def test_bond_tool_preview_management_and_snap_helpers(self) -> None:
        canvas = _FakeBondCanvas()
        tool = BondTool(canvas, context=_tool_context_for(canvas))

        with mock.patch.object(bond_tool_module, "clear_bond_preview_items_for", return_value=[]) as clear_helper:
            tool._preview_items = ["old"]
            tool._preview_signature = "single:1"
            tool._clear_preview_items()
            clear_helper.assert_called_once_with(canvas, ["old"])
            self.assertEqual(tool._preview_items, [])
            self.assertIsNone(tool._preview_signature)

        tool.activate()
        self.assertEqual(canvas.drag_mode, canvas.DragMode.NoDrag)

        tool._preview_items = ["existing"]
        tool._preview_signature = "single:1"
        tool._start_atom_id = 5
        with mock.patch.object(bond_tool_module, "update_bond_preview_items_for", return_value=True) as update_helper:
            tool._set_preview_items(QPointF(0.0, 0.0), QPointF(10.0, 0.0))
        update_helper.assert_called_once_with(
            canvas,
            ["existing"],
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            a_id=5,
            b_id=None,
            style="single",
            order=1,
        )

        with mock.patch.object(bond_tool_module, "update_bond_preview_items_for", return_value=False), \
             mock.patch.object(bond_tool_module, "add_bond_preview_items_for", return_value=["added"]) as add_helper, \
             mock.patch.object(bond_tool_module, "clear_bond_preview_items_for", return_value=[]), \
             mock.patch.object(bond_tool_module, "build_bond_preview_items_for", return_value=["preview"]):
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

    def test_bond_tool_additional_guard_and_deactivate_paths(self) -> None:
        canvas = _FakeBondCanvas()
        tool = BondTool(canvas, context=_tool_context_for(canvas))
        tool._preview_signature = "single:1"
        tool.deactivate()
        self.assertIsNone(tool._start_pos)
        self.assertIsNone(tool._start_atom_id)
        self.assertIsNone(tool._press_scene_pos)
        self.assertIsNone(tool._preview_signature)

        tool._clear_preview_items()
        self.assertIsNone(tool._preview_signature)

        with mock.patch.object(bond_tool_module, "build_bond_preview_items_for", return_value=[]):
            with mock.patch.object(bond_tool_module, "add_bond_preview_items_for") as add_helper:
                tool._set_preview_items(QPointF(0.0, 0.0), QPointF(2.0, 0.0))
        add_helper.assert_not_called()

        self.assertFalse(tool._apply_active_style_to_bond(99))
        canvas.model.bonds[0] = None
        self.assertFalse(tool._apply_active_style_to_bond(0))

        canvas.model.bonds[0] = Bond(1, 2, 2, style="bold_out")
        set_tool_setting_for(canvas, "active_bond_style", "bold")
        self.assertTrue(tool._apply_active_style_to_bond(0))
        self.assertEqual(canvas.bond_style_calls[-1], (0, "bold_in", 2))

        canvas.model.bonds[0] = Bond(1, 2, 2, style="single")
        self.assertTrue(tool._apply_active_style_to_bond(0))
        self.assertEqual(canvas.bond_style_calls[-1], (0, "bold_in", 2))
        self.assertFalse(tool.on_mouse_press(_FakeEvent(button=Qt.MouseButton.RightButton)))

        with mock.patch.object(tool, "_clear_preview_items") as clear_preview, \
             mock.patch.object(tool, "_snap_to_atom", return_value=QPointF(8.0, 8.0)), \
             mock.patch.object(tool, "_snap_endpoint", return_value=QPointF(9.0, 9.0)), \
             mock.patch.object(
                 bond_tool_module,
                 "default_bond_endpoint_for",
                 return_value=QPointF(canvas.default_endpoint),
             ):
            tool._start_pos = QPointF(1.0, 1.0)
            tool._start_atom_id = 1
            tool._press_scene_pos = None
            self.assertTrue(tool.on_mouse_release(_FakeEvent(QPointF(4.0, 4.0))))
            clear_preview.assert_called_once()
        self.assertEqual(canvas.added_bonds[-1][1], QPointF(canvas.default_endpoint))

        canvas.added_bonds.clear()
        with mock.patch.object(tool, "_clear_preview_items"), \
             mock.patch.object(tool, "_snap_to_atom", return_value=QPointF(6.0, 6.0)), \
             mock.patch.object(tool, "_snap_endpoint", return_value=QPointF(7.0, 7.0)):
            tool._start_pos = QPointF(1.0, 1.0)
            tool._start_atom_id = 1
            tool._press_scene_pos = QPointF(0.0, 0.0)
            self.assertTrue(tool.on_mouse_release(_FakeEvent(QPointF(20.0, 0.0))))
        self.assertEqual(canvas.added_bonds[-1][1], QPointF(7.0, 7.0))

    def test_bond_tool_mouse_press_move_release_and_style_dispatch(self) -> None:
        canvas = _FakeBondCanvas()
        tool = BondTool(canvas, context=_tool_context_for(canvas))

        selected_item = _FakeItem("atom", 99)
        selected_item.setSelected(True)
        canvas.scene_obj.selected_items = [selected_item]
        set_selected_notes_for(canvas, ["note"])
        canvas.atom_near = 1
        with mock.patch.object(tool, "_set_preview_items"):
            self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(2.0, 2.0))))
        self.assertEqual(canvas.scene_obj.clear_selection_calls, 1)
        self.assertEqual(canvas.scene_obj.selectedItems(), [])
        self.assertEqual(selected_notes_for(canvas), [])
        self.assertEqual(canvas.clear_note_selection_calls, 1)
        canvas.atom_near = None

        canvas.item = _FakeItem("bond", 0)
        set_tool_setting_for(canvas, "active_bond_style", "wedge")
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        self.assertEqual(canvas.bond_style_calls[-1], (0, "wedge", 1))

        set_tool_setting_for(canvas, "active_bond_style", "bold")
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        self.assertEqual(canvas.bond_style_calls[-1], (0, "bold_out", 2))

        set_tool_setting_for(canvas, "active_bond_style", "single")
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        self.assertEqual(canvas.cycle_calls[-1], 0)

        canvas.model.bonds[0] = Bond(1, 2, 2, style="double")
        set_tool_setting_for(canvas, "active_bond_style", "dotted")
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        self.assertEqual(canvas.bond_style_calls[-1], (0, "dotted_double", 2))

        canvas.model.bonds[0] = Bond(1, 2, 2, style="bold_in")
        canvas.item = None
        set_hover_bond_id_for(canvas, 0)
        set_tool_setting_for(canvas, "active_bond_style", "bold")
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 1.0))))
        self.assertEqual(canvas.bond_style_calls[-1], (0, "bold_out", 2))

        set_hover_bond_id_for(canvas, None)
        canvas.atom_near = 1
        with mock.patch.object(tool, "_set_preview_items") as preview:
            self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(2.0, 2.0))))
            preview.assert_called_once()

        canvas.atom_near = None
        canvas.item = None
        canvas.preferred_item = _FakeItem("bond", 0)
        set_tool_setting_for(canvas, "active_bond_style", "single")
        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(3.0, 3.0))))
        self.assertEqual(canvas.cycle_calls[-1], 0)
        canvas.preferred_item = None

        with mock.patch.object(tool, "_set_preview_items") as preview:
            self.assertTrue(tool.on_mouse_move(_FakeEvent(QPointF(4.0, 4.0))))
            preview.assert_called_once()

        with mock.patch.object(tool, "_clear_preview_items") as clear_preview, \
             mock.patch.object(
                 bond_tool_module,
                 "default_bond_endpoint_for",
                 return_value=QPointF(canvas.default_endpoint),
             ):
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
        tool = ArrowTool(canvas, mode="auto", context=_tool_context_for(canvas))
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

    def test_preview_drag_release_clears_start_position_when_commit_raises(self) -> None:
        canvas = _FakePreviewCanvas()
        canvas.services.scene_decoration_service.add_arrow = mock.Mock(side_effect=RuntimeError("commit"))
        tool = ArrowTool(canvas, mode="auto", context=_tool_context_for(canvas))

        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 2.0))))
        self.assertTrue(tool.on_mouse_move(_FakeEvent(QPointF(5.0, 6.0))))

        with self.assertRaisesRegex(RuntimeError, "commit"):
            tool.on_mouse_release(_FakeEvent(QPointF(8.0, 9.0)))

        self.assertIsNone(tool._start_pos)
        self.assertIsNone(tool._preview_item)

    def test_ts_bracket_tool_preview_drag_and_deactivate_cleanup(self) -> None:
        canvas = _FakePreviewCanvas()
        tool = TSBracketTool(canvas, context=_tool_context_for(canvas))
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
        preview_tool = PreviewDragTool("preview", canvas, context=_tool_context_for(canvas))
        with self.assertRaises(NotImplementedError):
            preview_tool._build_preview(QPointF(1.0, 2.0))
        with self.assertRaises(NotImplementedError):
            preview_tool._commit_drag(QPointF(3.0, 4.0))

        tool = ArrowTool(canvas, context=_tool_context_for(canvas))
        self.assertFalse(tool.on_mouse_press(_FakeEvent(button=Qt.MouseButton.RightButton)))
        self.assertFalse(tool.on_mouse_move(_FakeEvent(QPointF(1.0, 2.0))))
        self.assertFalse(tool.on_mouse_release(_FakeEvent(QPointF(1.0, 2.0))))


if __name__ == "__main__":
    unittest.main()
