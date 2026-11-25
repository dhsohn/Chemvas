from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from chemvas.bootstrap import reaction_assembly
from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.reaction_assembly import assemble_reaction_cdxml

APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def _normalized_input(*, shuffled: bool = False) -> bytes:
    parts = [
        (
            '<fragment id="10">'
            '<n id="11" p="0 0" Element="7" Charge="1"/><n id="12" p="20 0" Element="6"/>'
            '<b id="13" B="11" E="12"/>'
            "</fragment>"
        ),
        '<fragment id="20"><n id="21" p="0 0" Element="35" Charge="-1"/></fragment>',
        (
            '<fragment id="30">'
            '<n id="31" p="0 0" Element="6"/><n id="32" p="20 0" Element="8"/>'
            '<b id="33" B="31" E="32"/>'
            "</fragment>"
        ),
        '<fragment id="40"><n id="41" p="0 0" Element="7"/></fragment>',
        '<t id="50"><s font="3" size="12" face="1">+</s></t>',
        '<t id="51"><s font="3" size="10" face="1">Heat</s><s font="3" size="8" face="32">2</s></t>',
        '<graphic id="60" SupersededBy="62" GraphicType="Line" ArrowType="FullHead"/>',
        '<arrow id="62" ArrowheadHead="Full" ArrowheadTail="HalfHead"/>',
        (
            '<scheme id="70"><step id="71" '
            'ReactionStepReactants="10 20" '
            'ReactionStepProducts="30 50 40" '
            'ReactionStepArrows="60" '
            'ReactionStepObjectsAboveArrow="51"/></scheme>'
        ),
    ]
    if shuffled:
        random.Random(0).shuffle(parts)
    body = "".join(parts)
    return (
        '<CDXML CaptionFont="3" CaptionSize="10" BondLength="20">'
        '<fonttable><font id="3" name="Arial"/></fonttable>'
        f'<page id="1">{body}</page></CDXML>'
    ).encode()


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from chemvas.bootstrap.application import main; main()",
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_assemble_reaction_help_lists_required_output_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["chemvas", "assemble-reaction", "-h"],
    )
    with pytest.raises(SystemExit) as exit_info:
        reaction_assembly.run(["assemble-reaction", "-h"])
    assert exit_info.value.code == 0


def test_assemble_reaction_cli_writes_layout_and_preserves_role_ids(
    tmp_path: Path,
) -> None:
    source = tmp_path / "normalized.cdxml"
    output = tmp_path / "assembled.cdxml"
    source.write_bytes(_normalized_input())
    before_ids = {
        element.get("id")
        for element in ET.fromstring(source.read_bytes()).iter()
        if element.get("id")
    }

    result = _run("assemble-reaction", str(source), "--output", str(output))

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["format"] == "chemvas-assemble-reaction-report"
    assert report["written"] is True
    assert report["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assembled = output.read_bytes()
    root = ET.fromstring(assembled)
    after_ids = {element.get("id") for element in root.iter() if element.get("id")}
    assert before_ids == after_ids
    page = root.find("page")
    assert page is not None
    assert page.get("BoundingBox")
    arrow = root.find('.//arrow[@id="62"]')
    assert arrow is not None
    assert arrow.get("Head3D")
    assert arrow.get("Tail3D")
    assert root.find('.//t[@id="50"]').get("p")
    graphic = root.find('.//graphic[@id="60"]')
    assert graphic is not None
    assert graphic.get("BoundingBox")
    reopened = parse_cdxml_document(assembled).state
    assert any(
        atom.get("element") == "Br" for atom in reopened["model"]["atoms"].values()
    )


def test_assemble_reaction_is_invariant_to_shuffled_page_order(tmp_path: Path) -> None:
    ordered = assemble_reaction_cdxml(_normalized_input())
    shuffled = assemble_reaction_cdxml(_normalized_input(shuffled=True))

    def geometry(raw: bytes) -> dict[str, tuple[str, str | None]]:
        root = ET.fromstring(raw)
        values: dict[str, tuple[str, str | None]] = {}
        for element in root.iter():
            identity = element.get("id")
            if identity is None:
                continue
            values[identity] = (element.get("p", ""), element.get("BoundingBox"))
        return values

    assert geometry(ordered) == geometry(shuffled)


def test_counterion_stays_adjacent_without_inserted_plus(tmp_path: Path) -> None:
    raw = assemble_reaction_cdxml(_normalized_input())
    root = ET.fromstring(raw)
    substrate = root.find('.//n[@id="11"]')
    counterion = root.find('.//n[@id="21"]')
    assert substrate is not None and counterion is not None
    sub_x = float(substrate.get("p", "0 0").split()[0])
    br_x = float(counterion.get("p", "0 0").split()[0])
    assert abs(br_x - sub_x) < 20
    assert float(counterion.attrib["p"].split()[1]) < float(
        substrate.attrib["p"].split()[1]
    )
    assert root.find('.//t[@id="50"]') is not None


def test_assemble_reaction_rejects_multi_step() -> None:
    raw = (
        _normalized_input()
        .decode()
        .replace(
            "</scheme>",
            '<step id="72" ReactionStepReactants="10" ReactionStepProducts="30" ReactionStepArrows="62"/></scheme>',
        )
    )
    with pytest.raises(ValueError, match="exactly one step"):
        assemble_reaction_cdxml(raw.encode())


def test_assemble_reaction_rejects_page_bounds_on_input() -> None:
    raw = (
        _normalized_input()
        .decode()
        .replace('<page id="1">', '<page id="1" BoundingBox="0 0 100 100">')
    )
    with pytest.raises(ValueError, match="page position bounds"):
        assemble_reaction_cdxml(raw.encode())


def test_render_document_accepts_assembled_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("PyQt6")
    output = tmp_path / "assembled.cdxml"
    output.write_bytes(assemble_reaction_cdxml(_normalized_input()))
    rendered = tmp_path / "assembled.svg"
    result = _run(
        "render-document",
        str(output),
        "--output",
        str(rendered),
    )
    assert result.returncode == 0, result.stderr
    assert rendered.stat().st_size > 0


def test_application_help_includes_assemble_reaction(
    tmp_path: Path,
) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(APP_ROOT)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from chemvas.bootstrap.application import main; main()",
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "assemble-reaction" in result.stdout
