from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
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

        preview.refresh_from_canvas(canvas)

        self.assertIsNone(preview._scene)
        self.assertEqual(preview._message, "No structure selected")
        self.assertIsNone(preview._current_signature)

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


if __name__ == "__main__":
    unittest.main()
