import unittest

from chemvas.ui.insert.insert_mode_logic import (
    InsertSessionState,
    begin_template_insert,
    build_template_insert_request,
    clear_insert_session,
)


class InsertModeLogicTest(unittest.TestCase):
    def test_begin_template_insert_normalizes_style(
        self,
    ) -> None:
        next_state = begin_template_insert(6, " Chair ")

        assert next_state is not None
        self.assertTrue(next_state.template_active)
        self.assertEqual(next_state.template_ring_size, 6)
        self.assertEqual(next_state.template_ring_style, "chair")

    def test_begin_template_insert_rejects_invalid_inputs(self) -> None:
        self.assertIsNone(begin_template_insert(2, "regular"))
        self.assertIsNone(begin_template_insert(6, "weird"))

    def test_build_template_insert_request_uses_normalized_state(self) -> None:
        state = InsertSessionState(
            template_active=True,
            template_ring_size=5,
            template_ring_style="boat",
        )

        request = build_template_insert_request(state, (8.0, 9.0), 3)

        assert request is not None
        self.assertEqual(request.ring_size, 5)
        self.assertEqual(request.cursor_pos, (8.0, 9.0))
        self.assertEqual(request.bond_id, 3)
        self.assertEqual(request.ring_style, "boat")

    def test_build_template_insert_request_returns_none_when_inactive(self) -> None:
        self.assertIsNone(
            build_template_insert_request(clear_insert_session(), (0.0, 0.0), None)
        )
