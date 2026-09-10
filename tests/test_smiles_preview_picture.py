import copy
import math
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication

from chemvas.domain.document import MoleculeModel
from chemvas.features.insertion import smiles_preview_center, smiles_preview_offset
from chemvas.ui.canvas_insert_state import insert_state_for
from chemvas.ui.canvas_lifecycle import schedule_canvas_deletion_for
from chemvas.ui.canvas_service_ports import insert_controller_for_access
from chemvas.ui.canvas_view import CanvasView
from chemvas.ui.smiles_preview_picture import render_smiles_preview_picture
from tests.canvas_factory import build_canvas_view

SMILES = "OCc1ccccc1"


def _benzyl_alcohol() -> MoleculeModel:
    """Benzyl alcohol as the SMILES adapter lays it out: an aromatic ring with
    alternating double bonds, a methylene and a labelled oxygen."""
    model = MoleculeModel()
    ring = [
        model.add_atom(
            "C",
            20.0 * math.cos(math.radians(60.0 * i)),
            20.0 * math.sin(math.radians(60.0 * i)),
        )
        for i in range(6)
    ]
    for i in range(6):
        bond_id = model.add_bond(ring[i], ring[(i + 1) % 6], 2 if i % 2 == 0 else 1)
        if i % 2 == 0:
            model.bonds[bond_id].style = "double"
    methylene = model.add_atom("C", 40.0, 0.0)
    oxygen = model.add_atom("O", 50.0, 17.32)
    model.add_bond(ring[0], methylene, 1)
    model.add_bond(methylene, oxygen, 1)
    return model


def _atom_snapshot(model: MoleculeModel) -> list[tuple[int, str, float, float]]:
    return [(atom_id, a.element, a.x, a.y) for atom_id, a in model.atoms.items()]


def _render_scene(scene, region: QRectF) -> QImage:
    image = QImage(
        int(region.width()) * 4, int(region.height()) * 4, QImage.Format.Format_ARGB32
    )
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    scene.render(painter, QRectF(0.0, 0.0, image.width(), image.height()), region)
    painter.end()
    return image


def _render_picture(picture, region: QRectF, offset: tuple[float, float]) -> QImage:
    image = QImage(
        int(region.width()) * 4, int(region.height()) * 4, QImage.Format.Format_ARGB32
    )
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.scale(4.0, 4.0)
    painter.translate(-region.x(), -region.y())
    painter.translate(*offset)
    painter.drawPicture(QPointF(0.0, 0.0), picture)
    painter.end()
    return image


def _differing_pixels(left: QImage, right: QImage) -> int:
    assert left.size() == right.size()
    count = 0
    for y in range(left.height()):
        for x in range(left.width()):
            if left.pixel(x, y) != right.pixel(x, y):
                count += 1
    return count


def _inked_pixels(image: QImage) -> int:
    white = QColor("white").rgb()
    return sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixel(x, y) != white
    )


def _live_canvas_count() -> int:
    return sum(
        1 for widget in QApplication.allWidgets() if isinstance(widget, CanvasView)
    )


class SmilesPreviewPictureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.canvas = build_canvas_view()
        self.addCleanup(self._dispose_canvas)

    def _dispose_canvas(self) -> None:
        schedule_canvas_deletion_for(self.canvas)
        self.app.sendPostedEvents(self.canvas, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_picture_matches_the_committed_rendering_pixel_for_pixel(self) -> None:
        model = _benzyl_alcohol()
        before = _atom_snapshot(model)

        picture = render_smiles_preview_picture(self.canvas, model, SMILES)

        # Rendering works on its own copy; the commit plan reads this model.
        self.assertEqual(_atom_snapshot(model), before)

        target = QPointF(40.0, 10.0)
        controller = insert_controller_for_access(self.canvas)
        with patch.object(
            self.canvas.rdkit, "smiles_to_2d", return_value=copy.deepcopy(model)
        ):
            controller.begin_smiles_insert(SMILES)
        controller.commit_smiles_insert(target)
        self.assertEqual(insert_state_for(self.canvas).smiles_preview_items, [])
        self.assertEqual(len(self.canvas.model.atoms), 8)

        center = smiles_preview_center(model)
        assert center is not None
        offset = smiles_preview_offset(center, (target.x(), target.y()))
        scene = self.canvas.scene()
        # Whole scene units keep both renders at exactly four pixels per unit.
        region = QRectF(
            scene.itemsBoundingRect().adjusted(-10.0, -10.0, 10.0, 10.0).toAlignedRect()
        )
        committed = _render_scene(scene, region)
        ghost = _render_picture(picture, region, offset)

        # The ring's inner double-bond strokes, the O label and the bond
        # trimmed in front of it must all come from the same painter commands.
        self.assertGreater(_inked_pixels(committed), 0)
        self.assertEqual(_differing_pixels(committed, ghost), 0)

    def test_inserting_again_replaces_the_ghost_with_the_new_picture(self) -> None:
        controller = insert_controller_for_access(self.canvas)
        insert_state = insert_state_for(self.canvas)
        first = MoleculeModel()
        first.add_bond(first.add_atom("C", -10.0, 0.0), first.add_atom("C", 10.0, 0.0))
        with patch.object(self.canvas.rdkit, "smiles_to_2d", return_value=first):
            controller.begin_smiles_insert("CC")
        controller.render_smiles_preview(QPointF(5.0, 5.0))
        stale_item = insert_state.smiles_preview_items[0]

        with patch.object(
            self.canvas.rdkit, "smiles_to_2d", return_value=_benzyl_alcohol()
        ):
            controller.begin_smiles_insert(SMILES)
        controller.render_smiles_preview(QPointF(5.0, 5.0))

        (item,) = insert_state.smiles_preview_items
        self.assertIsNot(item, stale_item)
        self.assertIs(item.picture(), insert_state.smiles_preview_picture)
        self.assertIsNone(stale_item.scene())
        self.assertIs(item.scene(), self.canvas.scene())

    def test_ghost_canvas_is_disposed_after_rendering(self) -> None:
        before = _live_canvas_count()

        render_smiles_preview_picture(self.canvas, _benzyl_alcohol(), SMILES)
        self.app.processEvents()

        self.assertEqual(_live_canvas_count(), before)


if __name__ == "__main__":
    unittest.main()
