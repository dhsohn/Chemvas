import math
import os
import unittest
from itertools import pairwise
from types import SimpleNamespace

from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QGraphicsPathItem, QToolButton

from chemvas.bootstrap.main_window import build_main_window
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    CLIPBOARD_SELECTION_VERSION,
    VALID_ARROW_KINDS,
    VALID_LINE_KINDS,
    build_document_payload,
    extract_document_state,
    serialize_settings,
    validate_clipboard_selection_payload,
)
from chemvas.features.rendering import snapped_line_end, wavy_line_points
from chemvas.ui.canvas_arrow_build_service import CanvasArrowBuildService
from chemvas.ui.canvas_scene_items_state import CanvasSceneItemsState, arrow_items_for
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.canvas_tool_settings_state import (
    CanvasToolSettingsState,
    tool_settings_state_for,
)
from chemvas.ui.canvas_window_access import (
    restore_canvas_state_for,
    snapshot_canvas_state_for,
)
from chemvas.ui.line_tool import LINE_ANGLE_STEP_DEGREES, LineTool
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    services_for_window,
)
from chemvas.ui.move_access import move_item_for
from chemvas.ui.scene_item_access import apply_scene_item_state
from chemvas.ui.scene_item_restore import create_arrow_item_from_state
from chemvas.ui.scene_item_state_serialization import arrow_state_dict
from chemvas.ui.tool_context import ToolContext

LINE_KINDS = ("line", "line_dashed", "line_wavy", "line_bold")


class LineGeometryTest(unittest.TestCase):
    def test_snapped_end_rounds_angle_and_keeps_length(self) -> None:
        start = (10.0, 10.0)
        end = (
            10.0 + 20.0 * math.cos(math.radians(47.0)),
            10.0 + 20.0 * math.sin(math.radians(47.0)),
        )

        x, y = snapped_line_end(start, end, step_degrees=15.0)

        self.assertAlmostEqual(math.hypot(x - 10.0, y - 10.0), 20.0)
        self.assertAlmostEqual(math.degrees(math.atan2(y - 10.0, x - 10.0)), 45.0)

    def test_snapped_end_makes_near_horizontal_drag_exactly_horizontal(self) -> None:
        x, y = snapped_line_end((0.0, 0.0), (30.0, 2.0), step_degrees=15.0)

        self.assertAlmostEqual(y, 0.0)
        self.assertAlmostEqual(x, math.hypot(30.0, 2.0))

    def test_snapped_end_passes_zero_length_through(self) -> None:
        self.assertEqual(
            snapped_line_end((3.0, 4.0), (3.0, 4.0), step_degrees=15.0), (3.0, 4.0)
        )

    def test_wavy_points_start_and_end_exactly_on_the_axis(self) -> None:
        points = wavy_line_points(
            (0.0, 0.0), (44.0, 0.0), half_wavelength=4.4, amplitude=2.2
        )

        self.assertEqual(points[0], (0.0, 0.0))
        self.assertEqual(points[-1], (44.0, 0.0))
        # Ten half-waves of eight samples, plus the closing end point.
        self.assertEqual(len(points), 81)
        peaks = [y for _x, y in points if abs(abs(y) - 2.2) < 1e-9]
        self.assertEqual(len(peaks), 10)
        # Consecutive peaks alternate sides of the axis.
        self.assertTrue(all(a * b < 0 for a, b in pairwise(peaks)))

    def test_wavy_points_follow_a_diagonal_segment(self) -> None:
        start, end = (5.0, 5.0), (25.0, 25.0)
        points = wavy_line_points(start, end, half_wavelength=4.4, amplitude=2.2)

        length = math.hypot(20.0, 20.0)
        ux, uy = 20.0 / length, 20.0 / length
        offsets = [abs((x - 5.0) * -uy + (y - 5.0) * ux) for x, y in points]
        self.assertLessEqual(max(offsets), 2.2 + 1e-9)
        # The wave actually reaches its amplitude on the diagonal too.
        self.assertAlmostEqual(max(offsets), 2.2)
        self.assertEqual(points[-1], end)

    def test_wavy_points_are_capped_for_absurdly_long_lines(self) -> None:
        points = wavy_line_points(
            (0.0, 0.0), (1.0e9, 0.0), half_wavelength=4.4, amplitude=2.2
        )

        self.assertEqual(len(points), 2048 * 8 + 1)
        self.assertEqual(points[-1], (1.0e9, 0.0))

    def test_wavy_points_fall_back_to_a_segment_when_the_wavelength_is_zero(
        self,
    ) -> None:
        self.assertEqual(
            wavy_line_points(
                (0.0, 0.0), (30.0, 0.0), half_wavelength=0.0, amplitude=2.2
            ),
            [(0.0, 0.0), (30.0, 0.0)],
        )

    def test_wavy_points_for_zero_length_segment_are_its_two_ends(self) -> None:
        self.assertEqual(
            wavy_line_points(
                (1.0, 2.0), (1.0, 2.0), half_wavelength=4.4, amplitude=2.2
            ),
            [(1.0, 2.0), (1.0, 2.0)],
        )


class LineBuildServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _make_service(self):
        style = SimpleNamespace(bond_length_px=20.0, bond_spacing_px=4.4)

        def bold_pen():
            pen = QPen(QColor("#222222"))
            pen.setWidthF(3.3)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            return pen

        renderer = SimpleNamespace(
            style=style,
            bond_pen=lambda: QPen(QColor("#222222")),
            bold_bond_pen=bold_pen,
            bond_spacing=lambda: 4.4,
        )
        canvas = SimpleNamespace(
            renderer=renderer,
            runtime_state=canvas_runtime_state(
                tool_settings_state=CanvasToolSettingsState(
                    arrow_line_width=1.5, arrow_head_scale=0.3
                )
            ),
        )
        return CanvasArrowBuildService(canvas)

    def test_line_kinds_are_members_of_the_arrow_family(self) -> None:
        self.assertEqual(VALID_LINE_KINDS, frozenset(LINE_KINDS))
        self.assertTrue(VALID_LINE_KINDS <= VALID_ARROW_KINDS)

    def test_plain_line_is_a_headless_segment_with_arrow_metadata(self) -> None:
        service = self._make_service()
        start, end = QPointF(0.0, 0.0), QPointF(30.0, 0.0)

        item = service.build_arrow_item(start, end, "line")

        self.assertIsInstance(item, QGraphicsPathItem)
        self.assertEqual(item.path().elementCount(), 2)
        self.assertEqual(item.pen().style(), Qt.PenStyle.SolidLine)
        self.assertAlmostEqual(item.pen().widthF(), 1.5)
        self.assertEqual(
            item.data(2), {"start": start, "end": end, "control": None, "double": False}
        )

    def test_dashed_line_uses_the_dashed_arrow_pen(self) -> None:
        service = self._make_service()

        item = service.build_line_item(
            QPointF(0.0, 0.0), QPointF(30.0, 0.0), "line_dashed"
        )

        self.assertEqual(item.path().elementCount(), 2)
        self.assertEqual(item.pen().style(), Qt.PenStyle.DashLine)

    def test_bold_line_uses_the_bold_bond_pen(self) -> None:
        service = self._make_service()

        item = service.build_line_item(
            QPointF(0.0, 0.0), QPointF(30.0, 0.0), "line_bold"
        )

        self.assertEqual(item.path().elementCount(), 2)
        self.assertAlmostEqual(item.pen().widthF(), 3.3)
        self.assertEqual(item.pen().capStyle(), Qt.PenCapStyle.FlatCap)

    def test_wavy_line_is_a_polyline_within_half_a_bond_spacing_of_the_axis(
        self,
    ) -> None:
        service = self._make_service()
        start, end = QPointF(0.0, 0.0), QPointF(44.0, 0.0)

        item = service.build_line_item(start, end, "line_wavy")

        path = item.path()
        self.assertEqual(path.elementCount(), 81)
        self.assertEqual((path.elementAt(0).x, path.elementAt(0).y), (0.0, 0.0))
        self.assertEqual((path.elementAt(80).x, path.elementAt(80).y), (44.0, 0.0))
        self.assertAlmostEqual(path.boundingRect().height(), 4.4, places=6)
        self.assertEqual(item.pen().style(), Qt.PenStyle.SolidLine)

    def test_line_state_round_trips_through_serialization_and_restore(self) -> None:
        service = self._make_service()
        for kind in LINE_KINDS:
            item = service.build_line_item(QPointF(1.0, 2.0), QPointF(9.0, 4.0), kind)
            item.setData(0, kind)

            state = arrow_state_dict(item)
            self.assertEqual(state["kind"], kind)
            self.assertEqual(state["start"], (1.0, 2.0))
            self.assertEqual(state["end"], (9.0, 4.0))

            restored = create_arrow_item_from_state(
                state,
                build_arrow_item=service.build_arrow_item,
                set_curved_arrow_path=lambda *_args: None,
            )
            assert restored is not None
            self.assertEqual(restored.data(0), kind)
            self.assertEqual(arrow_state_dict(restored), state)
            self.assertEqual(
                restored.path().elementCount(), item.path().elementCount(), kind
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


def _line_state(kind: str) -> dict:
    return {"kind": kind, "start": [0.0, 0.0], "end": [40.0, 0.0]}


class LineDocumentContractTest(unittest.TestCase):
    def test_document_payload_round_trips_every_line_kind(self) -> None:
        state = _document_state([_line_state(kind) for kind in LINE_KINDS])

        payload = build_document_payload(state, CANVAS_FILE_VERSION)
        restored = extract_document_state(payload)

        self.assertEqual(payload["version"], CANVAS_FILE_VERSION)
        self.assertEqual(
            [arrow["kind"] for arrow in restored["arrows"]], list(LINE_KINDS)
        )

    def test_unknown_line_kind_is_rejected(self) -> None:
        state = _document_state([_line_state("line_dotted")])

        with self.assertRaises(ValueError):
            build_document_payload(state, CANVAS_FILE_VERSION)

    def test_clipboard_payload_accepts_line_kinds(self) -> None:
        payload = {
            "version": CLIPBOARD_SELECTION_VERSION,
            "atoms": [],
            "bonds": [],
            "ring_fills": [],
            "scene_items": [_line_state("line_bold")],
        }
        # The validator either accepts the item or names the bad field; a line
        # kind must not be what it rejects.
        try:
            validate_clipboard_selection_payload(payload)
        except ValueError as error:
            self.fail(f"line kind rejected by the clipboard validator: {error}")


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
        self,
        pos: QPointF,
        *,
        button=Qt.MouseButton.LeftButton,
        modifiers=Qt.KeyboardModifier.NoModifier,
    ) -> None:
        self._pos = QPointF(pos)
        self._button = button
        self._modifiers = modifiers

    def button(self):
        return self._button

    def modifiers(self):
        return self._modifiers

    def position(self):
        return QPointF(self._pos)


class _FakeLineCanvas:
    DragMode = SimpleNamespace(NoDrag="none")

    def __init__(self, kind: str = "line") -> None:
        self.scene_obj = _FakeScene()
        self.renderer = SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0))
        self.runtime_state = canvas_runtime_state(
            tool_settings_state=CanvasToolSettingsState(active_line_kind=kind),
            scene_items_state=CanvasSceneItemsState(),
        )
        self.preview_calls = []
        self.add_calls = []
        self.item_under_cursor = None
        self.services = canvas_runtime_services(
            hit_testing_service=SimpleNamespace(
                scene_pos_from_event=lambda event: event.position(),
                item_at_scene_pos=lambda pos: self.item_under_cursor,
            ),
            scene_decoration_service=SimpleNamespace(add_arrow=self.add_arrow),
            scene_decoration_build_service=SimpleNamespace(
                preview_arrow=self.preview_arrow
            ),
        )

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def scene(self):
        return self.scene_obj

    def preview_arrow(self, start, end, kind):
        self.preview_calls.append((QPointF(start), QPointF(end), kind))
        return _FakePreviewItem(self.scene_obj)

    def add_arrow(self, start, end, kind) -> None:
        self.add_calls.append((QPointF(start), QPointF(end), kind))


def _line_tool(canvas) -> LineTool:
    context = ToolContext(
        canvas,
        hit_testing_service=canvas.services.hit_testing_service,
        selection_controller=None,
        note_controller=None,
        handle_controller=None,
        selection_rotation_controller=None,
    )
    return LineTool(canvas, context=context)


class LineToolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_drag_previews_and_commits_the_active_kind(self) -> None:
        canvas = _FakeLineCanvas("line_wavy")
        tool = _line_tool(canvas)
        tool.activate()

        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(1.0, 2.0))))
        self.assertTrue(tool.on_mouse_move(_FakeEvent(QPointF(5.0, 6.0))))
        self.assertEqual(canvas.preview_calls[-1][2], "line_wavy")
        self.assertTrue(tool.on_mouse_release(_FakeEvent(QPointF(8.0, 9.0))))

        start, end, kind = canvas.add_calls[-1]
        self.assertEqual((start.x(), start.y()), (1.0, 2.0))
        self.assertEqual((end.x(), end.y()), (8.0, 9.0))
        self.assertEqual(kind, "line_wavy")
        self.assertIsNone(tool._start_pos)
        self.assertTrue(canvas.scene_obj.removed)

    def test_shift_locks_the_angle_for_preview_and_commit(self) -> None:
        canvas = _FakeLineCanvas()
        tool = _line_tool(canvas)
        shift = Qt.KeyboardModifier.ShiftModifier

        tool.on_mouse_press(_FakeEvent(QPointF(0.0, 0.0)))
        tool.on_mouse_move(_FakeEvent(QPointF(30.0, 2.0), modifiers=shift))
        _start, preview_end, _kind = canvas.preview_calls[-1]
        self.assertAlmostEqual(preview_end.y(), 0.0)
        self.assertAlmostEqual(preview_end.x(), math.hypot(30.0, 2.0))

        tool.on_mouse_release(_FakeEvent(QPointF(30.0, 2.0), modifiers=shift))
        _start, end, _kind = canvas.add_calls[-1]
        self.assertAlmostEqual(end.y(), 0.0)
        self.assertEqual(LINE_ANGLE_STEP_DEGREES, 15.0)

    def test_releasing_shift_before_release_commits_the_raw_point(self) -> None:
        canvas = _FakeLineCanvas()
        tool = _line_tool(canvas)

        tool.on_mouse_press(_FakeEvent(QPointF(0.0, 0.0)))
        tool.on_mouse_move(
            _FakeEvent(QPointF(30.0, 2.0), modifiers=Qt.KeyboardModifier.ShiftModifier)
        )
        tool.on_mouse_release(_FakeEvent(QPointF(30.0, 2.0)))

        _start, end, _kind = canvas.add_calls[-1]
        self.assertEqual((end.x(), end.y()), (30.0, 2.0))

    def test_click_without_drag_places_a_horizontal_level(self) -> None:
        canvas = _FakeLineCanvas("line_bold")
        tool = _line_tool(canvas)

        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(4.0, 4.0))))
        self.assertTrue(tool.on_mouse_release(_FakeEvent(QPointF(4.0, 4.0))))

        start, end, kind = canvas.add_calls[-1]
        self.assertEqual((start.x(), start.y()), (4.0, 4.0))
        self.assertEqual((end.x(), end.y()), (44.0, 4.0))
        self.assertEqual(kind, "line_bold")
        self.assertIsNone(tool._start_pos)

    def test_click_on_an_existing_object_places_nothing(self) -> None:
        canvas = _FakeLineCanvas()
        canvas.item_under_cursor = object()
        tool = _line_tool(canvas)

        self.assertTrue(tool.on_mouse_press(_FakeEvent(QPointF(4.0, 4.0))))
        self.assertTrue(tool.on_mouse_release(_FakeEvent(QPointF(4.0, 4.0))))

        self.assertEqual(canvas.add_calls, [])


class LineToolGuiTest(unittest.TestCase):
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

    def _drag(self, canvas, start: QPointF, end: QPointF, modifiers) -> None:
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

    def test_every_line_kind_draws_undoes_redoes_and_round_trips(self) -> None:
        canvas = active_canvas_for_window(self.window)
        tool_mode = canvas_services_for(canvas).input.tool_mode_controller
        history = canvas.runtime_state.history_service

        for index, kind in enumerate(LINE_KINDS):
            tool_mode.set_line_kind(kind)
            self.assertEqual(canvas.services.tool_controller.active.name, "line")
            self.assertEqual(tool_settings_state_for(canvas).active_line_kind, kind)
            start = QPointF(-40.0, -30.0 + 20.0 * index)
            end = QPointF(40.0, -30.0 + 20.0 * index)
            self._drag(canvas, start, end, Qt.KeyboardModifier.NoModifier)

            items = arrow_items_for(canvas)
            self.assertEqual(len(items), index + 1, kind)
            self.assertEqual(items[-1].data(0), kind)
            self.assertIs(items[-1].scene(), canvas.scene())

        history.undo()
        self.assertEqual(len(arrow_items_for(canvas)), len(LINE_KINDS) - 1)
        history.redo()
        self.assertEqual(
            [item.data(0) for item in arrow_items_for(canvas)], list(LINE_KINDS)
        )

        # Moving a wavy line patches its scene-coordinate data; the undo path
        # rebuilds the polyline from that data, so both must stay in step.
        wavy = arrow_items_for(canvas)[LINE_KINDS.index("line_wavy")]
        element_count = wavy.path().elementCount()
        before = arrow_state_dict(wavy)
        move_item_for(canvas, wavy, 7.0, -3.0)
        moved = arrow_state_dict(wavy)
        self.assertEqual(
            moved["start"], (before["start"][0] + 7.0, before["start"][1] - 3.0)
        )
        self.assertEqual(moved["end"], (before["end"][0] + 7.0, before["end"][1] - 3.0))
        apply_scene_item_state(canvas, wavy, moved)
        self.assertEqual(wavy.pos(), QPointF(0.0, 0.0))
        self.assertEqual(wavy.path().elementCount(), element_count)
        first = wavy.path().elementAt(0)
        self.assertAlmostEqual(first.x, moved["start"][0])
        self.assertAlmostEqual(first.y, moved["start"][1])
        self.assertEqual(arrow_state_dict(wavy), moved)

        state = snapshot_canvas_state_for(canvas)
        self.assertEqual([arrow["kind"] for arrow in state["arrows"]], list(LINE_KINDS))
        payload = build_document_payload(state, CANVAS_FILE_VERSION)
        restore_canvas_state_for(canvas, extract_document_state(payload))
        restored = arrow_items_for(canvas)
        self.assertEqual([item.data(0) for item in restored], list(LINE_KINDS))
        self.assertEqual(snapshot_canvas_state_for(canvas)["arrows"], state["arrows"])

    def test_shift_drag_on_the_canvas_snaps_the_committed_line(self) -> None:
        canvas = active_canvas_for_window(self.window)
        canvas_services_for(canvas).input.tool_mode_controller.set_line_kind(
            "line_bold"
        )

        self._drag(
            canvas,
            QPointF(0.0, 0.0),
            QPointF(60.0, 5.0),
            Qt.KeyboardModifier.ShiftModifier,
        )

        items = arrow_items_for(canvas)
        self.assertEqual(len(items), 1)
        data = items[0].data(2)
        self.assertAlmostEqual(data["end"].y(), data["start"].y(), places=3)
        self.assertAlmostEqual(
            data["end"].x() - data["start"].x(), math.hypot(60.0, 5.0), places=3
        )

    def test_line_context_page_offers_the_four_kinds(self) -> None:
        tips = ["Line", "Dashed line", "Wavy line", "Bold line"]
        buttons = {
            button.toolTip(): button
            for button in self.window.findChildren(QToolButton)
            if button.toolTip() in tips
        }
        self.assertEqual(sorted(buttons), sorted(tips))
        self.assertTrue(buttons["Line"].isChecked())

        buttons["Wavy line"].click()
        self.app.processEvents()
        canvas = active_canvas_for_window(self.window)
        self.assertEqual(tool_settings_state_for(canvas).active_line_kind, "line_wavy")
        self.assertEqual(canvas.services.tool_controller.active.name, "line")
