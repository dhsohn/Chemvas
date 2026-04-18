import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QColor, QFont, QPolygonF
    from PyQt6.QtWidgets import QApplication, QGraphicsPathItem, QGraphicsScene, QGraphicsTextItem
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.history import (
        AddAtomsCommand,
        AddBondCommand,
        AddSceneItemsCommand,
        ChangeAtomLabelCommand,
        CompositeCommand,
        DeleteAtomsCommand,
        DeleteBondCommand,
        UpdateAtomColorCommand,
        UpdateBondCommand,
        UpdateSceneItemCommand,
    )
    from core.model import Atom, Bond, MoleculeModel
    from ui.canvas_view import CanvasView


class _FakeCommand:
    def __init__(self) -> None:
        self.undo_calls = 0
        self.redo_calls = 0

    def undo(self, canvas) -> None:
        self.undo_calls += 1

    def redo(self, canvas) -> None:
        self.redo_calls += 1


class _FakeScene:
    def __init__(self, selected_items=None, items_at_pos=None) -> None:
        self._selected_items = list(selected_items or [])
        self._items_at_pos = list(items_at_pos or [])
        self.removed_items = []
        self.clear_selection_calls = 0
        self.focus_item = None

    def selectedItems(self):
        return list(self._selected_items)

    def items(self, *args, **kwargs):
        return list(self._items_at_pos)

    def clear(self) -> None:
        self._selected_items = []
        self._items_at_pos = []

    def clearSelection(self) -> None:
        self.clear_selection_calls += 1
        for item in self._selected_items:
            if hasattr(item, "setSelected"):
                item.setSelected(False)

    def removeItem(self, item) -> None:
        self.removed_items.append(item)

    def setFocusItem(self, item) -> None:
        self.focus_item = item


class _FakeItem:
    def __init__(
        self,
        kind,
        *,
        data1=None,
        data2=None,
        scene_token=None,
        children=None,
        polygon=None,
    ) -> None:
        self._data = {0: kind, 1: data1, 2: data2}
        self._scene_token = scene_token
        self._children = list(children or [])
        self._polygon = polygon
        self._selected = False

    def data(self, key):
        return self._data.get(key)

    def childItems(self):
        return list(self._children)

    def scene(self):
        return self._scene_token

    def polygon(self):
        return self._polygon

    def setSelected(self, selected: bool) -> None:
        self._selected = bool(selected)

    def isSelected(self) -> bool:
        return self._selected


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewAdditionalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_history_stack_and_tool_selection_helpers(self) -> None:
        first = _FakeCommand()
        second = _FakeCommand()
        third = _FakeCommand()
        history_view = SimpleNamespace(
            _history_enabled=True,
            _history=[],
            _history_limit=2,
            _redo_stack=["stale"],
        )

        CanvasView._push_command(history_view, first)
        CanvasView._push_command(history_view, second)
        history_view._redo_stack = ["stale"]
        CanvasView._push_command(history_view, third)

        self.assertEqual(history_view._history, [second, third])
        self.assertEqual(history_view._redo_stack, [])

        disabled_view = SimpleNamespace(
            _history_enabled=False,
            _history=[],
            _history_limit=2,
            _redo_stack=["redo"],
        )
        CanvasView._push_command(disabled_view, first)
        self.assertEqual(disabled_view._history, [])
        self.assertEqual(disabled_view._redo_stack, ["redo"])

        undo_redo_view = SimpleNamespace(_history=[first], _redo_stack=[])
        CanvasView.undo(undo_redo_view)
        self.assertEqual(first.undo_calls, 1)
        self.assertEqual(undo_redo_view._history, [])
        self.assertEqual(undo_redo_view._redo_stack, [first])

        CanvasView.redo(undo_redo_view)
        self.assertEqual(first.redo_calls, 1)
        self.assertEqual(undo_redo_view._history, [first])
        self.assertEqual(undo_redo_view._redo_stack, [])

        noop_view = SimpleNamespace(_history=[], _redo_stack=[])
        CanvasView.undo(noop_view)
        CanvasView.redo(noop_view)

        tool_view = SimpleNamespace(
            tools=SimpleNamespace(set_active=mock.Mock()),
            _update_selection_outline=mock.Mock(),
            _notify_tool_change=mock.Mock(),
            _refresh_hover_from_cursor=mock.Mock(),
            mark_kind="plus",
        )
        CanvasView.set_tool(tool_view, "bond")
        CanvasView.set_mark_kind(tool_view, "minus")
        CanvasView.set_mark_kind(tool_view, "unsupported")

        tool_view.tools.set_active.assert_any_call("bond")
        tool_view.tools.set_active.assert_any_call("mark")
        self.assertEqual(tool_view.mark_kind, "minus")
        self.assertEqual(tool_view._update_selection_outline.call_count, 2)
        self.assertEqual(tool_view._notify_tool_change.call_count, 2)
        self.assertEqual(tool_view._refresh_hover_from_cursor.call_count, 2)

    def test_service_and_scene_item_wrappers_delegate(self) -> None:
        scene_item_controller = mock.Mock()
        structure_insert_service = mock.Mock()
        selection_rotation_controller = mock.Mock()
        atom_label_service = mock.Mock()
        model = object()
        structure_insert_service.insert_structure_model.return_value = ({1}, {2})
        selection_rotation_controller.begin_selection_3d_rotation.return_value = True
        scene_item_controller._restore_ring_from_state.return_value = "ring"
        scene_item_controller._restore_note_from_state.return_value = "note"
        scene_item_controller._restore_mark_from_state.return_value = "mark"
        scene_item_controller._restore_arrow_from_state.return_value = "arrow"
        scene_item_controller._restore_ts_bracket_from_state.return_value = "ts"
        scene_item_controller._restore_orbital_from_state.return_value = "orbital"
        scene_item_controller.create_scene_item_from_state.return_value = "item"
        scene_item_controller._bond_ids_for_ring_item.return_value = {9}

        view = SimpleNamespace(
            _structure_insert_service=structure_insert_service,
            _selection_rotation_controller=selection_rotation_controller,
            _atom_label_service=atom_label_service,
            _scene_item_controller=scene_item_controller,
            _mark_center=lambda item: QPointF(1.0, 2.0),
        )

        result = CanvasView.insert_structure_model(
            view,
            model=model,
            center=QPointF(3.0, 4.0),
            title="Inserted",
        )
        self.assertEqual(result, ({1}, {2}))
        self.assertEqual(CanvasView.scene_item_state(view, None), {})
        self.assertEqual(CanvasView._restore_ring_from_state(view, {"kind": "ring"}), "ring")
        self.assertEqual(CanvasView._restore_note_from_state(view, {"kind": "note"}), "note")
        self.assertEqual(CanvasView._restore_mark_from_state(view, {"kind": "mark"}), "mark")
        self.assertEqual(CanvasView._restore_arrow_from_state(view, {"kind": "arrow"}), "arrow")
        self.assertEqual(CanvasView._restore_ts_bracket_from_state(view, {"kind": "ts"}), "ts")
        self.assertEqual(CanvasView._restore_orbital_from_state(view, {"kind": "orbital"}), "orbital")
        self.assertEqual(CanvasView.create_scene_item_from_state(view, {"kind": "note"}), "item")
        self.assertEqual(CanvasView._bond_ids_for_ring_item(view, "ring-item"), {9})
        CanvasView._refresh_bond_geometry_for_ring_item(view, "ring-item")
        CanvasView.restore_scene_item(view, "scene-item")
        CanvasView.remove_scene_item(view, "scene-item")
        CanvasView.apply_scene_item_state(view, "scene-item", {"kind": "note"})

        self.assertTrue(CanvasView.begin_selection_3d_rotation(view, axis_hint=7, press_pos=QPointF(1.0, 2.0)))
        CanvasView.update_selection_3d_rotation(view, 3.0, -4.0)
        CanvasView.end_selection_3d_rotation(view)
        self.assertEqual(CanvasView._merge_overlapping_atoms(view, 3), atom_label_service.merge_overlapping_atoms.return_value)
        CanvasView.add_or_update_atom_label(
            view,
            5,
            "N",
            clear_smiles=False,
            record=False,
            allow_merge=False,
            show_carbon=True,
        )

        structure_insert_service.insert_structure_model.assert_called_once_with(
            model,
            center=QPointF(3.0, 4.0),
            title="Inserted",
        )
        selection_rotation_controller.begin_selection_3d_rotation.assert_called_once_with(
            axis_hint=7,
            press_pos=QPointF(1.0, 2.0),
        )
        selection_rotation_controller.update_selection_3d_rotation.assert_called_once_with(3.0, -4.0)
        selection_rotation_controller.end_selection_3d_rotation.assert_called_once_with()
        atom_label_service.merge_overlapping_atoms.assert_called_once_with(3)
        atom_label_service.add_or_update_atom_label.assert_called_once_with(
            5,
            "N",
            clear_smiles=False,
            record=False,
            allow_merge=False,
            show_carbon=True,
        )
        scene_item_controller._refresh_bond_geometry_for_ring_item.assert_called_once_with("ring-item")
        scene_item_controller.restore_scene_item.assert_called_once_with("scene-item")
        scene_item_controller.remove_scene_item.assert_called_once_with("scene-item")
        scene_item_controller.apply_scene_item_state.assert_called_once_with("scene-item", {"kind": "note"})

    def test_clear_and_prompt_atom_label_use_atom_label_service(self) -> None:
        atom_label_service = mock.Mock()
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0, explicit_label=False),
                    2: Atom("O", 1.0, 0.0, explicit_label=True),
                }
            ),
            _atom_label_service=atom_label_service,
        )

        CanvasView.clear_atom_label(view, 1)
        with mock.patch("ui.canvas_view.QInputDialog.getText", side_effect=[(" N ", True), ("   ", True)]):
            CanvasView.prompt_atom_label(view, 2)
            CanvasView.prompt_atom_label(view, 1)

        atom_label_service.add_or_update_atom_label.assert_has_calls(
            [
                mock.call(1, "C", show_carbon=False),
                mock.call(2, "N", show_carbon=True),
                mock.call(1, "C", show_carbon=False),
            ]
        )

    def test_structure_build_wrappers_delegate(self) -> None:
        structure_build_service = mock.Mock()
        structure_build_service.add_atom_with_merge.return_value = 7
        structure_build_service.add_ring_from_points.return_value = [1, 2, 3]
        structure_build_service.add_linear_chain.return_value = [4, 5]
        structure_build_service.add_bond_between_points.return_value = (8, 9)
        structure_build_service.benzene_ring_points.return_value = ([QPointF(6.0, 7.0)], [(1, 0.0, 0.0)])
        view = SimpleNamespace(_structure_build_service=structure_build_service)

        CanvasView._add_regular_ring_template(view, 6)
        CanvasView._add_hetero_ring_template(view, 5, ["O", "C", "C", "C", "C"])
        CanvasView._add_fused_benzenes(view, 3, mode="angled")
        CanvasView._add_crown_ether(view, 18, 6)
        self.assertEqual(CanvasView._add_ring_from_points(view, ["p"], elements=["N"], merge=["m"]), [1, 2, 3])
        self.assertEqual(CanvasView._add_atom_with_merge(view, QPointF(1.0, 2.0), "Cl", []), 7)
        self.assertEqual(CanvasView._add_linear_chain(view, ["a"], ["C"], []), [4, 5])
        self.assertEqual(
            CanvasView._add_bond_between_points(view, QPointF(0.0, 0.0), QPointF(1.0, 0.0), "double", 2),
            (8, 9),
        )
        self.assertEqual(
            CanvasView._benzene_ring_points(view, QPointF(2.0, 3.0), attach_atom_id=1, attach_bond_id=2),
            ([QPointF(6.0, 7.0)], [(1, 0.0, 0.0)]),
        )
        CanvasView._sprout_bond_from_atom(view, 4, "double", 2, cyclic=True)
        CanvasView._sprout_benzene_from_atom(view, 6)
        CanvasView._sprout_acetyl_from_atom(view, 8)
        CanvasView._sprout_regular_ring_from_atom(view, 5, 6)
        CanvasView._fuse_benzene_to_bond(view, 3)
        CanvasView._fuse_regular_ring_to_bond(view, 7, 5)
        CanvasView._fuse_chair_to_bond(view, 9, mirrored=True)
        CanvasView.add_benzene_ring(view, QPointF(3.0, 4.0), attach_atom_id=1, attach_bond_id=2, before_smiles_input="before")
        CanvasView._render_model(view)

        structure_build_service.add_regular_ring_template.assert_called_once_with(6)
        structure_build_service.add_hetero_ring_template.assert_called_once_with(5, ["O", "C", "C", "C", "C"])
        structure_build_service.add_fused_benzenes.assert_called_once_with(3, mode="angled")
        structure_build_service.add_crown_ether.assert_called_once_with(18, 6)
        structure_build_service.add_ring_from_points.assert_called_once_with(["p"], elements=["N"], merge=["m"])
        structure_build_service.add_atom_with_merge.assert_called_once()
        structure_build_service.add_linear_chain.assert_called_once_with(["a"], ["C"], [])
        structure_build_service.add_bond_between_points.assert_called_once_with(
            QPointF(0.0, 0.0),
            QPointF(1.0, 0.0),
            "double",
            2,
        )
        structure_build_service.benzene_ring_points.assert_called_once_with(
            QPointF(2.0, 3.0),
            attach_atom_id=1,
            attach_bond_id=2,
        )
        structure_build_service.sprout_bond_from_atom.assert_called_once_with(4, style="double", order=2, cyclic=True)
        structure_build_service.sprout_benzene_from_atom.assert_called_once_with(6)
        structure_build_service.sprout_acetyl_from_atom.assert_called_once_with(8)
        structure_build_service.sprout_regular_ring_from_atom.assert_called_once_with(5, 6)
        structure_build_service.fuse_benzene_to_bond.assert_called_once_with(3)
        structure_build_service.fuse_regular_ring_to_bond.assert_called_once_with(7, 5)
        structure_build_service.fuse_chair_to_bond.assert_called_once_with(9, mirrored=True)
        structure_build_service.add_benzene_ring.assert_called_once_with(
            QPointF(3.0, 4.0),
            attach_atom_id=1,
            attach_bond_id=2,
            before_smiles_input="before",
        )
        structure_build_service.render_model.assert_called_once_with()

    def test_benzene_preview_wrappers_delegate(self) -> None:
        benzene_preview_service = mock.Mock()
        view = SimpleNamespace(_benzene_preview_service=benzene_preview_service)

        CanvasView._clear_benzene_preview(view)
        CanvasView._render_benzene_preview(view, QPointF(2.0, 3.0), attach_atom_id=1, attach_bond_id=2)

        benzene_preview_service.clear_preview.assert_called_once_with()
        benzene_preview_service.render_preview.assert_called_once_with(
            QPointF(2.0, 3.0),
            attach_atom_id=1,
            attach_bond_id=2,
        )

    def test_bond_hover_preview_wrappers_delegate(self) -> None:
        bond_hover_preview_service = mock.Mock()
        bond = object()
        view = SimpleNamespace(_bond_hover_preview_service=bond_hover_preview_service)

        CanvasView._add_bond_style_hover_preview(view, bond)
        CanvasView._add_bond_tool_hover_preview(view, 3, QPointF(4.0, 5.0))

        bond_hover_preview_service.add_bond_style_hover_preview.assert_called_once_with(bond)
        bond_hover_preview_service.add_bond_tool_hover_preview.assert_called_once_with(3, QPointF(4.0, 5.0))

    def test_scene_decoration_wrappers_delegate(self) -> None:
        decoration_service = mock.Mock()
        decoration_service.add_mark.return_value = "mark"
        decoration_service.add_arrow.return_value = "arrow"
        decoration_service.add_ts_bracket.return_value = "ts"
        decoration_service.add_orbital.return_value = "orbital"
        view = SimpleNamespace(_scene_decoration_service=decoration_service)

        self.assertEqual(
            CanvasView.add_mark(
                view,
                QPointF(1.0, 2.0),
                kind="plus",
                atom_id=5,
                offset=QPointF(0.5, -0.5),
                record=False,
            ),
            "mark",
        )
        self.assertEqual(
            CanvasView.add_arrow(view, QPointF(0.0, 0.0), QPointF(4.0, 5.0), "reaction"),
            "arrow",
        )
        self.assertEqual(
            CanvasView.add_ts_bracket(view, QRectF(QPointF(0.0, 0.0), QPointF(3.0, 6.0))),
            "ts",
        )
        self.assertEqual(CanvasView.add_orbital(view, QPointF(9.0, 8.0)), "orbital")

        decoration_service.add_mark.assert_called_once_with(
            QPointF(1.0, 2.0),
            kind="plus",
            atom_id=5,
            offset=QPointF(0.5, -0.5),
            record=False,
        )
        decoration_service.add_arrow.assert_called_once_with(
            QPointF(0.0, 0.0),
            QPointF(4.0, 5.0),
            "reaction",
        )
        decoration_service.add_ts_bracket.assert_called_once_with(
            QRectF(QPointF(0.0, 0.0), QPointF(3.0, 6.0)),
        )
        decoration_service.add_orbital.assert_called_once_with(QPointF(9.0, 8.0))

    def test_fragment_template_public_methods_use_recorded_build_helper(self) -> None:
        structure_build_service = SimpleNamespace(
            run_recorded_build=mock.Mock(side_effect=lambda action, **kwargs: action()),
        )
        view = SimpleNamespace(
            _structure_build_service=structure_build_service,
            _add_regular_ring_template=mock.Mock(),
            _add_hetero_ring_template=mock.Mock(),
            _add_fused_benzenes=mock.Mock(),
            _add_crown_ether=mock.Mock(),
        )

        CanvasView.add_cyclopropane(view)
        CanvasView.add_pyridine(view)
        CanvasView.add_naphthalene(view)
        CanvasView.add_crown_12_4(view)

        self.assertEqual(structure_build_service.run_recorded_build.call_count, 4)
        view._add_regular_ring_template.assert_called_once_with(3)
        view._add_hetero_ring_template.assert_called_once_with(6, ["C", "C", "C", "C", "C", "N"])
        view._add_fused_benzenes.assert_called_once_with(2)
        view._add_crown_ether.assert_called_once_with(12, 4)

    def test_set_curved_arrow_path_builds_path_and_arrow_heads(self) -> None:
        path_item = QGraphicsPathItem()
        view = SimpleNamespace(_add_arrow_head=mock.Mock())

        CanvasView._set_curved_arrow_path(
            view,
            path_item,
            start=QPointF(0.0, 0.0),
            end=QPointF(10.0, 0.0),
            control=QPointF(5.0, 4.0),
            double=True,
        )

        self.assertFalse(path_item.path().isEmpty())
        self.assertEqual(view._add_arrow_head.call_count, 2)

    def test_record_label_change_builds_composite_single_and_noop_commands(self) -> None:
        pushed_commands = []
        view = SimpleNamespace(
            _history_enabled=True,
            model=SimpleNamespace(
                atoms={5: Atom("N", 1.0, 2.0, explicit_label=True)},
                bonds=[
                    Bond(5, 6, 2, style="double", color="#112233"),
                    None,
                ],
                next_atom_id=8,
            ),
            last_smiles_input="after",
            _bond_state_dict=lambda bond: {
                "a": bond.a,
                "b": bond.b,
                "order": bond.order,
                "style": bond.style,
                "color": bond.color,
            },
            _push_command=pushed_commands.append,
        )

        CanvasView._record_label_change(
            view,
            atom_id=5,
            before_element="C",
            before_explicit_label=False,
            before_smiles_input="before",
            merge_ids=[7],
            merge_info={
                "bond_before_states": {
                    0: {"a": 5, "b": 6, "order": 1, "style": "single", "color": "#000000"},
                    1: {"a": 7, "b": 8, "order": 1, "style": "single", "color": "#abcdef"},
                },
                "deleted_bond_ids": [1],
                "atom_states": {7: {"element": "C"}},
            },
        )

        self.assertEqual(len(pushed_commands), 1)
        composite = pushed_commands.pop()
        self.assertIsInstance(composite, CompositeCommand)
        self.assertEqual(
            [type(command) for command in composite.commands],
            [ChangeAtomLabelCommand, UpdateBondCommand, DeleteBondCommand, DeleteAtomsCommand],
        )
        self.assertFalse(composite.commands[-1].remove_marks)

        CanvasView._record_label_change(
            view,
            atom_id=5,
            before_element="C",
            before_explicit_label=True,
            before_smiles_input="before",
            merge_ids=[],
            merge_info={},
        )
        self.assertIsInstance(pushed_commands.pop(), ChangeAtomLabelCommand)

        CanvasView._record_label_change(
            view,
            atom_id=5,
            before_element="N",
            before_explicit_label=True,
            before_smiles_input="after",
            merge_ids=[],
            merge_info={},
        )
        self.assertEqual(pushed_commands, [])

        disabled_view = SimpleNamespace(
            _history_enabled=False,
            model=view.model,
            last_smiles_input="after",
            _bond_state_dict=view._bond_state_dict,
            _push_command=pushed_commands.append,
        )
        CanvasView._record_label_change(
            disabled_view,
            atom_id=5,
            before_element="C",
            before_explicit_label=False,
            before_smiles_input="before",
            merge_ids=[7],
            merge_info={"atom_states": {7: {"element": "C"}}},
        )
        self.assertEqual(pushed_commands, [])

    def test_record_additions_builds_composite_single_and_noop_commands(self) -> None:
        pushed_commands = []
        note_item = object()
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("O", 1.0, 0.0),
                    3: Atom("N", 2.0, 0.0),
                },
                bonds=[Bond(1, 2, 1), None, Bond(2, 3, 2)],
                next_atom_id=4,
            ),
            last_smiles_input="after",
            _atom_state_dict=lambda atom_id: {"atom_id": atom_id},
            _bond_state_dict=lambda bond: {
                "a": bond.a,
                "b": bond.b,
                "order": bond.order,
                "style": bond.style,
                "color": bond.color,
            },
            scene_item_state=lambda item: {"kind": "note"} if item is note_item else {},
            _push_command=pushed_commands.append,
        )

        CanvasView._record_additions(
            view,
            before_next_atom_id=1,
            before_bond_count=1,
            before_smiles_input="before",
            added_scene_items=[note_item, None],
        )

        self.assertEqual(len(pushed_commands), 1)
        composite = pushed_commands.pop()
        self.assertIsInstance(composite, CompositeCommand)
        self.assertEqual(
            [type(command) for command in composite.commands],
            [AddAtomsCommand, AddBondCommand, AddSceneItemsCommand],
        )
        self.assertEqual(composite.commands[0].atom_states, {1: {"atom_id": 1}, 2: {"atom_id": 2}, 3: {"atom_id": 3}})
        self.assertEqual(composite.commands[2].item_states, [{"kind": "note"}])

        single_pushes = []
        single_view = SimpleNamespace(
            model=SimpleNamespace(atoms={}, bonds=[], next_atom_id=0),
            last_smiles_input="after",
            _atom_state_dict=view._atom_state_dict,
            _bond_state_dict=view._bond_state_dict,
            scene_item_state=lambda item: {"kind": "note"},
            _push_command=single_pushes.append,
        )
        CanvasView._record_additions(
            single_view,
            before_next_atom_id=0,
            before_bond_count=0,
            before_smiles_input=None,
            added_scene_items=[note_item],
        )
        self.assertIsInstance(single_pushes.pop(), AddSceneItemsCommand)

        CanvasView._record_additions(
            single_view,
            before_next_atom_id=0,
            before_bond_count=0,
            before_smiles_input=None,
            added_scene_items=[],
        )
        self.assertEqual(single_pushes, [])

    def test_bond_restore_remove_trim_and_update_helpers(self) -> None:
        pushed_commands = []
        update_view = SimpleNamespace(
            _history_enabled=True,
            _push_command=pushed_commands.append,
        )
        CanvasView._record_bond_update(
            update_view,
            bond_id=3,
            before_state={"order": 1},
            after_state={"order": 2},
            before_smiles_input="before",
            after_smiles_input="after",
        )
        self.assertIsInstance(pushed_commands.pop(), UpdateBondCommand)

        CanvasView._record_bond_update(
            update_view,
            bond_id=3,
            before_state={"order": 1},
            after_state={"order": 1},
            before_smiles_input="same",
            after_smiles_input="same",
        )
        self.assertEqual(pushed_commands, [])

        restore_scene = _FakeScene()
        old_bond_item = object()
        restore_view = SimpleNamespace(
            bond_items={0: [old_bond_item]},
            scene=lambda: restore_scene,
            model=SimpleNamespace(bonds=[Bond(1, 2, 1)]),
            _remove_bond_index=mock.Mock(),
            _remove_bond_neighbors=mock.Mock(),
            _add_bond_neighbors=mock.Mock(),
            _add_bond_index=mock.Mock(),
            _add_bond_graphics=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
        )
        CanvasView._restore_bond_from_state(
            restore_view,
            0,
            {"a": 2, "b": 3, "order": 2, "style": "double", "color": "#334455"},
        )
        self.assertEqual(restore_scene.removed_items, [old_bond_item])
        self.assertEqual(restore_view.model.bonds[0].a, 2)
        self.assertEqual(restore_view.model.bonds[0].b, 3)
        restore_view._remove_bond_index.assert_called_once_with(0, 1, 2)
        restore_view._remove_bond_neighbors.assert_called_once_with(1, 2, skip_bond_id=0)
        restore_view._add_bond_neighbors.assert_called_once_with(2, 3)
        restore_view._add_bond_index.assert_called_once_with(0, 2, 3)
        restore_view._add_bond_graphics.assert_called_once_with(0)
        restore_view._mark_spatial_index_dirty.assert_called_once_with()

        extend_view = SimpleNamespace(
            bond_items={},
            scene=lambda: _FakeScene(),
            model=SimpleNamespace(bonds=[]),
            _remove_bond_index=mock.Mock(),
            _remove_bond_neighbors=mock.Mock(),
            _add_bond_neighbors=mock.Mock(),
            _add_bond_index=mock.Mock(),
            _add_bond_graphics=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
        )
        CanvasView._restore_bond_from_state(
            extend_view,
            2,
            {"a": 8, "b": 9, "order": 1, "style": "single", "color": "#000000"},
        )
        self.assertEqual(len(extend_view.model.bonds), 3)
        self.assertIsNone(extend_view.model.bonds[0])
        self.assertIsNone(extend_view.model.bonds[1])
        self.assertEqual((extend_view.model.bonds[2].a, extend_view.model.bonds[2].b), (8, 9))

        remove_scene = _FakeScene()
        remove_view = SimpleNamespace(
            model=SimpleNamespace(bonds=[Bond(4, 5, 1)]),
            bond_items={0: [old_bond_item]},
            scene=lambda: remove_scene,
            _remove_bond_index=mock.Mock(),
            _remove_bond_neighbors=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
        )
        CanvasView._remove_bond_by_id(remove_view, -1)
        CanvasView._remove_bond_by_id(remove_view, 0)
        self.assertEqual(remove_scene.removed_items, [old_bond_item])
        self.assertIsNone(remove_view.model.bonds[0])
        remove_view._remove_bond_index.assert_called_once_with(0, 4, 5)
        remove_view._remove_bond_neighbors.assert_called_once_with(4, 5, skip_bond_id=0)
        remove_view._mark_spatial_index_dirty.assert_called_once_with()

        trim_scene = _FakeScene()
        trim_view = SimpleNamespace(
            model=SimpleNamespace(bonds=[Bond(1, 2, 1), None, Bond(2, 3, 2)]),
            bond_items={1: [object()], 2: [old_bond_item]},
            scene=lambda: trim_scene,
            _remove_bond_index=mock.Mock(),
            _remove_bond_neighbors=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
        )
        CanvasView._trim_bonds_to_length(trim_view, -1)
        CanvasView._trim_bonds_to_length(trim_view, 3)
        CanvasView._trim_bonds_to_length(trim_view, 1)
        self.assertEqual(len(trim_view.model.bonds), 1)
        self.assertEqual(len(trim_scene.removed_items), 2)
        trim_view._remove_bond_index.assert_called_once_with(2, 2, 3)
        trim_view._remove_bond_neighbors.assert_called_once_with(2, 3, skip_bond_id=2)
        trim_view._mark_spatial_index_dirty.assert_called_once_with()

    def test_atom_state_remove_restore_and_color_helpers(self) -> None:
        label_item = mock.Mock()
        dot_item = mock.Mock()
        state_view = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 1.0, 2.0, color="#111111")}),
            atom_items={1: label_item},
        )
        self.assertEqual(
            CanvasView._atom_state_dict(state_view, 1),
            {
                "element": "C",
                "x": 1.0,
                "y": 2.0,
                "color": "#111111",
                "explicit_label": True,
            },
        )
        self.assertEqual(CanvasView._atom_state_dict(state_view, 99), {})

        scene = _FakeScene()
        remove_view = SimpleNamespace(
            atom_items={1: label_item},
            atom_dots={1: dot_item},
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 2.0, 0.0)},
                bonds=[Bond(1, 2, 1)],
            ),
            atom_coords_3d={1: (0.0, 0.0, 0.0)},
            _atom_neighbors={1: {2}, 2: {1}},
            _graph_version=4,
            _selection_component_cache_signature="cached",
            _atom_bond_ids={1: {0}, 2: {0}},
            _remove_marks_for_atom=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
            scene=lambda: scene,
        )
        CanvasView._remove_atom_only(remove_view, 1)
        self.assertEqual(scene.removed_items, [label_item, dot_item])
        remove_view._remove_marks_for_atom.assert_called_once_with(1)
        self.assertNotIn(1, remove_view.model.atoms)
        self.assertNotIn(1, remove_view.atom_coords_3d)
        self.assertNotIn(1, remove_view._atom_neighbors)
        self.assertEqual(remove_view._atom_neighbors[2], set())
        self.assertEqual(remove_view._graph_version, 5)
        self.assertIsNone(remove_view._selection_component_cache_signature)
        self.assertEqual(remove_view._atom_bond_ids[2], set())
        remove_view._mark_spatial_index_dirty.assert_called_once_with()

        restore_scene = _FakeScene()
        old_label = object()
        old_dot = object()
        restore_view = SimpleNamespace(
            model=SimpleNamespace(atoms={}, next_atom_id=1),
            atom_items={4: old_label},
            atom_dots={4: old_dot},
            scene=lambda: restore_scene,
            _ensure_atom_neighbors=mock.Mock(),
            _ensure_atom_bond_ids=mock.Mock(),
            _atom_label_service=mock.Mock(),
            _ensure_carbon_dot=mock.Mock(),
            apply_atom_color=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
        )
        CanvasView._restore_atom_from_state(
            restore_view,
            4,
            {"element": "C", "x": 3.0, "y": 4.0, "color": "#00ff00", "explicit_label": True},
        )
        self.assertEqual(restore_scene.removed_items, [old_label, old_dot])
        self.assertEqual(restore_view.model.next_atom_id, 5)
        restore_view._atom_label_service.add_or_update_atom_label.assert_called_once_with(
            4,
            "C",
            clear_smiles=False,
            record=False,
            allow_merge=False,
            show_carbon=True,
        )
        restore_view._ensure_carbon_dot.assert_not_called()
        restore_view.apply_atom_color.assert_called_once_with(4, "#00ff00")
        restore_view._mark_spatial_index_dirty.assert_called_once_with()

        carbon_dot_view = SimpleNamespace(
            model=SimpleNamespace(atoms={}, next_atom_id=0),
            atom_items={},
            atom_dots={},
            scene=lambda: _FakeScene(),
            _ensure_atom_neighbors=mock.Mock(),
            _ensure_atom_bond_ids=mock.Mock(),
            _atom_label_service=mock.Mock(),
            _ensure_carbon_dot=mock.Mock(),
            apply_atom_color=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
        )
        CanvasView._restore_atom_from_state(
            carbon_dot_view,
            2,
            {"element": "C", "x": 0.0, "y": 0.0, "color": "#000000", "explicit_label": False},
        )
        carbon_dot_view._ensure_carbon_dot.assert_called_once_with(2)
        carbon_dot_view._atom_label_service.add_or_update_atom_label.assert_not_called()

        color_view = SimpleNamespace(
            model=SimpleNamespace(atoms={7: Atom("O", 0.0, 0.0, color="#101010")}),
            atom_items={7: mock.Mock()},
            atom_dots={7: mock.Mock()},
            _implicit_carbon_dot_brush=mock.Mock(return_value="brush"),
        )
        CanvasView.apply_atom_color(color_view, 7, QColor("#aabbcc"))
        self.assertEqual(color_view.model.atoms[7].color, "#aabbcc")
        color_view.atom_items[7].setDefaultTextColor.assert_called_once()
        color_view.atom_dots[7].setBrush.assert_called_once_with("brush")

        CanvasView.apply_atom_color(color_view, 7, "not-a-color")
        self.assertEqual(color_view.model.atoms[7].color, "#aabbcc")
        CanvasView.apply_atom_color(color_view, 99, "#ffffff")

    def test_scene_event_and_item_hit_helpers_cover_fallback_paths(self) -> None:
        class _PositionEvent:
            def position(self):
                return SimpleNamespace(toPoint=lambda: "position-point")

        class _PosEvent:
            def pos(self):
                return "pos-point"

        viewport = SimpleNamespace(mapFromGlobal=lambda pos: "global-point")
        event_view = SimpleNamespace(
            mapToScene=lambda value: QPointF(1.0, 2.0)
            if value == "position-point"
            else QPointF(3.0, 4.0)
            if value == "pos-point"
            else QPointF(5.0, 6.0),
            viewport=lambda: viewport,
        )
        self.assertEqual(CanvasView.scene_pos_from_event(event_view, _PositionEvent()), QPointF(1.0, 2.0))
        self.assertEqual(CanvasView.scene_pos_from_event(event_view, _PosEvent()), QPointF(3.0, 4.0))
        self.assertEqual(CanvasView.scene_pos_from_event(event_view, object()), QPointF(5.0, 6.0))

        atom_item = _FakeItem("atom")
        hit_scene = _FakeScene(
            items_at_pos=[
                _FakeItem("selection_outline"),
                _FakeItem("note_select"),
                _FakeItem("bond"),
                _FakeItem("ring"),
                atom_item,
            ]
        )
        hit_view = SimpleNamespace(
            scene=lambda: hit_scene,
            _find_bond_near=mock.Mock(return_value=None),
            _bond_pick_radius=mock.Mock(return_value=9.0),
            bond_items={},
        )
        self.assertIs(CanvasView.item_at_scene_pos(hit_view, QPointF(0.0, 0.0)), atom_item)

        nearby_bond_graphic = _FakeItem("bond_graphic")
        fallback_scene = _FakeScene(items_at_pos=[_FakeItem("note_box"), _FakeItem("other")])
        fallback_view = SimpleNamespace(
            scene=lambda: fallback_scene,
            _find_bond_near=mock.Mock(return_value=4),
            _bond_pick_radius=mock.Mock(return_value=7.0),
            bond_items={4: [nearby_bond_graphic]},
        )
        self.assertIs(CanvasView.item_at_scene_pos(fallback_view, QPointF(2.0, 2.0)), nearby_bond_graphic)

    def test_pick_radius_and_nearest_hit_helpers_cover_missing_and_success_paths(self) -> None:
        radius_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=1.0, bond_length_px=20.0))
        )
        self.assertEqual(CanvasView._atom_pick_radius(radius_view), 6.4)

        atom_view = SimpleNamespace(
            find_atom_near=mock.Mock(return_value=1),
            _atom_pick_radius=mock.Mock(return_value=5.0),
            model=SimpleNamespace(atoms={1: Atom("C", 3.0, 4.0)}),
        )
        atom_hit = CanvasView._nearest_atom_hit(atom_view, QPointF(0.0, 0.0))
        self.assertEqual(atom_hit, (1, 5.0))
        atom_view.find_atom_near.return_value = None
        self.assertIsNone(CanvasView._nearest_atom_hit(atom_view, QPointF(0.0, 0.0)))
        atom_view.find_atom_near.return_value = 2
        self.assertIsNone(CanvasView._nearest_atom_hit(atom_view, QPointF(0.0, 0.0)))

        bond_view = SimpleNamespace(
            _find_bond_near=mock.Mock(return_value=0),
            _bond_pick_radius=mock.Mock(return_value=9.0),
            model=SimpleNamespace(
                bonds=[Bond(1, 2, 1), None],
                atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 10.0, 0.0)},
            ),
            _distance_point_to_segment=CanvasView._distance_point_to_segment,
        )
        bond_hit = CanvasView._nearest_bond_hit(bond_view, QPointF(5.0, 2.0))
        self.assertEqual(bond_hit, (0, 2.0))
        bond_view._find_bond_near.return_value = None
        self.assertIsNone(CanvasView._nearest_bond_hit(bond_view, QPointF(0.0, 0.0)))
        bond_view._find_bond_near.return_value = 1
        self.assertIsNone(CanvasView._nearest_bond_hit(bond_view, QPointF(0.0, 0.0)))
        bond_view._find_bond_near.return_value = 0
        bond_view.model.atoms.pop(2)
        self.assertIsNone(CanvasView._nearest_bond_hit(bond_view, QPointF(0.0, 0.0)))

    def test_style_and_text_setting_helpers_clamp_values_and_apply_presets(self) -> None:
        style_view = SimpleNamespace(
            _curved_symmetry=False,
            _selection_color=QColor("#000000"),
            _selection_stroke_delta=0.6,
            _orbital_snap_enabled=False,
            _orbital_snap_step=15,
            text_font_family="Helvetica",
            text_font_size=11,
            text_font_weight=QFont.Weight.Normal,
            text_italic=False,
            text_color=QColor("#222222"),
            text_alignment=Qt.AlignmentFlag.AlignLeft,
            text_line_spacing=1.0,
            note_box_enabled=False,
            note_box_color=QColor("#ffffff"),
            note_box_alpha=0.3,
            note_border_enabled=False,
            note_border_color=QColor("#111111"),
            note_border_width=1.0,
            note_padding=4.0,
            atom_symbol="C",
            renderer=SimpleNamespace(style=SimpleNamespace(font_size_pt=12, atom_color="#123456")),
            tools=SimpleNamespace(set_active=mock.Mock()),
            _update_selection_outline=mock.Mock(),
            apply_text_style_to_selected=mock.Mock(),
        )

        CanvasView.set_curved_symmetry(style_view, True)
        self.assertTrue(CanvasView.get_curved_symmetry(style_view))
        CanvasView.set_selection_color(style_view, QColor("#abcdef"))
        self.assertEqual(style_view._selection_color.name(), "#abcdef")
        CanvasView.set_selection_color(style_view, QColor())
        self.assertEqual(style_view._selection_color.name(), "#abcdef")
        CanvasView.set_selection_stroke_delta(style_view, -5.0)
        self.assertEqual(CanvasView.get_selection_stroke_delta(style_view), 0.1)

        CanvasView.set_orbital_snap_enabled(style_view, True)
        self.assertTrue(CanvasView.get_orbital_snap_enabled(style_view))
        CanvasView.set_orbital_snap_step(style_view, 0)
        self.assertEqual(CanvasView.get_orbital_snap_step(style_view), 1)

        CanvasView.set_text_font(style_view, QFont("Courier New", 14))
        self.assertEqual(style_view.text_font_family, "Courier New")
        CanvasView.set_text_size(style_view, 2)
        self.assertEqual(CanvasView.get_text_size(style_view), 6)
        CanvasView.set_text_weight(style_view, 150)
        self.assertEqual(CanvasView.get_text_weight(style_view), 99)
        CanvasView.set_text_italic(style_view, True)
        self.assertTrue(style_view.text_italic)
        CanvasView.set_text_color(style_view, QColor("#ff00aa"))
        self.assertEqual(style_view.text_color.name(), "#ff00aa")
        CanvasView.set_text_color(style_view, QColor())
        self.assertEqual(style_view.text_color.name(), "#ff00aa")
        font = CanvasView.get_text_font(style_view)
        self.assertEqual(font.family(), "Courier New")
        self.assertEqual(font.pointSize(), 6)

        CanvasView.apply_text_preset_acs(style_view)
        self.assertEqual(style_view.text_font_family, "Arial")
        self.assertEqual(style_view.text_font_size, 12)
        self.assertEqual(style_view.text_color.name(), "#123456")
        self.assertFalse(style_view.note_box_enabled)
        self.assertFalse(style_view.note_border_enabled)

        CanvasView.apply_text_preset_paper_thin(style_view)
        self.assertEqual(style_view.text_font_size, 11)
        self.assertAlmostEqual(style_view.text_line_spacing, 1.05)
        self.assertEqual(style_view.text_color.name(), "#222222")

        CanvasView.apply_text_preset_paper_bold(style_view)
        self.assertEqual(style_view.text_font_size, 14)
        self.assertTrue(style_view.note_box_enabled)
        self.assertTrue(style_view.note_border_enabled)
        self.assertEqual(style_view.note_box_color.name(), "#ffffff")
        self.assertEqual(style_view.note_border_color.name(), "#111111")
        self.assertEqual(style_view.note_padding, 8.0)

        CanvasView.set_text_alignment(style_view, "center")
        self.assertEqual(style_view.text_alignment, Qt.AlignmentFlag.AlignHCenter)
        CanvasView.set_text_alignment(style_view, "bad")
        self.assertEqual(style_view.text_alignment, Qt.AlignmentFlag.AlignHCenter)
        CanvasView.set_text_line_spacing(style_view, 0.2)
        self.assertEqual(style_view.text_line_spacing, 0.8)
        CanvasView.set_atom_symbol(style_view, " N ")
        self.assertEqual(CanvasView.get_atom_symbol(style_view), "N")
        CanvasView.set_note_box_enabled(style_view, False)
        self.assertFalse(style_view.note_box_enabled)
        CanvasView.set_note_box_color(style_view, QColor("#00ff00"))
        self.assertEqual(style_view.note_box_color.name(), "#00ff00")
        CanvasView.set_note_box_color(style_view, QColor())
        self.assertEqual(style_view.note_box_color.name(), "#00ff00")
        CanvasView.set_note_box_alpha(style_view, 3.0)
        self.assertEqual(CanvasView.get_note_box_alpha(style_view), 1.0)
        CanvasView.set_note_border_enabled(style_view, False)
        self.assertFalse(style_view.note_border_enabled)
        CanvasView.set_note_border_color(style_view, QColor("#445566"))
        self.assertEqual(style_view.note_border_color.name(), "#445566")
        CanvasView.set_note_border_color(style_view, QColor())
        self.assertEqual(style_view.note_border_color.name(), "#445566")
        CanvasView.set_note_border_width(style_view, 0.1)
        self.assertEqual(style_view.note_border_width, 0.5)
        CanvasView.set_note_padding(style_view, 1.0)
        self.assertEqual(style_view.note_padding, 2.0)
        CanvasView.set_snap_angle_step(style_view, 22)
        self.assertEqual(style_view.snap_angle_step, 22)
        style_view.tools.set_active.assert_called_with("bond")
        style_view._update_selection_outline.assert_called_once_with()
        self.assertGreaterEqual(style_view.apply_text_style_to_selected.call_count, 14)

    def test_note_selection_and_text_style_helpers_update_boxes_and_focus(self) -> None:
        scene = QGraphicsScene()
        item = QGraphicsTextItem("Mechanism")
        scene.addItem(item)

        note_view = SimpleNamespace(
            selected_notes=[],
            note_padding=6.0,
            note_box_enabled=True,
            note_border_enabled=True,
            note_box_color=QColor("#ffffff"),
            note_box_alpha=0.4,
            note_border_color=QColor("#111111"),
            note_border_width=1.2,
            _selection_color=QColor("#1f5eff"),
            _selection_stroke_delta=0.8,
            text_font_family="Arial",
            text_font_size=13,
            text_font_weight=QFont.Weight.DemiBold,
            text_italic=True,
            text_color=QColor("#334455"),
            text_alignment=Qt.AlignmentFlag.AlignRight,
            text_line_spacing=1.25,
            scene=lambda: scene,
            setFocus=mock.Mock(),
        )
        note_view.clear_note_selection = lambda: CanvasView.clear_note_selection(note_view)
        note_view.select_note = lambda target, additive=False: CanvasView.select_note(note_view, target, additive=additive)
        note_view._update_note_box = lambda target: CanvasView._update_note_box(note_view, target)
        note_view._update_note_selection_box = lambda target: CanvasView._update_note_selection_box(note_view, target)
        note_view._apply_note_style = lambda target: CanvasView._apply_note_style(note_view, target)

        CanvasView.select_note(note_view, item, additive=False)
        self.assertEqual(note_view.selected_notes, [item])
        selection_box = item.data(21)
        self.assertIsNotNone(selection_box)
        self.assertTrue(selection_box.isVisible())

        CanvasView.apply_text_style_to_selected(note_view)
        box = item.data(20)
        self.assertIsNotNone(box)
        self.assertTrue(box.isVisible())
        self.assertEqual(item.defaultTextColor().name(), "#334455")
        self.assertTrue(item.font().italic())
        self.assertEqual(item.font().pointSize(), 13)

        CanvasView.update_text_note(note_view, item, "Updated")
        self.assertEqual(item.toPlainText(), "Updated")

        CanvasView.begin_note_edit(note_view, item)
        self.assertIn(item, note_view.selected_notes)
        note_view.setFocus.assert_called()
        self.assertIs(scene.focusItem(), item)
        self.assertNotEqual(item.textInteractionFlags(), Qt.TextInteractionFlag.NoTextInteraction)

        CanvasView.toggle_note_selection(note_view, item)
        self.assertEqual(note_view.selected_notes, [])
        self.assertFalse(item.data(21).isVisible())

        CanvasView.select_note(note_view, item, additive=False)
        CanvasView.clear_note_selection(note_view)
        self.assertEqual(note_view.selected_notes, [])
        self.assertFalse(item.data(21).isVisible())

        note_view.note_box_enabled = False
        note_view.note_border_enabled = False
        CanvasView._update_note_box(note_view, item)
        self.assertFalse(item.data(20).isVisible())

    def test_bond_id_from_event_prefers_hover_and_falls_back_to_scene_lookup(self) -> None:
        event = object()
        view = SimpleNamespace(
            hover_bond_id=7,
            scene_pos_from_event=mock.Mock(),
            _find_bond_near=mock.Mock(),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            _bond_pick_radius=mock.Mock(return_value=6.0),
        )
        self.assertEqual(CanvasView.bond_id_from_event(view, event), 7)
        view.scene_pos_from_event.assert_not_called()

        view.hover_bond_id = None
        view.scene_pos_from_event.return_value = QPointF(3.0, 4.0)
        view._find_bond_near.return_value = 2
        self.assertEqual(CanvasView.bond_id_from_event(view, event), 2)
        view._find_bond_near.assert_called_once_with(QPointF(3.0, 4.0), 7.0)

    def test_selection_and_copy_helpers_cover_transform_copy_and_mark_fallback(self) -> None:
        scene_token = object()
        selected_note = _FakeItem("note", scene_token=scene_token)
        transform_scene = _FakeScene(
            [
                _FakeItem("atom", data1=1, scene_token=scene_token),
                _FakeItem("handle", scene_token=scene_token),
                _FakeItem("note_box", scene_token=scene_token),
                selected_note,
            ]
        )
        selected_note._scene_token = transform_scene
        transform_view = SimpleNamespace(
            scene=lambda: transform_scene,
            selected_notes=[selected_note, _FakeItem("note", scene_token=object())],
        )
        transformed_items = CanvasView._selected_items_for_transform(transform_view)
        self.assertEqual([item.data(0) for item in transformed_items], ["atom", "note"])

        polygon = QPolygonF(
            [
                QPointF(-1.0, -1.0),
                QPointF(3.0, -1.0),
                QPointF(3.0, 3.0),
                QPointF(-1.0, 3.0),
            ]
        )
        selection_scene = _FakeScene(
            [
                _FakeItem("atom", data1=1, scene_token=scene_token),
                _FakeItem("bond", data1=7, scene_token=scene_token),
                _FakeItem("ring", data2=[2, "bad", 99], scene_token=scene_token),
                _FakeItem("ring", scene_token=scene_token, polygon=polygon),
            ]
        )
        selection_view = SimpleNamespace(
            scene=lambda: selection_scene,
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("O", 2.0, 0.0),
                    3: Atom("N", 1.0, 1.0),
                    4: Atom("F", 5.0, 5.0),
                }
            ),
        )
        atom_ids, bond_ids = CanvasView._selected_ids(selection_view)
        self.assertEqual(atom_ids, {1, 2, 3})
        self.assertEqual(bond_ids, {7})

        chemical_scene = _FakeScene([_FakeItem("mark", data1={"atom_id": 4}, scene_token=scene_token)])
        chemical_view = SimpleNamespace(
            scene=lambda: chemical_scene,
            _selected_ids=lambda: (set(), set()),
            model=SimpleNamespace(atoms={4: Atom("Cl", 0.0, 0.0)}),
        )
        self.assertEqual(CanvasView._selected_chemical_ids(chemical_view), ({4}, set()))

        bond_child = _FakeItem("bond_child", scene_token=scene_token)
        bond_graphic = _FakeItem("bond_graphic", scene_token=scene_token, children=[bond_child])
        extra_child = _FakeItem("arrow_head", scene_token=scene_token)
        generic_item = _FakeItem("arrow", scene_token=scene_token, children=[extra_child])
        note_select = _FakeItem("note_select", scene_token=scene_token)
        copy_scene = _FakeScene(
            [
                _FakeItem("bond", data1=5, scene_token=scene_token),
                generic_item,
                note_select,
            ]
        )
        note = _FakeItem("note", scene_token=scene_token)
        note._scene_token = copy_scene
        copy_view = SimpleNamespace(
            scene=lambda: copy_scene,
            selected_notes=[note, _FakeItem("note", scene_token=object())],
            bond_items={5: [bond_graphic]},
        )
        copied_items = CanvasView._selection_items_for_copy(copy_view)
        self.assertEqual(
            [item.data(0) for item in copied_items],
            ["bond_graphic", "bond_child", "arrow", "arrow_head", "note"],
        )

    def test_set_atom_positions_updates_geometry_marks_and_selection(self) -> None:
        label_item = object()
        dot_item = mock.Mock()
        mark_with_offset = _FakeItem("mark", data1={"dx": 1.5, "dy": -2.0})
        mark_without_offset = _FakeItem("mark", data1={})
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("O", 5.0, 5.0),
                    3: Atom("N", 9.0, 9.0),
                }
            ),
            atom_coords_3d={1: (0.0, 0.0, 1.0), 3: (9.0, 9.0, 3.0)},
            atom_items={1: label_item},
            atom_dots={1: dot_item},
            _marks_by_atom={1: [mark_with_offset, mark_without_offset]},
            _position_label=mock.Mock(),
            _set_mark_center=mock.Mock(),
            _redraw_bonds_for_atoms=mock.Mock(),
            _update_ring_fills_for_atoms=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
            _update_selection_outline=mock.Mock(),
        )

        CanvasView.set_atom_positions(
            view,
            positions={1: (2.0, 3.0), 99: (0.0, 0.0)},
            coords_3d={2: (7.0, 8.0, 9.0)},
        )

        self.assertEqual((view.model.atoms[1].x, view.model.atoms[1].y), (2.0, 3.0))
        self.assertEqual(view.atom_coords_3d[1], (2.0, 3.0, 1.0))
        self.assertEqual(view.atom_coords_3d[2], (7.0, 8.0, 9.0))
        view._position_label.assert_called_once_with(label_item, 2.0, 3.0)
        dot_item.setPos.assert_called_once_with(2.0, 3.0)
        self.assertEqual(
            view._set_mark_center.call_args_list,
            [
                mock.call(mark_with_offset, QPointF(3.5, 1.0)),
                mock.call(mark_without_offset, QPointF(2.0, 3.0)),
            ],
        )
        view._redraw_bonds_for_atoms.assert_called_once_with({1, 2})
        view._update_ring_fills_for_atoms.assert_called_once_with({1, 2})
        view._mark_spatial_index_dirty.assert_called_once_with()
        view._update_selection_outline.assert_called_once_with()

        quiet_view = SimpleNamespace(
            model=SimpleNamespace(atoms={}),
            atom_coords_3d={},
            atom_items={},
            atom_dots={},
            _marks_by_atom={},
            _position_label=mock.Mock(),
            _set_mark_center=mock.Mock(),
            _redraw_bonds_for_atoms=mock.Mock(),
            _update_ring_fills_for_atoms=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
            _update_selection_outline=mock.Mock(),
        )
        CanvasView.set_atom_positions(quiet_view, positions={}, coords_3d=None)
        quiet_view._mark_spatial_index_dirty.assert_not_called()

    def test_select_structure_for_item_selects_atom_bond_ring_and_scene_items(self) -> None:
        atom_item = _FakeItem("atom", data1=1)
        atom_item_2 = _FakeItem("atom", data1=2)
        bond_item = _FakeItem("bond", data1=0)
        bond_graphic = _FakeItem("bond")
        ring_item = _FakeItem("ring", data2=[1, 2])
        note_item = _FakeItem("note")
        selection_scene = _FakeScene([atom_item, bond_item, ring_item, note_item])
        view = SimpleNamespace(
            scene=lambda: selection_scene,
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 2.0, 0.0)},
                bonds=[Bond(1, 2, 1)],
            ),
            atom_items={1: atom_item, 2: atom_item_2},
            atom_dots={},
            bond_items={0: [bond_graphic]},
            ring_items=[ring_item],
            _expand_connected_atoms=mock.Mock(return_value={1, 2}),
            _update_selection_outline=mock.Mock(),
        )

        self.assertTrue(CanvasView.select_structure_for_item(view, atom_item))
        self.assertEqual(selection_scene.clear_selection_calls, 1)
        self.assertTrue(atom_item.isSelected())
        self.assertTrue(atom_item_2.isSelected())
        self.assertTrue(bond_graphic.isSelected())
        self.assertTrue(ring_item.isSelected())
        view._update_selection_outline.assert_called_once_with()

        selection_scene.clear_selection_calls = 0
        view._update_selection_outline.reset_mock()
        self.assertTrue(CanvasView.select_structure_for_item(view, bond_item))
        self.assertEqual(selection_scene.clear_selection_calls, 1)
        view._expand_connected_atoms.assert_called_with({1, 2})

        ring_only = _FakeItem("ring", data2=[1, 2])
        ring_scene = _FakeScene([ring_only])
        ring_view = SimpleNamespace(
            scene=lambda: ring_scene,
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 2.0, 0.0)}, bonds=[]),
            atom_items={1: _FakeItem("atom", data1=1), 2: _FakeItem("atom", data1=2)},
            atom_dots={},
            bond_items={},
            ring_items=[ring_only],
            _expand_connected_atoms=mock.Mock(return_value={1, 2}),
            _update_selection_outline=mock.Mock(),
        )
        self.assertTrue(CanvasView.select_structure_for_item(ring_view, ring_only))
        self.assertTrue(ring_only.isSelected())

        note_scene = _FakeScene([note_item])
        note_view = SimpleNamespace(
            scene=lambda: note_scene,
            model=SimpleNamespace(atoms={}, bonds=[]),
            atom_items={},
            atom_dots={},
            bond_items={},
            ring_items=[],
            _expand_connected_atoms=mock.Mock(),
            _update_selection_outline=mock.Mock(),
        )
        self.assertTrue(CanvasView.select_structure_for_item(note_view, note_item))
        self.assertEqual(note_scene.clear_selection_calls, 1)
        self.assertTrue(note_item.isSelected())
        note_view._update_selection_outline.assert_not_called()

        invalid_atom = _FakeItem("atom", data1="bad")
        invalid_view = SimpleNamespace(
            scene=lambda: _FakeScene([invalid_atom]),
            model=SimpleNamespace(atoms={}, bonds=[]),
            atom_items={},
            atom_dots={},
            bond_items={},
            ring_items=[],
            _expand_connected_atoms=mock.Mock(return_value=set()),
            _update_selection_outline=mock.Mock(),
        )
        self.assertFalse(CanvasView.select_structure_for_item(invalid_view, invalid_atom))
        self.assertFalse(CanvasView.select_structure_for_item(invalid_view, None))

    def test_apply_color_and_fill_helpers_cover_bond_atom_ring_and_commands(self) -> None:
        scene = QGraphicsScene()

        bond_item = QGraphicsPathItem()
        bond_item.setData(0, "bond")
        bond_item.setData(1, 0)
        scene.addItem(bond_item)
        bond_pushes = []
        bond_view = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(bonds=[Bond(1, 2, 1, color="#000000")]),
            bond_items={0: [bond_item]},
            last_smiles_input="smiles",
            _bond_state_dict=lambda bond: {
                "a": bond.a,
                "b": bond.b,
                "order": bond.order,
                "style": bond.style,
                "color": bond.color,
            },
            _apply_color_to_bond_item=mock.Mock(),
            _push_command=bond_pushes.append,
        )
        CanvasView.apply_color_to_item(bond_view, bond_item, QColor("#ff0000"))
        self.assertEqual(bond_view.model.bonds[0].color, "#ff0000")
        bond_view._apply_color_to_bond_item.assert_called_once()
        self.assertIsInstance(bond_pushes.pop(), UpdateBondCommand)

        atom_item = QGraphicsTextItem("O")
        atom_item.setData(0, "atom")
        atom_item.setData(1, 7)
        scene.addItem(atom_item)
        dot_item = mock.Mock()
        atom_pushes = []
        atom_view = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={7: Atom("O", 0.0, 0.0, color="#101010")}),
            atom_items={7: atom_item},
            atom_dots={7: dot_item},
            _implicit_carbon_dot_brush=mock.Mock(return_value="dot-brush"),
            _push_command=atom_pushes.append,
        )
        CanvasView.apply_color_to_item(atom_view, atom_item, QColor("#00aa00"))
        self.assertEqual(atom_view.model.atoms[7].color, "#00aa00")
        self.assertEqual(atom_item.defaultTextColor().name(), "#00aa00")
        dot_item.setBrush.assert_called_once_with("dot-brush")
        self.assertIsInstance(atom_pushes.pop(), UpdateAtomColorCommand)

        ring_item = QGraphicsPathItem()
        ring_item.setData(0, "ring")
        ring_item.setData(2, [1, 2])
        scene.addItem(ring_item)
        recurse_view = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 1.0, 0.0)}),
            atom_items={1: object()},
            atom_dots={2: object()},
            bond_items={3: [object()]},
            bond_sets_for_atoms=mock.Mock(return_value=({3}, set())),
            apply_color_to_item=mock.Mock(),
        )
        CanvasView.apply_color_to_item(recurse_view, ring_item, QColor("#336699"))
        self.assertEqual(
            recurse_view.apply_color_to_item.call_args_list,
            [
                mock.call(recurse_view.atom_items[1], QColor("#336699")),
                mock.call(recurse_view.atom_dots[2], QColor("#336699")),
                mock.call(recurse_view.bond_items[3][0], QColor("#336699")),
            ],
        )

        fill_pushes = []
        fill_view = SimpleNamespace(
            _ring_state_dict=lambda item: {
                "kind": "ring",
                "color": item.brush().color().name(),
                "alpha": round(item.brush().color().alphaF(), 2),
            },
            _push_command=fill_pushes.append,
        )
        CanvasView.apply_ring_fill_color(fill_view, ring_item, QColor("#123456"), alpha=2.0)
        self.assertAlmostEqual(ring_item.brush().color().alphaF(), 1.0)
        self.assertIsInstance(fill_pushes.pop(), UpdateSceneItemCommand)

        CanvasView.apply_color_to_item(atom_view, None, QColor("#ffffff"))
        CanvasView.apply_ring_fill_color(fill_view, None, QColor("#ffffff"))

    def test_clear_scene_resets_canvas_state_and_clears_previews(self) -> None:
        scene = _FakeScene([_FakeItem("atom")], [_FakeItem("bond")])
        apply_insert_session_state = mock.Mock()
        view = SimpleNamespace(
            scene=lambda: scene,
            hover_items=[object()],
            hover_atom_id=3,
            hover_bond_id=4,
            model=SimpleNamespace(dummy=True),
            _mark_spatial_index_dirty=mock.Mock(),
            atom_coords_3d={1: (1.0, 2.0, 3.0)},
            _projection_center_3d=(1.0, 1.0, 1.0),
            _projection_anchor_2d=(2.0, 2.0),
            _rotation_start_projection_center_3d=(3.0, 3.0, 3.0),
            _rotation_start_projection_anchor_2d=(4.0, 4.0),
            _rotation_axis_bond_id=7,
            _rotation_axis_atoms=(1, 2),
            _rotation_total_angle=1.2,
            _rotation_mode="bond",
            _rotation_free_angle_x=2.3,
            _rotation_free_angle_y=4.5,
            _rotation_start_positions={1: (0.0, 0.0)},
            _rotation_start_coords_3d={1: (0.0, 0.0, 0.0)},
            _rotation_coord_atom_ids={1},
            atom_items={1: object()},
            atom_dots={1: object()},
            _atom_neighbors={1: {2}},
            _atom_bond_ids={1: {0}},
            _graph_version=9,
            _selection_component_cache_signature="sig",
            _selection_component_cache=[{1}],
            bond_items={0: [object()]},
            ring_items=[object()],
            note_items=[object()],
            mark_items=[object()],
            arrow_items=[object()],
            ts_bracket_items=[object()],
            orbital_items=[object()],
            _marks_by_atom={1: [object()]},
            _smiles_preview_model=object(),
            _clear_template_preview=mock.Mock(),
            _clear_benzene_preview=mock.Mock(),
            _clear_smiles_preview=mock.Mock(),
            _apply_insert_session_state=apply_insert_session_state,
        )

        CanvasView.clear_scene(view)

        self.assertEqual(view.hover_items, [])
        self.assertIsNone(view.hover_atom_id)
        self.assertIsNone(view.hover_bond_id)
        self.assertIsInstance(view.model, MoleculeModel)
        view._mark_spatial_index_dirty.assert_called_once_with()
        self.assertEqual(view.atom_coords_3d, {})
        self.assertIsNone(view._projection_center_3d)
        self.assertIsNone(view._projection_anchor_2d)
        self.assertIsNone(view._rotation_start_projection_center_3d)
        self.assertIsNone(view._rotation_start_projection_anchor_2d)
        self.assertIsNone(view._rotation_axis_bond_id)
        self.assertIsNone(view._rotation_axis_atoms)
        self.assertEqual(view._rotation_total_angle, 0.0)
        self.assertIsNone(view._rotation_mode)
        self.assertEqual(view._rotation_free_angle_x, 0.0)
        self.assertEqual(view._rotation_free_angle_y, 0.0)
        self.assertEqual(view._rotation_start_positions, {})
        self.assertEqual(view._rotation_start_coords_3d, {})
        self.assertEqual(view._rotation_coord_atom_ids, set())
        self.assertEqual(view.atom_items, {})
        self.assertEqual(view.atom_dots, {})
        self.assertEqual(view._atom_neighbors, {})
        self.assertEqual(view._atom_bond_ids, {})
        self.assertEqual(view._graph_version, 0)
        self.assertIsNone(view._selection_component_cache_signature)
        self.assertEqual(view._selection_component_cache, [])
        self.assertEqual(view.bond_items, {})
        self.assertEqual(view.ring_items, [])
        self.assertEqual(view.note_items, [])
        self.assertEqual(view.mark_items, [])
        self.assertEqual(view.arrow_items, [])
        self.assertEqual(view.ts_bracket_items, [])
        self.assertEqual(view.orbital_items, [])
        self.assertEqual(view._marks_by_atom, {})
        self.assertIsNone(view._smiles_preview_model)
        view._clear_template_preview.assert_called_once_with()
        view._clear_benzene_preview.assert_called_once_with()
        view._clear_smiles_preview.assert_called_once_with()
        apply_insert_session_state.assert_called_once()


if __name__ == "__main__":
    unittest.main()
