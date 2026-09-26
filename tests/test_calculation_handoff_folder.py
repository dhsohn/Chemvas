from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import TYPE_CHECKING

import pytest

from chemvas import __version__
from chemvas.bootstrap.document_cli_shared import json_text
from chemvas.core import calculation_handoff_folder as publication
from chemvas.core.document_io import parse_document, read_exact_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.domain.json_io import strict_json_loads
from chemvas.features.calculation_bundle import build_calculation_handoff
from tests.calculation_artifact_support import _StateFakeAdapter
from tests.calculation_workflow_support import (
    _validate_common_machine,
    _write_document_with_plan,
)

if TYPE_CHECKING:
    from pathlib import Path


def _checked_pair(tmp_path: Path):
    source = tmp_path / "source.chemvas"
    _write_document_with_plan(source)
    exact_source = read_exact_document(source)
    artifact = build_calculation_handoff(
        exact_source,
        step_id="S01",
        adapter_factory=_StateFakeAdapter,
        producer_version=__version__,
    )
    return artifact, exact_source[0]


def _worker_bytes(artifact: dict) -> bytes:
    """Encode an observation as the pack-step worker writes machine.json."""
    return json_text(artifact).encode("utf-8")


def test_publish_preserves_source_and_separate_components(tmp_path: Path) -> None:
    artifact, source = _checked_pair(tmp_path)
    folder = tmp_path / "pair"
    publication.publish_handoff_folder(folder, _worker_bytes(artifact), source)
    assert (folder / "source.chemvas").read_bytes() == source
    assert (folder / "machine.json").read_bytes() == _worker_bytes(artifact)
    assert not (folder / "reactant.xyz").exists()
    for side, geometry in artifact["payload"]["data"]["endpoint_geometry"][
        "sides"
    ].items():
        for component in geometry["components"]:
            assert (
                folder / f"{side}-component-{component['component_index']}.xyz"
            ).read_text() == component["xyz"]["content"]
    _validate_common_machine(folder / "machine.json")
    before = {path.name: path.read_bytes() for path in folder.iterdir()}
    with pytest.raises(FileExistsError):
        publication.publish_handoff_folder(folder, _worker_bytes(artifact), source)
    assert {path.name: path.read_bytes() for path in folder.iterdir()} == before


def test_folder_publishes_the_checked_machine_json_bytes(tmp_path: Path) -> None:
    artifact, source = _checked_pair(tmp_path)
    # A re-encoding would escape this text; the published file must not differ
    # from the bytes the check wrote.
    artifact["payload"]["data"]["geometry_scope"]["intended_use"] += " (café)"
    checked = _worker_bytes(artifact)
    folder = tmp_path / "pair"

    publication.publish_handoff_folder(folder, checked, source)

    assert (folder / "machine.json").read_bytes() == checked


def test_single_component_xyz_uses_canonical_order(tmp_path: Path) -> None:
    artifact, source = _checked_pair(tmp_path)
    for side in artifact["payload"]["data"]["endpoint_geometry"]["sides"].values():
        component = deepcopy(side["components"][0])
        component["atom_indices"] = [1, 0]
        component["xyz"]["content"] = "2\nreversed\nO 1 0 0\nC 0 0 0\n"
        side["components"] = [component]
    folder = tmp_path / "single"
    publication.publish_handoff_folder(folder, _worker_bytes(artifact), source)
    assert (folder / "product.xyz").read_text().splitlines()[2:] == [
        "C 0 0 0",
        "O 1 0 0",
    ]


def test_observation_source_facts_come_from_one_exact_read(tmp_path: Path) -> None:
    artifact, source = _checked_pair(tmp_path)
    operation_digest = hashlib.sha256(
        b"chemvas-elementary-step-v2\0" + source + b"\0S01"
    ).hexdigest()

    assert artifact["payload"]["data"]["source"] == {
        "document_sha256": hashlib.sha256(source).hexdigest(),
        "document_bytes": len(source),
        "chemvas_document_version": CANVAS_FILE_VERSION,
    }
    assert artifact["operation"]["id"] == f"step-{operation_digest}"


def test_handoff_refuses_a_document_without_the_readers_digest(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.chemvas"
    _write_document_with_plan(source)
    data = source.read_bytes()

    with pytest.raises(ValueError, match="exact-bytes reader"):
        build_calculation_handoff(
            (data, parse_document(strict_json_loads(data))),
            step_id="S01",
            adapter_factory=_StateFakeAdapter,
            producer_version=__version__,
        )


def test_blocked_or_stale_check_never_creates_output(tmp_path: Path) -> None:
    artifact, source = _checked_pair(tmp_path)
    folder = tmp_path / "pair"
    with pytest.raises(ValueError, match="snapshot"):
        publication.publish_handoff_folder(
            folder, _worker_bytes(artifact), source + b" "
        )
    artifact["handoff"]["status"] = "blocked"
    with pytest.raises(ValueError, match="checks"):
        publication.publish_handoff_folder(folder, _worker_bytes(artifact), source)
    assert not folder.exists()


@pytest.mark.parametrize("failure", [OSError, ValueError])
def test_mid_export_failure_removes_only_owned_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: type[Exception]
) -> None:
    artifact, source = _checked_pair(tmp_path)
    folder = tmp_path / "pair"
    original = publication.atomic_create_bytes

    def fail(path: Path, content: bytes) -> None:
        if path.name == "machine.json":
            (folder / "unrelated.txt").write_text("keep")
            raise failure("publication failed")
        original(path, content)

    monkeypatch.setattr(publication, "atomic_create_bytes", fail)
    with pytest.raises(failure, match="publication failed"):
        publication.publish_handoff_folder(folder, _worker_bytes(artifact), source)
    assert {path.name for path in folder.iterdir()} == {"unrelated.txt"}
    assert (folder / "unrelated.txt").read_text() == "keep"
