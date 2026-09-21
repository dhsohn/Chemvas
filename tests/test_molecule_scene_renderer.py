"""The editor and standalone scenes share one model-preserving drawing owner."""

from dataclasses import asdict

import pytest
from PyQt6.QtCore import QEvent, QPointF
from PyQt6.QtWidgets import QApplication, QGraphicsScene

from chemvas.adapters.qt.renderer import Renderer
from chemvas.domain.document import Atom, Bond, MoleculeModel
from chemvas.features.graph import build_bond_adjacency_index
from chemvas.ui.molecule_scene_renderer import render_molecule
from chemvas.ui.scene_graphics_operations import detach_graphics_item
from chemvas.ui.scene_render_context import SceneRenderState
from chemvas.ui.scene_rendering import build_scene_render_context


@pytest.fixture
def make_context(qt_application):
    scenes = []

    def build(model):
        state = SceneRenderState()
        state.graph_state.atom_neighbors, state.graph_state.atom_bond_ids = (
            build_bond_adjacency_index(model.atoms, model.bonds)
        )
        scene = QGraphicsScene()
        scenes.append(scene)
        return build_scene_render_context(
            scene_provider=lambda: scene,
            model_provider=lambda: model,
            renderer=Renderer(),
            state=state,
        )

    yield build
    for scene in scenes:
        scene.deleteLater()
        qt_application.sendPostedEvents(scene, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize(
    "label,explicit,style,order",
    [
        ("C", False, "single", 1),
        ("c", True, "single", 1),
        ("NH2", False, "single", 1),
        ("CF3", False, "double", 2),
        ("OMe", False, "double_outer", 2),
        ("Ph3P", False, "triple", 3),
        ("O", False, "dotted", 1),
        ("N", False, "wedge", 1),
        ("Cl", False, "hash", 1),
        ("NH", False, "bold_center", 2),
        ("O", False, "double_either", 2),
        ("N", False, "dotted_double_outer", 2),
    ],
)
def test_model_draws_without_any_widget_or_editor_state(
    make_context, label, explicit, style, order
):
    model = MoleculeModel(
        atoms={0: Atom(label, 0, 0, explicit_label=explicit), 1: Atom("C", 60, 0)},
        bonds=[Bond(0, 1, order, style=style)],
    )
    before = asdict(model)
    context = make_context(model)

    render_molecule(context)

    assert asdict(model) == before
    assert not QApplication.allWidgets()
    assert not hasattr(context.state, "history_service")
    assert not hasattr(context.state, "input_view_state")
    assert not hasattr(context, "services")
    assert context.state.bond_graphics_state.bond_items[0]
    assert 1 in context.state.atom_graphics_state.atom_dots
    if label.upper() == "C" and not explicit:
        assert 0 in context.state.atom_graphics_state.atom_dots
    else:
        item = context.state.atom_graphics_state.atom_items[0]
        assert item.scene() is context.scene
        assert item.toPlainText()


def test_live_context_reads_replaced_model_and_replaced_graphics_containers(
    make_context,
):
    first = MoleculeModel(atoms={0: Atom("N", 0, 0)})
    second = MoleculeModel(atoms={0: Atom("O", 18, 25)})
    owner = [first]
    context = make_context(first)
    context.model_provider = lambda: owner[0]
    render_molecule(context)
    old_item = context.state.atom_graphics_state.atom_items[0]

    context.scene.removeItem(old_item)
    context.state.atom_graphics_state.atom_items = {}
    owner[0] = second
    render_molecule(context)

    item = context.state.atom_graphics_state.atom_items[0]
    assert item is not old_item
    assert item.toPlainText() == "O"
    assert item.scene() is context.scene
    assert context.geometry.current_atom_coords_3d(0) == (18, 25, 0)
    assert first.atoms[0].element == "N"


def test_mark_auto_position_uses_the_shared_label_geometry(make_context):
    context = make_context(MoleculeModel(atoms={0: Atom("NH2", 0, 0)}))
    render_molecule(context)
    offset = context.geometry.mark_offset_from_click(0, QPointF(), kind="plus")
    assert offset.x() > 0
    assert offset.y() < 0
    assert context.geometry.mark_offset_from_click(99, QPointF(), kind="plus").isNull()


def test_graphics_cleanup_tolerates_wrappers_deleted_by_qt_scene_clear(make_context):
    context = make_context(
        MoleculeModel(
            atoms={0: Atom("C", 0, 0), 1: Atom("C", 40, 0)},
            bonds=[Bond(0, 1)],
        )
    )
    render_molecule(context)
    old_bond_item = context.state.bond_graphics_state.bond_items[0][0]
    context.scene.clear()

    context.atom_labels.remove_carbon_dot(0)
    assert 0 not in context.state.atom_graphics_state.atom_dots
    assert detach_graphics_item(context.scene, old_bond_item) is False
