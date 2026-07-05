from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
    from PyQt6.QtGui import QFont, QFontMetricsF
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QWidget
except ModuleNotFoundError:
    QApplication = None
    QTest = None

if QApplication is not None:
    from core.model import MoleculeModel
    from core.rdkit_adapter import (
        Molecule3DAtom,
        Molecule3DBond,
        Molecule3DScene,
        MoleculeIdentifiers,
    )
    from ui.main_window_palette import PALETTE
    from ui.preview_3d import Preview3D
    from ui.preview_3d_painter import (
        preview_caption_font,
        preview_footer_height_for_lines,
        preview_layout_for_widget,
        project_preview_paint_scene,
    )
    from ui.preview_3d_renderer import status_badge_width
    from ui.preview_3d_state import (
        preview_empty_state_text,
        preview_info_items,
        preview_info_lines,
        preview_metadata_summary,
        preview_payload_signature,
        preview_status_badge,
    )


class _FakeMouseEvent:
    def __init__(
        self,
        position: QPointF,
        *,
        button=Qt.MouseButton.NoButton,
        buttons=Qt.MouseButton.NoButton,
    ) -> None:
        self._position = QPointF(position)
        self._button = button
        self._buttons = buttons

    def button(self):
        return self._button

    def buttons(self):
        return self._buttons

    def position(self):
        return QPointF(self._position)


class _FakeWheelEvent:
    def __init__(self, delta: int) -> None:
        self._delta = delta

    def angleDelta(self):
        return QPoint(0, self._delta)


class SequencedCanvas:
    def __init__(self, payloads) -> None:
        self._payloads = list(payloads)

    def build_3d_conversion_payload(self):
        payload = self._payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        return payload


class SequencedAdapter:
    def __init__(self, responses) -> None:
        self._responses = list(responses)
        self.calls = []
        self.last_error = None

    def compute_props(self, model):
        return None, None, None

    def compute_identifiers(self, model):
        return MoleculeIdentifiers()

    def model_to_3d_scene(self, model, atom_annotations=None):
        self.calls.append((model, atom_annotations))
        scene, error = self._responses.pop(0)
        self.last_error = error
        return scene


class AnnotatedIdentifierAdapter(SequencedAdapter):
    def __init__(self, responses) -> None:
        super().__init__(responses)
        self.identifier_annotations = []

    def compute_identifiers(self, model):
        annotations = getattr(model, "atom_annotations", {})
        self.identifier_annotations.append(
            {atom_id: dict(values) for atom_id, values in annotations.items()}
        )
        formal_charge = sum(values.get("formal_charge", 0) for values in annotations.values())
        radical_electrons = sum(values.get("radical_electrons", 0) for values in annotations.values())
        return MoleculeIdentifiers(
            formula=f"charge={formal_charge};radical={radical_electrons}",
            mw=12.0 + formal_charge + radical_electrons,
            smiles=f"[charge={formal_charge}].[radical={radical_electrons}]",
        )


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for Preview3D tests")
class Preview3DRecoveryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def tearDown(self) -> None:
        preview = getattr(self, "preview", None)
        if preview is not None:
            preview.close()
        self.app.processEvents()
        QTest.qWait(10)

    def _make_model(self) -> MoleculeModel:
        model = MoleculeModel()
        atom_a = model.add_atom("C", 0.0, 0.0)
        atom_b = model.add_atom("O", 30.0, 0.0)
        model.add_bond(atom_a, atom_b, 2)
        return model

    def _make_scene(self) -> Molecule3DScene:
        return Molecule3DScene(
            atoms=(
                Molecule3DAtom("C", 0.0, 0.0, 0.0),
                Molecule3DAtom("O", 1.2, 0.0, 0.5),
            ),
            bonds=(Molecule3DBond(0, 1, 2),),
        )

    def _create_preview(self, adapter: SequencedAdapter) -> Preview3D:
        self.preview = Preview3D(rdkit_adapter=adapter)
        self.preview._update_timer.setInterval(0)
        self.preview.show()
        self.app.processEvents()
        return self.preview

    def _wait_for_rebuild(self) -> None:
        self.app.processEvents()
        QTest.qWait(10)
        self.app.processEvents()

    def test_rdkit_adapter_can_be_rebound_without_private_access(self) -> None:
        adapter_a = SequencedAdapter([])
        adapter_b = SequencedAdapter([])
        preview = self._create_preview(adapter_a)

        self.assertIs(preview.rdkit_adapter, adapter_a)

        preview.set_rdkit_adapter(adapter_b)

        self.assertIs(preview.rdkit_adapter, adapter_b)

    def test_sync_preview_identifiers_use_payload_annotations(self) -> None:
        model = self._make_model()
        annotations = {
            0: {"formal_charge": 1},
            1: {"radical_electrons": 1},
        }
        scene = self._make_scene()
        adapter = AnnotatedIdentifierAdapter([(scene, None)])
        preview = self._create_preview(adapter)

        preview._set_canvas_structure(model, annotations)
        self._wait_for_rebuild()

        self.assertEqual(adapter.identifier_annotations, [annotations])
        self.assertEqual(adapter.calls, [(model, annotations)])
        self.assertEqual(preview._formula_text, "charge=1;radical=1")
        self.assertEqual(preview._mw_text, "14.00")
        self.assertEqual(preview._smiles_text, "[charge=1].[radical=1]")

    def test_preview_recovers_after_payload_failure_with_same_structure(self) -> None:
        model = self._make_model()
        scene = self._make_scene()
        adapter = SequencedAdapter([(scene, None), (scene, None)])
        canvas = SequencedCanvas(
            [
                (model, {0: {"formal_charge": 1}}),
                RuntimeError("No structure selected"),
                (model, {0: {"formal_charge": 1}}),
            ]
        )
        preview = self._create_preview(adapter)

        with mock.patch(
            "ui.preview_3d.build_selected_3d_conversion_payload_for",
            side_effect=lambda canvas: canvas.build_3d_conversion_payload(),
        ):
            preview.refresh_selected_from_canvas(canvas)
            self._wait_for_rebuild()

            self.assertEqual(len(adapter.calls), 1)
            self.assertEqual(preview._scene, scene)
            self.assertEqual(preview._formula_text, "")
            self.assertEqual(preview._mw_text, "")

            preview.refresh_selected_from_canvas(canvas)

            self.assertIsNone(preview._scene)
            self.assertEqual(preview._message, "No structure selected")
            self.assertIsNone(preview._current_signature)
            self.assertEqual(preview._formula_text, "")
            self.assertEqual(preview._mw_text, "")

            preview.refresh_selected_from_canvas(canvas)
            self._wait_for_rebuild()

            self.assertEqual(len(adapter.calls), 2)
            self.assertEqual(preview._scene, scene)
            self.assertEqual(preview._message, "")

    def test_preview_retries_same_structure_after_build_failure(self) -> None:
        model = self._make_model()
        scene = self._make_scene()
        adapter = SequencedAdapter([(None, "Temporary 3D failure"), (scene, None)])
        canvas = SequencedCanvas([(model, None), (model, None)])
        preview = self._create_preview(adapter)

        with mock.patch(
            "ui.preview_3d.build_selected_3d_conversion_payload_for",
            side_effect=lambda canvas: canvas.build_3d_conversion_payload(),
        ):
            preview.refresh_selected_from_canvas(canvas)
            self._wait_for_rebuild()

            self.assertEqual(len(adapter.calls), 1)
            self.assertIsNone(preview._scene)
            self.assertEqual(preview._message, "Temporary 3D failure")
            self.assertIsNone(preview._current_signature)

            preview.refresh_selected_from_canvas(canvas)
            self._wait_for_rebuild()

            self.assertEqual(len(adapter.calls), 2)
            self.assertEqual(preview._scene, scene)
            self.assertEqual(preview._message, "")

    def test_rebuild_scene_handles_disposed_missing_pending_and_empty_project_scene(self) -> None:
        preview = self._create_preview(SequencedAdapter([]))
        preview._disposed = True
        preview._pending_model = self._make_model()

        preview._rebuild_scene()
        self.assertIsNone(preview._scene)

        preview._disposed = False
        preview._scene = self._make_scene()
        preview._pending_model = None
        with mock.patch.object(preview, "_safe_update") as safe_update:
            preview._rebuild_scene()
        self.assertIsNone(preview._scene)
        self.assertEqual(preview._message, "3D preview unavailable")
        safe_update.assert_called_once_with()

        self.assertEqual(
            project_preview_paint_scene(
                Molecule3DScene(atoms=(), bonds=()),
                rotation_x=preview._rotation_x,
                rotation_y=preview._rotation_y,
                zoom=preview._zoom,
                widget_rect=QRectF(preview.rect()),
            ),
            [],
        )

    def test_mouse_and_wheel_events_update_rotation_zoom_and_last_pos(self) -> None:
        preview = self._create_preview(SequencedAdapter([]))

        with (
            mock.patch.object(QWidget, "mousePressEvent", new=mock.Mock(return_value=None)) as base_press,
            mock.patch.object(QWidget, "mouseMoveEvent", new=mock.Mock(return_value=None)) as base_move,
            mock.patch.object(QWidget, "mouseReleaseEvent", new=mock.Mock(return_value=None)) as base_release,
            mock.patch.object(QWidget, "wheelEvent", new=mock.Mock(return_value=None)) as base_wheel,
            mock.patch.object(preview, "update") as update,
        ):
            press = _FakeMouseEvent(QPointF(4.0, 5.0), button=Qt.MouseButton.LeftButton)
            preview.mousePressEvent(press)
            self.assertEqual(preview._last_pos, QPointF(4.0, 5.0))

            rotation_before = (preview._rotation_x, preview._rotation_y)
            move = _FakeMouseEvent(QPointF(10.0, 8.0), buttons=Qt.MouseButton.LeftButton)
            preview.mouseMoveEvent(move)
            self.assertNotEqual((preview._rotation_x, preview._rotation_y), rotation_before)
            self.assertEqual(preview._last_pos, QPointF(10.0, 8.0))
            update.assert_called_once_with()

            release = _FakeMouseEvent(QPointF(10.0, 8.0), button=Qt.MouseButton.LeftButton)
            preview.mouseReleaseEvent(release)
            self.assertIsNone(preview._last_pos)

            zoom_before = preview._zoom
            preview.wheelEvent(_FakeWheelEvent(120))
            self.assertGreater(preview._zoom, zoom_before)

            zoom_after_in = preview._zoom
            preview.wheelEvent(_FakeWheelEvent(0))
            self.assertEqual(preview._zoom, zoom_after_in)

            preview.wheelEvent(_FakeWheelEvent(-120))
            self.assertLess(preview._zoom, zoom_after_in)

            base_press.assert_called_once_with(press)
            base_move.assert_called_once_with(move)
            base_release.assert_called_once_with(release)
            self.assertEqual(base_wheel.call_count, 3)

    def test_safe_update_and_paint_event_cover_runtime_invalid_bond_and_empty_projection_paths(self) -> None:
        preview = self._create_preview(SequencedAdapter([]))
        preview._disposed = True
        preview._safe_update()

        preview._disposed = False
        preview.update = mock.Mock(side_effect=RuntimeError("deleted"))
        preview._safe_update()
        self.assertTrue(preview._disposed)

        preview._disposed = False
        preview._scene = Molecule3DScene(
            atoms=(Molecule3DAtom("C", 0.0, 0.0, 0.0),),
            bonds=(Molecule3DBond(0, 99, 1),),
        )
        preview._message = "No projection"
        with mock.patch("ui.preview_3d_painter.project_preview_paint_scene", return_value=[]):
            preview.paintEvent(None)

        with mock.patch(
            "ui.preview_3d_painter.project_preview_paint_scene",
            return_value=[(40.0, 50.0, 0.0, 8.0)],
        ):
            preview.paintEvent(None)

    def test_set_structure_set_info_and_footer_helpers_cover_signature_info_and_overlay_paths(self) -> None:
        preview = self._create_preview(SequencedAdapter([]))
        model = self._make_model()

        with (
            mock.patch.object(preview, "_safe_update") as safe_update,
            mock.patch.object(preview._update_timer, "start") as start,
        ):
            preview.set_structure(model, {0: {"formal_charge": 1}})
            preview.set_structure(model, {0: {"formal_charge": 1}})
            preview.set_info("C2H6O", "46.07")
            preview.set_info("C2H6O", "46.07")

        self.assertEqual(preview._current_signature, preview_payload_signature(model, {0: {"formal_charge": 1}}))
        self.assertEqual(preview._pending_model, model)
        self.assertEqual(preview._pending_annotations, {0: {"formal_charge": 1}})
        info_lines = preview_info_lines("C2H6O", "46.07")
        self.assertEqual(info_lines, ["Formula: C2H6O", "MW: 46.07"])
        self.assertGreater(preview_footer_height_for_lines(info_lines, preview.font()), 0.0)
        self.assertEqual(start.call_count, 1)
        self.assertEqual(safe_update.call_count, 2)

        projected = project_preview_paint_scene(
            self._make_scene(),
            rotation_x=preview._rotation_x,
            rotation_y=preview._rotation_y,
            zoom=preview._zoom,
            widget_rect=QRectF(preview.rect()),
            footer_height=80.0,
        )
        self.assertEqual(len(projected), 2)

        preview._scene = self._make_scene()
        preview.paintEvent(None)

    def test_inspector_layout_and_state_helpers_cover_preview_panel_sections(self) -> None:
        preview = self._create_preview(SequencedAdapter([]))
        preview.resize(320, 260)

        self.assertEqual(preview_metadata_summary(preview._scene, preview._message), "")
        self.assertEqual(preview_status_badge(preview._scene, preview._message)[0], "Empty")
        self.assertEqual(
            preview_empty_state_text(preview._message),
            ("No molecule yet", "Draw or paste a structure to preview it in 3D."),
        )

        preview._message = "There is no chemical structure to export."
        self.assertEqual(preview_metadata_summary(preview._scene, preview._message), "")
        self.assertEqual(preview_status_badge(preview._scene, preview._message)[0], "Empty")
        self.assertEqual(
            preview_empty_state_text(preview._message),
            ("No molecule yet", "Draw or paste a structure to preview it in 3D."),
        )

        preview._message = "Updating 3D preview..."
        self.assertEqual(preview_metadata_summary(preview._scene, preview._message), "Preparing coordinates")
        self.assertEqual(preview_status_badge(preview._scene, preview._message)[0], "Building")
        self.assertEqual(preview_empty_state_text(preview._message), ("Building preview", "Preparing coordinates"))

        preview._message = "Temporary 3D failure while preparing the selected structure"
        self.assertEqual(preview_metadata_summary(preview._scene, preview._message), "Preview needs attention")
        self.assertEqual(preview_status_badge(preview._scene, preview._message)[0], "Issue")
        self.assertEqual(
            preview_empty_state_text(preview._message),
            ("Preview unavailable", "Temporary 3D failure while preparing the selected structure"),
        )

        preview._scene = self._make_scene()
        preview.set_info("C2H6O", "46.07")
        self.assertEqual(preview_metadata_summary(preview._scene, preview._message), "2 atoms / 1 bond")
        self.assertEqual(preview_status_badge(preview._scene, preview._message)[0], "Ready")
        self.assertEqual(preview_info_items("C2H6O", "46.07"), [("FORMULA", "C2H6O"), ("MW", "46.07")])
        info_lines = preview_info_lines("C2H6O", "46.07")
        self.assertGreaterEqual(preview_footer_height_for_lines(info_lines, preview.font()), 68.0)

        layout = preview_layout_for_widget(QRectF(preview.rect()), info_lines, preview.font())
        self.assertFalse(layout["footer"].isNull())
        self.assertLess(layout["header"].bottom(), layout["viewport"].top())
        self.assertLess(layout["viewport"].bottom(), layout["footer"].top())

    def test_export_button_sits_left_of_ready_badge(self) -> None:
        preview = self._create_preview(SequencedAdapter([]))
        preview.resize(420, 320)
        export_callback = mock.Mock()

        preview.set_export_xyz_action(export_callback)

        button = preview.export_xyz_button
        self.assertIsNotNone(button)
        assert button is not None
        self.assertFalse(button.isVisible())

        preview._scene = self._make_scene()
        preview.set_info("CO", "28.01")
        preview._sync_export_xyz_button()

        layout = preview_layout_for_widget(
            QRectF(preview.rect()),
            [],
            preview.font(),
        )
        self.assertTrue(button.isVisible())
        self.assertEqual(button.objectName(), "preview_export_xyz_button")
        self.assertEqual(button.text(), "Export 3D")
        self.assertTrue(button.icon().isNull())
        self.assertEqual(button.toolButtonStyle(), Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.assertEqual(button.font().pixelSize(), 11)
        self.assertEqual(button.font().weight(), QFont.Weight.DemiBold)
        self.assertIn(f"background: {PALETTE['surface_input']}", button.styleSheet())
        self.assertIn(f"border: 1px solid {PALETTE['border_strong']}", button.styleSheet())
        self.assertIn(f"border-color: {PALETTE['checked_border']}", button.styleSheet())
        self.assertIn("text-align: center", button.styleSheet())
        # The "Ready" status badge is painted flush to the header's right edge;
        # the Export button must sit to its left so it does not cover the badge.
        badge_text = preview_status_badge(preview._scene, preview._message)[0]
        badge_width = status_badge_width(badge_text, QFontMetricsF(preview_caption_font(preview.font())))
        expected_right = round(layout["header"].right() - badge_width - 8.0)
        self.assertAlmostEqual(button.geometry().right(), expected_right, delta=2)
        self.assertLess(button.geometry().right(), round(layout["header"].right() - badge_width))
        self.assertAlmostEqual(button.geometry().top(), round(layout["header"].top() + 4.0), delta=1)

        button.click()
        export_callback.assert_called_once_with()
        self.assertTrue(layout["viewport"].contains(layout["molecule"]))
        self.assertTrue(layout["footer"].isNull())

        projected = project_preview_paint_scene(
            preview._scene,
            rotation_x=preview._rotation_x,
            rotation_y=preview._rotation_y,
            zoom=preview._zoom,
            widget_rect=QRectF(preview.rect()),
            viewport_rect=QRectF(40.0, 70.0, 220.0, 120.0),
        )
        self.assertEqual(len(projected), 2)
        self.assertTrue(all(40.0 <= atom[0] <= 260.0 for atom in projected))

    def test_copy_buttons_appear_and_copy_identifiers_to_clipboard(self) -> None:
        preview = self._create_preview(SequencedAdapter([]))
        preview.resize(560, 360)
        preview.set_export_xyz_action(mock.Mock())
        preview._scene = self._make_scene()
        preview.set_info("C2H4O", "44.05", "CC=O", "IKHGUXGNUITLKF-UHFFFAOYSA-N")
        preview._sync_export_xyz_button()

        smiles_button = preview._copy_smiles_button
        inchikey_button = preview._copy_inchikey_button
        export_button = preview.export_xyz_button
        assert smiles_button is not None
        assert inchikey_button is not None
        assert export_button is not None
        self.assertTrue(smiles_button.isVisible())
        self.assertTrue(inchikey_button.isVisible())
        self.assertEqual(smiles_button.objectName(), "preview_copy_smiles_button")
        # Copy buttons sit to the left of the Export 3D button.
        self.assertLessEqual(smiles_button.geometry().right(), inchikey_button.geometry().left())
        self.assertLessEqual(inchikey_button.geometry().right(), export_button.geometry().left())

        smiles_button.click()
        self.assertEqual(QApplication.clipboard().text(), "CC=O")
        self.assertEqual(smiles_button.text(), "Copied")

        inchikey_button.click()
        self.assertEqual(QApplication.clipboard().text(), "IKHGUXGNUITLKF-UHFFFAOYSA-N")

    def test_copy_buttons_hidden_when_identifiers_absent(self) -> None:
        preview = self._create_preview(SequencedAdapter([]))
        preview.set_export_xyz_action(mock.Mock())
        preview._scene = self._make_scene()
        preview.set_info("C2H4O", "44.05")
        preview._sync_export_xyz_button()

        assert preview._copy_smiles_button is not None
        assert preview._copy_inchikey_button is not None
        self.assertFalse(preview._copy_smiles_button.isVisible())
        self.assertFalse(preview._copy_inchikey_button.isVisible())

    def test_copy_buttons_appear_when_window_shown_after_building_while_hidden(self) -> None:
        # Regression: the Molecule Info preview is refreshed when the selection
        # changes, which can happen while its window is still closed. The copy
        # buttons must still appear once the window is shown — their visibility
        # must not depend on the Export button being visible at sync time.
        container = QWidget()
        container.resize(560, 520)
        self.addCleanup(container.close)
        preview = Preview3D(rdkit_adapter=SequencedAdapter([]))
        preview.setParent(container)
        preview.resize(560, 520)
        preview.set_export_xyz_action(mock.Mock())
        preview._scene = self._make_scene()
        preview.set_info("C2H4O", "44.05", "CC=O", "IKHGUXGNUITLKF-UHFFFAOYSA-N")
        preview._sync_export_xyz_button()

        assert preview._copy_smiles_button is not None
        assert preview._copy_inchikey_button is not None
        self.assertFalse(preview._copy_smiles_button.isVisible())

        container.show()
        self.app.processEvents()

        assert preview.export_xyz_button is not None
        self.assertTrue(preview.export_xyz_button.isVisible())
        self.assertTrue(preview._copy_smiles_button.isVisible())
        self.assertTrue(preview._copy_inchikey_button.isVisible())


if __name__ == "__main__":
    unittest.main()
