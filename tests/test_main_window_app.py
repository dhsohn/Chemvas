from __future__ import annotations

import unittest

from ui.main_window_app import (
    forget_window,
    open_new_window,
    open_windows,
    register_window,
    reset_window_registry,
)


class _FakeWindow:
    def __init__(self) -> None:
        self.shown = False
        self.moved_to: tuple[int, int] | None = None

    def show(self) -> None:
        self.shown = True

    def geometry(self):
        class _Geo:
            def x(self_inner) -> int:
                return 100

            def y(self_inner) -> int:
                return 50

        return _Geo()

    def move(self, x: int, y: int) -> None:
        self.moved_to = (x, y)


class MainWindowAppRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_window_registry()

    def tearDown(self) -> None:
        reset_window_registry()

    def test_register_is_idempotent_and_forget_removes(self) -> None:
        window = _FakeWindow()
        register_window(window)
        register_window(window)
        self.assertEqual(open_windows(), (window,))
        forget_window(window)
        self.assertEqual(open_windows(), ())

    def test_forget_unknown_window_is_silent(self) -> None:
        forget_window(_FakeWindow())
        self.assertEqual(open_windows(), ())

    def test_open_new_window_registers_shows_and_returns(self) -> None:
        created: list[_FakeWindow] = []

        def factory() -> _FakeWindow:
            window = _FakeWindow()
            created.append(window)
            return window

        window = open_new_window(window_factory=factory)

        self.assertEqual(len(created), 1)
        self.assertIs(window, created[0])
        self.assertIn(window, open_windows())
        self.assertTrue(window.shown)

    def test_open_new_window_cascades_from_reference(self) -> None:
        reference = _FakeWindow()
        window = open_new_window(reference, window_factory=_FakeWindow)
        self.assertEqual(window.moved_to, (132, 82))

    def test_reset_clears_registry(self) -> None:
        register_window(_FakeWindow())
        reset_window_registry()
        self.assertEqual(open_windows(), ())


if __name__ == "__main__":
    unittest.main()
