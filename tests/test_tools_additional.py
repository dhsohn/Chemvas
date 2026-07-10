import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QTextCursor
    from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsTextItem
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    import ui.edit_tools as edit_tools_module
    import ui.perspective_tool as perspective_tool_module
    import ui.text_tool as text_tool_module
    from core.history import (
        AddAtomsCommand,
        CompositeCommand,
        SetSmilesInputCommand,
    )
    from core.model import Atom, Bond, MoleculeModel
    from ui.canvas_hover_state import set_hover_atom_id_for, set_hover_bond_id_for
    from ui.canvas_rotation_state import CanvasRotationState
    from ui.canvas_smiles_input_state import set_last_smiles_input_for
    from ui.canvas_tool_settings_state import CanvasToolSettingsState
    from ui.history_commands import DeleteSceneItemsCommand, MoveItemsCommand
    from ui.tool_context import ToolContext
    from ui.tools import (
        BenzeneTool,
        ColorTool,
        DeleteTool,
        EditBondTool,
        FlipTool,
        MarkTool,
        MoveTool,
        NoteTool,
        OrbitalTool,
        PerspectiveTool,
        TextTool,
        ToolController,
        TransformTool,
    )


def _tool_context_for(canvas):
    services = getattr(canvas, "services", None)
    graph_service = getattr(services, "canvas_graph_service", None)
    color_mutation_service = getattr(services, "canvas_color_mutation_service", None)
    tool_mode_controller = getattr(services, "tool_mode_controller", None)
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
        selected_scene_items=lambda *, excluded_kinds: [
            item for item in canvas.scene().selectedItems() if item.data(0) not in excluded_kinds
        ],
        select_single_structure_item=getattr(canvas, "select_structure_for_item", None),
        atom_symbol_provider=getattr(tool_mode_controller, "get_atom_symbol", None),
        history_service=getattr(services, "history_service", None),
        set_drag_mode=getattr(canvas, "setDragMode", None),
        rubber_band_drag_mode=getattr(getattr(canvas, "DragMode", None), "RubberBandDrag", None),
    )


class _Event:
    def __init__(
        self,
        pos: QPointF | None = None,
        *,
        button=Qt.MouseButton.LeftButton,
        buttons=None,
        modifiers=Qt.KeyboardModifier.NoModifier,
    ) -> None:
        self._pos = QPointF(pos or QPointF())
        self._button = button
        self._buttons = button if buttons is None else buttons
        self._modifiers = modifiers

    def button(self):
        return self._button

    def buttons(self):
        return self._buttons

    def modifiers(self):
        return self._modifiers

    def position(self):
        return QPointF(self._pos)


class _DataItem:
    def __init__(self, kind=None, item_id=None, *, scene_obj=None) -> None:
        self._data = {0: kind, 1: item_id}
        self._scene = scene_obj
        self.selected = False
        self.visible = True
        self._has_focus = False

    def hasFocus(self) -> bool:
        return self._has_focus

    def data(self, key):
        return self._data.get(key)

    def setData(self, key, value) -> None:
        self._data[key] = value

    def scene(self):
        return self._scene

    def setSelected(self, selected: bool) -> None:
        self.selected = selected

    def isVisible(self) -> bool:
        return self.visible

    def setVisible(self, visible: bool) -> None:
        self.visible = visible


class _Scene:
    def __init__(self) -> None:
        self._selected_items = []

    def selectedItems(self):
        return list(self._selected_items)


class _TextCanvas:
    DragMode = SimpleNamespace(NoDrag="none")

    def __init__(self) -> None:
        self.drag_mode = None
        self.renderer = SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0))
        self.hover_atom_id = None
        self.hover_bond_id = None
        self.item = None
        self.bond_near = None
        self.find_atom_result = None
        self.tool_settings_state = CanvasToolSettingsState(atom_symbol="")
        self.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("O", 10.0, 0.0),
            },
            bonds=[Bond(1, 2, 1)],
        )
        set_last_smiles_input_for(self, "before")
        self.added_atoms = []
        self.label_calls = []
        self.pushed_commands = []
        self.history_service = SimpleNamespace(push=self.push_command)
        self.services = SimpleNamespace(
            history_service=self.history_service,
            canvas_atom_mutation_service=SimpleNamespace(add_atom=self.add_atom),
            atom_label_service=SimpleNamespace(add_or_update_atom_label=self.add_or_update_atom_label),
            tool_mode_controller=SimpleNamespace(get_atom_symbol=lambda: self.tool_settings_state.atom_symbol),
            hit_testing_service=SimpleNamespace(
                scene_pos_from_event=self.scene_pos_from_event,
                item_at_event=self.item_at_event,
                find_atom_near=self.find_atom_near,
                find_bond_near=self.find_bond_near,
            ),
        )

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def scene_pos_from_event(self, event):
        return event.position()

    def item_at_event(self, event):
        return self.item

    def find_bond_near(self, pos, radius):
        return self.bond_near

    def find_atom_near(self, x, y, radius):
        return self.find_atom_result

    def add_atom(self, element: str, x: float, y: float) -> int:
        self.added_atoms.append((element, x, y))
        return self.model.add_atom(element, x, y)

    def add_or_update_atom_label(
        self,
        atom_id: int,
        text: str,
        *,
        clear_smiles: bool = True,
        show_carbon: bool = False,
        record: bool = True,
        allow_merge: bool = True,
    ) -> None:
        self.label_calls.append((atom_id, text, show_carbon, record))
        self.model.atoms[atom_id].element = text

    def _atom_state_dict(self, atom_id: int) -> dict:
        atom = self.model.atoms[atom_id]
        return {"element": atom.element, "x": atom.x, "y": atom.y}

    def push_command(self, command) -> None:
        self.pushed_commands.append(command)


class _MiscCanvas:
    DragMode = SimpleNamespace(NoDrag="none")

    def __init__(self) -> None:
        self.drag_mode = None
        self.renderer = SimpleNamespace(style=SimpleNamespace(atom_color="#224466"))
        self.scene_obj = _Scene()
        self.item = None
        self.colored = []
        self.color_batches = []
        self.flipped = []
        self.cycled = []
        self.bond_id = None
        self.services = SimpleNamespace(
            canvas_color_mutation_service=SimpleNamespace(
                apply_color_to_item=self.apply_color_to_item,
                apply_color_to_items=self.apply_color_to_items,
            ),
            scene_transform_controller=SimpleNamespace(
                flip_bond_direction=self.flip_bond_direction,
                cycle_bond_style=self.cycle_bond_style,
            ),
            hit_testing_service=SimpleNamespace(
                item_at_event=self.item_at_event,
                bond_id_from_event=self.bond_id_from_event,
            ),
        )

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def item_at_event(self, event):
        return self.item

    def scene(self):
        return self.scene_obj

    def apply_color_to_item(self, item, color) -> None:
        self.colored.append((item, color.name()))

    def apply_color_to_items(self, items, color) -> None:
        items = list(items)
        self.color_batches.append((items, color.name()))
        for item in items:
            self.apply_color_to_item(item, color)

    def flip_bond_direction(self, bond_id: int) -> None:
        self.flipped.append(bond_id)

    def bond_id_from_event(self, event):
        return self.bond_id

    def cycle_bond_style(self, bond_id: int) -> None:
        self.cycled.append(bond_id)


class _DeleteCanvas:
    DragMode = SimpleNamespace(NoDrag="none")

    def __init__(self) -> None:
        self.drag_mode = None
        self.scene_obj = object()
        self.item = None
        set_last_smiles_input_for(self, "before")
        self.deleted_atoms = []
        self.deleted_bonds = []
        self.deleted_rings = []
        self.removed_items = []
        self.pushed_commands = []
        self.history_service = SimpleNamespace(push=self.push_command)
        self.services = SimpleNamespace(
            history_service=self.history_service,
            scene_delete_controller=SimpleNamespace(
                delete_atom=self.delete_atom,
                delete_bond=self.delete_bond,
                delete_ring=self.delete_ring,
            ),
            scene_item_controller=SimpleNamespace(remove_scene_item=self.remove_scene_item),
            hit_testing_service=SimpleNamespace(item_at_event=self.item_at_event),
        )

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def scene(self):
        return self.scene_obj

    def item_at_event(self, event):
        return self.item

    def delete_atom(self, atom_id: int, record: bool = True):
        self.deleted_atoms.append((atom_id, record))
        return f"atom-{atom_id}"

    def delete_bond(self, bond_id: int, record: bool = True):
        self.deleted_bonds.append((bond_id, record))
        return f"bond-{bond_id}"

    def delete_ring(self, item, record: bool = True):
        self.deleted_rings.append((item, record))
        return "ring"

    def remove_scene_item(self, item) -> None:
        self.removed_items.append(item)

    def push_command(self, command) -> None:
        self.pushed_commands.append(command)


class _MoveCanvas:
    DragMode = SimpleNamespace(NoDrag="none")

    def __init__(self) -> None:
        self.drag_mode = None
        self.selected_items_for_transform = []
        self.selected_atom_ids = set()
        self.selected_bond_ids = set()
        self.model = SimpleNamespace(bonds=[Bond(1, 2, 1)])
        self.item = None
        self.pushed_commands = []
        self.history_service = SimpleNamespace(push=self.push_command)
        self.selection_outline_updates = 0
        self.services = SimpleNamespace(
            history_service=self.history_service,
            hit_testing_service=SimpleNamespace(
                item_at_event=self.item_at_event,
                scene_pos_from_event=lambda event: event.position(),
            ),
        )

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def _selected_items_for_transform(self):
        return list(self.selected_items_for_transform)

    def item_at_event(self, event):
        return self.item

    def move_item(self, item, dx: float, dy: float) -> None:
        pass

    def _update_selection_outline(self) -> None:
        self.selection_outline_updates += 1

    def push_command(self, command) -> None:
        self.pushed_commands.append(command)


class _OrbitalMarkNoteCanvas:
    DragMode = SimpleNamespace(NoDrag="none")

    def __init__(self) -> None:
        self.drag_mode = None
        self.renderer = SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0))
        self.item = None
        self.atom_near = None
        self.added_orbitals = []
        self.orbital_handles = []
        self.curved_handles = []
        self.clear_handles_calls = 0
        self.added_atom_marks = []
        self.added_marks = []
        self.toggled_notes = []
        self.selected_notes = []
        self.edited_notes = []
        self.clear_note_selection_calls = 0
        self.added_notes = []
        self.services = SimpleNamespace(
            hit_testing_service=SimpleNamespace(
                scene_pos_from_event=self.scene_pos_from_event,
                item_at_event=self.item_at_event,
                find_atom_near=self.find_atom_near,
            ),
            scene_decoration_service=SimpleNamespace(
                add_mark=self.add_mark,
                add_orbital=self.add_orbital,
            ),
            canvas_mark_scene_service=SimpleNamespace(add_mark_for_atom=self.add_mark_for_atom),
            note_controller=SimpleNamespace(
                create_text_note=self.add_text_note,
                begin_note_edit=self.begin_note_edit,
            ),
            selection_controller=SimpleNamespace(
                toggle_note_selection=self.toggle_note_selection,
                select_note=self.select_note,
                clear_note_selection=self.clear_note_selection,
            ),
            handle_overlay_service=SimpleNamespace(
                clear_handles=self.clear_handles,
                show_orbital_handles=self.show_orbital_handles,
                show_curved_handles=self.show_curved_handles,
            ),
        )

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def item_at_event(self, event):
        return self.item

    def scene_pos_from_event(self, event):
        return event.position()

    def add_orbital(self, pos) -> None:
        self.added_orbitals.append(QPointF(pos))

    def clear_handles(self) -> None:
        self.clear_handles_calls += 1

    def show_orbital_handles(self, item) -> None:
        self.orbital_handles.append(item)

    def show_curved_handles(self, item) -> None:
        self.curved_handles.append(item)

    def find_atom_near(self, x, y, radius):
        return self.atom_near

    def add_mark_for_atom(self, atom_id: int, pos, *, kind: str | None = None, record: bool = True) -> None:
        self.added_atom_marks.append((atom_id, QPointF(pos)))

    def add_mark(
        self,
        pos,
        *,
        kind: str | None = None,
        atom_id: int | None = None,
        offset=None,
        record: bool = True,
    ) -> None:
        self.added_marks.append(QPointF(pos))

    def toggle_note_selection(self, item) -> None:
        self.toggled_notes.append(item)

    def select_note(self, item, additive: bool = False) -> None:
        self.selected_notes.append((item, additive))

    def begin_note_edit(self, item) -> None:
        self.edited_notes.append(item)

    def clear_note_selection(self) -> None:
        self.clear_note_selection_calls += 1

    def add_text_note(self, pos, text):
        note = _DataItem("note", scene_obj=None)
        self.added_notes.append((QPointF(pos), text, note))
        return note


class _PerspectiveCanvas:
    DragMode = SimpleNamespace(RubberBandDrag="rubber")

    def __init__(self) -> None:
        self.drag_mode = None
        self.item = None
        self.preferred_item = None
        self.selection_hit = False
        self.toggle_result = False
        self.select_result = True
        self.begin_rotation_result = True
        self.rotation_state = CanvasRotationState(mode="rigid")
        self.clear_handles_calls = 0
        self.selection_targets = []
        self.begin_calls = []
        self.update_calls = []
        self.end_calls = 0
        self.services = SimpleNamespace(
            hit_testing_service=SimpleNamespace(
                scene_pos_from_event=lambda event: event.position(),
                item_at_event=lambda event: self.item,
                bond_id_from_event=lambda event: None,
            ),
            selection_controller=SimpleNamespace(
                toggle_item_selection=self.toggle_item_selection,
                preferred_structure_item_at_scene_pos=lambda pos: self.preferred_item,
                selection_hit_test=lambda pos, snapshot=None: self.selection_hit,
                select_structure_for_item=self.select_structure_for_item,
            ),
            handle_overlay_service=SimpleNamespace(clear_handles=self.clear_handles),
            selection_rotation_controller=SimpleNamespace(
                begin_selection_3d_rotation=self.begin_selection_3d_rotation,
                update_selection_3d_rotation=self.update_selection_3d_rotation,
                end_selection_3d_rotation=self.end_selection_3d_rotation,
            ),
        )

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def item_at_event(self, event):
        return self.item

    def toggle_item_selection(self, item):
        return self.toggle_result

    def clear_handles(self) -> None:
        self.clear_handles_calls += 1

    def scene_pos_from_event(self, event):
        return event.position()

    def preferred_structure_item_at_scene_pos(self, pos):
        return self.preferred_item

    def selection_hit_test(self, pos):
        return self.selection_hit

    def select_structure_for_item(self, item):
        self.selection_targets.append(item)
        return self.select_result

    def begin_selection_3d_rotation(self, axis_hint=None, press_pos=None):
        self.begin_calls.append((axis_hint, QPointF(press_pos) if press_pos is not None else None))
        return self.begin_rotation_result

    def update_selection_3d_rotation(self, delta_x: float, delta_y: float) -> None:
        self.update_calls.append((delta_x, delta_y))

    def end_selection_3d_rotation(self) -> None:
        self.end_calls += 1


class _ControllerCanvas:
    DragMode = SimpleNamespace(NoDrag="none", RubberBandDrag="rubber")

    def __init__(self) -> None:
        self.drag_mode = None
        self.clear_benzene_preview_calls = 0
        self.services = SimpleNamespace(
            benzene_preview_service=SimpleNamespace(clear_preview=self.clear_benzene_preview)
        )

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def clear_benzene_preview(self) -> None:
        self.clear_benzene_preview_calls += 1

    def scene(self):
        return object()


class _PreviewScene:
    def __init__(self) -> None:
        self.removed_items = []

    def removeItem(self, item) -> None:
        self.removed_items.append(item)


class _PreviewItem:
    def __init__(self, scene_obj) -> None:
        self._scene = scene_obj

    def scene(self):
        return self._scene


class _ToolControllerPreviewCanvas:
    DragMode = SimpleNamespace(NoDrag="none", RubberBandDrag="rubber")

    def __init__(self) -> None:
        self.drag_mode = None
        self.scene_obj = _PreviewScene()
        self.active_arrow_type = "reaction"
        self.clear_handles_calls = 0
        self.clear_benzene_preview_calls = 0
        self.preview_arrow_calls = []
        self.add_arrow_calls = []
        self.services = SimpleNamespace(
            hit_testing_service=SimpleNamespace(scene_pos_from_event=self.scene_pos_from_event),
            benzene_preview_service=SimpleNamespace(clear_preview=self.clear_benzene_preview),
            scene_decoration_service=SimpleNamespace(add_arrow=self.add_arrow),
            scene_decoration_build_service=SimpleNamespace(preview_arrow=self.preview_arrow),
        )

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def scene(self):
        return self.scene_obj

    def scene_pos_from_event(self, event):
        return event.position()

    def preview_arrow(self, start, end, arrow_type):
        self.preview_arrow_calls.append((QPointF(start), QPointF(end), arrow_type))
        return _PreviewItem(self.scene_obj)

    def add_arrow(self, start, end, arrow_type) -> None:
        self.add_arrow_calls.append((QPointF(start), QPointF(end), arrow_type))

    def clear_handles(self) -> None:
        self.clear_handles_calls += 1

    def clear_benzene_preview(self) -> None:
        self.clear_benzene_preview_calls += 1


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for additional tools tests")
class ToolsAdditionalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_text_tool_updates_existing_atom_and_creates_atom_from_dialog(self) -> None:
        canvas = _TextCanvas()
        tool = TextTool(canvas, context=_tool_context_for(canvas))
        tool.activate()

        self.assertEqual(canvas.drag_mode, canvas.DragMode.NoDrag)

        set_hover_atom_id_for(canvas, 1)
        canvas.tool_settings_state.atom_symbol = "N"
        self.assertTrue(tool.on_mouse_press(_Event(QPointF(1.0, 1.0))))
        self.assertEqual(canvas.label_calls[-1], (1, "N", True, True))

        set_hover_atom_id_for(canvas, None)
        set_hover_bond_id_for(canvas, 0)
        canvas.tool_settings_state.atom_symbol = "O"
        self.assertTrue(tool.on_mouse_press(_Event(QPointF(9.0, 0.0))))
        self.assertEqual(canvas.label_calls[-1], (2, "O", True, True))

        set_hover_bond_id_for(canvas, None)
        canvas.tool_settings_state.atom_symbol = " "
        canvas.find_atom_result = None
        with mock.patch.object(text_tool_module.QInputDialog, "getText", return_value=("Cl", True)):
            self.assertTrue(tool.on_mouse_press(_Event(QPointF(15.0, 25.0))))
        self.assertEqual(canvas.added_atoms[-1], ("Cl", 15.0, 25.0))
        self.assertEqual(canvas.label_calls[-1], (3, "Cl", True, False))
        self.assertIsInstance(canvas.pushed_commands[-1], AddAtomsCommand)
        command = canvas.pushed_commands[-1]
        self.assertEqual(command.before_next_atom_id, 3)
        self.assertEqual(command.after_next_atom_id, 4)
        self.assertEqual(command.before_smiles_input, "before")
        self.assertEqual(command.after_smiles_input, "before")

    def test_text_tool_handles_dialog_cancel_and_invalid_hover_bond_fallback(self) -> None:
        canvas = _TextCanvas()
        tool = TextTool(canvas, context=_tool_context_for(canvas))

        canvas.tool_settings_state.atom_symbol = " "
        with mock.patch.object(text_tool_module.QInputDialog, "getText", return_value=("ignored", False)):
            self.assertTrue(tool.on_mouse_press(_Event(QPointF(4.0, 5.0))))
        self.assertEqual(canvas.added_atoms, [])
        self.assertEqual(canvas.label_calls, [])
        self.assertEqual(canvas.pushed_commands, [])

        set_hover_bond_id_for(canvas, 99)
        canvas.bond_near = 0
        canvas.tool_settings_state.atom_symbol = "S"
        self.assertTrue(tool.on_mouse_press(_Event(QPointF(9.0, 0.0))))
        self.assertEqual(canvas.label_calls[-1], (2, "S", True, True))

        set_hover_bond_id_for(canvas, None)
        set_hover_atom_id_for(canvas, 1)
        canvas.tool_settings_state.atom_symbol = " "
        with mock.patch.object(text_tool_module.QInputDialog, "getText", return_value=("   ", True)):
            self.assertTrue(tool.on_mouse_press(_Event(QPointF(2.0, 2.0))))
        self.assertEqual(canvas.label_calls[-1], (1, "", True, True))

        set_hover_atom_id_for(canvas, None)
        canvas.bond_near = None
        canvas.find_atom_result = None
        canvas.tool_settings_state.atom_symbol = " "
        added_atoms_before = len(canvas.added_atoms)
        label_calls_before = len(canvas.label_calls)
        pushed_before = len(canvas.pushed_commands)
        with mock.patch.object(text_tool_module.QInputDialog, "getText", return_value=("   ", True)):
            self.assertTrue(tool.on_mouse_press(_Event(QPointF(20.0, 21.0))))
        self.assertEqual(len(canvas.added_atoms), added_atoms_before)
        self.assertEqual(len(canvas.label_calls), label_calls_before)
        self.assertEqual(len(canvas.pushed_commands), pushed_before)

    def test_text_tool_prefers_atom_label_service_over_canvas_wrapper(self) -> None:
        canvas = _TextCanvas()
        service_calls = []

        def service_add_or_update(atom_id: int, text: str, **kwargs) -> None:
            service_calls.append((atom_id, text, kwargs))
            canvas.model.atoms[atom_id].element = text

        canvas.services.atom_label_service = SimpleNamespace(add_or_update_atom_label=service_add_or_update)
        tool = TextTool(canvas, context=_tool_context_for(canvas))

        set_hover_atom_id_for(canvas, 1)
        canvas.tool_settings_state.atom_symbol = "N"
        self.assertTrue(tool.on_mouse_press(_Event(QPointF(1.0, 1.0))))

        set_hover_atom_id_for(canvas, None)
        canvas.tool_settings_state.atom_symbol = " "
        canvas.find_atom_result = None
        with mock.patch.object(text_tool_module.QInputDialog, "getText", return_value=("Cl", True)):
            self.assertTrue(tool.on_mouse_press(_Event(QPointF(15.0, 25.0))))

        self.assertEqual(canvas.label_calls, [])
        self.assertEqual(
            service_calls,
            [
                (1, "N", {"clear_smiles": True, "record": True, "allow_merge": True, "show_carbon": True}),
                (3, "Cl", {"clear_smiles": True, "record": False, "allow_merge": True, "show_carbon": True}),
            ],
        )

    def test_wrapper_only_tools_cover_false_and_noop_branches(self) -> None:
        text_canvas = _TextCanvas()
        text_tool = TextTool(text_canvas, context=_tool_context_for(text_canvas))
        self.assertFalse(text_tool.on_mouse_press(_Event(button=Qt.MouseButton.RightButton)))

        misc_canvas = _MiscCanvas()
        color_tool = ColorTool(misc_canvas, context=_tool_context_for(misc_canvas))
        flip_tool = FlipTool(misc_canvas, context=_tool_context_for(misc_canvas))
        edit_tool = EditBondTool(misc_canvas, context=_tool_context_for(misc_canvas))

        self.assertFalse(color_tool.on_mouse_press(_Event(button=Qt.MouseButton.RightButton)))
        color_tool.activate()
        self.assertTrue(color_tool.on_mouse_press(_Event(QPointF())))
        self.assertEqual(misc_canvas.colored, [])
        misc_canvas.scene_obj._selected_items = [_DataItem("atom", 1)]
        color_tool.set_color("not-a-color")
        self.assertTrue(color_tool.on_mouse_press(_Event(QPointF())))
        self.assertEqual(misc_canvas.colored, [])

        self.assertFalse(flip_tool.on_mouse_press(_Event(button=Qt.MouseButton.RightButton)))
        flip_tool.activate()
        self.assertTrue(flip_tool.on_mouse_press(_Event(QPointF())))
        misc_canvas.item = _DataItem("bond", "bad")
        self.assertTrue(flip_tool.on_mouse_press(_Event(QPointF())))
        self.assertEqual(misc_canvas.flipped, [])

        self.assertFalse(edit_tool.on_mouse_press(_Event(button=Qt.MouseButton.RightButton)))
        edit_tool.activate()
        misc_canvas.item = _DataItem("note", 3)
        misc_canvas.bond_id = None
        self.assertTrue(edit_tool.on_mouse_press(_Event(QPointF())))
        self.assertEqual(misc_canvas.cycled, [])

        note_canvas = _OrbitalMarkNoteCanvas()
        self.assertFalse(
            OrbitalTool(note_canvas, context=_tool_context_for(note_canvas)).on_mouse_press(
                _Event(button=Qt.MouseButton.RightButton)
            )
        )
        self.assertFalse(
            TransformTool(note_canvas, context=_tool_context_for(note_canvas)).on_mouse_press(
                _Event(button=Qt.MouseButton.RightButton)
            )
        )
        self.assertFalse(
            MarkTool(note_canvas, context=_tool_context_for(note_canvas)).on_mouse_press(
                _Event(button=Qt.MouseButton.RightButton)
            )
        )
        note_tool = NoteTool(note_canvas, context=_tool_context_for(note_canvas))
        self.assertFalse(note_tool.on_mouse_press(_Event(button=Qt.MouseButton.RightButton)))
        self.assertFalse(note_tool.on_mouse_move(_Event(QPointF())))

    def test_benzene_color_flip_and_edit_bond_tools_cover_simple_branches(self) -> None:
        benzene_canvas = SimpleNamespace(
            DragMode=SimpleNamespace(NoDrag="none"),
            drag_mode=None,
            preview_calls=[],
            add_calls=[],
            setDragMode=lambda mode: setattr(benzene_canvas, "drag_mode", mode),
            scene_pos_from_event=lambda event: event.position(),
            add_benzene_ring=lambda pos, attach_bond_id=None, attach_atom_id=None: benzene_canvas.add_calls.append(
                ("add", QPointF(pos), attach_bond_id if attach_bond_id is not None else attach_atom_id)
            ),
            services=SimpleNamespace(
                hit_testing_service=SimpleNamespace(scene_pos_from_event=lambda event: event.position()),
                structure_build_service=SimpleNamespace(
                    add_benzene_ring=lambda pos, *, attach_atom_id=None, attach_bond_id=None, before_smiles_input=None: benzene_canvas.add_calls.append(
                        ("add", QPointF(pos), attach_bond_id if attach_bond_id is not None else attach_atom_id)
                    )
                ),
                benzene_preview_service=SimpleNamespace(
                    clear_preview=lambda: benzene_canvas.add_calls.append(("clear", None, None)),
                    render_preview=lambda pos, attach_atom_id=None, attach_bond_id=None: benzene_canvas.preview_calls.append(
                        (QPointF(pos), attach_atom_id, attach_bond_id)
                    ),
                ),
            ),
        )
        set_hover_bond_id_for(benzene_canvas, 4)
        set_hover_atom_id_for(benzene_canvas, 7)
        benzene_tool = BenzeneTool(benzene_canvas, context=_tool_context_for(benzene_canvas))
        benzene_tool.activate()
        self.assertEqual(benzene_canvas.drag_mode, benzene_canvas.DragMode.NoDrag)
        self.assertEqual(benzene_canvas.add_calls, [("clear", None, None)])
        self.assertFalse(benzene_tool.on_mouse_press(_Event(button=Qt.MouseButton.RightButton)))
        self.assertFalse(benzene_tool.on_mouse_press(_Event(QPointF(2.0, 3.0))))
        self.assertEqual(benzene_canvas.add_calls, [("clear", None, None)])
        set_hover_bond_id_for(benzene_canvas, None)
        self.assertFalse(benzene_tool.on_mouse_move(_Event(QPointF(5.0, 6.0), buttons=Qt.MouseButton.NoButton)))
        self.assertEqual(benzene_canvas.preview_calls, [])
        self.assertFalse(benzene_tool.on_mouse_move(_Event(QPointF(5.0, 6.0), buttons=Qt.MouseButton.LeftButton)))

        misc_canvas = _MiscCanvas()
        color_tool = ColorTool(misc_canvas, context=_tool_context_for(misc_canvas))
        flip_tool = FlipTool(misc_canvas, context=_tool_context_for(misc_canvas))
        edit_tool = EditBondTool(misc_canvas, context=_tool_context_for(misc_canvas))
        target = _DataItem("bond", 11)
        misc_canvas.item = target
        misc_canvas.scene_obj._selected_items = [_DataItem("atom", 1), _DataItem("ring", 2), _DataItem("note", 3)]

        color_tool.activate()
        self.assertTrue(color_tool.on_mouse_press(_Event(QPointF())))
        self.assertEqual(misc_canvas.colored[-1][0], target)
        self.assertEqual(misc_canvas.color_batches[-1][0], [target])
        misc_canvas.item = None
        self.assertTrue(color_tool.on_mouse_press(_Event(QPointF())))
        self.assertEqual(len(misc_canvas.colored), 3)
        self.assertEqual(len(misc_canvas.color_batches), 2)
        self.assertEqual(len(misc_canvas.color_batches[-1][0]), 2)

        flip_tool.activate()
        misc_canvas.item = _DataItem("bond", 9)
        self.assertTrue(flip_tool.on_mouse_press(_Event(QPointF())))
        self.assertEqual(misc_canvas.flipped, [9])

        edit_tool.activate()
        misc_canvas.item = _DataItem("bond", 6)
        self.assertTrue(edit_tool.on_mouse_press(_Event(QPointF())))
        misc_canvas.item = None
        misc_canvas.bond_id = 8
        self.assertTrue(edit_tool.on_mouse_press(_Event(QPointF())))
        self.assertEqual(misc_canvas.cycled, [6, 8])

    def test_delete_tool_builds_composite_and_scene_item_delete_command(self) -> None:
        canvas = _DeleteCanvas()
        tool = DeleteTool(canvas, context=_tool_context_for(canvas))
        tool.activate()
        self.assertEqual(canvas.drag_mode, canvas.DragMode.NoDrag)
        self.assertFalse(tool.on_mouse_press(_Event(button=Qt.MouseButton.RightButton)))

        atom_item = _DataItem("atom", 3, scene_obj=canvas.scene())
        note_item = _DataItem("note", 7, scene_obj=canvas.scene())
        note_item.setData(9, {"kind": "note", "id": 7})
        canvas.item = atom_item
        self.assertTrue(tool.on_mouse_press(_Event(QPointF(1.0, 1.0))))
        canvas.item = note_item
        self.assertTrue(tool.on_mouse_move(_Event(QPointF(2.0, 2.0), buttons=Qt.MouseButton.LeftButton)))
        self.assertTrue(tool.on_mouse_release(_Event(QPointF(2.0, 2.0))))
        self.assertIsInstance(canvas.pushed_commands[-1], CompositeCommand)
        composite = canvas.pushed_commands[-1]
        self.assertIsInstance(composite.commands[0], SetSmilesInputCommand)
        self.assertTrue(any(isinstance(command, DeleteSceneItemsCommand) for command in composite.commands))
        self.assertEqual(canvas.deleted_atoms, [(3, False)])
        self.assertEqual(canvas.removed_items, [note_item])

    def test_delete_tool_release_noops_without_changes_and_wraps_single_delete(self) -> None:
        canvas = _DeleteCanvas()
        tool = DeleteTool(canvas, context=_tool_context_for(canvas))

        canvas.item = None
        self.assertTrue(tool.on_mouse_press(_Event(QPointF(1.0, 1.0))))
        self.assertTrue(tool.on_mouse_release(_Event(QPointF(1.0, 1.0))))
        self.assertEqual(canvas.pushed_commands, [])

        atom_item = _DataItem("atom", 5, scene_obj=canvas.scene())
        canvas.item = atom_item
        self.assertTrue(tool.on_mouse_press(_Event(QPointF(2.0, 2.0))))
        self.assertTrue(tool.on_mouse_release(_Event(QPointF(2.0, 2.0))))
        self.assertIsInstance(canvas.pushed_commands[-1], CompositeCommand)
        self.assertIsInstance(canvas.pushed_commands[-1].commands[0], SetSmilesInputCommand)
        self.assertEqual(canvas.pushed_commands[-1].commands[1], "atom-5")

    def test_misc_tool_guard_paths_cover_benzene_color_flip_edit_and_move_delete_edges(self) -> None:
        benzene_calls = []
        preview_calls = []
        clear_calls = []
        benzene_canvas = SimpleNamespace(
            DragMode=SimpleNamespace(NoDrag="none"),
            drag_mode=None,
            setDragMode=lambda mode: setattr(benzene_canvas, "drag_mode", mode),
            scene_pos_from_event=lambda event: event.position(),
            add_benzene_ring=lambda pos, attach_atom_id=None, attach_bond_id=None: benzene_calls.append(
                (QPointF(pos), attach_atom_id, attach_bond_id)
            ),
            services=SimpleNamespace(
                hit_testing_service=SimpleNamespace(scene_pos_from_event=lambda event: event.position()),
                structure_build_service=SimpleNamespace(
                    add_benzene_ring=lambda pos, *, attach_atom_id=None, attach_bond_id=None, before_smiles_input=None: benzene_calls.append(
                        (QPointF(pos), attach_atom_id, attach_bond_id)
                    )
                ),
                benzene_preview_service=SimpleNamespace(
                    clear_preview=lambda: clear_calls.append(True),
                    render_preview=lambda pos, attach_atom_id=None, attach_bond_id=None: preview_calls.append(
                        (QPointF(pos), attach_atom_id, attach_bond_id)
                    ),
                ),
            ),
        )
        set_hover_atom_id_for(benzene_canvas, 5)
        benzene_tool = BenzeneTool(benzene_canvas, context=_tool_context_for(benzene_canvas))
        benzene_tool.activate()
        self.assertEqual(clear_calls, [True])
        self.assertFalse(benzene_tool.on_mouse_press(_Event(button=Qt.MouseButton.RightButton)))
        self.assertFalse(benzene_tool.on_mouse_press(_Event(QPointF(1.0, 2.0))))
        set_hover_atom_id_for(benzene_canvas, None)
        self.assertFalse(benzene_tool.on_mouse_press(_Event(QPointF(3.0, 4.0))))
        set_hover_bond_id_for(benzene_canvas, 9)
        self.assertFalse(benzene_tool.on_mouse_move(_Event(QPointF(5.0, 6.0), buttons=Qt.MouseButton.LeftButton)))
        self.assertFalse(benzene_tool.on_mouse_move(_Event(QPointF(5.0, 6.0), buttons=Qt.MouseButton.NoButton)))
        self.assertEqual(benzene_calls, [])
        self.assertEqual(preview_calls, [])

        misc_canvas = _MiscCanvas()
        color_tool = ColorTool(misc_canvas, context=_tool_context_for(misc_canvas))
        flip_tool = FlipTool(misc_canvas, context=_tool_context_for(misc_canvas))
        edit_tool = EditBondTool(misc_canvas, context=_tool_context_for(misc_canvas))
        self.assertFalse(color_tool.on_mouse_press(_Event(button=Qt.MouseButton.RightButton)))
        misc_canvas.scene_obj._selected_items = []
        self.assertTrue(color_tool.on_mouse_press(_Event(QPointF())))
        misc_canvas.item = _DataItem("atom", 1)
        color_tool.set_color("not-a-color")
        self.assertTrue(color_tool.on_mouse_press(_Event(QPointF())))
        self.assertEqual(misc_canvas.colored, [])

        self.assertFalse(flip_tool.on_mouse_press(_Event(button=Qt.MouseButton.RightButton)))
        misc_canvas.item = None
        self.assertTrue(flip_tool.on_mouse_press(_Event(QPointF())))
        self.assertFalse(edit_tool.on_mouse_press(_Event(button=Qt.MouseButton.RightButton)))
        misc_canvas.bond_id = None
        self.assertTrue(edit_tool.on_mouse_press(_Event(QPointF())))
        self.assertEqual(misc_canvas.cycled, [])

        move_canvas = _MoveCanvas()
        move_tool = MoveTool(move_canvas, context=_tool_context_for(move_canvas))
        self.assertFalse(move_tool.on_mouse_press(_Event(button=Qt.MouseButton.RightButton)))
        move_canvas.selected_items_for_transform = [_DataItem("note", 1)]
        move_canvas.item = None
        with mock.patch.object(move_tool, "_begin_selection_drag", return_value=False):
            self.assertTrue(move_tool.on_mouse_press(_Event(QPointF(1.0, 1.0))))
        move_tool._start_pos = QPointF(0.0, 0.0)
        self.assertTrue(move_tool.on_mouse_move(_Event(QPointF(1.0, 1.0))))
        move_tool._drag_item = _DataItem("arrow", 2)
        move_tool._start_pos = QPointF(1.0, 1.0)
        move_tool._moved = True
        move_tool._total_delta = QPointF(3.0, 4.0)
        self.assertTrue(move_tool.on_mouse_release(_Event(QPointF(1.0, 1.0))))
        self.assertIsInstance(move_canvas.pushed_commands[-1], MoveItemsCommand)

        delete_canvas = _DeleteCanvas()
        delete_tool = DeleteTool(delete_canvas, context=_tool_context_for(delete_canvas))
        self.assertFalse(delete_tool.on_mouse_move(_Event(QPointF())))
        delete_tool._erasing = True
        self.assertFalse(delete_tool.on_mouse_move(_Event(QPointF(), buttons=Qt.MouseButton.NoButton)))
        delete_tool._changed = True
        delete_tool._commands = ["cmd"]
        delete_tool._before_smiles_input = "before"
        with mock.patch.object(edit_tools_module, "build_delete_tool_history_command", return_value=None):
            self.assertTrue(delete_tool.on_mouse_release(_Event(QPointF())))
        self.assertEqual(delete_canvas.pushed_commands, [])

        delete_canvas.item = _DataItem("note", 1, scene_obj=object())
        delete_canvas.item.setData(9, {"kind": "note", "id": 1})
        delete_tool._erase_at_event(_Event(QPointF()))
        self.assertEqual(delete_canvas.removed_items, [])

        class _RuntimeSceneItem:
            def scene(self):
                raise RuntimeError("disposed")

        delete_canvas.item = _RuntimeSceneItem()
        delete_tool._erase_at_event(_Event(QPointF()))

        delete_canvas.item = _DataItem("atom", 2, scene_obj=delete_canvas.scene())
        with mock.patch.object(edit_tools_module, "erase_delete_tool_item", return_value=(False, None)):
            delete_tool._erase_at_event(_Event(QPointF()))
        self.assertFalse(delete_tool._changed)

        with mock.patch.object(edit_tools_module, "erase_delete_tool_item", return_value=(True, None)):
            delete_tool._erase_at_event(_Event(QPointF()))
        self.assertTrue(delete_tool._changed)
        self.assertEqual(delete_tool._commands, [])

        perspective_canvas = _PerspectiveCanvas()
        perspective_tool = PerspectiveTool(perspective_canvas, context=_tool_context_for(perspective_canvas))
        self.assertTrue(perspective_tool.on_mouse_release(_Event(QPointF())))
        self.assertEqual(perspective_canvas.end_calls, 0)

    def test_note_tool_click_collapses_selection_double_click_selects_word(self) -> None:
        scene = QGraphicsScene()
        note = QGraphicsTextItem("Hello World")
        note.setData(0, "note")
        scene.addItem(note)

        center_y = note.boundingRect().center().y()
        context = SimpleNamespace(
            scene_pos_from_event=lambda _event: note.mapToScene(QPointF(2.0, center_y))
        )
        tool = NoteTool(SimpleNamespace(), context=context)

        cursor = note.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        note.setTextCursor(cursor)
        self.assertTrue(note.textCursor().hasSelection())

        press = SimpleNamespace(type=lambda: QEvent.Type.MouseButtonPress)
        tool._place_caret_in_note(note, press)
        # A single click drops the selection (caret only).
        self.assertFalse(note.textCursor().hasSelection())

        dbl = SimpleNamespace(type=lambda: QEvent.Type.MouseButtonDblClick)
        tool._place_caret_in_note(note, dbl)
        # A double click selects the word under the caret.
        self.assertTrue(note.textCursor().hasSelection())
        self.assertEqual(note.textCursor().selectedText(), "Hello")

    def test_orbital_transform_mark_and_note_tools_cover_mouse_press_paths(self) -> None:
        canvas = _OrbitalMarkNoteCanvas()

        orbital_tool = OrbitalTool(canvas, context=_tool_context_for(canvas))
        orbital_tool.activate()
        self.assertTrue(orbital_tool.on_mouse_press(_Event(QPointF(3.0, 4.0))))
        self.assertEqual(canvas.added_orbitals[-1], QPointF(3.0, 4.0))

        transform_tool = TransformTool(canvas, context=_tool_context_for(canvas))
        transform_tool.activate()
        canvas.item = None
        self.assertTrue(transform_tool.on_mouse_press(_Event(QPointF())))
        self.assertEqual(canvas.clear_handles_calls, 1)
        handle = _DataItem("handle", 1)
        canvas.item = handle
        self.assertTrue(transform_tool.on_mouse_press(_Event(QPointF())))
        self.assertIs(transform_tool._active_handle, handle)
        orbital_item = _DataItem("orbital", 2)
        curved_item = _DataItem("curved_single", 3)
        canvas.item = orbital_item
        self.assertTrue(transform_tool.on_mouse_press(_Event(QPointF())))
        canvas.item = curved_item
        self.assertTrue(transform_tool.on_mouse_press(_Event(QPointF())))
        canvas.item = _DataItem("note", 7)
        self.assertTrue(transform_tool.on_mouse_press(_Event(QPointF())))
        self.assertIsNone(transform_tool._active_handle)
        self.assertEqual(canvas.orbital_handles, [orbital_item])
        self.assertEqual(canvas.curved_handles, [curved_item])
        self.assertEqual(canvas.clear_handles_calls, 2)
        transform_tool._active_handle = handle
        transform_tool.deactivate()
        self.assertIsNone(transform_tool._active_handle)
        self.assertEqual(canvas.clear_handles_calls, 3)

        mark_tool = MarkTool(canvas, context=_tool_context_for(canvas))
        mark_tool.activate()
        canvas.atom_near = 5
        self.assertTrue(mark_tool.on_mouse_press(_Event(QPointF(8.0, 9.0))))
        canvas.atom_near = None
        self.assertTrue(mark_tool.on_mouse_press(_Event(QPointF(1.0, 2.0))))
        self.assertEqual(canvas.added_atom_marks[0][0], 5)
        self.assertEqual(canvas.added_marks[0], QPointF(1.0, 2.0))

        note_tool = NoteTool(canvas, context=_tool_context_for(canvas))
        note_tool.activate()
        note = _DataItem("note", 9)
        canvas.item = note
        self.assertTrue(note_tool.on_mouse_press(_Event(QPointF(), modifiers=Qt.KeyboardModifier.ControlModifier)))
        self.assertTrue(note_tool.on_mouse_press(_Event(QPointF(), modifiers=Qt.KeyboardModifier.ShiftModifier)))
        self.assertTrue(note_tool.on_mouse_press(_Event(QPointF())))
        canvas.item = None
        self.assertTrue(note_tool.on_mouse_press(_Event(QPointF(10.0, 11.0))))
        self.assertEqual(canvas.toggled_notes, [note])
        self.assertEqual(canvas.selected_notes[:2], [(note, True), (note, False)])
        self.assertEqual(canvas.clear_note_selection_calls, 1)
        self.assertEqual(canvas.added_notes[0][1], "")
        self.assertFalse(note_tool.on_mouse_release(_Event(QPointF())))

    def test_perspective_tool_rotation_entry_updates_state_on_success_and_failure(self) -> None:
        canvas = _PerspectiveCanvas()
        tool = PerspectiveTool(canvas, context=_tool_context_for(canvas))
        tool.activate()
        self.assertEqual(canvas.drag_mode, canvas.DragMode.RubberBandDrag)

        controller = perspective_tool_module._perspective_tool_controller_for(canvas, context=tool.context)
        self.assertIsInstance(controller, perspective_tool_module.PerspectiveToolController)
        self.assertIs(controller.canvas, canvas)

        canvas.toggle_result = True
        self.assertTrue(tool.on_mouse_press(_Event(QPointF(1.0, 1.0), modifiers=Qt.KeyboardModifier.ShiftModifier)))
        canvas.toggle_result = False

        bond_item = _DataItem("bond", 12)
        canvas.preferred_item = bond_item
        self.assertTrue(tool.on_mouse_press(_Event(QPointF(2.0, 3.0))))
        self.assertEqual(canvas.begin_calls[-1][0], 12)
        self.assertTrue(tool._rotating)
        self.assertEqual(tool._last_pos, QPointF(2.0, 3.0))

        self.assertTrue(tool.on_mouse_move(_Event(QPointF(8.0, 4.0), modifiers=Qt.KeyboardModifier.ShiftModifier)))
        self.assertEqual(canvas.update_calls[-1], (6.0, 0.0))
        self.assertEqual(tool._axis_lock, "x")
        self.assertTrue(tool.on_mouse_move(_Event(QPointF(10.0, 7.0))))
        self.assertEqual(canvas.update_calls[-1], (2.0, 3.0))
        self.assertIsNone(tool._axis_lock)
        self.assertTrue(tool.on_mouse_release(_Event(QPointF())))
        self.assertEqual(canvas.end_calls, 1)
        self.assertFalse(tool._rotating)
        self.assertIsNone(tool._last_pos)

        canvas.begin_rotation_result = False
        self.assertFalse(tool.on_mouse_press(_Event(QPointF(6.0, 7.0))))
        self.assertFalse(tool._rotating)
        self.assertIsNone(tool._last_pos)

        self.assertFalse(tool.on_mouse_press(_Event(QPointF(0.0, 0.0), button=Qt.MouseButton.RightButton)))
        self.assertFalse(tool.on_mouse_move(_Event(QPointF(0.0, 0.0))))
        canvas.begin_rotation_result = True
        self.assertTrue(tool.on_mouse_press(_Event(QPointF(3.0, 3.0), modifiers=Qt.KeyboardModifier.ShiftModifier)))
        self.assertEqual(canvas.begin_calls[-1][1], QPointF(3.0, 3.0))
        self.assertTrue(tool.on_mouse_move(_Event(QPointF(3.0, 3.0), modifiers=Qt.KeyboardModifier.ShiftModifier)))
        self.assertEqual(canvas.update_calls[-1], (2.0, 3.0))

        tool.deactivate()
        self.assertFalse(tool._rotating)

        controller_canvas = _ControllerCanvas()
        controller = ToolController(
            controller_canvas,
            hit_testing_service=SimpleNamespace(),
            selection_controller=SimpleNamespace(),
            note_controller=SimpleNamespace(create_text_note=mock.Mock(), begin_note_edit=mock.Mock()),
            handle_controller=SimpleNamespace(update_handle_drag=mock.Mock()),
            selection_rotation_controller=SimpleNamespace(
                begin_selection_3d_rotation=mock.Mock(return_value=False),
                update_selection_3d_rotation=mock.Mock(),
                end_selection_3d_rotation=mock.Mock(),
            ),
            scene_transform_controller=SimpleNamespace(
                apply_bond_style=mock.Mock(),
                cycle_bond_style=mock.Mock(),
                flip_bond_direction=mock.Mock(),
            ),
            set_drag_mode=controller_canvas.setDragMode,
            rubber_band_drag_mode=controller_canvas.DragMode.RubberBandDrag,
        )
        controller.set_active("benzene")
        controller.set_active("missing")
        self.assertEqual(controller_canvas.clear_benzene_preview_calls, 2)
        self.assertEqual(controller_canvas.drag_mode, controller_canvas.DragMode.RubberBandDrag)

    def test_tool_controller_switch_cleans_arrow_preview(self) -> None:
        canvas = _ToolControllerPreviewCanvas()
        controller = ToolController(
            canvas,
            hit_testing_service=canvas.services.hit_testing_service,
            selection_controller=SimpleNamespace(),
            note_controller=SimpleNamespace(create_text_note=mock.Mock(), begin_note_edit=mock.Mock()),
            handle_controller=SimpleNamespace(update_handle_drag=mock.Mock()),
            selection_rotation_controller=SimpleNamespace(
                begin_selection_3d_rotation=mock.Mock(return_value=False),
                update_selection_3d_rotation=mock.Mock(),
                end_selection_3d_rotation=mock.Mock(),
            ),
            scene_transform_controller=SimpleNamespace(
                apply_bond_style=mock.Mock(),
                cycle_bond_style=mock.Mock(),
                flip_bond_direction=mock.Mock(),
            ),
            set_drag_mode=canvas.setDragMode,
            rubber_band_drag_mode=canvas.DragMode.RubberBandDrag,
        )

        controller.set_active("arrow")
        arrow_tool = controller.tools["arrow"]
        self.assertTrue(controller.active.on_mouse_press(_Event(QPointF(1.0, 2.0))))
        self.assertTrue(controller.active.on_mouse_move(_Event(QPointF(3.0, 4.0))))
        self.assertIsNotNone(arrow_tool._preview_item)
        self.assertIsNotNone(arrow_tool._start_pos)

        controller.set_active("note")
        self.assertIsNone(arrow_tool._preview_item)
        self.assertIsNone(arrow_tool._start_pos)
        self.assertEqual(len(canvas.scene_obj.removed_items), 1)


if __name__ == "__main__":
    unittest.main()
