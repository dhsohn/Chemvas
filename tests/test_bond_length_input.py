from unittest.mock import Mock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QToolButton

from chemvas.ui.main_window_context_bar_widgets import bond_length_input


@pytest.fixture
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.mark.parametrize("value", [300.0, 0.5, 20.123456789, 1073741823.0])
def test_loaded_legal_value_is_not_clamped_or_committed_on_focus(app, value):
    changed = Mock()
    widget, spin = bond_length_input(value, changed)
    try:
        assert spin.value() == value
        spin.editingFinished.emit()
        changed.assert_not_called()
    finally:
        widget.close()


@pytest.mark.parametrize("value,target", [(20.0, "300"), (300.0, "500")])
def test_typing_larger_legal_length_commits_the_complete_number(app, value, target):
    changed = Mock()
    widget, spin = bond_length_input(value, changed)
    widget.show()
    try:
        assert QTest.qWaitForWindowExposed(widget)
        spin.setFocus()
        spin.selectAll()
        QTest.keyClicks(spin, target)
        QTest.keyClick(spin, Qt.Key.Key_Return)
        changed.assert_called_once_with(float(target))
    finally:
        widget.close()


@pytest.mark.parametrize(
    "direction,expected", [("Increase", 301.0), ("Decrease", 299.0)]
)
def test_stepper_starts_from_the_loaded_value(app, direction, expected):
    changed = Mock()
    widget, spin = bond_length_input(300.0, changed)
    widget.show()
    try:
        assert QTest.qWaitForWindowExposed(widget)
        button = next(
            button
            for button in widget.findChildren(QToolButton)
            if button.toolTip() == f"{direction} bond length"
        )
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert spin.value() == expected
        changed.assert_called_once_with(expected)
    finally:
        widget.close()


@pytest.mark.parametrize("value", [0.5, 5e-324, 1073741823.0])
def test_boundaries_never_emit_zero_or_a_clamped_value_without_an_edit(app, value):
    changed = Mock()
    widget, spin = bond_length_input(value, changed)
    try:
        # Qt can round the smallest subnormal to zero at its 323-decimal
        # precision limit. Merely visiting that document is still a no-op.
        spin.editingFinished.emit()
        changed.assert_not_called()
        spin.setValue(0)
        spin.editingFinished.emit()
        changed.assert_not_called()
    finally:
        widget.close()


def test_switching_document_restores_its_precision_and_step_baseline(app):
    changed = Mock()
    widget, spin = bond_length_input(300, changed)
    try:
        for value in (20.123456789, 0.5, 500, 20):
            spin.sync_value(value)
            assert spin.value() == value
            spin.editingFinished.emit()
        changed.assert_not_called()
    finally:
        widget.close()
