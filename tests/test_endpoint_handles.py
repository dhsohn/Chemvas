import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.main_window import build_main_window
from chemvas.domain.document import (
    VALID_ARROW_KINDS,
    VALID_CURVED_ARROW_KINDS,
)
from chemvas.ui.canvas_scene_items_state import arrow_items_for
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.endpoint_snap_access import arrow_endpoints_for
from chemvas.ui.handle_state import active_handles_for, handle_target_for
from chemvas.ui.history_commands import UpdateSceneItemCommand
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    services_for_window,
)
from chemvas.ui.move_access import move_item_for
from chemvas.ui.scene_decoration_access import add_arrow_for
from chemvas.ui.scene_item_access import remove_scene_item
from chemvas.ui.scene_item_state_serialization import arrow_state_dict


def _handle_types(canvas) -> list[str]:
    return [handle.data(1) for handle in active_handles_for(canvas)]


class EndpointHandleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = build_main_window()
        self.window.show()
        self.canvas = active_canvas_for_window(self.window)
        self.canvas.setFocus()
        canvas_services_for(self.canvas).input.tool_mode_controller.set_tool("select")
        self.app.processEvents()
        QTest.qWait(20)

    def tearDown(self) -> None:
        document_service = services_for_window(self.window).canvas_document_service
        for canvas in self.window.tab_references.all_canvases():
            document_service.mark_clean(canvas)
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def _handles(self):
        return canvas_services_for(self.canvas).handles

    def _add(self, kind: str, start: QPointF, end: QPointF):
        return add_arrow_for(self.canvas, start, end, kind)

    def _click(self, scene_pos: QPointF) -> None:
        pos = self.canvas.mapFromScene(scene_pos)
        QTest.mousePress(
            self.canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            pos,
        )
        QTest.mouseRelease(
            self.canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

    def test_every_non_curved_arrow_kind_gets_two_endpoint_handles(self) -> None:
        overlay = self._handles().handle_overlay_service
        for kind in sorted(VALID_ARROW_KINDS - VALID_CURVED_ARROW_KINDS):
            item = self._add(kind, QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
            overlay.show_endpoint_handles(item)
            self.assertEqual(
                _handle_types(self.canvas), ["arrow_start", "arrow_end"], kind
            )
            self.assertIs(handle_target_for(self.canvas), item, kind)
            positions = [
                handle.sceneBoundingRect().center()
                for handle in active_handles_for(self.canvas)
            ]
            self.assertAlmostEqual(positions[0].x(), -40.0, places=6, msg=kind)
            self.assertAlmostEqual(positions[1].x(), 40.0, places=6, msg=kind)
            self._handles().handle_overlay_service.clear_handles()
            remove_scene_item(self.canvas, item)

    def test_curved_arrows_keep_their_three_handles(self) -> None:
        item = self._add("curved_single", QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        self._handles().handle_overlay_service.show_curved_handles(item)
        self.assertEqual(
            _handle_types(self.canvas), ["curved_start", "curved_control", "curved_end"]
        )

    def test_dragging_a_handle_moves_that_end_and_keeps_the_other(self) -> None:
        item = self._add("arrow", QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        controller = self._handles().handle_controller
        self._handles().handle_overlay_service.show_endpoint_handles(item)
        end_handle = active_handles_for(self.canvas)[1]

        controller.update_handle_drag(end_handle, QPointF(60.0, 30.0))

        state = arrow_state_dict(item)
        self.assertEqual(state["start"], (-40.0, 0.0))
        self.assertEqual(state["end"], (60.0, 30.0))
        # The handles follow the change, so a second drag starts from the new end.
        positions = [
            handle.sceneBoundingRect().center()
            for handle in active_handles_for(self.canvas)
        ]
        self.assertAlmostEqual(positions[1].x(), 60.0, places=6)
        self.assertAlmostEqual(positions[1].y(), 30.0, places=6)

    def test_dragging_an_endpoint_snaps_to_another_item_but_not_to_itself(self) -> None:
        level = self._add("line_bold", QPointF(-60.0, 0.0), QPointF(-20.0, 0.0))
        connector = self._add("line_dashed", QPointF(40.0, 40.0), QPointF(80.0, 40.0))
        controller = self._handles().handle_controller
        self._handles().handle_overlay_service.show_endpoint_handles(connector)
        start_handle = active_handles_for(self.canvas)[0]

        controller.update_handle_drag(start_handle, QPointF(-18.0, 2.0))

        self.assertEqual(arrow_state_dict(connector)["start"], (-20.0, 0.0))
        self.assertEqual(arrow_state_dict(level)["end"], (-20.0, 0.0))
        # The dragged item's own far end is not a snap candidate.
        self.assertNotIn(
            (80.0, 40.0), arrow_endpoints_for(self.canvas, exclude=connector)
        )
        self.assertIn((80.0, 40.0), arrow_endpoints_for(self.canvas))

    def test_an_end_can_be_dragged_close_to_its_own_start(self) -> None:
        # The item's own endpoints are not snap candidates, so a short arrow
        # stays draggable instead of snapping onto its start and being refused.
        item = self._add("arrow", QPointF(0.0, 0.0), QPointF(40.0, 0.0))
        controller = self._handles().handle_controller
        self._handles().handle_overlay_service.show_endpoint_handles(item)

        controller.update_handle_drag(
            active_handles_for(self.canvas)[1], QPointF(5.0, 0.0)
        )

        self.assertEqual(arrow_state_dict(item)["end"], (5.0, 0.0))

    def test_a_drag_onto_the_other_end_is_refused(self) -> None:
        item = self._add("arrow", QPointF(0.0, 0.0), QPointF(40.0, 0.0))
        controller = self._handles().handle_controller
        self._handles().handle_overlay_service.show_endpoint_handles(item)
        end_handle = active_handles_for(self.canvas)[1]

        controller.update_handle_drag(end_handle, QPointF(0.0, 0.0))

        self.assertEqual(arrow_state_dict(item)["end"], (40.0, 0.0))

    def test_a_curved_endpoint_takes_another_items_endpoint(self) -> None:
        # A curved arrow's ends carry the same kind of handle, so they snap the
        # same way; they used to copy the raw cursor instead.
        self._add("line_bold", QPointF(-60.0, 0.0), QPointF(-20.0, 0.0))
        curved = self._add("curved_single", QPointF(40.0, 40.0), QPointF(100.0, 40.0))
        controller = self._handles().handle_controller
        self._handles().handle_overlay_service.show_curved_handles(curved)

        controller.update_handle_drag(
            active_handles_for(self.canvas)[0], QPointF(-18.0, 2.0)
        )

        state = arrow_state_dict(curved)
        self.assertEqual(state["start"], (-20.0, 0.0))
        self.assertEqual(state["end"], (100.0, 40.0))

    def test_a_curved_end_can_be_dragged_close_to_its_own_start(self) -> None:
        # A curved arrow's own ends are not snap candidates either, so a
        # short curve stays draggable instead of collapsing onto its start.
        curved = self._add("curved_single", QPointF(0.0, 0.0), QPointF(40.0, 0.0))
        controller = self._handles().handle_controller
        self._handles().handle_overlay_service.show_curved_handles(curved)

        controller.update_handle_drag(
            active_handles_for(self.canvas)[2], QPointF(5.0, 0.0)
        )

        self.assertEqual(arrow_state_dict(curved)["end"], (5.0, 0.0))

    def test_a_curved_drag_onto_the_other_end_is_refused(self) -> None:
        curved = self._add("curved_single", QPointF(0.0, 0.0), QPointF(40.0, 0.0))
        controller = self._handles().handle_controller
        self._handles().handle_overlay_service.show_curved_handles(curved)

        controller.update_handle_drag(
            active_handles_for(self.canvas)[0], QPointF(40.0, 0.0)
        )

        self.assertEqual(arrow_state_dict(curved)["start"], (0.0, 0.0))

    def test_an_arc_keeps_its_sweep_and_its_label_follows(self) -> None:
        item = self._add("arc_90_left", QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        service = canvas_services_for(
            self.canvas
        ).scene_decoration.scene_decoration_service
        service.set_arrow_labels(item, {"above": "k_1"})
        before_elements = item.path().elementCount()
        label = next(
            child for child in item.childItems() if child.data(0) == "arrow_label"
        )
        before_label_x = label.sceneBoundingRect().center().x()
        controller = self._handles().handle_controller
        self._handles().handle_overlay_service.show_endpoint_handles(item)

        controller.update_handle_drag(
            active_handles_for(self.canvas)[1], QPointF(120.0, 0.0)
        )

        state = arrow_state_dict(item)
        self.assertEqual(state["end"], (120.0, 0.0))
        self.assertEqual(state["labels"], {"above": "k_1"})
        # Same sweep, so the same sample count; the bulge and label follow the
        # longer chord instead of staying put.
        self.assertEqual(item.path().elementCount(), before_elements)
        label = next(
            child for child in item.childItems() if child.data(0) == "arrow_label"
        )
        self.assertGreater(label.sceneBoundingRect().center().x(), before_label_x)

    def test_clicking_a_selected_arrow_toggles_its_handles(self) -> None:
        item = self._add("line", QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        item.setSelected(True)
        self.app.processEvents()

        self._click(QPointF(0.0, 0.0))
        self.assertEqual(_handle_types(self.canvas), ["arrow_start", "arrow_end"])

        self._click(QPointF(0.0, 0.0))
        self.assertEqual(_handle_types(self.canvas), [])

    def test_a_handle_drag_undoes_and_redoes_as_one_step(self) -> None:
        item = self._add("line_bold", QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        item.setSelected(True)
        self.app.processEvents()
        self._click(QPointF(0.0, 0.0))
        handle = active_handles_for(self.canvas)[1]
        history = self.canvas.runtime_state.history_service
        depth_before = len(history.state.history)

        handle_pos = self.canvas.mapFromScene(handle.sceneBoundingRect().center())
        target_pos = self.canvas.mapFromScene(QPointF(90.0, 25.0))
        QTest.mousePress(
            self.canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            handle_pos,
        )
        self.app.processEvents()
        QTest.mouseMove(self.canvas.viewport(), target_pos)
        self.app.processEvents()
        QTest.mouseRelease(
            self.canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            target_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(arrow_state_dict(item)["end"], (90.0, 25.0))
        self.assertEqual(len(history.state.history), depth_before + 1)
        history.undo()
        self.assertEqual(arrow_state_dict(item)["end"], (40.0, 0.0))
        history.redo()
        self.assertEqual(arrow_state_dict(item)["end"], (90.0, 25.0))

    def test_deleting_a_handled_arrow_clears_its_handles(self) -> None:
        item = self._add("arrow", QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        self._handles().handle_overlay_service.show_endpoint_handles(item)
        self.assertIs(handle_target_for(self.canvas), item)

        remove_scene_item(self.canvas, item)

        self.assertEqual(active_handles_for(self.canvas), [])
        self.assertIsNone(handle_target_for(self.canvas))
        self.assertEqual(arrow_items_for(self.canvas), [])

    def test_switching_tools_clears_the_handles(self) -> None:
        item = self._add("arrow", QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        self._handles().handle_overlay_service.show_endpoint_handles(item)

        canvas_services_for(self.canvas).input.tool_mode_controller.set_tool("bond")
        self.app.processEvents()

        self.assertEqual(active_handles_for(self.canvas), [])

    def test_endpoint_mutation_ignores_bad_geometry_and_bad_endpoint_names(
        self,
    ) -> None:
        mutation = self._handles().handle_mutation_service
        good = self._add("arrow", QPointF(0.0, 0.0), QPointF(40.0, 0.0))
        blank = self._add("arrow", QPointF(0.0, 60.0), QPointF(40.0, 60.0))
        blank.setData(2, {})

        with mock.patch.object(blank, "setPath") as blank_path:
            mutation.update_arrow_endpoint(blank, QPointF(10.0, 10.0), "start")
        blank_path.assert_not_called()

        with mock.patch.object(good, "setPath") as good_path:
            mutation.update_arrow_endpoint(good, QPointF(10.0, 10.0), "sideways")
        good_path.assert_not_called()
        self.assertEqual(arrow_state_dict(good)["end"], (40.0, 0.0))

    def test_dragging_an_endpoint_of_a_moved_arrow_stays_aligned(self) -> None:
        # A moved item carries its offset in pos() while its geometry stays
        # absolute; rebuilding the path without clearing that offset drew the
        # arrow one move-delta away from its own handles.
        item = self._add("arrow", QPointF(0.0, 0.0), QPointF(40.0, 0.0))
        move_item_for(self.canvas, item, 200.0, 0.0)
        controller = self._handles().handle_controller
        self._handles().handle_overlay_service.show_endpoint_handles(item)

        controller.update_handle_drag(
            active_handles_for(self.canvas)[1], QPointF(300.0, 0.0)
        )

        state = arrow_state_dict(item)
        self.assertEqual(state["start"], (200.0, 0.0))
        self.assertEqual(state["end"], (300.0, 0.0))
        rect = item.sceneBoundingRect()
        self.assertAlmostEqual(rect.left(), 200.0, delta=2.0)
        self.assertAlmostEqual(rect.right(), 300.0, delta=2.0)

    def test_a_drag_shorter_than_a_tenth_of_a_bond_length_is_refused(self) -> None:
        item = self._add("arrow", QPointF(0.0, 0.0), QPointF(40.0, 0.0))
        controller = self._handles().handle_controller
        self._handles().handle_overlay_service.show_endpoint_handles(item)
        handle = active_handles_for(self.canvas)[1]

        # 1.0 is inside the 0.1 x 20 px floor even though it is not the anchor.
        controller.update_handle_drag(handle, QPointF(1.0, 0.0))
        self.assertEqual(arrow_state_dict(item)["end"], (40.0, 0.0))

        controller.update_handle_drag(handle, QPointF(6.0, 0.0))
        self.assertEqual(arrow_state_dict(item)["end"], (6.0, 0.0))

    def test_undo_of_a_handle_drag_clears_the_stale_handles(self) -> None:
        item = self._add("line", QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        item.setSelected(True)
        self.app.processEvents()
        self._click(QPointF(0.0, 0.0))
        self.assertEqual(len(active_handles_for(self.canvas)), 2)
        controller = self._handles().handle_controller
        before = arrow_state_dict(item)
        controller.update_handle_drag(
            active_handles_for(self.canvas)[1], QPointF(90.0, 0.0)
        )
        after = arrow_state_dict(item)
        history = self.canvas.runtime_state.history_service
        history.push(UpdateSceneItemCommand(item, before, after))

        history.undo()

        self.assertEqual(arrow_state_dict(item)["end"], (40.0, 0.0))
        self.assertEqual(active_handles_for(self.canvas), [])
        self.assertIsNone(handle_target_for(self.canvas))

    def test_clicking_a_selected_curved_arrow_shows_its_control_handle(self) -> None:
        item = self._add("curved_single", QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        item.setSelected(True)
        self.app.processEvents()

        # Click the curve itself, not the empty midpoint of its chord.
        self._click(QPointF(0.0, 12.0))

        self.assertEqual(
            _handle_types(self.canvas),
            ["curved_start", "curved_control", "curved_end"],
        )

    def test_dragging_a_selected_arrow_moves_it_instead_of_toggling_handles(
        self,
    ) -> None:
        item = self._add("line", QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        item.setSelected(True)
        self.app.processEvents()
        start_pos = self.canvas.mapFromScene(QPointF(0.0, 0.0))
        end_pos = self.canvas.mapFromScene(QPointF(0.0, 50.0))

        QTest.mousePress(
            self.canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            start_pos,
        )
        self.app.processEvents()
        QTest.mouseMove(self.canvas.viewport(), end_pos)
        self.app.processEvents()
        QTest.mouseRelease(
            self.canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            end_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

        state = arrow_state_dict(item)
        self.assertAlmostEqual(state["start"][1], 50.0, delta=1.0)
        self.assertEqual(active_handles_for(self.canvas), [])

    def test_a_handle_press_without_movement_pushes_no_history(self) -> None:
        item = self._add("line", QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        item.setSelected(True)
        self.app.processEvents()
        self._click(QPointF(0.0, 0.0))
        handle_pos = self.canvas.mapFromScene(
            active_handles_for(self.canvas)[1].sceneBoundingRect().center()
        )
        history = self.canvas.runtime_state.history_service
        depth_before = len(history.state.history)

        QTest.mousePress(
            self.canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            handle_pos,
        )
        QTest.mouseRelease(
            self.canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            handle_pos,
        )
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(len(history.state.history), depth_before)
        self.assertEqual(arrow_state_dict(item)["end"], (40.0, 0.0))
