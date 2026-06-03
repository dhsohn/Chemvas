import unittest

from ui.selection_press_logic import (
    SelectionPressContext,
    SelectionPressDecision,
    plan_selection_press,
)


class SelectionPressLogicTest(unittest.TestCase):
    def test_drag_current_selection_when_selection_hit_and_target_exists(self) -> None:
        decision = plan_selection_press(
            SelectionPressContext(
                has_selection_target=True,
                hits_current_selection=True,
                has_preferred_structure=True,
            )
        )

        self.assertEqual(decision, SelectionPressDecision(action="drag_current_selection"))

    def test_reselect_preferred_when_current_selection_missed(self) -> None:
        decision = plan_selection_press(
            SelectionPressContext(
                has_selection_target=True,
                hits_current_selection=False,
                has_preferred_structure=True,
            )
        )

        self.assertEqual(decision, SelectionPressDecision(action="reselect_preferred_and_drag"))

    def test_reselect_preferred_when_no_current_selection_target_exists(self) -> None:
        decision = plan_selection_press(
            SelectionPressContext(
                has_selection_target=False,
                hits_current_selection=False,
                has_preferred_structure=True,
            )
        )

        self.assertEqual(decision, SelectionPressDecision(action="reselect_preferred_and_drag"))

    def test_ignore_when_no_selection_target_and_no_preferred_structure(self) -> None:
        decision = plan_selection_press(
            SelectionPressContext(
                has_selection_target=False,
                hits_current_selection=False,
                has_preferred_structure=False,
            )
        )

        self.assertEqual(decision, SelectionPressDecision(action="ignore"))

    def test_ignore_when_selection_missed_and_no_preferred_structure(self) -> None:
        decision = plan_selection_press(
            SelectionPressContext(
                has_selection_target=True,
                hits_current_selection=False,
                has_preferred_structure=False,
            )
        )

        self.assertEqual(decision, SelectionPressDecision(action="ignore"))


if __name__ == "__main__":
    unittest.main()
