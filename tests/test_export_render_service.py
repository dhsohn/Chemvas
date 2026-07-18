import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QLineF, Qt
    from PyQt6.QtGui import QColor, QFont, QImage, QPen
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsLineItem,
        QGraphicsRectItem,
        QGraphicsScene,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.features.export import (
        collect_export_items,
        content_bounds,
        export_scene,
        item_export_bounds,
        render_scene_to_pdf_bytes,
        render_scene_to_svg,
        render_scene_to_svg_bytes,
    )
    from chemvas.ui.graphics_items import AtomDotItem, AtomLabelItem


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for export render tests"
)
class ExportRenderServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _content_scene(self) -> QGraphicsScene:
        scene = QGraphicsScene()
        bond = QGraphicsLineItem(QLineF(0.0, 0.0, 40.0, 0.0))
        bond.setData(0, "bond")
        scene.addItem(bond)
        label = AtomLabelItem("CH3")
        label.setFont(QFont("Arial", 12))
        label.setDefaultTextColor(QColor("#000000"))
        label.setData(0, "atom")
        label.setPos(40.0, -6.0)
        scene.addItem(label)
        return scene

    def test_collect_excludes_transient_overlays(self) -> None:
        scene = self._content_scene()
        outline = QGraphicsRectItem(0.0, 0.0, 10.0, 10.0)
        outline.setData(0, "selection_outline")
        scene.addItem(outline)
        # A role-less overlay (e.g. hover/preview) must also be excluded.
        roleless = QGraphicsRectItem(0.0, 0.0, 5.0, 5.0)
        scene.addItem(roleless)

        roles = {item.data(0) for item in collect_export_items(scene)}
        self.assertIn("bond", roles)
        self.assertIn("atom", roles)
        self.assertNotIn("selection_outline", roles)
        self.assertNotIn(None, roles)

    def test_render_writes_svg_with_outlined_label(self) -> None:
        scene = self._content_scene()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "figure.svg")
            plan = render_scene_to_svg(scene, path, margin=4.0)
            self.assertTrue(os.path.exists(path))
            self.assertGreater(plan.source_w, 0.0)
            with open(path, encoding="utf-8") as handle:
                content = handle.read()

        self.assertIn("<svg", content)
        # The atom label is outlined to vector paths...
        self.assertIn("<path", content)
        # ...so the exported figure carries no font-dependent <text> element.
        self.assertNotIn("<text", content)

    def test_empty_scene_reports_nothing_to_export(self) -> None:
        scene = QGraphicsScene()
        self.assertIsNone(content_bounds([]))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                render_scene_to_svg(scene, os.path.join(tmp, "empty.svg"), margin=4.0)

    def test_atom_label_export_bounds_ignore_hit_radius(self) -> None:
        scene = QGraphicsScene()
        label = AtomLabelItem("N", hit_radius=80.0)
        label.setFont(QFont("Arial", 12))
        label.setData(0, "atom")
        label.setPos(10.0, 20.0)
        scene.addItem(label)

        export_rect = item_export_bounds(label)
        scene_rect = label.sceneBoundingRect()
        bounds = content_bounds([label])

        self.assertLess(export_rect.width(), scene_rect.width())
        self.assertLess(export_rect.height(), scene_rect.height())
        self.assertAlmostEqual(bounds.width(), export_rect.width())
        self.assertAlmostEqual(bounds.height(), export_rect.height())

    def test_atom_dot_export_bounds_ignore_hit_padding_and_transparent_dots(
        self,
    ) -> None:
        scene = QGraphicsScene()
        radical = AtomDotItem(-1.5, -1.5, 3.0, 3.0, hit_padding=24.0)
        radical.setBrush(QColor("#000000"))
        radical.setPen(QPen(Qt.PenStyle.NoPen))
        radical.setData(0, "mark")
        scene.addItem(radical)

        transparent_dot = AtomDotItem(-1.0, -1.0, 2.0, 2.0, hit_padding=24.0)
        transparent_dot.setBrush(QColor(0, 0, 0, 0))
        transparent_dot.setPen(QPen(Qt.PenStyle.NoPen))
        transparent_dot.setData(0, "atom")
        scene.addItem(transparent_dot)

        radical_export_rect = item_export_bounds(radical)
        self.assertLess(
            radical_export_rect.width(), radical.sceneBoundingRect().width()
        )
        self.assertAlmostEqual(
            content_bounds([radical]).width(), radical_export_rect.width()
        )
        self.assertTrue(item_export_bounds(transparent_dot).isNull())
        self.assertIsNone(content_bounds([transparent_dot]))

    def test_vector_clipboard_renderers_return_svg_and_pdf_bytes(self) -> None:
        scene = self._content_scene()
        items = collect_export_items(scene)
        bounds = content_bounds(items)
        assert bounds is not None

        svg_data = render_scene_to_svg_bytes(
            scene, source=bounds, items=items, title="Copy"
        )
        pdf_data = render_scene_to_pdf_bytes(
            scene, source=bounds, items=items, title="Copy"
        )

        self.assertIn(b"<svg", svg_data)
        self.assertIn(b"<path", svg_data)
        self.assertNotIn(b"<text", svg_data)
        self.assertTrue(pdf_data.startswith(b"%PDF-"))

    def test_export_pdf_writes_pdf_file(self) -> None:
        scene = self._content_scene()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "figure.pdf")
            export_scene(scene, path, fmt="pdf", margin=4.0, dpi=300)
            self.assertTrue(os.path.exists(path))
            with open(path, "rb") as handle:
                self.assertTrue(handle.read(5).startswith(b"%PDF-"))

    def test_export_png_carries_dpi_and_plan_size(self) -> None:
        scene = self._content_scene()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "figure.png")
            plan = export_scene(scene, path, fmt="png", margin=4.0, dpi=300)
            self.assertTrue(os.path.exists(path))
            loaded = QImage(path)
            self.assertEqual(loaded.width(), max(1, round(plan.out_w_pt / 72.0 * 300)))
            self.assertEqual(loaded.height(), max(1, round(plan.out_h_pt / 72.0 * 300)))
            # 300 dpi -> ~11811 dots per meter, written into the PNG metadata.
            self.assertAlmostEqual(loaded.dotsPerMeterX(), round(300 / 0.0254), delta=2)

    def test_unit_scale_sets_physical_size(self) -> None:
        scene = self._content_scene()
        with tempfile.TemporaryDirectory() as tmp:
            full = export_scene(
                scene,
                os.path.join(tmp, "a.png"),
                fmt="png",
                margin=4.0,
                dpi=300,
                unit_scale=1.0,
            )
            half = export_scene(
                scene,
                os.path.join(tmp, "b.png"),
                fmt="png",
                margin=4.0,
                dpi=300,
                unit_scale=0.5,
            )
        # Same source rect, but the physical/point size halves with unit_scale.
        self.assertAlmostEqual(half.source_w, full.source_w)
        self.assertAlmostEqual(half.out_w_pt, full.out_w_pt * 0.5)

    def test_target_width_fits_physical_width(self) -> None:
        scene = self._content_scene()
        with tempfile.TemporaryDirectory() as tmp:
            plan = export_scene(
                scene,
                os.path.join(tmp, "c.svg"),
                fmt="svg",
                margin=4.0,
                target_width_pt=238.11,
            )
        self.assertAlmostEqual(plan.out_w_pt, 238.11, places=2)

    def test_export_tiff_writes_file(self) -> None:
        scene = self._content_scene()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "figure.tiff")
            plan = export_scene(scene, path, fmt="tiff", margin=4.0, dpi=150)
            self.assertGreater(os.path.getsize(path), 0)
            from PIL import Image

            with Image.open(path) as image:
                self.assertEqual(
                    image.size,
                    (
                        max(1, round(plan.out_w_pt / 72.0 * 150)),
                        max(1, round(plan.out_h_pt / 72.0 * 150)),
                    ),
                )
                self.assertAlmostEqual(image.info["dpi"][0], 150, delta=1)

    def test_white_background_fills_corner_pixel(self) -> None:
        scene = self._content_scene()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "figure.png")
            export_scene(
                scene, path, fmt="png", margin=4.0, dpi=150, background="white"
            )
            loaded = QImage(path)
            corner = loaded.pixelColor(0, 0)
            self.assertEqual(corner.alpha(), 255)
            self.assertEqual(
                (corner.red(), corner.green(), corner.blue()), (255, 255, 255)
            )

    def test_selection_items_shrink_bounds(self) -> None:
        scene = self._content_scene()
        bond = next(
            item for item in collect_export_items(scene) if item.data(0) == "bond"
        )
        with tempfile.TemporaryDirectory() as tmp:
            full = export_scene(
                scene, os.path.join(tmp, "full.svg"), fmt="svg", margin=4.0
            )
            only_bond = export_scene(
                scene,
                os.path.join(tmp, "bond.svg"),
                fmt="svg",
                items=[bond],
                margin=4.0,
            )
        self.assertLess(only_bond.source_w, full.source_w)

    def test_unsupported_format_raises(self) -> None:
        scene = self._content_scene()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                export_scene(scene, os.path.join(tmp, "x.bmp"), fmt="bmp", margin=4.0)


if __name__ == "__main__":
    unittest.main()
