"""Publish a checked pair and its exact source snapshot without overwriting files."""

from __future__ import annotations

import contextlib
import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from chemvas.core.document_io import atomic_create_bytes


def publish_handoff_folder(
    directory: Path, observation: dict[str, Any], source: bytes
) -> None:
    if observation["handoff"]["status"] != "ready":
        raise ValueError("The pair has not passed the endpoint checks.")
    payload = observation["payload"]["data"]
    if payload["source"]["document_sha256"] != hashlib.sha256(source).hexdigest():
        raise ValueError("The checked source snapshot has changed.")
    files = {
        "source.chemvas": source,
        "machine.json": (
            json.dumps(observation, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
        ).encode(),
    }
    for side, geometry in payload["endpoint_geometry"]["sides"].items():
        components = geometry["components"]
        for component in components:
            xyz = component["xyz"]["content"]
            name = f"{side}-component-{component['component_index']}.xyz"
            if len(components) == 1:
                rows = xyz.splitlines()[2:]
                indices = component["atom_indices"]
                rows = [row for _, row in sorted(zip(indices, rows, strict=True))]
                xyz = (
                    f"{len(rows)}\nChemvas {side}; canonical path atom order\n"
                    + "\n".join(rows)
                    + "\n"
                )
                name = f"{side}.xyz"
            files[name] = xyz.encode()
    files["README.txt"] = (
        b"Chemvas reaction pair for external NEB preparation\n\n"
        b"source.chemvas is the exact checked drawing and plan snapshot.\n"
        b"machine.json records atom identities, charge, multiplicity, bond changes,\n"
        b"geometry generation and limitations. Path indices are zero based.\n"
        b"Single-component XYZ files use canonical path atom order on both sides.\n"
        b"Multiple components remain separate: component XYZ rows follow their\n"
        b"atom_indices in machine.json. Their relative placement is NOT provided.\n"
        b"Review geometry generation outcomes in machine.json. These are initial\n"
        b"geometries, not optimized NEB endpoints. Arrange components, optimize\n"
        b"endpoints and review electronic states with your external workflow.\n"
        b"Chemvas does not run NEB or infer transition states or spin states.\n"
    )
    directory.mkdir()  # Existing files, directories and symlinks are never replaced.
    created: list[Path] = []
    try:
        for name, content in files.items():
            path = directory / name
            atomic_create_bytes(path, content)
            created.append(path)
    except (OSError, ValueError):
        for path in reversed(created):
            path.unlink(missing_ok=True)
        # Never remove files created concurrently by someone else.
        with contextlib.suppress(OSError):
            directory.rmdir()
        raise
