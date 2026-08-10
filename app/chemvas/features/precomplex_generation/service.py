from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import replace

from chemvas.features.calculation_bundle import CalculationArtifacts

from .model import (
    CandidateTransform,
    ComponentGeometry,
    ContactRequest,
    GeneratedCandidate,
    GeometryAtom,
    PlacementRequest,
    ValidationMetrics,
    Vector3,
)

PROFILE_ID = "chemvas-rigid-precomplex-placement/1"
APPROACH_SAMPLE_COUNT = 12
ROTATION_SAMPLE_COUNT = 6
MAX_CANDIDATES = 16

# Frozen by PROFILE_ID. Values are covalent and van der Waals radii in angstrom.
_RADII: dict[str, tuple[float, float]] = {
    "H": (0.31, 1.20),
    "Li": (1.28, 1.82),
    "B": (0.84, 1.92),
    "C": (0.76, 1.70),
    "N": (0.71, 1.55),
    "O": (0.66, 1.52),
    "F": (0.57, 1.47),
    "Na": (1.66, 2.27),
    "Mg": (1.41, 1.73),
    "Al": (1.21, 1.84),
    "Si": (1.11, 2.10),
    "P": (1.07, 1.80),
    "S": (1.05, 1.80),
    "Cl": (1.02, 1.75),
    "K": (2.03, 2.75),
    "Ca": (1.76, 2.31),
    "Fe": (1.32, 2.00),
    "Co": (1.26, 2.00),
    "Ni": (1.24, 1.63),
    "Cu": (1.32, 1.40),
    "Zn": (1.22, 1.39),
    "Br": (1.20, 1.85),
    "Ru": (1.46, 2.00),
    "Rh": (1.42, 2.00),
    "Pd": (1.39, 1.63),
    "Ag": (1.45, 1.72),
    "Sn": (1.39, 2.17),
    "I": (1.39, 1.98),
    "Ir": (1.41, 2.00),
    "Pt": (1.36, 1.75),
    "Au": (1.36, 1.66),
}
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_EPSILON = 1e-12


def component_geometries_from_artifacts(
    artifacts: CalculationArtifacts,
    component_atom_ids: tuple[tuple[int, ...], ...],
) -> tuple[ComponentGeometry, ...]:
    if not artifacts.geometry_optimization_result.endswith("_converged"):
        raise ValueError(
            "Precomplex generation requires a converged component geometry; "
            f"received {artifacts.geometry_optimization_result}."
        )
    if not component_atom_ids or any(not component for component in component_atom_ids):
        raise ValueError("Precomplex component membership must be nonempty.")
    memberships = tuple(
        tuple(sorted(set(component))) for component in component_atom_ids
    )
    if memberships != component_atom_ids or len(set(memberships)) != len(memberships):
        raise ValueError("Precomplex component membership must be sorted and unique.")
    owner_by_source_id: dict[int, int] = {}
    for component_index, component in enumerate(memberships):
        for source_atom_id in component:
            if source_atom_id in owner_by_source_id:
                raise ValueError("Precomplex component membership overlaps.")
            owner_by_source_id[source_atom_id] = component_index

    rows = artifacts.xyz_block.splitlines()
    if len(rows) != artifacts.xyz_atom_count + 2:
        raise ValueError("Precomplex XYZ rows do not match the generated atom count.")
    try:
        declared_count = int(rows[0].strip())
    except ValueError as exc:
        raise ValueError("Precomplex XYZ has an invalid atom count.") from exc
    if (
        declared_count != artifacts.xyz_atom_count
        or len(artifacts.atom_map) != artifacts.xyz_atom_count
    ):
        raise ValueError("Precomplex XYZ and atom map counts are inconsistent.")

    atoms_by_component: list[list[GeometryAtom]] = [
        [] for _component in component_atom_ids
    ]
    identity_by_component: list[list[dict[str, object]]] = [
        [] for _component in component_atom_ids
    ]
    for expected_index, (row, entry) in enumerate(
        zip(rows[2:], artifacts.atom_map, strict=True),
        start=1,
    ):
        fields = row.split()
        if (
            entry.xyz_index != expected_index
            or len(fields) != 4
            or fields[0] != entry.symbol
        ):
            raise ValueError("Precomplex XYZ rows do not match the generated atom map.")
        try:
            coordinates = (float(fields[1]), float(fields[2]), float(fields[3]))
        except ValueError as exc:
            raise ValueError("Precomplex XYZ contains an invalid coordinate.") from exc
        if not all(math.isfinite(value) for value in coordinates):
            raise ValueError("Precomplex XYZ contains a nonfinite coordinate.")
        owner = entry.chemvas_atom_id
        if owner is None:
            owner = entry.parent_chemvas_atom_id
        owner_component_index = (
            owner_by_source_id.get(owner) if owner is not None else None
        )
        if owner_component_index is None:
            raise ValueError("Precomplex generated atom ownership is incomplete.")
        atom = GeometryAtom(
            path_index=expected_index - 1,
            symbol=entry.symbol,
            source_atom_id=entry.chemvas_atom_id,
            parent_source_atom_id=entry.parent_chemvas_atom_id,
            origin=entry.origin,
            coordinates=coordinates,
        )
        atoms_by_component[owner_component_index].append(atom)
        identity_by_component[owner_component_index].append(
            {
                "path_index": atom.path_index,
                "symbol": atom.symbol,
                "source_atom_id": atom.source_atom_id,
                "parent_source_atom_id": atom.parent_source_atom_id,
                "origin": atom.origin,
                "coordinates": [f"{value:.8f}" for value in coordinates],
            }
        )

    geometries: list[ComponentGeometry] = []
    for component_index, component in enumerate(memberships):
        atoms = tuple(atoms_by_component[component_index])
        if not atoms:
            raise ValueError("Precomplex component geometry is empty.")
        canonical = json.dumps(
            {
                "profile": PROFILE_ID,
                "component_atom_ids": list(component),
                "atoms": identity_by_component[component_index],
                "rdkit_version": artifacts.rdkit_version,
                "embedding": artifacts.geometry_embedding,
                "random_seed": artifacts.geometry_random_seed,
                "optimization_policy": artifacts.geometry_optimization_policy,
                "optimization_result": artifacts.geometry_optimization_result,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        geometries.append(
            ComponentGeometry(
                component_atom_ids=component,
                conformer_id="conf-"
                + hashlib.sha256(canonical.encode("ascii")).hexdigest(),
                atoms=atoms,
            )
        )
    return tuple(geometries)


def generate_precomplex_candidates(
    request: PlacementRequest,
    components: tuple[ComponentGeometry, ...],
) -> tuple[GeneratedCandidate, ...]:
    _validate_request(request, components)
    root, child, contact = _ordered_components(request.contacts[0], components)
    root_contact = _contact_atom(root, _contact_id_for_component(contact, root))
    child_contact = _contact_atom(child, _contact_id_for_component(contact, child))
    directions = _fibonacci_sphere(APPROACH_SAMPLE_COUNT)
    component_conformer_ids = tuple(component.conformer_id for component in components)
    candidates: list[GeneratedCandidate] = []
    for approach_index, direction in enumerate(directions):
        aligned = _align_child_contact_outward(child, child_contact, direction)
        for rotation_index in range(ROTATION_SAMPLE_COUNT):
            angle = (2.0 * math.pi * rotation_index) / ROTATION_SAMPLE_COUNT
            rotated = _rotate_component_about_contact(
                aligned,
                child_contact.path_index,
                direction,
                angle,
            )
            target = _add(
                root_contact.coordinates,
                _scale(direction, contact.target_distance_angstrom),
            )
            placed_child = _translate_contact_to(
                rotated,
                child_contact.path_index,
                target,
            )
            atoms = tuple(
                sorted(
                    root.atoms + placed_child.atoms, key=lambda atom: atom.path_index
                )
            )
            validation = _validate_placement(
                root,
                placed_child,
                atoms,
                root_contact.path_index,
                child_contact.path_index,
                contact,
            )
            if validation.hard_clash_count:
                continue
            xyz = _xyz_block(request, atoms)
            xyz_sha256 = hashlib.sha256(xyz.encode("ascii")).hexdigest()
            transform = CandidateTransform(
                approach_index=approach_index,
                rotation_index=rotation_index,
                approach_vector=direction,
            )
            candidate_id = _candidate_id(
                request,
                components,
                transform,
                xyz_sha256,
            )
            candidates.append(
                GeneratedCandidate(
                    id=candidate_id,
                    geometry_class="generated_candidate_ensemble",
                    profile=PROFILE_ID,
                    atoms=atoms,
                    xyz=xyz,
                    xyz_sha256=xyz_sha256,
                    transform=transform,
                    component_conformer_ids=component_conformer_ids,
                    validation=validation,
                )
            )
    candidates.sort(
        key=lambda candidate: (
            candidate.validation.hard_clash_count,
            candidate.validation.soft_overlap_score,
            candidate.validation.contact_error_angstrom,
            candidate.transform.approach_index,
            candidate.transform.rotation_index,
            candidate.id,
        )
    )
    if not candidates:
        raise ValueError(
            "chemvas/precomplex_no_candidates_survived: every deterministic "
            "placement failed clash or contact validation."
        )
    return tuple(candidates[: request.candidate_cap])


def _validate_request(
    request: PlacementRequest,
    components: tuple[ComponentGeometry, ...],
) -> None:
    if _SHA256_RE.fullmatch(request.source_sha256) is None:
        raise ValueError("Precomplex source_sha256 must be lowercase SHA-256 hex.")
    if _SHA256_RE.fullmatch(request.plan_sha256) is None:
        raise ValueError("Precomplex plan_sha256 must be lowercase SHA-256 hex.")
    if request.side not in {"reactant", "product"}:
        raise ValueError("Precomplex side must be reactant or product.")
    if not request.step_id or len(request.step_id) > 64:
        raise ValueError("Precomplex step id is invalid.")
    if not 1 <= request.candidate_cap <= MAX_CANDIDATES:
        raise ValueError(
            f"Precomplex candidate_cap must be between 1 and {MAX_CANDIDATES}."
        )
    if len(components) != 2:
        raise ValueError(
            "Placement profile v1 requires exactly two included components."
        )
    if len(request.contacts) != 1:
        raise ValueError(
            "chemvas/precomplex_contact_graph_incomplete: profile v1 requires "
            "exactly one intercomponent contact."
        )
    if components[0].component_atom_ids == components[1].component_atom_ids:
        raise ValueError("Precomplex components must be distinct.")
    path_indices = [
        atom.path_index for component in components for atom in component.atoms
    ]
    if sorted(path_indices) != list(range(len(path_indices))):
        raise ValueError(
            "Precomplex atom path indices must be one complete zero-based order."
        )
    for component in components:
        if not component.component_atom_ids or not component.atoms:
            raise ValueError(
                "Precomplex components and component geometries must be nonempty."
            )
        if (
            tuple(sorted(set(component.component_atom_ids)))
            != component.component_atom_ids
        ):
            raise ValueError("Precomplex component atom ids must be sorted and unique.")
        for atom in component.atoms:
            if atom.symbol not in _RADII:
                raise ValueError(
                    "chemvas/precomplex_unsupported_radius: placement profile v1 "
                    f"has no frozen radii for element {atom.symbol}."
                )
            if not atom.origin or not all(
                math.isfinite(value) for value in atom.coordinates
            ):
                raise ValueError(
                    "Precomplex component geometry contains invalid atom data."
                )
            owner = atom.source_atom_id
            if owner is None:
                owner = atom.parent_source_atom_id
            if owner not in component.component_atom_ids:
                raise ValueError("Precomplex generated atom ownership is incomplete.")
    contact = request.contacts[0]
    if not contact.id or len(contact.id) > 64:
        raise ValueError("Precomplex contact id is invalid.")
    if (
        not math.isfinite(contact.target_distance_angstrom)
        or contact.target_distance_angstrom <= 0.0
        or not math.isfinite(contact.tolerance_angstrom)
        or contact.tolerance_angstrom < 0.0
        or contact.tolerance_angstrom > 1.0
    ):
        raise ValueError("Precomplex contact distance or tolerance is invalid.")
    first_component = _component_for_source_atom(components, contact.first_atom_id)
    second_component = _component_for_source_atom(components, contact.second_atom_id)
    if first_component is second_component:
        raise ValueError(
            "Precomplex contacts must connect different included components."
        )
    _contact_atom(first_component, contact.first_atom_id)
    _contact_atom(second_component, contact.second_atom_id)


def _ordered_components(
    contact: ContactRequest,
    components: tuple[ComponentGeometry, ...],
) -> tuple[ComponentGeometry, ComponentGeometry, ContactRequest]:
    root = min(
        components,
        key=lambda component: (
            -sum(atom.symbol != "H" for atom in component.atoms),
            component.component_atom_ids,
        ),
    )
    child = components[1] if components[0] is root else components[0]
    return root, child, contact


def _component_for_source_atom(
    components: tuple[ComponentGeometry, ...], atom_id: int
) -> ComponentGeometry:
    matches = [
        component for component in components if atom_id in component.component_atom_ids
    ]
    if len(matches) != 1:
        raise ValueError(f"Precomplex contact atom {atom_id} is not uniquely owned.")
    return matches[0]


def _contact_id_for_component(
    contact: ContactRequest, component: ComponentGeometry
) -> int:
    if contact.first_atom_id in component.component_atom_ids:
        return contact.first_atom_id
    if contact.second_atom_id in component.component_atom_ids:
        return contact.second_atom_id
    raise ValueError("Precomplex contact does not connect the selected components.")


def _contact_atom(component: ComponentGeometry, atom_id: int) -> GeometryAtom:
    matches = [
        atom
        for atom in component.atoms
        if atom.source_atom_id == atom_id
        and atom.origin in {"chemvas_atom", "alias_attachment"}
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Precomplex contact atom {atom_id} does not have one canonical geometry atom."
        )
    return matches[0]


def _align_child_contact_outward(
    child: ComponentGeometry,
    child_contact: GeometryAtom,
    direction: Vector3,
) -> ComponentGeometry:
    heavy = [atom.coordinates for atom in child.atoms if atom.symbol != "H"]
    centroid = _centroid(heavy or [atom.coordinates for atom in child.atoms])
    outward = _subtract(child_contact.coordinates, centroid)
    if _norm(outward) < _EPSILON:
        outward = (1.0, 0.0, 0.0)
    target = _scale(direction, -1.0)
    return _rotate_component_from_to(child, child_contact.path_index, outward, target)


def _rotate_component_from_to(
    component: ComponentGeometry,
    center_index: int,
    source: Vector3,
    target: Vector3,
) -> ComponentGeometry:
    source_unit = _unit(source)
    target_unit = _unit(target)
    cross = _cross(source_unit, target_unit)
    cross_norm = _norm(cross)
    dot = max(-1.0, min(1.0, _dot(source_unit, target_unit)))
    if cross_norm < _EPSILON:
        if dot > 0.0:
            return component
        axis = _unit(_cross(source_unit, _least_parallel_axis(source_unit)))
        angle = math.pi
    else:
        axis = _scale(cross, 1.0 / cross_norm)
        angle = math.acos(dot)
    return _rotate_component_about_contact(component, center_index, axis, angle)


def _rotate_component_about_contact(
    component: ComponentGeometry,
    center_index: int,
    axis: Vector3,
    angle: float,
) -> ComponentGeometry:
    center = next(
        atom.coordinates for atom in component.atoms if atom.path_index == center_index
    )
    unit_axis = _unit(axis)
    rotated = tuple(
        replace(
            atom,
            coordinates=_add(
                center,
                _rodrigues(_subtract(atom.coordinates, center), unit_axis, angle),
            ),
        )
        for atom in component.atoms
    )
    return replace(component, atoms=rotated)


def _translate_contact_to(
    component: ComponentGeometry,
    contact_index: int,
    target: Vector3,
) -> ComponentGeometry:
    current = next(
        atom.coordinates for atom in component.atoms if atom.path_index == contact_index
    )
    shift = _subtract(target, current)
    return replace(
        component,
        atoms=tuple(
            replace(atom, coordinates=_add(atom.coordinates, shift))
            for atom in component.atoms
        ),
    )


def _validate_placement(
    root: ComponentGeometry,
    child: ComponentGeometry,
    atoms: tuple[GeometryAtom, ...],
    root_contact_index: int,
    child_contact_index: int,
    contact: ContactRequest,
) -> ValidationMetrics:
    by_index = {atom.path_index: atom for atom in atoms}
    contact_distance = _distance(
        by_index[root_contact_index].coordinates,
        by_index[child_contact_index].coordinates,
    )
    contact_error = abs(contact_distance - contact.target_distance_angstrom)
    hard_clashes = int(contact_error > contact.tolerance_angstrom + 1e-9)
    soft_overlap = 0.0
    limiting_pair: tuple[int, int] | None = None
    limiting_distance: float | None = None
    limiting_threshold: float | None = None
    for root_atom in root.atoms:
        for child_atom in child.atoms:
            distance = _distance(
                root_atom.coordinates,
                child_atom.coordinates,
            )
            covalent = _RADII[root_atom.symbol][0] + _RADII[child_atom.symbol][0]
            vdw = _RADII[root_atom.symbol][1] + _RADII[child_atom.symbol][1]
            designated = {
                root_atom.path_index,
                child_atom.path_index,
            } == {root_contact_index, child_contact_index}
            threshold = (
                0.85 * covalent if designated else max(1.05 * covalent, 0.60 * vdw)
            )
            if distance < threshold - 1e-9:
                hard_clashes += 1
                if (
                    limiting_distance is None
                    or limiting_threshold is None
                    or distance - threshold < limiting_distance - limiting_threshold
                ):
                    limiting_pair = (root_atom.path_index, child_atom.path_index)
                    limiting_distance = distance
                    limiting_threshold = threshold
            soft_threshold = 0.85 * vdw
            if distance < soft_threshold:
                soft_overlap += (soft_threshold - distance) ** 2
    return ValidationMetrics(
        hard_clash_count=hard_clashes,
        soft_overlap_score=round(soft_overlap, 12),
        contact_error_angstrom=round(contact_error, 12),
        limiting_pair=limiting_pair,
        limiting_distance_angstrom=(
            None if limiting_distance is None else round(limiting_distance, 12)
        ),
        limiting_threshold_angstrom=(
            None if limiting_threshold is None else round(limiting_threshold, 12)
        ),
    )


def _candidate_id(
    request: PlacementRequest,
    components: tuple[ComponentGeometry, ...],
    transform: CandidateTransform,
    xyz_sha256: str,
) -> str:
    payload = {
        "profile": PROFILE_ID,
        "source_sha256": request.source_sha256,
        "plan_sha256": request.plan_sha256,
        "step_id": request.step_id,
        "side": request.side,
        "contacts": [
            {
                "id": contact.id,
                "first_atom_id": contact.first_atom_id,
                "second_atom_id": contact.second_atom_id,
                "target_distance_angstrom": contact.target_distance_angstrom,
                "tolerance_angstrom": contact.tolerance_angstrom,
            }
            for contact in request.contacts
        ],
        "component_atom_ids": [
            list(component.component_atom_ids) for component in components
        ],
        "component_conformer_ids": [component.conformer_id for component in components],
        "approach_index": transform.approach_index,
        "rotation_index": transform.rotation_index,
        "xyz_sha256": xyz_sha256,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "pc-" + hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _xyz_block(request: PlacementRequest, atoms: tuple[GeometryAtom, ...]) -> str:
    lines = [
        str(len(atoms)),
        f"Chemvas {PROFILE_ID} {request.step_id} {request.side}",
    ]
    lines.extend(
        f"{atom.symbol:<2} {atom.coordinates[0]:.8f} {atom.coordinates[1]:.8f} "
        f"{atom.coordinates[2]:.8f}"
        for atom in atoms
    )
    return "\n".join(lines) + "\n"


def _fibonacci_sphere(count: int) -> tuple[Vector3, ...]:
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    directions: list[Vector3] = []
    for index in range(count):
        y = 1.0 - (2.0 * (index + 0.5) / count)
        radius = math.sqrt(max(0.0, 1.0 - y * y))
        angle = golden_angle * index
        directions.append((math.cos(angle) * radius, y, math.sin(angle) * radius))
    return tuple(directions)


def _rodrigues(vector: Vector3, axis: Vector3, angle: float) -> Vector3:
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return _add(
        _add(_scale(vector, cosine), _scale(_cross(axis, vector), sine)),
        _scale(axis, _dot(axis, vector) * (1.0 - cosine)),
    )


def _least_parallel_axis(vector: Vector3) -> Vector3:
    axes: tuple[Vector3, ...] = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    return min(axes, key=lambda axis: abs(_dot(vector, axis)))


def _centroid(points: list[Vector3]) -> Vector3:
    count = float(len(points))
    return (
        sum(point[0] for point in points) / count,
        sum(point[1] for point in points) / count,
        sum(point[2] for point in points) / count,
    )


def _distance(first: Vector3, second: Vector3) -> float:
    return _norm(_subtract(first, second))


def _norm(vector: Vector3) -> float:
    return math.sqrt(_dot(vector, vector))


def _unit(vector: Vector3) -> Vector3:
    length = _norm(vector)
    if length < _EPSILON:
        raise ValueError("Precomplex rotation axis is degenerate.")
    return _scale(vector, 1.0 / length)


def _add(first: Vector3, second: Vector3) -> Vector3:
    return (first[0] + second[0], first[1] + second[1], first[2] + second[2])


def _subtract(first: Vector3, second: Vector3) -> Vector3:
    return (first[0] - second[0], first[1] - second[1], first[2] - second[2])


def _scale(vector: Vector3, factor: float) -> Vector3:
    return (vector[0] * factor, vector[1] * factor, vector[2] * factor)


def _dot(first: Vector3, second: Vector3) -> float:
    return first[0] * second[0] + first[1] * second[1] + first[2] * second[2]


def _cross(first: Vector3, second: Vector3) -> Vector3:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


__all__ = [
    "APPROACH_SAMPLE_COUNT",
    "MAX_CANDIDATES",
    "PROFILE_ID",
    "ROTATION_SAMPLE_COUNT",
    "component_geometries_from_artifacts",
    "generate_precomplex_candidates",
]
