"""Browser Cut/Copy/Paste through the desktop's selection payload and paste plan."""

from __future__ import annotations

import http.client
import json
import threading
from copy import deepcopy

import pytest

from chemvas.bootstrap import web_adapter
from chemvas.bootstrap.web_adapter import (
    BrowserServer,
    BrowserSession,
    StaleRevisionError,
    edit_document,
    new_document,
)
from chemvas.domain.document import (
    CLIPBOARD_SELECTION_VERSION,
    build_document_payload,
    extract_document_state,
)
from chemvas.ui.scene.scene_clipboard_logic import decode_clipboard_selection_payload
from chemvas.ui.scene.scene_clipboard_transaction_logic import (
    clipboard_paste_offset,
    selection_payload_json,
)

COLLECTION_TARGETS = (
    ("arrows", "arrow"),
    ("shapes", "shape"),
    ("ring_fills", "ring"),
    ("marks", "mark"),
    ("orbitals", "orbital"),
    ("ts_brackets", "ts_bracket"),
    ("notes", "note"),
    ("images", "image"),
)


def rich_document() -> dict:
    """A filled ring, a coloured double bond to a charged oxygen with its mark,
    a free mark, an arrow, a shape and an orbital."""
    payload = json.loads(json.dumps(new_document()))
    state = payload["state"]

    def atom(element, x, y, color="#000000", explicit=False):
        return {
            "element": element,
            "x": x,
            "y": y,
            "color": color,
            "explicit_label": explicit,
        }

    def bond(a, b, order=1, style="single", color="#000000"):
        return {"a": a, "b": b, "order": order, "style": style, "color": color}

    state["model"] = {
        "atoms": {
            "0": atom("C", 0.0, 0.0),
            "1": atom("C", 20.0, 0.0),
            "2": atom("N", 10.0, 17.0, "#0000ff", True),
            # Both adapters save a shown heteroatom label as explicit.
            "3": atom("O", 40.0, 0.0, explicit=True),
        },
        "bonds": [
            bond(0, 1),
            bond(1, 2),
            bond(2, 0),
            bond(1, 3, 2, "double", "#123456"),
        ],
        "next_atom_id": 4,
        "atom_annotations": {"3": {"formal_charge": -1}},
    }
    state["ring_fills"] = [
        {
            "points": [[0.0, 0.0], [20.0, 0.0], [10.0, 17.0]],
            "atom_ids": [0, 1, 2],
            "color": "#ffcc00",
            "alpha": 0.3,
        }
    ]
    state["marks"] = [
        {
            "kind": "minus",
            "text": "-",
            "atom_id": 3,
            "dx": 6.0,
            "dy": -6.0,
            "x": 46.0,
            "y": -6.0,
        },
        {
            "kind": "plus",
            "text": "+",
            "atom_id": None,
            "dx": None,
            "dy": None,
            "x": 100.0,
            "y": 100.0,
        },
    ]
    state["arrows"] = [{"kind": "arrow", "start": [0.0, 50.0], "end": [60.0, 50.0]}]
    state["shapes"] = [
        {
            "kind": "shape",
            "left": 100.0,
            "top": 0.0,
            "right": 140.0,
            "bottom": 30.0,
            "shape_kind": "rect",
            "stroke_style": "solid",
        }
    ]
    state["orbitals"] = [
        {"kind": "p", "center": [150.0, 50.0], "scale": 1.0, "rotation": 0.0}
    ]
    return payload


def rich_session() -> BrowserSession:
    """The rich document with a Greek/Korean note and an arrow+shape group."""
    session = BrowserSession()
    session.dispatch(
        {
            "revision": 0,
            "action": "load",
            "document": rich_document(),
            "name": "Rich.chemvas",
        }
    )
    session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {
                "kind": "note_text",
                "id": None,
                "x": 0,
                "y": 80,
                "html": "<p>Ηλ 한글</p>",
            },
        }
    )
    session.dispatch(
        {
            "revision": 2,
            "action": "edit",
            "edit": {
                "kind": "group",
                "selection": [
                    {"target": "arrow", "id": 0},
                    {"target": "shape", "id": 0},
                ],
            },
        }
    )
    return session


def plain(document: dict) -> dict:
    """The document state as JSON, with string atom keys."""
    return json.loads(json.dumps(document["state"]))


def everything(document: dict) -> list[dict]:
    """Select All, as the browser builds it."""
    state = plain(document)
    items = [
        {"target": "atom", "id": int(atom_id)} for atom_id in state["model"]["atoms"]
    ]
    items += [
        {"target": "bond", "id": index}
        for index, bond in enumerate(state["model"]["bonds"])
        if bond is not None
    ]
    for key, target in COLLECTION_TARGETS:
        count = len(state.get(key, []))
        items += [{"target": target, "id": index} for index in range(count)]
    return items


def copy(session: BrowserSession, selection: list[dict] | None = None) -> str:
    if selection is None:
        selection = everything(session.info["document"])
    reply = session.dispatch(
        {"revision": session.revision, "action": "copy", "selection": selection}
    )
    return reply["payload"]


def paste(session: BrowserSession, text: str) -> dict:
    return session.dispatch(
        {
            "revision": session.revision,
            "action": "edit",
            "edit": {"kind": "paste", "payload": text},
        }
    )


def moved(point, dx, dy):
    return [point[0] + dx, point[1] + dy]


def test_copy_and_paste_keep_every_selected_object_with_new_ids():
    session = rich_session()
    source = plain(session.info["document"])
    history_before = len(session.state.history)
    text = copy(session)
    # Copy reads only: no document, revision or history change.
    assert plain(session.info["document"]) == source
    assert len(session.state.history) == history_before
    payload = json.loads(text)
    assert payload["format"] == "chemvas-selection"
    assert payload["version"] == CLIPBOARD_SELECTION_VERSION
    # The same text the desktop puts on its clipboard for this payload.
    assert text == selection_payload_json(payload)

    revision = session.revision
    result = paste(session, text)
    assert session.revision == revision + 1
    pasted = plain(result["document"])
    dx, dy = clipboard_paste_offset(1, source["settings"]["bond_length_px"])
    atoms, new_atoms = source["model"]["atoms"], pasted["model"]["atoms"]
    # The originals stay; the copies take fresh ids after next_atom_id.
    assert {key: new_atoms[key] for key in atoms} == atoms
    remap = {old: old + 4 for old in range(4)}
    assert sorted(map(int, new_atoms)) == list(range(8))
    for old, new in remap.items():
        original, copied = atoms[str(old)], new_atoms[str(new)]
        assert copied == {
            **original,
            "x": original["x"] + dx,
            "y": original["y"] + dy,
        }
    assert pasted["model"]["next_atom_id"] == 8
    assert pasted["model"]["bonds"][:4] == source["model"]["bonds"]
    assert pasted["model"]["bonds"][4:] == [
        {**old, "a": remap[old["a"]], "b": remap[old["b"]]}
        for old in source["model"]["bonds"]
    ]
    assert pasted["model"]["atom_annotations"] == {
        "3": {"formal_charge": -1},
        "7": {"formal_charge": -1},
    }
    ring = pasted["ring_fills"][1]
    assert ring["atom_ids"] == [4, 5, 6]
    old_points = source["ring_fills"][0]["points"]
    assert [list(point) for point in ring["points"]] == [
        moved(point, dx, dy) for point in old_points
    ]
    bound, free = pasted["marks"][2:]
    assert (bound["atom_id"], bound["dx"], bound["dy"]) == (7, 6.0, -6.0)
    assert (free["atom_id"], free["x"], free["y"]) == (None, 100.0 + dx, 100.0 + dy)
    arrow, old_arrow = pasted["arrows"][1], source["arrows"][0]
    assert list(arrow["start"]) == moved(old_arrow["start"], dx, dy)
    assert list(arrow["end"]) == moved(old_arrow["end"], dx, dy)
    shape = pasted["shapes"][1]
    assert (shape["left"], shape["top"]) == (100.0 + dx, 0.0 + dy)
    assert list(pasted["orbitals"][1]["center"]) == moved([150.0, 50.0], dx, dy)
    note = pasted["notes"][1]
    assert note["text"] == source["notes"][0]["text"] == "Ηλ 한글"
    assert (note["x"], note["y"]) == (0.0 + dx, 80.0 + dy)
    # The copied group is a new group over the copied members.
    groups = sorted(sorted(map(tuple, group["items"])) for group in pasted["groups"])
    assert groups == [[("arrows", 0), ("shapes", 0)], [("arrows", 1), ("shapes", 1)]]
    # Exactly the pasted items become the selection.
    selected = sorted((item["target"], item["id"]) for item in result["pasted"])
    objects = [("arrow", 1), ("shape", 1), ("ring", 1), ("mark", 2), ("mark", 3)]
    objects += [("orbital", 1), ("note", 1)]
    structure = [(kind, index) for kind in ("atom", "bond") for index in range(4, 8)]
    assert selected == sorted(structure + objects)
    # One Undo/Redo step restores and repeats the whole paste exactly.
    assert len(session.state.history) == history_before + 1
    undone = session.dispatch({"revision": session.revision, "action": "undo"})
    assert plain(undone["document"]) == source
    redone = session.dispatch({"revision": session.revision, "action": "redo"})
    assert plain(redone["document"]) == pasted


def turned_ring_session() -> BrowserSession:
    """A ring turned in 3D with its depth points, an embedded PNG and a shape
    stacked by depth, a rotated note and a transition-state bracket."""
    from io import BytesIO

    from PIL import Image

    from chemvas.domain.document.images import image_state_from_bytes
    from chemvas.domain.document.perspective import project_point_3d
    from chemvas.features.selection import rigid_rotated_coords

    payload = edit_document(
        {"document": new_document(), "edit": {"kind": "ring", "x": 100, "y": 100}}
    )["document"]
    state = extract_document_state(payload)
    atoms = state["model"]["atoms"]
    length = state["settings"]["bond_length_px"]
    center = (100.0, 100.0, 0.0)
    rotated = rigid_rotated_coords(
        set(atoms),
        {atom_id: (atom["x"], atom["y"], 0.0) for atom_id, atom in atoms.items()},
        center,
        angle_x=1.0,
        angle_y=0.5,
    )
    for atom_id, atom in atoms.items():
        atom["x"], atom["y"] = project_point_3d(
            rotated[atom_id],
            bond_length_px=length,
            center_3d=center,
            anchor_2d=center[:2],
        )
    state["perspective"] = {
        "atom_coords_3d": rotated,
        "projection_center_3d": center,
        "projection_anchor_2d": center[:2],
    }
    state["ring_fills"] = [
        {**ring, "points": [(atoms[i]["x"], atoms[i]["y"]) for i in ring["atom_ids"]]}
        for ring in state["ring_fills"]
    ]
    buffer = BytesIO()
    Image.new("RGB", (5, 3), (10, 200, 30)).save(buffer, "PNG")
    state["images"] = [
        image_state_from_bytes(
            buffer.getvalue(), x=300, y=40, width=50, height=30, z=4.5
        )
    ]
    state["shapes"] = [
        {
            "kind": "shape",
            "left": 300.0,
            "top": 100.0,
            "right": 340.0,
            "bottom": 130.0,
            "shape_kind": "rect",
            "stroke_style": "solid",
            "z": 2.5,
        }
    ]
    state["notes"] = [
        {"text": "Turned", "html": "", "x": 20.0, "y": -30.0, "rotation": 30.0}
    ]
    state["ts_brackets"] = [
        {
            "kind": "ts_bracket",
            "bracket_kind": "dagger",
            "left": 400.0,
            "top": 0.0,
            "right": 436.0,
            "bottom": 48.0,
        }
    ]
    session = BrowserSession()
    session.dispatch(
        {
            "revision": 0,
            "action": "load",
            "document": build_document_payload(state, payload["version"]),
        }
    )
    return session


def test_paste_keeps_image_bytes_rotation_depth_brackets_and_depth_points():
    session = turned_ring_session()
    source = plain(session.info["document"])
    assert not session.info["unsupported"]
    text = copy(session)
    copied = json.loads(text)
    [image] = [item for item in copied["scene_items"] if item["kind"] == "image"]
    # The copy carries the embedded file itself, byte for byte.
    assert image["data_base64"] == source["images"][0]["data_base64"]
    depth_points = copied["perspective"]["atom_coords_3d"]
    assert {entry["atom_id"] for entry in depth_points} == {
        int(atom_id) for atom_id in source["model"]["atoms"]
    }
    result = paste(session, text)
    pasted = plain(result["document"])
    dx, dy = clipboard_paste_offset(1, source["settings"]["bond_length_px"])
    old_image, new_image = pasted["images"]
    assert old_image == source["images"][0]
    assert new_image == {
        **old_image,
        "x": pytest.approx(old_image["x"] + dx),
        "y": pytest.approx(old_image["y"] + dy),
    }
    assert new_image["z"] == 4.5
    shape = pasted["shapes"][1]
    assert shape == {
        **source["shapes"][0],
        "left": pytest.approx(300.0 + dx),
        "right": pytest.approx(340.0 + dx),
        "top": pytest.approx(100.0 + dy),
        "bottom": pytest.approx(130.0 + dy),
    }
    note = pasted["notes"][1]
    assert (note["text"], note["rotation"]) == ("Turned", 30.0)
    assert (note["x"], note["y"]) == pytest.approx((20.0 + dx, -30.0 + dy))
    assert pasted["ts_brackets"][1] == {
        **source["ts_brackets"][0],
        "left": pytest.approx(400.0 + dx),
        "right": pytest.approx(436.0 + dx),
        "top": pytest.approx(0.0 + dy),
        "bottom": pytest.approx(48.0 + dy),
    }
    # The copied atoms keep depth points of their own beside the originals.
    old_ids = set(source["model"]["atoms"])
    new_ids = set(pasted["model"]["atoms"]) - old_ids
    assert len(new_ids) == len(old_ids)
    assert set(pasted["perspective"]["atom_coords_3d"]) == old_ids | new_ids
    selected = {(item["target"], item["id"]) for item in result["pasted"]}
    assert {("image", 1), ("shape", 1), ("note", 1), ("ts_bracket", 1)} <= selected
    undone = session.dispatch({"revision": session.revision, "action": "undo"})
    assert plain(undone["document"]) == source


def test_repeated_paste_cascades_and_another_window_starts_its_own():
    session = rich_session()
    text = copy(session)
    bond_length = plain(session.info["document"])["settings"]["bond_length_px"]
    step1 = clipboard_paste_offset(1, bond_length)
    step2 = clipboard_paste_offset(2, bond_length)
    first = plain(paste(session, text)["document"])
    second = plain(paste(session, text)["document"])
    assert first["model"]["atoms"]["4"]["x"] == 0.0 + step1[0]
    assert second["model"]["atoms"]["8"]["x"] == 0.0 + step2[0]
    # A copy in this window restarts the cascade, as a desktop copy does.
    copy(session, [{"target": "atom", "id": 3}])
    third = plain(paste(session, text)["document"])
    assert third["model"]["atoms"]["12"]["x"] == 0.0 + step1[0]
    # Another window pastes the same text at the first step: no shared state.
    other = BrowserSession()
    other.dispatch({"revision": 0, "action": "load", "document": new_document()})
    pasted = plain(paste(other, text)["document"])
    assert pasted["model"]["atoms"]["0"]["x"] == 0.0 + step1[0]


def test_copy_of_a_bond_or_ring_takes_its_atoms_and_detaches_unselected_owners():
    session = rich_session()
    # A selected bound mark whose atom is not copied becomes a free mark.
    text = copy(session, [{"target": "bond", "id": 0}, {"target": "mark", "id": 0}])
    payload = json.loads(text)
    assert sorted(atom["id"] for atom in payload["atoms"]) == [0, 1]
    marks = [(m["atom_id"], m["dx"], m["dy"]) for m in payload["marks"]]
    assert marks == [(None, None, None)]
    # A selected ring takes its atoms, bonds and fill.
    ring = json.loads(copy(session, [{"target": "ring", "id": 0}]))
    assert sorted(atom["id"] for atom in ring["atoms"]) == [0, 1, 2]
    assert [r["atom_ids"] for r in ring["rings"]] == [[0, 1, 2]]
    assert len(ring["bonds"]) == 3


def selection_text(**changes) -> str:
    return json.dumps(
        {
            "format": "chemvas-selection",
            "version": 3,
            "atoms": [],
            "bonds": [],
            "rings": [],
            "marks": [],
            "scene_items": [],
            **changes,
        }
    )


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("{", "damaged or invalid"),
        ("not a selection", "damaged or invalid"),
        ('{"format": "other", "version": 3}', "not a supported Chemvas selection"),
        (selection_text(version=99), "unsupported version"),
        (selection_text(bonds=[{"a": 0, "b": 1, "order": 1}]), "damaged or invalid"),
        (selection_text(), "empty"),
    ],
)
def test_invalid_clipboard_text_is_refused_without_any_change(text, message):
    session = rich_session()
    before = deepcopy(session.info)
    revision, history = session.revision, list(session.state.history)
    paste_state = (session.paste_source, session.paste_count)
    with pytest.raises(ValueError, match=message):
        paste(session, text)
    assert session.info == before
    assert session.revision == revision
    assert list(session.state.history) == history
    assert (session.paste_source, session.paste_count) == paste_state


def test_oversized_and_unrenderable_selections_are_refused(monkeypatch):
    session = rich_session()
    text = copy(session)
    before, revision = deepcopy(session.info), session.revision
    limit = len(text.encode()) - 1
    monkeypatch.setattr(web_adapter, "MAX_CLIPBOARD_SELECTION_PAYLOAD_BYTES", limit)
    with pytest.raises(ValueError, match="too large to paste"):
        paste(session, text)
    monkeypatch.undo()
    # A desktop note the browser cannot render would leave the drawing read-only.
    payload = json.loads(text)
    note = next(item for item in payload["scene_items"] if item["kind"] == "note")
    note["html"] = "<ul><li>Item</li></ul>"
    with pytest.raises(ValueError, match="note lists"):
        paste(session, selection_payload_json(payload))
    assert session.info == before
    assert session.revision == revision


def test_read_only_drawings_refuse_paste_but_still_copy():
    payload = new_document()
    payload["state"]["notes"] = [
        {"text": "Item", "html": "<ul><li>Item</li></ul>", "x": 10, "y": 20}
    ]
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": payload})
    text = copy(session, [{"target": "note", "id": 0}])
    assert json.loads(text)["scene_items"][0]["html"] == "<ul><li>Item</li></ul>"
    before = deepcopy(session.info)
    with pytest.raises(ValueError, match="read-only"):
        paste(session, text)
    assert session.info == before


def test_copy_refuses_empty_and_stale_selections():
    session = rich_session()
    with pytest.raises(ValueError, match="Select a structure or object"):
        copy(session, [])
    with pytest.raises(ValueError, match="no longer exists"):
        copy(session, [{"target": "atom", "id": 99}])
    with pytest.raises(StaleRevisionError):
        session.dispatch(
            {
                "revision": session.revision - 1,
                "action": "copy",
                "selection": [{"target": "atom", "id": 0}],
            }
        )
    # A paste based on an older revision cannot edit the newer drawing.
    text = copy(session)
    before = deepcopy(session.info)
    with pytest.raises(StaleRevisionError):
        session.dispatch(
            {
                "revision": session.revision - 1,
                "action": "edit",
                "edit": {"kind": "paste", "payload": text},
            }
        )
    assert session.info == before


def test_paste_has_no_preview():
    session = rich_session()
    text = copy(session)
    with pytest.raises(ValueError, match="no preview"):
        session.dispatch(
            {
                "revision": session.revision,
                "action": "preview",
                "edit": {"kind": "paste", "payload": text},
            }
        )


@pytest.fixture
def server():
    with BrowserServer() as running:
        thread = threading.Thread(target=running.serve_forever, daemon=True)
        thread.start()
        try:
            yield running
        finally:
            running.shutdown()
            thread.join(timeout=5)


def post(server, body):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request(
            "POST",
            "/api/session",
            body=json.dumps(body),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + server.token,
            },
        )
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def test_http_copy_and_paste_round_trip_and_stale_copy(server):
    status, opened = post(
        server,
        {"revision": 0, "action": "load", "document": rich_document()},
    )
    assert status == 200
    session, revision = opened["session"], opened["revision"]
    selection = everything(opened["document"])
    status, copied = post(
        server,
        {
            "session": session,
            "revision": revision,
            "action": "copy",
            "selection": selection,
        },
    )
    assert status == 200
    assert copied["revision"] == revision
    status, pasted = post(
        server,
        {
            "session": session,
            "revision": revision,
            "action": "edit",
            "edit": {"kind": "paste", "payload": copied["payload"]},
        },
    )
    assert status == 200
    assert len(pasted["document"]["state"]["model"]["atoms"]) == 8
    # The cascade source stays on the server; the reply names the selection.
    assert "paste" not in pasted
    assert pasted["pasted"]
    # The old revision's copy request is stale against the pasted drawing.
    status, stale = post(
        server,
        {
            "session": session,
            "revision": revision,
            "action": "copy",
            "selection": selection,
        },
    )
    assert status == 409
    assert "stale" in stale["error"]


@pytest.fixture
def desktop_canvas(qt_application):
    from tests.canvas_factory import build_canvas_view

    canvas = build_canvas_view()
    yield canvas
    canvas.services.canvas_scene_reset_service.clear_scene()
    canvas.close()


def _rounded(value):
    return None if value is None else round(float(value), 6)


def comparable_payload(payload: dict) -> dict:
    return {
        "atoms": {
            atom["id"]: (
                atom["element"],
                atom["color"],
                atom["explicit_label"],
                _rounded(atom["x"]),
                _rounded(atom["y"]),
                atom.get("annotation"),
            )
            for atom in payload["atoms"]
        },
        "bonds": [
            (bond["a"], bond["b"], bond["order"], bond["style"], bond["color"])
            for bond in payload["bonds"]
        ],
        "rings": sorted(ring["atom_ids"] for ring in payload["rings"]),
        "marks": sorted(
            repr((m["mark_kind"], m["atom_id"], _rounded(m["dx"]), _rounded(m["dy"])))
            for m in payload["marks"]
        ),
        "scene_items": sorted(item["kind"] for item in payload["scene_items"]),
        "notes": sorted(
            item["text"] for item in payload["scene_items"] if item["kind"] == "note"
        ),
        "groups": len(payload.get("groups", [])),
    }


def comparable_state(state: dict) -> dict:
    model = state["model"]
    return {
        "atoms": {
            key: (
                atom["element"],
                atom["color"],
                atom["explicit_label"],
                _rounded(atom["x"]),
                _rounded(atom["y"]),
            )
            for key, atom in model["atoms"].items()
        },
        "bonds": model["bonds"],
        "annotations": model.get("atom_annotations", {}),
        "rings": sorted(ring["atom_ids"] for ring in state["ring_fills"]),
        "marks": sorted(repr((m["kind"], m["atom_id"])) for m in state["marks"]),
        "arrows": sorted(
            repr([_rounded(v) for v in [*arrow["start"], *arrow["end"]]])
            for arrow in state["arrows"]
        ),
        "shapes": sorted(
            repr([_rounded(s[k]) for k in ("left", "top", "right", "bottom")])
            for s in state["shapes"]
        ),
        "notes": sorted(note["text"] for note in state["notes"]),
        "groups": len(state.get("groups", [])),
    }


def test_browser_and_desktop_exchange_the_same_selection_payload(desktop_canvas):
    """Differential: each adapter pastes the other's copy as it pastes its own."""
    session = rich_session()
    document = session.info["document"]
    documents = desktop_canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(document))
    desktop_canvas.services.selection.select_all()
    controller = desktop_canvas.services.scene_clipboard_controller
    desktop_text = selection_payload_json(controller.selection_payload_for_clipboard())
    browser_text = copy(session)
    browser_copy = comparable_payload(json.loads(browser_text))
    assert browser_copy == comparable_payload(json.loads(desktop_text))

    def browser_payload():
        return decode_clipboard_selection_payload(
            [browser_text], version=CLIPBOARD_SELECTION_VERSION
        )

    # The desktop pastes the browser's text through its own validation...
    assert controller.paste_selection_from_clipboard(payload_provider=browser_payload)
    desktop_after = json.loads(json.dumps(documents.snapshot_state()))
    # ...and the browser pastes the desktop's text into the same starting drawing.
    browser = BrowserSession()
    browser.dispatch({"revision": 0, "action": "load", "document": document})
    browser_after = plain(paste(browser, desktop_text)["document"])
    assert comparable_state(browser_after) == comparable_state(desktop_after)
