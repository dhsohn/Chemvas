import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
except ModuleNotFoundError:
    QPointF = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QPointF is not None:
    from core.model import Atom, Bond
    from ui.canvas_chemdraw_shortcut_service import CanvasChemdrawShortcutService, canvas_chemdraw_shortcut_service_for
    from ui.canvas_view import CanvasView


class _FakeKeyEvent:
    def __init__(self, key, modifiers=Qt.KeyboardModifier.NoModifier, text: str = "") -> None:
        self._key = key
        self._modifiers = modifiers
        self._text = text

    def key(self):
        return self._key

    def modifiers(self):
        return self._modifiers

    def text(self):
        return self._text


@unittest.skipUnless(QPointF is not None, "PyQt6 is required for ChemDraw shortcut service tests")
class CanvasChemDrawShortcutServiceTest(unittest.TestCase):
    def test_object_and_generic_shortcuts_dispatch_expected_actions(self) -> None:
        calls: list[tuple] = []
        canvas = SimpleNamespace(
            _shortcut_modifiers=lambda event: CanvasView._shortcut_modifiers(event),
            flip_horizontal=lambda: calls.append(("flip_h",)),
            flip_vertical=lambda: calls.append(("flip_v",)),
            set_tool=lambda tool: calls.append(("tool", tool)),
            set_bond_style=lambda style, order: calls.append(("bond_style", style, order)),
        )
        service = CanvasChemdrawShortcutService(canvas)

        self.assertTrue(
            service.handle_object_shortcut(
                _FakeKeyEvent(Qt.Key.Key_H, Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier)
            )
        )
        self.assertTrue(
            service.handle_object_shortcut(
                _FakeKeyEvent(Qt.Key.Key_V, Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier)
            )
        )
        self.assertFalse(service.handle_object_shortcut(_FakeKeyEvent(Qt.Key.Key_X)))

        self.assertTrue(service.handle_generic_hotkey(_FakeKeyEvent(Qt.Key.Key_Space)))
        self.assertTrue(service.handle_generic_hotkey(_FakeKeyEvent(Qt.Key.Key_X)))
        self.assertTrue(service.handle_generic_hotkey(_FakeKeyEvent(Qt.Key.Key_G, Qt.KeyboardModifier.ShiftModifier)))
        self.assertTrue(service.handle_generic_hotkey(_FakeKeyEvent(Qt.Key.Key_D, Qt.KeyboardModifier.AltModifier)))
        self.assertFalse(service.handle_generic_hotkey(_FakeKeyEvent(Qt.Key.Key_Z)))

        self.assertIn(("flip_h",), calls)
        self.assertIn(("flip_v",), calls)
        self.assertIn(("tool", "select"), calls)
        self.assertIn(("bond_style", "single", 1), calls)
        self.assertIn(("tool", "ts_bracket"), calls)
        self.assertIn(("tool", "perspective"), calls)

    def test_handle_shortcut_routes_between_object_atom_bond_and_generic_paths(self) -> None:
        canvas = SimpleNamespace(
            hover_atom_id=4,
            hover_bond_id=None,
        )
        service = CanvasChemdrawShortcutService(canvas)
        service.handle_object_shortcut = mock.Mock(return_value=False)
        service.handle_atom_hotkey = mock.Mock(return_value=True)
        service.handle_bond_hotkey = mock.Mock(return_value=True)
        service.handle_generic_hotkey = mock.Mock(return_value=True)

        event = _FakeKeyEvent(Qt.Key.Key_C, text="c")
        self.assertTrue(service.handle_shortcut(event))
        service.handle_atom_hotkey.assert_called_once_with(event, 4)

        canvas.hover_atom_id = None
        canvas.hover_bond_id = 7
        self.assertTrue(service.handle_shortcut(event))
        service.handle_bond_hotkey.assert_called_once_with(event, 7)

        canvas.hover_bond_id = None
        self.assertTrue(service.handle_shortcut(event))
        service.handle_generic_hotkey.assert_called_once_with(event)

        service.handle_object_shortcut.return_value = True
        self.assertTrue(service.handle_shortcut(event))

    def test_atom_hotkey_routes_to_prompt_marks_labels_and_sprouts(self) -> None:
        calls: list[tuple] = []
        canvas = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 1.0, 2.0)}, bonds=[]),
            _shortcut_modifiers=lambda event: CanvasView._shortcut_modifiers(event),
            prompt_atom_label=lambda atom_id: calls.append(("prompt", atom_id)),
            _atom_point=lambda atom_id: QPointF(1.0, 2.0),
            add_mark_for_atom=lambda atom_id, pos, kind: calls.append(("mark", atom_id, pos.x(), pos.y(), kind)),
            _atom_label_service=SimpleNamespace(
                add_or_update_atom_label=lambda atom_id, text, show_carbon=True: calls.append(
                    ("label", atom_id, text, show_carbon)
                )
            ),
            _sprout_bond_from_atom=lambda atom_id, style, order, cyclic=False: calls.append(
                ("bond", atom_id, style, order, cyclic)
            ),
            _sprout_acetyl_from_atom=lambda atom_id: calls.append(("acetyl", atom_id)),
            _sprout_benzene_from_atom=lambda atom_id: calls.append(("benzene", atom_id)),
            _sprout_regular_ring_from_atom=lambda atom_id, n: calls.append(("ring", atom_id, n)),
        )
        service = CanvasChemdrawShortcutService(canvas)

        self.assertFalse(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_C, text="c"), 99))
        self.assertFalse(
            service.handle_atom_hotkey(
                _FakeKeyEvent(Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier, text="c"),
                1,
            )
        )
        self.assertTrue(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_Return), 1))
        self.assertTrue(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_Plus, text="+"), 1))
        self.assertTrue(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_Minus, text="-"), 1))
        self.assertTrue(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_F, text="F"), 1))
        self.assertTrue(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_0, text="0"), 1))
        self.assertTrue(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_2, text="2"), 1))
        self.assertTrue(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_3, text="3"), 1))
        self.assertTrue(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_4, text="4"), 1))
        self.assertTrue(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_5, text="5"), 1))
        self.assertTrue(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_6, text="6"), 1))
        self.assertTrue(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_7, text="7"), 1))
        self.assertTrue(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_8, text="8"), 1))
        self.assertTrue(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_Z, text="z"), 1))
        self.assertTrue(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_U, text="u"), 1))
        self.assertTrue(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_V, text="v"), 1))
        self.assertFalse(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_unknown, text=""), 1))
        self.assertFalse(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_unknown, text="?"), 1))

        self.assertIn(("prompt", 1), calls)
        self.assertIn(("mark", 1, 1.0, 2.0, "plus"), calls)
        self.assertIn(("mark", 1, 1.0, 2.0, "minus"), calls)
        self.assertIn(("label", 1, "CF3", True), calls)
        self.assertIn(("bond", 1, "single", 1, True), calls)
        self.assertIn(("bond", 1, "hash", 1, False), calls)
        self.assertIn(("acetyl", 1), calls)
        self.assertIn(("benzene", 1), calls)
        self.assertIn(("ring", 1, 5), calls)
        self.assertIn(("ring", 1, 4), calls)
        self.assertIn(("ring", 1, 6), calls)
        self.assertIn(("bond", 1, "double", 2, False), calls)
        self.assertIn(("bond", 1, "triple", 3, False), calls)
        self.assertIn(("ring", 1, 3), calls)

    def test_bond_hotkey_routes_to_style_and_fusion_actions(self) -> None:
        calls: list[tuple] = []
        canvas = SimpleNamespace(
            model=SimpleNamespace(
                atoms={1: Atom("C", 1.0, 2.0), 2: Atom("O", 4.0, 5.0)},
                bonds=[Bond(1, 2, 1), None],
            ),
            _shortcut_modifiers=lambda event: CanvasView._shortcut_modifiers(event),
            apply_bond_style=lambda bond_id, style, order: calls.append(("style", bond_id, style, order)),
            _fuse_benzene_to_bond=lambda bond_id: calls.append(("benzene", bond_id)),
            _fuse_regular_ring_to_bond=lambda bond_id, n: calls.append(("ring", bond_id, n)),
            _fuse_chair_to_bond=lambda bond_id, mirrored=False: calls.append(("chair", bond_id, mirrored)),
        )
        service = CanvasChemdrawShortcutService(canvas)

        self.assertFalse(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_1, text="1"), 1))
        self.assertFalse(
            service.handle_bond_hotkey(
                _FakeKeyEvent(Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier, text="1"),
                0,
            )
        )
        self.assertTrue(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_B, Qt.KeyboardModifier.ShiftModifier, text="B"), 0))
        self.assertTrue(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_H, Qt.KeyboardModifier.ShiftModifier, text="H"), 0))
        self.assertTrue(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_1, text="1"), 0))
        self.assertTrue(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_2, text="2"), 0))
        self.assertTrue(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_3, text="3"), 0))
        self.assertTrue(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_B, text="b"), 0))
        self.assertTrue(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_W, text="w"), 0))
        self.assertTrue(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_H, text="h"), 0))
        self.assertTrue(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_A, text="a"), 0))
        self.assertTrue(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_6, text="6"), 0))
        self.assertTrue(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_0, text="0"), 0))
        self.assertFalse(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_X, text="x"), 0))

        self.assertIn(("style", 0, "bold_in", 2), calls)
        self.assertIn(("style", 0, "hash", 1), calls)
        self.assertIn(("style", 0, "single", 1), calls)
        self.assertIn(("style", 0, "double", 2), calls)
        self.assertIn(("style", 0, "triple", 3), calls)
        self.assertIn(("style", 0, "bold_in", 1), calls)
        self.assertIn(("style", 0, "wedge", 1), calls)
        self.assertIn(("benzene", 0), calls)
        self.assertIn(("ring", 0, 6), calls)
        self.assertIn(("chair", 0, True), calls)

    def test_service_resolver_reuses_bound_duck_typed_or_fresh_service(self) -> None:
        canvas = SimpleNamespace()
        bound = CanvasChemdrawShortcutService(canvas)
        canvas._chemdraw_shortcut_service = bound
        self.assertIs(canvas_chemdraw_shortcut_service_for(canvas), bound)

        injected = SimpleNamespace(
            handle_shortcut=mock.Mock(),
            handle_object_shortcut=mock.Mock(),
            handle_generic_hotkey=mock.Mock(),
            handle_atom_hotkey=mock.Mock(),
            handle_bond_hotkey=mock.Mock(),
        )
        other_canvas = SimpleNamespace(_chemdraw_shortcut_service=injected)
        self.assertIs(canvas_chemdraw_shortcut_service_for(other_canvas), injected)

        fresh_canvas = SimpleNamespace()
        resolved = canvas_chemdraw_shortcut_service_for(fresh_canvas)
        self.assertIsInstance(resolved, CanvasChemdrawShortcutService)
        self.assertIs(resolved.canvas, fresh_canvas)


if __name__ == "__main__":
    unittest.main()
