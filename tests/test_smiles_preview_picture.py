import copy
import math
import os
import unittest
from dataclasses import asdict, replace
from unittest.mock import patch

from PyQt6 import sip

import chemvas.ui.smiles_preview_picture as preview_module

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication, QGraphicsScene

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
        self._assert_picture_matches_commit(_benzyl_alcohol())

    def _assert_picture_matches_commit(self, model) -> None:
        before = asdict(model)
        session = self.canvas.services.document.canvas_document_session_service
        document_before = session.snapshot_state()

        picture = render_smiles_preview_picture(self.canvas.renderer, model)

        # Rendering works on its own copy; the commit plan reads this model.
        self.assertEqual(asdict(model), before)

        center = smiles_preview_center(model)
        assert center is not None
        target = QPointF(center[0] + 40.0, center[1] + 10.0)
        controller = insert_controller_for_access(self.canvas)
        with patch.object(
            self.canvas.rdkit, "smiles_to_2d", return_value=copy.deepcopy(model)
        ):
            controller.begin_smiles_insert(SMILES)
        controller.commit_smiles_insert(target)
        self.assertEqual(insert_state_for(self.canvas).smiles_preview_items, [])
        self.assertEqual(len(self.canvas.model.atoms), len(model.atoms))

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
        document_after = session.snapshot_state()
        history = self.canvas.services.history_service
        history.undo()
        self.assertEqual(session.snapshot_state(), document_before)
        history.redo()
        self.assertEqual(session.snapshot_state(), document_after)
        history.undo()

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

    def test_preview_does_not_construct_an_editor(self) -> None:
        before = _live_canvas_count()
        scene = QGraphicsScene()
        with (
            patch.object(preview_module, "QGraphicsScene", return_value=scene),
            patch(
                "chemvas.ui.canvas_view.CanvasView",
                side_effect=AssertionError("preview must not construct an editor"),
            ),
        ):
            picture = render_smiles_preview_picture(
                self.canvas.renderer, _benzyl_alcohol()
            )
        self.assertFalse(picture.isNull())
        self.assertTrue(sip.isdeleted(scene))
        self.assertIs(QApplication.instance(), self.app)
        self.assertEqual(_live_canvas_count(), before)

    def test_charged_and_styled_previews_match_actual_insertion(self) -> None:
        for length in (20.0, 33.0):
            self.canvas.renderer.style = replace(
                self.canvas.renderer.style,
                bond_length_px=length,
                atom_color="#672234",
                bond_color="#244862",
            )
            for style, order in (
                ("single", 1),
                ("double", 2),
                ("double_outer", 2),
                ("triple", 3),
                ("wedge", 1),
                ("hash", 1),
                ("dotted", 1),
                ("bold_center", 1),
                ("double_either", 2),
            ):
                with self.subTest(length=length, style=style):
                    model = MoleculeModel()
                    a = model.add_atom("NH2", -30.0, 10.0)
                    b = model.add_atom("C", 15.0, 28.0)
                    c = model.add_atom("O", 36.0, -8.0)
                    model.atoms[b].explicit_label = True
                    bond = model.add_bond(a, b, order)
                    model.bonds[bond].style = style
                    model.bonds[bond].color = "#1248AB"
                    model.add_bond(b, c)
                    model.bonds.append(None)
                    model.atom_annotations = {
                        a: {"formal_charge": 1, "radical_electrons": 1},
                        c: {"formal_charge": -1},
                        99: {"formal_charge": 1},
                    }
                    self._assert_picture_matches_commit(model)

    def test_preview_failure_cleans_graphics_and_leaves_live_state_untouched(
        self,
    ) -> None:
        model = _benzyl_alcohol()
        model.atoms[0].element = " N "
        model.atom_annotations = {0: {"formal_charge": 1}}
        before_model = asdict(model)
        session = self.canvas.services.document.canvas_document_session_service
        history = self.canvas.services.history_service
        # Keep a genuine redo branch to detect accidental history publication.
        decoration = self.canvas.services.scene_decoration.scene_decoration_service
        decoration.add_shape(QRectF(10, 20, 60, 40))
        history.undo()
        before_document = session.snapshot_state()
        before_stacks = (tuple(history.state.history), tuple(history.state.redo_stack))
        before_style = self.canvas.renderer.style
        for phase in ("molecule", "mark", "record"):
            with self.subTest(phase=phase):
                scene = QGraphicsScene()
                held_items = []

                def fail_after_drawing(
                    context,
                    *,
                    draw=preview_module.render_molecule,
                    items=held_items,
                    scene=scene,
                ):
                    draw(context)
                    items.extend(scene.items())
                    raise RuntimeError("drawing failed")

                def fail_later(*args, items=held_items, scene=scene, **kwargs):
                    items.extend(scene.items())
                    raise RuntimeError("drawing failed")

                if phase == "molecule":
                    failing = patch.object(
                        preview_module,
                        "render_molecule",
                        side_effect=fail_after_drawing,
                    )
                elif phase == "mark":
                    failing = patch(
                        "chemvas.ui.annotations.graphics.AnnotationGraphics.build_mark_item",
                        side_effect=fail_later,
                    )
                else:
                    failing = patch.object(scene, "render", side_effect=fail_later)
                with (
                    patch.object(preview_module, "QGraphicsScene", return_value=scene),
                    failing,
                ):
                    with self.assertRaisesRegex(RuntimeError, "drawing failed"):
                        render_smiles_preview_picture(self.canvas.renderer, model)
                self.assertTrue(held_items)
                self.assertTrue(sip.isdeleted(scene))
                self.assertIs(QApplication.instance(), self.app)
                self.assertTrue(all(sip.isdeleted(item) for item in held_items))
                self.assertEqual(asdict(model), before_model)
                self.assertEqual(session.snapshot_state(), before_document)
                self.assertEqual(
                    (tuple(history.state.history), tuple(history.state.redo_stack)),
                    before_stacks,
                )
                self.assertEqual(self.canvas.renderer.style, before_style)


if __name__ == "__main__":
    unittest.main()
