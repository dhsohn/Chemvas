from __future__ import annotations

import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from itertools import pairwise
from pathlib import Path

import pytest

from chemvas.bootstrap.web_adapter import (
    BrowserSession,
    StaleRevisionError,
    edit_document,
    new_document,
)
from chemvas.domain.document import (
    VALID_ARROW_KINDS,
    MoleculeModel,
    extract_document_state,
    serialize_model_state_with_warnings,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def desktop_canvas(qt_application):
    from tests.canvas_factory import build_canvas_view

    canvas = build_canvas_view()
    yield canvas
    canvas.services.canvas_scene_reset_service.clear_scene()
    canvas.close()


def mol_chain():
    """C-C-C-C-N-O with a wedge, a hash, an unspecified double and a ring bond."""
    model = MoleculeModel()
    ids = [
        model.add_atom(element, 40.0 + 20.0 * index, 60.0 + 12.0 * (index % 2))
        for index, element in enumerate("CCCCNO")
    ]
    for (a, b), order, style in zip(
        [*pairwise(ids), (ids[0], ids[2])],
        (1, 1, 2, 1, 1, 1),
        ("wedge", "hash", "double_either", "single", "single", "single"),
        strict=True,
    ):
        bond_id = model.add_bond(a, b, order)
        model.bonds[bond_id] = replace(model.bonds[bond_id], style=style)
    return model


def mol_document(model, marks=()):
    """A browser document of ``model`` with charge and radical marks on atoms."""
    source = new_document()
    source["state"]["model"] = serialize_model_state_with_warnings(model)[0]
    source["state"]["marks"] = [
        {
            "kind": kind,
            "text": None,
            "atom_id": atom_id,
            "dx": 8.0,
            "dy": -8.0,
            "x": 0.0,
            "y": 0.0,
        }
        for atom_id, kind in marks
    ]
    return source


def loaded_session(source):
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    return session


def export_mol(session, selection):
    return session.dispatch(
        {"revision": session.revision, "action": "export_mol", "selection": selection}
    )


def unchanged(session):
    """Everything an export must leave as it was."""
    return (
        session.revision,
        deepcopy(session.info),
        session.saved,
        session.name,
        session.history.can_undo(),
        session.history.can_redo(),
    )


@pytest.mark.parametrize(
    "target", ["bonds", "all", "mark", "mixed", "atoms", "stored", "summed"]
)
def test_browser_mol_export_matches_the_desktop_selected_export(
    desktop_canvas, tmp_path, target
):
    from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for

    source = mol_document(mol_chain(), [(4, "plus"), (5, "radical")])
    if target == "stored":
        source = mol_document(mol_chain())
        source["state"]["model"]["atom_annotations"] = {4: {"formal_charge": 1}}
    if target == "summed":
        source = mol_document(
            mol_chain(), [(4, "plus"), (4, "plus"), (5, "radical"), (5, "radical")]
        )
    documents = desktop_canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    # Start from the serialized native state so item IDs are identical.
    source["state"] = documents.snapshot_state()
    bond_items = desktop_canvas.runtime_state.bond_graphics_state.bond_items
    bond_ids = range(len(desktop_canvas.model.bonds))
    if target == "bonds":
        items = [bond_items[0][0], bond_items[1][0]]
        selection = [{"target": "bond", "id": 0}, {"target": "bond", "id": 1}]
    elif target in {"all", "mixed", "atoms", "stored", "summed"}:
        atom_ids = (
            [0, 1, 2] if target == "atoms" else sorted(desktop_canvas.model.atoms)
        )
        bond_ids = [] if target == "atoms" else [0] if target == "mixed" else bond_ids
        items = [visible_atom_item_for(desktop_canvas, i) for i in atom_ids]
        items += [bond_items[i][0] for i in bond_ids]
        selection = [{"target": "atom", "id": i} for i in atom_ids]
        selection += [{"target": "bond", "id": i} for i in bond_ids]
    else:
        items = [
            next(
                item
                for item in desktop_canvas.scene().items()
                if item.data(0) == "mark" and (item.data(1) or {}).get("atom_id") == 4
            )
        ]
        selection = [{"target": "mark", "id": 0}]
    for item in items:
        item.setSelected(True)
    path = tmp_path / "native.mol"
    documents.export_mol(str(path), selected_only=True)
    native = path.read_text(encoding="utf-8")

    session = loaded_session(source)
    before = unchanged(session)
    assert export_mol(session, selection) == {
        "molfile": native,
        "revision": session.revision,
    }
    assert unchanged(session) == before
    if target == "bonds":
        # Selected bonds export only themselves, not the ring bond between their ends.
        assert native.splitlines()[3].startswith("  3  2")
    if target == "mark":
        assert native.splitlines()[3].startswith("  1  0") and "M  CHG" in native

    if target == "mixed":
        assert native.splitlines()[3].startswith("  6  1")
    if target == "atoms":
        assert native.splitlines()[3].startswith("  3  3")
    if target == "stored":
        assert "M  CHG" not in native
    if target == "summed":
        assert "M  CHG  1   5   2" in native
        assert "M  RAD  1   6   3" in native


def test_browser_mol_export_refuses_selections_without_structure():
    source = mol_document(mol_chain(), [(4, "plus")])
    source["state"]["arrows"] = [
        {"kind": min(VALID_ARROW_KINDS), "start": [0, 0], "end": [60, 30]}
    ]
    source["state"]["marks"].append(
        {
            "kind": "minus",
            "text": None,
            "atom_id": None,
            "dx": None,
            "dy": None,
            "x": 200.0,
            "y": 200.0,
        }
    )
    session = loaded_session(source)
    before = unchanged(session)
    for selection in (
        [],
        [{"target": "arrow", "id": 0}],
        [{"target": "mark", "id": 1}],
    ):
        with pytest.raises(
            ValueError, match="Select a molecular structure on the canvas first."
        ):
            export_mol(session, selection)
    with pytest.raises(ValueError, match="Expected the selection to export as MOL."):
        session.dispatch({"revision": session.revision, "action": "export_mol"})
    with pytest.raises(ValueError, match="Expected the selection to export as MOL."):
        session.dispatch(
            {
                "revision": session.revision,
                "action": "export_mol",
                "selection": [],
                "path": "/tmp/out.mol",
            }
        )
    with pytest.raises(ValueError, match="Expected a bounded list of selected items."):
        export_mol(session, "bond:0")
    with pytest.raises(ValueError, match="The atom no longer exists."):
        export_mol(session, [{"target": "atom", "id": 99}])
    with pytest.raises(StaleRevisionError):
        session.dispatch(
            {
                "revision": session.revision + 1,
                "action": "export_mol",
                "selection": [{"target": "bond", "id": 0}],
            }
        )
    assert unchanged(session) == before


def test_browser_mol_export_takes_a_selected_ring_fill_as_its_ring_atoms():
    ring = edit_document(
        {"document": new_document(), "edit": {"kind": "ring", "x": 100, "y": 100}}
    )["document"]
    session = loaded_session(ring)
    atoms = [{"target": "atom", "id": int(i)} for i in ring["state"]["model"]["atoms"]]
    molfile = export_mol(session, [{"target": "ring", "id": 0}])["molfile"]
    assert molfile == export_mol(session, atoms)["molfile"]
    assert molfile.splitlines()[3].startswith("  6  6")


def test_browser_mol_export_shares_the_desktop_rdkit_fallback_and_limits(monkeypatch):
    import chemvas.bootstrap.web_adapter as web_adapter

    calls = []

    class Backend:
        block = None
        last_error = "RDKit is not available in this environment."

        def model_to_mol_block(self, model, atom_annotations=None):
            calls.append((len(model.atoms), atom_annotations))
            return Backend.block

    monkeypatch.setattr(web_adapter, "RDKitAdapter", Backend)
    abbreviated = MoleculeModel()
    carbon = abbreviated.add_atom("C", 40.0, 60.0)
    abbreviated.add_bond(carbon, abbreviated.add_atom("Ph", 60.0, 60.0), 1)
    oversized = MoleculeModel()
    for index in range(1000):
        oversized.add_atom("N", 20.0 * (index % 40), 20.0 * (index // 40))

    def export(model):
        selection = [{"target": "atom", "id": atom_id} for atom_id in model.atoms]
        session = loaded_session(mol_document(model))
        before = unchanged(session)
        try:
            return export_mol(session, selection)["molfile"]
        finally:
            assert unchanged(session) == before

    with pytest.raises(
        ValueError, match="Install RDKit to expand these abbreviations automatically."
    ):
        export(abbreviated)
    Backend.block = "expanded\n\n\n  0  0  0  0  0  0  0  0999 V2000\nM  END\n"
    assert export(abbreviated) == Backend.block
    with pytest.raises(ValueError, match="999 atoms"):
        export(oversized)
    assert calls == [(2, {}), (2, {})]
    Backend.block = None
    Backend.last_error = "Dotted contacts cannot be represented as covalent bonds."
    with pytest.raises(ValueError) as error:
        export(abbreviated)
    assert str(error.value) == Backend.last_error
    assert calls == [(2, {}), (2, {}), (2, {})]


def test_browser_mol_export_runs_without_qt_or_site_packages():
    script = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from chemvas.bootstrap.web_adapter import BrowserSession, edit_document, new_document; "
        "drawn = edit_document({'document': new_document(), 'edit': {'kind': 'bond', 'start': [100, 100], 'end': [120, 100], 'style': 'single'}}); "
        "session = BrowserSession(); session.dispatch({'revision': 0, 'action': 'load', 'document': drawn['document']}); "
        "molfile = session.dispatch({'revision': session.revision, 'action': 'export_mol', 'selection': [{'target': 'bond', 'id': 0}]})['molfile']; "
        "assert molfile.splitlines()[3].startswith('  2  1') and 'M  END' in molfile; "
        "assert not any(name.startswith('PyQt6') for name in sys.modules)"
    )
    subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", script, str(ROOT / "app")], check=True
    )


def test_browser_mol_export_preserves_readonly_notes_and_live_redo():
    source = mol_document(mol_chain())
    source["state"]["notes"] = [
        {"text": "item", "html": "<ul><li>item</li></ul>", "x": 10, "y": 20}
    ]
    session = loaded_session(source)
    assert session.info["unsupported"] == [
        "note lists or formatting without a browser renderer"
    ]
    before = unchanged(session)
    assert (
        export_mol(session, [{"target": "bond", "id": 0}])["molfile"]
        .splitlines()[3]
        .startswith("  2  1")
    )
    assert unchanged(session) == before

    session = loaded_session(mol_document(mol_chain()))
    session.dispatch(
        {
            "revision": session.revision,
            "action": "edit",
            "edit": {
                "kind": "move",
                "selection": [{"target": "atom", "id": 0}],
                "dx": 5,
                "dy": 0,
            },
        }
    )
    session.dispatch({"revision": session.revision, "action": "undo"})
    assert session.history.can_redo()
    before = unchanged(session)
    export_mol(session, [{"target": "bond", "id": 0}])
    assert unchanged(session) == before
    session.dispatch({"revision": session.revision, "action": "redo"})
    assert session.history.can_undo()
