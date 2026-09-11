import math
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QPen, QTransform
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.main_window import build_main_window
from chemvas.domain.document import (
    ARC_KIND_SWEEPS,
    CANVAS_FILE_VERSION,
    VALID_ARC_KINDS,
    VALID_ARROW_KINDS,
    build_document_payload,
    extract_document_state,
    mirrored_arc_kind,
    serialize_settings,
)
from chemvas.features.rendering import arc_midpoint, arc_points, snapped_endpoint
from chemvas.ui.canvas_arrow_build_service import (
    ARROW_LABEL_ROLE,
    CanvasArrowBuildService,
)
from chemvas.ui.canvas_scene_items_state import CanvasSceneItemsState, arrow_items_for
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.canvas_text_style_state import CanvasTextStyleState
from chemvas.ui.canvas_tool_settings_state import CanvasToolSettingsState
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.endpoint_snap_access import (
    ENDPOINT_SNAP_SCREEN_PX,
    snap_to_endpoint_for,
)
from chemvas.ui.line_tool import LineTool
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    services_for_window,
)
from chemvas.ui.preview_tools import ArrowTool
from chemvas.ui.scene_decoration_access import add_arrow_for
from chemvas.ui.scene_item_state_serialization import arrow_state_dict
from chemvas.ui.tool_context import ToolContext


def _circumcenter(a, b, c) -> tuple[float, float]:
    d = 2.0 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    ux = (
        (a[0] ** 2 + a[1] ** 2) * (b[1] - c[1])
        + (b[0] ** 2 + b[1] ** 2) * (c[1] - a[1])
        + (c[0] ** 2 + c[1] ** 2) * (a[1] - b[1])
    ) / d
    uy = (
        (a[0] ** 2 + a[1] ** 2) * (c[0] - b[0])
        + (b[0] ** 2 + b[1] ** 2) * (a[0] - c[0])
        + (c[0] ** 2 + c[1] ** 2) * (b[0] - a[0])
    ) / d
    return (ux, uy)


def _distance_from_chord(point, start, end) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    return ((point[0] - start[0]) * -dy + (point[1] - start[1]) * dx) / length


class ArcGeometryTest(unittest.TestCase):
    def test_arc_ends_are_exact_and_bulge_sits_on_the_requested_side(self) -> None:
        start, end = (0.0, 0.0), (40.0, 0.0)
        for sweep in (90.0, 180.0, 270.0):
            left = arc_points(start, end, sweep_degrees=sweep, bulge_left=True)
            right = arc_points(start, end, sweep_degrees=sweep, bulge_left=False)
            self.assertEqual((left[0], left[-1]), (start, end), sweep)
            self.assertEqual((right[0], right[-1]), (start, end), sweep)
            # Screen-left of a rightward drag is upward (smaller y).
            self.assertLess(min(y for _x, y in left), 0.0, sweep)
            self.assertGreater(max(y for _x, y in right), 0.0, sweep)
            self.assertGreaterEqual(len(left), 9)

    def test_arc_points_lie_on_one_circle_with_the_expected_sagitta(self) -> None:
        start, end = (10.0, 5.0), (50.0, 35.0)
        chord = math.hypot(40.0, 30.0)
        for sweep in (90.0, 180.0, 270.0):
            points = arc_points(start, end, sweep_degrees=sweep, bulge_left=True)
            mid = arc_midpoint(start, end, sweep_degrees=sweep, bulge_left=True)
            radius = chord / (2.0 * math.sin(math.radians(sweep) / 2.0))
            sagitta = radius * (1.0 - math.cos(math.radians(sweep) / 2.0))
            self.assertAlmostEqual(
                abs(_distance_from_chord(mid, start, end)), sagitta, places=6, msg=sweep
            )
            # Every sample lies on the circle through start, midpoint and end.
            center = _circumcenter(start, mid, end)
            for point in points:
                self.assertAlmostEqual(
                    math.hypot(point[0] - center[0], point[1] - center[1]),
                    radius,
                    places=6,
                    msg=(sweep, point),
                )

    def test_half_circle_midpoint_is_half_a_chord_away(self) -> None:
        mid = arc_midpoint(
            (0.0, 0.0), (40.0, 0.0), sweep_degrees=180.0, bulge_left=True
        )
        self.assertAlmostEqual(mid[0], 20.0)
        self.assertAlmostEqual(mid[1], -20.0)

    def test_zero_length_chord_degrades_to_its_ends(self) -> None:
        self.assertEqual(
            arc_points((3.0, 3.0), (3.0, 3.0), sweep_degrees=90.0, bulge_left=True),
            [(3.0, 3.0), (3.0, 3.0)],
        )

    def test_mirrored_arc_kind_round_trips(self) -> None:
        for kind in VALID_ARC_KINDS:
            mirrored = mirrored_arc_kind(kind)
            self.assertIn(mirrored, VALID_ARC_KINDS)
            self.assertNotEqual(mirrored, kind)
            self.assertEqual(mirrored_arc_kind(mirrored), kind)
            self.assertEqual(ARC_KIND_SWEEPS[kind][0], ARC_KIND_SWEEPS[mirrored][0])
        self.assertEqual(mirrored_arc_kind("arrow"), "arrow")
        self.assertTrue(VALID_ARC_KINDS <= VALID_ARROW_KINDS)


class EndpointSnapTest(unittest.TestCase):
    def test_nearest_candidate_within_radius_wins(self) -> None:
        candidates = [(0.0, 0.0), (10.0, 0.0), (100.0, 100.0)]
        self.assertEqual(
            snapped_endpoint((7.0, 1.0), candidates, radius=5.0), (10.0, 0.0)
        )
        self.assertEqual(
            snapped_endpoint((4.0, 0.0), candidates, radius=5.0), (0.0, 0.0)
        )
        self.assertEqual(
            snapped_endpoint((50.0, 50.0), candidates, radius=5.0), (50.0, 50.0)
        )
        self.assertEqual(snapped_endpoint((5.0, 0.0), [], radius=5.0), (5.0, 0.0))


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


class ArcDocumentTest(unittest.TestCase):
    def test_every_arc_kind_round_trips(self) -> None:
        arrows = [
            {"kind": kind, "start": [0.0, 0.0], "end": [40.0, 0.0]}
            for kind in sorted(VALID_ARC_KINDS)
        ]
        restored = extract_document_state(
            build_document_payload(_document_state(arrows), CANVAS_FILE_VERSION)
        )
        self.assertEqual(
            [arrow["kind"] for arrow in restored["arrows"]], sorted(VALID_ARC_KINDS)
        )


def _build_service():
    style = SimpleNamespace(bond_length_px=20.0, bond_spacing_px=4.4)
    renderer = SimpleNamespace(
        style=style,
        bond_pen=lambda: QPen(QColor("#222222")),
        bond_spacing=lambda: 4.4,
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


class ArcBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_arc_arrow_path_follows_the_arc_and_ends_with_a_head(self) -> None:
        service = _build_service()
        start, end = QPointF(0.0, 0.0), QPointF(40.0, 0.0)

        item = service.build_arrow_item(start, end, "arc_180_left")

        path = item.path()
        # arc samples (36 + 1 points) plus a three-element head.
        self.assertEqual(path.elementCount(), 37 + 3)
        self.assertLess(path.boundingRect().top(), -15.0)
        tip = path.elementAt(path.elementCount() - 2)
        self.assertAlmostEqual(tip.x, 40.0)
        self.assertAlmostEqual(tip.y, 0.0)
        self.assertEqual(
            item.data(2), {"start": start, "end": end, "control": None, "double": False}
        )

    def test_arc_labels_sit_at_the_arc_midpoint(self) -> None:
        service = _build_service()
        item = service.build_arrow_item(
            QPointF(0.0, 0.0), QPointF(40.0, 0.0), "arc_180_left"
        )
        item.setData(0, "arc_180_left")

        service.apply_arrow_labels(item, {"above": "k"})

        (above,) = [c for c in item.childItems() if c.data(0) == ARROW_LABEL_ROLE]
        self.assertLess(above.sceneBoundingRect().bottom(), -20.0)
        self.assertAlmostEqual(above.sceneBoundingRect().center().x(), 20.0, delta=0.5)


class _FakeScene:
    def __init__(self) -> None:
        self.removed = []

    def removeItem(self, item) -> None:
        self.removed.append(item)


class _FakePreviewItem:
    def __init__(self, scene) -> None:
        self._scene = scene

    def scene(self):
        return self._scene


class _FakeEvent:
    def __init__(
        self, pos: QPointF, *, modifiers=Qt.KeyboardModifier.NoModifier
    ) -> None:
        self._pos = QPointF(pos)
        self._modifiers = modifiers

    def button(self):
        return Qt.MouseButton.LeftButton

    def modifiers(self):
        return self._modifiers

    def position(self):
        return QPointF(self._pos)


class _FakeArrowItem:
    def __init__(self, start: QPointF, end: QPointF) -> None:
        self._data = {2: {"start": start, "end": end, "control": None, "double": False}}

    def data(self, role):
        return self._data.get(role)


class _FakeToolCanvas:
    DragMode = SimpleNamespace(NoDrag="none")

    def __init__(
        self, *, arrow_type: str = "reaction", line_kind: str = "line"
    ) -> None:
        self.scene_obj = _FakeScene()
        self.renderer = SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0))
        self.runtime_state = canvas_runtime_state(
            tool_settings_state=CanvasToolSettingsState(
                active_arrow_type=arrow_type, active_line_kind=line_kind
            ),
            scene_items_state=CanvasSceneItemsState(
                arrow_items=[_FakeArrowItem(QPointF(0.0, 0.0), QPointF(100.0, 0.0))]
            ),
        )
        self.preview_calls = []
        self.snap_mark_calls = []
        self.add_calls = []
        self.services = canvas_runtime_services(
            hit_testing_service=SimpleNamespace(
                scene_pos_from_event=lambda event: event.position(),
                item_at_scene_pos=lambda pos: None,
            ),
            scene_decoration_service=SimpleNamespace(add_arrow=self.add_arrow),
            arrow_build_service=SimpleNamespace(
                preview_arrow=self.preview_arrow,
                mark_snapped_points=lambda item, points: self.snap_mark_calls.append(
                    (item, list(points))
                ),
            ),
        )

    def transform(self):
        # The snap reach is a screen distance, so it asks the view.
        return QTransform()

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def scene(self):
        return self.scene_obj

    def preview_arrow(self, start, end, kind):
        self.preview_calls.append((QPointF(start), QPointF(end), kind))
        return _FakePreviewItem(self.scene_obj)

    def add_arrow(self, start, end, kind) -> None:
        self.add_calls.append((QPointF(start), QPointF(end), kind))


def _context(canvas) -> ToolContext:
    return ToolContext(
        canvas,
        hit_testing_service=canvas.services.hit_testing_service,
        selection_controller=None,
        note_controller=None,
        handle_controller=None,
        selection_rotation_controller=None,
    )


class SnapToolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_snap_radius_is_a_distance_on_screen(self) -> None:
        canvas = _FakeToolCanvas()
        radius = ENDPOINT_SNAP_SCREEN_PX
        near = snap_to_endpoint_for(canvas, QPointF(100.0 + radius * 0.9, 1.0))
        far = snap_to_endpoint_for(canvas, QPointF(100.0 + radius * 1.5, 0.0))
        assert near is not None
        self.assertEqual((near.x(), near.y()), (100.0, 0.0))
        self.assertIsNone(far)

    def test_line_tool_snaps_both_ends_and_snap_beats_the_angle_lock(self) -> None:
        canvas = _FakeToolCanvas()
        tool = LineTool(canvas, context=_context(canvas))

        tool.on_mouse_press(_FakeEvent(QPointF(3.0, 2.0)))
        self.assertEqual((tool._start_pos.x(), tool._start_pos.y()), (0.0, 0.0))
        tool.on_mouse_move(
            _FakeEvent(QPointF(97.0, 4.0), modifiers=Qt.KeyboardModifier.ShiftModifier)
        )
        _start, preview_end, _kind = canvas.preview_calls[-1]
        self.assertEqual((preview_end.x(), preview_end.y()), (100.0, 0.0))
        tool.on_mouse_release(
            _FakeEvent(QPointF(97.0, 4.0), modifiers=Qt.KeyboardModifier.ShiftModifier)
        )
        start, end, _kind = canvas.add_calls[-1]
        self.assertEqual((start.x(), start.y()), (0.0, 0.0))
        self.assertEqual((end.x(), end.y()), (100.0, 0.0))

    def test_arrow_tool_snaps_and_shift_mirrors_an_arc(self) -> None:
        canvas = _FakeToolCanvas(arrow_type="arc_90_left")
        tool = ArrowTool(canvas, mode="auto", context=_context(canvas))

        tool.on_mouse_press(_FakeEvent(QPointF(102.0, -3.0)))
        tool.on_mouse_move(_FakeEvent(QPointF(150.0, 50.0)))
        self.assertEqual(canvas.preview_calls[-1][2], "arc_90_left")
        tool.on_mouse_move(
            _FakeEvent(
                QPointF(150.0, 50.0), modifiers=Qt.KeyboardModifier.ShiftModifier
            )
        )
        self.assertEqual(canvas.preview_calls[-1][2], "arc_90_right")
        tool.on_mouse_release(
            _FakeEvent(
                QPointF(150.0, 50.0), modifiers=Qt.KeyboardModifier.ShiftModifier
            )
        )
        start, end, kind = canvas.add_calls[-1]
        self.assertEqual((start.x(), start.y()), (100.0, 0.0))
        self.assertEqual((end.x(), end.y()), (150.0, 50.0))
        self.assertEqual(kind, "arc_90_right")

    def test_started_drag_can_finish_near_its_start_without_self_snapping(
        self,
    ) -> None:
        for tool_class in (LineTool, ArrowTool):
            canvas = _FakeToolCanvas()
            tool = tool_class(canvas, context=_context(canvas))
            tool.on_mouse_press(_FakeEvent(QPointF(101.0, 1.0)))
            # Establish an intentional drag before returning close to its start.
            # The old press→release alone moves only five screen pixels, which
            # is now correctly a wobble/click, not a request for a short segment.
            tool.on_mouse_move(
                _FakeEvent(QPointF(102.0 + QApplication.startDragDistance(), 1.0))
            )
            tool.on_mouse_release(_FakeEvent(QPointF(104.0, 3.0)))
            start, end, _kind = canvas.add_calls[-1]
            self.assertEqual((start.x(), start.y()), (100.0, 0.0), tool_class)
            self.assertEqual((end.x(), end.y()), (104.0, 3.0), tool_class)

    def test_shift_does_not_mirror_a_plain_arrow(self) -> None:
        canvas = _FakeToolCanvas(arrow_type="reaction")
        tool = ArrowTool(canvas, mode="auto", context=_context(canvas))
        tool.on_mouse_press(_FakeEvent(QPointF(200.0, 200.0)))
        tool.on_mouse_release(
            _FakeEvent(
                QPointF(260.0, 200.0), modifiers=Qt.KeyboardModifier.ShiftModifier
            )
        )
        self.assertEqual(canvas.add_calls[-1][2], "reaction")


class KineticToolsGuiTest(unittest.TestCase):
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

    def _drag(
        self,
        canvas,
        start: QPointF,
        end: QPointF,
        modifiers=Qt.KeyboardModifier.NoModifier,
    ) -> None:
        start_pos = canvas.mapFromScene(start)
        end_pos = canvas.mapFromScene(end)
        QTest.mousePress(
            canvas.viewport(), Qt.MouseButton.LeftButton, modifiers, start_pos
        )
        self.app.processEvents()
        QTest.mouseMove(canvas.viewport(), end_pos)
        self.app.processEvents()
        QTest.mouseRelease(
            canvas.viewport(), Qt.MouseButton.LeftButton, modifiers, end_pos
        )
        self.app.processEvents()
        QTest.qWait(10)

    def test_wobble_on_an_existing_endpoint_does_not_add_a_stub_or_level(self) -> None:
        canvas = active_canvas_for_window(self.window)
        add_arrow_for(canvas, QPointF(-20.0, 0.0), QPointF(20.0, 0.0), "line")
        tool_mode = canvas_services_for(canvas).input.tool_mode_controller
        history = canvas_services_for(canvas).history_service
        for tool_kind in ("line", "arrow"):
            with self.subTest(tool_kind=tool_kind):
                tool_mode.set_tool(tool_kind)
                before = snapshot_canvas_state_for(canvas)
                stacks = history.capture_stack_snapshot()
                start = canvas.mapFromScene(QPointF(20.0, 0.0))
                end = start + QPoint(3, 0)
                QTest.mousePress(
                    canvas.viewport(), Qt.MouseButton.LeftButton, pos=start
                )
                QTest.mouseMove(canvas.viewport(), end)
                QTest.mouseRelease(
                    canvas.viewport(), Qt.MouseButton.LeftButton, pos=end
                )
                self.app.processEvents()
                self.assertEqual(snapshot_canvas_state_for(canvas), before)
                history.verify_stack_snapshot(stacks)

    def test_second_line_snaps_to_the_first_and_flipping_an_arc_mirrors_it(
        self,
    ) -> None:
        canvas = active_canvas_for_window(self.window)
        tool_mode = canvas_services_for(canvas).input.tool_mode_controller
        tool_mode.set_line_kind("line_bold")
        self._drag(canvas, QPointF(-60.0, 0.0), QPointF(-20.0, 0.0))
        tool_mode.set_line_kind("line_dashed")
        self._drag(canvas, QPointF(-17.0, 3.0), QPointF(40.0, -40.0))

        level, connector = arrow_items_for(canvas)
        self.assertEqual(arrow_state_dict(connector)["start"], (-20.0, 0.0))

        tool_mode.set_arrow_type("arc_90_left")
        self._drag(canvas, QPointF(60.0, 60.0), QPointF(120.0, 60.0))
        arc = arrow_items_for(canvas)[-1]
        self.assertEqual(arc.data(0), "arc_90_left")
        # Drawn left to right, a left-bulging arc rises above its chord.
        self.assertLess(arc.path().boundingRect().top(), 60.0 - 5.0)
        arc.setSelected(True)
        QTest.keyClick(
            canvas,
            Qt.Key.Key_H,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
        self.app.processEvents()
        self.assertEqual(arc.data(0), "arc_90_right")
        self.assertEqual(arrow_state_dict(arc)["kind"], "arc_90_right")
        # The mirror image still rises above the chord, so the path did change
        # side relative to its (now reversed) drag direction.
        self.assertLess(arc.path().boundingRect().top(), 60.0 - 5.0)
        self.assertGreater(
            arrow_state_dict(arc)["start"][0], arrow_state_dict(arc)["end"][0]
        )
        QTest.keyClick(
            canvas,
            Qt.Key.Key_V,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
        self.app.processEvents()
        # A vertical flip mirrors again: the bulge is now below the chord.
        self.assertEqual(arc.data(0), "arc_90_left")
        self.assertGreater(arc.path().boundingRect().bottom(), 60.0 + 5.0)
        history = canvas.runtime_state.history_service
        history.undo()
        history.undo()
        self.assertEqual(arc.data(0), "arc_90_left")
        self.assertLess(arc.path().boundingRect().top(), 60.0 - 5.0)

        snapshot_kinds = [
            state["kind"] for state in snapshot_canvas_state_for(canvas)["arrows"]
        ]
        self.assertEqual(snapshot_kinds, ["line_bold", "line_dashed", "arc_90_left"])

    def test_line_tool_double_click_labels_the_level_without_adding_one(self) -> None:
        canvas = active_canvas_for_window(self.window)
        tool_mode = canvas_services_for(canvas).input.tool_mode_controller
        tool_mode.set_line_kind("line_bold")
        self._drag(canvas, QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        (level,) = arrow_items_for(canvas)
        pos = canvas.mapFromScene(QPointF(0.0, 0.0))

        with mock.patch(
            "chemvas.ui.scene_decoration_service.prompt_arrow_labels",
            return_value={"above": "TS", "below": ""},
        ) as prompt:
            for press in (
                QTest.mousePress,
                QTest.mouseRelease,
                QTest.mouseDClick,
                QTest.mouseRelease,
            ):
                press(
                    canvas.viewport(),
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    pos,
                )
            self.app.processEvents()
            QTest.qWait(10)

        prompt.assert_called_once()
        self.assertEqual(arrow_items_for(canvas), [level])
        self.assertEqual(arrow_state_dict(level)["labels"], {"above": "TS"})
