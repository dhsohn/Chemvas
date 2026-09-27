import os
import unittest
from unittest import mock

from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.domain.document import (
    VALID_ARROW_KINDS,
    VALID_CURVED_ARROW_KINDS,
)
from chemvas.ui.annotations.state import arrow_state_dict_for
from chemvas.ui.history.history_commands import UpdateSceneItemCommand
from chemvas.ui.tools.endpoint_snap_access import arrow_endpoints_for
from tests.canvas_factory import build_canvas_view


def _handle_types(canvas) -> list[str]:
    return [
        handle.data(1) for handle in canvas.runtime_state.handle_state.active_handles
    ]


class EndpointHandleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.canvas = build_canvas_view()
        self.canvas.resize(800, 600)
        self.canvas.show()
        self.canvas.setFocus()
        self.canvas.services.tool_mode_controller.set_tool("select")
        self.app.processEvents()

    def tearDown(self) -> None:
        self.canvas.close()
        self.app.processEvents()

    def _handles(self):
        return self.canvas.services

    def _add(self, kind: str, start: QPointF, end: QPointF):
        return self.canvas.services.scene_decoration_service.add_arrow(start, end, kind)

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

    def test_every_non_curved_arrow_kind_gets_two_endpoint_handles(self) -> None:
        overlay = self._handles().handle_overlay_service
        for kind in sorted(VALID_ARROW_KINDS - VALID_CURVED_ARROW_KINDS):
            item = self._add(kind, QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
            overlay.show_endpoint_handles(item)
            self.assertEqual(
                _handle_types(self.canvas), ["arrow_start", "arrow_end"], kind
            )
            self.assertIs(self.canvas.runtime_state.handle_state.target, item, kind)
            positions = [
                handle.sceneBoundingRect().center()
                for handle in self.canvas.runtime_state.handle_state.active_handles
            ]
            self.assertAlmostEqual(positions[0].x(), -40.0, places=6, msg=kind)
            self.assertAlmostEqual(positions[1].x(), 40.0, places=6, msg=kind)
            self._handles().handle_overlay_service.clear_handles()
            self.canvas.services.scene_item_controller.remove_scene_item(item)

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
        end_handle = self.canvas.runtime_state.handle_state.active_handles[1]

        controller.update_handle_drag(
            end_handle, QPointF(60.0, 30.0), arrow_state_dict_for(self.canvas, item)
        )

        state = arrow_state_dict_for(self.canvas, item)
        self.assertEqual(state["start"], (-40.0, 0.0))
        self.assertEqual(state["end"], (60.0, 30.0))
        # The handles follow the change, so a second drag starts from the new end.
        positions = [
            handle.sceneBoundingRect().center()
            for handle in self.canvas.runtime_state.handle_state.active_handles
        ]
        self.assertAlmostEqual(positions[1].x(), 60.0, places=6)
        self.assertAlmostEqual(positions[1].y(), 30.0, places=6)

    def test_dragging_an_endpoint_snaps_to_another_item_but_not_to_itself(self) -> None:
        level = self._add("line_bold", QPointF(-60.0, 0.0), QPointF(-20.0, 0.0))
        connector = self._add("line_dashed", QPointF(40.0, 40.0), QPointF(80.0, 40.0))
        controller = self._handles().handle_controller
        self._handles().handle_overlay_service.show_endpoint_handles(connector)
        start_handle = self.canvas.runtime_state.handle_state.active_handles[0]

        controller.update_handle_drag(
            start_handle,
            QPointF(-18.0, 2.0),
            arrow_state_dict_for(self.canvas, connector),
        )

        self.assertEqual(
            arrow_state_dict_for(self.canvas, connector)["start"], (-20.0, 0.0)
        )
        self.assertEqual(arrow_state_dict_for(self.canvas, level)["end"], (-20.0, 0.0))
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
            self.canvas.runtime_state.handle_state.active_handles[1],
            QPointF(5.0, 0.0),
            arrow_state_dict_for(self.canvas, item),
        )

        self.assertEqual(arrow_state_dict_for(self.canvas, item)["end"], (5.0, 0.0))

    def test_a_curved_endpoint_takes_another_items_endpoint(self) -> None:
        # A curved arrow's ends carry the same kind of handle, so they snap the
        # same way; they used to copy the raw cursor instead.
        self._add("line_bold", QPointF(-60.0, 0.0), QPointF(-20.0, 0.0))
        curved = self._add("curved_single", QPointF(40.0, 40.0), QPointF(100.0, 40.0))
        controller = self._handles().handle_controller
        self._handles().handle_overlay_service.show_curved_handles(curved)

        controller.update_handle_drag(
            self.canvas.runtime_state.handle_state.active_handles[0],
            QPointF(-18.0, 2.0),
            arrow_state_dict_for(self.canvas, curved),
        )

        state = arrow_state_dict_for(self.canvas, curved)
        self.assertEqual(state["start"], (-20.0, 0.0))
        self.assertEqual(state["end"], (100.0, 40.0))

    def test_a_curved_end_can_be_dragged_close_to_its_own_start(self) -> None:
        # A curved arrow's own ends are not snap candidates either, so a
        # short curve stays draggable instead of collapsing onto its start.
        curved = self._add("curved_single", QPointF(0.0, 0.0), QPointF(40.0, 0.0))
        controller = self._handles().handle_controller
        self._handles().handle_overlay_service.show_curved_handles(curved)

        controller.update_handle_drag(
            self.canvas.runtime_state.handle_state.active_handles[2],
            QPointF(5.0, 0.0),
            arrow_state_dict_for(self.canvas, curved),
        )

        self.assertEqual(arrow_state_dict_for(self.canvas, curved)["end"], (5.0, 0.0))

    def test_a_curved_drag_onto_the_other_end_is_refused(self) -> None:
        curved = self._add("curved_single", QPointF(0.0, 0.0), QPointF(40.0, 0.0))
        controller = self._handles().handle_controller
        self._handles().handle_overlay_service.show_curved_handles(curved)

        controller.update_handle_drag(
            self.canvas.runtime_state.handle_state.active_handles[0],
            QPointF(40.0, 0.0),
            arrow_state_dict_for(self.canvas, curved),
        )

        self.assertEqual(arrow_state_dict_for(self.canvas, curved)["start"], (0.0, 0.0))

    def test_an_arc_keeps_its_sweep_and_its_label_follows(self) -> None:
        item = self._add("arc_90_left", QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        service = self.canvas.services.scene_decoration_service
        service.set_arrow_labels(item, {"above": "k_1"})
        before_elements = item.path().elementCount()
        label = next(
            child for child in item.childItems() if child.data(0) == "arrow_label"
        )
        before_label_x = label.sceneBoundingRect().center().x()
        controller = self._handles().handle_controller
        self._handles().handle_overlay_service.show_endpoint_handles(item)

        controller.update_handle_drag(
            self.canvas.runtime_state.handle_state.active_handles[1],
            QPointF(120.0, 0.0),
            arrow_state_dict_for(self.canvas, item),
        )

        state = arrow_state_dict_for(self.canvas, item)
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
        handle = self.canvas.runtime_state.handle_state.active_handles[1]
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

        self.assertEqual(arrow_state_dict_for(self.canvas, item)["end"], (90.0, 25.0))
        self.assertEqual(len(history.state.history), depth_before + 1)
        history.undo()
        self.assertEqual(arrow_state_dict_for(self.canvas, item)["end"], (40.0, 0.0))
        history.redo()
        self.assertEqual(arrow_state_dict_for(self.canvas, item)["end"], (90.0, 25.0))

    def test_deleting_a_handled_arrow_clears_its_handles(self) -> None:
        item = self._add("arrow", QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        self._handles().handle_overlay_service.show_endpoint_handles(item)
        self.assertIs(self.canvas.runtime_state.handle_state.target, item)

        self.canvas.services.scene_item_controller.remove_scene_item(item)

        self.assertEqual(self.canvas.runtime_state.handle_state.active_handles, [])
        self.assertIsNone(self.canvas.runtime_state.handle_state.target)
        self.assertEqual(self.canvas.runtime_state.arrow_items(), [])

    def test_switching_tools_clears_the_handles(self) -> None:
        item = self._add("arrow", QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        self._handles().handle_overlay_service.show_endpoint_handles(item)

        self.canvas.services.tool_mode_controller.set_tool("bond")
        self.app.processEvents()

        self.assertEqual(self.canvas.runtime_state.handle_state.active_handles, [])

    def test_endpoint_mutation_requires_a_record_and_ignores_bad_endpoint_names(
        self,
    ) -> None:
        mutation = self._handles().handle_mutation_service
        good = self._add("arrow", QPointF(0.0, 0.0), QPointF(40.0, 0.0))
        blank = self._add("arrow", QPointF(0.0, 60.0), QPointF(40.0, 60.0))
        pressed = self.canvas.render_context.arrows.record(blank)
        self.canvas.runtime_state.arrow_state.records.pop(blank.data(3))

        with mock.patch.object(blank, "setPath") as blank_path:
            with self.assertRaisesRegex(RuntimeError, "no record"):
                mutation.update_arrow_endpoint(
                    blank, QPointF(10.0, 10.0), "start", pressed=pressed
                )
        blank_path.assert_not_called()
        self.canvas.services.scene_item_controller.remove_scene_item(blank)

        with mock.patch.object(good, "setPath") as good_path:
            mutation.update_arrow_endpoint(
                good,
                QPointF(10.0, 10.0),
                "sideways",
                pressed=self.canvas.render_context.arrows.record(good),
            )
        good_path.assert_not_called()
        self.assertEqual(arrow_state_dict_for(self.canvas, good)["end"], (40.0, 0.0))

    def test_dragging_an_endpoint_of_a_moved_arrow_stays_aligned(self) -> None:
        # A moved item carries its offset in pos() while its geometry stays
        # absolute; rebuilding the path without clearing that offset drew the
        # arrow one move-delta away from its own handles.
        item = self._add("arrow", QPointF(0.0, 0.0), QPointF(40.0, 0.0))
        self.canvas.services.move_controller.move_item(item, 200.0, 0.0)
        controller = self._handles().handle_controller
        self._handles().handle_overlay_service.show_endpoint_handles(item)

        controller.update_handle_drag(
            self.canvas.runtime_state.handle_state.active_handles[1],
            QPointF(300.0, 0.0),
            arrow_state_dict_for(self.canvas, item),
        )

        state = arrow_state_dict_for(self.canvas, item)
        self.assertEqual(state["start"], (200.0, 0.0))
        self.assertEqual(state["end"], (300.0, 0.0))
        rect = item.sceneBoundingRect()
        self.assertAlmostEqual(rect.left(), 200.0, delta=2.0)
        self.assertAlmostEqual(rect.right(), 300.0, delta=2.0)

    def test_a_drag_shorter_than_a_tenth_of_a_bond_length_is_refused(self) -> None:
        item = self._add("arrow", QPointF(0.0, 0.0), QPointF(40.0, 0.0))
        controller = self._handles().handle_controller
        self._handles().handle_overlay_service.show_endpoint_handles(item)
        handle = self.canvas.runtime_state.handle_state.active_handles[1]

        pressed = arrow_state_dict_for(self.canvas, item)

        # 1.0 is inside the 0.1 x 20 px floor even though it is not the anchor.
        controller.update_handle_drag(handle, QPointF(1.0, 0.0), pressed)
        self.assertEqual(arrow_state_dict_for(self.canvas, item)["end"], (40.0, 0.0))

        controller.update_handle_drag(handle, QPointF(6.0, 0.0), pressed)
        self.assertEqual(arrow_state_dict_for(self.canvas, item)["end"], (6.0, 0.0))

    def test_an_arrow_shorter_than_the_floor_can_be_dragged_back(self) -> None:
        # A file can hold an arrow shorter than a tenth of a bond length. Its
        # own length at the press is its floor, so its end still returns to
        # where it was but comes no closer to the other end.
        for kind, handle_index in (("arrow", 1), ("curved_single", 2)):
            with self.subTest(kind=kind):
                item = self._add(kind, QPointF(0.0, 0.0), QPointF(0.5, 0.0))
                controller = self._handles().handle_controller
                if kind == "arrow":
                    self._handles().handle_overlay_service.show_endpoint_handles(item)
                else:
                    self._handles().handle_overlay_service.show_curved_handles(item)
                handle = self.canvas.runtime_state.handle_state.active_handles[
                    handle_index
                ]
                pressed = arrow_state_dict_for(self.canvas, item)

                for x in (10.0, 100.0, 3.0):
                    controller.update_handle_drag(handle, QPointF(x, 0.0), pressed)
                self.assertEqual(
                    arrow_state_dict_for(self.canvas, item)["end"], (3.0, 0.0)
                )

                controller.update_handle_drag(handle, QPointF(0.2, 0.0), pressed)
                self.assertEqual(
                    arrow_state_dict_for(self.canvas, item)["end"], (3.0, 0.0)
                )

                controller.update_handle_drag(handle, QPointF(0.5, 0.0), pressed)
                self.assertEqual(arrow_state_dict_for(self.canvas, item), pressed)
                self._handles().handle_overlay_service.clear_handles()
                self.canvas.services.scene_item_controller.remove_scene_item(item)

    def test_undo_of_a_handle_drag_clears_the_stale_handles(self) -> None:
        item = self._add("line", QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        item.setSelected(True)
        self.app.processEvents()
        self._click(QPointF(0.0, 0.0))
        self.assertEqual(len(self.canvas.runtime_state.handle_state.active_handles), 2)
        controller = self._handles().handle_controller
        before = arrow_state_dict_for(self.canvas, item)
        controller.update_handle_drag(
            self.canvas.runtime_state.handle_state.active_handles[1],
            QPointF(90.0, 0.0),
            before,
        )
        after = arrow_state_dict_for(self.canvas, item)
        history = self.canvas.runtime_state.history_service
        history.push(
            UpdateSceneItemCommand(require_scene_record_id(item), before, after)
        )

        history.undo()

        self.assertEqual(arrow_state_dict_for(self.canvas, item)["end"], (40.0, 0.0))
        self.assertEqual(self.canvas.runtime_state.handle_state.active_handles, [])
        self.assertIsNone(self.canvas.runtime_state.handle_state.target)

    def _show_curved_handles_by_clicking(self, item) -> None:
        item.setSelected(True)
        self.app.processEvents()
        self._click(item.path().pointAtPercent(0.5))
        self.assertIs(self.canvas.runtime_state.handle_state.target, item)

    def _drag_handle(self, handle_type: str, through: list[QPointF], *, back: bool):
        handle = next(
            handle
            for handle in self.canvas.runtime_state.handle_state.active_handles
            if handle.data(1) == handle_type
        )
        viewport = self.canvas.viewport()
        press = self.canvas.mapFromScene(handle.sceneBoundingRect().center())
        QTest.mousePress(
            viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, press
        )
        release = press
        for point in through:
            release = self.canvas.mapFromScene(point)
            QTest.mouseMove(viewport, release)
            self.app.processEvents()
        if back:
            release = press
            QTest.mouseMove(viewport, release)
            self.app.processEvents()
        QTest.mouseRelease(
            viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, release
        )
        self.app.processEvents()

    def test_a_curved_end_dragged_away_and_back_leaves_no_edit(self) -> None:
        # Every frame starts from the press, so shrinking the chord (which
        # used to clip the bulge for good) and turning it both come back.
        item = self._add("curved_single", QPointF(-100.0, 0.0), QPointF(100.0, 0.0))
        before = arrow_state_dict_for(self.canvas, item)
        self._show_curved_handles_by_clicking(item)
        history = self.canvas.runtime_state.history_service
        depth = len(history.state.history)

        self._drag_handle(
            "curved_end",
            [QPointF(-80.0, 0.0), QPointF(-100.0, 150.0), QPointF(60.0, -40.0)],
            back=True,
        )

        self.assertEqual(arrow_state_dict_for(self.canvas, item), before)
        self.assertEqual(len(history.state.history), depth)

    def test_a_curved_end_drag_turns_and_scales_the_curve_with_its_chord(
        self,
    ) -> None:
        item = self._add("curved_single", QPointF(-100.0, 0.0), QPointF(100.0, 0.0))
        before = arrow_state_dict_for(self.canvas, item)
        self.assertEqual(before["control"], (0.0, 60.0))
        self._show_curved_handles_by_clicking(item)
        history = self.canvas.runtime_state.history_service
        depth = len(history.state.history)

        # A quarter turn about the start at half the length: the bulge turns
        # and halves with the chord instead of being re-fitted to it.
        self._drag_handle(
            "curved_end",
            [QPointF(-60.0, 0.0), QPointF(40.0, 80.0), QPointF(-100.0, 100.0)],
            back=False,
        )

        after = arrow_state_dict_for(self.canvas, item)
        self.assertEqual(after["start"], (-100.0, 0.0))
        self.assertEqual(after["end"], (-100.0, 100.0))
        self.assertEqual(after["control"], (-130.0, 50.0))
        self.assertEqual(len(history.state.history), depth + 1)
        history.undo()
        self.assertEqual(arrow_state_dict_for(self.canvas, item), before)
        history.redo()
        self.assertEqual(arrow_state_dict_for(self.canvas, item), after)

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

        state = arrow_state_dict_for(self.canvas, item)
        self.assertAlmostEqual(state["start"][1], 50.0, delta=1.0)
        self.assertEqual(self.canvas.runtime_state.handle_state.active_handles, [])

    def test_a_handle_press_without_movement_pushes_no_history(self) -> None:
        item = self._add("line", QPointF(-40.0, 0.0), QPointF(40.0, 0.0))
        item.setSelected(True)
        self.app.processEvents()
        self._click(QPointF(0.0, 0.0))
        handle_pos = self.canvas.mapFromScene(
            self.canvas.runtime_state.handle_state.active_handles[1]
            .sceneBoundingRect()
            .center()
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

        self.assertEqual(len(history.state.history), depth_before)
        self.assertEqual(arrow_state_dict_for(self.canvas, item)["end"], (40.0, 0.0))
