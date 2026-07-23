import os
import tempfile
import unittest
from json import dumps
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None
    QTest = None
    Qt = None
    QPointF = None

if QApplication is not None:
    from chemvas.bootstrap.main_window import build_main_window
    from chemvas.core.document_io import read_document
    from chemvas.core.rdkit_adapter import (
        Molecule3DAtom,
        Molecule3DBond,
        Molecule3DScene,
        MoleculeIdentifiers,
    )
    from chemvas.domain.document import MoleculeModel
    from chemvas.features.insertion import RDKitResult
    from chemvas.ui.bond_graphics_access import add_bond_graphics_for
    from chemvas.ui.canvas_atom_graphics_state import atom_items_for
    from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id
    from chemvas.ui.canvas_document_metadata_state import document_file_path_for
    from chemvas.ui.canvas_history_state import history_state_for
    from chemvas.ui.canvas_insert_state import insert_state_for
    from chemvas.ui.canvas_mark_registry import mark_registry_for
    from chemvas.ui.canvas_scene_items_state import (
        arrow_items_for,
        mark_items_for,
        note_items_for,
        orbital_items_for,
        ring_items_for,
    )
    from chemvas.ui.canvas_scene_reset_access import clear_scene_for
    from chemvas.ui.canvas_service_access import canvas_services_for
    from chemvas.ui.canvas_smiles_input_state import (
        last_smiles_input_for,
        set_last_smiles_input_for,
    )
    from chemvas.ui.canvas_tool_settings_state import (
        set_tool_setting_for,
        tool_settings_state_for,
    )
    from chemvas.ui.canvas_window_access import (
        restore_canvas_state_for,
        save_canvas_to_file_for,
        snapshot_canvas_state_for,
    )
    from chemvas.ui.main_window_ports import (
        active_canvas_for_window,
        preview_for_window,
        preview_window_for_window,
        services_for_window,
    )
    from chemvas.ui.mark_item_access import mark_center_for
    from chemvas.ui.preview_3d_painter import preview_overlay_font
    from chemvas.ui.scene_decoration_access import (
        add_arrow_for,
        add_mark_for,
        add_mark_for_atom_for,
        add_orbital_for,
        add_ts_bracket_from_points_for,
    )
    from chemvas.ui.structure_mutation_access import (
        add_atom_for,
        add_benzene_ring_for,
        add_bond_between_points_for,
        add_bond_for,
    )
    from chemvas.ui.structure_payload_access import build_3d_conversion_payload_for


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for GUI tests")
class GuiDocumentAndTemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = build_main_window()
        self.window.show()
        active_canvas_for_window(self.window).setFocus()
        self.app.processEvents()
        QTest.qWait(20)

    def tearDown(self) -> None:
        for canvas in self.window.tab_references.all_canvases():
            services_for_window(self.window).canvas_document_service.mark_clean(canvas)
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def _set_current_file_path(self, path: str | None) -> None:
        services_for_window(self.window).canvas_document_service.set_file_path(
            active_canvas_for_window(self.window),
            path,
        )

    def _current_file_path(self) -> str | None:
        return document_file_path_for(active_canvas_for_window(self.window))

    def _hover_scene_point(self, point: QPointF) -> None:
        viewport_pos = active_canvas_for_window(self.window).mapFromScene(point)
        QTest.mouseMove(active_canvas_for_window(self.window).viewport(), viewport_pos)
        self.app.processEvents()
        if insert_state_for(active_canvas_for_window(self.window)).template_active:
            active_canvas_for_window(
                self.window
            ).services.structure.insert_controller.render_template_preview(point)
        if insert_state_for(active_canvas_for_window(self.window)).smiles_active:
            active_canvas_for_window(
                self.window
            ).services.structure.insert_controller.render_smiles_preview(point)
        self.app.processEvents()
        QTest.qWait(10)

    def _click_scene_point(self, point: QPointF) -> None:
        viewport_pos = active_canvas_for_window(self.window).mapFromScene(point)
        QTest.mouseClick(
            active_canvas_for_window(self.window).viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            viewport_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

    def _press_key(self, key: int, modifiers=None) -> None:
        if modifiers is None:
            modifiers = Qt.KeyboardModifier.NoModifier
        QTest.keyClick(active_canvas_for_window(self.window), key, modifiers)
        self.app.processEvents()
        QTest.qWait(10)

    def _template_handler(self, label: str):
        entries = dict(
            services_for_window(self.window).tool_routing_service.template_entries(
                self.window
            )
        )
        return entries[label]

    def _document_actions(self):
        return services_for_window(self.window).document_action_service

    @staticmethod
    def _canvas_note_text(canvas) -> str:
        return "\n".join(item.toPlainText() for item in note_items_for(canvas))

    def test_save_canvas_appends_extension_and_writes_document_payload(self) -> None:
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        canvas_services_for(
            active_canvas_for_window(self.window)
        ).interaction.note_controller.create_text_note(QPointF(60.0, 10.0), "Scheme")
        add_mark_for(
            active_canvas_for_window(self.window),
            QPointF(20.0, 20.0),
            kind="plus",
            atom_id=0,
            record=False,
        )
        add_arrow_for(
            active_canvas_for_window(self.window),
            QPointF(-40.0, -20.0),
            QPointF(40.0, -20.0),
            "reaction",
        )
        set_last_smiles_input_for(active_canvas_for_window(self.window), "CCO")

        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "example"
            saved_path = Path(f"{raw_path}.chemvas")
            with patch(
                "chemvas.ui.main_window_document_action_service.QFileDialog.getSaveFileName",
                return_value=(str(raw_path), ""),
            ):
                self._document_actions().save_canvas(self.window)

            self.assertTrue(saved_path.exists())
            document = read_document(saved_path)

        self.assertEqual(self._current_file_path(), str(saved_path))
        self.assertEqual(
            self.window.statusBar().currentMessage(), f"Saved: {saved_path}"
        )
        self.assertEqual(len(document.state["ring_fills"]), 1)
        self.assertEqual(len(document.state["notes"]), 1)
        self.assertEqual(len(document.state["marks"]), 1)
        self.assertEqual(len(document.state["arrows"]), 1)
        self.assertEqual(document.state["last_smiles_input"], "CCO")

    def test_load_canvas_restores_document_and_resets_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "roundtrip.chemvas"
            add_benzene_ring_for(
                active_canvas_for_window(self.window), QPointF(0.0, 0.0)
            )
            canvas_services_for(
                active_canvas_for_window(self.window)
            ).interaction.note_controller.create_text_note(
                QPointF(75.0, 10.0), "Roundtrip"
            )
            add_mark_for(
                active_canvas_for_window(self.window),
                QPointF(20.0, 20.0),
                kind="minus",
                atom_id=0,
                record=False,
            )
            add_arrow_for(
                active_canvas_for_window(self.window),
                QPointF(-50.0, -10.0),
                QPointF(50.0, -10.0),
                "equilibrium",
            )
            set_last_smiles_input_for(active_canvas_for_window(self.window), "NCCO")
            save_canvas_to_file_for(active_canvas_for_window(self.window), str(path))

            clear_scene_for(active_canvas_for_window(self.window))
            history_state_for(active_canvas_for_window(self.window)).history = ["dirty"]
            history_state_for(active_canvas_for_window(self.window)).redo_stack = [
                "dirty"
            ]
            set_last_smiles_input_for(active_canvas_for_window(self.window), None)

            preview_model = MoleculeModel()
            left = preview_model.add_atom("C", -10.0, 0.0)
            right = preview_model.add_atom("C", 10.0, 0.0)
            preview_model.add_bond(left, right)
            with patch.object(
                active_canvas_for_window(self.window).rdkit,
                "smiles_to_2d",
                return_value=preview_model,
            ):
                active_canvas_for_window(
                    self.window
                ).services.structure.insert_controller.begin_smiles_insert("CC")
            self.assertTrue(
                insert_state_for(active_canvas_for_window(self.window)).smiles_active
            )

            with patch(
                "chemvas.ui.main_window_document_action_service.QFileDialog.getOpenFileName",
                return_value=(str(path), ""),
            ):
                self._document_actions().load_canvas(self.window)

        self.assertEqual(self._current_file_path(), str(path))
        self.assertEqual(self.window.statusBar().currentMessage(), f"Loaded: {path}")
        self.assertEqual(len(ring_items_for(active_canvas_for_window(self.window))), 1)
        self.assertEqual(len(note_items_for(active_canvas_for_window(self.window))), 1)
        self.assertEqual(len(mark_items_for(active_canvas_for_window(self.window))), 1)
        self.assertEqual(len(arrow_items_for(active_canvas_for_window(self.window))), 1)
        self.assertEqual(
            last_smiles_input_for(active_canvas_for_window(self.window)), "NCCO"
        )
        self.assertEqual(
            history_state_for(active_canvas_for_window(self.window)).history, []
        )
        self.assertEqual(
            history_state_for(active_canvas_for_window(self.window)).redo_stack, []
        )
        self.assertFalse(
            insert_state_for(active_canvas_for_window(self.window)).smiles_active
        )
        self.assertIsNone(
            insert_state_for(active_canvas_for_window(self.window)).smiles_preview_model
        )
        self.assertIsNone(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).smiles_preview_smiles
        )
        self.assertIsNone(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).smiles_preview_center
        )
        self.assertEqual(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).smiles_preview_items,
            [],
        )

    def test_snapshot_restore_reapplies_saved_settings_before_recreating_items(
        self,
    ) -> None:
        saved_weight = 77
        geometry_controller = canvas_services_for(
            active_canvas_for_window(self.window)
        ).scene_view.geometry_controller
        tool_mode_controller = canvas_services_for(
            active_canvas_for_window(self.window)
        ).input.tool_mode_controller
        style_controller = canvas_services_for(
            active_canvas_for_window(self.window)
        ).scene_operations.style_controller
        geometry_controller.set_bond_length(28.0)
        tool_mode_controller.set_arrow_line_width(3.6)
        tool_mode_controller.set_arrow_head_scale(0.55)
        tool_mode_controller.set_orbital_phase_enabled(True)
        style_controller.set_text_size(18)
        style_controller.set_text_weight(saved_weight)
        style_controller.set_text_italic(True)
        canvas_services_for(
            active_canvas_for_window(self.window)
        ).interaction.note_controller.create_text_note(QPointF(30.0, 15.0), "Styled")
        add_arrow_for(
            active_canvas_for_window(self.window),
            QPointF(-40.0, 0.0),
            QPointF(40.0, 0.0),
            "arrow",
        )

        state = snapshot_canvas_state_for(active_canvas_for_window(self.window))

        geometry_controller.set_bond_length(16.0)
        tool_mode_controller.set_arrow_line_width(1.1)
        tool_mode_controller.set_arrow_head_scale(0.2)
        tool_mode_controller.set_orbital_phase_enabled(False)
        style_controller.set_text_size(10)
        style_controller.set_text_weight(24)
        style_controller.set_text_italic(False)
        clear_scene_for(active_canvas_for_window(self.window))

        restore_canvas_state_for(active_canvas_for_window(self.window), state)

        self.assertAlmostEqual(
            active_canvas_for_window(self.window).renderer.style.bond_length_px, 28.0
        )
        self.assertAlmostEqual(tool_mode_controller.get_arrow_line_width(), 3.6)
        self.assertAlmostEqual(tool_mode_controller.get_arrow_head_scale(), 0.55)
        self.assertTrue(
            tool_settings_state_for(
                active_canvas_for_window(self.window)
            ).orbital_phase_enabled
        )
        note_items = note_items_for(active_canvas_for_window(self.window))
        self.assertEqual(len(note_items), 1)
        restored_font = note_items[0].font()
        self.assertEqual(restored_font.pointSize(), 18)
        self.assertEqual(restored_font.weight(), saved_weight)
        self.assertTrue(restored_font.italic())
        arrow_items = arrow_items_for(active_canvas_for_window(self.window))
        self.assertEqual(len(arrow_items), 1)
        self.assertAlmostEqual(arrow_items[0].pen().widthF(), 3.6)

    def test_snapshot_restore_preserves_atom_bound_mark_offsets(self) -> None:
        atom_id = add_atom_for(active_canvas_for_window(self.window), "C", 12.0, -8.0)
        add_mark_for_atom_for(
            active_canvas_for_window(self.window),
            atom_id,
            QPointF(42.0, -20.0),
            kind="minus",
            record=False,
        )

        state = snapshot_canvas_state_for(active_canvas_for_window(self.window))
        self.assertEqual(len(state["marks"]), 1)
        saved_mark = state["marks"][0]

        clear_scene_for(active_canvas_for_window(self.window))
        restore_canvas_state_for(active_canvas_for_window(self.window), state)

        marks_by_atom = mark_registry_for(active_canvas_for_window(self.window)).by_atom
        self.assertIn(atom_id, marks_by_atom)
        self.assertEqual(len(marks_by_atom[atom_id]), 1)
        restored_mark = marks_by_atom[atom_id][0]
        restored_data = restored_mark.data(1) or {}
        self.assertEqual(restored_data.get("kind"), "minus")
        self.assertEqual(restored_data.get("atom_id"), atom_id)
        self.assertAlmostEqual(restored_data.get("dx"), saved_mark["dx"])
        self.assertAlmostEqual(restored_data.get("dy"), saved_mark["dy"])
        restored_center = mark_center_for(
            active_canvas_for_window(self.window), restored_mark
        )
        self.assertAlmostEqual(restored_center.x(), saved_mark["x"])
        self.assertAlmostEqual(restored_center.y(), saved_mark["y"])

    def test_snapshot_restore_rebuilds_orbital_metadata_from_restored_settings(
        self,
    ) -> None:
        geometry_controller = canvas_services_for(
            active_canvas_for_window(self.window)
        ).scene_view.geometry_controller
        tool_mode_controller = canvas_services_for(
            active_canvas_for_window(self.window)
        ).input.tool_mode_controller
        geometry_controller.set_bond_length(28.0)
        tool_mode_controller.set_orbital_phase_enabled(True)
        set_tool_setting_for(
            active_canvas_for_window(self.window), "active_orbital_type", "p"
        )
        add_orbital_for(active_canvas_for_window(self.window), QPointF(18.0, -12.0))
        orbital = orbital_items_for(active_canvas_for_window(self.window))[0]
        orbital.setScale(1.35)
        orbital.setRotation(22.0)

        state = snapshot_canvas_state_for(active_canvas_for_window(self.window))

        geometry_controller.set_bond_length(16.0)
        tool_mode_controller.set_orbital_phase_enabled(False)
        clear_scene_for(active_canvas_for_window(self.window))

        restore_canvas_state_for(active_canvas_for_window(self.window), state)

        orbital_items = orbital_items_for(active_canvas_for_window(self.window))
        self.assertEqual(len(orbital_items), 1)
        restored = orbital_items[0]
        data = restored.data(1) or {}
        center = data.get("center")
        meta = restored.data(2) or {}
        self.assertTrue(
            tool_settings_state_for(
                active_canvas_for_window(self.window)
            ).orbital_phase_enabled
        )
        self.assertEqual(meta.get("kind"), "p")
        self.assertAlmostEqual(
            active_canvas_for_window(self.window).renderer.style.bond_length_px, 28.0
        )
        self.assertAlmostEqual(data.get("base_handle_dist"), 22.4)
        self.assertAlmostEqual(center.x(), 18.0)
        self.assertAlmostEqual(center.y(), -12.0)
        self.assertAlmostEqual(restored.scale(), 1.35)
        self.assertAlmostEqual(restored.rotation(), 22.0)
        self.assertIs(restored.scene(), active_canvas_for_window(self.window).scene())

    def test_save_canvas_writes_only_active_canvas_state(self) -> None:
        add_bond_between_points_for(
            active_canvas_for_window(self.window),
            QPointF(-20.0, 0.0),
            QPointF(20.0, 0.0),
        )
        first_canvas_state = snapshot_canvas_state_for(
            active_canvas_for_window(self.window)
        )

        services_for_window(self.window).canvas_document_service.new_canvas(self.window)
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        active_state = snapshot_canvas_state_for(active_canvas_for_window(self.window))

        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "canvas"
            saved_path = Path(f"{raw_path}.chemvas")
            with patch(
                "chemvas.ui.main_window_document_action_service.QFileDialog.getSaveFileName",
                return_value=(str(raw_path), ""),
            ):
                self._document_actions().save_canvas(self.window)

            document = read_document(saved_path)

        self.assertNotIn("sheets", document.state)
        self.assertEqual(
            len(document.state["ring_fills"]), len(active_state["ring_fills"])
        )
        self.assertNotEqual(document.state["model"], first_canvas_state["model"])

    def test_load_canvas_rejects_workbook_payload(self) -> None:
        add_bond_between_points_for(
            active_canvas_for_window(self.window),
            QPointF(-20.0, 0.0),
            QPointF(20.0, 0.0),
        )
        original_state = snapshot_canvas_state_for(
            active_canvas_for_window(self.window)
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "workbook.chemvas"
            path.write_text(
                dumps(
                    {
                        "type": "chemvas",
                        "version": 2,
                        "state": {
                            "active_sheet_index": 1,
                            "sheets": [
                                {
                                    "name": "Reactant Canvas",
                                    "kind": "canvas",
                                    "content": original_state,
                                },
                                {
                                    "name": "Product Canvas",
                                    "kind": "canvas",
                                    "content": original_state,
                                },
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch(
                    "chemvas.ui.main_window_document_action_service.QFileDialog.getOpenFileName",
                    return_value=(str(path), ""),
                ),
                patch(
                    "chemvas.ui.main_window_document_action_service.QMessageBox.warning"
                ) as warning,
            ):
                self._document_actions().load_canvas(self.window)

        warning.assert_called_once()
        self.assertEqual(self.window.tab_references.canvas_count(), 1)
        self.assertEqual(
            snapshot_canvas_state_for(active_canvas_for_window(self.window)),
            original_state,
        )

    def test_save_canvas_cancel_keeps_current_path_and_status_message(self) -> None:
        self._set_current_file_path(None)
        self.window.statusBar().showMessage("Idle")

        with patch(
            "chemvas.ui.main_window_document_action_service.QFileDialog.getSaveFileName",
            return_value=("", ""),
        ):
            self._document_actions().save_canvas(self.window)

        self.assertIsNone(self._current_file_path())
        self.assertEqual(self.window.statusBar().currentMessage(), "Idle")

    def test_save_canvas_reuses_current_path_without_opening_dialog(self) -> None:
        self._set_current_file_path("/tmp/existing.chemvas")
        doc_service = active_canvas_for_window(
            self.window
        ).services.document.canvas_document_session_service

        with (
            patch.object(doc_service, "save_to_file", return_value=[]) as save_mock,
            patch(
                "chemvas.ui.main_window_document_action_service.QFileDialog.getSaveFileName"
            ) as dialog_mock,
        ):
            self.assertFalse(
                hasattr(active_canvas_for_window(self.window), "save_to_file")
            )
            self._document_actions().save_canvas(self.window)

        save_mock.assert_called_once_with("/tmp/existing.chemvas")
        dialog_mock.assert_not_called()
        self.assertEqual(self._current_file_path(), "/tmp/existing.chemvas")
        self.assertEqual(
            self.window.statusBar().currentMessage(), "Saved: /tmp/existing.chemvas"
        )

    def test_save_canvas_as_updates_current_path_and_status_message(self) -> None:
        add_bond_between_points_for(
            active_canvas_for_window(self.window),
            QPointF(-20.0, 0.0),
            QPointF(20.0, 0.0),
        )
        self._set_current_file_path("/tmp/original.chemvas")

        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "renamed"
            saved_path = Path(f"{raw_path}.chemvas")
            with patch(
                "chemvas.ui.main_window_document_action_service.QFileDialog.getSaveFileName",
                return_value=(str(raw_path), ""),
            ):
                self._document_actions().save_canvas_as(self.window)

            self.assertTrue(saved_path.exists())

        self.assertEqual(self._current_file_path(), str(saved_path))
        self.assertEqual(
            self.window.statusBar().currentMessage(), f"Saved: {saved_path}"
        )

    def test_save_canvas_as_cancel_keeps_current_path_and_status_message(self) -> None:
        self._set_current_file_path("/tmp/original.chemvas")
        self.window.statusBar().showMessage("Idle")

        with patch(
            "chemvas.ui.main_window_document_action_service.QFileDialog.getSaveFileName",
            return_value=("", ""),
        ):
            self._document_actions().save_canvas_as(self.window)

        self.assertEqual(self._current_file_path(), "/tmp/original.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Idle")

    def test_save_canvas_as_failure_warns_and_preserves_current_path(self) -> None:
        self._set_current_file_path("/tmp/original.chemvas")
        self.window.statusBar().showMessage("Before save as")
        doc_service = active_canvas_for_window(
            self.window
        ).services.document.canvas_document_session_service

        with (
            patch(
                "chemvas.ui.main_window_document_action_service.QFileDialog.getSaveFileName",
                return_value=("/tmp/renamed.chemvas", ""),
            ),
            patch.object(
                doc_service, "save_to_file", side_effect=OSError("disk full")
            ) as save_mock,
            patch(
                "chemvas.ui.main_window_document_action_service.QMessageBox.warning"
            ) as warning,
        ):
            self.assertFalse(
                hasattr(active_canvas_for_window(self.window), "save_to_file")
            )
            self._document_actions().save_canvas_as(self.window)

        save_mock.assert_called_once_with("/tmp/renamed.chemvas")
        warning.assert_called_once_with(
            self.window,
            "Save Error",
            "Failed to save file:\ndisk full",
        )
        self.assertEqual(self._current_file_path(), "/tmp/original.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Before save as")

    def test_export_xyz_appends_extension_and_updates_status_message(self) -> None:
        self._set_current_file_path("/tmp/example.chemvas")

        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "exported_structure"
            expected_path = Path(f"{raw_path}.xyz")

            def export_success(path, *, on_success, on_error) -> None:
                on_success(path)

            doc_service = active_canvas_for_window(
                self.window
            ).services.document.canvas_document_session_service
            with (
                patch(
                    "chemvas.ui.main_window_document_action_service.QFileDialog.getSaveFileName",
                    return_value=(str(raw_path), ""),
                ),
                patch.object(
                    doc_service, "export_xyz_async", side_effect=export_success
                ) as export_mock,
            ):
                self.assertFalse(
                    hasattr(active_canvas_for_window(self.window), "export_xyz_async")
                )
                self._document_actions().export_xyz(self.window)

        self.assertEqual(export_mock.call_args.args, (str(expected_path),))
        self.assertEqual(self._current_file_path(), "/tmp/example.chemvas")
        self.assertEqual(
            self.window.statusBar().currentMessage(), f"Exported XYZ: {expected_path}"
        )

    def test_export_xyz_cancel_keeps_current_path_and_status_message(self) -> None:
        self._set_current_file_path("/tmp/original.chemvas")
        self.window.statusBar().showMessage("Idle")

        with patch(
            "chemvas.ui.main_window_document_action_service.QFileDialog.getSaveFileName",
            return_value=("", ""),
        ):
            self._document_actions().export_xyz(self.window)

        self.assertEqual(self._current_file_path(), "/tmp/original.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Idle")

    def test_export_xyz_failure_warns_and_preserves_status_message(self) -> None:
        self._set_current_file_path("/tmp/original.chemvas")
        self.window.statusBar().showMessage("Before export")

        with (
            patch(
                "chemvas.ui.main_window_document_action_service.QFileDialog.getSaveFileName",
                return_value=("/tmp/output.xyz", ""),
            ),
            patch.object(
                active_canvas_for_window(
                    self.window
                ).services.document.canvas_document_session_service,
                "export_xyz_async",
                side_effect=lambda path, *, on_success, on_error: on_error(
                    "RDKit missing"
                ),
            ) as export_mock,
            patch(
                "chemvas.ui.main_window_document_action_service.QMessageBox.warning"
            ) as warning,
        ):
            self.assertFalse(
                hasattr(active_canvas_for_window(self.window), "export_xyz_async")
            )
            self._document_actions().export_xyz(self.window)

        self.assertEqual(export_mock.call_args.args, ("/tmp/output.xyz",))
        warning.assert_called_once_with(
            self.window,
            "Export Error",
            "Failed to export XYZ:\nRDKit missing",
        )
        self.assertEqual(self._current_file_path(), "/tmp/original.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Before export")

    def test_load_canvas_cancel_keeps_current_path_and_status_message(self) -> None:
        self._set_current_file_path("/tmp/original.chemvas")
        self.window.statusBar().showMessage("Idle")

        with patch(
            "chemvas.ui.main_window_document_action_service.QFileDialog.getOpenFileName",
            return_value=("", ""),
        ):
            self._document_actions().load_canvas(self.window)

        self.assertEqual(self._current_file_path(), "/tmp/original.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Idle")

    def test_save_canvas_failure_warns_and_preserves_current_path(self) -> None:
        self._set_current_file_path("/tmp/original.chemvas")
        self.window.statusBar().showMessage("Before save")
        doc_service = active_canvas_for_window(
            self.window
        ).services.document.canvas_document_session_service

        with (
            patch.object(
                doc_service, "save_to_file", side_effect=OSError("disk full")
            ) as save_mock,
            patch(
                "chemvas.ui.main_window_document_action_service.QMessageBox.warning"
            ) as warning,
        ):
            self.assertFalse(
                hasattr(active_canvas_for_window(self.window), "save_to_file")
            )
            self._document_actions().save_canvas(self.window)

        save_mock.assert_called_once_with("/tmp/original.chemvas")
        warning.assert_called_once_with(
            self.window,
            "Save Error",
            "Failed to save file:\ndisk full",
        )
        self.assertEqual(self._current_file_path(), "/tmp/original.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Before save")

    def test_load_canvas_failure_warns_and_preserves_existing_scene(self) -> None:
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        canvas_services_for(
            active_canvas_for_window(self.window)
        ).interaction.note_controller.create_text_note(QPointF(75.0, 10.0), "Keep me")
        set_last_smiles_input_for(active_canvas_for_window(self.window), "CCO")
        history_state_for(active_canvas_for_window(self.window)).history = [
            "keep-history"
        ]
        history_state_for(active_canvas_for_window(self.window)).redo_stack = [
            "keep-redo"
        ]
        self._set_current_file_path("/tmp/original.chemvas")
        self.window.statusBar().showMessage("Before load")

        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_path = Path(temp_dir) / "invalid.chemvas"
            invalid_path.write_text(dumps({"state": {}}), encoding="utf-8")

            with (
                patch(
                    "chemvas.ui.main_window_document_action_service.QFileDialog.getOpenFileName",
                    return_value=(str(invalid_path), ""),
                ),
                patch(
                    "chemvas.ui.main_window_document_action_service.QMessageBox.warning"
                ) as warning,
            ):
                self._document_actions().load_canvas(self.window)

        warning.assert_called_once_with(
            self.window,
            "Load Error",
            "Failed to load file:\nInvalid Chemvas file.",
        )
        self.assertEqual(self._current_file_path(), "/tmp/original.chemvas")
        self.assertEqual(self.window.statusBar().currentMessage(), "Before load")
        self.assertEqual(len(ring_items_for(active_canvas_for_window(self.window))), 1)
        self.assertEqual(len(note_items_for(active_canvas_for_window(self.window))), 1)
        self.assertEqual(
            last_smiles_input_for(active_canvas_for_window(self.window)), "CCO"
        )
        self.assertEqual(
            history_state_for(active_canvas_for_window(self.window)).history,
            ["keep-history"],
        )
        self.assertEqual(
            history_state_for(active_canvas_for_window(self.window)).redo_stack,
            ["keep-redo"],
        )

    def test_regular_template_preview_reuses_existing_preview_items(self) -> None:
        self._template_handler("Cyclopropane")()
        self.assertTrue(
            insert_state_for(active_canvas_for_window(self.window)).template_active
        )

        self._hover_scene_point(QPointF(-30.0, 0.0))
        self.assertEqual(
            len(
                insert_state_for(
                    active_canvas_for_window(self.window)
                ).template_preview_lines
            ),
            3,
        )
        self.assertEqual(
            len(
                insert_state_for(
                    active_canvas_for_window(self.window)
                ).template_preview_dots
            ),
            3,
        )
        preview_lines = list(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).template_preview_lines
        )
        first_line_before = preview_lines[0].line()

        self._hover_scene_point(QPointF(30.0, 20.0))

        self.assertEqual(
            len(
                insert_state_for(
                    active_canvas_for_window(self.window)
                ).template_preview_lines
            ),
            3,
        )
        self.assertEqual(
            len(
                insert_state_for(
                    active_canvas_for_window(self.window)
                ).template_preview_dots
            ),
            3,
        )
        self.assertIs(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).template_preview_lines[0],
            preview_lines[0],
        )
        self.assertNotEqual(
            insert_state_for(active_canvas_for_window(self.window))
            .template_preview_lines[0]
            .line(),
            first_line_before,
        )

    def test_large_regular_template_preview_uses_requested_ring_size(self) -> None:
        for label, ring_size in (("Cycloheptane", 7), ("Cyclooctane", 8)):
            with self.subTest(label=label):
                self._template_handler(label)()
                self.assertTrue(
                    insert_state_for(
                        active_canvas_for_window(self.window)
                    ).template_active
                )
                self.assertEqual(
                    insert_state_for(
                        active_canvas_for_window(self.window)
                    ).template_ring_size,
                    ring_size,
                )
                self.assertEqual(
                    insert_state_for(
                        active_canvas_for_window(self.window)
                    ).template_ring_style,
                    "regular",
                )

                self._hover_scene_point(QPointF(20.0, 20.0))

                self.assertEqual(
                    len(
                        insert_state_for(
                            active_canvas_for_window(self.window)
                        ).template_preview_lines
                    ),
                    ring_size,
                )
                self.assertEqual(
                    len(
                        insert_state_for(
                            active_canvas_for_window(self.window)
                        ).template_preview_dots
                    ),
                    ring_size,
                )
                active_canvas_for_window(
                    self.window
                ).services.structure.insert_controller.cancel_template_insert()

    def test_regular_template_commit_on_bond_merges_existing_endpoints(self) -> None:
        add_bond_between_points_for(
            active_canvas_for_window(self.window),
            QPointF(-20.0, 0.0),
            QPointF(20.0, 0.0),
        )
        canvas = active_canvas_for_window(self.window)
        before_atom_count = len(active_canvas_for_window(self.window).model.atoms)
        before_bond_count = sum(
            1
            for bond in active_canvas_for_window(self.window).model.bonds
            if bond is not None
        )
        before_ring_count = len(ring_items_for(canvas))

        self._template_handler("Cyclobutane")()
        self._hover_scene_point(QPointF(0.0, 0.0))
        self.assertEqual(
            len(
                insert_state_for(
                    active_canvas_for_window(self.window)
                ).template_preview_lines
            ),
            4,
        )

        self._click_scene_point(QPointF(0.0, 0.0))

        self.assertTrue(
            insert_state_for(active_canvas_for_window(self.window)).template_active
        )
        self.assertEqual(
            insert_state_for(active_canvas_for_window(self.window)).template_ring_size,
            4,
        )
        self.assertEqual(
            insert_state_for(active_canvas_for_window(self.window)).template_ring_style,
            "regular",
        )
        self.assertEqual(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).template_preview_lines,
            [],
        )
        self.assertEqual(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).template_preview_dots,
            [],
        )
        self.assertEqual(
            len(active_canvas_for_window(self.window).model.atoms),
            before_atom_count + 2,
        )
        self.assertEqual(
            sum(
                1
                for bond in active_canvas_for_window(self.window).model.bonds
                if bond is not None
            ),
            before_bond_count + 3,
        )
        self.assertEqual(len(ring_items_for(canvas)), before_ring_count + 1)
        added_ring = ring_items_for(canvas)[-1]
        added_ring_atom_ids = added_ring.data(2)
        self.assertIsInstance(added_ring_atom_ids, list)
        self.assertEqual(len(added_ring_atom_ids), 4)

        canvas.runtime_state.history_service.undo()
        self.assertEqual(len(ring_items_for(canvas)), before_ring_count)

        canvas.runtime_state.history_service.redo()
        self.assertEqual(len(ring_items_for(canvas)), before_ring_count + 1)
        self.assertIs(ring_items_for(canvas)[-1], added_ring)
        self.assertEqual(added_ring.data(2), added_ring_atom_ids)
        added_color = added_ring.brush().color().name()
        added_alpha = added_ring.brush().color().alphaF()

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "attached-template.chemvas"
            save_canvas_to_file_for(canvas, str(path))
            document = read_document(path)
            self.assertEqual(len(document.state["ring_fills"]), 1)
            self.assertEqual(
                document.state["ring_fills"][0]["atom_ids"], added_ring_atom_ids
            )
            clear_scene_for(canvas)
            restore_canvas_state_for(canvas, document.state)

        self.assertEqual(len(ring_items_for(canvas)), 1)
        restored_ring = ring_items_for(canvas)[0]
        self.assertEqual(restored_ring.data(2), added_ring_atom_ids)
        self.assertEqual(restored_ring.brush().color().name(), added_color)
        self.assertAlmostEqual(restored_ring.brush().color().alphaF(), added_alpha)

    def test_chair_template_commit_on_ring_bond_places_new_atoms_outside_existing_ring(
        self,
    ) -> None:
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        canvas = active_canvas_for_window(self.window)
        ring_item = ring_items_for(active_canvas_for_window(self.window))[0]
        before_ring_count = len(ring_items_for(canvas))
        original_polygon = ring_item.polygon()
        ring_atom_ids = ring_item.data(2)
        self.assertIsInstance(ring_atom_ids, list)
        original_atom_ids = set(active_canvas_for_window(self.window).model.atoms)
        bond_id = active_canvas_for_window(
            self.window
        ).services.graph_service.bond_id_between(ring_atom_ids[0], ring_atom_ids[1])
        self.assertIsNotNone(bond_id)
        atom_a = active_canvas_for_window(self.window).model.atoms[ring_atom_ids[0]]
        atom_b = active_canvas_for_window(self.window).model.atoms[ring_atom_ids[1]]
        midpoint = QPointF((atom_a.x + atom_b.x) / 2.0, (atom_a.y + atom_b.y) / 2.0)

        self._template_handler("Cyclohexane (Chair)")()
        self._hover_scene_point(midpoint)
        self.assertEqual(
            len(
                insert_state_for(
                    active_canvas_for_window(self.window)
                ).template_preview_lines
            ),
            6,
        )

        self._click_scene_point(midpoint)

        self.assertTrue(
            insert_state_for(active_canvas_for_window(self.window)).template_active
        )
        self.assertEqual(
            insert_state_for(active_canvas_for_window(self.window)).template_ring_size,
            6,
        )
        self.assertEqual(
            insert_state_for(active_canvas_for_window(self.window)).template_ring_style,
            "chair",
        )
        new_atom_ids = (
            set(active_canvas_for_window(self.window).model.atoms) - original_atom_ids
        )
        self.assertEqual(len(new_atom_ids), 4)
        for atom_id in new_atom_ids:
            atom = active_canvas_for_window(self.window).model.atoms[atom_id]
            self.assertFalse(
                original_polygon.containsPoint(
                    QPointF(atom.x, atom.y), Qt.FillRule.WindingFill
                ),
            )
        self.assertEqual(len(ring_items_for(canvas)), before_ring_count + 1)
        chair_ring = ring_items_for(canvas)[-1]
        chair_atom_ids = chair_ring.data(2)
        self.assertIsInstance(chair_atom_ids, list)
        self.assertEqual(len(chair_atom_ids), 6)

        canvas.runtime_state.history_service.undo()
        self.assertEqual(len(ring_items_for(canvas)), before_ring_count)

        canvas.runtime_state.history_service.redo()
        self.assertEqual(len(ring_items_for(canvas)), before_ring_count + 1)
        self.assertIs(ring_items_for(canvas)[-1], chair_ring)
        self.assertEqual(chair_ring.data(2), chair_atom_ids)

    def test_escape_cancels_template_insert_and_prevents_commit(self) -> None:
        self._template_handler("Cyclopropane")()
        self._hover_scene_point(QPointF(25.0, 10.0))
        preview_items = list(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).template_preview_items
        )

        self.assertTrue(
            insert_state_for(active_canvas_for_window(self.window)).template_active
        )
        self.assertGreater(len(preview_items), 0)

        self._press_key(Qt.Key.Key_Escape)
        atom_count_before = len(active_canvas_for_window(self.window).model.atoms)
        bond_count_before = sum(
            1
            for bond in active_canvas_for_window(self.window).model.bonds
            if bond is not None
        )
        active_canvas_for_window(
            self.window
        ).services.structure.insert_controller.commit_template_insert(
            QPointF(25.0, 10.0)
        )

        self.assertFalse(
            insert_state_for(active_canvas_for_window(self.window)).template_active
        )
        self.assertIsNone(
            insert_state_for(active_canvas_for_window(self.window)).template_ring_size
        )
        self.assertIsNone(
            insert_state_for(active_canvas_for_window(self.window)).template_ring_style
        )
        self.assertEqual(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).template_preview_items,
            [],
        )
        self.assertEqual(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).template_preview_lines,
            [],
        )
        self.assertEqual(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).template_preview_dots,
            [],
        )
        self.assertEqual(
            len(active_canvas_for_window(self.window).model.atoms), atom_count_before
        )
        self.assertEqual(
            sum(
                1
                for bond in active_canvas_for_window(self.window).model.bonds
                if bond is not None
            ),
            bond_count_before,
        )
        self.assertTrue(all(item.scene() is None for item in preview_items))

    def test_begin_smiles_insert_cancels_active_template_preview(self) -> None:
        self._template_handler("Cyclobutane")()
        self._hover_scene_point(QPointF(15.0, 15.0))
        preview_items = list(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).template_preview_items
        )

        model = MoleculeModel()
        left = model.add_atom("C", -10.0, 0.0)
        right = model.add_atom("C", 10.0, 0.0)
        model.add_bond(left, right)

        with patch.object(
            active_canvas_for_window(self.window).rdkit,
            "smiles_to_2d",
            return_value=model,
        ):
            active_canvas_for_window(
                self.window
            ).services.structure.insert_controller.begin_smiles_insert("CC")

        self.assertFalse(
            insert_state_for(active_canvas_for_window(self.window)).template_active
        )
        self.assertEqual(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).template_preview_items,
            [],
        )
        self.assertEqual(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).template_preview_lines,
            [],
        )
        self.assertEqual(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).template_preview_dots,
            [],
        )
        self.assertTrue(all(item.scene() is None for item in preview_items))
        self.assertTrue(
            insert_state_for(active_canvas_for_window(self.window)).smiles_active
        )
        self.assertEqual(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).smiles_preview_smiles,
            "CC",
        )
        self.assertGreater(
            len(
                insert_state_for(
                    active_canvas_for_window(self.window)
                ).smiles_preview_items
            ),
            0,
        )

    def test_begin_template_insert_cancels_active_smiles_preview(self) -> None:
        model = MoleculeModel()
        left = model.add_atom("C", -10.0, 0.0)
        right = model.add_atom("C", 10.0, 0.0)
        model.add_bond(left, right)

        with patch.object(
            active_canvas_for_window(self.window).rdkit,
            "smiles_to_2d",
            return_value=model,
        ):
            active_canvas_for_window(
                self.window
            ).services.structure.insert_controller.begin_smiles_insert("CC")

        self.assertTrue(
            insert_state_for(active_canvas_for_window(self.window)).smiles_active
        )
        smiles_preview_items = list(
            insert_state_for(active_canvas_for_window(self.window)).smiles_preview_items
        )

        self._template_handler("Cyclobutane")()

        self.assertFalse(
            insert_state_for(active_canvas_for_window(self.window)).smiles_active
        )
        self.assertIsNone(
            insert_state_for(active_canvas_for_window(self.window)).smiles_preview_model
        )
        self.assertIsNone(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).smiles_preview_smiles
        )
        self.assertIsNone(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).smiles_preview_center
        )
        self.assertEqual(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).smiles_preview_items,
            [],
        )
        self.assertTrue(all(item.scene() is None for item in smiles_preview_items))
        self.assertTrue(
            insert_state_for(active_canvas_for_window(self.window)).template_active
        )
        self.assertEqual(
            insert_state_for(active_canvas_for_window(self.window)).template_ring_size,
            4,
        )
        self.assertEqual(
            insert_state_for(active_canvas_for_window(self.window)).template_ring_style,
            "regular",
        )
        self.assertEqual(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).template_preview_items,
            [],
        )
        self.assertEqual(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).template_preview_lines,
            [],
        )
        self.assertEqual(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).template_preview_dots,
            [],
        )

        self._hover_scene_point(QPointF(15.0, 15.0))

        self.assertGreater(
            len(
                insert_state_for(
                    active_canvas_for_window(self.window)
                ).template_preview_items
            ),
            0,
        )
        self.assertGreater(
            len(
                insert_state_for(
                    active_canvas_for_window(self.window)
                ).template_preview_lines
            ),
            0,
        )
        self.assertGreater(
            len(
                insert_state_for(
                    active_canvas_for_window(self.window)
                ).template_preview_dots
            ),
            0,
        )

    def test_smiles_preview_reuses_existing_preview_items(self) -> None:
        model = MoleculeModel()
        left = model.add_atom("C", -10.0, 0.0)
        right = model.add_atom("C", 10.0, 0.0)
        model.add_bond(left, right)

        with patch.object(
            active_canvas_for_window(self.window).rdkit,
            "smiles_to_2d",
            return_value=model,
        ):
            active_canvas_for_window(
                self.window
            ).services.structure.insert_controller.begin_smiles_insert("CC")

        self.assertTrue(
            insert_state_for(active_canvas_for_window(self.window)).smiles_active
        )
        self._hover_scene_point(QPointF(-30.0, 0.0))
        self.assertEqual(
            len(
                insert_state_for(
                    active_canvas_for_window(self.window)
                ).smiles_preview_bond_items[0]
            ),
            1,
        )
        preview_line = insert_state_for(
            active_canvas_for_window(self.window)
        ).smiles_preview_bond_items[0][0]
        preview_rect = (
            insert_state_for(active_canvas_for_window(self.window))
            .smiles_preview_atom_items[left]
            .rect()
        )
        preview_atom = insert_state_for(
            active_canvas_for_window(self.window)
        ).smiles_preview_atom_items[left]

        self._hover_scene_point(QPointF(30.0, 20.0))

        self.assertIs(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).smiles_preview_bond_items[0][0],
            preview_line,
        )
        self.assertIs(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).smiles_preview_atom_items[left],
            preview_atom,
        )
        self.assertNotEqual(
            insert_state_for(active_canvas_for_window(self.window))
            .smiles_preview_atom_items[left]
            .rect(),
            preview_rect,
        )

    def test_clear_scene_resets_active_smiles_insert_state(self) -> None:
        model = MoleculeModel()
        left = model.add_atom("C", -10.0, 0.0)
        right = model.add_atom("C", 10.0, 0.0)
        model.add_bond(left, right)

        with patch.object(
            active_canvas_for_window(self.window).rdkit,
            "smiles_to_2d",
            return_value=model,
        ):
            active_canvas_for_window(
                self.window
            ).services.structure.insert_controller.begin_smiles_insert("CC")

        self.assertTrue(
            insert_state_for(active_canvas_for_window(self.window)).smiles_active
        )
        self.assertIsNotNone(
            insert_state_for(active_canvas_for_window(self.window)).smiles_preview_model
        )
        self.assertGreater(
            len(
                insert_state_for(
                    active_canvas_for_window(self.window)
                ).smiles_preview_items
            ),
            0,
        )

        clear_scene_for(active_canvas_for_window(self.window))

        self.assertFalse(
            insert_state_for(active_canvas_for_window(self.window)).smiles_active
        )
        self.assertIsNone(
            insert_state_for(active_canvas_for_window(self.window)).smiles_preview_model
        )
        self.assertIsNone(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).smiles_preview_smiles
        )
        self.assertIsNone(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).smiles_preview_center
        )
        self.assertEqual(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).smiles_preview_items,
            [],
        )

    def test_smiles_insert_commit_adds_atoms_bonds_and_clears_preview(self) -> None:
        model = MoleculeModel()
        left = model.add_atom("C", -10.0, 0.0)
        right = model.add_atom("N", 10.0, 0.0)
        model.atoms[right].color = "#336699"
        model.atoms[right].explicit_label = True
        model.add_bond(left, right, 2)
        model.bonds[0].style = "double"
        model.bonds[0].color = "#123456"

        with patch.object(
            active_canvas_for_window(self.window).rdkit,
            "smiles_to_2d",
            return_value=model,
        ):
            active_canvas_for_window(
                self.window
            ).services.structure.insert_controller.begin_smiles_insert("CN")

        self.assertTrue(
            insert_state_for(active_canvas_for_window(self.window)).smiles_active
        )
        preview_items = list(
            insert_state_for(active_canvas_for_window(self.window)).smiles_preview_items
        )
        active_canvas_for_window(
            self.window
        ).services.structure.insert_controller.commit_smiles_insert(QPointF(40.0, 10.0))

        self.assertFalse(
            insert_state_for(active_canvas_for_window(self.window)).smiles_active
        )
        self.assertEqual(len(active_canvas_for_window(self.window).model.atoms), 2)
        self.assertEqual(
            sum(
                1
                for bond in active_canvas_for_window(self.window).model.bonds
                if bond is not None
            ),
            1,
        )
        atom0 = active_canvas_for_window(self.window).model.atoms[0]
        atom1 = active_canvas_for_window(self.window).model.atoms[1]
        self.assertEqual((atom0.x, atom0.y), (30.0, 10.0))
        self.assertEqual((atom1.x, atom1.y), (50.0, 10.0))
        self.assertEqual(atom1.color, "#336699")
        atom_items = atom_items_for(active_canvas_for_window(self.window))
        self.assertIn(1, atom_items)
        self.assertEqual(atom_items[1].toPlainText(), "N")
        self.assertEqual(
            last_smiles_input_for(active_canvas_for_window(self.window)), "CN"
        )
        self.assertEqual(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).smiles_preview_items,
            [],
        )
        self.assertTrue(all(item.scene() is None for item in preview_items))

    def test_escape_cancels_smiles_insert_and_prevents_commit(self) -> None:
        model = MoleculeModel()
        left = model.add_atom("C", -10.0, 0.0)
        right = model.add_atom("C", 10.0, 0.0)
        model.add_bond(left, right)

        with patch.object(
            active_canvas_for_window(self.window).rdkit,
            "smiles_to_2d",
            return_value=model,
        ):
            active_canvas_for_window(
                self.window
            ).services.structure.insert_controller.begin_smiles_insert("CC")

        preview_items = list(
            insert_state_for(active_canvas_for_window(self.window)).smiles_preview_items
        )
        self.assertTrue(
            insert_state_for(active_canvas_for_window(self.window)).smiles_active
        )

        self._press_key(Qt.Key.Key_Escape)
        active_canvas_for_window(
            self.window
        ).services.structure.insert_controller.commit_smiles_insert(QPointF(20.0, 0.0))

        self.assertFalse(
            insert_state_for(active_canvas_for_window(self.window)).smiles_active
        )
        self.assertIsNone(
            insert_state_for(active_canvas_for_window(self.window)).smiles_preview_model
        )
        self.assertIsNone(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).smiles_preview_smiles
        )
        self.assertIsNone(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).smiles_preview_center
        )
        self.assertEqual(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).smiles_preview_items,
            [],
        )
        self.assertEqual(len(active_canvas_for_window(self.window).model.atoms), 0)
        self.assertEqual(len(active_canvas_for_window(self.window).model.bonds), 0)
        self.assertTrue(all(item.scene() is None for item in preview_items))

    def test_begin_smiles_insert_invalid_smiles_warns_without_entering_mode(
        self,
    ) -> None:
        active_canvas_for_window(self.window).rdkit.last_error = "bad smiles"

        with (
            patch.object(
                active_canvas_for_window(self.window).rdkit,
                "smiles_to_2d",
                return_value=None,
            ),
            patch("chemvas.ui.insert_smiles_service.QMessageBox.warning") as warning,
        ):
            active_canvas_for_window(
                self.window
            ).services.structure.insert_controller.begin_smiles_insert("not-a-smiles")

        # The error is reported inline via the main window status bar rather
        # than a blocking modal, so QMessageBox should not be used.
        warning.assert_not_called()
        self.assertIn("bad smiles", self.window.statusBar().currentMessage())
        self.assertEqual(self.window.statusBar().property("statusState"), "error")
        self.assertFalse(
            insert_state_for(active_canvas_for_window(self.window)).smiles_active
        )
        self.assertIsNone(
            insert_state_for(active_canvas_for_window(self.window)).smiles_preview_model
        )
        self.assertEqual(
            insert_state_for(
                active_canvas_for_window(self.window)
            ).smiles_preview_items,
            [],
        )

    def test_canvas_export_xyz_uses_selected_structure_submodel(self) -> None:
        left = add_atom_for(active_canvas_for_window(self.window), "C", -20.0, 0.0)
        middle = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        right = add_atom_for(active_canvas_for_window(self.window), "O", 20.0, 0.0)
        add_bond_for(active_canvas_for_window(self.window), left, middle, 1)
        add_bond_for(active_canvas_for_window(self.window), middle, right, 1)
        active_canvas_for_window(self.window).model.bonds[0].style = "bold_in"
        add_bond_graphics_for(active_canvas_for_window(self.window), 0)
        add_bond_graphics_for(active_canvas_for_window(self.window), 1)

        bond_item = bond_items_for_id(active_canvas_for_window(self.window), 0)[0]
        bond_item.setSelected(True)

        captured = {}

        def _capture_export(model, atom_annotations=None):
            captured["model"] = model
            captured["atom_annotations"] = atom_annotations
            return "2\nChemvas XYZ export\nC 0.000000 0.000000 0.000000\nC 1.000000 0.000000 0.000000\n"

        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = Path(temp_dir) / "selected.xyz"
            with patch.object(
                active_canvas_for_window(self.window).rdkit,
                "model_to_xyz_block",
                side_effect=_capture_export,
            ):
                canvas_services_for(
                    active_canvas_for_window(self.window)
                ).document.canvas_document_session_service.export_xyz(str(export_path))
            xyz_text = export_path.read_text(encoding="utf-8")

        exported_model = captured["model"]
        self.assertEqual(len(exported_model.atoms), 2)
        self.assertEqual(len(exported_model.bonds), 1)
        self.assertEqual(exported_model.bonds[0].style, "bold_in")
        self.assertEqual(captured["atom_annotations"], {})
        self.assertIn("Chemvas XYZ export", xyz_text)

    def test_canvas_export_xyz_passes_charge_and_radical_annotations(self) -> None:
        atom_id = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        add_mark_for_atom_for(
            active_canvas_for_window(self.window),
            atom_id,
            QPointF(10.0, -10.0),
            kind="plus",
            record=False,
        )
        add_mark_for_atom_for(
            active_canvas_for_window(self.window),
            atom_id,
            QPointF(12.0, -12.0),
            kind="radical",
            record=False,
        )

        captured = {}

        def _capture_export(model, atom_annotations=None):
            captured["annotations"] = atom_annotations
            return "1\nChemvas XYZ export\nC 0.000000 0.000000 0.000000\n"

        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = Path(temp_dir) / "charged.xyz"
            with patch.object(
                active_canvas_for_window(self.window).rdkit,
                "model_to_xyz_block",
                side_effect=_capture_export,
            ):
                canvas_services_for(
                    active_canvas_for_window(self.window)
                ).document.canvas_document_session_service.export_xyz(str(export_path))

        self.assertEqual(
            captured["annotations"],
            {0: {"formal_charge": 1, "radical_electrons": 1}},
        )

    def test_build_3d_conversion_payload_ignores_scene_only_items_in_mixed_selection(
        self,
    ) -> None:
        left = add_atom_for(active_canvas_for_window(self.window), "C", -20.0, 0.0)
        middle = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        right = add_atom_for(active_canvas_for_window(self.window), "O", 20.0, 0.0)
        add_bond_for(active_canvas_for_window(self.window), left, middle, 1)
        add_bond_for(active_canvas_for_window(self.window), middle, right, 1)
        add_bond_graphics_for(active_canvas_for_window(self.window), 0)
        add_bond_graphics_for(active_canvas_for_window(self.window), 1)
        arrow = add_arrow_for(
            active_canvas_for_window(self.window),
            QPointF(-40.0, -20.0),
            QPointF(40.0, -20.0),
            "reaction",
        )
        ts_bracket = add_ts_bracket_from_points_for(
            active_canvas_for_window(self.window),
            QPointF(-8.0, -28.0),
            QPointF(8.0, 28.0),
        )
        note = canvas_services_for(
            active_canvas_for_window(self.window)
        ).interaction.note_controller.create_text_note(QPointF(55.0, 10.0), "Scheme")

        active_canvas_for_window(self.window).scene().clearSelection()
        bond_items_for_id(active_canvas_for_window(self.window), 0)[0].setSelected(True)
        arrow.setSelected(True)
        ts_bracket.setSelected(True)
        note.setSelected(True)
        self.app.processEvents()
        QTest.qWait(10)

        export_model, atom_annotations = build_3d_conversion_payload_for(
            active_canvas_for_window(self.window)
        )

        self.assertEqual(len(export_model.atoms), 2)
        self.assertEqual(len(export_model.bonds), 1)
        self.assertEqual(atom_annotations, {})

    def test_build_3d_conversion_payload_uses_atom_bound_mark_selection(self) -> None:
        left = add_atom_for(active_canvas_for_window(self.window), "N", -20.0, 0.0)
        add_atom_for(active_canvas_for_window(self.window), "O", 20.0, 0.0)
        mark = add_mark_for_atom_for(
            active_canvas_for_window(self.window),
            left,
            QPointF(-12.0, -10.0),
            kind="plus",
            record=False,
        )
        arrow = add_arrow_for(
            active_canvas_for_window(self.window),
            QPointF(-40.0, -20.0),
            QPointF(40.0, -20.0),
            "reaction",
        )

        active_canvas_for_window(self.window).scene().clearSelection()
        mark.setSelected(True)
        arrow.setSelected(True)
        self.app.processEvents()
        QTest.qWait(10)

        export_model, atom_annotations = build_3d_conversion_payload_for(
            active_canvas_for_window(self.window)
        )

        self.assertEqual(len(export_model.atoms), 1)
        self.assertEqual(len(export_model.bonds), 0)
        self.assertEqual(atom_annotations, {0: {"formal_charge": 1}})

    def test_preview_panel_updates_from_canvas_structure(self) -> None:
        preview = preview_for_window(self.window)
        preview._async_enabled = False
        atom_id = add_atom_for(active_canvas_for_window(self.window), "N", 0.0, 0.0)
        add_mark_for_atom_for(
            active_canvas_for_window(self.window),
            atom_id,
            QPointF(10.0, -10.0),
            kind="plus",
            record=False,
        )
        atom_items_for(active_canvas_for_window(self.window))[atom_id].setSelected(True)

        scene = Molecule3DScene(
            atoms=(
                Molecule3DAtom("N", 0.0, 0.0, 0.0),
                Molecule3DAtom("H", 0.8, 0.0, 0.4),
            ),
            bonds=(Molecule3DBond(0, 1, 1),),
        )

        with (
            patch.object(
                preview.rdkit_adapter,
                "compute_identifiers",
                return_value=MoleculeIdentifiers(
                    formula="NH4", mw=18.04, smiles="[NH4+]"
                ),
            ),
            patch.object(
                preview.rdkit_adapter,
                "model_to_3d_scene_result",
                return_value=RDKitResult(scene),
            ),
        ):
            preview.refresh_selected_from_canvas(active_canvas_for_window(self.window))
            self.app.processEvents()
            QTest.qWait(150)
            self.app.processEvents()

        self.assertIsNotNone(preview._scene)
        self.assertEqual(preview._formula_text, "NH4")
        self.assertEqual(preview._mw_text, "18.04")
        preview_window = preview_window_for_window(self.window)
        self.assertIsNotNone(preview_window)
        self.assertIs(preview.parent(), preview_window)

    def test_preview_panel_uses_selected_structure_when_scene_only_items_are_also_selected(
        self,
    ) -> None:
        preview = preview_for_window(self.window)
        preview._async_enabled = False
        left = add_atom_for(active_canvas_for_window(self.window), "C", -20.0, 0.0)
        middle = add_atom_for(active_canvas_for_window(self.window), "C", 0.0, 0.0)
        right = add_atom_for(active_canvas_for_window(self.window), "O", 20.0, 0.0)
        add_bond_for(active_canvas_for_window(self.window), left, middle, 1)
        add_bond_for(active_canvas_for_window(self.window), middle, right, 1)
        add_bond_graphics_for(active_canvas_for_window(self.window), 0)
        add_bond_graphics_for(active_canvas_for_window(self.window), 1)
        arrow = add_arrow_for(
            active_canvas_for_window(self.window),
            QPointF(-40.0, -20.0),
            QPointF(40.0, -20.0),
            "reaction",
        )
        ts_bracket = add_ts_bracket_from_points_for(
            active_canvas_for_window(self.window),
            QPointF(-8.0, -28.0),
            QPointF(8.0, 28.0),
        )
        note = canvas_services_for(
            active_canvas_for_window(self.window)
        ).interaction.note_controller.create_text_note(QPointF(55.0, 10.0), "Scheme")

        active_canvas_for_window(self.window).scene().clearSelection()
        bond_items_for_id(active_canvas_for_window(self.window), 0)[0].setSelected(True)
        arrow.setSelected(True)
        ts_bracket.setSelected(True)
        note.setSelected(True)
        self.app.processEvents()
        QTest.qWait(10)

        scene = Molecule3DScene(
            atoms=(
                Molecule3DAtom("C", 0.0, 0.0, 0.0),
                Molecule3DAtom("C", 1.0, 0.0, 0.0),
            ),
            bonds=(Molecule3DBond(0, 1, 1),),
        )

        with patch.object(
            preview.rdkit_adapter,
            "model_to_3d_scene_result",
            return_value=RDKitResult(scene),
        ) as mocked:
            preview.refresh_selected_from_canvas(active_canvas_for_window(self.window))
            self.app.processEvents()
            QTest.qWait(150)
            self.app.processEvents()

        called_model = mocked.call_args.args[0]
        self.assertEqual(len(called_model.atoms), 2)
        self.assertEqual(len(called_model.bonds), 1)

    def test_preview_panel_hint_font_is_zoom_independent(self) -> None:
        preview = preview_for_window(self.window)
        initial_size = preview_overlay_font(preview.font()).pixelSize()

        preview._zoom = 0.4
        zoomed_out_size = preview_overlay_font(preview.font()).pixelSize()

        preview._zoom = 2.8
        zoomed_in_size = preview_overlay_font(preview.font()).pixelSize()

        self.assertEqual(initial_size, 12)
        self.assertEqual(zoomed_out_size, initial_size)
        self.assertEqual(zoomed_in_size, initial_size)

    def test_arrow_default_preset_matches_legacy_acs_values(self) -> None:
        tool_mode_controller = canvas_services_for(
            active_canvas_for_window(self.window)
        ).input.tool_mode_controller
        tool_state_service = services_for_window(self.window).tool_state_service
        tool_mode_controller.set_arrow_line_width(4.0)
        tool_mode_controller.set_arrow_head_scale(0.6)

        tool_state_service.set_arrow_preset(self.window, "Default")
        self.assertAlmostEqual(tool_mode_controller.get_arrow_line_width(), 1.2)
        self.assertAlmostEqual(tool_mode_controller.get_arrow_head_scale(), 0.3)

        tool_mode_controller.set_arrow_line_width(4.0)
        tool_mode_controller.set_arrow_head_scale(0.6)
        tool_state_service.set_arrow_preset(self.window, "ACS")
        self.assertAlmostEqual(tool_mode_controller.get_arrow_line_width(), 1.2)
        self.assertAlmostEqual(tool_mode_controller.get_arrow_head_scale(), 0.3)


if __name__ == "__main__":
    unittest.main()
