from __future__ import annotations

from types import SimpleNamespace

import chemvas.ui.tool_controller_factory as tool_controller_factory
from chemvas.ui.tool_controller_factory import build_tool_controller


class _StubToolController:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs


def test_build_tool_controller_injects_canvas_ports(monkeypatch) -> None:
    monkeypatch.setattr(tool_controller_factory, "ToolController", _StubToolController)
    canvas = SimpleNamespace()
    canvas.tool_settings_state = SimpleNamespace(atom_symbol="Br")
    canvas.setDragMode = object()
    canvas.DragMode = SimpleNamespace(RubberBandDrag="rubber")
    graph_service = SimpleNamespace(bond_sets_for_atoms=object())
    collaborators = {
        "hit_testing_service": object(),
        "selection_controller": object(),
        "note_controller": object(),
        "handle_controller": object(),
        "selection_rotation_controller": object(),
        "scene_delete_controller": object(),
        "scene_transform_controller": object(),
        "style_controller": object(),
        "color_mutation_service": object(),
        "history_service": object(),
    }

    controller = build_tool_controller(
        canvas,
        graph_service=graph_service,
        **collaborators,
    )

    assert isinstance(controller, _StubToolController)
    assert controller.args == (canvas,)
    for name, value in collaborators.items():
        assert controller.kwargs[name] is value
    assert controller.kwargs["bond_sets_for_atoms"] is graph_service.bond_sets_for_atoms
    assert callable(controller.kwargs["selected_scene_items"])
    assert callable(controller.kwargs["select_single_structure_item"])
    assert controller.kwargs["atom_symbol_provider"]() == "Br"
    assert controller.kwargs["set_drag_mode"] is canvas.setDragMode
    assert controller.kwargs["rubber_band_drag_mode"] is canvas.DragMode.RubberBandDrag
