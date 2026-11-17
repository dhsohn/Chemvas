"""Structure edits run through named ports; only recording needs a canvas."""

import pytest

from chemvas.domain.document import MoleculeModel
from chemvas.ui.molecule.structure_build_committer import (
    StructureBuildCommitter,
    StructureEditPorts,
)


class _Point:
    def __init__(self, x, y):
        self._x, self._y = x, y

    def x(self):
        return self._x

    def y(self):
        return self._y


def _committer():
    model = MoleculeModel()
    calls = []
    ports = StructureEditPorts(
        model=lambda: model,
        bond_length=lambda: 20.0,
        atom_bond_ids=dict,
        add_atom=model.add_atom,
        add_bond=model.add_bond,
        add_bond_graphics=lambda bond_id: calls.append(("graphics", bond_id)),
        update_bond_geometry=lambda bond_id: calls.append(("geometry", bond_id)),
        add_or_update_atom_label=lambda atom_id, text, **kwargs: calls.append(
            ("label", atom_id, text, kwargs)
        ),
        create_ring_fill_item=lambda points, atom_ids: ("fill", tuple(atom_ids)),
        attach_scene_item=lambda item: calls.append(("attach", item)),
    )
    return StructureBuildCommitter(ports), model, calls


def test_ring_edits_use_only_the_ports():
    committer, model, calls = _committer()
    points = [_Point(0, 0), _Point(20, 0), _Point(10, 17)]
    atom_ids = committer.add_ring_from_points(points, ["C", "N", "C"])
    assert len(model.atoms) == 3 and len([b for b in model.bonds if b]) == 3
    assert committer.bond_id_between(atom_ids[0], atom_ids[1]) is not None
    # A point within a fifth of a bond of an existing atom merges into it.
    merge = [(atom_ids[0], 0.0, 0.0)]
    assert committer.add_atom_with_merge(_Point(3, 0), "C", merge) == atom_ids[0]
    assert ("attach", ("fill", tuple(atom_ids))) in calls
    assert ("graphics", 0) in calls
    assert (
        "label",
        atom_ids[1],
        "N",
        {"record": False, "allow_merge": False, "show_carbon": False},
    ) in calls


def test_recording_without_a_canvas_is_refused_by_name():
    committer, _model, _calls = _committer()
    with pytest.raises(RuntimeError, match="records no desktop history"):
        committer.begin_recorded_change()
