"""Regression tests for apply_paste_payload's defensive handling of malformed
clipboard payloads.

These use plain-Python fakes (no PyQt) so they run anywhere, including headless
environments. They lock in the guard that a foreign/corrupt payload — one that
carries the right format/version markers but contains a self-bond or an
out-of-range bond order — is skipped rather than crashing mid-paste (which would
leave atoms added with no bonds and no undo grouping).
"""

import unittest

from ui.scene_paste_apply_logic import apply_paste_payload


class _ModelLikeBondAdder:
    """Mimics core.model.MoleculeModel.add_bond's strictness."""

    def __init__(self) -> None:
        self._next_atom_id = 100
        self.added_bonds: list[tuple[int, int, int]] = []
        self.added_atoms: list[tuple[str, float, float]] = []

    def add_atom(self, element: str, x: float, y: float) -> int:
        atom_id = self._next_atom_id
        self._next_atom_id += 1
        self.added_atoms.append((element, x, y))
        return atom_id

    def add_bond(self, a: int, b: int, order: int) -> int:
        if type(a) is not int or type(b) is not int:
            raise ValueError("Bond endpoints must be atom ids.")
        if a == b:
            raise ValueError("Bond endpoints must be distinct.")
        if type(order) is not int or order not in (1, 2, 3):
            raise ValueError("Bond order must be 1, 2, or 3.")
        bond_id = len(self.added_bonds)
        self.added_bonds.append((a, b, order))
        return bond_id


def _noop(*_args, **_kwargs) -> None:
    return None


def _run(model: _ModelLikeBondAdder, *, atoms, bonds):
    return apply_paste_payload(
        atoms=atoms,
        bonds=bonds,
        rings=[],
        marks=[],
        scene_items=[],
        dx=0.0,
        dy=0.0,
        add_atom=model.add_atom,
        apply_atom_color=_noop,
        set_atom_annotation=_noop,
        add_or_update_atom_label=_noop,
        add_bond=model.add_bond,
        restore_bond_from_state=_noop,
        translated_scene_item_state=lambda state, **_kwargs: None,
        create_scene_item_from_state=lambda state: None,
    )


class ApplyPastePayloadHardeningTest(unittest.TestCase):
    def setUp(self) -> None:
        self.atoms = [
            {"id": 1, "element": "C", "x": 0.0, "y": 0.0},
            {"id": 2, "element": "O", "x": 1.0, "y": 0.0},
        ]

    def test_self_bond_is_skipped_without_raising(self) -> None:
        model = _ModelLikeBondAdder()
        result = _run(
            model,
            atoms=self.atoms,
            bonds=[{"a": 1, "b": 1, "order": 1, "style": "single", "color": "#000000"}],
        )
        self.assertEqual(model.added_bonds, [])
        self.assertEqual(result.atom_id_map, {1: 100, 2: 101})

    def test_out_of_range_order_is_skipped_without_raising(self) -> None:
        model = _ModelLikeBondAdder()
        _run(
            model,
            atoms=self.atoms,
            bonds=[{"a": 1, "b": 2, "order": 99, "style": "single", "color": "#000000"}],
        )
        self.assertEqual(model.added_bonds, [])

    def test_non_numeric_order_is_skipped_without_raising(self) -> None:
        model = _ModelLikeBondAdder()
        _run(
            model,
            atoms=self.atoms,
            bonds=[{"a": 1, "b": 2, "order": "x", "style": "single", "color": "#000000"}],
        )
        self.assertEqual(model.added_bonds, [])

    def test_perspective_state_is_remapped_to_new_atom_ids_and_translated(self) -> None:
        model = _ModelLikeBondAdder()
        applied: list[tuple[dict[int, tuple[float, float, float]], tuple[float, float, float] | None, tuple[float, float] | None]] = []

        apply_paste_payload(
            atoms=self.atoms,
            bonds=[],
            rings=[],
            marks=[],
            scene_items=[],
            dx=10.0,
            dy=20.0,
            add_atom=model.add_atom,
            apply_atom_color=_noop,
            set_atom_annotation=_noop,
            add_or_update_atom_label=_noop,
            add_bond=model.add_bond,
            restore_bond_from_state=_noop,
            translated_scene_item_state=lambda state, **_kwargs: None,
            create_scene_item_from_state=lambda state: None,
            perspective={
                "atom_coords_3d": [
                    {"atom_id": 1, "coords": [1.0, 2.0, 3.0]},
                    {"atom_id": 99, "coords": [9.0, 9.0, 9.0]},
                ],
                "projection_center_3d": [4.0, 5.0, 6.0],
                "projection_anchor_2d": [7.0, 8.0],
            },
            apply_perspective=lambda coords, center, anchor: applied.append((coords, center, anchor)),
        )

        self.assertEqual(applied, [({100: (11.0, 22.0, 3.0)}, (14.0, 25.0, 6.0), (17.0, 28.0))])

    def test_valid_bonds_are_still_applied(self) -> None:
        model = _ModelLikeBondAdder()
        result = _run(
            model,
            atoms=self.atoms,
            bonds=[
                {"a": 1, "b": 2, "order": 2, "style": "double", "color": "#999999"},
                {"a": 1, "b": 1, "order": 1, "style": "single", "color": "#000000"},
                {"a": 1, "b": 2, "order": 99, "style": "single", "color": "#000000"},
            ],
        )
        # Only the valid bond survives; malformed siblings are skipped.
        self.assertEqual(model.added_bonds, [(100, 101, 2)])
        self.assertTrue(result.has_changes())


if __name__ == "__main__":
    unittest.main()
