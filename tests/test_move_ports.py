"""A move runs through named ports: no canvas, scene or renderer needed."""

from chemvas.domain.document import MoleculeModel
from chemvas.ui.canvas.canvas_mark_registry import CanvasMarkRegistry
from chemvas.ui.canvas.canvas_move_controller import CanvasMoveController, MovePorts


class _Point:
    def __init__(self, x, y):
        self._x, self._y = x, y

    def x(self):
        return self._x

    def y(self):
        return self._y


class _Mark:
    def __init__(self, x, y):
        self.center = _Point(x, y)

    def moveBy(self, dx, dy):
        self.center = _Point(self.center.x() + dx, self.center.y() + dy)


def test_move_and_place_atoms_through_ports_only():
    model = MoleculeModel()
    a = model.add_atom("C", 0.0, 0.0)
    b = model.add_atom("C", 20.0, 0.0)
    model.add_bond(a, b, 1)
    marks = CanvasMarkRegistry()
    mark = _Mark(5.0, -10.0)
    marks.add_for_atom(a, mark)
    geometry_refreshes, ring_refreshes, index_dirty = [], [], []

    def unused(*_args):
        raise AssertionError("not part of an atom move")

    controller = CanvasMoveController(
        MovePorts(
            model=lambda: model,
            atom_bond_ids=lambda: {a: {0}, b: {0}},
            bond_items=lambda _bond_id: (),
            update_bond_geometry=lambda bond_id, rebuild: geometry_refreshes.append(
                (bond_id, rebuild)
            ),
            redraw_bond=lambda _bond_id: False,
            redraw_connected_bonds=lambda _atom_id, _skip: None,
            ring_items=lambda: (),
            update_ring_fills_for_atoms=ring_refreshes.append,
            update_selection_outline=lambda: None,
            handles_for=lambda _item: (),
            atom_label=lambda _atom_id: None,
            atom_dot=lambda _atom_id: None,
            position_label=unused,
            marks=lambda: marks,
            mark_center=lambda item: item.center,
            set_mark_center=lambda item, center: setattr(item, "center", center),
            coords_3d=dict,
            bond_length=lambda: 20.0,
            projection_center_3d=lambda: None,
            arrows=unused,
            shape_record=unused,
            set_shape_record=unused,
            ts_bracket_record=unused,
            set_ts_bracket_record=unused,
        ),
        hit_testing_service=type(
            "Index",
            (),
            {"mark_spatial_index_dirty": lambda self: index_dirty.append(1)},
        )(),
        point_factory=_Point,
    )
    controller.move_atoms({a}, 3.0, 4.0, bond_ids=set(), update_selection=False)
    assert (model.atoms[a].x, model.atoms[a].y) == (3.0, 4.0)
    assert (mark.center.x(), mark.center.y()) == (8.0, -6.0)
    assert geometry_refreshes == [(0, False)]
    controller.set_atom_positions({b: (40.0, 0.0)}, update_selection=False)
    assert (model.atoms[b].x, model.atoms[b].y) == (40.0, 0.0)
    assert geometry_refreshes[-1] == (0, True)
    assert ring_refreshes == [{b}]
    assert index_dirty
