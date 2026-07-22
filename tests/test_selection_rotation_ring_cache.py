import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QPolygonF
    from PyQt6.QtWidgets import QApplication, QGraphicsPolygonItem
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    import chemvas.ui.canvas_ring_fill_scene_service as ring_fill_service
    import chemvas.ui.selection_rotation_preview_transaction as preview_transaction
    from chemvas.ui.canvas_lifecycle import schedule_canvas_deletion_for
    from chemvas.ui.canvas_view import CanvasView


@unittest.skipUnless(QApplication is not None, "PyQt6 is required")
class SelectionRotationRingCacheTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_actual_many_ring_session_scans_registry_only_at_authority_capture(
        self,
    ) -> None:
        canvas = CanvasView()
        controller = canvas.services.interaction.selection_rotation_controller
        atom_id = canvas.model.add_atom("C", 0.0, 0.0)
        controller.rotation.atom_ids = {atom_id}
        polygon = QPolygonF([QPointF(0.0, 0.0), QPointF(2.0, 0.0), QPointF(1.0, 2.0)])
        matching_ring = QGraphicsPolygonItem(polygon)
        matching_ring.setData(0, "ring")
        matching_ring.setData(2, [atom_id])
        canvas.scene().addItem(matching_ring)

        unrelated_rings = []
        for index in range(512):
            ring = QGraphicsPolygonItem(polygon)
            ring.setData(0, "ring")
            base = 10_000 + index * 3
            ring.setData(2, [base, base + 1, base + 2])
            canvas.scene().addItem(ring)
            unrelated_rings.append(ring)
        canvas.runtime_state.scene_items_state.ring_items = [
            matching_ring,
            *unrelated_rings,
        ]

        authority = None
        original_scan = preview_transaction._affected_ring_items
        try:
            with (
                mock.patch.object(
                    preview_transaction,
                    "_affected_ring_items",
                    wraps=original_scan,
                ) as ring_registry_scan,
                mock.patch.object(
                    ring_fill_service,
                    "ring_items_for",
                    wraps=ring_fill_service.ring_items_for,
                ) as frame_registry_scan,
            ):
                authority = preview_transaction.capture_rotation_preview_authority(
                    controller,
                    {atom_id},
                )
                controller._rotation_preview_authority = authority
                self.assertEqual(
                    authority.affected_ring_items,
                    (matching_ring,),
                )

                for _ in range(8):
                    authority.run_update(
                        lambda: controller.refresh_atom_geometry({atom_id})
                    )

                ring_registry_scan.assert_called_once_with(
                    canvas,
                    {atom_id},
                )
                frame_registry_scan.assert_not_called()
        finally:
            controller._rotation_preview_authority = None
            if authority is not None:
                authority.release()
            schedule_canvas_deletion_for(canvas)
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
