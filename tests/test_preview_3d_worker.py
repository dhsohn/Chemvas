from __future__ import annotations

from core.model import MoleculeModel
from core.rdkit_types import (
    Molecule3DAtom,
    Molecule3DScene,
    MoleculeIdentifiers,
    RDKitResult,
)
from ui.preview_3d_worker import Preview3DWorker


class RecordingPreviewAdapter:
    def __init__(self) -> None:
        self.identifier_annotations: list[dict[int, dict[str, int]]] = []
        self.scene_annotations: list[dict[int, dict[str, int]] | None] = []

    def compute_identifiers(self, model):
        annotations = getattr(model, "atom_annotations", {})
        self.identifier_annotations.append(
            {atom_id: dict(values) for atom_id, values in annotations.items()}
        )
        formal_charge = sum(values.get("formal_charge", 0) for values in annotations.values())
        radical_electrons = sum(values.get("radical_electrons", 0) for values in annotations.values())
        return MoleculeIdentifiers(
            formula=f"charge={formal_charge};radical={radical_electrons}",
            mw=42.5 + formal_charge + radical_electrons,
            smiles=f"[charge={formal_charge}].[radical={radical_electrons}]",
            inchikey="ANNOTATED",
        )

    def model_to_3d_scene_result(self, model, atom_annotations=None):
        self.scene_annotations.append(atom_annotations)
        return RDKitResult(
            Molecule3DScene(
                atoms=(Molecule3DAtom("N", 0.0, 0.0, 0.0),),
                bonds=(),
            ),
            None,
        )


def test_preview_worker_uses_payload_annotations_for_charged_radical_identifiers() -> None:
    model = MoleculeModel()
    nitrogen_id = model.add_atom("N", 0.0, 0.0)
    carbon_id = model.add_atom("C", 1.0, 0.0)
    annotations = {
        nitrogen_id: {"formal_charge": 1},
        carbon_id: {"radical_electrons": 1},
    }
    adapter = RecordingPreviewAdapter()
    emissions = []
    worker = Preview3DWorker(7, adapter, model, annotations)
    worker.finished.connect(lambda *args: emissions.append(args))

    worker.run()

    assert adapter.identifier_annotations == [annotations]
    assert adapter.scene_annotations == [annotations]
    assert model.atom_annotations == {}
    assert emissions
    assert emissions[0][0:5] == (
        7,
        "charge=1;radical=1",
        44.5,
        "[charge=1].[radical=1]",
        "ANNOTATED",
    )
    assert emissions[0][5] is not None
    assert emissions[0][6] is None
