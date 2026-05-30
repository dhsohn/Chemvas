import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui.canvas_document_session_service import CanvasDocumentSessionService


class CanvasDocumentSessionServiceTest(unittest.TestCase):
    def test_apply_state_restores_document_lifecycle_and_reenables_history(self) -> None:
        events = []
        canvas = SimpleNamespace(
            _history_enabled=True,
            clear_scene=mock.Mock(side_effect=lambda: events.append("clear")),
            _rebuild_bond_adjacency=mock.Mock(side_effect=lambda: events.append("adjacency")),
            _render_model=mock.Mock(side_effect=lambda: events.append("render")),
            _mark_spatial_index_dirty=mock.Mock(side_effect=lambda: events.append("dirty")),
            model="old-model",
        )
        service = CanvasDocumentSessionService(canvas)

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
        self.assertTrue(canvas._history_enabled)
        self.assertEqual(events, ["clear", "settings", "deserialize", "adjacency", "pre", "render", "post", "dirty"])

    def test_apply_state_reenables_history_when_restore_fails(self) -> None:
        canvas = SimpleNamespace(
            _history_enabled=True,
            clear_scene=mock.Mock(),
            _rebuild_bond_adjacency=mock.Mock(),
            _render_model=mock.Mock(),
            _mark_spatial_index_dirty=mock.Mock(),
            model="old-model",
        )
        service = CanvasDocumentSessionService(canvas)

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

        self.assertTrue(canvas._history_enabled)

    def test_restore_save_and_load_delegate_through_session_methods(self) -> None:
        canvas = SimpleNamespace(
            _history=[],
            _redo_stack=[],
            FILE_FORMAT_VERSION=7,
            _notify_history_change=mock.Mock(),
        )
        service = CanvasDocumentSessionService(canvas)

        with mock.patch.object(service, "apply_state") as apply_state:
            canvas._history[:] = ["undo"]
            canvas._redo_stack[:] = ["redo"]
            service.restore_state({"model": {}})

        apply_state.assert_called_once_with({"model": {}})
        self.assertEqual(canvas._history, [])
        self.assertEqual(canvas._redo_stack, [])

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


if __name__ == "__main__":
    unittest.main()
