from __future__ import annotations

import argparse
import sys
from pathlib import Path

from chemvas.bootstrap.document_cli_shared import (
    MAX_DOCUMENT_BYTES,
    encode_cli_document,
    json_text,
    read_json_request,
    validate_source_document,
)
from chemvas.core.calculation_handoff import (
    build_calculation_handoff,
    write_calculation_handoff,
)
from chemvas.core.document_io import (
    atomic_create_bytes,
    create_document,
    read_document,
    read_exact_document,
)
from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    calculation_plan_to_state,
)
from chemvas.domain.document.inspection import ComponentSummary, inspect_components
from chemvas.features.calculation_bundle import (
    calculation_plan_report,
    validate_calculation_plan,
)


def run(argv: list[str]) -> int:
    parser = _argument_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            payload = _inspect(Path(args.document))
            sys.stdout.write(json_text(payload))
            return 0
        if args.command == "attach-plan":
            result = _attach_plan(
                Path(args.document),
                plan_path=Path(args.plan),
                output=Path(args.output),
            )
            sys.stdout.write(json_text(result))
            return 0
        if args.command == "inspect-plan":
            payload = _inspect_plan(Path(args.document))
            sys.stdout.write(json_text(payload))
            return 0
        if args.command == "pack-step":
            artifact = _pack_step(
                Path(args.document),
                step_id=args.step,
                output=Path(args.output),
            )
            sys.stdout.write(json_text(artifact))
            return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"chemvas: error: {exc}\n")
    parser.error("a command is required")
    return 2


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chemvas",
        description="Chemvas GUI and headless calculation-plan/bundle tools.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect", help="inspect connected structures as JSON without starting Qt"
    )
    inspect_parser.add_argument("document", help="input .chemvas document")

    attach_parser = subparsers.add_parser(
        "attach-plan",
        help="validate a Calculation Plan JSON file and embed it in a new .chemvas file",
    )
    attach_parser.add_argument("document", help="input .chemvas document")
    attach_parser.add_argument("plan", help="Calculation Plan v2 JSON file")
    attach_parser.add_argument("--output", required=True)

    inspect_plan_parser = subparsers.add_parser(
        "inspect-plan",
        help="inspect embedded calculation states and elementary steps as JSON",
    )
    inspect_plan_parser.add_argument("document", help="input .chemvas document")

    pack_step_parser = subparsers.add_parser(
        "pack-step",
        help="create one non-overwriting elementary-step machine.json artifact",
    )
    pack_step_parser.add_argument("document", help="input .chemvas document")
    pack_step_parser.add_argument("--step", required=True)
    pack_step_parser.add_argument("--output", required=True)
    return parser


def _attach_plan(
    source: Path,
    *,
    plan_path: Path,
    output: Path,
) -> dict[str, object]:
    validate_source_document(source)
    _validate_new_chemvas_output(source, output)
    if not plan_path.is_file():
        raise ValueError(f"calculation plan does not exist: {plan_path}")
    _, plan_payload = read_json_request(
        plan_path,
        max_bytes=MAX_DOCUMENT_BYTES,
        limit_message=f"calculation plan exceeds the {MAX_DOCUMENT_BYTES}-byte limit",
        invalid_message="Invalid Calculation Plan JSON file.",
    )
    _source_bytes, document = read_exact_document(source)
    plan = validate_calculation_plan(document.state, plan_payload)
    state = dict(document.state)
    state["calculation_plan"] = calculation_plan_to_state(plan)
    output_document = create_document(state, CANVAS_FILE_VERSION)
    atomic_create_bytes(
        output,
        encode_cli_document(output_document.payload, max_bytes=MAX_DOCUMENT_BYTES),
    )
    report = calculation_plan_report(output_document.state)
    return {
        "format": "chemvas-calculation-plan-attachment",
        "version": 1,
        "source": str(source),
        "output": str(output),
        "chemvas_document_version": CANVAS_FILE_VERSION,
        "state_count": len(plan.states),
        "step_count": len(plan.steps),
        "steps": report["steps"],
    }


def _inspect_plan(source: Path) -> dict[str, object]:
    validate_source_document(source)
    document = read_document(source)
    report = calculation_plan_report(document.state)
    return {
        **report,
        "source": str(source),
        "chemvas_document_version": int(document.payload["version"]),
    }


def _inspect(source: Path) -> dict[str, object]:
    validate_source_document(source)
    document = read_document(source)
    components = inspect_components(document.state)
    return {
        "format": "chemvas-structure-inspection",
        "version": 1,
        "source": str(source),
        "chemvas_document_version": int(document.payload["version"]),
        "component_count": len(components),
        "components": [_component_dict(component) for component in components],
    }


def _pack_step(
    source: Path,
    *,
    step_id: str,
    output: Path,
) -> dict[str, object]:
    validate_source_document(source)
    _validate_new_step_output(output)
    source_bytes, document = read_exact_document(source)
    observation = build_calculation_handoff(
        document, source_bytes, step_id=step_id, adapter_factory=RDKitAdapter
    )
    write_calculation_handoff(output, observation)
    return observation


def _component_dict(component: ComponentSummary) -> dict[str, object]:
    return {
        "index": component.index,
        "atom_ids": list(component.atom_ids),
        "atom_count": len(component.atom_ids),
        "bond_count": component.bond_count,
        "formula_labels": dict(component.formula_labels),
        "formal_charge": component.formal_charge,
        "radical_electrons": component.radical_electrons,
        "bounds": list(component.bounds),
    }


def _validate_new_step_output(output: Path) -> None:
    if output.name != "machine.json":
        raise ValueError("pack-step output filename must be machine.json")
    if output.exists() or output.is_symlink():
        raise ValueError(f"output path already exists: {output}")
    if not output.parent.is_dir():
        raise ValueError(f"output parent directory does not exist: {output.parent}")


def _validate_new_chemvas_output(source: Path, output: Path) -> None:
    if output.suffix.lower() != ".chemvas":
        raise ValueError("output must use the .chemvas filename extension")
    if output.absolute() == source.absolute():
        raise ValueError(
            "attach-plan writes a new document; output must differ from input"
        )
    if output.exists() or output.is_symlink():
        raise ValueError(f"output path already exists: {output}")
    if not output.parent.is_dir():
        raise ValueError(f"output parent directory does not exist: {output.parent}")


__all__ = ["run"]
