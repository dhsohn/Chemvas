import unittest
from types import SimpleNamespace
from unittest import mock

from chemvas.domain.document import Atom, Bond
from chemvas.ui.bond_preview_access import bond_hover_endpoint_for
from chemvas.ui.canvas_mark_scene_service import CanvasMarkSceneService
from chemvas.ui.canvas_rotation_state import CanvasRotationState
from chemvas.ui.canvas_tool_settings_state import CanvasToolSettingsState
from chemvas.ui.mark_item_access import mark_center_for_pointer_for
from chemvas.ui.selection_info_access import (
    emit_selection_info_for,
    maybe_warm_rdkit_for,
)
from chemvas.ui.selection_info_state import SelectionInfoState
from chemvas.ui.structure_geometry_access import (
    connected_atom_unit_vectors_for,
    default_bond_angle_for_vectors,
    default_bond_endpoint_for,
)
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication


class _SelectedItem:
    def __init__(self, kind: str, item_id: int) -> None:
        self.kind = kind
        self.item_id = item_id

    def data(self, index: int):
        if index == 0:
            return self.kind
        if index == 1:
            return self.item_id
        return None


def _scene_with_selected(*items):
    return SimpleNamespace(selectedItems=lambda: list(items))


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for canvas view tests"
)
class CanvasViewHoverHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_emit_selection_info_uses_rdkit_cache_and_handles_unavailable_pending_and_empty_selections(
        self,
    ) -> None:
        callback = mock.Mock()
        rdkit = mock.Mock()
        rdkit.is_unavailable.return_value = False
        rdkit.is_loaded.return_value = True
        rdkit.compute_props.return_value = ("C2H6", 30.12, None)

        loaded_view = SimpleNamespace(
            rdkit=rdkit,
            selection_info_state=SelectionInfoState(callback=callback),
            scene=lambda: _scene_with_selected(
                _SelectedItem("atom", 1),
                _SelectedItem("atom", 2),
                _SelectedItem("bond", 3),
            ),
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 1.0),
                    2: Atom("C", 2.0, 3.0),
                },
                bounds=mock.Mock(return_value=(0.0, 1.0, 2.0, 3.0)),
            ),
            rotation_state=CanvasRotationState(),
        )

        with mock.patch(
            "chemvas.ui.selection_info_access.build_submodel_state",
            return_value=("submodel", None, None),
        ) as build_submodel:
            emit_selection_info_for(loaded_view)
            emit_selection_info_for(loaded_view)

        self.assertEqual(
            callback.call_args_list,
            [mock.call("C2H6", "30.12"), mock.call("C2H6", "30.12")],
        )
        self.assertEqual(rdkit.compute_props.call_count, 1)
        build_submodel.assert_called_once()
        self.assertEqual(
            build_submodel.call_args.args, (loaded_view.model, {1, 2}, {3})
        )
        bounds_getter = build_submodel.call_args.kwargs["bounds_getter"]
        self.assertEqual(bounds_getter({1}, include_labels=True), (0.0, 1.0, 0.0, 1.0))
        self.assertEqual(
            loaded_view.selection_info_state.signature,
            (frozenset({1, 2}), frozenset({3})),
        )
        self.assertEqual(loaded_view.selection_info_state.pending_signature, None)

        empty_callback = mock.Mock()
        empty_view = SimpleNamespace(
            rdkit=mock.Mock(
                is_unavailable=mock.Mock(return_value=False),
                is_loaded=mock.Mock(return_value=True),
                compute_props=mock.Mock(),
            ),
            selection_info_state=SelectionInfoState(
                callback=empty_callback,
                signature=frozenset({9}),
                pending_signature=frozenset({9}),
                cache=("cached", "1.00"),
                rdkit_warmup_pending=True,
            ),
            rotation_state=CanvasRotationState(),
        )

        emit_selection_info_for(empty_view)
        self.assertEqual(empty_callback.call_args_list, [mock.call("", "")])
        self.assertIsNone(empty_view.selection_info_state.signature)
        self.assertIsNone(empty_view.selection_info_state.pending_signature)
        self.assertEqual(empty_view.selection_info_state.cache, ("", ""))
        self.assertFalse(empty_view.selection_info_state.rdkit_warmup_pending)

        unavailable_callback = mock.Mock()
        unavailable_view = SimpleNamespace(
            rdkit=mock.Mock(
                is_unavailable=mock.Mock(return_value=True),
                is_loaded=mock.Mock(return_value=False),
                compute_props=mock.Mock(),
            ),
            selection_info_state=SelectionInfoState(
                callback=unavailable_callback,
                cache=("cached", "1.00"),
                rdkit_warmup_pending=True,
            ),
            scene=lambda: _scene_with_selected(_SelectedItem("atom", 4)),
            rotation_state=CanvasRotationState(),
        )

        emit_selection_info_for(unavailable_view)
        self.assertEqual(unavailable_callback.call_args_list, [mock.call("", "")])
        self.assertIsNone(unavailable_view.selection_info_state.signature)
        self.assertIsNone(unavailable_view.selection_info_state.pending_signature)
        self.assertEqual(unavailable_view.selection_info_state.cache, ("", ""))
        self.assertFalse(unavailable_view.selection_info_state.rdkit_warmup_pending)

        pending_callback = mock.Mock()
        pending_rdkit = mock.Mock()
        pending_rdkit.is_unavailable.return_value = False
        pending_rdkit.is_loaded.return_value = False
        pending_view = SimpleNamespace(
            rdkit=pending_rdkit,
            selection_info_state=SelectionInfoState(
                callback=pending_callback,
                cache=("cached", "1.00"),
            ),
            scene=lambda: _scene_with_selected(
                _SelectedItem("atom", 7), _SelectedItem("bond", 8)
            ),
            rotation_state=CanvasRotationState(),
        )

        emit_selection_info_for(pending_view)
        emit_selection_info_for(pending_view)
        self.assertEqual(pending_callback.call_args_list, [mock.call("", "")])
        self.assertEqual(
            pending_view.selection_info_state.pending_signature,
            (frozenset({7}), frozenset({8})),
        )
        self.assertTrue(pending_view.selection_info_state.rdkit_warmup_pending)
        self.assertEqual(pending_rdkit.compute_props.call_count, 0)

    def test_maybe_warm_rdkit_handles_loaded_unavailable_and_idle_paths(self) -> None:
        loaded_callback = mock.Mock()
        loaded_view = SimpleNamespace(
            rdkit=mock.Mock(
                is_unavailable=mock.Mock(return_value=False),
                is_loaded=mock.Mock(return_value=True),
                preload=mock.Mock(),
            ),
            selection_info_state=SelectionInfoState(
                callback=loaded_callback,
                rdkit_warmup_pending=True,
                pending_signature=("pending",),
                last_interaction_time=0.0,
                rdkit_idle_threshold=5.0,
            ),
            rotation_state=CanvasRotationState(),
        )

        maybe_warm_rdkit_for(loaded_view)
        self.assertFalse(loaded_view.selection_info_state.rdkit_warmup_pending)
        self.assertIsNone(loaded_view.selection_info_state.pending_signature)
        loaded_view.rdkit.preload.assert_not_called()
        loaded_callback.assert_called_once_with("", "")

        unavailable_callback = mock.Mock()
        unavailable_view = SimpleNamespace(
            rdkit=mock.Mock(
                is_unavailable=mock.Mock(return_value=True),
                is_loaded=mock.Mock(return_value=False),
                preload=mock.Mock(),
            ),
            selection_info_state=SelectionInfoState(
                callback=unavailable_callback,
                rdkit_warmup_pending=True,
                pending_signature=("pending",),
                last_interaction_time=0.0,
                rdkit_idle_threshold=5.0,
            ),
        )

        maybe_warm_rdkit_for(unavailable_view)
        self.assertFalse(unavailable_view.selection_info_state.rdkit_warmup_pending)
        self.assertIsNone(unavailable_view.selection_info_state.pending_signature)
        unavailable_view.rdkit.preload.assert_not_called()
        unavailable_callback.assert_not_called()

        idle_callback = mock.Mock()
        idle_rdkit = mock.Mock()
        idle_rdkit.is_unavailable.return_value = False
        idle_rdkit.is_loaded.return_value = False
        idle_view = SimpleNamespace(
            rdkit=idle_rdkit,
            selection_info_state=SelectionInfoState(
                callback=idle_callback,
                rdkit_warmup_pending=True,
                pending_signature=("pending",),
                last_interaction_time=10.0,
                rdkit_idle_threshold=5.0,
            ),
            rotation_state=CanvasRotationState(),
        )

        with mock.patch(
            "chemvas.ui.selection_info_access.time.monotonic", return_value=20.0
        ):
            maybe_warm_rdkit_for(idle_view)

        idle_rdkit.preload.assert_called_once_with()
        idle_callback.assert_called_once_with("", "")
        self.assertFalse(idle_view.selection_info_state.rdkit_warmup_pending)
        self.assertIsNone(idle_view.selection_info_state.pending_signature)

        busy_callback = mock.Mock()
        busy_rdkit = mock.Mock()
        busy_rdkit.is_unavailable.return_value = False
        busy_rdkit.is_loaded.return_value = False
        busy_view = SimpleNamespace(
            rdkit=busy_rdkit,
            selection_info_state=SelectionInfoState(
                callback=busy_callback,
                rdkit_warmup_pending=True,
                pending_signature=("pending",),
                last_interaction_time=18.0,
                rdkit_idle_threshold=5.0,
            ),
        )

        with mock.patch(
            "chemvas.ui.selection_info_access.time.monotonic", return_value=20.0
        ):
            maybe_warm_rdkit_for(busy_view)

        busy_rdkit.preload.assert_not_called()
        busy_callback.assert_not_called()
        self.assertTrue(busy_view.selection_info_state.rdkit_warmup_pending)
        self.assertEqual(busy_view.selection_info_state.pending_signature, ("pending",))

    def test_emit_selection_info_returns_immediately_without_callback(self) -> None:
        no_callback_view = SimpleNamespace(
            selection_info_state=SelectionInfoState(callback=None)
        )

        emit_selection_info_for(no_callback_view)

    def test_mark_center_and_bond_helpers_cover_pointer_and_endpoint_logic(
        self,
    ) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(atoms={7: Atom("C", 10.0, 20.0)}, bonds=[]),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=10.0)),
            tool_settings_state=CanvasToolSettingsState(
                active_bond_style="double",
                active_bond_order=2,
                snap_angle_step=45,
            ),
        )
        mark_scene_service = CanvasMarkSceneService(view)
        mark_scene_service.mark_offset_from_click = mock.Mock(
            return_value=QPointF(1.5, -2.5)
        )
        view.services = SimpleNamespace(
            canvas_mark_scene_service=mark_scene_service,
            tools=SimpleNamespace(active=SimpleNamespace(name="bond")),
        )

        point = QPointF(5.0, 6.0)
        self.assertEqual(
            mark_center_for_pointer_for(view, point, None, kind=None).toPoint(),
            point.toPoint(),
        )
        self.assertEqual(
            mark_center_for_pointer_for(view, point, 999, kind=None).toPoint(),
            point.toPoint(),
        )

        centered = mark_center_for_pointer_for(view, point, 7, kind="minus")
        self.assertAlmostEqual(centered.x(), 11.5)
        self.assertAlmostEqual(centered.y(), 17.5)
        mark_scene_service.mark_offset_from_click.assert_called_once_with(
            7, point, kind="minus"
        )

        endpoint = bond_hover_endpoint_for(view, QPointF(0.0, 0.0), QPointF(1.0, 1.0))
        self.assertAlmostEqual(endpoint.x(), 7.071, places=3)
        self.assertAlmostEqual(endpoint.y(), 7.071, places=3)

        zero_length = bond_hover_endpoint_for(
            view, QPointF(0.0, 0.0), QPointF(0.0, 0.0)
        )
        self.assertAlmostEqual(zero_length.x(), 10.0)
        self.assertAlmostEqual(zero_length.y(), 0.0)

        delegated = bond_hover_endpoint_for(
            view, QPointF(0.0, 0.0), QPointF(9.0, 9.0), start_atom_id=7
        )
        self.assertAlmostEqual(delegated.x(), 10.0)
        self.assertAlmostEqual(delegated.y(), 0.0)

    def test_default_bond_endpoint_handles_missing_single_and_balanced_neighbor_vectors(
        self,
    ) -> None:
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

        missing = default_bond_endpoint_for(single_view, QPointF(3.0, 4.0), 999)
        self.assertAlmostEqual(missing.x(), 13.0)
        self.assertAlmostEqual(missing.y(), 4.0)

        no_atom = default_bond_endpoint_for(single_view, QPointF(3.0, 4.0), None)
        self.assertAlmostEqual(no_atom.x(), 13.0)
        self.assertAlmostEqual(no_atom.y(), 4.0)

        single = default_bond_endpoint_for(single_view, QPointF(10.0, 10.0), 0)
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
        balanced = default_bond_endpoint_for(balanced_view, QPointF(0.0, 0.0), 0)
        self.assertAlmostEqual(balanced.x(), 0.0, places=2)
        self.assertAlmostEqual(balanced.y(), -10.0, places=2)

    def test_connected_atom_vectors_and_angle_helper_skip_invalid_neighbors(
        self,
    ) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    0: Atom("C", 0.0, 0.0),
                    1: Atom("C", 10.0, 0.0),
                    2: Atom("C", 0.0, 10.0),
                    3: Atom("C", 0.0, 0.0),
                },
                bonds=[Bond(0, 1), Bond(0, 2), Bond(0, 99), Bond(0, 3), None],
            )
        )

        vectors = connected_atom_unit_vectors_for(view, 0)
        self.assertEqual(len(vectors), 2)
        self.assertEqual(vectors, [(1.0, 0.0), (0.0, 1.0)])
        self.assertEqual(connected_atom_unit_vectors_for(view, 999), [])

        self.assertEqual(default_bond_angle_for_vectors([]), 0.0)
        self.assertEqual(default_bond_angle_for_vectors([(1.0, 0.0)]), -120.0)
        self.assertEqual(
            default_bond_angle_for_vectors([(1.0, 0.0), (-1.0, 0.0)]),
            -90.0,
        )
        self.assertEqual(
            default_bond_angle_for_vectors([(1.0, 0.0), (0.0, 1.0)]),
            -135.0,
        )
