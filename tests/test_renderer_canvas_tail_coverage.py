from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest import mock

from chemvas.ui.selection.selection_controller import SelectionController
from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chemvas.ui.canvas.canvas_atom_graphics_state import CanvasAtomGraphicsState
from chemvas.ui.canvas.canvas_bond_graphics_state import CanvasBondGraphicsState
from chemvas.ui.canvas.canvas_group_state import CanvasGroupState
from chemvas.ui.scene.scene_clipboard_transaction_logic import (
    translated_scene_item_state,
)
from chemvas.ui.selection.selection_queries import append_selected_item_ids


class _DataItem:
    def __init__(self, values: dict[int, object]) -> None:
        self._values = values

    def data(self, key: int):
        return self._values.get(key)


class RendererCanvasTailCoverageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_selection_translation_helpers_cover_missing_item_branches(self) -> None:
        atom_ids: set[int] = set()
        bond_ids: set[int] = set()
        append_selected_item_ids(
            SimpleNamespace(),
            atom_ids,
            bond_ids,
            _DataItem({0: "ring", 2: ("not", "a", "list")}),
        )
        self.assertEqual(atom_ids, set())
        self.assertEqual(bond_ids, set())

        translated_note = translated_scene_item_state(
            {"kind": "note", "text": "unchanged"},
            dx=4.0,
            dy=5.0,
            atom_id_map={},
        )
        self.assertEqual(translated_note, {"kind": "note", "text": "unchanged"})

        scene = SimpleNamespace(
            clearSelection=mock.Mock(), blockSignals=mock.Mock(return_value=False)
        )
        selection_controller = SimpleNamespace(update_selection_outline=mock.Mock())
        restore_view = SimpleNamespace(
            scene=lambda: scene,
            runtime_state=canvas_runtime_state(
                atom_graphics_state=CanvasAtomGraphicsState(),
                bond_graphics_state=CanvasBondGraphicsState(),
                group_state=CanvasGroupState(),
            ),
            services=canvas_runtime_services(selection=selection_controller),
        )
        owner = SelectionController(
            restore_view, graph_service=None, hit_testing_service=None
        )
        owner.update_selection_outline = selection_controller.update_selection_outline
        owner.restore_ids({99}, {42})
        scene.clearSelection.assert_called_once_with()
        selection_controller.update_selection_outline.assert_called_once_with()
