from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QWidget
except ModuleNotFoundError:
    QApplication = None
    QTest = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.model import MoleculeModel
    from core.rdkit_adapter import Molecule3DAtom, Molecule3DBond, Molecule3DScene
    from ui.preview_3d import Preview3D


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

    def model_to_3d_scene(self, model, atom_annotations=None):
        self.calls.append((model, atom_annotations))
        scene, error = self._responses.pop(0)
        self.last_error = error
        return scene


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

        preview.refresh_from_canvas(canvas)
        self._wait_for_rebuild()

        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(preview._scene, scene)
        self.assertEqual(preview._formula_text, "")
        self.assertEqual(preview._mw_text, "")

        preview.refresh_from_canvas(canvas)

        self.assertIsNone(preview._scene)
        self.assertEqual(preview._message, "No structure selected")
        self.assertIsNone(preview._current_signature)
        self.assertEqual(preview._formula_text, "")
        self.assertEqual(preview._mw_text, "")

        preview.refresh_from_canvas(canvas)
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

        preview.refresh_from_canvas(canvas)
        self._wait_for_rebuild()

        self.assertEqual(len(adapter.calls), 1)
        self.assertIsNone(preview._scene)
        self.assertEqual(preview._message, "Temporary 3D failure")
        self.assertIsNone(preview._current_signature)

        preview.refresh_from_canvas(canvas)
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

        self.assertEqual(preview._project_scene(Molecule3DScene(atoms=(), bonds=())), [])

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
        with mock.patch.object(preview, "_project_scene", return_value=[]):
            preview.paintEvent(None)

        with mock.patch.object(preview, "_project_scene", return_value=[(40.0, 50.0, 0.0, 8.0)]):
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

        self.assertEqual(preview._current_signature, preview._payload_signature(model, {0: {"formal_charge": 1}}))
        self.assertEqual(preview._pending_model, model)
        self.assertEqual(preview._pending_annotations, {0: {"formal_charge": 1}})
        self.assertEqual(preview._info_lines(), ["Formula: C2H6O", "MW: 46.07"])
        self.assertGreater(preview._footer_height(preview._info_lines()), 0.0)
        self.assertEqual(start.call_count, 1)
        self.assertEqual(safe_update.call_count, 2)

        projected = preview._project_scene(self._make_scene(), footer_height=80.0)
        self.assertEqual(len(projected), 2)

        preview._scene = self._make_scene()
        preview.paintEvent(None)

    def test_inspector_layout_and_state_helpers_cover_preview_panel_sections(self) -> None:
        preview = self._create_preview(SequencedAdapter([]))
        preview.resize(320, 260)

        self.assertEqual(preview._metadata_summary(), "No structure loaded")
        self.assertEqual(preview._status_badge()[0], "Empty")
        self.assertEqual(preview._empty_state_text(), ("No 3D structure", "Canvas has no molecule"))

        preview._message = "There is no chemical structure to export."
        self.assertEqual(preview._metadata_summary(), "No structure loaded")
        self.assertEqual(preview._status_badge()[0], "Empty")
        self.assertEqual(preview._empty_state_text(), ("No 3D structure", "Canvas has no molecule"))

        preview._message = "Updating 3D preview..."
        self.assertEqual(preview._metadata_summary(), "Preparing coordinates")
        self.assertEqual(preview._status_badge()[0], "Building")
        self.assertEqual(preview._empty_state_text(), ("Building preview", "Preparing coordinates"))

        preview._message = "Temporary 3D failure while preparing the selected structure"
        self.assertEqual(preview._metadata_summary(), "Preview needs attention")
        self.assertEqual(preview._status_badge()[0], "Issue")
        self.assertEqual(
            preview._empty_state_text(),
            ("Preview unavailable", "Temporary 3D failure while preparing the selected structure"),
        )

        preview._scene = self._make_scene()
        preview.set_info("C2H6O", "46.07")
        self.assertEqual(preview._metadata_summary(), "2 atoms / 1 bond")
        self.assertEqual(preview._status_badge()[0], "Ready")
        self.assertEqual(preview._info_items(), [("FORMULA", "C2H6O"), ("MW", "46.07")])
        self.assertGreaterEqual(preview._footer_height(preview._info_lines()), 68.0)

        layout = preview._layout_rects(preview._info_lines())
        self.assertFalse(layout["footer"].isNull())
        self.assertLess(layout["header"].bottom(), layout["viewport"].top())
        self.assertLess(layout["viewport"].bottom(), layout["footer"].top())
        self.assertTrue(layout["viewport"].contains(layout["molecule"]))
        footer_items = preview._footer_item_rects(layout["footer"], 2)
        self.assertEqual(len(footer_items), 2)
        self.assertGreater(footer_items[0].width(), layout["footer"].width() * 0.9)
        self.assertLess(footer_items[0].bottom(), footer_items[1].top())

        projected = preview._project_scene(preview._scene, viewport_rect=QRectF(40.0, 70.0, 220.0, 120.0))
        self.assertEqual(len(projected), 2)
        self.assertTrue(all(40.0 <= atom[0] <= 260.0 for atom in projected))


if __name__ == "__main__":
    unittest.main()
