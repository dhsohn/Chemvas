import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
except ModuleNotFoundError:
    QPointF = None

if QPointF is not None:
    from core.model import Atom, Bond
    from ui.canvas_chemdraw_shortcut_service import CanvasChemdrawShortcutService
    from ui.canvas_hover_state import set_hover_atom_id_for, set_hover_bond_id_for
    from ui.input_view_access import shortcut_modifiers_for


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


def _shortcut_service(canvas, *, scene_transform_controller=None, tool_mode_controller=None, mark_scene_service=None):
    services = getattr(canvas, "services", None)
    if scene_transform_controller is None:
        scene_transform_controller = getattr(
            services,
            "scene_transform_controller",
            SimpleNamespace(
                flip_selected_items=mock.Mock(),
                apply_bond_style=mock.Mock(),
            ),
        )
    if tool_mode_controller is None:
        tool_mode_controller = getattr(
            services,
            "tool_mode_controller",
            SimpleNamespace(
                set_tool=mock.Mock(),
                set_bond_style=mock.Mock(),
            ),
        )
    if mark_scene_service is None:
        mark_scene_service = getattr(services, "canvas_mark_scene_service", None)
    return CanvasChemdrawShortcutService(
        canvas,
        scene_transform_controller=scene_transform_controller,
        tool_mode_controller=tool_mode_controller,
        mark_scene_service=mark_scene_service,
    )


@unittest.skipUnless(QPointF is not None, "PyQt6 is required for ChemDraw shortcut service tests")
class CanvasChemDrawShortcutServiceTest(unittest.TestCase):
    def test_object_and_generic_shortcuts_dispatch_expected_actions(self) -> None:
        calls: list[tuple] = []
        scene_transform_controller = SimpleNamespace(
            flip_selected_items=lambda *, horizontal: calls.append(("flip", horizontal)),
            rotate_selected_items=lambda angle: calls.append(("rotate", angle)),
            translate_selected_items=lambda dx, dy: (calls.append(("translate", dx, dy)), True)[1],
        )
        tool_mode_controller = SimpleNamespace(
            set_tool=lambda tool: calls.append(("tool", tool)),
            set_bond_style=lambda style, order: calls.append(("bond_style", style, order)),
            set_arrow_type=lambda arrow_type: calls.append(("arrow_type", arrow_type)),
            set_bracket_type=lambda bracket_type: calls.append(("bracket_type", bracket_type)),
            set_orbital_type=lambda orbital_type: calls.append(("orbital_type", orbital_type)),
            set_mark_kind=lambda kind: calls.append(("mark_kind", kind)),
        )
        canvas = SimpleNamespace(
            _shortcut_modifiers=shortcut_modifiers_for,
            services=SimpleNamespace(
                scene_transform_controller=scene_transform_controller,
                tool_mode_controller=tool_mode_controller,
            ),
        )
        service = _shortcut_service(canvas)

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
        self.assertTrue(service.handle_object_shortcut(_FakeKeyEvent(Qt.Key.Key_Up, Qt.KeyboardModifier.AltModifier)))
        self.assertTrue(
            service.handle_object_shortcut(_FakeKeyEvent(Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier))
        )
        self.assertTrue(
            service.handle_object_shortcut(_FakeKeyEvent(Qt.Key.Key_Left, Qt.KeyboardModifier.AltModifier))
        )
        self.assertTrue(
            service.handle_object_shortcut(_FakeKeyEvent(Qt.Key.Key_Right, Qt.KeyboardModifier.AltModifier))
        )
        self.assertTrue(
            service.handle_object_shortcut(_FakeKeyEvent(Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier))
        )

        self.assertTrue(service.handle_generic_hotkey(_FakeKeyEvent(Qt.Key.Key_Space)))
        self.assertTrue(service.handle_generic_hotkey(_FakeKeyEvent(Qt.Key.Key_X)))
        self.assertTrue(service.handle_generic_hotkey(_FakeKeyEvent(Qt.Key.Key_E)))
        self.assertTrue(service.handle_generic_hotkey(_FakeKeyEvent(Qt.Key.Key_T, Qt.KeyboardModifier.ShiftModifier)))
        self.assertTrue(service.handle_generic_hotkey(_FakeKeyEvent(Qt.Key.Key_G, Qt.KeyboardModifier.ShiftModifier)))
        self.assertTrue(service.handle_generic_hotkey(_FakeKeyEvent(Qt.Key.Key_E, Qt.KeyboardModifier.ShiftModifier)))
        self.assertTrue(service.handle_generic_hotkey(_FakeKeyEvent(Qt.Key.Key_D, Qt.KeyboardModifier.AltModifier)))
        self.assertFalse(service.handle_generic_hotkey(_FakeKeyEvent(Qt.Key.Key_Z)))

        self.assertIn(("flip", True), calls)
        self.assertIn(("flip", False), calls)
        self.assertIn(("rotate", -15.0), calls)
        self.assertIn(("rotate", 15.0), calls)
        self.assertIn(("rotate", -1.0), calls)
        self.assertIn(("rotate", 1.0), calls)
        self.assertIn(("translate", 10.0, 0.0), calls)
        self.assertIn(("tool", "select"), calls)
        self.assertIn(("bond_style", "single", 1), calls)
        self.assertIn(("arrow_type", "reaction"), calls)
        self.assertIn(("bracket_type", "square_pair"), calls)
        self.assertIn(("orbital_type", "s"), calls)
        self.assertIn(("mark_kind", "plus"), calls)
        self.assertIn(("tool", "perspective"), calls)

    def test_handle_shortcut_routes_between_object_atom_bond_and_generic_paths(self) -> None:
        canvas = SimpleNamespace()
        set_hover_atom_id_for(canvas, 4)
        service = _shortcut_service(canvas)
        service.handle_object_shortcut = mock.Mock(return_value=False)
        service.handle_atom_hotkey = mock.Mock(return_value=True)
        service.handle_bond_hotkey = mock.Mock(return_value=True)
        service.handle_generic_hotkey = mock.Mock(return_value=True)

        event = _FakeKeyEvent(Qt.Key.Key_C, text="c")
        self.assertTrue(service.handle_shortcut(event))
        service.handle_atom_hotkey.assert_called_once_with(event, 4)

        set_hover_atom_id_for(canvas, None)
        set_hover_bond_id_for(canvas, 7)
        self.assertTrue(service.handle_shortcut(event))
        service.handle_bond_hotkey.assert_called_once_with(event, 7)

        set_hover_bond_id_for(canvas, None)
        self.assertTrue(service.handle_shortcut(event))
        service.handle_generic_hotkey.assert_called_once_with(event)

        service.handle_object_shortcut.return_value = True
        self.assertTrue(service.handle_shortcut(event))

    def test_atom_hotkey_routes_to_prompt_marks_labels_and_sprouts(self) -> None:
        calls: list[tuple] = []
        canvas = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 1.0, 2.0)}, bonds=[]),
            _shortcut_modifiers=shortcut_modifiers_for,
            services=SimpleNamespace(
                canvas_mark_scene_service=SimpleNamespace(
                    add_mark_for_atom=lambda atom_id, pos, kind: calls.append(
                        ("mark", atom_id, pos.x(), pos.y(), kind)
                    )
                ),
                atom_label_service=SimpleNamespace(
                    add_or_update_atom_label=lambda atom_id, text, show_carbon=True: calls.append(
                        ("label", atom_id, text, show_carbon)
                    ),
                    prompt_atom_label=lambda atom_id: calls.append(("prompt", atom_id)),
                ),
                structure_build_service=SimpleNamespace(
                    sprout_bond_from_atom=lambda atom_id, style, order, cyclic=False: calls.append(
                        ("bond", atom_id, style, order, cyclic)
                    ),
                    sprout_acetyl_from_atom=lambda atom_id: calls.append(("acetyl", atom_id)),
                    sprout_benzene_from_atom=lambda atom_id: calls.append(("benzene", atom_id)),
                    sprout_dimethyl_from_atom=lambda atom_id: calls.append(("dimethyl", atom_id)),
                    sprout_regular_ring_from_atom=lambda atom_id, n: calls.append(("ring", atom_id, n)),
                ),
            ),
        )
        service = _shortcut_service(canvas)

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
        self.assertTrue(service.handle_atom_hotkey(_FakeKeyEvent(Qt.Key.Key_9, text="9"), 1))
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
        self.assertIn(("dimethyl", 1), calls)
        self.assertIn(("benzene", 1), calls)
        self.assertIn(("ring", 1, 5), calls)
        self.assertIn(("ring", 1, 4), calls)
        self.assertIn(("ring", 1, 6), calls)
        self.assertIn(("bond", 1, "double", 2, False), calls)
        self.assertIn(("bond", 1, "triple", 3, False), calls)
        self.assertIn(("ring", 1, 3), calls)

    def test_bond_hotkey_routes_to_style_and_fusion_actions(self) -> None:
        calls: list[tuple] = []
        scene_transform_controller = SimpleNamespace(
            apply_bond_style=lambda bond_id, style, order: calls.append(("style", bond_id, style, order))
        )
        canvas = SimpleNamespace(
            model=SimpleNamespace(
                atoms={1: Atom("C", 1.0, 2.0), 2: Atom("O", 4.0, 5.0)},
                bonds=[Bond(1, 2, 1), None, Bond(1, 2, 2)],
            ),
            _shortcut_modifiers=shortcut_modifiers_for,
            services=SimpleNamespace(
                scene_transform_controller=scene_transform_controller,
                structure_build_service=SimpleNamespace(
                    fuse_benzene_to_bond=lambda bond_id: calls.append(("benzene", bond_id)),
                    fuse_regular_ring_to_bond=lambda bond_id, n: calls.append(("ring", bond_id, n)),
                    fuse_chair_to_bond=lambda bond_id, mirrored=False: calls.append(("chair", bond_id, mirrored)),
                ),
            ),
        )
        service = _shortcut_service(canvas)

        self.assertFalse(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_1, text="1"), 1))
        self.assertFalse(
            service.handle_bond_hotkey(
                _FakeKeyEvent(Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier, text="1"),
                0,
            )
        )
        self.assertTrue(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_B, Qt.KeyboardModifier.ShiftModifier, text="B"), 0))
        self.assertTrue(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_H, Qt.KeyboardModifier.ShiftModifier, text="H"), 0))
        self.assertTrue(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_D, Qt.KeyboardModifier.ShiftModifier, text="D"), 0))
        self.assertTrue(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_D, text="d"), 0))
        self.assertFalse(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_C, text="c"), 0))
        self.assertTrue(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_C, text="c"), 2))
        self.assertTrue(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_L, text="l"), 2))
        self.assertTrue(service.handle_bond_hotkey(_FakeKeyEvent(Qt.Key.Key_R, text="r"), 2))
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
        self.assertIn(("style", 0, "dotted", 1), calls)
        self.assertIn(("style", 0, "dotted_double", 2), calls)
        self.assertIn(("style", 2, "double_center", 2), calls)
        self.assertIn(("style", 2, "double", 2), calls)
        self.assertIn(("style", 2, "double_outer", 2), calls)
        self.assertIn(("style", 0, "single", 1), calls)
        self.assertIn(("style", 0, "double", 2), calls)
        self.assertIn(("style", 0, "triple", 3), calls)
        self.assertIn(("style", 0, "bold_in", 1), calls)
        self.assertIn(("style", 0, "wedge", 1), calls)
        self.assertIn(("benzene", 0), calls)
        self.assertIn(("ring", 0, 6), calls)
        self.assertIn(("chair", 0, True), calls)

if __name__ == "__main__":
    unittest.main()
