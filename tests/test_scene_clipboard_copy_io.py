import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QMimeData, QRectF
    from PyQt6.QtWidgets import QApplication, QGraphicsRectItem, QGraphicsScene
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.ui.scene_clipboard_copy_io import (
        CLIPBOARD_PDF_MIME,
        CLIPBOARD_SVG_MIME,
        build_clipboard_mime_data,
        render_clipboard_raster_image,
        set_vector_clipboard_data,
    )
    from chemvas.ui.scene_clipboard_transaction_logic import ClipboardCopyPlan

    class _FakeCanvas:
        def __init__(self, scene: QGraphicsScene) -> None:
            self._scene = scene

        def scene(self) -> QGraphicsScene:
            return self._scene


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for scene clipboard copy I/O tests"
)
class SceneClipboardCopyIOTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_render_clipboard_raster_image_uses_plan_dimensions_and_scale(self) -> None:
        scene = QGraphicsScene()
        scene.addItem(QGraphicsRectItem(0.0, 0.0, 10.0, 10.0))
        plan = ClipboardCopyPlan(
            QRectF(0.0, 0.0, 12.0, 8.0),
            scale=2.0,
            image_width=24,
            image_height=16,
            payload_json=None,
        )

        image = render_clipboard_raster_image(_FakeCanvas(scene), plan)

        self.assertEqual((image.width(), image.height()), (24, 16))
        self.assertAlmostEqual(image.devicePixelRatio(), 2.0)

    def test_build_clipboard_mime_data_sets_raster_vector_and_payload_formats(
        self,
    ) -> None:
        scene = QGraphicsScene()
        item = QGraphicsRectItem(0.0, 0.0, 10.0, 10.0)
        scene.addItem(item)
        plan = ClipboardCopyPlan(
            QRectF(-2.0, -2.0, 14.0, 14.0),
            scale=1.0,
            image_width=14,
            image_height=14,
            payload_json='{"format":"chemvas-selection"}',
        )

        mime_data = build_clipboard_mime_data(
            _FakeCanvas(scene),
            items=[item],
            plan=plan,
            payload_mime_type="application/x-test-selection",
            bond_line_width=1.0,
        )

        self.assertTrue(mime_data.hasImage())
        self.assertTrue(mime_data.hasFormat(CLIPBOARD_SVG_MIME))
        self.assertTrue(mime_data.hasFormat(CLIPBOARD_PDF_MIME))
        self.assertEqual(
            bytes(mime_data.data("application/x-test-selection")),
            b'{"format":"chemvas-selection"}',
        )

    def test_set_vector_clipboard_data_ignores_empty_bounds_and_render_errors(
        self,
    ) -> None:
        scene = QGraphicsScene()
        canvas = _FakeCanvas(scene)
        mime_data = QMimeData()

        set_vector_clipboard_data(
            mime_data, canvas=canvas, items=[], bond_line_width=1.0
        )

        self.assertFalse(mime_data.hasFormat(CLIPBOARD_SVG_MIME))
        self.assertFalse(mime_data.hasFormat(CLIPBOARD_PDF_MIME))

        item = QGraphicsRectItem(0.0, 0.0, 10.0, 10.0)
        with mock.patch(
            "chemvas.ui.scene_clipboard_copy_io.render_canvas_selection_vector_bytes",
            side_effect=RuntimeError,
        ):
            set_vector_clipboard_data(
                mime_data, canvas=canvas, items=[item], bond_line_width=1.0
            )

        self.assertFalse(mime_data.hasFormat(CLIPBOARD_SVG_MIME))
        self.assertFalse(mime_data.hasFormat(CLIPBOARD_PDF_MIME))


if __name__ == "__main__":
    unittest.main()
