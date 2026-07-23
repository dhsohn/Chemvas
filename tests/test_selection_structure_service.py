from types import SimpleNamespace
from unittest import mock

from chemvas.domain.document import Atom, Bond
from chemvas.features.selection import StructureHit
from chemvas.ui.canvas_atom_graphics_state import set_atom_dots_for, set_atom_items_for
from chemvas.ui.canvas_bond_graphics_state import set_bond_items_for
from chemvas.ui.canvas_scene_items_state import set_scene_item_collection_for
from chemvas.ui.selection_structure_service import SelectionStructureService

from tests.runtime_services import canvas_runtime_services


class _FakeItem:
    def __init__(self, kind=None, *, data1=None, data2=None, selected=False) -> None:
        self._data = {0: kind, 1: data1, 2: data2}
        self._selected = selected

    def data(self, key):
        return self._data.get(key)

    def setSelected(self, selected: bool) -> None:
        self._selected = selected

    def isSelected(self) -> bool:
        return self._selected


class _FakeScene:
    def __init__(self, selected_items=None) -> None:
        self.selected_items = list(selected_items or [])
        self.clear_selection_calls = 0

    def clearSelection(self) -> None:
        self.clear_selection_calls += 1
        for item in self.selected_items:
            item.setSelected(False)


def _make_canvas(**overrides):
    scene = overrides.pop("scene", _FakeScene())
    canvas = SimpleNamespace(
        model=overrides.pop("model", SimpleNamespace(atoms={}, bonds=[])),
        services=canvas_runtime_services(
            graph_service=SimpleNamespace(
                expand_connected_atoms=overrides.pop(
                    "expand_connected_atoms",
                    mock.Mock(side_effect=lambda ids: set(ids)),
                )
            ),
            selection_controller=overrides.pop(
                "selection_controller", SimpleNamespace()
            ),
        ),
        scene=lambda: scene,
    )
    set_atom_items_for(canvas, overrides.pop("atom_items", {}))
    set_atom_dots_for(canvas, overrides.pop("atom_dots", {}))
    set_bond_items_for(canvas, overrides.pop("bond_items", {}))
    set_scene_item_collection_for(canvas, "ring_items", overrides.pop("ring_items", []))
    return canvas


def _structure_service(canvas) -> SelectionStructureService:
    return SelectionStructureService(
        canvas,
        graph_service=canvas.services.graph_service,
    )


def test_structure_hit_and_item_resolution_cover_atoms_bonds_and_rings() -> None:
    atom_item = _FakeItem("atom", data1=1)
    atom_dot = _FakeItem("atom", data1=2)
    bond_item = _FakeItem("bond", data1=0)
    ring_item = _FakeItem("ring", data2=[1, 2])
    service = _structure_service(
        _make_canvas(
            model=SimpleNamespace(atoms={}, bonds=[Bond(1, 2, 1), None]),
            atom_items={1: atom_item},
            atom_dots={2: atom_dot},
            bond_items={0: [bond_item]},
        )
    )

    assert service.structure_hit_from_item(None) == (None, None, None)
    assert service.structure_hit_from_item(atom_item)[0] == StructureHit(
        kind="atom", id=1
    )
    assert service.structure_hit_from_item(_FakeItem("atom", data1="bad")) == (
        None,
        None,
        None,
    )
    assert service.structure_hit_from_item(bond_item) == (
        StructureHit(kind="bond", id=0),
        (1, 2),
        None,
    )
    assert service.structure_hit_from_item(_FakeItem("bond", data1=1)) == (
        None,
        None,
        None,
    )
    assert service.structure_hit_from_item(ring_item) == (
        StructureHit(kind="ring"),
        None,
        [1, 2],
    )
    assert service.structure_hit_from_item(_FakeItem("note"))[0] == StructureHit(
        kind="other"
    )
    assert service.structure_item_for_hit(StructureHit(kind="atom", id=1)) is atom_item
    assert service.structure_item_for_hit(StructureHit(kind="atom", id=2)) is atom_dot
    assert service.structure_item_for_hit(StructureHit(kind="bond", id=0)) is bond_item
    assert service.structure_item_for_hit(StructureHit(kind="ring")) is None


def test_selection_targets_for_item_resolves_graphics_items_only() -> None:
    atom_item = _FakeItem("atom", data1=1)
    bond_item = _FakeItem("bond", data1=0)
    overlay_item = _FakeItem("orbital")
    service = _structure_service(
        _make_canvas(atom_items={1: atom_item}, bond_items={0: [bond_item, None]})
    )

    assert service.selection_targets_for_item(_FakeItem("atom", data1=1)) == [atom_item]
    assert service.selection_targets_for_item(_FakeItem("bond", data1=0)) == [bond_item]
    assert service.selection_targets_for_item(overlay_item) == [overlay_item]
    assert service.selection_targets_for_item(None) == []
    assert service.selection_targets_for_item(_FakeItem("atom", data1="bad")) == []
    assert service.selection_targets_for_item(_FakeItem("unknown")) == []


def test_select_structure_for_item_selects_connected_atoms_bonds_and_rings() -> None:
    atom_item = _FakeItem("atom", data1=1)
    atom_item_2 = _FakeItem("atom", data1=2)
    bond_graphic = _FakeItem("bond")
    ring_item = _FakeItem("ring", data2=[1, 2])
    unrelated_ring_item = _FakeItem("ring", data2=[1, 3])
    scene = _FakeScene(
        [atom_item, atom_item_2, bond_graphic, ring_item, unrelated_ring_item]
    )
    selection_controller = SimpleNamespace(clear_note_selection=mock.Mock())
    service = _structure_service(
        _make_canvas(
            scene=scene,
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("O", 1.0, 0.0),
                    3: Atom("N", 2.0, 0.0),
                },
                bonds=[Bond(1, 2, 1), Bond(1, 3, 1)],
            ),
            atom_items={1: atom_item, 2: atom_item_2},
            bond_items={0: [bond_graphic], 1: [_FakeItem("bond")]},
            ring_items=[ring_item, unrelated_ring_item],
            expand_connected_atoms=mock.Mock(return_value={1, 2}),
            selection_controller=selection_controller,
        )
    )

    result = service.select_structure_for_item(_FakeItem("atom", data1=1))

    assert result.selected
    assert result.update_outline
    assert scene.clear_selection_calls == 1
    assert atom_item.isSelected()
    assert atom_item_2.isSelected()
    assert bond_graphic.isSelected()
    assert ring_item.isSelected()
    assert not unrelated_ring_item.isSelected()
    selection_controller.clear_note_selection.assert_called_once_with()


def test_select_structure_for_item_selects_overlay_without_outline_refresh() -> None:
    note_item = _FakeItem("note")
    scene = _FakeScene([note_item])
    selection_controller = SimpleNamespace(clear_note_selection=mock.Mock())
    service = _structure_service(
        _make_canvas(scene=scene, selection_controller=selection_controller)
    )

    result = service.select_structure_for_item(note_item)

    assert result.selected
    assert not result.update_outline
    assert scene.clear_selection_calls == 1
    assert note_item.isSelected()
    selection_controller.clear_note_selection.assert_called_once_with()
