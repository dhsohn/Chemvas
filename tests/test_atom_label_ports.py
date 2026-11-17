"""Unrecorded label edits run through named ports; recording needs a canvas."""

from types import SimpleNamespace

import pytest

from chemvas.domain.document import MoleculeModel
from chemvas.ui.molecule.atom_label_merge_service import AtomLabelMergeService
from chemvas.ui.molecule.atom_label_service import AtomLabelPorts, AtomLabelService


class _Drawing:
    def __init__(self):
        self.drawn = []

    def atom_item_for_id(self, atom_id):
        return None

    def implicit_carbon_dot_brush(self):
        return None

    def ensure_carbon_dot(self, atom_id):
        pass

    def remove_carbon_dot(self, atom_id):
        pass

    def position_label(self, item, x, y):
        pass

    def relayout_atom_label(self, atom_id):
        return False

    def relayout_atom_labels(self, atom_ids, *, skip_bond_ids=()):
        pass

    def draw_atom(self, atom_id, *, visible=None):
        self.drawn.append((atom_id, visible))


def _service():
    model = MoleculeModel()
    drawing = _Drawing()
    # The merge service still reads a canvas-shaped holder; it is not under test.
    holder = SimpleNamespace(
        model=model,
        renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
    )
    graph = type("Graph", (), {"rebuild_bond_adjacency": lambda self: None})()
    service = AtomLabelService(
        AtomLabelPorts(
            model=lambda: model,
            drawing=drawing,
            select_items=lambda items: None,
            hovered_atom_id=lambda: None,
            add_atom=model.add_atom,
        ),
        graph_service=graph,
        merge_service=AtomLabelMergeService(
            holder, graph_service=graph, capture_history=False
        ),
        connection_allowed=lambda ids: True,
    )
    return service, model, drawing


def test_unrecorded_label_edits_use_only_the_ports():
    service, model, drawing = _service()
    atom_id = service.add_labelled_atom("N", 10.0, 20.0, record=False)
    assert (model.atoms[atom_id].element, model.atoms[atom_id].explicit_label) == (
        "N",
        False,
    )
    service.add_or_update_atom_label(atom_id, "C", record=False, show_carbon=True)
    assert model.atoms[atom_id].explicit_label is True
    assert drawing.drawn == [(atom_id, True), (atom_id, True)]
    assert service.atom_label_prompt_initial(atom_id) == "C"


def test_recorded_label_edits_without_a_canvas_are_refused_by_name():
    service, model, _drawing = _service()
    atom_id = model.add_atom("C", 0.0, 0.0)
    with pytest.raises(RuntimeError, match="records no desktop history"):
        service.add_or_update_atom_label(atom_id, "O")
