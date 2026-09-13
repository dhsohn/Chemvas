"""Shared standalone shown-canvas fixtures for native geometry workflows."""

import math

import pytest
from PyQt6.QtWidgets import QApplication

from chemvas.ui.structure_mutation_access import add_atom_for, add_bond_for
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    view.resize(800, 600)
    view.show()
    app.processEvents()
    yield view
    view.services.document.canvas_scene_reset_service.clear_scene()
    view.close()
    app.processEvents()


def _plain_ring(canvas, size=6, angle=0.0, offset=0.0):
    ids = [
        add_atom_for(
            canvas,
            "C",
            offset + 20 * math.cos(angle + index * 2 * math.pi / size),
            20 * math.sin(angle + index * 2 * math.pi / size),
        )
        for index in range(size)
    ]
    bonds = [
        add_bond_for(canvas, ids[index], ids[(index + 1) % size])
        for index in range(size)
    ]
    canvas.services.structure.structure_build_service.render_model()
    return ids, bonds
