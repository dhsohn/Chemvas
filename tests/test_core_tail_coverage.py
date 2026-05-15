import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

from core.model import Atom, Bond, MoleculeModel
from core.rdkit_adapter import RDKitAdapter

if QApplication is not None:
    from ui.tools import MoveTool, SelectTool, TextTool


class _FakeRDAtom:
    def __init__(self, symbol) -> None:
        self.symbol = getattr(symbol, "symbol", symbol)
        self.no_implicit = False

    def SetNoImplicit(self, value: bool) -> None:
        self.no_implicit = bool(value)

    def SetFormalCharge(self, value: int) -> None:
        self.formal_charge = value

    def SetNumRadicalElectrons(self, value: int) -> None:
        self.radical_electrons = value


class _FakeRWMol:
    def __init__(self) -> None:
        self.atoms = []
        self.bonds = []

    def AddAtom(self, atom) -> int:
        self.atoms.append(atom)
        return len(self.atoms) - 1

    def AddBond(self, a: int, b: int, bond_type) -> None:
        self.bonds.append((a, b, bond_type))

    def GetMol(self):
        return SimpleNamespace(atoms=self.atoms, bonds=self.bonds)


class _FakeChem:
    class BondType:
        SINGLE = "single"
        DOUBLE = "double"
        TRIPLE = "triple"

    def __init__(self, mols_by_smiles=None) -> None:
        self.mols_by_smiles = dict(mols_by_smiles or {})
        self.sanitized_molecules = []

    def Atom(self, symbol):
        return _FakeRDAtom(symbol)

    def RWMol(self):
        return _FakeRWMol()

    def MolFromSmiles(self, smiles: str):
        return self.mols_by_smiles.get(smiles)

    def SanitizeMol(self, mol) -> None:
        self.sanitized_molecules.append(mol)


class _NoComputeAllChem:
    pass


class _AliasAtom:
    def __init__(self, idx: int, symbol: str, atomic_num: int) -> None:
        self._idx = idx
        self.symbol = symbol
        self._atomic_num = atomic_num
        self._neighbors = []

    def GetIdx(self) -> int:
        return self._idx

    def GetAtomicNum(self) -> int:
        return self._atomic_num

    def GetNeighbors(self):
        return list(self._neighbors)

    def add_neighbor(self, atom) -> None:
        self._neighbors.append(atom)


class _AliasBond:
    def __init__(self, begin_idx: int, end_idx: int, bond_type="single") -> None:
        self._begin_idx = begin_idx
        self._end_idx = end_idx
        self._bond_type = bond_type

    def GetBeginAtomIdx(self) -> int:
        return self._begin_idx

    def GetEndAtomIdx(self) -> int:
        return self._end_idx

    def GetBondType(self):
        return self._bond_type


class _AliasFragment:
    def __init__(self, atoms, bonds) -> None:
        self._atoms = atoms
        self._bonds = bonds
        atom_map = {atom.GetIdx(): atom for atom in atoms}
        for bond in bonds:
            begin = atom_map[bond.GetBeginAtomIdx()]
            end = atom_map[bond.GetEndAtomIdx()]
            begin.add_neighbor(end)
            end.add_neighbor(begin)

    def GetAtoms(self):
        return list(self._atoms)

    def GetBonds(self):
        return list(self._bonds)

    def GetNumConformers(self) -> int:
        return 0


class _SubsetIterationAtoms(dict):
    def __iter__(self):
        return iter([0])


class RDKitConversionTailCoverageTest(unittest.TestCase):
    def test_xyz_unsupported_style_error_truncates_long_detail(self) -> None:
        adapter = RDKitAdapter()
        adapter._rdkit = (_FakeChem(), _NoComputeAllChem())
        model = MoleculeModel()
        atom_ids = [model.add_atom("C", float(index), 0.0) for index in range(7)]
        for index in range(6):
            model.bonds.append(Bond(atom_ids[index], atom_ids[index + 1], 1, style="wedge"))

        mol, atom_map = adapter._conversion_helper._build_rdkit_mol_with_map(
            model,
            unsupported_bond_styles={"wedge"},
        )

        self.assertIsNone(mol)
        self.assertIsNone(atom_map)
        self.assertIn("wedge (bond 4), ...", adapter.last_error)
        self.assertNotIn("wedge (bond 5)", adapter.last_error)

    def test_alias_fragment_allows_allchem_without_2d_coords_helper(self) -> None:
        adapter = RDKitAdapter()
        adapter._alias_smiles = {"Alias": "[*]C"}
        helper = adapter._conversion_helper
        anchor = _AliasAtom(0, "*", 0)
        carbon = _AliasAtom(1, "C", 6)
        fragment = _AliasFragment([anchor, carbon], [_AliasBond(0, 1)])
        model = MoleculeModel()
        scaffold_id = model.add_atom("C", 0.0, 0.0)
        alias_id = model.add_atom("Alias", 2.0, 3.0)
        model.add_bond(scaffold_id, alias_id, 1)

        attachment_idx, coord_map = helper._build_alias_fragment(
            "Alias",
            atom_id=alias_id,
            atom=model.atoms[alias_id],
            neighbors=[scaffold_id],
            model=model,
            formal_charge=0,
            radical_electrons=0,
            rw=_FakeRWMol(),
            Chem=_FakeChem({"[*]C": fragment}),
            AllChem=_NoComputeAllChem(),
        )

        self.assertEqual(attachment_idx, 0)
        self.assertEqual(coord_map, {0: (2.0, 3.0)})

    def test_conversion_skips_bond_when_atom_map_lacks_valid_endpoint(self) -> None:
        adapter = RDKitAdapter()
        adapter._rdkit = (_FakeChem(), _NoComputeAllChem())
        model = MoleculeModel()
        model.atoms = _SubsetIterationAtoms(
            {
                0: Atom("C", 0.0, 0.0),
                1: Atom("O", 1.0, 0.0),
            }
        )
        model.bonds = [Bond(0, 1, 1)]

        mol = adapter._build_conversion_rdkit_mol(model)

        self.assertIsNotNone(mol)
        self.assertEqual(len(mol.atoms), 1)
        self.assertEqual(mol.bonds, [])


class _Item:
    def __init__(self, kind=None, item_id=None, extra=None) -> None:
        self._data = {0: kind, 1: item_id}
        if extra is not None:
            self._data[2] = extra
        self.selected = False

    def data(self, key):
        return self._data.get(key)

    def setSelected(self, selected: bool) -> None:
        self.selected = selected


class _Scene:
    def __init__(self) -> None:
        self.selected_items = []
        self.clear_selection_calls = 0

    def selectedItems(self):
        return list(self.selected_items)

    def clearSelection(self) -> None:
        self.clear_selection_calls += 1
        self.selected_items = []


class _Event:
    def __init__(
        self,
        pos=None,
        *,
        button=None,
        modifiers=None,
    ) -> None:
        self._pos = QPointF(pos or QPointF())
        self._button = button if button is not None else Qt.MouseButton.LeftButton
        self._modifiers = modifiers if modifiers is not None else Qt.KeyboardModifier.NoModifier

    def button(self):
        return self._button

    def modifiers(self):
        return self._modifiers

    def position(self):
        return QPointF(self._pos)


class _SelectCanvas:
    DragMode = SimpleNamespace(RubberBandDrag="rubber")

    def __init__(self) -> None:
        self.scene_obj = _Scene()
        self.snapshot = None
        self.item = None
        self.preferred_item = None
        self.selection_hit = False
        self.atom_items = {}
        self.bond_items = {}
        self.atom_dots = {}
        self._handle_target = None
        self._active_handles = []
        self.clear_handles_calls = 0
        self.curved_handles = []
        self.pushed_commands = []
        self.updated_outline = 0

    def scene(self):
        return self.scene_obj

    def _selection_snapshot(self):
        return self.snapshot

    def bond_sets_for_atoms(self, atom_ids):
        return set(), set()

    def clear_handles(self) -> None:
        self.clear_handles_calls += 1

    def show_curved_handles(self, item) -> None:
        self.curved_handles.append(item)

    def item_at_event(self, event):
        return self.item

    def scene_pos_from_event(self, event):
        return event.position()

    def preferred_structure_item_at_scene_pos(self, pos):
        return self.preferred_item

    def selection_hit_test(self, pos, snapshot=None):
        return self.selection_hit

    def _push_command(self, command) -> None:
        self.pushed_commands.append(command)

    def scene_item_state(self, item):
        return {"id": id(item)}

    def suspend_selection_outline(self, suspended: bool) -> None:
        pass

    def shift_selection_outlines(self, dx: float, dy: float) -> None:
        pass

    def _update_selection_outline(self) -> None:
        self.updated_outline += 1


class _TextCanvas:
    def __init__(self) -> None:
        self.renderer = SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0))
        self.hover_atom_id = None
        self.hover_bond_id = None
        self.item = _Item("atom", "not-an-int")
        self.nearby_bond_calls = []
        self.nearby_atom_calls = []
        self.label_calls = []
        self.model = MoleculeModel(atoms={1: Atom("C", 5.0, 6.0)}, bonds=[])

    def scene_pos_from_event(self, event):
        return event.position()

    def item_at_event(self, event):
        return self.item

    def _find_bond_near(self, pos, radius):
        self.nearby_bond_calls.append((QPointF(pos), radius))
        return None

    def find_atom_near(self, x: float, y: float, radius: float):
        self.nearby_atom_calls.append((x, y, radius))
        return 1

    def get_atom_symbol(self) -> str:
        return "N"

    def add_or_update_atom_label(
        self,
        atom_id: int,
        text: str,
        *,
        clear_smiles: bool = True,
        record: bool = True,
        allow_merge: bool = True,
        show_carbon: bool = False,
    ) -> None:
        self.label_calls.append((atom_id, text, show_carbon, record))


class _MoveCanvas:
    def __init__(self) -> None:
        self.pushed_commands = []
        self.updated_outline = 0

    def _push_command(self, command) -> None:
        self.pushed_commands.append(command)

    def _update_selection_outline(self) -> None:
        self.updated_outline += 1


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for tool tests")
class ToolsTailCoverageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_select_tool_curved_handle_guards_and_release_edges(self) -> None:
        canvas = _SelectCanvas()
        tool = SelectTool(canvas)
        curved = _Item("curved_single")

        canvas.snapshot = SimpleNamespace(selected_atom_ids=set(), selection_items=[])
        self.assertFalse(tool._begin_curved_handle_toggle_or_drag(curved, QPointF(1.0, 1.0)))

        canvas.snapshot = SimpleNamespace(selected_atom_ids=set(), selection_items=[curved])
        canvas.scene_obj.selected_items = []
        self.assertIsNone(tool._selected_curved_item_for_handle_toggle(canvas.snapshot))

        canvas._handle_target = object()
        self.assertTrue(tool._begin_curved_handle_toggle_or_drag(curved, QPointF(1.0, 1.0)))
        self.assertEqual(canvas.clear_handles_calls, 1)

        tool._pending_curved_handle_item = None
        canvas._handle_target = curved
        canvas._active_handles = [object()]
        self.assertTrue(tool._begin_curved_handle_toggle_or_drag(curved, QPointF(1.0, 1.0)))
        self.assertTrue(tool.on_mouse_release(_Event(QPointF(1.0, 1.0))))
        self.assertEqual(canvas.clear_handles_calls, 2)
        self.assertEqual(canvas.curved_handles, [])

        tool._pending_curved_handle_item = curved
        tool._pending_curved_handle_action = "show"
        tool._start_pos = QPointF(2.0, 2.0)
        self.assertTrue(tool.on_mouse_move(_Event(QPointF(2.0, 2.0))))
        self.assertIs(tool._pending_curved_handle_item, curved)

        handle = _Item("handle")
        target = object()
        tool._active_handle = handle
        tool._handle_target = target
        tool._handle_before_state = {"state": 1}
        canvas.scene_item_state = lambda item: {"state": 1}
        self.assertTrue(tool.on_mouse_release(_Event(QPointF(2.0, 2.0))))
        self.assertEqual(canvas.pushed_commands, [])

        tool._pending_curved_handle_item = curved
        tool._pending_curved_handle_action = "noop"
        self.assertTrue(tool.on_mouse_release(_Event(QPointF(2.0, 2.0))))
        self.assertEqual(canvas.clear_handles_calls, 2)
        self.assertEqual(canvas.curved_handles, [])

        tool._drag_selection = True
        tool._start_pos = None
        self.assertTrue(tool.on_mouse_release(_Event(QPointF(2.0, 2.0))))
        self.assertFalse(tool._drag_selection)

        tool._start_pos = None
        self.assertFalse(tool.on_mouse_release(_Event(QPointF(2.0, 2.0))))

    def test_select_tool_rejects_unselectable_preferred_structure(self) -> None:
        canvas = _SelectCanvas()
        tool = SelectTool(canvas)
        canvas.preferred_item = _Item("atom", "bad")

        self.assertFalse(tool.on_mouse_press(_Event(QPointF(3.0, 4.0))))
        self.assertEqual(canvas.scene_obj.clear_selection_calls, 1)

    def test_text_tool_ignores_non_integer_item_atom_id_for_nearby_pick(self) -> None:
        canvas = _TextCanvas()
        tool = TextTool(canvas)

        self.assertTrue(tool.on_mouse_press(_Event(QPointF(5.0, 6.0))))

        self.assertEqual(len(canvas.nearby_bond_calls), 1)
        self.assertEqual(len(canvas.nearby_atom_calls), 1)
        self.assertEqual(canvas.label_calls, [(1, "N", True, True)])

    def test_move_tool_release_covers_idle_and_moved_without_target_states(self) -> None:
        canvas = _MoveCanvas()
        tool = MoveTool(canvas)

        self.assertTrue(tool.on_mouse_release(_Event(QPointF(1.0, 1.0))))

        tool._moved = True
        tool._drag_selection = False
        tool._drag_item = None
        tool._start_pos = None
        self.assertTrue(tool.on_mouse_release(_Event(QPointF(2.0, 2.0))))

        self.assertEqual(canvas.pushed_commands, [])
        self.assertEqual(canvas.updated_outline, 0)


if __name__ == "__main__":
    unittest.main()
