from __future__ import annotations

import os
import threading
import time
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.domain.document import MoleculeModel
from chemvas.features.insertion import (
    Molecule3DAtom,
    Molecule3DScene,
    MoleculeIdentifiers,
    RDKitResult,
)
from chemvas.ui.preview_3d import Preview3D
from chemvas.ui.preview_3d_painter import draw_footer
from chemvas.ui.preview_3d_worker import Preview3DWorker


class SlowSceneAdapter:
    last_error = None

    def __init__(self, *, fail: bool = False) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.fail = fail

    def is_loaded(self):
        return True

    def compute_identifiers(self, model):
        return MoleculeIdentifiers("CH4", 16.04, "C", "InChI=METHANE", "METHANE")

    def model_to_3d_scene_result(self, model, atom_annotations=None):
        self.entered.set()
        if not self.release.wait(4.0):
            raise RuntimeError("test did not release the 3D build")
        if self.fail:
            return RDKitResult(None, "Synthetic 3D failure")
        return RDKitResult(
            Molecule3DScene((Molecule3DAtom("C", 0.0, 0.0, 0.0),), ()), None
        )


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


def wait_until(predicate) -> None:
    deadline = time.monotonic() + 2.0
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


def make_model():
    model = MoleculeModel()
    model.add_atom("C", 0.0, 0.0)
    return model


def test_worker_publishes_identifiers_before_entering_3d_build() -> None:
    adapter = SlowSceneAdapter()
    adapter.release.set()
    events = []
    worker = Preview3DWorker(7, adapter, make_model(), None)
    worker.identifiers_ready.connect(
        lambda *args: events.append((args, adapter.entered.is_set()))
    )
    worker.finished.connect(lambda *args: events.append((args, True)))

    worker.run()

    assert len(events) == 2
    assert events[0] == ((7, "CH4", 16.04, "C", "InChI=METHANE", "METHANE"), False)
    assert events[1][0][0:6] == events[0][0]


@pytest.mark.parametrize("fail", [False, True])
def test_real_worker_shows_and_copies_identifiers_while_3d_is_blocked(app, fail):
    adapter = SlowSceneAdapter(fail=fail)
    preview = Preview3D(rdkit_adapter=adapter)
    preview._async_enabled = True
    preview.set_export_xyz_action(mock.Mock())
    preview.resize(560, 520)
    preview.show()
    try:
        with mock.patch("chemvas.ui.preview_3d.RDKitAdapter", return_value=adapter):
            preview.set_structure(make_model())
            preview._update_timer.stop()
            preview._rebuild_scene()
            wait_until(lambda: adapter.entered.is_set())
            # The worker cannot complete until this test releases its event.
            wait_until(lambda: preview._formula_text == "CH4")
            assert preview._preview_jobs
            assert preview._scene is None
            assert preview._message == "Updating 3D preview..."
            assert preview._mw_text == "16.04"
            assert not preview.export_xyz_button.isVisible()
            assert preview._copy_smiles_button.isVisible()
            preview._copy_smiles_button.click()
            assert app.clipboard().text() == "C"
            footers = []

            def record_footer(painter, rect, **kwargs):
                # A Mock's call history would retain the live QPainter past
                # paintEvent, then end it after its paint device is destroyed.
                # Keep only immutable content and perform the real painting.
                footers.append(kwargs["items"])
                draw_footer(painter, rect, **kwargs)

            with mock.patch(
                "chemvas.ui.preview_3d_painter.draw_footer", new=record_footer
            ):
                preview.grab()
            assert footers == [[("FORMULA", "CH4"), ("MW", "16.04")]]

            adapter.release.set()
            wait_until(lambda: not preview._preview_jobs)

        assert preview._formula_text == "CH4"
        assert preview._copy_smiles_button.isVisible()
        assert preview.export_xyz_button.isVisible() is not fail
        assert (preview._scene is None) is fail
        assert preview._message == ("Synthetic 3D failure" if fail else "")
    finally:
        adapter.release.set()
        preview.close()
        app.processEvents()


@pytest.mark.parametrize("invalidate", ["new_structure", "clear", "pause", "shutdown"])
def test_identifier_progress_rejects_obsolete_requests(app, invalidate):
    preview = Preview3D(rdkit_adapter=SlowSceneAdapter())
    try:
        preview.set_structure(make_model())
        preview._update_timer.stop()
        request_id = preview._preview_request_id
        preview._handle_preview_identifiers_ready(
            request_id, "CH4", 16.04, "C", "I", "K"
        )
        assert preview._formula_text == "CH4"
        if invalidate == "new_structure":
            model = make_model()
            model.atoms[0].x = 20.0
            preview.set_structure(model)
            preview._update_timer.stop()
            assert preview._formula_text == ""
            assert not preview._copy_smiles_button.isEnabled()
        elif invalidate == "clear":
            preview.clear_preview()
        elif invalidate == "pause":
            preview.pause_updates()
        else:
            preview.begin_shutdown()
        before = (preview._formula_text, preview._smiles_text, preview._message)

        preview._handle_preview_identifiers_ready(
            request_id, "STALE", 99.0, "S", "I", "K"
        )

        assert (preview._formula_text, preview._smiles_text, preview._message) == before
    finally:
        preview.close()


def test_synchronous_3d_failure_preserves_identifiers(app):
    adapter = SlowSceneAdapter(fail=True)
    adapter.release.set()
    preview = Preview3D(rdkit_adapter=adapter)
    try:
        preview._set_canvas_structure(make_model(), None)
        preview._update_timer.stop()
        preview._rebuild_scene()

        assert preview._scene is None
        assert preview._current_signature is None
        assert preview._formula_text == "CH4"
        assert preview._smiles_text == "C"
        assert preview._message == "Synthetic 3D failure"
    finally:
        preview.close()
