"""Compare macrocycle imports without changing the application's depiction policy.

Run in a fresh process with PYTHONPATH=app and the optional RDKit backend installed.
The pinned corpus is read locally; evaluation never fetches or rewrites structures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import statistics
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw
from rdkit import Chem, rdBase
from rdkit.Chem import rdDepictor, rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D

from chemvas.core.rdkit_adapter import RDKitAdapter


def geometry(model):
    ids = sorted(model.atoms)
    points = {i: (model.atoms[i].x, model.atoms[i].y) for i in ids}
    bonds = [(b.a, b.b) for b in model.bonds if b is not None]
    connected = {frozenset(pair) for pair in bonds}
    lengths = [math.dist(points[a], points[b]) for a, b in bonds]
    median = statistics.median(lengths)
    if any(length <= 0 for length in lengths) or not all(
        math.isfinite(v) for p in points.values() for v in p
    ):
        raise ValueError("Depiction has nonfinite coordinates or zero bond scale")
    distances = [
        math.dist(points[a], points[b]) / median
        for j, a in enumerate(ids)
        for b in ids[j + 1 :]
        if frozenset((a, b)) not in connected
    ]
    on_bonds = []
    for i in ids:
        for a, b in bonds:
            if i in (a, b):
                continue
            px, py = points[i]
            ax, ay = points[a]
            bx, by = points[b]
            dx, dy = bx - ax, by - ay
            denominator = dx * dx + dy * dy
            if denominator == 0:
                continue
            t = ((px - ax) * dx + (py - ay) * dy) / denominator
            if (
                0 < t < 1
                and math.hypot(px - ax - t * dx, py - ay - t * dy) / median < 0.1
            ):
                on_bonds.append([i, a, b])
    return {
        "finite_nondegenerate_geometry": True,
        "nonbonded_pairs_below_0_5": sum(d < 0.5 for d in distances),
        "closest_nonbonded_pair": min(distances),
        "atom_bond_contacts_below_0_1": len(on_bonds),
        "atoms_in_bond_contacts": len({c[0] for c in on_bonds}),
        "max_bond_over_median": max(lengths) / median,
        "min_bond_over_median": min(lengths) / median,
    }


def evaluate(corpus: Path, output: Path) -> dict:
    raw = corpus.read_bytes()
    fixtures = json.loads(raw)["molecules"]
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError("Corpus molecules must be a nonempty list")
    output.mkdir(parents=True, exist_ok=True)
    results = []
    images = []
    for fixture in fixtures:
        source = Chem.MolFromSmiles(fixture["smiles"])
        if source is None:
            raise ValueError(f"Invalid corpus molecule: {fixture['name']}")
        if rdMolDescriptors.CalcMolFormula(source) != fixture["formula"]:
            raise ValueError(f"Corpus formula mismatch: {fixture['name']}")
        if Chem.MolToInchiKey(source) != fixture["inchikey"]:
            raise ValueError(f"Corpus InChIKey mismatch: {fixture['name']}")
        expected = Chem.MolToSmiles(source, canonical=True, isomericSmiles=True)
        for method in ("rdkit-default", "coordgen"):
            adapter = RDKitAdapter()
            # Scoped preference restores the prior value on exit. This isolated
            # evaluator never changes the installed app or library defaults.
            with rdDepictor.UsingCoordGen(method == "coordgen"):
                model = adapter.smiles_to_2d(fixture["smiles"])
            result = {
                "molecule": fixture["name"],
                "method": method,
                "import_accepted": model is not None,
                "specified_tetrahedral_centers": sum(
                    a.GetChiralTag() != Chem.ChiralType.CHI_UNSPECIFIED
                    for a in source.GetAtoms()
                ),
            }
            if model is None:
                result["error"] = adapter.last_error
                results.append(result)
                images.append(Image.new("RGB", (800, 600), "white"))
                continue
            restored = adapter._build_conversion_rdkit_mol(model)
            if restored is None:
                raise ValueError(
                    f"Imported model could not be reconstructed: {fixture['name']}"
                )
            result["isomeric_identity_preserved"] = (
                Chem.MolToSmiles(restored, canonical=True, isomericSmiles=True)
                == expected
            )
            result.update(geometry(model))
            # Molfile and image contain the actual imported coordinates, not a
            # second call to the coordinate generator.
            stem = f"{fixture['name']}-{method}"
            (output / f"{stem}.mol").write_text(Chem.MolToMolBlock(restored))
            drawer = rdMolDraw2D.MolDraw2DCairo(800, 600)
            drawer.drawOptions().prepareMolsBeforeDrawing = False
            drawer.DrawMolecule(restored)
            drawer.FinishDrawing()
            images.append(Image.open(BytesIO(drawer.GetDrawingText())).convert("RGB"))
            results.append(result)
    sheet = Image.new("RGB", (1600, 660 * len(fixtures)), "white")
    painter = ImageDraw.Draw(sheet)
    for i, (result, img) in enumerate(zip(results, images, strict=True)):
        x, y = (i % 2) * 800, (i // 2) * 660
        sheet.paste(img, (x, y + 60))
        painter.text(
            (x + 20, y + 12), f"{result['molecule']} / {result['method']}", fill="black"
        )
        painter.text(
            (x + 20, y + 30),
            f"accepted={result['import_accepted']} identity={result.get('isomeric_identity_preserved')}",
            fill="black",
        )
    sheet.save(output / "comparison.png")
    report = {
        "rdkit": rdBase.rdkitVersion,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "corpus_sha256": hashlib.sha256(raw).hexdigest(),
        "results": results,
    }
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus", type=Path, default=Path("tests/fixtures/depiction/macrocycles.json")
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.corpus, args.output_dir)
    print(json.dumps(report, indent=2))
    if not all(
        result.get("isomeric_identity_preserved")
        and result.get("finite_nondegenerate_geometry")
        for result in report["results"]
    ):
        raise SystemExit(
            "At least one depiction failed import or identity preservation"
        )


if __name__ == "__main__":
    main()
