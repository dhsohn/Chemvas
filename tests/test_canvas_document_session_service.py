import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui.canvas_document_session_service import CanvasDocumentSessionService
from ui.canvas_history_service import CanvasHistoryService
from ui.canvas_history_state import CanvasHistoryState, history_state_for


class _SceneItem:
    def __init__(self, kind: str = "arrow") -> None:
        self.kind = kind

    def data(self, index: int):
        if index == 0:
            return self.kind
        return None

    def childItems(self):
        return []


class _Scene:
    def __init__(self, selected_items=None) -> None:
        self._selected_items = list(selected_items or [])

    def selectedItems(self):
        return list(self._selected_items)


def _document_services(
    *,
    clear_scene,
    rebuild_bond_adjacency,
    render_model,
    mark_spatial_index_dirty,
):
    return SimpleNamespace(
        canvas_scene_reset_service=SimpleNamespace(clear_scene=clear_scene),
        canvas_graph_service=SimpleNamespace(rebuild_bond_adjacency=rebuild_bond_adjacency),
        structure_build_service=SimpleNamespace(render_model=render_model),
        hit_testing_service=SimpleNamespace(mark_spatial_index_dirty=mark_spatial_index_dirty),
    )


def _attach_history_service(canvas):
    service = CanvasHistoryService(canvas, history_state_for(canvas))
    services = getattr(canvas, "services", None)
    if services is None:
        services = SimpleNamespace()
        canvas.services = services
    services.history_service = service
    return canvas


def _session_service(canvas):
    services = getattr(canvas, "services", None)
    if services is None:
        services = SimpleNamespace()
        canvas.services = services
    hit_testing_service = getattr(services, "hit_testing_service", None)
    if hit_testing_service is None:
        hit_testing_service = SimpleNamespace(mark_spatial_index_dirty=mock.Mock())
        services.hit_testing_service = hit_testing_service
    graph_service = getattr(services, "canvas_graph_service", None)
    if graph_service is None:
        graph_service = SimpleNamespace(rebuild_bond_adjacency=mock.Mock())
        services.canvas_graph_service = graph_service
    structure_build_service = getattr(services, "structure_build_service", None)
    if structure_build_service is None:
        structure_build_service = SimpleNamespace(render_model=mock.Mock())
        services.structure_build_service = structure_build_service
    return CanvasDocumentSessionService(
        canvas,
        hit_testing_service=hit_testing_service,
        graph_service=graph_service,
        structure_build_service=structure_build_service,
        history_service=services.history_service,
    )


class CanvasDocumentSessionServiceTest(unittest.TestCase):
    def test_apply_state_restores_document_lifecycle_and_reenables_history(self) -> None:
        events = []
        canvas = SimpleNamespace(
            history_state=CanvasHistoryState(),
            clear_scene=mock.Mock(side_effect=lambda: events.append("clear")),
            model="old-model",
        )
        canvas.services = _document_services(
            clear_scene=lambda: canvas.clear_scene(),
            rebuild_bond_adjacency=mock.Mock(side_effect=lambda: events.append("adjacency")),
            render_model=mock.Mock(side_effect=lambda: events.append("render")),
            mark_spatial_index_dirty=mock.Mock(side_effect=lambda: events.append("dirty")),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)

        with (
            mock.patch(
                "ui.canvas_document_session_service.apply_document_settings",
                side_effect=lambda _canvas, _state: events.append("settings"),
            ),
            mock.patch(
                "ui.canvas_document_session_service.deserialize_model_state",
                side_effect=lambda _model: events.append("deserialize") or "new-model",
            ),
            mock.patch(
                "ui.canvas_document_session_service.restore_document_pre_model_items",
                side_effect=lambda _canvas, _state: events.append("pre"),
            ),
            mock.patch(
                "ui.canvas_document_session_service.restore_document_post_model_items",
                side_effect=lambda _canvas, _state: events.append("post"),
            ),
        ):
            service.apply_state({"model": {"atoms": []}})

        self.assertEqual(canvas.model, "new-model")
        self.assertTrue(history_state_for(canvas).enabled)
        self.assertEqual(events, ["clear", "settings", "deserialize", "adjacency", "pre", "render", "post", "dirty"])

    def test_apply_state_reenables_history_when_restore_fails(self) -> None:
        canvas = SimpleNamespace(
            history_state=CanvasHistoryState(),
            clear_scene=mock.Mock(),
            model="old-model",
        )
        canvas.services = _document_services(
            clear_scene=lambda: canvas.clear_scene(),
            rebuild_bond_adjacency=mock.Mock(),
            render_model=mock.Mock(),
            mark_spatial_index_dirty=mock.Mock(),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)

        with (
            mock.patch("ui.canvas_document_session_service.apply_document_settings"),
            mock.patch("ui.canvas_document_session_service.deserialize_model_state", return_value="new-model"),
            mock.patch("ui.canvas_document_session_service.restore_document_pre_model_items"),
            mock.patch(
                "ui.canvas_document_session_service.restore_document_post_model_items",
                side_effect=RuntimeError("boom"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                service.apply_state({"model": {"atoms": []}})

        self.assertTrue(history_state_for(canvas).enabled)

    def test_restore_save_and_load_delegate_through_session_methods(self) -> None:
        canvas = SimpleNamespace(
            history_state=CanvasHistoryState(),
            FILE_FORMAT_VERSION=7,
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)

        with mock.patch.object(service, "apply_state") as apply_state:
            history_state_for(canvas).history[:] = ["undo"]
            history_state_for(canvas).redo_stack[:] = ["redo"]
            service.restore_state({"model": {}})

        apply_state.assert_called_once_with({"model": {}})
        self.assertEqual(history_state_for(canvas).history, [])
        self.assertEqual(history_state_for(canvas).redo_stack, [])

        with (
            mock.patch.object(service, "snapshot_state", return_value={"state": 1}) as snapshot_state,
            mock.patch("ui.canvas_document_session_service.write_document") as write_document,
        ):
            service.save_to_file("/tmp/example.chemvas")

        snapshot_state.assert_called_once_with()
        write_document.assert_called_once_with("/tmp/example.chemvas", {"state": 1}, 7)

        with (
            mock.patch("ui.canvas_document_session_service.read_document", return_value=SimpleNamespace(state={"loaded": 1})) as read_document,
            mock.patch.object(service, "restore_state") as restore_state,
        ):
            service.load_from_file("/tmp/example.chemvas")

        read_document.assert_called_once_with("/tmp/example.chemvas")
        restore_state.assert_called_once_with({"loaded": 1})

    def test_export_figure_selection_scope_uses_selected_scene_items(self) -> None:
        selected_item = _SceneItem()
        scene = _Scene([selected_item])
        canvas = SimpleNamespace(
            renderer=SimpleNamespace(
                style=SimpleNamespace(
                    bond_line_width=1.5,
                    bond_length_px=30.0,
                    bond_length_pt=15.0,
                )
            ),
            scene=mock.Mock(return_value=scene),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)

        with mock.patch("ui.canvas_document_session_service.export_canvas_scene_for") as export_canvas_scene:
            service.export_figure(
                "/tmp/out.svg",
                fmt="svg",
                scope="selection",
                dpi=144,
                background="white",
                sizing="bond",
            )

        export_canvas_scene.assert_called_once_with(
            canvas,
            "/tmp/out.svg",
            fmt="svg",
            items=[selected_item],
            margin=3.0,
            dpi=144,
            background="white",
            title="Chemvas drawing",
            unit_scale=0.5,
            target_width_pt=None,
        )
        self.assertEqual(canvas.scene.call_count, 2)

    def test_export_figure_selection_scope_requires_selected_items(self) -> None:
        scene = _Scene()
        canvas = SimpleNamespace(
            renderer=SimpleNamespace(
                style=SimpleNamespace(
                    bond_line_width=1.0,
                    bond_length_px=30.0,
                    bond_length_pt=15.0,
                )
            ),
            scene=mock.Mock(return_value=scene),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)

        with (
            mock.patch("ui.canvas_document_session_service.export_canvas_scene_for") as export_canvas_scene,
            self.assertRaisesRegex(ValueError, "Select something to export"),
        ):
            service.export_figure("/tmp/out.svg", scope="selection")

        export_canvas_scene.assert_not_called()

    def test_export_figure_column_sizing_sets_target_width(self) -> None:
        canvas = SimpleNamespace(
            renderer=SimpleNamespace(
                style=SimpleNamespace(
                    bond_line_width=1.0,
                    bond_length_px=30.0,
                    bond_length_pt=15.0,
                )
            ),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)

        with mock.patch("ui.canvas_document_session_service.export_canvas_scene_for") as export_canvas_scene:
            service.export_figure("/tmp/out.png", fmt="png", sizing="col1")

        self.assertIsNone(export_canvas_scene.call_args.kwargs["items"])
        self.assertEqual(export_canvas_scene.call_args.kwargs["unit_scale"], 1.0)
        self.assertAlmostEqual(export_canvas_scene.call_args.kwargs["target_width_pt"], 84.0 / 25.4 * 72.0)


if __name__ == "__main__":
    unittest.main()
