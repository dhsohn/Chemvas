import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.model import Bond
    from ui.canvas_view import CanvasView


class _FakeItem:
    def __init__(self, kind: str, *, scene_token=None) -> None:
        self._kind = kind
        self._scene_token = scene_token

    def data(self, key):
        if key == 0:
            return self._kind
        return None

    def scene(self):
        return self._scene_token


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewSelectionClipboardWrappersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_selected_items_for_transform_filters_excluded_items_and_deduplicates_notes(self) -> None:
        scene = SimpleNamespace()
        kept_atom = _FakeItem("atom", scene_token=scene)
        excluded_handle = _FakeItem("handle", scene_token=scene)
        excluded_note_box = _FakeItem("note_box", scene_token=scene)
        included_note = _FakeItem("note", scene_token=scene)
        other_scene_note = _FakeItem("note", scene_token=object())

        scene.selectedItems = lambda: [kept_atom, excluded_handle, excluded_note_box, included_note]
        view = SimpleNamespace(
            scene=lambda: scene,
            selected_notes=[included_note, other_scene_note],
        )

        selected_items = CanvasView._selected_items_for_transform(view)

        self.assertEqual(selected_items, [kept_atom, included_note])

    def test_selected_atom_ids_for_transform_includes_bond_endpoints_and_skips_invalid_bonds(self) -> None:
        view = SimpleNamespace(
            _selected_ids=lambda: ({7}, {0, 1, 2, 9}),
            model=SimpleNamespace(
                bonds=[
                    Bond(1, 2, 1),
                    None,
                    Bond(3, 4, 2),
                ]
            ),
        )

        atom_ids = CanvasView._selected_atom_ids_for_transform(view)

        self.assertEqual(atom_ids, {1, 2, 3, 4, 7})

    def test_flip_wrappers_delegate_to_scene_ops_controller(self) -> None:
        controller = SimpleNamespace(flip_selected_items=mock.Mock())
        view = SimpleNamespace(_scene_ops_controller=controller)

        CanvasView.flip_horizontal(view)
        CanvasView.flip_vertical(view)

        controller.flip_selected_items.assert_has_calls([mock.call(horizontal=True), mock.call(horizontal=False)])
        self.assertEqual(controller.flip_selected_items.call_count, 2)

    def test_clipboard_and_delete_wrappers_delegate_to_scene_ops_controller(self) -> None:
        controller = SimpleNamespace(
            copy_selection_to_clipboard=mock.Mock(return_value=True),
            paste_selection_from_clipboard=mock.Mock(return_value=False),
            delete_selected_items=mock.Mock(return_value=True),
        )
        view = SimpleNamespace(_scene_ops_controller=controller)

        self.assertTrue(CanvasView.copy_selection_to_clipboard(view))
        self.assertFalse(CanvasView.paste_selection_from_clipboard(view))
        self.assertTrue(CanvasView.delete_selected_items(view))

        controller.copy_selection_to_clipboard.assert_called_once_with()
        controller.paste_selection_from_clipboard.assert_called_once_with()
        controller.delete_selected_items.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
