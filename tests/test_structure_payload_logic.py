import unittest

from chemvas.domain.document import Bond, MoleculeModel
from chemvas.features.insertion import (
    build_3d_conversion_payload,
    build_atom_annotations,
    build_structure_payload,
    build_submodel,
    expand_atom_ids_for_structure,
    model_with_atom_annotations,
)


class StructurePayloadLogicTest(unittest.TestCase):
    @staticmethod
    def _bounds_for(atom_ids: set[int]) -> tuple[float, float, float, float]:
        return (float(min(atom_ids)), -1.0, float(max(atom_ids)), 1.0)

    def _example_model(self) -> MoleculeModel:
        model = MoleculeModel()
        a = model.add_atom("C", -20.0, 0.0)
        b = model.add_atom("O", 0.0, 0.0)
        c = model.add_atom("N", 20.0, 0.0)
        model.atoms[a].color = "#111111"
        model.atoms[b].explicit_label = True
        model.bonds.append(Bond(a=a, b=b, order=2, style="double", color="#222222"))
        model.bonds.append(Bond(a=b, b=c, order=1, style="wedge", color="#333333"))
        return model

    def test_expand_atom_ids_for_structure_adds_selected_bond_endpoints(self) -> None:
        model = self._example_model()

        atom_ids = expand_atom_ids_for_structure(model, {0}, {1})

        self.assertEqual(atom_ids, {0, 1, 2})

    def test_build_submodel_with_atom_selection_includes_induced_bonds(self) -> None:
        model = self._example_model()

        submodel, bounds, id_map = build_submodel(
            model,
            {0, 1},
            set(),
            bounds_getter=self._bounds_for,
        )

        self.assertEqual(bounds, (0.0, -1.0, 1.0, 1.0))
        self.assertEqual(id_map, {0: 0, 1: 1})
        self.assertEqual(sorted(submodel.atoms), [0, 1])
        self.assertEqual(len(submodel.bonds), 1)
        self.assertEqual(submodel.atoms[0].color, "#111111")
        self.assertTrue(submodel.atoms[1].explicit_label)
        self.assertEqual(submodel.bonds[0].order, 2)
        self.assertEqual(submodel.bonds[0].style, "double")
        self.assertEqual(submodel.bonds[0].color, "#222222")

    def test_build_structure_payload_remaps_annotation_ids(self) -> None:
        model = self._example_model()
        mark_kinds_by_atom = {
            1: ["plus", "circled_plus"],
            2: ["radical", "circled_minus"],
        }

        export_model, atom_annotations, bounds = build_structure_payload(
            model,
            set(),
            {1},
            mark_kinds_by_atom,
            bounds_getter=self._bounds_for,
        )

        self.assertEqual(bounds, (1.0, -1.0, 2.0, 1.0))
        self.assertEqual(len(export_model.atoms), 2)
        self.assertEqual(len(export_model.bonds), 1)
        self.assertEqual(export_model.bonds[0].style, "wedge")
        self.assertEqual(
            atom_annotations,
            {
                0: {"formal_charge": 2},
                1: {"formal_charge": -1, "radical_electrons": 1},
            },
        )

    def test_build_structure_payload_rejects_empty_scope(self) -> None:
        model = self._example_model()

        with self.assertRaisesRegex(
            ValueError, "There is no chemical structure to export."
        ):
            build_structure_payload(
                model,
                set(),
                set(),
                {},
                bounds_getter=self._bounds_for,
            )

    def test_build_3d_conversion_payload_falls_back_to_whole_model(self) -> None:
        model = self._example_model()
        mark_kinds_by_atom = {
            0: ["minus"],
            2: ["radical"],
        }

        export_model, atom_annotations = build_3d_conversion_payload(
            model,
            set(),
            set(),
            mark_kinds_by_atom,
            bounds_getter=self._bounds_for,
        )

        self.assertEqual(len(export_model.atoms), 3)
        self.assertEqual(len(export_model.bonds), 2)
        self.assertEqual(atom_annotations[0], {"formal_charge": -1})
        self.assertEqual(atom_annotations[2], {"radical_electrons": 1})

    def test_model_with_atom_annotations_overlays_payload_without_mutating_source(
        self,
    ) -> None:
        model = self._example_model()
        model.atom_annotations = {1: {"formal_charge": 1}}

        identifier_model = model_with_atom_annotations(
            model,
            {
                1: {"formal_charge": -1, "radical_electrons": 0},
                2: {"radical_electrons": 1},
            },
        )

        self.assertIsNot(identifier_model, model)
        self.assertEqual(identifier_model.atoms, model.atoms)
        self.assertEqual(identifier_model.bonds, model.bonds)
        self.assertEqual(
            identifier_model.atom_annotations,
            {
                1: {"formal_charge": -1},
                2: {"radical_electrons": 1},
            },
        )
        self.assertEqual(model.atom_annotations, {1: {"formal_charge": 1}})

        cleared_model = model_with_atom_annotations(model, {})

        self.assertEqual(cleared_model.atom_annotations, {})

    def test_model_with_atom_annotations_preserves_model_when_payload_is_missing(
        self,
    ) -> None:
        model = self._example_model()

        self.assertIs(model_with_atom_annotations(model, None), model)

    def test_expand_build_and_annotation_helpers_skip_invalid_or_missing_entries(
        self,
    ) -> None:
        model = MoleculeModel()
        model.add_atom("C", 0.0, 0.0)
        model.bonds = [None, Bond(0, 9, 1, "wedge", "#334455")]

        selected = expand_atom_ids_for_structure(model, {0, 5}, {-1, 0, 1, 4})

        self.assertEqual(selected, {0, 5, 9})

        submodel, bounds, id_map = build_submodel(
            model,
            {0, 5},
            {0, 1, 4},
            bounds_getter=self._bounds_for,
        )

        self.assertEqual(bounds, (0.0, -1.0, 9.0, 1.0))
        self.assertEqual(id_map, {0: 0})
        self.assertEqual(sorted(submodel.atoms), [0])
        self.assertEqual(submodel.bonds, [])

        annotations = build_atom_annotations(
            {0, 7},
            id_map,
            {
                0: ["plus", "minus", "radical", "radical"],
                7: ["plus"],
            },
        )
        self.assertEqual(annotations, {0: {"radical_electrons": 2}})

    def test_build_structure_payload_rejects_nonempty_selection_without_exportable_atoms(
        self,
    ) -> None:
        model = MoleculeModel()
        model.bonds = [Bond(7, 8, 1)]

        with self.assertRaisesRegex(
            ValueError, "There is no chemical structure to export."
        ):
            build_structure_payload(
                model,
                set(),
                {0},
                {},
                bounds_getter=self._bounds_for,
            )


if __name__ == "__main__":
    unittest.main()
