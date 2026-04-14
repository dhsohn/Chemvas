import unittest
from pathlib import Path
from unittest import mock
import sys

ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.model import MoleculeModel
from core.rdkit_adapter import Molecule3DAtom, Molecule3DBond, Molecule3DScene
from core.xtb_adapter import XTBAdapter


class XTBAdapterTest(unittest.TestCase):
    @staticmethod
    def _base_scene() -> Molecule3DScene:
        return Molecule3DScene(
            atoms=(
                Molecule3DAtom("C", 0.0, 0.0, 0.0),
                Molecule3DAtom("O", 1.2, 0.0, 0.0),
                Molecule3DAtom("H", -0.6, 0.8, -0.1),
            ),
            bonds=(
                Molecule3DBond(0, 1, 2),
                Molecule3DBond(0, 2, 1),
            ),
        )

    @staticmethod
    def _which_side_effect(name: str) -> str | None:
        executables = {
            "xtb": "/usr/local/bin/xtb",
            "crest": "/usr/local/bin/crest",
        }
        return executables.get(name)

    def test_optimize_returns_canvas_model_and_metrics(self) -> None:
        scene = self._base_scene()
        rdkit = mock.Mock()
        rdkit.model_to_3d_scene.return_value = scene
        adapter = XTBAdapter(rdkit)

        def _fake_run(command, cwd, capture_output, text, timeout, check):
            Path(cwd, "xtbopt.xyz").write_text(
                "\n".join(
                    [
                        "3",
                        "opt",
                        "C 0.100000 0.200000 0.000000",
                        "O 1.300000 0.100000 0.100000",
                        "H -0.500000 0.900000 -0.100000",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            return mock.Mock(
                returncode=0,
                stdout="TOTAL ENERGY      -12.345678\nGRADIENT NORM      0.000321\nHOMO-LUMO GAP      5.4321\n",
                stderr="",
            )

        with (
            mock.patch("core.xtb_adapter.shutil.which", return_value="/usr/local/bin/xtb"),
            mock.patch("core.xtb_adapter.subprocess.run", side_effect=_fake_run),
        ):
            result = adapter.optimize(MoleculeModel(), bond_length_px=24.0)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertAlmostEqual(result.total_energy_hartree or 0.0, -12.345678)
        self.assertAlmostEqual(result.gradient_norm or 0.0, 0.000321)
        self.assertAlmostEqual(result.homo_lumo_gap_ev or 0.0, 5.4321)
        self.assertIsNotNone(result.optimized_scene)
        self.assertIsNotNone(result.canvas_model)
        assert result.canvas_model is not None
        self.assertEqual(len(result.canvas_model.atoms), 2)
        self.assertEqual(sum(1 for bond in result.canvas_model.bonds if bond is not None), 1)

    def test_compare_reports_delta_energy(self) -> None:
        scene = self._base_scene()
        rdkit = mock.Mock()
        rdkit.model_to_3d_scene.side_effect = [scene, scene]
        adapter = XTBAdapter(rdkit)
        outputs = iter(
            [
                mock.Mock(returncode=0, stdout="TOTAL ENERGY      -10.000000\nHOMO-LUMO GAP      4.0000\n", stderr=""),
                mock.Mock(returncode=0, stdout="TOTAL ENERGY      -10.500000\nHOMO-LUMO GAP      3.5000\n", stderr=""),
            ]
        )

        with (
            mock.patch("core.xtb_adapter.shutil.which", return_value="/usr/local/bin/xtb"),
            mock.patch("core.xtb_adapter.subprocess.run", side_effect=lambda *args, **kwargs: next(outputs)),
        ):
            result = adapter.compare(MoleculeModel(), MoleculeModel())

        self.assertIsNotNone(result)
        assert result is not None
        self.assertAlmostEqual(result.delta_energy_kcal_mol or 0.0, -313.7515)

    def test_compare_pair_singlepoint_is_available_as_explicit_workflow(self) -> None:
        adapter = XTBAdapter(mock.Mock())
        expected = mock.Mock()
        with mock.patch.object(
            adapter,
            "compare_pair_singlepoint",
            return_value=expected,
        ) as compare_pair:
            result = adapter.compare(MoleculeModel(), MoleculeModel())

        self.assertIs(result, expected)
        compare_pair.assert_called_once()

    def test_optimize_fails_when_xtb_is_unavailable(self) -> None:
        rdkit = mock.Mock()
        rdkit.model_to_3d_scene.return_value = Molecule3DScene(atoms=(), bonds=())
        adapter = XTBAdapter(rdkit)

        with mock.patch("core.xtb_adapter.shutil.which", return_value=None):
            result = adapter.optimize(MoleculeModel())

        self.assertIsNone(result)
        self.assertEqual(
            adapter.last_error,
            "GFN2-xTB executable not found. Install `xtb` to enable calculations.",
        )

    def test_conformer_search_returns_ensemble_and_canvas_model(self) -> None:
        scene = self._base_scene()
        rdkit = mock.Mock()
        rdkit.model_to_3d_scene.return_value = scene
        adapter = XTBAdapter(rdkit)

        def _fake_run(command, cwd, capture_output, text, timeout, check):
            self.assertEqual(
                command,
                [
                    "/usr/local/bin/crest",
                    "input.xyz",
                    "--gfn2",
                    "-T",
                    "4",
                    "--chrg",
                    "1",
                    "--uhf",
                    "1",
                ],
            )
            Path(cwd, "crest_conformers.xyz").write_text(
                "\n".join(
                    [
                        "3",
                        "conf1",
                        "C 0.000000 0.000000 0.000000",
                        "O 1.210000 0.000000 0.000000",
                        "H -0.550000 0.820000 -0.050000",
                        "3",
                        "conf2",
                        "C 0.020000 0.010000 0.000000",
                        "O 1.230000 0.020000 0.010000",
                        "H -0.520000 0.810000 -0.030000",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            return mock.Mock(
                returncode=0,
                stdout="TOTAL ENERGY      -15.432100\nHOMO-LUMO GAP      4.8765\n",
                stderr="",
            )

        with (
            mock.patch("core.xtb_adapter.shutil.which", side_effect=self._which_side_effect),
            mock.patch("core.xtb_adapter.subprocess.run", side_effect=_fake_run),
        ):
            result = adapter.conformer_search(
                MoleculeModel(),
                atom_annotations={0: {"formal_charge": 1, "radical_electrons": 1}},
                bond_length_px=30.0,
                threads=4,
            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.mode, "crest")
        self.assertEqual(result.conformer_count, 2)
        self.assertAlmostEqual(result.total_energy_hartree or 0.0, -15.4321)
        self.assertEqual(result.command[0], "/usr/local/bin/crest")
        self.assertIsNotNone(result.best_xyz)
        self.assertIsNotNone(result.best_scene)
        self.assertIsNotNone(result.canvas_model)
        assert result.canvas_model is not None
        self.assertEqual(len(result.canvas_model.atoms), 2)

    def test_conformer_search_fails_when_crest_is_unavailable(self) -> None:
        rdkit = mock.Mock()
        rdkit.model_to_3d_scene.return_value = self._base_scene()
        adapter = XTBAdapter(rdkit)

        with mock.patch(
            "core.xtb_adapter.shutil.which",
            side_effect=lambda name: "/usr/local/bin/xtb" if name == "xtb" else None,
        ):
            result = adapter.conformer_search(MoleculeModel())

        self.assertIsNone(result)
        self.assertEqual(
            adapter.last_error,
            "CREST executable not found. Install `crest` to enable conformer searches.",
        )

    def test_reaction_path_parses_barriers_and_collects_output_files(self) -> None:
        scene = self._base_scene()
        rdkit = mock.Mock()
        rdkit.model_to_3d_scene.side_effect = [scene, scene]
        adapter = XTBAdapter(rdkit)

        def _fake_run(command, cwd, capture_output, text, timeout, check):
            self.assertEqual(
                command,
                [
                    "/usr/local/bin/xtb",
                    "start.xyz",
                    "--path",
                    "end.xyz",
                    "--input",
                    "path.inp",
                    "--gfn",
                    "2",
                ],
            )
            path_input = Path(cwd, "path.inp").read_text(encoding="utf-8")
            self.assertIn("npoint=30", path_input)
            self.assertIn("kpush=0.004", path_input)
            Path(cwd, "xtbpath_0.xyz").write_text(
                "3\npath\nC 0.0 0.0 0.0\nO 1.2 0.0 0.0\nH -0.6 0.8 -0.1\n",
                encoding="utf-8",
            )
            Path(cwd, "xtbpath_ts.xyz").write_text(
                "3\nts\nC 0.1 0.0 0.0\nO 1.3 0.1 0.0\nH -0.5 0.7 -0.1\n",
                encoding="utf-8",
            )
            return mock.Mock(
                returncode=0,
                stdout=(
                    "forward  barrier (kcal)  :    12.420\n"
                    "backward barrier (kcal)  :    37.497\n"
                    "reaction energy  (kcal)  :   -25.076\n"
                ),
                stderr="",
            )

        with (
            mock.patch("core.xtb_adapter.shutil.which", side_effect=self._which_side_effect),
            mock.patch("core.xtb_adapter.subprocess.run", side_effect=_fake_run),
        ):
            result = adapter.reaction_path(
                MoleculeModel(),
                MoleculeModel(),
                path_settings={"npoint": 30, "kpush": 0.004},
            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.mode, "path")
        self.assertAlmostEqual(result.forward_barrier_kcal_mol or 0.0, 12.42)
        self.assertAlmostEqual(result.backward_barrier_kcal_mol or 0.0, 37.497)
        self.assertAlmostEqual(result.reaction_energy_kcal_mol or 0.0, -25.076)
        self.assertIn("path", result.path_xyz or "")
        self.assertIn("ts", result.transition_state_xyz or "")

    def test_reaction_path_rejects_charge_or_spin_mismatch(self) -> None:
        scene = self._base_scene()
        rdkit = mock.Mock()
        rdkit.model_to_3d_scene.side_effect = [scene, scene]
        adapter = XTBAdapter(rdkit)

        with mock.patch("core.xtb_adapter.shutil.which", return_value="/usr/local/bin/xtb"):
            result = adapter.reaction_path(
                MoleculeModel(),
                MoleculeModel(),
                input_annotations={0: {"formal_charge": 0, "radical_electrons": 0}},
                output_annotations={0: {"formal_charge": 1, "radical_electrons": 0}},
            )

        self.assertIsNone(result)
        self.assertEqual(
            adapter.last_error,
            "Reaction path analysis requires matching total charge and radical count for input and output structures.",
        )


if __name__ == "__main__":
    unittest.main()
