from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from core.model import MoleculeModel
from core.rdkit_adapter import Molecule3DAtom, Molecule3DBond, Molecule3DScene, RDKitAdapter


_TOTAL_ENERGY_RE = re.compile(r"TOTAL ENERGY\s+(-?\d+(?:\.\d+)?)")
_GAP_RE = re.compile(r"HOMO-LUMO GAP\s+(-?\d+(?:\.\d+)?)")
_GRADIENT_RE = re.compile(r"GRADIENT NORM\s+(-?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)")
_FORWARD_BARRIER_RE = re.compile(r"forward\s+barrier\s+\(kcal\)\s*:\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
_BACKWARD_BARRIER_RE = re.compile(r"backward\s+barrier\s+\(kcal\)\s*:\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
_REACTION_ENERGY_RE = re.compile(r"reaction energy\s+\(kcal\)\s*:\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)

_DEFAULT_REACTION_PATH_SETTINGS: tuple[tuple[str, int | float], ...] = (
    ("nrun", 1),
    ("npoint", 25),
    ("anopt", 10),
    ("kpush", 0.003),
    ("kpull", -0.015),
    ("ppull", 0.05),
    ("alp", 1.2),
)


@dataclass(frozen=True)
class XTBRunResult:
    mode: str
    total_energy_hartree: float | None
    homo_lumo_gap_ev: float | None
    gradient_norm: float | None
    stdout: str
    stderr: str
    command: tuple[str, ...]
    optimized_xyz: str | None = None
    optimized_scene: Molecule3DScene | None = None
    canvas_model: MoleculeModel | None = None


@dataclass(frozen=True)
class XTBComparisonResult:
    input_result: XTBRunResult
    output_result: XTBRunResult
    delta_energy_kcal_mol: float | None


@dataclass(frozen=True)
class XTBCRESTResult:
    mode: str
    total_energy_hartree: float | None
    homo_lumo_gap_ev: float | None
    gradient_norm: float | None
    conformer_count: int | None
    stdout: str
    stderr: str
    command: tuple[str, ...]
    conformer_xyz: str | None = None
    best_xyz: str | None = None
    rotamer_xyz: str | None = None
    best_scene: Molecule3DScene | None = None
    canvas_model: MoleculeModel | None = None


@dataclass(frozen=True)
class XTBReactionPathResult:
    mode: str
    forward_barrier_kcal_mol: float | None
    backward_barrier_kcal_mol: float | None
    reaction_energy_kcal_mol: float | None
    stdout: str
    stderr: str
    command: tuple[str, ...]
    path_xyz: str | None = None
    transition_state_xyz: str | None = None


class XTBAdapter:
    def __init__(self, rdkit_adapter: RDKitAdapter | None = None) -> None:
        self._rdkit = rdkit_adapter or RDKitAdapter()
        self.last_error: str | None = None

    def find_xtb_executable(self) -> str | None:
        return shutil.which("xtb")

    def find_executable(self) -> str | None:
        return self.find_xtb_executable()

    def find_crest_executable(self) -> str | None:
        return shutil.which("crest")

    def is_available(self) -> bool:
        return self.find_xtb_executable() is not None

    def availability_message(self) -> str:
        path = self.find_xtb_executable()
        if path is None:
            return "GFN2-xTB executable not found. Install `xtb` to enable calculations."
        return f"GFN2-xTB executable: {path}"

    def is_crest_available(self) -> bool:
        return self.find_crest_executable() is not None and self.find_xtb_executable() is not None

    def crest_availability_message(self) -> str:
        crest_path = self.find_crest_executable()
        xtb_path = self.find_xtb_executable()
        if crest_path is None and xtb_path is None:
            return "CREST workflow requires both `crest` and `xtb` executables on PATH."
        if crest_path is None:
            return "CREST executable not found. Install `crest` to enable conformer searches."
        if xtb_path is None:
            return "CREST requires the `xtb` executable on PATH. Install `xtb` to enable conformer searches."
        return f"CREST executable: {crest_path} (xtb: {xtb_path})"

    def optimize(
        self,
        model: MoleculeModel,
        *,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
        bond_length_px: float = 40.0,
    ) -> XTBRunResult | None:
        self.last_error = None
        scene = self._build_scene(
            model,
            atom_annotations=atom_annotations,
            workflow_name="GFN2-xTB optimization",
        )
        if scene is None:
            return None
        total_charge, total_unpaired = self._totals_from_annotations(atom_annotations)
        result = self._run_xtb(
            scene,
            mode="opt",
            total_charge=total_charge,
            total_unpaired=total_unpaired,
        )
        if result is None or result.optimized_xyz is None:
            return result
        optimized_scene = self._scene_from_xyz(result.optimized_xyz, template=scene)
        if optimized_scene is None:
            self.last_error = "GFN2-xTB returned an optimized structure that could not be mapped back to the canvas graph."
            return None
        canvas_model = self._scene_to_canvas_model(optimized_scene, bond_length_px=bond_length_px)
        return XTBRunResult(
            mode=result.mode,
            total_energy_hartree=result.total_energy_hartree,
            homo_lumo_gap_ev=result.homo_lumo_gap_ev,
            gradient_norm=result.gradient_norm,
            stdout=result.stdout,
            stderr=result.stderr,
            command=result.command,
            optimized_xyz=result.optimized_xyz,
            optimized_scene=optimized_scene,
            canvas_model=canvas_model,
        )

    def compare(
        self,
        input_model: MoleculeModel,
        output_model: MoleculeModel,
        *,
        input_annotations: Mapping[int, Mapping[str, int]] | None = None,
        output_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> XTBComparisonResult | None:
        return self.compare_pair_singlepoint(
            input_model,
            output_model,
            input_annotations=input_annotations,
            output_annotations=output_annotations,
        )

    def compare_pair_singlepoint(
        self,
        input_model: MoleculeModel,
        output_model: MoleculeModel,
        *,
        input_annotations: Mapping[int, Mapping[str, int]] | None = None,
        output_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> XTBComparisonResult | None:
        self.last_error = None
        input_result = self.singlepoint(input_model, atom_annotations=input_annotations)
        if input_result is None:
            return None
        output_result = self.singlepoint(output_model, atom_annotations=output_annotations)
        if output_result is None:
            return None
        delta_energy = None
        if (
            input_result.total_energy_hartree is not None
            and output_result.total_energy_hartree is not None
        ):
            delta_energy = (output_result.total_energy_hartree - input_result.total_energy_hartree) * 627.503
        return XTBComparisonResult(
            input_result=input_result,
            output_result=output_result,
            delta_energy_kcal_mol=delta_energy,
        )

    def conformer_search(
        self,
        model: MoleculeModel,
        *,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
        bond_length_px: float = 40.0,
        threads: int | None = None,
    ) -> XTBCRESTResult | None:
        self.last_error = None
        crest_path = self.find_crest_executable()
        xtb_path = self.find_xtb_executable()
        if crest_path is None:
            self.last_error = "CREST executable not found. Install `crest` to enable conformer searches."
            return None
        if xtb_path is None:
            self.last_error = "CREST requires the `xtb` executable on PATH. Install `xtb` to enable conformer searches."
            return None
        scene = self._build_scene(
            model,
            atom_annotations=atom_annotations,
            workflow_name="CREST conformer search",
        )
        if scene is None:
            return None
        total_charge, total_unpaired = self._totals_from_annotations(atom_annotations)
        command = [crest_path, "input.xyz", "--gfn2"]
        if threads is not None:
            command.extend(["-T", str(threads)])
        if total_charge:
            command.extend(["--chrg", str(total_charge)])
        if total_unpaired:
            command.extend(["--uhf", str(total_unpaired)])
        with tempfile.TemporaryDirectory(prefix="litedraw-crest-") as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "input.xyz").write_text(self._scene_to_xyz_block(scene), encoding="utf-8")
            completed = self._execute_command(
                command,
                cwd=temp_dir,
                timeout=900,
                workflow_name="CREST conformer search",
            )
            if completed is None:
                return None
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            output_text = "\n".join(part for part in (stdout, stderr) if part)
            conformer_xyz = self._read_text_if_exists(temp_path / "crest_conformers.xyz")
            rotamer_xyz = self._read_text_if_exists(temp_path / "crest_rotamers.xyz")
            best_xyz = self._read_text_if_exists(temp_path / "crest_best.xyz")
            if best_xyz is None:
                best_xyz = self._first_xyz_model(conformer_xyz)
            if completed.returncode != 0 and conformer_xyz is None and best_xyz is None:
                summary = stderr.strip() or stdout.strip() or f"exit code {completed.returncode}"
                self.last_error = f"CREST conformer search failed: {summary}"
                return None
            best_scene = None
            canvas_model = None
            if best_xyz is not None:
                best_scene = self._scene_from_xyz(best_xyz, template=scene)
                if best_scene is not None:
                    canvas_model = self._scene_to_canvas_model(best_scene, bond_length_px=bond_length_px)
            return XTBCRESTResult(
                mode="crest",
                total_energy_hartree=self._parse_float(_TOTAL_ENERGY_RE, output_text),
                homo_lumo_gap_ev=self._parse_float(_GAP_RE, output_text),
                gradient_norm=self._parse_float(_GRADIENT_RE, output_text),
                conformer_count=self._count_xyz_models(conformer_xyz),
                stdout=stdout,
                stderr=stderr,
                command=tuple(command),
                conformer_xyz=conformer_xyz,
                best_xyz=best_xyz,
                rotamer_xyz=rotamer_xyz,
                best_scene=best_scene,
                canvas_model=canvas_model,
            )

    def crest_search(
        self,
        model: MoleculeModel,
        *,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
        bond_length_px: float = 40.0,
        threads: int | None = None,
    ) -> XTBCRESTResult | None:
        return self.conformer_search(
            model,
            atom_annotations=atom_annotations,
            bond_length_px=bond_length_px,
            threads=threads,
        )

    def reaction_path(
        self,
        input_model: MoleculeModel,
        output_model: MoleculeModel,
        *,
        input_annotations: Mapping[int, Mapping[str, int]] | None = None,
        output_annotations: Mapping[int, Mapping[str, int]] | None = None,
        path_settings: Mapping[str, int | float] | None = None,
    ) -> XTBReactionPathResult | None:
        self.last_error = None
        xtb_path = self.find_xtb_executable()
        if xtb_path is None:
            self.last_error = "GFN2-xTB executable not found. Install `xtb` to enable calculations."
            return None
        input_scene = self._build_scene(
            input_model,
            atom_annotations=input_annotations,
            workflow_name="GFN2-xTB reaction path analysis",
        )
        if input_scene is None:
            return None
        output_scene = self._build_scene(
            output_model,
            atom_annotations=output_annotations,
            workflow_name="GFN2-xTB reaction path analysis",
        )
        if output_scene is None:
            return None
        if not self._scenes_share_atom_signature(input_scene, output_scene):
            self.last_error = (
                "Reaction path analysis requires input and output structures with the same atom ordering and composition."
            )
            return None
        input_charge, input_unpaired = self._totals_from_annotations(input_annotations)
        output_charge, output_unpaired = self._totals_from_annotations(output_annotations)
        if (input_charge, input_unpaired) != (output_charge, output_unpaired):
            self.last_error = (
                "Reaction path analysis requires matching total charge and radical count for input and output structures."
            )
            return None
        command = [xtb_path, "start.xyz", "--path", "end.xyz", "--input", "path.inp", "--gfn", "2"]
        if input_charge:
            command.extend(["--chrg", str(input_charge)])
        if input_unpaired:
            command.extend(["--uhf", str(input_unpaired)])
        with tempfile.TemporaryDirectory(prefix="litedraw-xtb-path-") as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "start.xyz").write_text(self._scene_to_xyz_block(input_scene), encoding="utf-8")
            (temp_path / "end.xyz").write_text(self._scene_to_xyz_block(output_scene), encoding="utf-8")
            (temp_path / "path.inp").write_text(
                self._reaction_path_input_text(path_settings),
                encoding="utf-8",
            )
            completed = self._execute_command(
                command,
                cwd=temp_dir,
                timeout=900,
                workflow_name="GFN2-xTB reaction path analysis",
            )
            if completed is None:
                return None
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            output_text = "\n".join(part for part in (stdout, stderr) if part)
            path_xyz = self._read_path_xyz(temp_path)
            transition_state_xyz = self._read_text_if_exists(temp_path / "xtbpath_ts.xyz")
            if completed.returncode != 0 and path_xyz is None and transition_state_xyz is None:
                summary = stderr.strip() or stdout.strip() or f"exit code {completed.returncode}"
                self.last_error = f"GFN2-xTB reaction path analysis failed: {summary}"
                return None
            return XTBReactionPathResult(
                mode="path",
                forward_barrier_kcal_mol=self._parse_float(_FORWARD_BARRIER_RE, output_text),
                backward_barrier_kcal_mol=self._parse_float(_BACKWARD_BARRIER_RE, output_text),
                reaction_energy_kcal_mol=self._parse_float(_REACTION_ENERGY_RE, output_text),
                stdout=stdout,
                stderr=stderr,
                command=tuple(command),
                path_xyz=path_xyz,
                transition_state_xyz=transition_state_xyz,
            )

    def singlepoint(
        self,
        model: MoleculeModel,
        *,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> XTBRunResult | None:
        self.last_error = None
        scene = self._build_scene(
            model,
            atom_annotations=atom_annotations,
            workflow_name="GFN2-xTB single-point calculation",
        )
        if scene is None:
            return None
        total_charge, total_unpaired = self._totals_from_annotations(atom_annotations)
        return self._run_xtb(
            scene,
            mode="sp",
            total_charge=total_charge,
            total_unpaired=total_unpaired,
        )

    def _run_xtb(
        self,
        scene: Molecule3DScene,
        *,
        mode: str,
        total_charge: int,
        total_unpaired: int,
    ) -> XTBRunResult | None:
        xtb_path = self.find_xtb_executable()
        if xtb_path is None:
            self.last_error = "GFN2-xTB executable not found. Install `xtb` to enable calculations."
            return None
        xyz_text = self._scene_to_xyz_block(scene)
        command = [xtb_path, "input.xyz", "--gfn", "2"]
        if mode == "opt":
            command.append("--opt")
        else:
            command.append("--scc")
        if total_charge:
            command.extend(["--chrg", str(total_charge)])
        if total_unpaired:
            command.extend(["--uhf", str(total_unpaired)])
        with tempfile.TemporaryDirectory(prefix="litedraw-xtb-") as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.xyz"
            input_path.write_text(xyz_text, encoding="utf-8")
            completed = self._execute_command(
                command,
                cwd=temp_dir,
                timeout=300,
                workflow_name="GFN2-xTB",
            )
            if completed is None:
                return None
            optimized_xyz = None
            optimized_path = temp_path / "xtbopt.xyz"
            if mode == "opt" and optimized_path.exists():
                optimized_xyz = optimized_path.read_text(encoding="utf-8")
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            output_text = "\n".join(part for part in (stdout, stderr) if part)
            if completed.returncode != 0 and optimized_xyz is None:
                summary = stderr.strip() or stdout.strip() or f"exit code {completed.returncode}"
                self.last_error = f"GFN2-xTB failed: {summary}"
                return None
            return XTBRunResult(
                mode=mode,
                total_energy_hartree=self._parse_float(_TOTAL_ENERGY_RE, output_text),
                homo_lumo_gap_ev=self._parse_float(_GAP_RE, output_text),
                gradient_norm=self._parse_float(_GRADIENT_RE, output_text),
                stdout=stdout,
                stderr=stderr,
                command=tuple(command),
                optimized_xyz=optimized_xyz,
            )

    @staticmethod
    def _parse_float(pattern: re.Pattern[str], text: str) -> float | None:
        match = pattern.search(text)
        if match is None:
            return None
        try:
            return float(match.group(1))
        except Exception:
            return None

    @staticmethod
    def _scene_to_xyz_block(scene: Molecule3DScene) -> str:
        lines = [str(len(scene.atoms)), "LiteDraw xTB input"]
        for atom in scene.atoms:
            lines.append(f"{atom.symbol:<2} {atom.x:.6f} {atom.y:.6f} {atom.z:.6f}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _totals_from_annotations(
        atom_annotations: Mapping[int, Mapping[str, int]] | None,
    ) -> tuple[int, int]:
        if atom_annotations is None:
            return 0, 0
        total_charge = 0
        total_unpaired = 0
        for values in atom_annotations.values():
            total_charge += int(values.get("formal_charge", 0))
            total_unpaired += int(values.get("radical_electrons", 0))
        return total_charge, total_unpaired

    def _build_scene(
        self,
        model: MoleculeModel,
        *,
        atom_annotations: Mapping[int, Mapping[str, int]] | None,
        workflow_name: str,
    ) -> Molecule3DScene | None:
        scene = self._rdkit.model_to_3d_scene(model, atom_annotations=atom_annotations)
        if scene is None:
            self.last_error = self._rdkit.last_error or f"Failed to prepare the input structure for {workflow_name}."
        return scene

    def _execute_command(
        self,
        command: Sequence[str],
        *,
        cwd: str,
        timeout: int,
        workflow_name: str,
    ) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                list(command),
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except Exception as exc:
            self.last_error = f"{workflow_name} execution failed: {exc}"
            return None

    @staticmethod
    def _reaction_path_input_text(path_settings: Mapping[str, int | float] | None) -> str:
        settings = {key: value for key, value in _DEFAULT_REACTION_PATH_SETTINGS}
        if path_settings:
            settings.update(path_settings)
        lines = ["$path"]
        for key, _default in _DEFAULT_REACTION_PATH_SETTINGS:
            lines.append(f"   {key}={settings[key]}")
        lines.extend(["$end", ""])
        return "\n".join(lines)

    @staticmethod
    def _read_text_if_exists(path: Path) -> str | None:
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _read_path_xyz(temp_path: Path) -> str | None:
        primary = temp_path / "xtbpath_0.xyz"
        if primary.exists():
            return primary.read_text(encoding="utf-8")
        fallback_files = sorted(temp_path.glob("xtbpath_*.xyz"))
        for path in fallback_files:
            if path.name == "xtbpath_ts.xyz":
                continue
            return path.read_text(encoding="utf-8")
        return None

    @staticmethod
    def _scenes_share_atom_signature(left: Molecule3DScene, right: Molecule3DScene) -> bool:
        if len(left.atoms) != len(right.atoms):
            return False
        return all(left_atom.symbol == right_atom.symbol for left_atom, right_atom in zip(left.atoms, right.atoms))

    @staticmethod
    def _count_xyz_models(xyz_text: str | None) -> int | None:
        if xyz_text is None:
            return None
        blocks = XTBAdapter._split_xyz_blocks(xyz_text)
        if blocks is None:
            return None
        return len(blocks)

    @staticmethod
    def _first_xyz_model(xyz_text: str | None) -> str | None:
        if xyz_text is None:
            return None
        blocks = XTBAdapter._split_xyz_blocks(xyz_text)
        if not blocks:
            return None
        return blocks[0]

    @staticmethod
    def _split_xyz_blocks(xyz_text: str) -> list[str] | None:
        lines = xyz_text.splitlines()
        blocks: list[str] = []
        index = 0
        total_lines = len(lines)
        while index < total_lines:
            while index < total_lines and not lines[index].strip():
                index += 1
            if index >= total_lines:
                break
            try:
                atom_count = int(lines[index].strip())
            except Exception:
                return None
            end_index = index + atom_count + 2
            if end_index > total_lines:
                return None
            block_lines = lines[index:end_index]
            blocks.append("\n".join(block_lines).strip() + "\n")
            index = end_index
        return blocks

    def _scene_from_xyz(self, xyz_text: str, *, template: Molecule3DScene) -> Molecule3DScene | None:
        lines = [line.strip() for line in xyz_text.splitlines() if line.strip()]
        if len(lines) < 3:
            return None
        try:
            atom_count = int(lines[0])
        except Exception:
            return None
        atom_lines = lines[2:]
        if len(atom_lines) < atom_count:
            return None
        atoms: list[Molecule3DAtom] = []
        for index in range(atom_count):
            parts = atom_lines[index].split()
            if len(parts) < 4:
                return None
            symbol = parts[0]
            try:
                x = float(parts[1])
                y = float(parts[2])
                z = float(parts[3])
            except Exception:
                return None
            atoms.append(Molecule3DAtom(symbol=symbol, x=x, y=y, z=z))
        if len(atoms) != len(template.atoms):
            return None
        for atom, template_atom in zip(atoms, template.atoms):
            if atom.symbol != template_atom.symbol:
                return None
        return Molecule3DScene(atoms=tuple(atoms), bonds=template.bonds)

    def _scene_to_canvas_model(
        self,
        scene: Molecule3DScene,
        *,
        bond_length_px: float,
    ) -> MoleculeModel:
        model = MoleculeModel()
        kept_indices = [
            index
            for index, atom in enumerate(scene.atoms)
            if atom.symbol != "H"
        ]
        if not kept_indices:
            kept_indices = list(range(len(scene.atoms)))

        avg_length = self._average_kept_bond_length(scene, kept_indices)
        scale = (bond_length_px / avg_length) if avg_length > 1e-6 else 1.0

        index_map: dict[int, int] = {}
        for old_index in kept_indices:
            atom = scene.atoms[old_index]
            new_id = model.add_atom(atom.symbol, atom.x * scale, atom.y * scale)
            model.atoms[new_id].explicit_label = atom.symbol != "C"
            index_map[old_index] = new_id
        for bond in scene.bonds:
            if bond.a not in index_map or bond.b not in index_map:
                continue
            model.add_bond(index_map[bond.a], index_map[bond.b], bond.order)
        return model

    @staticmethod
    def _average_kept_bond_length(scene: Molecule3DScene, kept_indices: list[int]) -> float:
        kept = set(kept_indices)
        lengths: list[float] = []
        for bond in scene.bonds:
            if bond.a not in kept or bond.b not in kept:
                continue
            atom_a = scene.atoms[bond.a]
            atom_b = scene.atoms[bond.b]
            dx = atom_a.x - atom_b.x
            dy = atom_a.y - atom_b.y
            length = (dx * dx + dy * dy) ** 0.5
            if length > 1e-6:
                lengths.append(length)
        if not lengths:
            return 1.0
        return sum(lengths) / len(lengths)
