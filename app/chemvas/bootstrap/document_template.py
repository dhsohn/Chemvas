from __future__ import annotations

import argparse
import hashlib
import math
import sys
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from chemvas.bootstrap.document_cli_shared import (
    MAX_DOCUMENT_BYTES,
    MAX_GRAPHICS_RECORDS,
    graphics_record_count,
    json_text,
    offscreen_canvas,
)
from chemvas.core.document_io import atomic_create_bytes, read_exact_document
from chemvas.domain.document import (
    Atom,
    Bond,
    MoleculeModel,
    build_document_payload,
    deserialize_model_state,
    is_document_number,
    normalize_json_numbers,
    serialize_model_state,
)
from chemvas.domain.json_io import strict_json_loads
from chemvas.features.calculation_bundle import inspect_components
from chemvas.features.insertion import (
    TemplateInsertPlan,
    TemplateInsertRequest,
    TemplateInsertResolution,
    plan_template_commit,
)

MAX_REQUEST_BYTES = 64 * 1024
MAX_RING_SIZE = 12
MAX_POSITION = 1_000_000.0
_REQUEST_KEYS = {
    "format",
    "version",
    "source_sha256",
    "ring_size",
    "style",
    "position",
    "anchor",
}


def run(argv: list[str]) -> int:
    parser = _argument_parser()
    args = parser.parse_args(argv)
    try:
        source, request_path = Path(args.document), Path(args.request)
        output = Path(args.output) if args.output is not None else None
        _validate_paths(source, request_path, output)
        source_bytes, document = read_exact_document(
            source, max_bytes=MAX_DOCUMENT_BYTES
        )
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        with request_path.open("rb") as stream:
            request_bytes = stream.read(MAX_REQUEST_BYTES + 1)
        if len(request_bytes) > MAX_REQUEST_BYTES:
            raise ValueError(
                f"template request exceeds the {MAX_REQUEST_BYTES}-byte limit"
            )
        try:
            raw = strict_json_loads(request_bytes)
        except (ValueError, RecursionError, UnicodeError) as exc:
            raise ValueError("Invalid Chemvas template insertion JSON file.") from exc
        state = document.state
        request = validate_template_request(state, raw, source_sha256=source_hash)
        candidate, added_atoms = insert_template(state, request)
        version = int(document.payload["version"])
        payload = normalize_json_numbers(build_document_payload(candidate, version))
        candidate_bytes = json_text(payload).encode("utf-8")
        if len(candidate_bytes) > MAX_DOCUMENT_BYTES:
            raise ValueError(
                f"candidate document exceeds the {MAX_DOCUMENT_BYTES}-byte limit"
            )
        if output is not None:
            atomic_create_bytes(output, candidate_bytes)
        sys.stdout.write(
            json_text(
                {
                    "format": "chemvas-template-insertion-report",
                    "version": 1,
                    "source": str(source),
                    "source_sha256": source_hash,
                    "request_sha256": hashlib.sha256(request_bytes).hexdigest(),
                    "candidate_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
                    "chemvas_document_version": version,
                    "output": str(output) if output is not None else None,
                    "dry_run": bool(args.dry_run),
                    "written": output is not None,
                    "added_atom_ids": added_atoms,
                    "ring_size": request.ring_size,
                    "style": request.ring_style,
                    "anchor": cast("Mapping[str, object]", raw)["anchor"],
                }
            )
        )
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"chemvas: error: {exc}\n")
    return 2


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chemvas",
        description="Insert an explicit native ring template into a new document.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser(
        "insert-template",
        help="insert a native ring template without overwriting the source",
    )
    command.add_argument("document", help="input .chemvas document")
    command.add_argument(
        "--request", required=True, help="source-pinned template insertion v1 JSON"
    )
    destination = command.add_mutually_exclusive_group(required=True)
    destination.add_argument(
        "--dry-run",
        action="store_true",
        help="fully validate the native candidate without writing",
    )
    destination.add_argument("--output", help="new non-overwriting .chemvas path")
    return parser


def _validate_paths(source: Path, request: Path, output: Path | None) -> None:
    if source.suffix.lower() != ".chemvas" or not source.is_file():
        raise ValueError("input must be an existing .chemvas document")
    if request.suffix.lower() != ".json" or not request.is_file():
        raise ValueError("request must be an existing .json file")
    if output is None:
        return
    if output.suffix.lower() != ".chemvas":
        raise ValueError("output must use the .chemvas filename extension")
    if output.exists() or output.is_symlink():
        raise ValueError(f"output path already exists: {output}")
    if not output.parent.is_dir():
        raise ValueError(f"output parent directory does not exist: {output.parent}")


def validate_template_request(
    state: dict[str, Any], raw: object, *, source_sha256: str
) -> TemplateInsertRequest:
    if not isinstance(raw, Mapping) or set(raw) != _REQUEST_KEYS:
        raise ValueError("template request has missing or unknown keys")
    if (
        raw["format"] != "chemvas-template-insertion"
        or type(raw["version"]) is not int
        or raw["version"] != 1
    ):
        raise ValueError(
            "template request must use chemvas-template-insertion version 1"
        )
    pin = raw["source_sha256"]
    if (
        not isinstance(pin, str)
        or len(pin) != 64
        or any(c not in "0123456789abcdef" for c in pin)
        or pin != source_sha256
    ):
        raise ValueError("source_sha256 does not match the exact input document bytes")
    size, style = raw["ring_size"], raw["style"]
    if type(size) is not int or not 3 <= size <= MAX_RING_SIZE:
        raise ValueError(f"ring_size must be an integer from 3 to {MAX_RING_SIZE}")
    if not isinstance(style, str) or style not in {
        "regular",
        "benzene",
        "chair",
        "chair_flip",
        "boat",
    }:
        raise ValueError("style must be regular, benzene, chair, chair_flip, or boat")
    if style != "regular" and size != 6:
        raise ValueError("benzene, chair, chair_flip, and boat require ring_size 6")
    position = raw["position"]
    if (
        not isinstance(position, list)
        or len(position) != 2
        or any(
            not is_document_number(value) or abs(float(value)) > MAX_POSITION
            for value in position
        )
    ):
        raise ValueError(
            f"position must be two finite numbers within +/-{MAX_POSITION:g}"
        )
    if state.get("calculation_plan") is not None or state.get("perspective"):
        raise ValueError(
            "template insertion does not edit Calculation Plan or perspective documents"
        )
    if graphics_record_count(state) + 2 * size + 1 > MAX_GRAPHICS_RECORDS:
        raise ValueError(
            f"template insertion exceeds the {MAX_GRAPHICS_RECORDS}-graphics-record limit"
        )
    model = deserialize_model_state(state["model"])
    if (
        any(
            abs(value) > MAX_POSITION
            for atom in model.atoms.values()
            for value in (atom.x, atom.y)
        )
        or state["settings"]["bond_length_px"] > MAX_POSITION
    ):
        raise ValueError(
            "source geometry exceeds the supported template coordinate bounds"
        )
    inspect_components(state)
    atom_id, bond_id = _anchor(raw["anchor"], model)
    if atom_id is not None and style in {"chair", "chair_flip", "boat"}:
        raise ValueError(
            "chair and boat templates support free or bond anchors, not atom anchors"
        )
    anchor_ids = {atom_id} if atom_id is not None else set()
    if bond_id is not None:
        bond = model.bonds[bond_id]
        assert bond is not None
        anchor_ids = {bond.a, bond.b}
        allowed_orders = {1, 2} if style in {"regular", "benzene"} else {1}
        if bond.order not in allowed_orders or bond.style not in {
            "single",
            "double",
            "double_center",
            "double_outer",
        }:
            raise ValueError(
                "template bond anchor must be plain single, or plain double "
                "for regular rings and benzene"
            )
    for bond in model.bonds:
        if (
            bond is not None
            and anchor_ids.intersection((bond.a, bond.b))
            and bond.style in {"wedge", "hash"}
        ):
            raise ValueError(
                "template anchors must not touch wedge/hash stereochemistry"
            )
    for group in state.get("groups", []):
        if anchor_ids.intersection(group.get("atoms", [])):
            raise ValueError("template anchors must not split an existing native group")
    return TemplateInsertRequest(
        ring_size=size,
        ring_style=style,
        cursor_pos=(float(position[0]), float(position[1])),
        atom_id=atom_id,
        bond_id=bond_id,
    )


def _anchor(raw: object, model: MoleculeModel) -> tuple[int | None, int | None]:
    if not isinstance(raw, Mapping):
        raise ValueError("anchor must be an explicit free, atom, or bond object")
    kind = raw.get("kind")
    keys = {"free": {"kind"}, "atom": {"kind", "atom_id"}, "bond": {"kind", "a", "b"}}
    if not isinstance(kind, str) or kind not in keys or set(raw) != keys[kind]:
        raise ValueError("anchor has missing or unknown keys")
    ids = [raw[key] for key in sorted(keys[kind] - {"kind"})]
    if any(type(atom_id) is not int or atom_id not in model.atoms for atom_id in ids):
        raise ValueError("anchor atom IDs must reference existing atoms")
    if kind == "atom":
        return cast("int", raw["atom_id"]), None
    if kind == "bond":
        if raw["a"] == raw["b"]:
            raise ValueError("anchor bond endpoints must be distinct")
        for bond_id, bond in enumerate(model.bonds):
            if bond is not None and {bond.a, bond.b} == {raw["a"], raw["b"]}:
                return None, bond_id
        raise ValueError("anchor bond does not exist")
    return None, None


def insert_template(
    state: dict[str, Any], request: TemplateInsertRequest
) -> tuple[dict[str, Any], list[int]]:
    """Use the GUI's template resolver and recorded commit on a disposable canvas."""
    plan = plan_template_commit(request)
    if plan is None:
        raise ValueError("native template planner rejected the request")
    original = deserialize_model_state(state["model"])
    with offscreen_canvas(state, command="insert-template", pin_locale=True) as (
        canvas,
        session,
    ):
        from chemvas.ui.canvas_model_access import model_for
        from chemvas.ui.insert_template_commit_service import (
            apply_template_commit_resolution,
        )
        from chemvas.ui.template_geometry_resolver_service import (
            TemplateGeometryResolverService,
        )

        resolution = TemplateGeometryResolverService(canvas).resolve_insert(
            request, plan
        )
        expected_model, expected_ring = _planned_template(
            canvas, original, request, plan, resolution
        )
        if not apply_template_commit_resolution(
            canvas,
            request,
            plan,
            resolution,
            before_smiles_input=state.get("last_smiles_input"),
        ):
            raise ValueError(
                "native template insertion did not create a ring at the requested anchor"
            )
        model = model_for(canvas)
        snapshot, warnings = session.snapshot_state_with_warnings()
        if warnings:
            raise ValueError(
                "native template insertion produced serialization warnings: "
                + "; ".join(warnings)
            )
        if model != expected_model:
            raise ValueError(
                "inserted chemical records differ from the native template plan"
            )
        added_atoms = sorted(set(model.atoms) - set(original.atoms))
        for atom_id in added_atoms:
            atom = model.atoms[atom_id]
            if not all(
                math.isfinite(value) and abs(value) <= MAX_POSITION
                for value in (atom.x, atom.y)
            ):
                raise ValueError(
                    "native template coordinates exceed the supported bounds"
                )
        ring_count = len(state.get("ring_fills", []))
        if len(snapshot["ring_fills"]) != ring_count + 1:
            raise ValueError("native template insertion must add exactly one ring")
        if snapshot["ring_fills"][-1] != expected_ring:
            raise ValueError(
                "inserted ring metadata differs from the native template plan"
            )
        candidate = deepcopy(state)
        candidate["model"] = serialize_model_state(model)
        candidate["ring_fills"] = deepcopy(state.get("ring_fills", [])) + [
            snapshot["ring_fills"][-1]
        ]
        candidate["last_smiles_input"] = None
    inspect_components(candidate)
    return candidate, added_atoms


def _planned_template(
    canvas: Any,
    original: MoleculeModel,
    request: TemplateInsertRequest,
    plan: TemplateInsertPlan,
    resolution: TemplateInsertResolution | None,
) -> tuple[MoleculeModel, dict[str, Any]]:
    """Pin native resolved geometry and bond policy before the recorded mutation."""
    from PyQt6.QtCore import QPointF

    from chemvas.features.insertion import alternating_ring_bond_specs
    from chemvas.ui.canvas_service_ports import (
        ring_fill_scene_service_for_access,
        structure_insert_build_service_for_access,
    )
    from chemvas.ui.scene_item_state import ring_state_dict_for
    from chemvas.ui.structure_build_committer import StructureBuildCommitter

    if plan.generator == "benzene":
        geometry = structure_insert_build_service_for_access(
            canvas
        ).benzene_ring_points(
            QPointF(*request.cursor_pos),
            attach_atom_id=request.atom_id,
            attach_bond_id=request.bond_id,
        )
        points = [(p.x(), p.y()) for p in geometry[0]] if geometry is not None else None
    else:
        points = resolution.points if resolution is not None else None
    if points is None or len(points) != request.ring_size:
        raise ValueError("native template plan did not resolve the requested ring")
    anchor_ids = {request.atom_id} if request.atom_id is not None else set()
    if request.bond_id is not None:
        anchor = original.bonds[request.bond_id]
        assert anchor is not None
        anchor_ids = {anchor.a, anchor.b}
    expected = deepcopy(original)
    ring_ids: list[int] = []
    for x, y in points:
        matches = [
            atom_id
            for atom_id in anchor_ids
            if math.dist((x, y), (original.atoms[atom_id].x, original.atoms[atom_id].y))
            <= 1e-7
        ]
        if len(matches) > 1:
            raise ValueError("native template plan has ambiguous anchor geometry")
        if matches:
            ring_ids.append(matches[0])
        else:
            atom_id = expected.next_atom_id
            expected.atoms[atom_id] = Atom("C", x, y)
            expected.next_atom_id += 1
            ring_ids.append(atom_id)
    if len(set(ring_ids)) != request.ring_size or not anchor_ids <= set(ring_ids):
        raise ValueError("native template plan does not preserve the explicit anchor")
    orders = (
        [order for _, _, order in alternating_ring_bond_specs(ring_ids)]
        if plan.generator == "benzene"
        else None
    )
    resolved_orders = StructureBuildCommitter(canvas).resolved_ring_bond_orders(
        ring_ids, orders
    )
    original_pairs = {
        frozenset((bond.a, bond.b)) for bond in original.bonds if bond is not None
    }
    for index, a in enumerate(ring_ids):
        b = ring_ids[(index + 1) % len(ring_ids)]
        if frozenset((a, b)) not in original_pairs:
            expected.bonds.append(Bond(a, b, order=resolved_orders[index]))
    ring_item = ring_fill_scene_service_for_access(canvas).create_ring_fill_item(
        [QPointF(x, y) for x, y in points], ring_ids
    )
    ring_state = ring_state_dict_for(canvas, ring_item)
    ring_state.pop("kind")  # Document ring records omit the generic scene-item tag.
    # Native document snapshots pin ring points to their atoms, including exact
    # existing anchor coordinates rather than resolver round-off at that vertex.
    ring_state["points"] = [
        (expected.atoms[atom_id].x, expected.atoms[atom_id].y) for atom_id in ring_ids
    ]
    return expected, ring_state


__all__ = ["insert_template", "run", "validate_template_request"]
