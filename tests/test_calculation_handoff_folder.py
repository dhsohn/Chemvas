from __future__ import annotations

import json
from copy import deepcopy
from typing import TYPE_CHECKING

import pytest

from chemvas.core import calculation_handoff_folder as publication
from chemvas.core.calculation_handoff import build_calculation_handoff
from chemvas.core.document_io import read_document
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
    data = source.read_bytes()
    artifact = build_calculation_handoff(
        read_document(source), data, step_id="S01", adapter_factory=_StateFakeAdapter
    )
    return artifact, data


def test_publish_preserves_source_and_separate_components(tmp_path: Path) -> None:
    artifact, source = _checked_pair(tmp_path)
    folder = tmp_path / "pair"
    publication.publish_handoff_folder(folder, artifact, source)
    assert (folder / "source.chemvas").read_bytes() == source
    assert json.loads((folder / "machine.json").read_bytes()) == artifact
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
        publication.publish_handoff_folder(folder, artifact, source)
    assert {path.name: path.read_bytes() for path in folder.iterdir()} == before


def test_single_component_xyz_uses_canonical_order(tmp_path: Path) -> None:
    artifact, source = _checked_pair(tmp_path)
    for side in artifact["payload"]["data"]["endpoint_geometry"]["sides"].values():
        component = deepcopy(side["components"][0])
        component["atom_indices"] = [1, 0]
        component["xyz"]["content"] = "2\nreversed\nO 1 0 0\nC 0 0 0\n"
        side["components"] = [component]
    folder = tmp_path / "single"
    publication.publish_handoff_folder(folder, artifact, source)
    assert (folder / "product.xyz").read_text().splitlines()[2:] == [
        "C 0 0 0",
        "O 1 0 0",
    ]


def test_blocked_or_stale_check_never_creates_output(tmp_path: Path) -> None:
    artifact, source = _checked_pair(tmp_path)
    folder = tmp_path / "pair"
    with pytest.raises(ValueError, match="snapshot"):
        publication.publish_handoff_folder(folder, artifact, source + b" ")
    artifact["handoff"]["status"] = "blocked"
    with pytest.raises(ValueError, match="checks"):
        publication.publish_handoff_folder(folder, artifact, source)
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
        publication.publish_handoff_folder(folder, artifact, source)
    assert {path.name for path in folder.iterdir()} == {"unrelated.txt"}
    assert (folder / "unrelated.txt").read_text() == "keep"
