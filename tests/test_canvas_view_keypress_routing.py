import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QKeySequence
    from PyQt6.QtWidgets import QApplication, QGraphicsTextItem, QGraphicsView
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.canvas_view import CanvasView


class _FakeKeyEvent:
    def __init__(self, key, *, matches=None) -> None:
        self._key = key
        self._matches = set(matches or ())
        self.accept = mock.Mock()

    def key(self):
        return self._key

    def matches(self, standard_key) -> bool:
        return standard_key in self._matches

    def modifiers(self):
        return Qt.KeyboardModifier.NoModifier

    def text(self):
        return ""


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewKeyPressRoutingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_key_press_event_respects_text_editor_focus(self) -> None:
        focus_item = QGraphicsTextItem()
        focus_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        view = SimpleNamespace(scene=lambda: SimpleNamespace(focusItem=lambda: focus_item))

        with mock.patch.object(QGraphicsView, "keyPressEvent", new=mock.Mock(return_value=None)) as base_key_press:
            CanvasView.keyPressEvent(view, _FakeKeyEvent(Qt.Key.Key_A))

        base_key_press.assert_called_once()

    def test_key_press_event_routes_standard_shortcuts_and_selected_delete(self) -> None:
        scene = SimpleNamespace(focusItem=lambda: None, selectedItems=lambda: [object()])
        view = SimpleNamespace(
            scene=lambda: scene,
            _refresh_hover_from_cursor=mock.Mock(),
            _template_insert_active=False,
            _smiles_insert_active=False,
            undo=mock.Mock(),
            redo=mock.Mock(),
            copy_selection_to_clipboard=mock.Mock(return_value=True),
            paste_selection_from_clipboard=mock.Mock(return_value=True),
            delete_selected_items=mock.Mock(),
            hover_atom_id=None,
            hover_bond_id=None,
            _handle_chemdraw_shortcut=mock.Mock(return_value=False),
        )

        undo_event = _FakeKeyEvent(Qt.Key.Key_Z, matches={QKeySequence.StandardKey.Undo})
        CanvasView.keyPressEvent(view, undo_event)
        view.undo.assert_called_once_with()
        undo_event.accept.assert_called_once_with()

        copy_event = _FakeKeyEvent(Qt.Key.Key_C, matches={QKeySequence.StandardKey.Copy})
        CanvasView.keyPressEvent(view, copy_event)
        view.copy_selection_to_clipboard.assert_called_once_with()
        copy_event.accept.assert_called_once_with()

        delete_event = _FakeKeyEvent(Qt.Key.Key_Delete)
        CanvasView.keyPressEvent(view, delete_event)
        view.delete_selected_items.assert_called_once_with()
        delete_event.accept.assert_called_once_with()

    def test_key_press_event_routes_hover_atom_bond_and_shortcut_handlers(self) -> None:
        scene = SimpleNamespace(focusItem=lambda: None, selectedItems=lambda: [])

        atom_view = SimpleNamespace(
            scene=lambda: scene,
            _refresh_hover_from_cursor=mock.Mock(),
            _template_insert_active=False,
            _smiles_insert_active=False,
            undo=mock.Mock(),
            redo=mock.Mock(),
            copy_selection_to_clipboard=mock.Mock(return_value=False),
            paste_selection_from_clipboard=mock.Mock(return_value=False),
            delete_selected_items=mock.Mock(),
            hover_atom_id=7,
            hover_bond_id=None,
            _atom_has_visible_label=mock.Mock(return_value=True),
            clear_atom_label=mock.Mock(),
            delete_atom=mock.Mock(),
            _handle_chemdraw_shortcut=mock.Mock(return_value=False),
        )
        atom_event = _FakeKeyEvent(Qt.Key.Key_Delete)
        CanvasView.keyPressEvent(atom_view, atom_event)
        atom_view.clear_atom_label.assert_called_once_with(7)
        atom_view.delete_atom.assert_not_called()

        bond_view = SimpleNamespace(
            scene=lambda: scene,
            _refresh_hover_from_cursor=mock.Mock(),
            _template_insert_active=False,
            _smiles_insert_active=False,
            undo=mock.Mock(),
            redo=mock.Mock(),
            copy_selection_to_clipboard=mock.Mock(return_value=False),
            paste_selection_from_clipboard=mock.Mock(return_value=False),
            delete_selected_items=mock.Mock(),
            hover_atom_id=None,
            hover_bond_id=3,
            _clear_hover_highlight=mock.Mock(),
            delete_bond=mock.Mock(),
            _handle_chemdraw_shortcut=mock.Mock(return_value=False),
        )
        bond_event = _FakeKeyEvent(Qt.Key.Key_Delete)
        CanvasView.keyPressEvent(bond_view, bond_event)
        bond_view._clear_hover_highlight.assert_called_once_with()
        bond_view.delete_bond.assert_called_once_with(3, record=True)

        shortcut_view = SimpleNamespace(
            scene=lambda: scene,
            _refresh_hover_from_cursor=mock.Mock(),
            _template_insert_active=False,
            _smiles_insert_active=False,
            undo=mock.Mock(),
            redo=mock.Mock(),
            copy_selection_to_clipboard=mock.Mock(return_value=False),
            paste_selection_from_clipboard=mock.Mock(return_value=False),
            delete_selected_items=mock.Mock(),
            hover_atom_id=None,
            hover_bond_id=None,
            _handle_chemdraw_shortcut=mock.Mock(return_value=True),
        )
        shortcut_event = _FakeKeyEvent(Qt.Key.Key_T)
        CanvasView.keyPressEvent(shortcut_view, shortcut_event)
        shortcut_view._handle_chemdraw_shortcut.assert_called_once_with(shortcut_event)
        shortcut_event.accept.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
