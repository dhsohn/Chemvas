from __future__ import annotations

import http.client
import json
import shutil
import subprocess
import sys
import threading
from copy import deepcopy
from pathlib import Path

import pytest

from chemvas.bootstrap.web_adapter import (
    MAX_REQUEST_BYTES,
    BrowserServer,
    BrowserSession,
    atom_input_plan,
    document_info,
    edit_document,
    new_document,
    ui_css,
    ui_spec,
)
from chemvas.domain.document import build_document_payload, extract_document_state

ROOT = Path(__file__).resolve().parents[1]


def draw_bond(payload, start=(30, 40), end=(50, 40), style="single"):
    return edit_document(
        {
            "document": payload,
            "edit": {
                "kind": "bond",
                "start": list(start),
                "end": list(end),
                "style": style,
            },
        }
    )


def test_adapter_imports_without_qt_or_site_packages():
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            (
                "import sys; sys.path.insert(0, sys.argv[1]); "
                "from chemvas.bootstrap.web_adapter import new_document, document_info, ui_spec, BrowserSession, edit_document; "
                "assert not document_info(new_document())['unsupported']; ui_spec(); BrowserSession(); edit_document({'document': new_document(), 'edit': {'kind': 'bond', 'start': [100, 100], 'end': [100, 100], 'style': 'single'}}); "
                "ring = edit_document({'document': new_document(), 'edit': {'kind': 'ring', 'x': 100, 'y': 100}}); "
                "edit_document({'document': ring['document'], 'edit': {'kind': 'delete_selection', 'selection': [{'target': 'bond', 'id': 0}]}}); "
                "edit_document({'document': ring['document'], 'edit': {'kind': 'atom', 'x': 100, 'y': 100, 'text': 'N'}}); "
                "atoms = ring['document']['state']['model']['atoms']; atoms[77] = dict(atoms[0]); ring['document']['state']['model']['next_atom_id'] = 78; "
                "merged = edit_document({'document': ring['document'], 'edit': {'kind': 'atom', 'atom_id': 0, 'x': atoms[0]['x'], 'y': atoms[0]['y'], 'text': 'O'}}); assert 77 not in merged['document']['state']['model']['atoms']; "
                "edit_document({'document': merged['document'], 'edit': {'kind': 'move', 'selection': [{'target': 'bond', 'id': 0}], 'dx': 5, 'dy': 10}}); "
                "edit_document({'document': merged['document'], 'edit': {'kind': 'bond_style', 'id': 0, 'style': 'bold_in'}}); "
                "assert not any(n.split('.')[0] in {'PyQt6', 'PIL', 'rdkit'} for n in sys.modules)"
            ),
            str(ROOT / "app"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_atomic_shared_edit_and_rejection_leave_input_untouched():
    source = new_document()
    before = deepcopy(source)
    changed = draw_bond(source)
    assert source == before
    assert len(changed["document"]["state"]["model"]["atoms"]) == 2
    with pytest.raises(ValueError):
        draw_bond(source, end=(float("nan"), 40))
    assert source == before
    # A rejected transaction consumed neither an ID nor a history state.
    assert draw_bond(source) == changed


@pytest.mark.parametrize("version", [7, 8, 9])
def test_supported_document_versions_roundtrip_without_changing_source(version):
    payload = build_document_payload(new_document()["state"], version)
    encoded = json.dumps(payload)
    info = document_info(json.loads(encoded))
    assert info["document"] == json.loads(encoded)
    assert info["document"]["version"] == version
    updated = draw_bond(info["document"])["document"]
    assert updated["version"] == version
    extract_document_state(updated)
    assert json.dumps(payload) == encoded


def test_unsupported_content_is_preserved_and_server_rejects_edits():
    payload = new_document()
    payload["state"]["notes"] = [
        {"text": "Important", "html": "<p><b>Important</b></p>", "x": 10, "y": 20}
    ]
    original = deepcopy(payload)
    info = document_info(payload)
    assert "text annotations" in info["unsupported"]
    assert info["document"] == original
    with pytest.raises(ValueError, match="read-only"):
        draw_bond(payload)
    assert payload == original


@pytest.mark.parametrize(
    "edit",
    [
        {"kind": "graph", "operations": []},
        {"kind": "note", "text": "Text", "x": 10, "y": 20},
        {"kind": "arrow", "start": [20, 30], "end": [80, 30]},
        {"kind": "delete", "target": "note", "id": 0},
        {"kind": "delete", "target": "atom", "id": 0},
    ],
)
def test_removed_demo_actions_cannot_publish_or_consume_history(edit):
    session = BrowserSession()
    before = deepcopy(session.info)
    with pytest.raises(ValueError):
        session.dispatch({"revision": 0, "action": "edit", "edit": edit})
    assert session.info == before
    assert session.revision == 0
    assert not session.history.can_undo()


def test_delete_atom_removes_its_bonds_without_reusing_ids():
    payload = draw_bond(new_document())["document"]
    result = edit_document(
        {
            "document": payload,
            "edit": {
                "kind": "delete_selection",
                "selection": [{"target": "atom", "id": 0}],
            },
        }
    )
    model = result["document"]["state"]["model"]
    assert len(model["atoms"]) == 0
    assert model["bonds"] == []
    assert model["next_atom_id"] == 2
    extract_document_state(result["document"])


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


def request(server, path, *, method="GET", body=None, authorized=True, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    values = {"Content-Type": "application/json"}
    if authorized:
        values["Authorization"] = "Bearer " + server.token
    values.update(headers or {})
    try:
        connection.request(method, path, body=body, headers=values)
        response = connection.getresponse()
        return response.status, response.read(), dict(response.getheaders())
    finally:
        connection.close()


def test_http_auth_host_origin_and_static_allowlist(server):
    assert request(server, "/api/new", authorized=False)[0] == 401
    assert (
        request(server, "/api/new", headers={"Origin": "https://example.org"})[0] == 403
    )
    assert request(server, "/api/new", headers={"Host": "example.org"})[0] == 403
    assert request(server, "/../pyproject.toml")[0] == 404
    status, body, headers = request(server, "/")
    assert status == 200 and b"Chemical drawing canvas" in body
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "Access-Control-Allow-Origin" not in headers
    for path in ("/app.mjs", "/transport.mjs", "/scene.mjs", "/style.css"):
        assert request(server, path)[0] == 200


def test_http_open_edit_rejects_malformed_and_oversized_documents(server):
    status, body, _ = request(server, "/api/new")
    assert status == 200
    extract_document_state(json.loads(body)["document"])
    status, body, _ = request(
        server,
        "/api/session",
        method="POST",
        body=json.dumps(
            {
                "revision": 0,
                "action": "edit",
                "edit": {"kind": "ring", "x": 100, "y": 100},
            }
        ),
    )
    assert status == 200
    assert len(json.loads(body)["document"]["state"]["model"]["atoms"]) == 6
    assert (
        request(
            server, "/api/open", method="POST", body='{"version": 7, "version": 9}'
        )[0]
        == 400
    )
    assert request(server, "/api/open", method="POST", body='{"x": NaN}')[0] == 400
    assert (
        request(
            server,
            "/api/open",
            method="POST",
            body="{}",
            headers={"Content-Length": str(MAX_REQUEST_BYTES + 1)},
        )[0]
        == 413
    )
    assert (
        request(
            server,
            "/api/open",
            method="POST",
            body="{}",
            headers={"Content-Type": "text/plain"},
        )[0]
        == 415
    )
    assert request(server, "/api/edit", method="POST", body="{}")[0] == 404
    # Serving another request proves a failed edit did not poison a session.
    assert request(server, "/api/new")[0] == 200


def test_browser_state_and_svg_contracts():
    node = shutil.which("node")
    assert node is not None, (
        "The browser adapter checks require Node.js 20+ (runtime has no Node dependency)."
    )
    for source in (ROOT / "app/chemvas/web").glob("*.mjs"):
        result = subprocess.run(
            [node, "--check", str(source)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr
    result = subprocess.run(
        [node, "--test", str(ROOT / "tests/web_adapter.test.mjs")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_existing_desktop_history_owns_browser_undo_and_rejected_edits():
    from chemvas.ui.canvas.canvas_history_service import CanvasHistoryService
    from chemvas.ui.molecule.structure_geometry_logic import (
        compute_free_benzene_ring_points,
    )

    session = BrowserSession()
    assert isinstance(session.history, CanvasHistoryService)
    before = deepcopy(session.info)
    ring = session.dispatch(
        {"revision": 0, "action": "edit", "edit": {"kind": "ring", "x": 100, "y": 100}}
    )
    points = compute_free_benzene_ring_points((100, 100), bond_length=20)
    atoms = list(ring["document"]["state"]["model"]["atoms"].values())
    assert [(atom["x"], atom["y"]) for atom in atoms] == points
    restored = session.dispatch({"revision": 1, "action": "undo"})
    assert restored["document"] == before["document"]
    assert restored["can_redo"]
    with pytest.raises(ValueError):
        session.dispatch(
            {
                "revision": 2,
                "action": "edit",
                "edit": {
                    "kind": "delete_selection",
                    "selection": [{"target": "atom", "id": 99}],
                },
            }
        )
    assert session.revision == 2
    assert session.state.redo_stack
    redo = session.dispatch({"revision": 2, "action": "redo"})
    assert redo["document"] == ring["document"]
    with pytest.raises(ValueError, match="stale"):
        session.dispatch({"revision": 2, "action": "undo"})
    assert session.info["document"] == ring["document"]


def test_browser_ui_uses_the_desktop_definitions():
    from chemvas.shell.icon_design import design_icon_svg
    from chemvas.shell.palette import PALETTE
    from chemvas.ui.window.main_window_config import TOOLBAR_TOOL_ACTION_ORDER

    spec = ui_spec()
    assert [
        item["key"] for group in spec["groups"] for item in group
    ] == TOOLBAR_TOOL_ACTION_ORDER
    assert spec["groups"][1][0]["icon"] == design_icon_svg("bond")
    assert spec["groups"][1][0]["tip"] == "Bond (Shortcut: X)"
    assert PALETTE["accent"] in ui_css()
    assert "--toolbar-thickness: 38px" in ui_css()


@pytest.mark.parametrize("length", [20, 40])
@pytest.mark.parametrize("fused", [False, True])
@pytest.mark.parametrize("records", [False, True])
def test_benzene_visible_lines_match_the_actual_qt_scene(
    desktop_canvas, length, fused, records
):
    from PyQt6.QtWidgets import QGraphicsLineItem

    payload = new_document()
    payload["state"]["settings"]["bond_length_px"] = length
    browser = edit_document(
        {"document": payload, "edit": {"kind": "ring", "x": 100, "y": 100}}
    )
    if fused:
        browser = edit_document(
            {
                "document": browser["document"],
                "edit": {"kind": "ring", "x": 100, "y": 100, "bond_id": 0},
            }
        )
    if not records:
        browser["document"]["state"]["ring_fills"] = []
        browser = document_info(browser["document"])
    canvas = desktop_canvas
    canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(browser["document"])
    )
    count = 0
    for bond_id, items in canvas.runtime_state.bond_graphics_state.bond_items.items():
        actual = [item.line() for item in items if isinstance(item, QGraphicsLineItem)]
        expected = browser["drawing"]["bonds"][str(bond_id)]
        assert len(actual) == len(expected)
        for line, primitive in zip(actual, expected, strict=True):
            assert primitive["line"] == pytest.approx(
                (line.x1(), line.y1(), line.x2(), line.y2()), abs=1e-9
            )
            count += 1
    assert count == (16 if fused else 9)


def test_main_entry_selects_browser_before_qt(monkeypatch):
    from chemvas.bootstrap import application, web_adapter

    seen = []
    monkeypatch.setattr(sys, "argv", ["chemvas", "--ui", "web", "--no-browser"])
    monkeypatch.setattr(web_adapter, "main", lambda argv: seen.append(argv))
    application.main()
    assert seen == [["--no-browser"]]


def test_bond_input_uses_existing_endpoint_policy():
    payload = new_document()
    edit = {
        "kind": "bond",
        "start": [100, 100],
        "end": [153, 107],
        "style": "single",
    }
    info = edit_document({"document": payload, "edit": edit})
    atoms = list(info["document"]["state"]["model"]["atoms"].values())
    assert [(atom["x"], atom["y"]) for atom in atoms] == [(100, 100), (120, 100)]
    assert info["drawing"]["bonds"]["0"][0]["line"] == pytest.approx(
        (100, 100, 120, 100)
    )


@pytest.fixture
def desktop_canvas(qt_application):
    from tests.canvas_factory import build_canvas_view

    canvas = build_canvas_view()
    yield canvas
    canvas.services.canvas_scene_reset_service.clear_scene()
    canvas.close()


@pytest.mark.parametrize(
    "attachment", ["free", "atom", "single", "double", "triple", "occupied", "interior"]
)
def test_browser_benzene_build_matches_existing_desktop_workflow(
    desktop_canvas, attachment
):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    builder = canvas.services.structure_build_service
    session = canvas.services.canvas_document_session_service
    center = QPointF(100, 100)
    atom_id = bond_id = None
    if attachment != "free":
        builder.add_benzene_ring(center)
        if attachment == "atom":
            atom_id = 0
        elif attachment != "occupied":
            bond_id = 0
            if attachment in {"single", "double", "triple"}:
                bond = canvas.model.bonds[0]
                bond.order = {"single": 1, "double": 2, "triple": 3}[attachment]
                bond.style = attachment
            if attachment == "interior":
                builder.add_benzene_ring(center, attach_bond_id=0)
    before = session.snapshot_state()
    payload = build_document_payload(before, 9)
    browser = edit_document(
        {
            "document": payload,
            "edit": {
                "kind": "ring",
                "x": center.x(),
                "y": center.y(),
                "atom_id": atom_id,
                "bond_id": bond_id,
            },
        }
    )
    assert not browser["unsupported"]
    builder.add_benzene_ring(center, attach_atom_id=atom_id, attach_bond_id=bond_id)
    actual = session.snapshot_state()
    expected = extract_document_state(browser["document"])
    assert expected["model"] == actual["model"]
    assert expected["ring_fills"] == actual["ring_fills"]
    if attachment in {"triple", "occupied", "interior"}:
        assert expected["model"] == before["model"]


@pytest.mark.parametrize("target", ["atom", "bond"])
@pytest.mark.parametrize("shape", ["chain", "ring"])
def test_browser_deletion_matches_desktop_document(desktop_canvas, target, shape):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    builder = canvas.services.structure_build_service
    if shape == "ring":
        builder.add_benzene_ring(QPointF(100, 100))
    else:
        builder.add_bond_between_points(QPointF(20, 20), QPointF(40, 20), "single", 1)
        builder.add_bond_between_points(QPointF(40, 20), QPointF(60, 20), "single", 1)
    snapshot = canvas.services.canvas_document_session_service.snapshot_state
    before = snapshot()
    browser = edit_document(
        {
            "document": build_document_payload(before, 9),
            "edit": {
                "kind": "delete_selection",
                "selection": [{"target": target, "id": 0}],
            },
        }
    )
    getattr(canvas.services.scene_delete_controller, "delete_" + target)(0)
    actual = snapshot()
    expected = extract_document_state(browser["document"])
    assert expected["model"] == actual["model"]
    assert expected["ring_fills"] == actual["ring_fills"]


def test_failed_shared_ring_build_keeps_document_history_and_identifiers(monkeypatch):
    from chemvas.ui.molecule.structure_build_committer import StructureBuildCommitter

    session = BrowserSession()
    before = deepcopy(session.info)
    original = StructureBuildCommitter.add_bond

    def fail_after_first_bond(self, *args, **kwargs):
        if len(self.canvas.model.bonds):
            raise ValueError("injected construction failure")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(StructureBuildCommitter, "add_bond", fail_after_first_bond)
    with pytest.raises(ValueError, match="injected"):
        session.dispatch(
            {
                "revision": 0,
                "action": "edit",
                "edit": {"kind": "ring", "x": 100, "y": 100},
            }
        )
    assert session.info == before
    assert session.revision == 0
    assert not session.history.can_undo()
    monkeypatch.setattr(StructureBuildCommitter, "add_bond", original)
    result = session.dispatch(
        {"revision": 0, "action": "edit", "edit": {"kind": "ring", "x": 100, "y": 100}}
    )
    assert result["document"]["state"]["model"]["next_atom_id"] == 6
    assert len(result["document"]["state"]["ring_fills"]) == 1


@pytest.mark.parametrize(
    "style", ["single", "double", "triple", "wedge", "hash", "double_center", "bold_in"]
)
def test_bond_click_uses_the_same_policy_as_qt(desktop_canvas, style):
    from PyQt6.QtCore import QPointF

    from chemvas.ui.window.main_window_toolbar_logic import bond_style_from_label

    canvas = desktop_canvas
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(20, 20),
        QPointF(40, 20),
        "double",
        2,
    )
    snapshot = canvas.services.canvas_document_session_service.snapshot_state
    source = build_document_payload(snapshot(), 9)
    browser = edit_document(
        {"document": source, "edit": {"kind": "bond_style", "id": 0, "style": style}}
    )
    settings = canvas.runtime_state.tool_settings_state
    settings.active_bond_style = style
    settings.active_bond_order = bond_style_from_label(style.capitalize())[1]
    assert canvas.services.tool_controller.tools["bond"]._apply_active_style_to_bond(0)
    assert json.loads(
        json.dumps(extract_document_state(browser["document"])["model"])
    ) == json.loads(json.dumps(snapshot()["model"]))


def test_ring_document_continues_web_qt_web_with_shared_records(
    desktop_canvas, tmp_path
):
    from PyQt6.QtCore import QPointF

    session = BrowserSession()
    web = session.dispatch(
        {"revision": 0, "action": "edit", "edit": {"kind": "ring", "x": 100, "y": 100}}
    )
    canvas = desktop_canvas
    desktop = canvas.services.canvas_document_session_service
    desktop.apply_state(extract_document_state(web["document"]))
    assert (
        desktop.snapshot_state()["model"]
        == extract_document_state(web["document"])["model"]
    )
    canvas.services.structure_build_service.add_benzene_ring(
        QPointF(100, 100), attach_bond_id=0
    )
    saved_path = tmp_path / "adapter-roundtrip.chemvas"
    desktop.save_to_file(str(saved_path))
    reopened = session.dispatch(
        {
            "revision": 1,
            "action": "load",
            "document": json.loads(saved_path.read_text()),
        }
    )
    assert len(reopened["document"]["state"]["model"]["atoms"]) == 10
    assert len(reopened["document"]["state"]["ring_fills"]) == 2
    assert not reopened["unsupported"]
    removed = session.dispatch(
        {
            "revision": 2,
            "action": "edit",
            "edit": {
                "kind": "delete_selection",
                "selection": [{"target": "bond", "id": 0}],
            },
        }
    )
    assert removed["document"]["state"]["ring_fills"] == []
    restored = session.dispatch({"revision": 3, "action": "undo"})
    assert restored["document"] == reopened["document"]
    desktop.apply_state(extract_document_state(restored["document"]))
    assert (
        json.loads(json.dumps(desktop.snapshot_state()["model"]))
        == extract_document_state(reopened["document"])["model"]
    )


@pytest.mark.parametrize(
    "style", ["single", "double", "triple", "wedge", "hash", "bold_in"]
)
@pytest.mark.parametrize("placement", ["free", "attached", "existing"])
def test_bond_construction_uses_the_existing_qt_builder(
    desktop_canvas, style, placement
):
    from PyQt6.QtCore import QPointF

    from chemvas.ui.window.main_window_toolbar_logic import bond_style_from_label

    builder = desktop_canvas.services.structure_build_service
    snapshot = desktop_canvas.services.canvas_document_session_service.snapshot_state
    if placement != "free":
        builder.add_bond_between_points(QPointF(30, 40), QPointF(50, 40), "single", 1)
    start = (50, 40) if placement == "attached" else (30, 40)
    end = (70, 40) if placement == "attached" else (50, 40)
    source = build_document_payload(snapshot(), 9)
    browser = draw_bond(source, start=start, end=end, style=style)
    builder.add_bond_between_points(
        QPointF(*start),
        QPointF(*end),
        style,
        bond_style_from_label(style.capitalize())[1],
    )
    assert extract_document_state(browser["document"])["model"] == snapshot()["model"]
    assert len(browser["document"]["state"]["model"]["atoms"]) == (
        3 if placement == "attached" else 2
    )


def test_bond_click_reuses_existing_default_direction(desktop_canvas):
    from PyQt6.QtCore import QPointF

    builder = desktop_canvas.services.structure_build_service
    builder.add_bond_between_points(QPointF(30, 40), QPointF(50, 40), "single", 1)
    snapshot = desktop_canvas.services.canvas_document_session_service.snapshot_state
    source = build_document_payload(snapshot(), 9)
    browser = draw_bond(source, start=(50, 40), end=(50, 40))
    endpoint = builder.default_bond_endpoint(QPointF(50, 40), 1)
    builder.add_bond_between_points(QPointF(50, 40), endpoint, "single", 1)
    assert extract_document_state(browser["document"])["model"] == snapshot()["model"]


def test_failed_bond_build_keeps_candidate_private_and_redo_available(monkeypatch):
    from chemvas.ui.molecule.structure_build_committer import StructureBuildCommitter

    session = BrowserSession()
    session.dispatch(
        {"revision": 0, "action": "edit", "edit": {"kind": "ring", "x": 100, "y": 100}}
    )
    session.dispatch({"revision": 1, "action": "undo"})
    before = deepcopy(session.info)

    def fail_after_atoms(self, *args, **kwargs):
        assert len(self.canvas.model.atoms) == 2
        raise ValueError("injected bond failure")

    monkeypatch.setattr(StructureBuildCommitter, "add_bond", fail_after_atoms)
    with pytest.raises(ValueError, match="injected"):
        session.dispatch(
            {
                "revision": 2,
                "action": "edit",
                "edit": {
                    "kind": "bond",
                    "start": [30, 40],
                    "end": [50, 40],
                    "style": "single",
                },
            }
        )
    assert session.info == before
    assert session.revision == 2
    assert session.history.can_redo()
    assert (
        session.dispatch({"revision": 2, "action": "redo"})["document"]["state"][
            "model"
        ]["next_atom_id"]
        == 6
    )


@pytest.mark.parametrize("text", ["N", "O", " C ", "c", "NH2", "Ph", ""])
@pytest.mark.parametrize("existing", [False, True])
def test_atom_input_matches_native_service(desktop_canvas, text, existing):
    from chemvas.ui.tools.text_tool_logic import (
        apply_text_input,
        resolve_text_tool_target,
    )

    canvas = desktop_canvas
    document = canvas.services.canvas_document_session_service
    labels = canvas.services.atom_label_service
    atom_id = None
    if existing:
        atom_id = labels.add_labelled_atom("C", 100, 100)
    before = build_document_payload(document.snapshot_state(), 9)
    edit = {"kind": "atom", "x": 100, "y": 100, "text": text, "atom_id": atom_id}
    result = edit_document({"document": before, "edit": edit})
    target = resolve_text_tool_target(
        canvas.model, pos=(100, 100), item_atom_id=atom_id
    )
    apply_text_input(
        target,
        text.strip(),
        "C" if existing else "",
        add_atom=labels.add_labelled_atom,
        update_label=labels.add_or_update_atom_label,
        notify_error=lambda message: pytest.fail(message),
    )
    assert result["document"]["state"]["model"] == document.snapshot_state()["model"]
    if text.strip().upper() == "C":
        assert result["drawing"]["atom_labels"][str(atom_id or 0)] == text.strip()
    if existing and not text:
        assert result["drawing"]["atom_labels"] == {}


def test_atom_overlap_merge_matches_native_and_restores_history(desktop_canvas):
    canvas = desktop_canvas
    mutation = canvas.services.canvas_atom_mutation_service
    a = mutation.add_atom("C", 100, 100)
    b = mutation.add_atom("C", 100.3, 100)
    c = mutation.add_atom("C", 120, 100)
    canvas.services.canvas_bond_mutation_service.add_bond(a, c, 1)
    bid = canvas.services.canvas_bond_mutation_service.add_bond(b, c, 2)
    canvas.model.bonds[bid].style = "double"
    document = canvas.services.canvas_document_session_service
    before = build_document_payload(document.snapshot_state(), 9)
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": before})
    changed = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {"kind": "atom", "x": 100, "y": 100, "atom_id": a, "text": "O"},
        }
    )
    canvas.services.atom_label_service.add_or_update_atom_label(
        a, "O", show_carbon=True
    )
    assert changed["document"]["state"]["model"] == document.snapshot_state()["model"]
    assert len(changed["document"]["state"]["model"]["atoms"]) == 2
    restored = session.dispatch({"revision": 2, "action": "undo"})
    assert restored["document"] == before
    assert (
        session.dispatch({"revision": 3, "action": "redo"})["document"]
        == changed["document"]
    )


def test_atom_input_plan_uses_native_target_and_prompt_policy():
    payload = draw_bond(new_document(), start=(100, 100), end=(120, 100))["document"]
    request = {"document": payload, "edit": {"x": 119, "y": 102}, "symbol": ""}
    assert atom_input_plan(request) == {
        "text": None,
        "needs_prompt": True,
        "initial": "C",
    }
    request["symbol"] = " O "
    assert atom_input_plan(request)["text"] == "O"
    changed = edit_document(
        {"document": payload, "edit": {"kind": "atom", "x": 119, "y": 102, "text": "O"}}
    )
    assert changed["document"]["state"]["model"]["atoms"][1]["element"] == "O"
    assert len(changed["document"]["state"]["model"]["atoms"]) == 2


def test_failed_atom_edit_keeps_candidate_history_and_redo(monkeypatch):
    from chemvas.ui.molecule.atom_label_merge_service import AtomLabelMergeService

    session = BrowserSession()
    created = session.dispatch(
        {
            "revision": 0,
            "action": "edit",
            "edit": {"kind": "atom", "x": 100, "y": 100, "text": "N"},
        }
    )
    before = session.dispatch({"revision": 1, "action": "read"})
    with pytest.raises(ValueError, match="Cannot hide"):
        session.dispatch(
            {
                "revision": 1,
                "action": "edit",
                "edit": {"kind": "atom", "x": 100, "y": 100, "text": ""},
            }
        )
    assert session.dispatch({"revision": 1, "action": "read"}) == before
    session.dispatch({"revision": 1, "action": "undo"})
    before = session.dispatch({"revision": 2, "action": "read"})

    def fail(self, atom_id):
        raise ValueError("merge failed after atom creation")

    monkeypatch.setattr(AtomLabelMergeService, "merge_overlapping_atoms", fail)
    with pytest.raises(ValueError, match="merge failed"):
        session.dispatch(
            {
                "revision": 2,
                "action": "edit",
                "edit": {"kind": "atom", "x": 100, "y": 100, "text": "O"},
            }
        )
    assert session.dispatch({"revision": 2, "action": "read"}) == before
    assert (
        session.dispatch({"revision": 2, "action": "redo"})["document"]
        == created["document"]
    )


def test_atom_control_uses_native_default_and_properties():
    from chemvas.ui.canvas.canvas_tool_settings_state import CanvasToolSettingsState
    from chemvas.ui.window.main_window_config import ATOM_INPUT_SPEC

    assert ui_spec()["atom_input"] == {
        **ATOM_INPUT_SPEC,
        "value": CanvasToolSettingsState().atom_symbol,
    }


@pytest.mark.parametrize(
    "items",
    [
        [{"target": "atom", "id": 0}],
        [{"target": "bond", "id": 0}],
        [
            {"target": "atom", "id": 0},
            {"target": "bond", "id": 0},
            {"target": "bond", "id": 1},
        ],
        [{"target": "atom", "id": i} for i in range(6)],
    ],
)
@pytest.mark.parametrize("delta", [(25.5, -10.25), (-14, 37), (0, 0)])
def test_browser_movement_matches_native_controller_and_ring_polygon(
    desktop_canvas, items, delta
):
    from PyQt6.QtCore import QPointF

    from chemvas.features.selection import selected_atom_ids_with_bond_endpoints

    canvas = desktop_canvas
    canvas.services.structure_build_service.add_benzene_ring(QPointF(100, 100))
    documents = canvas.services.canvas_document_session_service
    before = build_document_payload(documents.snapshot_state(), 9)
    moved = edit_document(
        {
            "document": before,
            "edit": {
                "kind": "move",
                "selection": items,
                "dx": delta[0],
                "dy": delta[1],
            },
        }
    )
    atoms = selected_atom_ids_with_bond_endpoints(
        [item["id"] for item in items if item["target"] == "atom"],
        [item["id"] for item in items if item["target"] == "bond"],
        bonds=canvas.model.bonds,
    )
    canvas.services.move_controller.move_atoms(atoms, *delta)
    native = documents.snapshot_state()
    assert moved["document"]["state"]["model"] == native["model"]
    assert moved["document"]["state"]["ring_fills"] == native["ring_fills"]
    for atom_id, atom in moved["document"]["state"]["model"]["atoms"].items():
        source = before["state"]["model"]["atoms"][atom_id]
        assert atom["x"] == source["x"] + (delta[0] if atom_id in atoms else 0)
        assert atom["y"] == source["y"] + (delta[1] if atom_id in atoms else 0)
    if delta == (0, 0):
        assert moved["document"] == before


def test_move_failure_and_preview_leave_session_and_redo_unchanged(monkeypatch):
    from chemvas.ui.canvas.canvas_move_controller import CanvasMoveController

    session = BrowserSession()
    first = session.dispatch(
        {"revision": 0, "action": "edit", "edit": {"kind": "ring", "x": 100, "y": 100}}
    )
    change = {
        "kind": "move",
        "selection": [{"target": "bond", "id": 0}],
        "dx": 10,
        "dy": 20,
    }
    preview = edit_document({"document": first["document"], "edit": change})
    assert session.dispatch({"revision": 1, "action": "read"}) == first
    moved = session.dispatch({"revision": 1, "action": "edit", "edit": change})
    assert moved["document"] == preview["document"]
    assert len(session.state.history) == 2
    undone = session.dispatch({"revision": 2, "action": "undo"})
    assert undone["document"] == first["document"]
    before = session.dispatch({"revision": 3, "action": "read"})
    original = CanvasMoveController.move_atom

    def fail(self, atom_id, dx, dy):
        original(self, atom_id, dx, dy)
        raise ValueError("redraw failed after movement")

    monkeypatch.setattr(CanvasMoveController, "move_atom", fail)
    with pytest.raises(ValueError, match="after movement"):
        session.dispatch({"revision": 3, "action": "edit", "edit": change})
    assert session.dispatch({"revision": 3, "action": "read"}) == before
    assert (
        session.dispatch({"revision": 3, "action": "redo"})["document"]
        == moved["document"]
    )


def test_zero_move_does_not_consume_redo_or_history():
    session = BrowserSession()
    session.dispatch(
        {"revision": 0, "action": "edit", "edit": {"kind": "ring", "x": 100, "y": 100}}
    )
    change = {
        "kind": "move",
        "selection": [{"target": "bond", "id": 0}],
        "dx": 10,
        "dy": 20,
    }
    session.dispatch({"revision": 1, "action": "edit", "edit": change})
    before = session.dispatch({"revision": 2, "action": "undo"})
    after = session.dispatch(
        {"revision": 3, "action": "edit", "edit": {**change, "dx": 0, "dy": 0}}
    )
    assert after["document"] == before["document"]
    assert after["can_redo"]
    assert len(session.state.history) == 1


@pytest.mark.parametrize(
    "selection",
    [
        [{"target": "atom", "id": True}],
        [{"target": "bond", "id": -1}],
        [{"target": "atom", "id": 999}],
        [{"target": "note", "id": 0}],
        None,
    ],
)
def test_invalid_move_selection_is_rejected(selection):
    source = draw_bond(new_document())["document"]
    with pytest.raises(ValueError):
        edit_document(
            {
                "document": source,
                "edit": {"kind": "move", "selection": selection, "dx": 1, "dy": 2},
            }
        )


def test_multiple_delete_is_one_shared_plan_and_undo():
    session = BrowserSession()
    ring = session.dispatch(
        {"revision": 0, "action": "edit", "edit": {"kind": "ring", "x": 100, "y": 100}}
    )
    changed = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {
                "kind": "delete_selection",
                "selection": [{"target": "atom", "id": i} for i in range(6)],
            },
        }
    )
    assert changed["document"]["state"]["model"]["atoms"] == {}
    assert changed["document"]["state"]["ring_fills"] == []
    assert len(session.state.history) == 2
    assert (
        session.dispatch({"revision": 2, "action": "undo"})["document"]
        == ring["document"]
    )


@pytest.mark.parametrize("dx", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_move_is_rejected_without_changing_source(dx):
    source = draw_bond(new_document())["document"]
    before = deepcopy(source)
    with pytest.raises(ValueError, match="finite"):
        edit_document(
            {
                "document": source,
                "edit": {
                    "kind": "move",
                    "selection": [{"target": "atom", "id": 0}],
                    "dx": dx,
                    "dy": 1,
                },
            }
        )
    assert source == before


@pytest.mark.parametrize("style", ["bold_in", "bold_center", "bold_out"])
@pytest.mark.parametrize("order", [1, 2, 3])
@pytest.mark.parametrize("ring", [False, True])
def test_bold_geometry_matches_native_items(desktop_canvas, style, order, ring):
    from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsPolygonItem

    if ring:
        payload = edit_document(
            {"document": new_document(), "edit": {"kind": "ring", "x": 100, "y": 100}}
        )["document"]
    else:
        payload = draw_bond(new_document())["document"]
        payload = draw_bond(payload, start=(50, 40), end=(60, 57.32))["document"]
    for bond in payload["state"]["model"]["bonds"]:
        bond["style"], bond["order"] = style, order
    browser = document_info(payload)
    assert not browser["unsupported"]
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(payload)
    )
    for (
        bond_id,
        items,
    ) in desktop_canvas.runtime_state.bond_graphics_state.bond_items.items():
        primitives = browser["drawing"]["bonds"][str(bond_id)]
        painted = [
            item
            for item in items
            if isinstance(item, (QGraphicsLineItem, QGraphicsPolygonItem))
        ]
        assert len(painted) == len(primitives)
        for item, primitive in zip(painted, primitives, strict=True):
            if isinstance(item, QGraphicsLineItem):
                line = item.line()
                assert primitive["line"] == pytest.approx(
                    (line.x1(), line.y1(), line.x2(), line.y2()), abs=1e-9
                )
            else:
                actual = [(p.x(), p.y()) for p in item.polygon()]
                assert len(actual) == len(primitive["polygon"])
                for expected, point in zip(primitive["polygon"], actual, strict=True):
                    assert expected == pytest.approx(point, abs=1e-9)


def test_bold_overlay_preserves_double_order_and_undo():
    session = BrowserSession()
    source = draw_bond(new_document(), style="double")["document"]
    session.dispatch({"revision": 0, "action": "load", "document": source})
    bold = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {"kind": "bond_style", "id": 0, "style": "bold_in"},
        }
    )
    bond = bold["document"]["state"]["model"]["bonds"][0]
    assert (bond["style"], bond["order"]) == ("bold_in", 2)
    assert session.dispatch({"revision": 2, "action": "undo"})["document"] == source
    assert (
        session.dispatch({"revision": 3, "action": "redo"})["document"]
        == bold["document"]
    )
