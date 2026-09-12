import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.runtime_state import canvas_runtime_state

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageChops, ImageFilter
from PyQt6.QtCore import QByteArray, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QLabel,
    QPlainTextEdit,
    QPushButton,
)

from chemvas.bootstrap.main_window import build_main_window
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    MAX_ARROW_LABEL_CHARS,
    build_document_payload,
    extract_document_state,
    serialize_settings,
)
from chemvas.features.annotations import (
    LabelRun,
    arrow_label_html,
    parse_arrow_label,
)
from chemvas.features.document_composition import compose_document_state
from chemvas.features.export import (
    collect_export_items,
    content_bounds,
    export_scene,
    render_scene_to_svg_bytes,
)
from chemvas.ui.arrow_label_dialog import prompt_arrow_labels
from chemvas.ui.canvas_arrow_build_service import (
    ARROW_LABEL_ROLE,
    CanvasArrowBuildService,
)
from chemvas.ui.canvas_scene_items_state import arrow_items_for
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.canvas_text_style_state import CanvasTextStyleState
from chemvas.ui.canvas_tool_settings_state import CanvasToolSettingsState
from chemvas.ui.canvas_window_access import (
    restore_canvas_state_for,
    snapshot_canvas_state_for,
)
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    services_for_window,
)
from chemvas.ui.move_access import move_item_for
from chemvas.ui.scene_item_restore import create_arrow_item_from_state
from chemvas.ui.scene_item_state import apply_scene_item_state
from chemvas.ui.scene_item_state_serialization import arrow_state_dict
from chemvas.ui.selection_collection_access import selection_items_for_copy_for


class ArrowLabelSyntaxTest(unittest.TestCase):
    def test_chemical_formula_requires_braces_to_limit_each_subscript(self) -> None:
        self.assertEqual(
            parse_arrow_label("K_2CO_3"),
            (LabelRun("K", "normal"), LabelRun("2CO3", "sub")),
        )
        self.assertEqual(
            parse_arrow_label("K_{2}CO_{3}"),
            (
                LabelRun("K", "normal"),
                LabelRun("2", "sub"),
                LabelRun("CO", "normal"),
                LabelRun("3", "sub"),
            ),
        )

    def test_marker_applies_to_the_following_token(self) -> None:
        self.assertEqual(
            parse_arrow_label("k_1"), (LabelRun("k", "normal"), LabelRun("1", "sub"))
        )
        self.assertEqual(
            parse_arrow_label("k_-1 (fast)"),
            (
                LabelRun("k", "normal"),
                LabelRun("-1", "sub"),
                LabelRun(" (fast)", "normal"),
            ),
        )

    def test_braces_group_and_markers_chain(self) -> None:
        self.assertEqual(
            parse_arrow_label("K_{eq}^‡"),
            (LabelRun("K", "normal"), LabelRun("eq", "sub"), LabelRun("‡", "super")),
        )

    def test_dangling_marker_and_unclosed_brace_stay_readable(self) -> None:
        self.assertEqual(parse_arrow_label("k_"), (LabelRun("k_", "normal"),))
        self.assertEqual(
            parse_arrow_label("k_{obs"),
            (LabelRun("k", "normal"), LabelRun("obs", "sub")),
        )
        self.assertEqual(parse_arrow_label(""), ())

    def test_html_escapes_text_and_wraps_runs(self) -> None:
        self.assertEqual(arrow_label_html("k_-1"), "k<sub>-1</sub>")
        self.assertEqual(arrow_label_html("a<b^2"), "a&lt;b<sup>2</sup>")
        self.assertEqual(
            arrow_label_html("A & B \"C\" 'D'"), "A &amp; B &quot;C&quot; &#x27;D&#x27;"
        )


def _document_state(arrows: list[dict]) -> dict:
    return {
        "model": {"atoms": {}, "bonds": [], "next_atom_id": 0},
        "ring_fills": [],
        "notes": [],
        "marks": [],
        "arrows": arrows,
        "ts_brackets": [],
        "shapes": [],
        "orbitals": [],
        "settings": serialize_settings(
            bond_length_px=20.0,
            arrow_line_width=1.0,
            arrow_head_scale=0.3,
            orbital_phase_enabled=False,
            text_font_size=12,
            text_font_weight=50,
            text_italic=False,
            sheet_size="A4",
            sheet_orientation="portrait",
        ),
        "last_smiles_input": None,
    }


def _arrow(kind: str = "arrow", **extra) -> dict:
    return {"kind": kind, "start": [0.0, 0.0], "end": [40.0, 0.0], **extra}


class ArrowLabelComposeTest(unittest.TestCase):
    def _composition(self, arrow: dict) -> dict:
        return {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [{"id": 0, "element": "C", "x": 0.0, "y": 0.0}],
            "bonds": [],
            "arrows": [arrow],
        }

    def test_compose_passes_labels_through_to_the_document(self) -> None:
        state = compose_document_state(
            self._composition(
                {
                    "kind": "equilibrium_forward",
                    "start": [0.0, 0.0],
                    "end": [40.0, 0.0],
                    "labels": {"above": "k_1"},
                }
            )
        )
        self.assertEqual(state["arrows"][0]["labels"], {"above": "k_1"})
        self.assertEqual(state["arrows"][0]["kind"], "equilibrium_forward")

    def test_compose_rejects_bad_labels(self) -> None:
        with self.assertRaises(ValueError):
            compose_document_state(
                self._composition(
                    {
                        "kind": "arrow",
                        "start": [0.0, 0.0],
                        "end": [40.0, 0.0],
                        "labels": {"left": "k"},
                    }
                )
            )


class ArrowLabelDocumentContractTest(unittest.TestCase):
    def test_labels_and_favored_equilibrium_round_trip(self) -> None:
        state = _document_state(
            [
                _arrow(labels={"above": "k_1", "below": "k_-1"}),
                _arrow("equilibrium_forward", labels={"above": "K_{eq}"}),
                _arrow("equilibrium_reverse"),
            ]
        )

        restored = extract_document_state(
            build_document_payload(state, CANVAS_FILE_VERSION)
        )

        self.assertEqual(
            restored["arrows"][0]["labels"], {"above": "k_1", "below": "k_-1"}
        )
        self.assertEqual(restored["arrows"][1]["labels"], {"above": "K_{eq}"})
        self.assertNotIn("labels", restored["arrows"][2])

    def test_invalid_labels_are_rejected(self) -> None:
        for labels in (
            {},
            {"left": "k"},
            {"above": ""},
            {"above": "   "},
            {"above": 1},
            {"above": "k" * (MAX_ARROW_LABEL_CHARS + 1)},
            "k_1",
        ):
            with self.subTest(labels=labels), self.assertRaises(ValueError):
                build_document_payload(
                    _document_state([_arrow(labels=labels)]), CANVAS_FILE_VERSION
                )


class _FakeScene:
    def __init__(self) -> None:
        self.removed = []

    def removeItem(self, item) -> None:
        self.removed.append(item)


def _build_service(metric_scale: float = 1.0):
    style = SimpleNamespace(bond_length_px=20.0 * metric_scale, bond_spacing_px=4.4)
    renderer = SimpleNamespace(
        style=style,
        bond_pen=lambda: QPen(QColor("#222222")),
        bond_spacing=lambda: 4.4 * metric_scale,
    )
    canvas = SimpleNamespace(
        renderer=renderer,
        runtime_state=canvas_runtime_state(
            tool_settings_state=CanvasToolSettingsState(
                arrow_line_width=1.5, arrow_head_scale=0.3
            ),
            text_style_state=CanvasTextStyleState(),
        ),
    )
    return CanvasArrowBuildService(canvas)


def _label_children(item):
    return [child for child in item.childItems() if child.data(0) == ARROW_LABEL_ROLE]


class ArrowLabelBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_labels_become_children_above_and_below_the_arrow(self) -> None:
        service = _build_service()
        item = service.build_arrow_item(
            QPointF(0.0, 50.0), QPointF(60.0, 50.0), "arrow"
        )

        service.apply_arrow_labels(item, {"above": "k_1", "below": "k_-1"})

        children = _label_children(item)
        self.assertEqual(len(children), 2)
        above, below = children
        self.assertLess(above.sceneBoundingRect().bottom(), 50.0)
        self.assertGreater(below.sceneBoundingRect().top(), 50.0)
        for child in children:
            self.assertFalse(
                child.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            )
            self.assertAlmostEqual(
                child.sceneBoundingRect().center().x(), 30.0, delta=0.5
            )
        self.assertIn("vertical-align:sub", above.toHtml())

    def test_svg_preserves_shaped_arrow_labels_without_font_dependent_text(self):
        for text, bold, italic, angle in (
            ("MnO_2", False, False, 0),
            ("_{22}", False, False, 0),
            ("^{22}", False, False, 0),
            ("K_{eq}^‡", True, True, 0),
            ("ΔG^‡ < 0 & k_-1", False, True, 37),
            ("K_{2}CO_{3}\nDMSO, rt", False, False, 0),
            ("ΔG^{‡}\r\n\r\n68%, 96% ee", True, True, 37),
            ("k_{a\rb} < 2", False, True, 0),
        ):
            with self.subTest(text=text, angle=angle):
                service = _build_service()
                scene = QGraphicsScene()
                item = service.build_arrow_item(
                    QPointF(0, 50), QPointF(180, 50), "arrow"
                )
                item.setData(0, "arrow")
                scene.addItem(item)
                service.apply_arrow_labels(item, {"above": text, "below": "oxidation"})
                label_color = QColor("#195b90")
                for child in _label_children(item):
                    font = QFont("DejaVu Sans", 12)
                    # Compare glyph geometry without platform-specific text
                    # smoothing; the SVG paths still use painter antialiasing.
                    font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
                    font.setBold(bold)
                    font.setItalic(italic)
                    child.setFont(font)
                    child.setDefaultTextColor(label_color)
                item.setRotation(angle)
                items = collect_export_items(scene)
                source = content_bounds(items).adjusted(-4, -4, 4, 4)
                before = self._render_labels(scene, source)
                state = arrow_state_dict(item)
                # Passing only the parent exercises selected-arrow clipboard
                # export: its label descendants must enter outline mode too.
                svg = render_scene_to_svg_bytes(scene, source=source, items=[item])
                self.assertNotIn(b"<text", svg)
                self.assertNotIn(b"<image", svg)
                renderer = QSvgRenderer(QByteArray(svg))
                self.assertTrue(renderer.isValid())
                rendered = self._render_labels(scene, source, renderer=renderer)
                # Allow one pixel of edge/hinting variation at 4x magnification,
                # while measuring missing ink rather than the white background.
                for child in _label_children(item):
                    rect = child.sceneBoundingRect()
                    crop = (
                        round((rect.left() - source.left()) * 4),
                        round((rect.top() - source.top()) * 4),
                        round((rect.right() - source.left()) * 4),
                        round((rect.bottom() - source.top()) * 4),
                    )
                    pixels = [
                        self._pixels(image).crop(crop) for image in (before, rendered)
                    ]
                    for sample in pixels:
                        colors = sample.getcolors(sample.width * sample.height)
                        self.assertIn(
                            label_color.getRgb(), {color for _, color in colors}
                        )
                    masks = [
                        sample.convert("L").point(
                            lambda value: 255 if value < 160 else 0
                        )
                        for sample in pixels
                    ]
                    for actual, expected in (masks, masks[::-1]):
                        missing = ImageChops.subtract(
                            actual, expected.filter(ImageFilter.MaxFilter(3))
                        )
                        ink = actual.histogram()[255]
                        self.assertGreater(ink, 0)
                        self.assertLess(missing.histogram()[255] / ink, 0.05)
                self.assertEqual(self._render_labels(scene, source), before)
                self.assertEqual(arrow_state_dict(item), state)

    @staticmethod
    def _render_labels(scene, source, *, renderer=None):
        image = QImage(
            round(source.width() * 4),
            round(source.height() * 4),
            QImage.Format.Format_RGBA8888,
        )
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if renderer is None:
            scene.render(painter, QRectF(image.rect()), source)
        else:
            renderer.render(painter, QRectF(image.rect()))
        painter.end()
        return image

    @staticmethod
    def _pixels(image):
        pixels = image.constBits().asstring(image.sizeInBytes())
        return Image.frombytes("RGBA", (image.width(), image.height()), pixels)

    def test_file_export_outlines_labels_and_failure_restores_screen_state(self):
        service = _build_service()
        scene = QGraphicsScene()
        item = service.build_arrow_item(QPointF(0, 50), QPointF(120, 50), "arrow")
        item.setData(0, "arrow")
        scene.addItem(item)
        service.apply_arrow_labels(item, {"above": "MnO_2"})
        (child,) = _label_children(item)
        source = content_bounds(collect_export_items(scene))
        before = self._render_labels(scene, source)
        html = child.toHtml()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scheme.svg"
            export_scene(scene, str(path), fmt="svg", margin=4)
            self.assertNotIn("<text", path.read_text())
            with (
                mock.patch(
                    "chemvas.features.export.vector.paint_scene_region",
                    side_effect=RuntimeError("paint failed"),
                ),
                self.assertRaisesRegex(RuntimeError, "paint failed"),
            ):
                export_scene(scene, str(path), fmt="svg", margin=4)
        self.assertEqual(child.toHtml(), html)
        self.assertEqual(self._render_labels(scene, source), before)

    def test_above_stays_toward_smaller_y_when_drawn_right_to_left(self) -> None:
        service = _build_service()
        item = service.build_arrow_item(
            QPointF(60.0, 50.0), QPointF(0.0, 50.0), "arrow"
        )

        service.apply_arrow_labels(item, {"above": "up"})

        (above,) = _label_children(item)
        self.assertLess(above.sceneBoundingRect().bottom(), 50.0)

    def test_vertical_arrow_labels_clear_the_shaft_by_their_width(self) -> None:
        service = _build_service()
        item = service.build_arrow_item(
            QPointF(50.0, 80.0), QPointF(50.0, 0.0), "arrow"
        )

        service.apply_arrow_labels(item, {"above": "left label", "below": "right"})

        above, below = _label_children(item)
        # "Above" is the left side of an upward arrow; neither box crosses x=50.
        self.assertLess(above.sceneBoundingRect().right(), 50.0)
        self.assertGreater(below.sceneBoundingRect().left(), 50.0)
        self.assertAlmostEqual(above.sceneBoundingRect().center().y(), 40.0, delta=0.5)

    def test_equilibrium_labels_sit_outside_the_harpoons_at_any_bond_length(
        self,
    ) -> None:
        for metric_scale in (0.5, 1.0, 2.0):
            service = _build_service(metric_scale)
            item = service.build_arrow_item(
                QPointF(0.0, 0.0), QPointF(60.0, 0.0), "equilibrium"
            )
            item.setData(0, "equilibrium")

            service.apply_arrow_labels(item, {"above": "K", "below": "K"})

            # The harpoons are the outermost path elements; read them back.
            path = item.path()
            harpoon_top = min(path.elementAt(i).y for i in range(path.elementCount()))
            harpoon_bottom = max(
                path.elementAt(i).y for i in range(path.elementCount())
            )
            above, below = _label_children(item)
            self.assertLess(
                above.sceneBoundingRect().bottom(), harpoon_top, metric_scale
            )
            self.assertGreater(
                below.sceneBoundingRect().top(), harpoon_bottom, metric_scale
            )

    def test_curved_arrow_labels_follow_the_curve_midpoint(self) -> None:
        service = _build_service()
        item = service.build_arrow_item(
            QPointF(0.0, 0.0), QPointF(60.0, 0.0), "curved_single"
        )
        control = item.data(2)["control"]
        self.assertIsInstance(control, QPointF)

        service.apply_arrow_labels(item, {"above": "a", "below": "b"})

        curve_mid_y = 0.5 * control.y()
        above, below = _label_children(item)
        self.assertLess(above.sceneBoundingRect().bottom(), curve_mid_y)
        self.assertGreater(below.sceneBoundingRect().top(), curve_mid_y)

    def test_reapplying_replaces_children_and_none_clears_them(self) -> None:
        service = _build_service()
        item = service.build_arrow_item(QPointF(0.0, 0.0), QPointF(60.0, 0.0), "arrow")
        service.apply_arrow_labels(item, {"above": "a", "below": "b"})
        first = _label_children(item)

        service.apply_arrow_labels(item, {"below": "c"})
        second = _label_children(item)
        self.assertEqual(len(second), 1)
        self.assertNotIn(second[0], first)

        service.apply_arrow_labels(item, None)
        self.assertEqual(_label_children(item), [])

    def test_apply_removes_stale_children_from_their_scene(self) -> None:
        service = _build_service()
        scene = QGraphicsScene()
        item = service.build_arrow_item(QPointF(0.0, 0.0), QPointF(60.0, 0.0), "arrow")
        scene.addItem(item)
        service.apply_arrow_labels(item, {"above": "a"})
        self.assertEqual(len(scene.items()), 2)

        service.apply_arrow_labels(item, None)

        self.assertEqual(len(scene.items()), 1)

    def test_favored_equilibrium_shortens_the_disfavored_harpoon(self) -> None:
        service = _build_service()
        start, end = QPointF(0.0, 0.0), QPointF(40.0, 0.0)

        balanced = service.build_arrow_item(start, end, "equilibrium").path()
        forward = service.build_arrow_item(start, end, "equilibrium_forward").path()
        reverse = service.build_arrow_item(start, end, "equilibrium_reverse").path()

        def shaft_length(path: QPainterPath, first: int) -> float:
            return abs(path.elementAt(first + 1).x - path.elementAt(first).x)

        for path in (balanced, forward, reverse):
            self.assertEqual(path.elementCount(), 8)
        self.assertAlmostEqual(shaft_length(balanced, 0), 40.0)
        self.assertAlmostEqual(shaft_length(balanced, 4), 40.0)
        # Forward favored: the forward (upper) harpoon keeps its length and
        # the reverse one is halved and centered.
        self.assertAlmostEqual(shaft_length(forward, 0), 40.0)
        self.assertAlmostEqual(shaft_length(forward, 4), 20.0)
        self.assertAlmostEqual(forward.elementAt(4).x, 30.0)
        self.assertAlmostEqual(forward.elementAt(5).x, 10.0)
        self.assertAlmostEqual(shaft_length(reverse, 0), 20.0)
        self.assertAlmostEqual(shaft_length(reverse, 4), 40.0)


class ArrowLabelCodecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _plain_item(self) -> QGraphicsPathItem:
        item = QGraphicsPathItem()
        item.setData(0, "arrow")
        item.setData(
            2,
            {
                "start": QPointF(0.0, 0.0),
                "end": QPointF(10.0, 0.0),
                "control": None,
                "double": False,
                "labels": {"above": "k_1"},
            },
        )
        return item

    def test_state_dict_carries_labels_only_when_present(self) -> None:
        with_labels = arrow_state_dict(self._plain_item())
        self.assertEqual(with_labels["labels"], {"above": "k_1"})

        item = self._plain_item()
        data = item.data(2)
        del data["labels"]
        item.setData(2, data)
        self.assertNotIn("labels", arrow_state_dict(item))

    def test_restore_and_apply_hand_labels_to_the_port(self) -> None:
        setter = mock.Mock()
        builder = mock.Mock(return_value=QGraphicsPathItem())
        state = {
            "kind": "arrow",
            "start": (0.0, 0.0),
            "end": (9.0, 0.0),
            "labels": {"below": "k_-1"},
        }

        restored = create_arrow_item_from_state(
            state,
            build_arrow_item=builder,
            set_curved_arrow_path=lambda *_args: None,
            set_arrow_labels=setter,
        )
        assert restored is not None
        self.assertEqual(restored.data(2)["labels"], {"below": "k_-1"})
        setter.assert_called_once_with(restored, {"below": "k_-1"})

        setter.reset_mock()
        apply_scene_item_state(
            restored,
            {"kind": "arrow", "start": (0.0, 0.0), "end": (9.0, 0.0), "double": False},
            model_atoms={},
            note_style_applier=lambda item: None,
            mark_center_setter=lambda item, center: None,
            ring_fill_brush_getter=lambda: QBrush(QColor("#000000")),
            ts_bracket_path_builder=lambda rect: QPainterPath(),
            bond_color="#000000",
            build_arrow_item=builder,
            set_curved_arrow_path=lambda *args: None,
            orbital_base_handle_dist=18.0,
            set_arrow_labels=setter,
        )
        self.assertNotIn("labels", restored.data(2))
        setter.assert_called_once_with(restored, None)

    def test_labels_without_a_port_fail_closed(self) -> None:
        state = {
            "kind": "arrow",
            "start": (0.0, 0.0),
            "end": (9.0, 0.0),
            "labels": {"above": "k"},
        }
        with self.assertRaises(ValueError):
            create_arrow_item_from_state(
                state,
                build_arrow_item=lambda *_args: QGraphicsPathItem(),
                set_curved_arrow_path=lambda *_args: None,
            )


class ArrowLabelDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = build_main_window()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_dialog_prefills_and_returns_edited_text(self) -> None:
        def drive_dialog(dialog: QDialog):
            above = dialog.findChild(QPlainTextEdit, "arrowLabelAboveInput")
            below = dialog.findChild(QPlainTextEdit, "arrowLabelBelowInput")
            self.assertEqual(above.toPlainText(), "k_1")
            self.assertEqual(below.toPlainText(), "")
            counter = dialog.findChild(QLabel, "arrowLabelAboveInputLimit")
            self.assertIsNotNone(counter)
            self.assertIn("3/200", counter.text())
            above.insertPlainText("x" * 250)
            self.assertIn("253/200", counter.text())
            self.assertEqual(len(above.toPlainText()), 253)
            self.assertFalse(
                next(
                    b for b in dialog.findChildren(QPushButton) if b.text() == "OK"
                ).isEnabled()
            )
            above.setPlainText("k_1")
            below.setPlainText("k_-1")
            next(
                b for b in dialog.findChildren(QPushButton) if b.text() == "OK"
            ).click()
            return QDialog.DialogCode.Accepted

        with mock.patch("chemvas.ui.arrow_label_dialog.QDialog.exec", new=drive_dialog):
            result = prompt_arrow_labels(
                active_canvas_for_window(self.window), above="k_1", below=""
            )
        self.assertEqual(result, {"above": "k_1", "below": "k_-1"})

    def test_cancel_returns_none(self) -> None:
        with mock.patch(
            "chemvas.ui.arrow_label_dialog.QDialog.exec",
            new=lambda dialog: QDialog.DialogCode.Rejected,
        ):
            self.assertIsNone(
                prompt_arrow_labels(
                    active_canvas_for_window(self.window), above="", below=""
                )
            )

    def test_live_previews_show_initial_scope_and_follow_each_input(self) -> None:
        def drive_dialog(dialog: QDialog):
            above = dialog.findChild(QPlainTextEdit, "arrowLabelAboveInput")
            below = dialog.findChild(QPlainTextEdit, "arrowLabelBelowInput")
            above_preview = dialog.findChild(QLabel, "arrowLabelAbovePreview")
            below_preview = dialog.findChild(QLabel, "arrowLabelBelowPreview")
            self.assertIsNotNone(above_preview)
            self.assertIsNotNone(below_preview)
            self.assertEqual(above_preview.textFormat(), Qt.TextFormat.RichText)
            self.assertEqual(above_preview.text(), "MeI, K<sub>2CO3</sub>")
            self.assertEqual(below_preview.text(), "k<sub>-1</sub>")

            above.selectAll()
            QTest.keyClicks(above, "MeI, K_{2}CO_{3}")
            self.assertEqual(above_preview.text(), "MeI, K<sub>2</sub>CO<sub>3</sub>")
            self.assertEqual(below_preview.text(), "k<sub>-1</sub>")
            below.clear()
            self.assertEqual(below_preview.text(), "No label")
            self.assertEqual(above.toPlainText(), "MeI, K_{2}CO_{3}")
            self.assertEqual(below.toPlainText(), "")
            return QDialog.DialogCode.Accepted

        with mock.patch("chemvas.ui.arrow_label_dialog.QDialog.exec", new=drive_dialog):
            result = prompt_arrow_labels(
                active_canvas_for_window(self.window),
                above="MeI, K_2CO_3",
                below="k_-1",
            )
        self.assertEqual(result, {"above": "MeI, K_{2}CO_{3}", "below": ""})

    def test_preview_escapes_markup_and_cancel_keeps_the_document_unchanged(self):
        canvas = active_canvas_for_window(self.window)
        before = snapshot_canvas_state_for(canvas)

        def drive_dialog(dialog: QDialog):
            above = dialog.findChild(QPlainTextEdit, "arrowLabelAboveInput")
            below = dialog.findChild(QPlainTextEdit, "arrowLabelBelowInput")
            preview = dialog.findChild(QLabel, "arrowLabelAbovePreview")
            self.assertIsNotNone(preview)
            above.setPlainText("<b>실온 & 산화</b>^‡")
            self.assertEqual(
                preview.text(), "&lt;b&gt;실온 &amp; 산화&lt;/b&gt;<sup>‡</sup>"
            )
            self.assertEqual(above.toPlainText(), "<b>실온 & 산화</b>^‡")
            below.setPlainText("x" * (MAX_ARROW_LABEL_CHARS + 1))
            self.assertEqual(len(below.toPlainText()), MAX_ARROW_LABEL_CHARS + 1)
            self.assertEqual(
                dialog.findChild(QLabel, "arrowLabelBelowPreview").text(),
                "x" * (MAX_ARROW_LABEL_CHARS + 1),
            )
            above.setPlainText("&" * MAX_ARROW_LABEL_CHARS)
            self.assertEqual(preview.text(), "&amp;" * MAX_ARROW_LABEL_CHARS)
            dialog.adjustSize()
            available = dialog.screen().availableGeometry()
            self.assertLessEqual(dialog.width(), min(640, available.width()))
            self.assertLessEqual(dialog.height(), available.height())
            return QDialog.DialogCode.Rejected

        with mock.patch("chemvas.ui.arrow_label_dialog.QDialog.exec", new=drive_dialog):
            self.assertIsNone(prompt_arrow_labels(canvas, above="", below=""))
        self.assertEqual(snapshot_canvas_state_for(canvas), before)


class ArrowLabelGuiTest(unittest.TestCase):
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
        document_service = services_for_window(self.window).canvas_document_service
        for canvas in self.window.tab_references.all_canvases():
            document_service.mark_clean(canvas)
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def _draw_arrow(self, canvas, start: QPointF, end: QPointF) -> None:
        canvas_services_for(canvas).input.tool_mode_controller.set_tool("arrow")
        start_pos = canvas.mapFromScene(start)
        end_pos = canvas.mapFromScene(end)
        QTest.mousePress(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            start_pos,
        )
        self.app.processEvents()
        QTest.mouseMove(canvas.viewport(), end_pos)
        self.app.processEvents()
        QTest.mouseRelease(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            end_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

    def _double_click(self, canvas, scene_pos: QPointF) -> None:
        pos = canvas.mapFromScene(scene_pos)
        QTest.mousePress(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            pos,
        )
        QTest.mouseRelease(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            pos,
        )
        QTest.mouseDClick(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            pos,
        )
        QTest.mouseRelease(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

    def test_double_click_labels_arrow_with_undo_move_flip_and_round_trip(self) -> None:
        # Nonblank labels preserve the typed text, including edge whitespace.
        expected_labels = {"above": " k_1 ", "below": "k_-1"}
        canvas = active_canvas_for_window(self.window)
        self._draw_arrow(canvas, QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        (arrow,) = arrow_items_for(canvas)
        canvas_services_for(canvas).input.tool_mode_controller.set_tool("select")

        with mock.patch(
            "chemvas.ui.scene_decoration_service.prompt_arrow_labels",
            return_value=expected_labels,
        ) as prompt:
            self._double_click(canvas, QPointF(0.0, 0.0))
        prompt.assert_called_once()
        self.assertEqual(prompt.call_args.kwargs, {"above": "", "below": ""})

        state = arrow_state_dict(arrow)
        self.assertEqual(state["labels"], expected_labels)
        children = _label_children(arrow)
        self.assertEqual(len(children), 2)
        self.assertIs(children[0].scene(), canvas.scene())

        # The labels widen the export bounds beyond the arrow's own rect.
        export_items = collect_export_items(canvas.scene())
        self.assertGreater(
            content_bounds(export_items).height(), arrow.sceneBoundingRect().height()
        )

        history = canvas.runtime_state.history_service
        history.undo()
        self.assertNotIn("labels", arrow_state_dict(arrow))
        self.assertEqual(_label_children(arrow), [])
        history.redo()
        self.assertEqual(len(_label_children(arrow)), 2)

        above_before = _label_children(arrow)[0].scenePos()
        move_item_for(canvas, arrow, 15.0, 5.0)
        above_after = _label_children(arrow)[0].scenePos()
        self.assertAlmostEqual(above_after.x() - above_before.x(), 15.0)
        self.assertAlmostEqual(above_after.y() - above_before.y(), 5.0)

        arrow.setSelected(True)
        QTest.keyClick(
            canvas,
            Qt.Key.Key_H,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
        self.app.processEvents()
        flipped = arrow_state_dict(arrow)
        self.assertGreater(flipped["start"][0], flipped["end"][0])
        self.assertEqual(flipped["labels"], expected_labels)
        self.assertEqual(len(_label_children(arrow)), 2)

        snapshot = snapshot_canvas_state_for(canvas)
        self.assertEqual(snapshot["arrows"][0]["labels"], expected_labels)
        payload = build_document_payload(snapshot, CANVAS_FILE_VERSION)
        restore_canvas_state_for(canvas, extract_document_state(payload))
        (restored,) = arrow_items_for(canvas)
        self.assertEqual(arrow_state_dict(restored)["labels"], expected_labels)
        self.assertEqual(len(_label_children(restored)), 2)

    def test_arrow_tool_double_click_edits_the_arrow_without_adding_a_stub(
        self,
    ) -> None:
        canvas = active_canvas_for_window(self.window)
        self._draw_arrow(canvas, QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        (arrow,) = arrow_items_for(canvas)
        self.assertEqual(canvas.services.tool_controller.active.name, "arrow")

        with mock.patch(
            "chemvas.ui.scene_decoration_service.prompt_arrow_labels",
            return_value={"above": "k_1", "below": ""},
        ) as prompt:
            self._double_click(canvas, QPointF(0.0, 0.0))

        prompt.assert_called_once()
        self.assertEqual([item for item in arrow_items_for(canvas)], [arrow])
        self.assertEqual(arrow_state_dict(arrow)["labels"], {"above": "k_1"})

    def test_labels_survive_rotation_and_copy_items_include_them(self) -> None:
        canvas = active_canvas_for_window(self.window)
        self._draw_arrow(canvas, QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        (arrow,) = arrow_items_for(canvas)
        service = canvas_services_for(canvas).scene_decoration.scene_decoration_service
        service.set_arrow_labels(arrow, {"above": "k_1", "below": "k_-1"})
        canvas_services_for(canvas).input.tool_mode_controller.set_tool("select")
        arrow.setSelected(True)

        copy_items = selection_items_for_copy_for(canvas)
        for child in _label_children(arrow):
            self.assertIn(child, copy_items)

        QTest.keyClick(canvas, Qt.Key.Key_Up, Qt.KeyboardModifier.AltModifier)
        self.app.processEvents()
        rotated = arrow_state_dict(arrow)
        self.assertNotAlmostEqual(rotated["end"][1], rotated["start"][1])
        self.assertEqual(rotated["labels"], {"above": "k_1", "below": "k_-1"})
        self.assertEqual(len(_label_children(arrow)), 2)

    def test_curved_handle_drag_moves_the_labels_with_the_curve(self) -> None:
        canvas = active_canvas_for_window(self.window)
        canvas_services_for(canvas).input.tool_mode_controller.set_arrow_type(
            "curved_single"
        )
        self._draw_arrow(canvas, QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        (arrow,) = arrow_items_for(canvas)
        service = canvas_services_for(canvas).scene_decoration.scene_decoration_service
        service.set_arrow_labels(arrow, {"above": "k_1"})
        (above,) = _label_children(arrow)
        before = above.scenePos()

        canvas_services_for(
            canvas
        ).handles.handle_mutation_service.update_curved_control(
            arrow, QPointF(0.0, -60.0)
        )

        (above_after,) = _label_children(arrow)
        self.assertNotAlmostEqual(above_after.scenePos().y(), before.y(), places=1)
        self.assertEqual(arrow_state_dict(arrow)["labels"], {"above": "k_1"})

    def test_double_click_on_a_label_child_reaches_its_arrow(self) -> None:
        canvas = active_canvas_for_window(self.window)
        self._draw_arrow(canvas, QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        (arrow,) = arrow_items_for(canvas)
        canvas_services_for(canvas).input.tool_mode_controller.set_tool("select")
        canvas_services_for(
            canvas
        ).scene_decoration.scene_decoration_service.set_arrow_labels(
            arrow, {"above": "k_1"}
        )
        (above,) = _label_children(arrow)
        hit = canvas_services_for(
            canvas
        ).selection.hit_testing_service.item_at_scene_pos(
            above.sceneBoundingRect().center()
        )
        self.assertIs(hit, arrow)

        with mock.patch(
            "chemvas.ui.scene_decoration_service.prompt_arrow_labels", return_value=None
        ) as prompt:
            self._double_click(canvas, above.sceneBoundingRect().center())
        self.assertEqual(prompt.call_args.kwargs, {"above": "k_1", "below": ""})
        self.assertEqual(arrow_state_dict(arrow)["labels"], {"above": "k_1"})

    def test_empty_labels_remove_the_key_and_unchanged_edit_pushes_nothing(
        self,
    ) -> None:
        canvas = active_canvas_for_window(self.window)
        self._draw_arrow(canvas, QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        (arrow,) = arrow_items_for(canvas)
        service = canvas_services_for(canvas).scene_decoration.scene_decoration_service
        history = canvas.runtime_state.history_service

        self.assertFalse(service.set_arrow_labels(arrow, {"above": "", "below": "  "}))
        self.assertNotIn("labels", arrow_state_dict(arrow))
        self.assertTrue(service.set_arrow_labels(arrow, {"above": "k_1"}))
        self.assertTrue(service.set_arrow_labels(arrow, {"above": "", "below": ""}))
        self.assertNotIn("labels", arrow_state_dict(arrow))
        self.assertEqual(_label_children(arrow), [])
        history.undo()
        self.assertEqual(arrow_state_dict(arrow)["labels"], {"above": "k_1"})
