"""Embed molecules in 3D and lay out disconnected components for the preview."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from chemvas.domain.chemistry_types import (
    Molecule3DAtom,
    Molecule3DBond,
    Molecule3DScene,
)
from chemvas.domain.document import (
    Bond,
    MoleculeModel,
    connected_atom_components,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from chemvas.core.rdkit_adapter import RDKitAdapter

logger = logging.getLogger(__name__)

_GEOMETRY_OPTIMIZATION_MAX_ITERS = 500


class _RDKitEmbedding:
    adapter: RDKitAdapter

    def _embed_3d_molecule(self, mol, Chem, AllChem):
        optimization_result = "not_attempted"
        try:
            mol_h = Chem.AddHs(mol)
            if any(
                atom.GetSymbol() == "P" and atom.GetDegree() == 6
                for atom in mol_h.GetAtoms()
            ):
                self.adapter.last_error = (
                    "Cannot generate 3D geometry for six-coordinate phosphorus: "
                    "this force-field path does not reliably preserve its "
                    "coordination geometry. Keep the drawing or export MOL, "
                    "and use an external geometry method suited to this structure."
                )
                return None
            mmff_supported = hasattr(
                AllChem, "MMFFHasAllMoleculeParams"
            ) and AllChem.MMFFHasAllMoleculeParams(mol_h)
            uff_supported = AllChem.UFFHasAllMoleculeParams(mol_h)
            if not mmff_supported and not uff_supported:
                self.adapter.last_error = (
                    "Cannot generate reliable 3D geometry: neither MMFF nor UFF "
                    "has all force-field parameters for this structure. "
                    "Use an external geometry method suited to its elements "
                    "and coordination."
                )
                return None
            params = AllChem.ETKDGv3()
            params.randomSeed = 0xC0FFEE
            status = AllChem.EmbedMolecule(mol_h, params)
            if status != 0:
                params.useRandomCoords = True
                status = AllChem.EmbedMolecule(mol_h, params)
            if status != 0:
                self.adapter.last_error = "3D embedding failed."
                return None
            try:
                if mmff_supported:
                    status = AllChem.MMFFOptimizeMolecule(
                        mol_h, maxIters=_GEOMETRY_OPTIMIZATION_MAX_ITERS
                    )
                    optimization_result = self._optimization_result("MMFF", status)
                else:
                    status = AllChem.UFFOptimizeMolecule(
                        mol_h, maxIters=_GEOMETRY_OPTIMIZATION_MAX_ITERS
                    )
                    optimization_result = self._optimization_result("UFF", status)
            except Exception:
                if not uff_supported:
                    self.adapter.last_error = (
                        "3D optimization failed and UFF fallback parameters "
                        "are incomplete for this structure."
                    )
                    return None
                logger.debug(
                    "Primary force-field optimization failed; falling back to UFF.",
                    exc_info=True,
                )
                try:
                    status = AllChem.UFFOptimizeMolecule(
                        mol_h, maxIters=_GEOMETRY_OPTIMIZATION_MAX_ITERS
                    )
                    optimization_result = self._optimization_result(
                        "UFF_fallback", status
                    )
                except Exception:
                    optimization_result = "unoptimized_after_optimization_errors"
                    logger.debug(
                        "UFF optimization fallback failed; using unoptimized geometry.",
                        exc_info=True,
                    )
        except Exception as exc:
            self.adapter.last_error = f"3D coordinate generation failed: {exc}"
            return None
        if hasattr(mol_h, "GetNumConformers") and mol_h.GetNumConformers() == 0:
            self.adapter.last_error = "3D coordinate generation failed: no conformer."
            return None
        if hasattr(mol_h, "SetProp"):
            try:
                mol_h.SetProp("_ChemvasOptimizationResult", optimization_result)
            except Exception:
                logger.debug("Recording optimization result failed.", exc_info=True)
        return mol_h

    @staticmethod
    def _optimization_result(method: str, status) -> str:
        if status == 0:
            return f"{method}_converged"
        if isinstance(status, int):
            return f"{method}_not_converged_status_{status}"
        return f"{method}_completed_status_unknown"

    @staticmethod
    def _build_model_adjacency(model: MoleculeModel) -> dict[int, list[int]]:
        adjacency: dict[int, list[int]] = {atom_id: [] for atom_id in model.atoms}
        for bond in model.bonds:
            if bond is None or bond.a == bond.b:
                continue
            if bond.a not in model.atoms or bond.b not in model.atoms:
                continue
            adjacency.setdefault(bond.a, []).append(bond.b)
            adjacency.setdefault(bond.b, []).append(bond.a)
        return adjacency

    @staticmethod
    def _component_sort_key(
        model: MoleculeModel, atom_ids: set[int]
    ) -> tuple[float, float, int]:
        # Every component comes from _model_components, which seeds from
        # model.atoms and walks components built over the same keys: the ids
        # are always live and a component is never empty.
        xs = [model.atoms[atom_id].x for atom_id in atom_ids]
        ys = [model.atoms[atom_id].y for atom_id in atom_ids]
        center_x = (min(xs) + max(xs)) * 0.5
        center_y = (min(ys) + max(ys)) * 0.5
        return center_x, center_y, min(atom_ids)

    def _model_components(self, model: MoleculeModel) -> list[set[int]]:
        components = [
            set(atom_ids)
            for atom_ids in connected_atom_components(
                model.atoms,
                ((bond.a, bond.b) for bond in model.bonds if bond is not None),
            )
        ]
        components.sort(key=lambda atom_ids: self._component_sort_key(model, atom_ids))
        return components

    @staticmethod
    def _build_component_model(
        model: MoleculeModel,
        atom_ids: set[int],
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
        *,
        bonds: Iterable[Bond | None],
    ) -> tuple[MoleculeModel, dict[int, dict[str, int]]]:
        component_model = MoleculeModel()
        active_annotations = (
            atom_annotations if atom_annotations is not None else model.atom_annotations
        )
        id_map: dict[int, int] = {}
        for old_id in sorted(atom_ids):
            atom = model.atoms.get(old_id)
            if atom is None:
                continue
            # Preserve document IDs through the preview's component split so
            # conversion errors still identify the atom the user can edit.
            component_model.atoms[old_id] = replace(atom)
            id_map[old_id] = old_id
        component_model.next_atom_id = max(component_model.atoms, default=-1) + 1
        for bond in bonds:
            if bond is None:
                continue
            if bond.a not in id_map or bond.b not in id_map:
                continue
            component_model.bonds.append(
                Bond(
                    a=id_map[bond.a],
                    b=id_map[bond.b],
                    order=bond.order,
                    style=bond.style,
                    color=bond.color,
                )
            )
        component_annotations: dict[int, dict[str, int]] = {}
        if active_annotations:
            for old_id, new_id in id_map.items():
                values = active_annotations.get(old_id)
                if not values:
                    continue
                component_annotations[new_id] = {
                    key: int(value) for key, value in values.items()
                }
        component_model.atom_annotations = component_annotations
        return component_model, component_annotations

    @staticmethod
    def _scene_from_embedded_mol(mol_h) -> Molecule3DScene:
        conf = mol_h.GetConformer()
        atoms = tuple(
            Molecule3DAtom(
                symbol=atom.GetSymbol(),
                x=conf.GetAtomPosition(atom.GetIdx()).x,
                y=conf.GetAtomPosition(atom.GetIdx()).y,
                z=conf.GetAtomPosition(atom.GetIdx()).z,
            )
            for atom in mol_h.GetAtoms()
        )
        bond_iterable = mol_h.GetBonds() if hasattr(mol_h, "GetBonds") else ()
        bonds = tuple(
            Molecule3DBond(
                a=bond.GetBeginAtomIdx(),
                b=bond.GetEndAtomIdx(),
                order=max(1, round(bond.GetBondTypeAsDouble())),
            )
            for bond in bond_iterable
        )
        return Molecule3DScene(atoms=atoms, bonds=bonds)

    @staticmethod
    def _scene_bounds(
        scene: Molecule3DScene,
    ) -> tuple[float, float, float, float, float, float]:
        xs = [atom.x for atom in scene.atoms]
        ys = [atom.y for atom in scene.atoms]
        zs = [atom.z for atom in scene.atoms]
        return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)

    @staticmethod
    def _translate_scene(
        scene: Molecule3DScene,
        *,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
    ) -> Molecule3DScene:
        return Molecule3DScene(
            atoms=tuple(
                Molecule3DAtom(
                    symbol=atom.symbol,
                    x=atom.x + dx,
                    y=atom.y + dy,
                    z=atom.z + dz,
                )
                for atom in scene.atoms
            ),
            bonds=scene.bonds,
        )

    def _layout_component_scenes(
        self,
        component_scenes: list[Molecule3DScene],
        *,
        gap: float = 2.5,
    ) -> Molecule3DScene:
        if not component_scenes:
            return Molecule3DScene(atoms=(), bonds=())
        if len(component_scenes) == 1:
            return component_scenes[0]

        combined_atoms: list[Molecule3DAtom] = []
        combined_bonds: list[Molecule3DBond] = []
        atom_offset = 0
        cursor_right: float | None = None
        for scene in component_scenes:
            min_x, max_x, min_y, max_y, min_z, max_z = self._scene_bounds(scene)
            centered_scene = self._translate_scene(
                scene,
                dx=-((min_x + max_x) * 0.5),
                dy=-((min_y + max_y) * 0.5),
                dz=-((min_z + max_z) * 0.5),
            )
            centered_min_x, _, _, _, _, _ = self._scene_bounds(centered_scene)
            shift_x = (
                0.0 if cursor_right is None else cursor_right + gap - centered_min_x
            )
            shifted_scene = self._translate_scene(centered_scene, dx=shift_x)
            combined_atoms.extend(shifted_scene.atoms)
            combined_bonds.extend(
                Molecule3DBond(
                    a=bond.a + atom_offset,
                    b=bond.b + atom_offset,
                    order=bond.order,
                )
                for bond in shifted_scene.bonds
            )
            _, shifted_max_x, _, _, _, _ = self._scene_bounds(shifted_scene)
            cursor_right = shifted_max_x
            atom_offset += len(shifted_scene.atoms)
        return Molecule3DScene(atoms=tuple(combined_atoms), bonds=tuple(combined_bonds))
