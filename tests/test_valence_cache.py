from copy import deepcopy
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtGui import QImage, QPainter

from chemvas.adapters.qt.renderer import Renderer
from chemvas.domain.document import Bond, MoleculeModel
from chemvas.features.rendering import ValenceWarningCache, overvalent_atom_ids
from chemvas.ui.canvas.canvas_view import CanvasView
from chemvas.ui.transactions.document import document_transaction


def _nitrogen():
    model = MoleculeModel()
    model.add_atom("N", 0, 0)
    for index in range(4):
        atom_id = model.add_atom("H", 20 * (index + 1), 0)
        model.add_bond(0, atom_id)
    return model


def test_unchanged_foreground_reuses_warnings_and_geometry_edits_do_not_invalidate(
    qt_application,
):
    canvas = CanvasView(renderer=Renderer())
    canvas.model = _nitrogen()
    image = QImage(300, 100, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        with patch(
            "chemvas.features.rendering.valence.overvalent_atom_ids",
            wraps=overvalent_atom_ids,
        ) as calculate:
            for offset in range(30):
                canvas.model.atoms[0].x = offset
                canvas.model.atoms[0].color = "#ff0000"
                canvas.drawForeground(painter, canvas.sceneRect())
            calculate.assert_called_once_with(canvas.model)
        assert canvas.runtime_state.valence_warnings.warnings_for(canvas.model) == {0}
    finally:
        painter.end()
        canvas.deleteLater()
        QCoreApplication.sendPostedEvents(canvas, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize(
    "edit,expected",
    [
        ("charge", set()),
        ("radical", set()),
        ("element", set()),
        ("neighbor", set()),
        ("style", set()),
        ("order", {0, 1}),
        ("delete_bond", set()),
        ("rewire", {1}),
        ("delete_atom", set()),
    ],
)
def test_direct_mutations_and_restored_values_cannot_reuse_stale_warnings(
    edit, expected
):
    model = _nitrogen()
    original = deepcopy(model)
    cache = ValenceWarningCache()
    assert cache.warnings_for(model) == {0}
    if edit == "charge":
        model.atom_annotations[0] = {"formal_charge": 1}
    elif edit == "radical":
        model.atom_annotations[0] = {"radical_electrons": 1}
    elif edit == "element":
        model.atoms[0].element = "C"
    elif edit == "neighbor":
        model.atoms[1].element = "Zn"
    elif edit == "style":
        model.bonds[0].style = "dotted"
    elif edit == "order":
        model.bonds[0].order = 2
    elif edit == "delete_bond":
        model.bonds[0] = None
    elif edit == "rewire":
        model.bonds[-1].a = 1
    elif edit == "delete_atom":
        del model.atoms[0]
        model.bonds.clear()
    assert cache.warnings_for(model) == expected
    model.atoms = original.atoms
    model.bonds = original.bonds
    model.atom_annotations = original.atom_annotations
    assert cache.warnings_for(model) == {0}
    assert cache.warnings_for(MoleculeModel()) == set()
    assert cache.warnings_for(model) == {0}


def test_cache_retries_after_failure_without_publishing_a_wrong_key():
    model = _nitrogen()
    cache = ValenceWarningCache()
    assert cache.warnings_for(model) == {0}
    model.atom_annotations[0] = {"formal_charge": 1}
    with patch(
        "chemvas.features.rendering.valence.overvalent_atom_ids",
        side_effect=RuntimeError("injected"),
    ):
        with pytest.raises(RuntimeError, match="injected"):
            cache.warnings_for(model)
    assert cache.warnings_for(model) == set()


def test_adding_and_replacing_graphs_never_aliases_a_cached_version():
    cache = ValenceWarningCache()
    model = _nitrogen()
    model.bonds.pop()
    assert cache.warnings_for(model) == set()
    model.bonds.append(Bond(0, 4))
    assert cache.warnings_for(model) == {0}
    other = deepcopy(model)
    other.atom_annotations = {0: {"formal_charge": 1}}
    assert cache.warnings_for(other) == set()
    # In-place annotation changes, without any graph-index version change.
    other.atom_annotations[0]["formal_charge"] = 0
    assert cache.warnings_for(other) == {0}


def test_exact_transaction_rollback_rechecks_warnings_computed_mid_edit(qt_application):
    canvas = CanvasView(renderer=Renderer())
    canvas.model = _nitrogen()
    cache = canvas.runtime_state.valence_warnings
    original = deepcopy(canvas.model)
    history = canvas.services.history_service.capture_stack_snapshot()
    try:
        assert cache.warnings_for(canvas.model) == {0}
        with pytest.raises(RuntimeError, match="injected"):
            with document_transaction(
                canvas, history_service=canvas.services.history_service
            ):
                canvas.model.atom_annotations[0] = {"formal_charge": 1}
                assert cache.warnings_for(canvas.model) == set()
                raise RuntimeError("injected")
        assert canvas.model == original
        assert canvas.services.history_service.capture_stack_snapshot() == history
        assert cache.warnings_for(canvas.model) == {0}
    finally:
        canvas.deleteLater()
        QCoreApplication.sendPostedEvents(canvas, QEvent.Type.DeferredDelete)
