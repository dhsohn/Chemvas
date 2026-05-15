import unittest

from ui.insert_mode_logic import (
    InsertSessionState,
    begin_smiles_insert,
    begin_template_insert,
    build_template_insert_request,
    cancel_smiles_insert,
    cancel_template_insert,
    clear_insert_session,
)


class InsertModeLogicTest(unittest.TestCase):
    def test_begin_template_insert_normalizes_style_and_clears_smiles_state(self) -> None:
        state = InsertSessionState(
            smiles_active=True,
            smiles_text="CCO",
            smiles_center=(10.0, 20.0),
        )

        next_state = begin_template_insert(state, 6, " Chair ")

        assert next_state is not None
        self.assertTrue(next_state.template_active)
        self.assertEqual(next_state.template_ring_size, 6)
        self.assertEqual(next_state.template_ring_style, "chair")
        self.assertFalse(next_state.smiles_active)
        self.assertIsNone(next_state.smiles_text)
        self.assertIsNone(next_state.smiles_center)

    def test_begin_template_insert_rejects_invalid_inputs(self) -> None:
        state = InsertSessionState()

        self.assertIsNone(begin_template_insert(state, 2, "regular"))
        self.assertIsNone(begin_template_insert(state, 6, "weird"))

    def test_cancel_template_insert_preserves_smiles_state(self) -> None:
        state = InsertSessionState(
            template_active=True,
            template_ring_size=5,
            template_ring_style="regular",
            smiles_active=True,
            smiles_text="CO",
            smiles_center=(4.0, 6.0),
        )

        next_state = cancel_template_insert(state)

        self.assertFalse(next_state.template_active)
        self.assertIsNone(next_state.template_ring_size)
        self.assertIsNone(next_state.template_ring_style)
        self.assertTrue(next_state.smiles_active)
        self.assertEqual(next_state.smiles_text, "CO")
        self.assertEqual(next_state.smiles_center, (4.0, 6.0))

    def test_begin_smiles_insert_strips_text_and_clears_template_state(self) -> None:
        state = InsertSessionState(
            template_active=True,
            template_ring_size=6,
            template_ring_style="benzene",
        )

        next_state = begin_smiles_insert(state, "  NCCO  ", (1.5, 2.5))

        assert next_state is not None
        self.assertFalse(next_state.template_active)
        self.assertIsNone(next_state.template_ring_size)
        self.assertIsNone(next_state.template_ring_style)
        self.assertTrue(next_state.smiles_active)
        self.assertEqual(next_state.smiles_text, "NCCO")
        self.assertEqual(next_state.smiles_center, (1.5, 2.5))

    def test_begin_smiles_insert_rejects_blank_text_or_missing_center(self) -> None:
        state = InsertSessionState()

        self.assertIsNone(begin_smiles_insert(state, "   ", (0.0, 0.0)))
        self.assertIsNone(begin_smiles_insert(state, "CC", None))

    def test_cancel_smiles_insert_preserves_template_state(self) -> None:
        state = InsertSessionState(
            template_active=True,
            template_ring_size=7,
            template_ring_style="regular",
            smiles_active=True,
            smiles_text="CC",
            smiles_center=(0.0, 1.0),
        )

        next_state = cancel_smiles_insert(state)

        self.assertTrue(next_state.template_active)
        self.assertEqual(next_state.template_ring_size, 7)
        self.assertEqual(next_state.template_ring_style, "regular")
        self.assertFalse(next_state.smiles_active)
        self.assertIsNone(next_state.smiles_text)
        self.assertIsNone(next_state.smiles_center)

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
        self.assertIsNone(build_template_insert_request(clear_insert_session(), (0.0, 0.0), None))


if __name__ == "__main__":
    unittest.main()
