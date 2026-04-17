import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication, QGraphicsEllipseItem, QGraphicsScene


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.model import Atom, Bond
from ui.canvas_view import CanvasView


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewHoverHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_emit_selection_info_uses_rdkit_cache_and_handles_unavailable_pending_and_empty_selections(self) -> None:
        callback = mock.Mock()
        rdkit = mock.Mock()
        rdkit.is_unavailable.return_value = False
        rdkit.is_loaded.return_value = True
        rdkit.compute_props.return_value = ("C2H6", 30.12, None)

        loaded_view = SimpleNamespace(
            rdkit=rdkit,
            _selection_info_callback=callback,
            _selected_chemical_ids=mock.Mock(return_value=({1, 2}, {3})),
            _build_submodel=mock.Mock(return_value=("submodel", None, None)),
            _selection_signature_for=CanvasView._selection_signature_for,
            _selection_signature=None,
            _selection_pending_signature=None,
            _selection_info_cache=("", ""),
            _rdkit_warmup_pending=False,
            _rotation_selection_ids=None,
        )

        CanvasView._emit_selection_info(loaded_view)
        CanvasView._emit_selection_info(loaded_view)

        self.assertEqual(callback.call_args_list, [mock.call("C2H6", "30.12"), mock.call("C2H6", "30.12")])
        self.assertEqual(rdkit.compute_props.call_count, 1)
        self.assertEqual(loaded_view._selection_signature, (frozenset({1, 2}), frozenset({3})))
        self.assertEqual(loaded_view._selection_pending_signature, None)

        empty_callback = mock.Mock()
        empty_view = SimpleNamespace(
            rdkit=mock.Mock(
                is_unavailable=mock.Mock(return_value=False),
                is_loaded=mock.Mock(return_value=True),
                compute_props=mock.Mock(),
            ),
            _selection_info_callback=empty_callback,
            _selected_chemical_ids=mock.Mock(return_value=(set(), set())),
            _build_submodel=mock.Mock(),
            _selection_signature_for=CanvasView._selection_signature_for,
            _selection_signature=frozenset({9}),
            _selection_pending_signature=frozenset({9}),
            _selection_info_cache=("cached", "1.00"),
            _rdkit_warmup_pending=True,
            _rotation_selection_ids=None,
        )

        CanvasView._emit_selection_info(empty_view)
        self.assertEqual(empty_callback.call_args_list, [mock.call("", "")])
        self.assertIsNone(empty_view._selection_signature)
        self.assertIsNone(empty_view._selection_pending_signature)
        self.assertEqual(empty_view._selection_info_cache, ("", ""))
        self.assertFalse(empty_view._rdkit_warmup_pending)

        unavailable_callback = mock.Mock()
        unavailable_view = SimpleNamespace(
            rdkit=mock.Mock(
                is_unavailable=mock.Mock(return_value=True),
                is_loaded=mock.Mock(return_value=False),
                compute_props=mock.Mock(),
            ),
            _selection_info_callback=unavailable_callback,
            _selected_chemical_ids=mock.Mock(return_value=({4}, set())),
            _build_submodel=mock.Mock(),
            _selection_signature_for=CanvasView._selection_signature_for,
            _selection_signature=None,
            _selection_pending_signature=None,
            _selection_info_cache=("cached", "1.00"),
            _rdkit_warmup_pending=True,
            _rotation_selection_ids=None,
        )

        CanvasView._emit_selection_info(unavailable_view)
        self.assertEqual(unavailable_callback.call_args_list, [mock.call("", "")])
        self.assertIsNone(unavailable_view._selection_signature)
        self.assertIsNone(unavailable_view._selection_pending_signature)
        self.assertEqual(unavailable_view._selection_info_cache, ("", ""))
        self.assertFalse(unavailable_view._rdkit_warmup_pending)

        pending_callback = mock.Mock()
        pending_rdkit = mock.Mock()
        pending_rdkit.is_unavailable.return_value = False
        pending_rdkit.is_loaded.return_value = False
        pending_view = SimpleNamespace(
            rdkit=pending_rdkit,
            _selection_info_callback=pending_callback,
            _selected_chemical_ids=mock.Mock(return_value=({7}, {8})),
            _build_submodel=mock.Mock(),
            _selection_signature_for=CanvasView._selection_signature_for,
            _selection_signature=None,
            _selection_pending_signature=None,
            _selection_info_cache=("cached", "1.00"),
            _rdkit_warmup_pending=False,
            _rotation_selection_ids=None,
        )

        CanvasView._emit_selection_info(pending_view)
        self.assertEqual(pending_callback.call_args_list, [mock.call("", "")])
        self.assertEqual(pending_view._selection_pending_signature, (frozenset({7}), frozenset({8})))
        self.assertTrue(pending_view._rdkit_warmup_pending)
        self.assertEqual(pending_rdkit.compute_props.call_count, 0)

    def test_maybe_warm_rdkit_handles_loaded_unavailable_and_idle_paths(self) -> None:
        loaded_emit = mock.Mock()
        loaded_view = SimpleNamespace(
            rdkit=mock.Mock(
                is_unavailable=mock.Mock(return_value=False),
                is_loaded=mock.Mock(return_value=True),
                preload=mock.Mock(),
            ),
            _rdkit_warmup_pending=True,
            _selection_pending_signature=("pending",),
            _last_interaction_time=0.0,
            _rdkit_idle_threshold=5.0,
            _emit_selection_info=loaded_emit,
        )

        CanvasView._maybe_warm_rdkit(loaded_view)
        self.assertFalse(loaded_view._rdkit_warmup_pending)
        self.assertIsNone(loaded_view._selection_pending_signature)
        loaded_view.rdkit.preload.assert_not_called()
        loaded_emit.assert_called_once_with()

        unavailable_emit = mock.Mock()
        unavailable_view = SimpleNamespace(
            rdkit=mock.Mock(
                is_unavailable=mock.Mock(return_value=True),
                is_loaded=mock.Mock(return_value=False),
                preload=mock.Mock(),
            ),
            _rdkit_warmup_pending=True,
            _selection_pending_signature=("pending",),
            _last_interaction_time=0.0,
            _rdkit_idle_threshold=5.0,
            _emit_selection_info=unavailable_emit,
        )

        CanvasView._maybe_warm_rdkit(unavailable_view)
        self.assertFalse(unavailable_view._rdkit_warmup_pending)
        self.assertIsNone(unavailable_view._selection_pending_signature)
        unavailable_view.rdkit.preload.assert_not_called()
        unavailable_emit.assert_not_called()

        idle_emit = mock.Mock()
        idle_rdkit = mock.Mock()
        idle_rdkit.is_unavailable.return_value = False
        idle_rdkit.is_loaded.return_value = False
        idle_view = SimpleNamespace(
            rdkit=idle_rdkit,
            _rdkit_warmup_pending=True,
            _selection_pending_signature=("pending",),
            _last_interaction_time=10.0,
            _rdkit_idle_threshold=5.0,
            _emit_selection_info=idle_emit,
        )

        with mock.patch("ui.canvas_view.time.monotonic", return_value=20.0):
            CanvasView._maybe_warm_rdkit(idle_view)

        idle_rdkit.preload.assert_called_once_with()
        idle_emit.assert_called_once_with()
        self.assertFalse(idle_view._rdkit_warmup_pending)
        self.assertIsNone(idle_view._selection_pending_signature)

    def test_clear_hover_highlight_and_add_atom_hover_indicator_manage_scene_items(self) -> None:
        scene = QGraphicsScene()
        view = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={3: Atom("C", 12.0, 34.0)}),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            hover_items=[],
            hover_atom_id=99,
            hover_bond_id=77,
            _hover_preview_style="preview",
        )

        CanvasView._add_atom_hover_indicator(view, 3)
        self.assertEqual(len(view.hover_items), 1)
        indicator = view.hover_items[0]
        self.assertIsInstance(indicator, QGraphicsEllipseItem)
        self.assertEqual(len(scene.items()), 1)
        rect = indicator.rect()
        self.assertAlmostEqual(rect.x(), 7.0)
        self.assertAlmostEqual(rect.y(), 29.0)
        self.assertAlmostEqual(rect.width(), 10.0)
        self.assertAlmostEqual(rect.height(), 10.0)

        CanvasView._add_atom_hover_indicator(view, 999)
        self.assertEqual(len(view.hover_items), 1)
        self.assertEqual(len(scene.items()), 1)

        CanvasView._clear_hover_highlight(view)
        self.assertEqual(view.hover_items, [])
        self.assertIsNone(view.hover_atom_id)
        self.assertIsNone(view.hover_bond_id)
        self.assertIsNone(view._hover_preview_style)
        self.assertEqual(len(scene.items()), 0)

    def test_mark_center_and_bond_helpers_cover_pointer_and_endpoint_logic(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(atoms={7: Atom("C", 10.0, 20.0)}),
            _mark_offset_from_click=mock.Mock(return_value=QPointF(1.5, -2.5)),
            tools=SimpleNamespace(active=SimpleNamespace(name="bond")),
            active_bond_style="double",
            active_bond_order=2,
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=10.0)),
            snap_angle_step=45,
            _default_bond_endpoint=mock.Mock(return_value=QPointF(2.0, 3.0)),
        )

        point = QPointF(5.0, 6.0)
        self.assertEqual(CanvasView._mark_center_for_pointer(view, point).toPoint(), point.toPoint())
        self.assertEqual(CanvasView._mark_center_for_pointer(view, point, 999).toPoint(), point.toPoint())

        centered = CanvasView._mark_center_for_pointer(view, point, 7, kind="minus")
        self.assertAlmostEqual(centered.x(), 11.5)
        self.assertAlmostEqual(centered.y(), 17.5)
        view._mark_offset_from_click.assert_called_once_with(7, point, kind="minus")

        self.assertEqual(CanvasView._bond_preview_signature(view), "double:2")
        view.tools.active = SimpleNamespace(name="select")
        self.assertIsNone(CanvasView._bond_preview_signature(view))

        endpoint = CanvasView._bond_hover_endpoint(view, QPointF(0.0, 0.0), QPointF(1.0, 1.0))
        self.assertAlmostEqual(endpoint.x(), 7.071, places=3)
        self.assertAlmostEqual(endpoint.y(), 7.071, places=3)

        zero_length = CanvasView._bond_hover_endpoint(view, QPointF(0.0, 0.0), QPointF(0.0, 0.0))
        self.assertAlmostEqual(zero_length.x(), 10.0)
        self.assertAlmostEqual(zero_length.y(), 0.0)

        delegated = CanvasView._bond_hover_endpoint(view, QPointF(0.0, 0.0), QPointF(9.0, 9.0), start_atom_id=7)
        self.assertAlmostEqual(delegated.x(), 2.0)
        self.assertAlmostEqual(delegated.y(), 3.0)
        view._default_bond_endpoint.assert_called_once_with(QPointF(0.0, 0.0), 7)

    def test_default_bond_endpoint_handles_missing_single_and_balanced_neighbor_vectors(self) -> None:
        single_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=10.0)),
            model=SimpleNamespace(
                atoms={
                    0: Atom("C", 10.0, 10.0),
                    1: Atom("C", 20.0, 10.0),
                },
                bonds=[Bond(0, 1)],
            ),
        )

        missing = CanvasView._default_bond_endpoint(single_view, QPointF(3.0, 4.0), 999)
        self.assertAlmostEqual(missing.x(), 13.0)
        self.assertAlmostEqual(missing.y(), 4.0)

        single = CanvasView._default_bond_endpoint(single_view, QPointF(10.0, 10.0), 0)
        self.assertAlmostEqual(single.x(), 5.0, places=2)
        self.assertAlmostEqual(single.y(), 1.34, places=2)

        balanced_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=10.0)),
            model=SimpleNamespace(
                atoms={
                    0: Atom("C", 0.0, 0.0),
                    1: Atom("C", 10.0, 0.0),
                    2: Atom("C", -10.0, 0.0),
                },
                bonds=[Bond(0, 1), Bond(0, 2)],
            ),
        )
        balanced = CanvasView._default_bond_endpoint(balanced_view, QPointF(0.0, 0.0), 0)
        self.assertAlmostEqual(balanced.x(), 0.0, places=2)
        self.assertAlmostEqual(balanced.y(), -10.0, places=2)
