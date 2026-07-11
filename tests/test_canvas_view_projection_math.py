import math
import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QPen, QPolygonF
    from PyQt6.QtWidgets import QApplication, QGraphicsPolygonItem
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.history import (
        CompositeCommand,
        HistoryTransactionRestoreResult,
        SetAtomPositionsCommand,
        SetRingPolygonsCommand,
        UpdateBondLengthCommand,
    )
    from core.model import Atom, Bond
    from ui.atom_coords_access import (
        atom_coords_3d_for,
        current_atom_coords_3d_for,
        set_atom_coords_3d_for,
    )
    from ui.bond_graphics_access import (
        add_bond_graphics_for,
        apply_color_to_bond_item_for,
        bond_offset_unit_3d_for,
        dotted_bond_path_for,
        draw_dotted_bond_for,
        draw_hash_bond_for,
        draw_parallel_bonds_for,
        draw_ring_double_bond_for,
        draw_wedge_bond_for,
        hash_segments_for,
        line_normal_components,
        line_normal_for,
        one_sided_bond_strip_for,
        orient_normal_toward_target,
        parallel_bond_segments_for,
        project_point_3d_for,
        ring_double_segments_for,
        strip_polygon_for,
        wedge_polygon_for,
    )
    from ui.bond_renderer import bond_renderer_for
    from ui.canvas_atom_graphics_state import (
        atom_dots_for,
        atom_items_for,
        set_atom_dots_for,
        set_atom_items_for,
    )
    from ui.canvas_bond_graphics_state import bond_items_for_id
    from ui.canvas_geometry_controller import CanvasGeometryController
    from ui.canvas_graph_service import CanvasGraphService
    from ui.canvas_graph_state import CanvasGraphState
    from ui.canvas_mark_registry import CanvasMarkRegistry
    from ui.canvas_move_controller import CanvasMoveController
    from ui.canvas_rotation_state import CanvasRotationState
    from ui.canvas_scene_items_state import (
        ring_items_for,
        set_scene_item_collection_for,
    )
    from ui.canvas_view import CanvasView
    from ui.graphics_items import AtomLabelItem
    from ui.history_commands import UpdateSceneItemCommand
    from ui.renderer_style_access import bond_length_px_for
    from ui.selection_rotation_access import (
        apply_projected_atom_positions_for,
        atom_in_planar_system_for,
        average_bond_length_for_atoms_for,
        bond_ids_for_atom_ids_for,
        bond_ids_within_atom_ids_for,
        bond_is_planar_fragment_edge_for,
        center_for_coords_3d,
        flatten_planar_fragments_for,
        fragment_plane_normal_for,
        normalize_3d,
        planar_fragment_components_for,
        rotate_point_around_axis_for,
        rotation_scale_for_coords_for,
        unproject_scene_point_3d_for,
    )
    from ui.structure_mutation_access import add_atom_for, add_bond_for


class _FakeRingItem:
    def __init__(self, points) -> None:
        self._polygon = QPolygonF([QPointF(x, y) for x, y in points])

    def polygon(self):
        return QPolygonF(self._polygon)

    def setPolygon(self, polygon) -> None:
        self._polygon = QPolygonF(polygon)


class _FakeDot:
    def __init__(self) -> None:
        self.positions = []

    def setPos(self, x: float, y: float) -> None:
        self.positions.append((x, y))


class _FakeMark:
    def __init__(self, payload) -> None:
        self._payload = payload

    def data(self, key):
        if key == 1:
            return self._payload
        return None


class _FakePen:
    def __init__(self) -> None:
        self.color = None

    def setColor(self, color) -> None:
        self.color = color


class _FakeBrush:
    def __init__(self, style) -> None:
        self._style = style

    def style(self):
        return self._style


class _FakePenBrushItem:
    def __init__(self, brush_style) -> None:
        self._pen = _FakePen()
        self._brush = _FakeBrush(brush_style)
        self.pen_updates = []
        self.brush_updates = []

    def pen(self):
        return self._pen

    def setPen(self, pen) -> None:
        self.pen_updates.append(pen)

    def brush(self):
        return self._brush

    def setBrush(self, color) -> None:
        self.brush_updates.append(color)


class _FakeBrushOnlyItem:
    def __init__(self, brush_style) -> None:
        self._brush = _FakeBrush(brush_style)
        self.brush_updates = []

    def brush(self):
        return self._brush

    def setBrush(self, color) -> None:
        self.brush_updates.append(color)


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewProjectionMathTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _real_bond_length_canvas(self):
        canvas = CanvasView()

        def close_canvas(target=canvas) -> None:
            target.services.canvas_scene_reset_service.clear_scene()
            target.close()

        self.addCleanup(close_canvas)
        label_atom_id = add_atom_for(canvas, "N", 0.0, 0.0)
        dot_atom_id = add_atom_for(canvas, "C", 20.0, 0.0)
        bond_id = add_bond_for(canvas, label_atom_id, dot_atom_id)
        add_bond_graphics_for(canvas, bond_id)
        return canvas, label_atom_id, dot_atom_id, bond_id

    def test_bond_length_history_preserves_graphics_selection_and_prior_item_command(self) -> None:
        canvas, label_atom_id, dot_atom_id, bond_id = self._real_bond_length_canvas()
        label_item = atom_items_for(canvas)[label_atom_id]
        dot_item = atom_dots_for(canvas)[dot_atom_id]
        bond_item = bond_items_for_id(canvas, bond_id)[0]
        original_ids = (id(label_item), id(dot_item), id(bond_item))
        original_font_size = label_item.font().pointSizeF()
        original_dot_hit_width = dot_item.boundingRect().width()
        original_pen_width = bond_item.pen().widthF()
        for item in (label_item, dot_item, bond_item):
            item.setSelected(True)

        prior_command = UpdateSceneItemCommand(
            item=bond_item,
            before_state={"opacity": 1.0},
            after_state={"opacity": 0.4},
        )
        bond_item.setOpacity(0.4)
        canvas.services.history_service.push(prior_command)

        canvas.services.geometry_controller.set_bond_length(30.0)

        self.assertEqual(
            (
                id(atom_items_for(canvas)[label_atom_id]),
                id(atom_dots_for(canvas)[dot_atom_id]),
                id(bond_items_for_id(canvas, bond_id)[0]),
            ),
            original_ids,
        )
        self.assertGreater(label_item.font().pointSizeF(), original_font_size)
        self.assertGreater(dot_item.boundingRect().width(), original_dot_hit_width)
        self.assertGreater(bond_item.pen().widthF(), original_pen_width)
        self.assertTrue(all(item.isSelected() for item in (label_item, dot_item, bond_item)))

        canvas.services.history_service.undo()

        self.assertEqual(bond_length_px_for(canvas), 20.0)
        self.assertEqual(
            (
                id(atom_items_for(canvas)[label_atom_id]),
                id(atom_dots_for(canvas)[dot_atom_id]),
                id(bond_items_for_id(canvas, bond_id)[0]),
            ),
            original_ids,
        )
        self.assertEqual(label_item.font().pointSizeF(), original_font_size)
        self.assertEqual(dot_item.boundingRect().width(), original_dot_hit_width)
        self.assertEqual(bond_item.pen().widthF(), original_pen_width)
        self.assertTrue(all(item.isSelected() for item in (label_item, dot_item, bond_item)))

        with mock.patch(
            "ui.history_commands._apply_scene_item_state",
            side_effect=lambda _canvas, item, state: item.setOpacity(state["opacity"]),
        ):
            canvas.services.history_service.undo()

        self.assertIs(prior_command.item, bond_items_for_id(canvas, bond_id)[0])
        self.assertEqual(bond_item.opacity(), 1.0)

    def test_set_bond_length_rejects_noop_forward_graphics_setters(self) -> None:
        cases = (
            ("bond pen", "setPen", "bond graphics pen"),
            ("atom font", "setFont", "atom-label font"),
            ("atom dot position", "setPos", "atom-dot position"),
        )
        for target_name, setter_name, expected_error in cases:
            with self.subTest(target=target_name):
                canvas, label_atom_id, dot_atom_id, bond_id = (
                    self._real_bond_length_canvas()
                )
                label_item = atom_items_for(canvas)[label_atom_id]
                dot_item = atom_dots_for(canvas)[dot_atom_id]
                bond_item = bond_items_for_id(canvas, bond_id)[0]
                original_style = canvas.renderer.style
                original_font = label_item.font()
                original_dot_rect = dot_item.rect()
                original_pen = bond_item.pen()
                target = {
                    "bond pen": bond_item,
                    "atom font": label_item,
                    "atom dot position": dot_item,
                }[target_name]

                with mock.patch.object(
                    type(target),
                    setter_name,
                    lambda _item, _value: None,
                ):
                    with self.assertRaisesRegex(RuntimeError, expected_error):
                        canvas.services.geometry_controller.set_bond_length(40.0)

                self.assertIs(canvas.renderer.style, original_style)
                self.assertEqual(bond_length_px_for(canvas), 20.0)
                self.assertEqual(label_item.font(), original_font)
                self.assertEqual(dot_item.rect(), original_dot_rect)
                self.assertEqual(bond_item.pen(), original_pen)
                self.assertFalse(canvas.services.history_service.can_undo())

    def test_bond_length_command_fail_once_restores_metrics_identity_and_selection(self) -> None:
        canvas, label_atom_id, dot_atom_id, bond_id = self._real_bond_length_canvas()
        canvas.services.geometry_controller.set_bond_length(30.0)
        canvas.services.history_service.clear()
        label_item = atom_items_for(canvas)[label_atom_id]
        dot_item = atom_dots_for(canvas)[dot_atom_id]
        bond_item = bond_items_for_id(canvas, bond_id)[0]
        for item in (label_item, dot_item, bond_item):
            item.setSelected(True)
        original_ids = (id(label_item), id(dot_item), id(bond_item))
        original_metrics = (
            label_item.font().pointSizeF(),
            dot_item.boundingRect().width(),
            bond_item.pen().widthF(),
            bond_item.line(),
        )
        update_calls = 0
        original_update = canvas.bond_renderer.update_bond_geometry

        def fail_once_after_update(_canvas, target_bond_id: int) -> None:
            nonlocal update_calls
            original_update(target_bond_id)
            update_calls += 1
            if update_calls == 1:
                raise RuntimeError("injected in-place refresh failure")

        command = UpdateBondLengthCommand(before_length=20.0, after_length=30.0)
        with mock.patch(
            "ui.bond_length_graphics_refresh.update_bond_geometry_for",
            side_effect=fail_once_after_update,
        ):
            with self.assertRaisesRegex(RuntimeError, "in-place refresh failure"):
                command.undo(canvas)

        self.assertEqual(bond_length_px_for(canvas), 30.0)
        self.assertEqual(
            (
                id(atom_items_for(canvas)[label_atom_id]),
                id(atom_dots_for(canvas)[dot_atom_id]),
                id(bond_items_for_id(canvas, bond_id)[0]),
            ),
            original_ids,
        )
        self.assertEqual(
            (
                label_item.font().pointSizeF(),
                dot_item.boundingRect().width(),
                bond_item.pen().widthF(),
                bond_item.line(),
            ),
            original_metrics,
        )
        self.assertTrue(all(item.isSelected() for item in (label_item, dot_item, bond_item)))

    def test_set_bond_length_fail_once_rolls_back_model_metrics_and_history(self) -> None:
        canvas, label_atom_id, dot_atom_id, bond_id = self._real_bond_length_canvas()
        label_item = atom_items_for(canvas)[label_atom_id]
        dot_item = atom_dots_for(canvas)[dot_atom_id]
        bond_item = bond_items_for_id(canvas, bond_id)[0]
        for item in (label_item, dot_item, bond_item):
            item.setSelected(True)
        original_ids = (id(label_item), id(dot_item), id(bond_item))
        original_positions = {
            atom_id: (atom.x, atom.y) for atom_id, atom in canvas.model.atoms.items()
        }
        original_metrics = (
            label_item.font().pointSizeF(),
            dot_item.boundingRect().width(),
            bond_item.pen().widthF(),
            bond_item.line(),
        )
        update_calls = 0
        original_update = canvas.bond_renderer.update_bond_geometry

        def fail_once_after_update(_canvas, target_bond_id: int) -> None:
            nonlocal update_calls
            original_update(target_bond_id)
            update_calls += 1
            if update_calls == 1:
                raise RuntimeError("injected initial refresh failure")

        with mock.patch(
            "ui.bond_length_graphics_refresh.update_bond_geometry_for",
            side_effect=fail_once_after_update,
        ):
            with self.assertRaisesRegex(RuntimeError, "initial refresh failure"):
                canvas.services.geometry_controller.set_bond_length(30.0)

        self.assertEqual(bond_length_px_for(canvas), 20.0)
        self.assertEqual(
            {atom_id: (atom.x, atom.y) for atom_id, atom in canvas.model.atoms.items()},
            original_positions,
        )
        self.assertEqual(
            (
                id(atom_items_for(canvas)[label_atom_id]),
                id(atom_dots_for(canvas)[dot_atom_id]),
                id(bond_items_for_id(canvas, bond_id)[0]),
            ),
            original_ids,
        )
        self.assertEqual(
            (
                label_item.font().pointSizeF(),
                dot_item.boundingRect().width(),
                bond_item.pen().widthF(),
                bond_item.line(),
            ),
            original_metrics,
        )
        self.assertTrue(all(item.isSelected() for item in (label_item, dot_item, bond_item)))
        self.assertFalse(canvas.services.history_service.can_undo())

    def test_set_bond_length_live_pen_port_failure_rolls_back_all_primitives(self) -> None:
        for failure_port in ("pen", "setPen"):
            with self.subTest(failure_port=failure_port):
                canvas, _label_atom_id, _dot_atom_id, bond_id = (
                    self._real_bond_length_canvas()
                )
                bond_item = bond_items_for_id(canvas, bond_id)[0]

                class FailingPenItem:
                    def __init__(self, initial_pen, *, failure_port: str) -> None:
                        self._pen = QPen(initial_pen)
                        self._pos = QPointF()
                        self.failure_port = failure_port
                        self.pen_port_reads = 0
                        self.setter_port_reads = 0

                    @property
                    def pen(self):
                        self.pen_port_reads += 1
                        if self.failure_port == "pen" and self.pen_port_reads == 2:
                            raise AttributeError("live pen descriptor failed")
                        return self._get_pen

                    def _get_pen(self):
                        return QPen(self._pen)

                    @property
                    def setPen(self):
                        self.setter_port_reads += 1
                        if (
                            self.failure_port == "setPen"
                            and self.setter_port_reads == 2
                        ):
                            raise AttributeError("live setPen descriptor failed")
                        return self._set_pen

                    def _set_pen(self, pen) -> None:
                        self._pen = QPen(pen)

                    def pos(self):
                        return QPointF(self._pos)

                    def setPos(self, *args) -> None:
                        self._pos = QPointF(*args)

                failing_item = FailingPenItem(
                    bond_item.pen(),
                    failure_port=failure_port,
                )
                bond_items_for_id(canvas, bond_id).append(failing_item)
                original_positions = {
                    atom_id: (atom.x, atom.y)
                    for atom_id, atom in canvas.model.atoms.items()
                }
                original_real_pen = QPen(bond_item.pen())
                original_failing_pen = failing_item._get_pen()

                with self.assertRaisesRegex(
                    AttributeError,
                    rf"live {failure_port} descriptor failed",
                ):
                    canvas.services.geometry_controller.set_bond_length(30.0)

                self.assertEqual(bond_length_px_for(canvas), 20.0)
                self.assertEqual(
                    {
                        atom_id: (atom.x, atom.y)
                        for atom_id, atom in canvas.model.atoms.items()
                    },
                    original_positions,
                )
                self.assertEqual(bond_item.pen(), original_real_pen)
                self.assertEqual(failing_item._get_pen(), original_failing_pen)
                self.assertGreaterEqual(failing_item.pen_port_reads, 2)
                self.assertGreaterEqual(failing_item.setter_port_reads, 1)
                self.assertFalse(canvas.services.history_service.can_undo())

    def test_set_bond_length_persistent_pre_update_failure_restores_raw_bond_geometry(self) -> None:
        canvas, label_atom_id, dot_atom_id, bond_id = self._real_bond_length_canvas()
        label_item = atom_items_for(canvas)[label_atom_id]
        dot_item = atom_dots_for(canvas)[dot_atom_id]
        bond_item = bond_items_for_id(canvas, bond_id)[0]
        for item in (label_item, dot_item, bond_item):
            item.setSelected(True)
        original_style = canvas.renderer.style
        original_positions = {
            atom_id: (atom.x, atom.y) for atom_id, atom in canvas.model.atoms.items()
        }
        original_metrics = (
            label_item.font(),
            dot_item.rect(),
            dot_item.boundingRect(),
            bond_item.pen(),
            bond_item.line(),
        )

        with mock.patch(
            "ui.bond_length_graphics_refresh.update_bond_geometry_for",
            side_effect=RuntimeError("persistent geometry callback failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "persistent geometry"):
                canvas.services.geometry_controller.set_bond_length(30.0)

        self.assertIs(canvas.renderer.style, original_style)
        self.assertEqual(bond_length_px_for(canvas), 20.0)
        self.assertEqual(
            {atom_id: (atom.x, atom.y) for atom_id, atom in canvas.model.atoms.items()},
            original_positions,
        )
        self.assertEqual(
            (
                label_item.font(),
                dot_item.rect(),
                dot_item.boundingRect(),
                bond_item.pen(),
                bond_item.line(),
            ),
            original_metrics,
        )
        self.assertIs(atom_items_for(canvas)[label_atom_id], label_item)
        self.assertIs(atom_dots_for(canvas)[dot_atom_id], dot_item)
        self.assertIs(bond_items_for_id(canvas, bond_id)[0], bond_item)
        self.assertTrue(all(item.isSelected() for item in (label_item, dot_item, bond_item)))
        self.assertFalse(canvas.services.history_service.can_undo())

    def test_set_bond_length_keeps_rollback_control_flow_failure_as_note(self) -> None:
        canvas, _label_atom_id, _dot_atom_id, _bond_id = self._real_bond_length_canvas()
        original_style = canvas.renderer.style
        original_error = RuntimeError("initial bond-length refresh failed")
        rollback_error = SystemExit("rollback refresh terminated")

        with mock.patch(
            "ui.canvas_geometry_controller.refresh_bond_length_graphics_for",
            side_effect=[original_error, rollback_error],
        ):
            with self.assertRaises(RuntimeError) as caught:
                canvas.services.geometry_controller.set_bond_length(30.0)

        self.assertIs(caught.exception, original_error)
        self.assertIs(canvas.renderer.style, original_style)
        self.assertEqual(bond_length_px_for(canvas), 20.0)
        self.assertTrue(
            any(
                "SystemExit: rollback refresh terminated" in note
                for note in caught.exception.__notes__
            )
        )

    def test_bond_length_exact_restore_retries_fail_once_and_persistent_results(
        self,
    ) -> None:
        from ui import canvas_geometry_controller as geometry_module

        for behavior in ("fail_once", "persistent"):
            with self.subTest(behavior=behavior):
                canvas, _label_atom_id, _dot_atom_id, _bond_id = (
                    self._real_bond_length_canvas()
                )
                original_positions = {
                    atom_id: (atom.x, atom.y)
                    for atom_id, atom in canvas.model.atoms.items()
                }
                original_style = canvas.renderer.style
                primary = KeyboardInterrupt(
                    f"{behavior} bond-length refresh interrupted"
                )
                first_error = SystemExit("first bond exact restore failed")
                first = HistoryTransactionRestoreResult(
                    authoritative=False,
                    fallback_to_inverse=False,
                    errors=(first_error,),
                )
                original_restore = (
                    geometry_module.restore_history_transaction_for_history
                )
                calls = 0

                def restore(
                    *args,
                    _first=first,
                    _behavior=behavior,
                    _original_restore=original_restore,
                    **kwargs,
                ):
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        return _first
                    if _behavior == "fail_once":
                        return _original_restore(*args, **kwargs)
                    return HistoryTransactionRestoreResult(
                        authoritative=False,
                        fallback_to_inverse=False,
                        errors=(
                            RuntimeError("persistent bond exact restore failure"),
                        ),
                    )

                with (
                    mock.patch.object(
                        geometry_module,
                        "refresh_bond_length_graphics_for",
                        side_effect=(primary, None),
                    ),
                    mock.patch.object(
                        geometry_module,
                        "restore_history_transaction_for_history",
                        side_effect=restore,
                    ),
                    self.assertRaises(KeyboardInterrupt) as raised,
                ):
                    canvas.services.geometry_controller.set_bond_length(30.0)

                self.assertIs(raised.exception, primary)
                self.assertEqual(calls, 2)
                self.assertIs(canvas.renderer.style, original_style)
                self.assertEqual(bond_length_px_for(canvas), 20.0)
                self.assertEqual(
                    {
                        atom_id: (atom.x, atom.y)
                        for atom_id, atom in canvas.model.atoms.items()
                    },
                    original_positions,
                )
                self.assertTrue(
                    any(
                        "first bond exact restore failed" in note
                        for note in getattr(primary, "__notes__", [])
                    )
                )
                if behavior == "persistent":
                    self.assertTrue(
                        any(
                            "persistent bond exact restore failure" in note
                            for note in getattr(primary, "__notes__", [])
                        )
                    )

    def test_set_bond_length_persistent_label_setter_failure_restores_raw_atom_graphics(self) -> None:
        canvas, label_atom_id, _dot_atom_id, _bond_id = self._real_bond_length_canvas()
        label_item = atom_items_for(canvas)[label_atom_id]
        label_item.setSelected(True)
        original_font = label_item.font()
        original_bounds = label_item.boundingRect()
        original_shape_bounds = label_item.shape().boundingRect()
        original_position = label_item.pos()
        original_style = canvas.renderer.style
        original_set_font = AtomLabelItem.setFont
        calls = 0

        def mutate_once_then_fail_persistently(item, font) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                original_set_font(item, font)
            raise RuntimeError("persistent atom font callback failure")

        with mock.patch.object(
            AtomLabelItem,
            "setFont",
            new=mutate_once_then_fail_persistently,
        ):
            with self.assertRaisesRegex(RuntimeError, "persistent atom font"):
                canvas.services.geometry_controller.set_bond_length(30.0)

        self.assertGreaterEqual(calls, 2)
        self.assertIs(canvas.renderer.style, original_style)
        self.assertEqual(bond_length_px_for(canvas), 20.0)
        self.assertIs(atom_items_for(canvas)[label_atom_id], label_item)
        self.assertEqual(label_item.font(), original_font)
        self.assertEqual(label_item.boundingRect(), original_bounds)
        self.assertEqual(label_item.shape().boundingRect(), original_shape_bounds)
        self.assertEqual(label_item.pos(), original_position)
        self.assertTrue(label_item.isSelected())
        self.assertFalse(canvas.services.history_service.can_undo())

    def test_update_bond_length_history_persistent_label_failure_restores_exact_state(self) -> None:
        canvas, label_atom_id, _dot_atom_id, _bond_id = self._real_bond_length_canvas()
        canvas.services.geometry_controller.set_bond_length(30.0)
        label_item = atom_items_for(canvas)[label_atom_id]
        label_item.setSelected(True)
        original_style = canvas.renderer.style
        original_font = label_item.font()
        original_bounds = label_item.boundingRect()
        original_shape_bounds = label_item.shape().boundingRect()
        original_position = label_item.pos()
        original_set_font = AtomLabelItem.setFont
        calls = 0

        def mutate_then_fail_persistently(item, font) -> None:
            nonlocal calls
            calls += 1
            original_set_font(item, font)
            raise RuntimeError("persistent history atom font callback failure")

        with mock.patch.object(
            AtomLabelItem,
            "setFont",
            new=mutate_then_fail_persistently,
        ):
            with self.assertRaisesRegex(RuntimeError, "persistent history atom font"):
                UpdateBondLengthCommand(20.0, 30.0).undo(canvas)

        self.assertGreaterEqual(calls, 1)
        self.assertIs(canvas.renderer.style, original_style)
        self.assertEqual(bond_length_px_for(canvas), 30.0)
        self.assertIs(atom_items_for(canvas)[label_atom_id], label_item)
        self.assertEqual(label_item.font(), original_font)
        self.assertEqual(label_item.boundingRect(), original_bounds)
        self.assertEqual(label_item.shape().boundingRect(), original_shape_bounds)
        self.assertEqual(label_item.pos(), original_position)
        self.assertTrue(label_item.isSelected())

    def test_real_bond_length_composite_failure_restores_atoms_ring_and_history_stacks(self) -> None:
        class _PersistentFailRingItem(QGraphicsPolygonItem):
            fail_set_polygon = False

            def setPolygon(self, polygon) -> None:
                QGraphicsPolygonItem.setPolygon(self, polygon)
                if self.fail_set_polygon:
                    raise RuntimeError("persistent ring polygon callback failure")

        canvas, label_atom_id, dot_atom_id, bond_id = self._real_bond_length_canvas()
        third_atom_id = add_atom_for(canvas, "C", 10.0, 10.0)
        ring_atom_ids = [label_atom_id, dot_atom_id, third_atom_id]
        ring_item = _PersistentFailRingItem(
            QPolygonF(
                [
                    QPointF(0.0, 0.0),
                    QPointF(20.0, 0.0),
                    QPointF(10.0, 10.0),
                ]
            )
        )
        ring_item.setData(0, "ring")
        ring_item.setData(2, ring_atom_ids)
        canvas.scene().addItem(ring_item)
        set_scene_item_collection_for(canvas, "ring_items", [ring_item])
        set_atom_coords_3d_for(
            canvas,
            {
                label_atom_id: (0.0, 0.0, 3.0),
                dot_atom_id: (20.0, 0.0, 7.0),
                third_atom_id: (10.0, 10.0, 5.0),
            },
        )

        before_positions = {
            atom_id: (atom.x, atom.y)
            for atom_id, atom in canvas.model.atoms.items()
        }
        before_coords = dict(atom_coords_3d_for(canvas))
        before_polygon = [(point.x(), point.y()) for point in ring_item.polygon()]
        canvas.services.geometry_controller.set_bond_length(30.0)

        history_service = canvas.services.history_service
        state = history_service.state
        command = state.history[-1]
        stale_redo = UpdateSceneItemCommand(
            item=ring_item,
            before_state={"kind": "ring"},
            after_state={"kind": "ring"},
        )
        state.redo_stack.append(stale_redo)
        history_list = state.history
        redo_list = state.redo_stack
        atom_objects = dict(canvas.model.atoms)
        bond_object = canvas.model.bonds[bond_id]
        ring_list = ring_items_for(canvas)
        coords_mapping = atom_coords_3d_for(canvas)
        after_style = canvas.renderer.style
        after_positions = {
            atom_id: (atom.x, atom.y)
            for atom_id, atom in canvas.model.atoms.items()
        }
        after_coords = dict(coords_mapping)
        after_polygon = [(point.x(), point.y()) for point in ring_item.polygon()]

        original_set_font = AtomLabelItem.setFont

        def mutate_font_then_fail(item, font) -> None:
            original_set_font(item, font)
            raise RuntimeError("persistent composite atom font failure")

        with mock.patch.object(
            AtomLabelItem,
            "setFont",
            new=mutate_font_then_fail,
        ):
            with self.assertRaisesRegex(RuntimeError, "persistent composite atom font"):
                history_service.undo()

        self.assertIs(state.history, history_list)
        self.assertIs(state.redo_stack, redo_list)
        self.assertEqual(state.history, [command])
        self.assertIs(state.history[0], command)
        self.assertEqual(state.redo_stack, [stale_redo])
        self.assertIs(canvas.renderer.style, after_style)
        self.assertEqual(
            {atom_id: (atom.x, atom.y) for atom_id, atom in canvas.model.atoms.items()},
            after_positions,
        )
        self.assertEqual(dict(coords_mapping), after_coords)
        self.assertEqual(
            [(point.x(), point.y()) for point in ring_item.polygon()],
            after_polygon,
        )
        self.assertIs(ring_items_for(canvas), ring_list)
        self.assertEqual(ring_items_for(canvas), [ring_item])
        for atom_id, atom in atom_objects.items():
            self.assertIs(canvas.model.atoms[atom_id], atom)
        self.assertIs(canvas.model.bonds[bond_id], bond_object)

        history_service.undo()
        self.assertEqual(
            {atom_id: (atom.x, atom.y) for atom_id, atom in canvas.model.atoms.items()},
            before_positions,
        )
        self.assertEqual(dict(coords_mapping), before_coords)
        self.assertEqual(
            [(point.x(), point.y()) for point in ring_item.polygon()],
            before_polygon,
        )

        ring_item.fail_set_polygon = True
        try:
            with self.assertRaisesRegex(RuntimeError, "persistent ring polygon"):
                history_service.redo()
        finally:
            ring_item.fail_set_polygon = False

        self.assertIs(state.history, history_list)
        self.assertIs(state.redo_stack, redo_list)
        self.assertEqual(state.history, [])
        self.assertEqual(state.redo_stack, [stale_redo, command])
        self.assertIs(state.redo_stack[-1], command)
        self.assertEqual(
            {atom_id: (atom.x, atom.y) for atom_id, atom in canvas.model.atoms.items()},
            before_positions,
        )
        self.assertEqual(dict(coords_mapping), before_coords)
        self.assertEqual(
            [(point.x(), point.y()) for point in ring_item.polygon()],
            before_polygon,
        )

    def test_set_bond_length_append_then_raise_restores_history_identity_and_style(self) -> None:
        canvas, label_atom_id, dot_atom_id, bond_id = self._real_bond_length_canvas()
        label_item = atom_items_for(canvas)[label_atom_id]
        dot_item = atom_dots_for(canvas)[dot_atom_id]
        bond_item = bond_items_for_id(canvas, bond_id)[0]
        for item in (label_item, dot_item, bond_item):
            item.setSelected(True)

        history = canvas.services.history_service
        state = history.state
        prior_command = UpdateSceneItemCommand(
            item=bond_item,
            before_state={"opacity": 1.0},
            after_state={"opacity": 0.5},
        )
        redo_command = UpdateSceneItemCommand(
            item=label_item,
            before_state={"opacity": 0.7},
            after_state={"opacity": 1.0},
        )
        state.history.append(prior_command)
        state.redo_stack.append(redo_command)
        history_list = state.history
        redo_list = state.redo_stack
        renderer_style = canvas.renderer.style
        original_positions = {
            atom_id: (atom.x, atom.y) for atom_id, atom in canvas.model.atoms.items()
        }
        original_ids = (id(label_item), id(dot_item), id(bond_item))
        original_push = history.push

        def append_then_raise(command) -> None:
            original_push(command)
            raise RuntimeError("history push failed after append")

        with mock.patch.object(history, "push", side_effect=append_then_raise):
            with self.assertRaisesRegex(RuntimeError, "failed after append"):
                canvas.services.geometry_controller.set_bond_length(30.0)

        self.assertIs(canvas.renderer.style, renderer_style)
        self.assertEqual(bond_length_px_for(canvas), 20.0)
        self.assertEqual(
            {atom_id: (atom.x, atom.y) for atom_id, atom in canvas.model.atoms.items()},
            original_positions,
        )
        self.assertEqual(
            (
                id(atom_items_for(canvas)[label_atom_id]),
                id(atom_dots_for(canvas)[dot_atom_id]),
                id(bond_items_for_id(canvas, bond_id)[0]),
            ),
            original_ids,
        )
        self.assertTrue(all(item.isSelected() for item in (label_item, dot_item, bond_item)))
        self.assertIs(state.history, history_list)
        self.assertIs(state.redo_stack, redo_list)
        self.assertEqual(state.history, [prior_command])
        self.assertEqual(state.redo_stack, [redo_command])

    def test_set_bond_length_rescales_model_and_pushes_composite_command(self) -> None:
        ring_item = _FakeRingItem([(0.0, 0.0), (20.0, 0.0), (10.0, 10.0)])
        style = SimpleNamespace(bond_length_px=20.0)

        def _set_renderer_bond_length(length_px: float) -> None:
            style.bond_length_px = length_px

        pushed = []
        structure_build_service = SimpleNamespace(render_model=mock.Mock())
        view = SimpleNamespace(
            renderer=SimpleNamespace(style=style, set_bond_length=mock.Mock(side_effect=_set_renderer_bond_length)),
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("O", 20.0, 0.0),
                }
            ),
            rotation_state=CanvasRotationState(
                projection_center_3d=(10.0, 0.0, 0.0),
                projection_anchor_2d=(10.0, 0.0),
            ),
            bond_items={},
            atom_items={},
            atom_dots={},
            scene=lambda: SimpleNamespace(removeItem=mock.Mock()),
            services=SimpleNamespace(
                history_service=SimpleNamespace(push=pushed.append),
                structure_build_service=structure_build_service,
                hit_testing_service=SimpleNamespace(mark_spatial_index_dirty=mock.Mock()),
            ),
        )
        set_scene_item_collection_for(view, "ring_items", [ring_item])
        set_atom_coords_3d_for(view, {1: (0.25, 0.0, 4.0), 2: (19.75, 0.0, 4.0)})

        CanvasGeometryController(
            view,
            hit_testing_service=view.services.hit_testing_service,
            history_service=view.services.history_service,
        ).set_bond_length(30.0)

        self.assertEqual(style.bond_length_px, 30.0)
        self.assertAlmostEqual(view.model.atoms[1].x, -5.0)
        self.assertAlmostEqual(view.model.atoms[2].x, 25.0)
        self.assertEqual(atom_coords_3d_for(view), {1: (-4.625, 0.0, 6.0), 2: (24.625, 0.0, 6.0)})
        self.assertEqual(current_atom_coords_3d_for(view, 1), (-4.625, 0.0, 6.0))
        self.assertEqual(view.rotation_state.projection_center_3d, (10.0, 0.0, 0.0))
        self.assertEqual(view.rotation_state.projection_anchor_2d, (10.0, 0.0))
        scaled_points = [(point.x(), point.y()) for point in ring_item.polygon()]
        self.assertEqual(scaled_points, [(-5.0, 0.0), (25.0, 0.0), (10.0, 15.0)])
        structure_build_service.render_model.assert_not_called()
        self.assertEqual(len(pushed), 1)
        command = pushed[0]
        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual([type(entry) for entry in command.commands], [UpdateBondLengthCommand, SetAtomPositionsCommand, SetRingPolygonsCommand])
        atom_positions_command = command.commands[1]
        self.assertEqual(atom_positions_command.before_coords_3d, {1: (0.25, 0.0, 4.0), 2: (19.75, 0.0, 4.0)})
        self.assertEqual(atom_positions_command.after_coords_3d, {1: (-4.625, 0.0, 6.0), 2: (24.625, 0.0, 6.0)})
        self.assertTrue(atom_positions_command.restore_projection_state)
        self.assertEqual(atom_positions_command.before_projection_center_3d, (10.0, 0.0, 0.0))
        self.assertEqual(atom_positions_command.after_projection_center_3d, (10.0, 0.0, 0.0))

    def test_set_bond_length_short_circuits_for_empty_model_or_same_scale(self) -> None:
        empty_style = SimpleNamespace(bond_length_px=20.0)
        empty_view = SimpleNamespace(
            renderer=SimpleNamespace(style=empty_style, set_bond_length=mock.Mock(side_effect=lambda value: setattr(empty_style, "bond_length_px", value))),
            model=SimpleNamespace(atoms={}),
            push_command=mock.Mock(),
            services=SimpleNamespace(),
        )
        set_scene_item_collection_for(empty_view, "ring_items", [])
        empty_view.services.history_service = SimpleNamespace(push=empty_view.push_command)

        CanvasGeometryController(empty_view).set_bond_length(30.0)

        empty_view.push_command.assert_not_called()

        same_style = SimpleNamespace(bond_length_px=24.0)
        same_view = SimpleNamespace(
            renderer=SimpleNamespace(style=same_style, set_bond_length=mock.Mock(side_effect=lambda value: setattr(same_style, "bond_length_px", value))),
            model=SimpleNamespace(atoms={1: Atom("C", 1.0, 2.0)}),
            push_command=mock.Mock(),
            services=SimpleNamespace(),
        )
        set_scene_item_collection_for(same_view, "ring_items", [])
        same_view.services.history_service = SimpleNamespace(push=same_view.push_command)

        CanvasGeometryController(same_view).set_bond_length(24.0)

        same_view.push_command.assert_not_called()

    def test_normalize_project_unproject_and_current_coords_3d_helpers(self) -> None:
        self.assertIsNone(normalize_3d(0.0, 0.0, 0.0))
        self.assertEqual(normalize_3d(0.0, 3.0, 4.0), (0.0, 0.6, 0.8))

        no_projection_view = SimpleNamespace(rotation_state=CanvasRotationState())
        self.assertEqual(project_point_3d_for(no_projection_view, (2.0, 3.0, 4.0)), (2.0, 3.0))
        self.assertEqual(
            unproject_scene_point_3d_for(no_projection_view, QPointF(2.0, 3.0), 4.0),
            (2.0, 3.0, 4.0),
        )

        projected_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            rotation_state=CanvasRotationState(
                projection_center_3d=(10.0, 20.0, 30.0),
                projection_anchor_2d=(100.0, 200.0),
            ),
        )

        scene_xy = project_point_3d_for(projected_view, (14.0, 26.0, 40.0))
        restored = unproject_scene_point_3d_for(projected_view, QPointF(*scene_xy), 40.0)
        self.assertAlmostEqual(restored[0], 14.0, places=6)
        self.assertAlmostEqual(restored[1], 26.0, places=6)
        self.assertAlmostEqual(restored[2], 40.0, places=6)

        projected_atom = project_point_3d_for(projected_view, (12.0, 13.0, 30.0))
        projected_view.model = SimpleNamespace(
            atoms={
                1: Atom("C", projected_atom[0], projected_atom[1]),
                2: Atom("N", 40.0, 50.0),
            }
        )
        set_atom_coords_3d_for(
            projected_view,
            {
                1: (12.0, 13.0, 30.0),
                2: (50.0, 60.0, 80.0),
            },
        )

        coords = current_atom_coords_3d_for(projected_view, 1)
        self.assertEqual(coords, (12.0, 13.0, 30.0))
        self.assertEqual(current_atom_coords_3d_for(projected_view, 2), (40.0, 50.0, 0.0))
        self.assertIsNone(current_atom_coords_3d_for(projected_view, 99))

        set_atom_coords_3d_for(projected_view, {})
        self.assertEqual(current_atom_coords_3d_for(projected_view, 1), projected_atom + (0.0,))

    def test_projection_and_center_helpers_cover_anchor_and_empty_fallbacks(self) -> None:
        projected_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            rotation_state=CanvasRotationState(projection_center_3d=(10.0, 20.0, 30.0)),
        )

        projected = project_point_3d_for(projected_view, (12.0, 24.0, 30.0))
        restored = unproject_scene_point_3d_for(projected_view, QPointF(*projected), 30.0)
        self.assertAlmostEqual(projected[0], 12.0)
        self.assertAlmostEqual(projected[1], 24.0)
        self.assertAlmostEqual(restored[0], 12.0)
        self.assertAlmostEqual(restored[1], 24.0)
        self.assertEqual(center_for_coords_3d(set(), {}), None)
        self.assertEqual(
            center_for_coords_3d({1, 2}, {3: (1.0, 2.0, 3.0)}),
            None,
        )

        explicit_projected = project_point_3d_for(
            projected_view,
            (12.0, 24.0, 31.0),
            center_3d=(10.0, 20.0, 30.0),
            anchor_2d=(0.0, 0.0),
        )
        explicit_restored = unproject_scene_point_3d_for(
            projected_view,
            QPointF(*explicit_projected),
            31.0,
            center_3d=(10.0, 20.0, 30.0),
            anchor_2d=(0.0, 0.0),
        )
        self.assertAlmostEqual(explicit_restored[0], 12.0)
        self.assertAlmostEqual(explicit_restored[1], 24.0)

    def test_planar_fragment_helpers_detect_and_flatten_connected_planar_atoms(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(
                bonds=[
                    Bond(1, 2, 2),
                    Bond(2, 3, 1),
                    Bond(3, 4, 1),
                    Bond(4, 5, 1),
                    None,
                ]
            ),
            graph_state=CanvasGraphState(
                atom_bond_ids={
                    1: {0},
                    2: {0, 1},
                    3: {1, 2},
                    4: {2, 3},
                    5: {3},
                }
            ),
            services=SimpleNamespace(
                canvas_graph_service=SimpleNamespace(bond_in_cycle=lambda bond_id: bond_id in {2, 3})
            ),
        )
        bond_in_cycle = view.services.canvas_graph_service.bond_in_cycle
        self.assertTrue(atom_in_planar_system_for(view, 2, bond_in_cycle=bond_in_cycle))
        self.assertTrue(bond_is_planar_fragment_edge_for(view, 1, bond_in_cycle=bond_in_cycle))
        self.assertTrue(bond_is_planar_fragment_edge_for(view, 3, bond_in_cycle=bond_in_cycle))
        self.assertFalse(bond_is_planar_fragment_edge_for(view, 99, bond_in_cycle=bond_in_cycle))
        self.assertEqual(
            planar_fragment_components_for(view, {1, 2, 3, 4, 5}, bond_in_cycle=bond_in_cycle),
            [{1, 2, 3, 4, 5}],
        )

        coords = {
            1: (0.0, 0.0, 0.0),
            2: (1.0, 0.0, 1.0),
            3: (2.0, 0.0, 0.0),
            4: (3.0, 1.0, 0.0),
            5: (4.0, 1.0, 2.0),
        }
        normal = fragment_plane_normal_for({1, 2, 3}, coords)
        self.assertIsNotNone(normal)
        flattened = flatten_planar_fragments_for(view, {1, 2, 3, 4, 5}, coords, bond_in_cycle=bond_in_cycle)
        self.assertNotEqual(flattened[5], coords[5])

    def test_planar_fragment_helpers_cover_invalid_none_collinear_and_skip_paths(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(bonds=[None, Bond(1, 2, 1), Bond(2, 3, 1)]),
            graph_state=CanvasGraphState(atom_bond_ids={1: {0, 9}, 2: {0, 1}, 3: {2}}),
            services=SimpleNamespace(canvas_graph_service=SimpleNamespace(bond_in_cycle=lambda bond_id: False)),
        )
        bond_in_cycle = view.services.canvas_graph_service.bond_in_cycle
        self.assertFalse(atom_in_planar_system_for(view, 1, bond_in_cycle=bond_in_cycle))
        self.assertFalse(bond_is_planar_fragment_edge_for(view, 0, bond_in_cycle=bond_in_cycle))
        self.assertFalse(bond_is_planar_fragment_edge_for(view, 9, bond_in_cycle=bond_in_cycle))
        self.assertIsNone(
            fragment_plane_normal_for(
                {1, 2},
                {
                    1: (0.0, 0.0, 0.0),
                    2: (1.0, 0.0, 0.0),
                },
            )
        )
        self.assertEqual(
            fragment_plane_normal_for(
                {1, 2, 3},
                {
                    1: (0.0, 0.0, 0.0),
                    2: (1.0, 0.0, 0.0),
                    3: (2.0, 0.0, 0.0),
                },
            ),
            (0.0, 0.0, 1.0),
        )
        self.assertEqual(
            flatten_planar_fragments_for(view, set(), {1: (1.0, 2.0, 3.0)}),
            {1: (1.0, 2.0, 3.0)},
        )

        skip_view = SimpleNamespace()
        coords = {1: (0.0, 0.0, 0.0), 2: (1.0, 0.0, 1.0), 3: (2.0, 0.0, 0.0)}
        with (
            mock.patch("ui.selection_rotation_planarity.planar_fragment_components_for", return_value=[{1, 2, 3}]),
            mock.patch("ui.selection_rotation_planarity.fragment_plane_normal_for", return_value=None),
            mock.patch("ui.selection_rotation_planarity.center_for_coords_3d", return_value=(1.0, 1.0, 1.0)),
        ):
            self.assertEqual(flatten_planar_fragments_for(skip_view, {1, 2, 3}, coords), coords)

        centroid_skip_view = SimpleNamespace()
        with (
            mock.patch("ui.selection_rotation_planarity.planar_fragment_components_for", return_value=[{1, 2, 3}]),
            mock.patch("ui.selection_rotation_planarity.fragment_plane_normal_for", return_value=(0.0, 0.0, 1.0)),
            mock.patch("ui.selection_rotation_planarity.center_for_coords_3d", return_value=None),
        ):
            self.assertEqual(flatten_planar_fragments_for(centroid_skip_view, {1, 2, 3}, coords), coords)

        small_component_view = SimpleNamespace(
            model=SimpleNamespace(bonds=[Bond(1, 2, 2)]),
        )
        self.assertEqual(planar_fragment_components_for(small_component_view, {1, 2}), [])

        missing_point_view = SimpleNamespace()
        with (
            mock.patch("ui.selection_rotation_planarity.planar_fragment_components_for", return_value=[{1, 2, 3}]),
            mock.patch("ui.selection_rotation_planarity.fragment_plane_normal_for", return_value=(0.0, 0.0, 1.0)),
            mock.patch("ui.selection_rotation_planarity.center_for_coords_3d", return_value=(0.0, 0.0, 0.0)),
        ):
            flattened_missing = flatten_planar_fragments_for(
                missing_point_view,
                {1, 2, 3},
                {
                    1: (0.0, 0.0, 1.0),
                    2: (1.0, 0.0, 0.0),
                },
            )
        self.assertEqual(flattened_missing[1], (0.0, 0.0, 0.0))
        self.assertEqual(flattened_missing[2], (1.0, 0.0, 0.0))

    def test_apply_projected_atom_positions_updates_labels_dots_and_marks(self) -> None:
        label = object()
        dot = _FakeDot()
        mark_with_offset = _FakeMark({"dx": 2.0, "dy": -3.0})
        mark_without_offset = _FakeMark({})
        atom_label_service = SimpleNamespace(position_label=mock.Mock())
        scene_decoration_build_service = SimpleNamespace(set_mark_center=mock.Mock())
        view = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 4.0, 5.0)}),
            mark_registry=CanvasMarkRegistry({1: [mark_with_offset, mark_without_offset]}),
            services=SimpleNamespace(
                atom_label_service=atom_label_service,
                scene_decoration_build_service=scene_decoration_build_service,
            ),
        )
        set_atom_coords_3d_for(view, {})
        set_atom_items_for(view, {1: label})
        set_atom_dots_for(view, {1: dot})

        with mock.patch(
            "ui.selection_rotation_access.project_point_3d_for",
            side_effect=lambda canvas, point: (point[0] + 10.0, point[1] - 5.0),
        ):
            apply_projected_atom_positions_for(
                view,
                {1, 2, 99},
                {
                    1: (1.0, 2.0, 3.0),
                    2: (5.0, 7.0, 11.0),
                },
            )

        self.assertEqual(atom_coords_3d_for(view)[1], (1.0, 2.0, 3.0))
        self.assertEqual(atom_coords_3d_for(view)[2], (5.0, 7.0, 11.0))
        self.assertEqual((view.model.atoms[1].x, view.model.atoms[1].y), (11.0, -3.0))
        self.assertEqual((view.model.atoms[2].x, view.model.atoms[2].y), (15.0, 2.0))
        atom_label_service.position_label.assert_called_once_with(label, 11.0, -3.0)
        self.assertEqual(dot.positions, [(11.0, -3.0)])
        set_mark_center = scene_decoration_build_service.set_mark_center
        self.assertEqual(set_mark_center.call_count, 2)
        first_mark_pos = set_mark_center.call_args_list[0].args[1]
        second_mark_pos = set_mark_center.call_args_list[1].args[1]
        self.assertEqual((first_mark_pos.x(), first_mark_pos.y()), (13.0, -6.0))
        self.assertEqual((second_mark_pos.x(), second_mark_pos.y()), (11.0, -3.0))

    def test_apply_projected_positions_average_lengths_and_rotation_scale_cover_noop_cases(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0)}),
            mark_registry=CanvasMarkRegistry(),
            services=SimpleNamespace(
                atom_label_service=SimpleNamespace(position_label=mock.Mock()),
                scene_decoration_build_service=SimpleNamespace(set_mark_center=mock.Mock()),
            ),
        )
        set_atom_coords_3d_for(view, {})
        set_atom_items_for(view, {})
        set_atom_dots_for(view, {})

        with mock.patch(
            "ui.selection_rotation_access.project_point_3d_for",
            side_effect=lambda canvas, point: (point[0], point[1]),
        ):
            apply_projected_atom_positions_for(
                view,
                {1, 2},
                {
                    1: (1.0, 2.0, 3.0),
                    2: (4.0, 5.0, 6.0),
                },
            )
        self.assertEqual(atom_coords_3d_for(view)[2], (4.0, 5.0, 6.0))
        self.assertEqual((view.model.atoms[1].x, view.model.atoms[1].y), (1.0, 2.0))

        sparse_view = SimpleNamespace(
            graph_state=CanvasGraphState(atom_bond_ids={1: {0, 99}, 2: {0}, 3: {1}}),
            model=SimpleNamespace(bonds=[Bond(1, 2, 1), None]),
            rotation_state=CanvasRotationState(
                base_bond_length=10.0,
                base_coords={1: (0.0, 0.0, 0.0), 2: (5.0, 0.0, 0.0)},
            ),
        )
        self.assertEqual(bond_ids_within_atom_ids_for(sparse_view, set()), set())
        self.assertIsNone(
            average_bond_length_for_atoms_for(
                sparse_view,
                {1, 2, 3},
                {
                    1: (0.0, 0.0, 0.0),
                    3: (0.0, 0.0, 0.0),
                },
            )
        )
        self.assertEqual(rotation_scale_for_coords_for(sparse_view, {1, 2}, {}), 2.0)
        with mock.patch("ui.selection_rotation_access.average_bond_length_for_atoms_for", return_value=float("nan")):
            self.assertEqual(rotation_scale_for_coords_for(sparse_view, {1, 2}, {}), 1.0)
        with mock.patch("ui.selection_rotation_access.average_bond_length_for_atoms_for", return_value=0.0):
            self.assertEqual(rotation_scale_for_coords_for(sparse_view, {1, 2}, {}), 1.0)

        tail_view = SimpleNamespace(
            graph_state=CanvasGraphState(atom_bond_ids={1: {0, 1, 2}, 2: {0, 2}, 3: {1}}),
            model=SimpleNamespace(
                bonds=[
                    None,
                    Bond(1, 3, 1),
                    Bond(1, 2, 1),
                ]
            ),
        )
        self.assertIsNone(
            average_bond_length_for_atoms_for(
                tail_view,
                {1, 2},
                {
                    1: (0.0, 0.0, 0.0),
                    2: (0.0, 0.0, 0.0),
                    3: (2.0, 0.0, 0.0),
                },
            )
        )

        forced_tail_view = SimpleNamespace(
            model=SimpleNamespace(
                bonds=[
                    None,
                    Bond(1, 3, 1),
                    Bond(1, 2, 1),
                ]
            )
        )
        self.assertAlmostEqual(
            average_bond_length_for_atoms_for(
                forced_tail_view,
                {1, 2},
                {
                    1: (0.0, 0.0, 0.0),
                    2: (3.0, 4.0, 0.0),
                    3: (2.0, 0.0, 0.0),
                },
            ),
            5.0,
        )

    def test_bond_lookup_average_scale_and_axis_rotation_helpers(self) -> None:
        indexed_view = SimpleNamespace(
            graph_state=CanvasGraphState(atom_bond_ids={1: {0, 99}, 2: {0, 1}, 3: {1, 2}}),
            model=SimpleNamespace(bonds=[Bond(1, 2, 1), Bond(2, 3, 1), Bond(3, 4, 1), None]),
            rotation_state=CanvasRotationState(
                base_bond_length=10.0,
                base_coords={1: (0.0, 0.0, 0.0), 2: (8.0, 0.0, 0.0), 3: (18.0, 0.0, 0.0)},
            ),
            _redraw_bond=mock.Mock(),
        )

        self.assertEqual(bond_ids_for_atom_ids_for(indexed_view, {1, 2, 99}), {0, 1, 99})
        self.assertEqual(bond_ids_within_atom_ids_for(indexed_view, {1, 2, 3}), {0, 1})
        self.assertAlmostEqual(
            average_bond_length_for_atoms_for(
                indexed_view,
                {1, 2, 3},
                {
                    1: (0.0, 0.0, 0.0),
                    2: (3.0, 4.0, 0.0),
                    3: (3.0, 8.0, 0.0),
                },
            ),
            4.5,
        )
        self.assertAlmostEqual(
            rotation_scale_for_coords_for(
                indexed_view,
                {2},
                {2: (6.0, 0.0, 0.0)},
                extra_atom_ids={1, 3},
            ),
            10.0 / 9.0,
        )

        redraw_view = SimpleNamespace(
            graph_state=CanvasGraphState(atom_bond_ids={1: {0}, 2: {0, 1}}),
            bond_renderer=SimpleNamespace(redraw_bond=mock.Mock()),
        )
        CanvasMoveController(
            redraw_view,
            hit_testing_service=SimpleNamespace(mark_spatial_index_dirty=mock.Mock()),
        ).redraw_bonds_for_atoms({1, 2})
        self.assertEqual({call.args[0] for call in redraw_view.bond_renderer.redraw_bond.call_args_list}, {0, 1})

        fallback_view = SimpleNamespace(
            graph_state=CanvasGraphState(),
            model=SimpleNamespace(bonds=[Bond(1, 2, 1), None, Bond(2, 3, 1)]),
        )
        self.assertEqual(bond_ids_within_atom_ids_for(fallback_view, {1, 2, 3}), {0, 2})
        self.assertIsNone(average_bond_length_for_atoms_for(fallback_view, set(), {}))

        no_scale_view = SimpleNamespace(rotation_state=CanvasRotationState())
        self.assertEqual(rotation_scale_for_coords_for(no_scale_view, set(), {}), 1.0)

        rotated = rotate_point_around_axis_for(
            SimpleNamespace(),
            (1.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 1.0),
            math.pi / 2,
        )
        self.assertAlmostEqual(rotated[0], 0.0, places=6)
        self.assertAlmostEqual(rotated[1], 1.0, places=6)
        self.assertAlmostEqual(rotated[2], 0.0, places=6)
        self.assertEqual(
            rotate_point_around_axis_for(
                SimpleNamespace(),
                (1.0, 2.0, 3.0),
                (0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0),
                0.75,
            ),
            (1.0, 2.0, 3.0),
        )

    def test_bond_match_lookup_order_sum_and_normal_helpers(self) -> None:
        bonds = [Bond(1, 2, 2), Bond(2, 1, 3), None, Bond(1, 3, 0)]
        cached_view = SimpleNamespace(
            model=SimpleNamespace(bonds=bonds, atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 10.0, 0.0)}),
            graph_state=CanvasGraphState(atom_bond_ids={1: {0, 1, 3}, 2: {0, 1}, 3: {3}}),
        )
        fallback_view = SimpleNamespace(
            model=SimpleNamespace(bonds=bonds, atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 10.0, 0.0)}),
            graph_state=CanvasGraphState(),
        )

        cached_service = CanvasGraphService(cached_view)
        fallback_service = CanvasGraphService(fallback_view)
        cached_view.services = SimpleNamespace(canvas_graph_service=cached_service)

        self.assertFalse(CanvasGraphService.bond_matches_atoms(None, 1, 2))
        self.assertTrue(CanvasGraphService.bond_matches_atoms(bonds[0], 1, 2))
        self.assertTrue(CanvasGraphService.bond_matches_atoms(bonds[0], 2, 1))
        self.assertEqual(CanvasGraphService.first_matching_bond_id(bonds, 1, 2), 0)
        self.assertEqual(CanvasGraphService.first_matching_bond_id(bonds, 1, 2, skip_bond_id=0), 1)
        self.assertIsNone(cached_service.bond_id_between(1, 1))
        self.assertEqual(cached_service.bond_id_between(1, 2), 0)
        self.assertEqual(cached_service.bond_id_between(1, 2, skip_bond_id=0), 1)
        self.assertEqual(fallback_service.bond_id_between(1, 2, skip_bond_id=0), 1)
        self.assertIsNone(CanvasGraphService.first_matching_bond_id([Bond(3, 4, 1), None], 1, 2))
        self.assertIsNone(
            CanvasGraphService(
                SimpleNamespace(
                    model=SimpleNamespace(bonds=[Bond(3, 4, 1), None]),
                    graph_state=CanvasGraphState(atom_bond_ids={1: {0, 1}, 2: {0, 1}}),
                )
            ).bond_id_between(1, 2)
        )
        self.assertTrue(cached_service.bond_exists(1, 2))
        self.assertFalse(cached_service.bond_exists(2, 3))
        self.assertEqual(CanvasGraphService(cached_view).atom_bond_order_sum(1), 6)

        nx, ny, length = line_normal_components(0.0, 0.0, 10.0, 0.0)
        self.assertEqual((nx, ny, length), (0.0, 1.0, 10.0))
        self.assertEqual(line_normal_components(0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        self.assertEqual(orient_normal_toward_target(0.0, 1.0, 5.0, 0.0, 5.0, -3.0), (0.0, -1.0))
        self.assertEqual(line_normal_for(SimpleNamespace(), 0.0, 0.0, 10.0, 0.0), (0.0, 1.0))
        self.assertEqual(
            line_normal_for(SimpleNamespace(), 0.0, 0.0, 10.0, 0.0, QPointF(5.0, -2.0)),
            (0.0, -1.0),
        )

        self.assertEqual(bond_offset_unit_3d_for(cached_view, 99, 2), None)
        self.assertEqual(
            bond_offset_unit_3d_for(
                SimpleNamespace(
                    model=SimpleNamespace(
                        atoms={1: Atom("C", 1.0, 1.0), 2: Atom("C", 1.0, 1.0)},
                    ),
                ),
                1,
                2,
            ),
            None,
        )
        self.assertEqual(bond_offset_unit_3d_for(cached_view, 1, 2), (0.0, 1.0))
        self.assertEqual(bond_offset_unit_3d_for(cached_view, 1, 2, target=(5.0, -2.0, 0.0)), (0.0, -1.0))

    def test_bond_graphics_access_and_color_fallbacks_delegate_cleanly(self) -> None:
        wedge_polygon = object()
        hash_segments = [(0.0, 0.0, 1.0, 1.0)]
        strip_polygon = object()
        ring_segments = ((1.0, 2.0, 3.0, 4.0), (5.0, 6.0, 7.0, 8.0), (0.0, 1.0))
        ring_bond = object()
        one_sided_strip = object()
        parallel_bonds = [object(), object()]
        wedge_bond = object()
        hash_bond = object()
        dotted_bond = object()
        dotted_path = object()
        renderer = SimpleNamespace(
            parallel_bond_segments=mock.Mock(return_value=hash_segments),
            wedge_polygon=mock.Mock(return_value=wedge_polygon),
            hash_segments=mock.Mock(return_value=hash_segments),
            strip_polygon=mock.Mock(return_value=strip_polygon),
            ring_double_segments=mock.Mock(return_value=ring_segments),
            update_bond_geometry=mock.Mock(),
            add_bond_graphics=mock.Mock(),
            redraw_connected_bonds=mock.Mock(),
            draw_ring_double_bond=mock.Mock(return_value=ring_bond),
            one_sided_bond_strip=mock.Mock(return_value=one_sided_strip),
            draw_parallel_bonds=mock.Mock(return_value=parallel_bonds),
            draw_wedge_bond=mock.Mock(return_value=wedge_bond),
            draw_hash_bond=mock.Mock(return_value=hash_bond),
            draw_dotted_bond=mock.Mock(return_value=dotted_bond),
            dotted_bond_path=mock.Mock(return_value=dotted_path),
        )
        view = SimpleNamespace(bond_renderer=renderer)
        center = QPointF(5.0, 6.0)

        self.assertEqual(parallel_bond_segments_for(view, 1.0, 2.0, 3.0, 4.0, 2, 7, 8), hash_segments)
        self.assertIs(wedge_polygon_for(view, 1.0, 2.0, 3.0, 4.0, 7, 8), wedge_polygon)
        self.assertEqual(hash_segments_for(view, 1.0, 2.0, 3.0, 4.0, 3, 7, 8), hash_segments)
        self.assertIs(strip_polygon_for(view, 1.0, 2.0, 3.0, 4.0, 0.0, 1.0, 2.0, 3.0), strip_polygon)
        self.assertEqual(ring_double_segments_for(view, "a", "b", center, 7, 8, (0.0, 0.0, 1.0)), ring_segments)
        bond_renderer_for(view).update_bond_geometry(4)
        add_bond_graphics_for(view, 5)
        self.assertIs(
            draw_ring_double_bond_for(
                view,
                "a",
                "b",
                center,
                7,
                8,
                outer_style="bold",
                center_3d=(1.0, 2.0, 3.0),
            ),
            ring_bond,
        )
        self.assertIs(one_sided_bond_strip_for(view, 1.0, 2.0, 3.0, 4.0, 0.0, 1.0, 2.0, 3.0), one_sided_strip)
        self.assertEqual(draw_parallel_bonds_for(view, 1.0, 2.0, 3.0, 4.0, 2, 7, 8), parallel_bonds)
        self.assertIs(draw_wedge_bond_for(view, 1.0, 2.0, 3.0, 4.0, 7, 8), wedge_bond)
        self.assertIs(draw_hash_bond_for(view, 1.0, 2.0, 3.0, 4.0, 7, 8), hash_bond)
        self.assertIs(draw_dotted_bond_for(view, 1.0, 2.0, 3.0, 4.0, 7, 8), dotted_bond)
        self.assertIs(dotted_bond_path_for(view, 1.0, 2.0, 3.0, 4.0, 7, 8), dotted_path)

        renderer.parallel_bond_segments.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 2, 7, 8)
        renderer.wedge_polygon.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 7, 8)
        renderer.hash_segments.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 3, 7, 8)
        renderer.strip_polygon.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 0.0, 1.0, 2.0, 3.0)
        renderer.ring_double_segments.assert_called_once_with("a", "b", center, 7, 8, (0.0, 0.0, 1.0))
        renderer.update_bond_geometry.assert_called_once_with(4)
        renderer.add_bond_graphics.assert_called_once_with(5)
        renderer.draw_ring_double_bond.assert_called_once_with(
            "a",
            "b",
            center,
            7,
            8,
            outer_style="bold",
            center_3d=(1.0, 2.0, 3.0),
        )
        renderer.one_sided_bond_strip.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 0.0, 1.0, 2.0, 3.0)
        renderer.draw_parallel_bonds.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 2, 7, 8)
        renderer.draw_wedge_bond.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 7, 8)
        renderer.draw_hash_bond.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 7, 8)
        renderer.draw_dotted_bond.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 7, 8)
        renderer.dotted_bond_path.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 7, 8)

        CanvasMoveController(
            view,
            hit_testing_service=SimpleNamespace(mark_spatial_index_dirty=mock.Mock()),
        ).redraw_connected_bonds(1, skip_bond_id=3)
        renderer.redraw_connected_bonds.assert_called_once_with(1, skip_bond_id=3)

        color = object()
        pen_and_brush_item = _FakePenBrushItem(Qt.BrushStyle.SolidPattern)
        brush_only_item = _FakeBrushOnlyItem(Qt.BrushStyle.SolidPattern)
        no_brush_item = _FakeBrushOnlyItem(Qt.BrushStyle.NoBrush)

        apply_color_to_bond_item_for(view, pen_and_brush_item, color)
        apply_color_to_bond_item_for(view, brush_only_item, color)
        apply_color_to_bond_item_for(view, no_brush_item, color)

        self.assertIs(pen_and_brush_item._pen.color, color)
        self.assertEqual(pen_and_brush_item.pen_updates, [pen_and_brush_item._pen])
        self.assertEqual(pen_and_brush_item.brush_updates, [color])
        self.assertEqual(brush_only_item.brush_updates, [color])
        self.assertEqual(no_brush_item.brush_updates, [])


if __name__ == "__main__":
    unittest.main()
