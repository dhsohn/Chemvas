import unittest
from types import SimpleNamespace
from unittest import mock

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QPen
except ModuleNotFoundError:
    QPointF = None

if QPointF is not None:
    from chemvas.ui.main_window_icon_canvas_style import MainWindowIconCanvasStyle


def _window_for_canvas(canvas):
    return SimpleNamespace(
        runtime_state=SimpleNamespace(last_canvas_tab_index=0),
        tab_references=SimpleNamespace(
            active_canvas_or_none=mock.Mock(return_value=canvas)
        ),
    )


@unittest.skipUnless(
    QPointF is not None, "PyQt6 is required for main window icon canvas style tests"
)
class MainWindowIconCanvasStyleTest(unittest.TestCase):
    def test_delegates_renderer_style_and_bond_renderer_access(self) -> None:
        bond_pen = QPen()
        bold_pen = QPen()
        bold_pen.setWidthF(5.0)
        dotted_pen = QPen()
        renderer = SimpleNamespace(
            style=SimpleNamespace(
                bond_length_px=24.0,
                hash_spacing_px=4.0,
            ),
            bond_pen=mock.Mock(return_value=bond_pen),
            bold_bond_pen=mock.Mock(return_value=bold_pen),
            dotted_bond_pen=mock.Mock(return_value=dotted_pen),
        )
        bond_renderer = SimpleNamespace(
            ring_double_segments=mock.Mock(
                return_value=(
                    (0.0, 0.0, 1.0, 1.0),
                    (2.0, 3.0, 4.0, 5.0),
                    (6.0, 7.0, 8.0, 9.0),
                )
            )
        )
        canvas = SimpleNamespace(renderer=renderer, bond_renderer=bond_renderer)
        window = _window_for_canvas(canvas)
        style = MainWindowIconCanvasStyle(window)

        self.assertEqual(style.bond_length_px(), 24.0)
        self.assertEqual(style.hash_spacing_px(), 4.0)
        self.assertIs(style.bond_pen(), bond_pen)
        self.assertIs(style.bold_bond_pen(), bold_pen)
        self.assertIs(style.dotted_bond_pen(), dotted_pen)
        self.assertEqual(
            style.ring_double_inner_segment(
                QPointF(10.0, 11.0),
                QPointF(12.0, 13.0),
                QPointF(14.0, 15.0),
            ),
            (2.0, 3.0, 4.0, 5.0),
        )

        start_atom, end_atom, center = bond_renderer.ring_double_segments.call_args.args
        window.tab_references.active_canvas_or_none.assert_called()
        self.assertEqual((start_atom.x, start_atom.y), (10.0, 11.0))
        self.assertEqual((end_atom.x, end_atom.y), (12.0, 13.0))
        self.assertEqual(center, QPointF(14.0, 15.0))

    def test_missing_ring_double_segments_returns_none(self) -> None:
        renderer = SimpleNamespace(
            style=SimpleNamespace(
                bond_length_px=24.0,
                hash_spacing_px=4.0,
            ),
            bond_pen=mock.Mock(return_value=QPen()),
            bold_bond_pen=mock.Mock(return_value=QPen()),
            dotted_bond_pen=mock.Mock(return_value=QPen()),
        )
        canvas = SimpleNamespace(
            renderer=renderer,
            bond_renderer=SimpleNamespace(
                ring_double_segments=mock.Mock(return_value=None)
            ),
        )
        style = MainWindowIconCanvasStyle(_window_for_canvas(canvas))

        self.assertIsNone(
            style.ring_double_inner_segment(
                QPointF(0.0, 0.0), QPointF(1.0, 1.0), QPointF(0.5, 0.5)
            )
        )


if __name__ == "__main__":
    unittest.main()
