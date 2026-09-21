"""Parameterized graphics cases borrow one application, never recreate it."""

import gc
import weakref

import pytest
from PyQt6 import sip
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.document_cli_shared import offscreen_document_scene
from chemvas.features.document_composition import compose_document_state

_applications = []


@pytest.mark.parametrize("iteration", range(3))
def test_application_outlives_graphics_cases(qt_application, iteration):
    gc.collect()
    assert all(reference() is qt_application for reference in _applications)
    _applications.append(weakref.ref(qt_application))
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [{"id": 0, "element": "N", "x": iteration * 10, "y": 0}],
            "bonds": [],
        }
    )
    with offscreen_document_scene(state, command="lifetime-test") as context:
        scene = context.scene
        assert scene.items()
        assert QApplication.instance() is qt_application
    assert sip.isdeleted(scene)
    assert not sip.isdeleted(qt_application)
