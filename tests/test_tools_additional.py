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
    from core.history import AddAtomsCommand, CompositeCommand, DeleteSceneItemsCommand, SetSmilesInputCommand
    from core.model import Atom, Bond, MoleculeModel
    from core.tools import (
        BenzeneTool,
        ColorTool,
        DeleteTool,
        EditBondTool,
        FlipTool,
        MarkTool,
        NoteTool,
        OrbitalTool,
        PerspectiveTool,
        TextTool,
        ToolController,
        TransformTool,
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
        self.symbol = ""
        self.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("O", 10.0, 0.0),
            },
            bonds=[Bond(1, 2, 1)],
        )
        self.last_smiles_input = "before"
        self.added_atoms = []
        self.label_calls = []
        self.pushed_commands = []

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def scene_pos_from_event(self, event):
        return event.position()

    def item_at_event(self, event):
        return self.item

    def _find_bond_near(self, pos, radius):
        return self.bond_near

    def find_atom_near(self, x, y, radius):
        return self.find_atom_result

    def get_atom_symbol(self):
        return self.symbol

    def add_atom(self, element: str, x: float, y: float) -> int:
        self.added_atoms.append((element, x, y))
        return self.model.add_atom(element, x, y)

    def add_or_update_atom_label(self, atom_id: int, text: str, show_carbon: bool = False, record: bool = True) -> None:
        self.label_calls.append((atom_id, text, show_carbon, record))
        self.model.atoms[atom_id].element = text

    def _atom_state_dict(self, atom_id: int) -> dict:
        atom = self.model.atoms[atom_id]
        return {"element": atom.element, "x": atom.x, "y": atom.y}

    def _push_command(self, command) -> None:
        self.pushed_commands.append(command)


class _MiscCanvas:
    DragMode = SimpleNamespace(NoDrag="none")

    def __init__(self) -> None:
        self.drag_mode = None
        self.renderer = SimpleNamespace(style=SimpleNamespace(atom_color="#224466"))
        self.scene_obj = _Scene()
        self.item = None
        self.colored = []
        self.flipped = []
        self.cycled = []
        self.bond_id = None

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def item_at_event(self, event):
        return self.item

    def scene(self):
        return self.scene_obj

    def apply_color_to_item(self, item, color) -> None:
        self.colored.append((item, color.name()))

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
        self.last_smiles_input = "before"
        self.deleted_atoms = []
        self.deleted_bonds = []
        self.deleted_rings = []
        self.removed_items = []
        self.pushed_commands = []

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

    def scene_item_state(self, item) -> dict:
        return {"kind": item.data(0), "id": item.data(1)}

    def remove_scene_item(self, item) -> None:
        self.removed_items.append(item)

    def _push_command(self, command) -> None:
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

    def add_mark_for_atom(self, atom_id: int, pos) -> None:
        self.added_atom_marks.append((atom_id, QPointF(pos)))

    def add_mark(self, pos) -> None:
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
        self._rotation_mode = "rigid"
        self.clear_handles_calls = 0
        self.selection_targets = []
        self.begin_calls = []
        self.update_calls = []
        self.end_calls = 0

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

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def _clear_benzene_preview(self) -> None:
        self.clear_benzene_preview_calls += 1

    def scene(self):
        return object()


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for additional tools tests")
class ToolsAdditionalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_text_tool_updates_existing_atom_and_creates_atom_from_dialog(self) -> None:
        canvas = _TextCanvas()
        tool = TextTool(canvas)
        tool.activate()

        self.assertEqual(canvas.drag_mode, canvas.DragMode.NoDrag)

        canvas.hover_atom_id = 1
        canvas.symbol = "N"
        self.assertTrue(tool.on_mouse_press(_Event(QPointF(1.0, 1.0))))
        self.assertEqual(canvas.label_calls[-1], (1, "N", True, True))

        canvas.hover_atom_id = None
        canvas.hover_bond_id = 0
        canvas.symbol = "O"
        self.assertTrue(tool.on_mouse_press(_Event(QPointF(9.0, 0.0))))
        self.assertEqual(canvas.label_calls[-1], (2, "O", True, True))

        canvas.hover_bond_id = None
        canvas.symbol = " "
        canvas.find_atom_result = None
        with mock.patch.object(tools_module.QInputDialog, "getText", return_value=("Cl", True)):
            self.assertTrue(tool.on_mouse_press(_Event(QPointF(15.0, 25.0))))
        self.assertEqual(canvas.added_atoms[-1], ("Cl", 15.0, 25.0))
        self.assertEqual(canvas.label_calls[-1], (3, "Cl", True, False))
        self.assertIsInstance(canvas.pushed_commands[-1], AddAtomsCommand)

    def test_benzene_color_flip_and_edit_bond_tools_cover_simple_branches(self) -> None:
        benzene_canvas = SimpleNamespace(
            DragMode=SimpleNamespace(NoDrag="none"),
            drag_mode=None,
            hover_bond_id=4,
            hover_atom_id=7,
            preview_calls=[],
            add_calls=[],
            setDragMode=lambda mode: setattr(benzene_canvas, "drag_mode", mode),
            _clear_benzene_preview=lambda: benzene_canvas.add_calls.append(("clear", None, None)),
            scene_pos_from_event=lambda event: event.position(),
            add_benzene_ring=lambda pos, attach_bond_id=None, attach_atom_id=None: benzene_canvas.add_calls.append(
                ("add", QPointF(pos), attach_bond_id if attach_bond_id is not None else attach_atom_id)
            ),
            _render_benzene_preview=lambda pos, attach_atom_id=None, attach_bond_id=None: benzene_canvas.preview_calls.append(
                (QPointF(pos), attach_atom_id, attach_bond_id)
            ),
        )
        benzene_tool = BenzeneTool(benzene_canvas)
        benzene_tool.activate()
        self.assertEqual(benzene_canvas.drag_mode, benzene_canvas.DragMode.NoDrag)
        self.assertFalse(benzene_tool.on_mouse_press(_Event(button=Qt.MouseButton.RightButton)))
        self.assertTrue(benzene_tool.on_mouse_press(_Event(QPointF(2.0, 3.0))))
        self.assertEqual(benzene_canvas.add_calls[-2][2], 4)
        benzene_canvas.hover_bond_id = None
        self.assertTrue(benzene_tool.on_mouse_move(_Event(QPointF(5.0, 6.0), buttons=Qt.MouseButton.NoButton)))
        self.assertEqual(benzene_canvas.preview_calls[-1][1], 7)
        self.assertFalse(benzene_tool.on_mouse_move(_Event(QPointF(5.0, 6.0), buttons=Qt.MouseButton.LeftButton)))

        misc_canvas = _MiscCanvas()
        color_tool = ColorTool(misc_canvas)
        flip_tool = FlipTool(misc_canvas)
        edit_tool = EditBondTool(misc_canvas)
        target = _DataItem("bond", 11)
        misc_canvas.item = target
        misc_canvas.scene_obj._selected_items = [_DataItem("atom", 1), _DataItem("ring", 2), _DataItem("note", 3)]

        color_tool.activate()
        self.assertTrue(color_tool.on_mouse_press(_Event(QPointF())))
        self.assertEqual(misc_canvas.colored[-1][0], target)
        misc_canvas.item = None
        self.assertTrue(color_tool.on_mouse_press(_Event(QPointF())))
        self.assertEqual(len(misc_canvas.colored), 3)

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
        tool = DeleteTool(canvas)
        tool.activate()
        self.assertEqual(canvas.drag_mode, canvas.DragMode.NoDrag)
        self.assertFalse(tool.on_mouse_press(_Event(button=Qt.MouseButton.RightButton)))

        atom_item = _DataItem("atom", 3, scene_obj=canvas.scene())
        note_item = _DataItem("note", 7, scene_obj=canvas.scene())
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

    def test_orbital_transform_mark_and_note_tools_cover_mouse_press_paths(self) -> None:
        canvas = _OrbitalMarkNoteCanvas()

        orbital_tool = OrbitalTool(canvas)
        orbital_tool.activate()
        self.assertTrue(orbital_tool.on_mouse_press(_Event(QPointF(3.0, 4.0))))
        self.assertEqual(canvas.added_orbitals[-1], QPointF(3.0, 4.0))

        transform_tool = TransformTool(canvas)
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
        self.assertEqual(canvas.orbital_handles, [orbital_item])
        self.assertEqual(canvas.curved_handles, [curved_item])

        mark_tool = MarkTool(canvas)
        mark_tool.activate()
        canvas.atom_near = 5
        self.assertTrue(mark_tool.on_mouse_press(_Event(QPointF(8.0, 9.0))))
        canvas.atom_near = None
        self.assertTrue(mark_tool.on_mouse_press(_Event(QPointF(1.0, 2.0))))
        self.assertEqual(canvas.added_atom_marks[0][0], 5)
        self.assertEqual(canvas.added_marks[0], QPointF(1.0, 2.0))

        note_tool = NoteTool(canvas)
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
        tool = PerspectiveTool(canvas)
        tool.activate()
        self.assertEqual(canvas.drag_mode, canvas.DragMode.RubberBandDrag)

        controller = tools_module._perspective_tool_controller_for(canvas)
        self.assertIsInstance(controller, tools_module.PerspectiveToolController)
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
        self.assertTrue(tool.on_mouse_release(_Event(QPointF())))
        self.assertEqual(canvas.end_calls, 1)
        self.assertFalse(tool._rotating)
        self.assertIsNone(tool._last_pos)

        canvas.begin_rotation_result = False
        self.assertFalse(tool.on_mouse_press(_Event(QPointF(6.0, 7.0))))
        self.assertFalse(tool._rotating)
        self.assertIsNone(tool._last_pos)

        tool.deactivate()
        self.assertFalse(tool._rotating)

        controller_canvas = _ControllerCanvas()
        controller = ToolController(controller_canvas)
        controller.set_active("benzene")
        controller.set_active("missing")
        self.assertEqual(controller_canvas.clear_benzene_preview_calls, 2)
        self.assertEqual(controller_canvas.drag_mode, controller_canvas.DragMode.RubberBandDrag)


if __name__ == "__main__":
    unittest.main()
