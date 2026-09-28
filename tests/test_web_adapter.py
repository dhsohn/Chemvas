from __future__ import annotations

import http.client
import json
import shutil
import subprocess
import sys
import threading
from copy import deepcopy
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import pytest

from chemvas.bootstrap.web_adapter import (
    MAX_REQUEST_BYTES,
    BrowserFontMeasurements,
    BrowserServer,
    BrowserSession,
    BrowserStructureAdapter,
    atom_input_plan,
    document_info,
    edit_document,
    new_document,
    ui_css,
    ui_spec,
)
from chemvas.domain.document import (
    VALID_ARROW_KINDS,
    build_document_payload,
    extract_document_state,
)
from chemvas.ui.window.main_window_config import ARROW_MENU_SPECS

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
                "edit_document({'document': merged['document'], 'edit': {'kind': 'bond_style', 'id': 0, 'style': 'bold_in'}}); edit_document({'document': merged['document'], 'edit': {'kind': 'bond_style', 'id': 0, 'style': 'dotted'}}); "
                "from chemvas.ui.canvas.canvas_chemdraw_shortcut_service import CanvasChemdrawShortcutService; "
                "atom = ring['document']['state']['model']['atoms'][0]; "
                "[edit_document({'document': ring['document'], 'edit': {'kind': 'hover_shortcut', 'x': atom['x'], 'y': atom['y'], 'key': key}}) for key in CanvasChemdrawShortcutService.ATOM_HOTKEYS - {'+', '-'}]; "
                "atoms = ring['document']['state']['model']['atoms']; bond = ring['document']['state']['model']['bonds'][0]; a, b = atoms[bond['a']], atoms[bond['b']]; "
                "[edit_document({'document': ring['document'], 'edit': {'kind': 'hover_shortcut', 'x': (a['x']+b['x'])/2, 'y': (a['y']+b['y'])/2, 'key': key}}) for key in CanvasChemdrawShortcutService.BOND_HOTKEYS]; "
                "from chemvas.bootstrap.web_adapter import atom_input_plan; "
                "plan = atom_input_plan({'document': ring['document'], 'edit': {'kind': 'atom_prompt', 'x': atom['x'], 'y': atom['y']}, 'symbol': ''}); assert plan['needs_prompt']; "
                "labelled = edit_document({'document': ring['document'], 'edit': {'kind': 'atom_prompt', 'atom_id': plan['atom_id'], 'x': atom['x'], 'y': atom['y'], 'text': 'NH2'}}); "
                "edit_document({'document': labelled['document'], 'edit': {'kind': 'delete_hover', 'x': atom['x'], 'y': atom['y']}}); "
                "from chemvas.bootstrap.web_adapter import BrowserFontMeasurements; "
                "spec = labelled['drawing']['label_measurements']; "
                "font = BrowserFontMeasurements({'family': spec['family'], 'metrics': {q['key']: {'width': 8, 'ascent': 12, 'descent': 4, 'cap_height': 11, 'line_height': 18} for q in spec['queries']}, 'ink': {str(q['pixels'])+':'+q['text']: [[-4,-6],[4,-6],[4,6],[-4,6]] for q in spec['queries']}}); "
                "assert 'atom_layouts' in document_info(labelled['document'], font=font)['drawing']; "
                "from chemvas.domain.document import VALID_ARROW_KINDS; "
                "arrows = new_document(); arrows['state']['arrows'] = [{'kind': k, 'start': [0,0], 'end': [60,30]} for k in VALID_ARROW_KINDS]; "
                "assert len(document_info(arrows)['drawing']['arrows']) == len(VALID_ARROW_KINDS); "
                "from chemvas.bootstrap.web_adapter import BrowserStructureAdapter; from chemvas.domain.document import extract_document_state; BrowserStructureAdapter(extract_document_state(arrows)).pick_target(20, 12, [], preferred=False, scale=1); "
                "moved = edit_document({'document': arrows, 'edit': {'kind': 'move', 'selection': [{'target': 'arrow', 'id': i} for i in range(len(VALID_ARROW_KINDS))], 'dx': 5, 'dy': -10}}); "
                "edit_document({'document': moved['document'], 'edit': {'kind': 'delete_selection', 'selection': [{'target': 'arrow', 'id': 0}]}}); "
                "edit_document({'document': new_document(), 'edit': {'kind': 'arrow', 'start': [0,0], 'end': [60,30], 'style': 'curved_double', 'dragged': True, 'shift': False, 'scale': 1}}); "
                "edit_document({'document': new_document(), 'edit': {'kind': 'line', 'start': [0,0], 'end': [60,30], 'style': 'line_wavy', 'dragged': True, 'shift': True, 'scale': 1, 'hits': []}}); "
                "picked = BrowserSession(); picked.dispatch({'revision': 0, 'action': 'pick', 'scale': 1, 'x': 0, 'y': 0, 'hits': [], 'preferred': True}); "
                "edit_document({'document': ring['document'], 'edit': {'kind': 'erase', 'scale': 1, 'x': 100, 'y': 100, 'hits': []}}); "
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
        atoms = browser["document"]["state"]["model"]["atoms"]
        a, b = atoms[0], atoms[1]
        browser = edit_document(
            {
                "document": browser["document"],
                "edit": {
                    "kind": "ring",
                    "x": (a["x"] + b["x"]) / 2,
                    "y": (a["y"] + b["y"]) / 2,
                },
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
    expected = deepcopy(before)
    adapter = BrowserStructureAdapter(expected)
    adapter.insert_benzene(center.x(), center.y(), atom_id, bond_id)
    builder.add_benzene_ring(center, attach_atom_id=atom_id, attach_bond_id=bond_id)
    actual = session.snapshot_state()
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
    "style",
    [
        "single",
        "double",
        "triple",
        "wedge",
        "hash",
        "bold_in",
        "dotted",
    ],
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
    "style", ["single", "double", "triple", "wedge", "hash", "bold_in", "dotted"]
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


@pytest.mark.parametrize("style", ["dotted", "dotted_double", "dotted_double_outer"])
@pytest.mark.parametrize("length", [20, 40])
@pytest.mark.parametrize("ring", [False, True])
def test_dotted_geometry_matches_native_paths(desktop_canvas, style, length, ring):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QPainterPath
    from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsPathItem

    payload = new_document()
    payload["state"]["settings"]["bond_length_px"] = length
    if ring:
        payload = edit_document(
            {"document": payload, "edit": {"kind": "ring", "x": 100, "y": 100}}
        )["document"]
    else:
        payload = draw_bond(payload)["document"]
    for bond in payload["state"]["model"]["bonds"]:
        bond["style"] = style
        bond["order"] = 1 if style == "dotted" else 2
    browser = document_info(payload)
    assert not browser["unsupported"]
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(payload)
    )
    for (
        bond_id,
        items,
    ) in desktop_canvas.runtime_state.bond_graphics_state.bond_items.items():
        painted = [
            item
            for item in items
            if isinstance(item, (QGraphicsLineItem, QGraphicsPathItem))
        ]
        primitives = browser["drawing"]["bonds"][str(bond_id)]
        assert len(painted) == len(primitives)
        for item, primitive in zip(painted, primitives, strict=True):
            if isinstance(item, QGraphicsLineItem):
                line = item.line()
                assert primitive["line"] == pytest.approx(
                    (line.x1(), line.y1(), line.x2(), line.y2()), abs=1e-9
                )
            else:
                expected = QPainterPath()
                for x, y in primitive["dots"]:
                    expected.addEllipse(
                        QPointF(x, y), primitive["radius"], primitive["radius"]
                    )
                assert expected == item.path()


def test_dotted_overlay_keeps_order_and_history():
    session = BrowserSession()
    source = draw_bond(new_document(), style="double")["document"]
    session.dispatch({"revision": 0, "action": "load", "document": source})
    result = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {"kind": "bond_style", "id": 0, "style": "dotted"},
        }
    )
    bond = result["document"]["state"]["model"]["bonds"][0]
    assert (bond["style"], bond["order"]) == ("dotted_double", 2)
    assert session.dispatch({"revision": 2, "action": "undo"})["document"] == source
    assert (
        session.dispatch({"revision": 3, "action": "redo"})["document"]
        == result["document"]
    )


def test_dotted_centered_double_refusal_preserves_redo():
    session = BrowserSession()
    source = draw_bond(new_document(), style="double")["document"]
    source["state"]["model"]["bonds"][0]["style"] = "double_center"
    session.dispatch({"revision": 0, "action": "load", "document": source})
    session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {"kind": "bond_style", "id": 0, "style": "triple"},
        }
    )
    before = session.dispatch({"revision": 2, "action": "undo"})
    with pytest.raises(ValueError, match="inner or outer"):
        session.dispatch(
            {
                "revision": 3,
                "action": "edit",
                "edit": {"kind": "bond_style", "id": 0, "style": "dotted"},
            }
        )
    assert session.info["document"] == before["document"]
    assert session.history.can_redo()
    assert session.revision == 3


@pytest.mark.parametrize("style", ["double_center", "bold_out", "dotted_double"])
def test_edit_rejects_non_toolbar_styles_instead_of_guessing_order(style):
    source = draw_bond(new_document())["document"]
    with pytest.raises(ValueError, match="Unsupported bond style"):
        draw_bond(source, style=style)
    with pytest.raises(ValueError, match="Unsupported bond style"):
        edit_document(
            {
                "document": source,
                "edit": {"kind": "bond_style", "id": 0, "style": style},
            }
        )


@pytest.mark.parametrize(
    "value", ["100", True, None, float("nan"), float("inf"), float("-inf")]
)
@pytest.mark.parametrize("kind", ["bond", "ring", "atom", "move"])
def test_non_numeric_or_nonfinite_coordinates_leave_session_unchanged(value, kind):
    session = BrowserSession()
    edit = {
        "bond": {
            "kind": "bond",
            "start": [value, 20],
            "end": [40, 20],
            "style": "single",
        },
        "ring": {"kind": "ring", "x": value, "y": 20},
        "atom": {"kind": "atom", "x": value, "y": 20, "text": "N"},
        "move": {"kind": "move", "selection": [], "dx": value, "dy": 20},
    }[kind]
    before = deepcopy(session.info)
    with pytest.raises(ValueError, match="finite numbers"):
        session.dispatch({"revision": 0, "action": "edit", "edit": edit})
    assert session.info == before
    assert session.revision == 0
    assert not session.history.can_undo()


def test_failed_first_requests_do_not_consume_session_slots(server):
    for payload in (
        {"revision": 5, "action": "read"},
        {"revision": 0, "action": "load", "document": {}},
    ):
        for _ in range(17):
            assert (
                request(
                    server, "/api/session", method="POST", body=json.dumps(payload)
                )[0]
                == 400
            )
            assert not server.sessions
    status, body, _ = request(
        server,
        "/api/session",
        method="POST",
        body=json.dumps({"revision": 0, "action": "read"}),
    )
    assert status == 200
    session_id = json.loads(body)["session"]
    assert list(server.sessions) == [session_id]
    assert (
        request(
            server,
            "/api/session",
            method="POST",
            body=json.dumps({"revision": 9, "action": "read", "session": session_id}),
        )[0]
        == 200
    )
    assert list(server.sessions) == [session_id]


@pytest.mark.parametrize("kind", ["bond", "ring", "atom", "move"])
def test_http_fractional_coordinates_use_strict_json_numbers(server, kind):
    edit = {
        "bond": {
            "kind": "bond",
            "start": [100.25, 120.5],
            "end": [120.25, 120.5],
            "style": "dotted",
        },
        "ring": {"kind": "ring", "x": 100.25, "y": 120.5},
        "atom": {"kind": "atom", "x": 100.25, "y": 120.5, "text": "N"},
        "move": {"kind": "move", "selection": [], "dx": 0.25, "dy": 0.5},
    }[kind]
    status, body, _ = request(
        server,
        "/api/session",
        method="POST",
        body=json.dumps({"revision": 0, "action": "edit", "edit": edit}),
    )
    assert status == 200, body
    assert json.loads(body)["revision"] == 1


def test_http_atom_input_accepts_fractional_scene_point(server):
    status, body, _ = request(
        server,
        "/api/atom-input",
        method="POST",
        body=json.dumps(
            {
                "document": new_document(),
                "edit": {"x": 100.25, "y": 120.5},
                "symbol": "N",
            }
        ),
    )
    assert status == 200, body


@pytest.mark.parametrize("length", [20, 40])
@pytest.mark.parametrize("snap_step", [30, 45])
@pytest.mark.parametrize(
    "case",
    [
        "near_bond",
        "outer_bond",
        "far_bond",
        "outside_bond",
        "near_atom",
        "release_bond",
        "free",
    ],
)
def test_bond_scene_points_match_native_press_and_release(
    desktop_canvas, monkeypatch, length, snap_step, case
):
    from types import SimpleNamespace

    from PyQt6.QtCore import QPointF, Qt

    from chemvas.bootstrap.web_adapter import BrowserStructureAdapter

    canvas = desktop_canvas
    builder = canvas.services.structure_build_service
    builder.add_bond_between_points(
        QPointF(100, 100), QPointF(100 + length, 100), "single", 1
    )
    session = canvas.services.canvas_document_session_service
    source = session.snapshot_state()
    source["settings"]["bond_length_px"] = length
    session.apply_state(source)
    offsets = {
        "near_bond": ((0.5, 0.275), (0.5, 0.275)),
        "outer_bond": ((0.5, 0.45), (0.5, 0.45)),
        "far_bond": ((0.5, 0.50), (0.5, 0.50)),
        "outside_bond": ((0.5, 0.54), (0.5, 0.54)),
        "near_atom": ((0.325, 0), (0.325, 1)),
        "release_bond": ((0.5, 1.5), (0.5, 0.05)),
        "free": ((3, 3), (3.9, 3.7)),
    }
    start, end = [[100 + x * length, 100 + y * length] for x, y in offsets[case]]
    candidate = deepcopy(source)
    adapter = BrowserStructureAdapter(candidate)
    adapter.runtime_state.tool_settings_state.snap_angle_step = snap_step
    adapter.insert_bond(start, end, "double")

    settings = canvas.runtime_state.tool_settings_state
    settings.snap_angle_step = snap_step
    settings.active_bond_style, settings.active_bond_order = "double", 2
    tool = canvas.services.tool_controller.tools["bond"]
    monkeypatch.setattr(
        tool.context.hit_testing_service, "_scene_pos_mapper", lambda event: event.scene
    )
    press = SimpleNamespace(
        scene=QPointF(*start), button=lambda: Qt.MouseButton.LeftButton
    )
    release = SimpleNamespace(
        scene=QPointF(*end), button=lambda: Qt.MouseButton.LeftButton
    )
    assert tool.on_mouse_press(press)
    tool.on_mouse_release(release)
    assert candidate["model"] == session.snapshot_state()["model"]
    if case in {"near_bond", "outer_bond", "far_bond"}:
        assert len(adapter.model.atoms) == 2
        assert adapter.model.bonds[0].order == 2
    elif case == "release_bond":
        assert len(adapter.model.atoms) == 3
        assert 0 in (adapter.model.bonds[-1].a, adapter.model.bonds[-1].b)


@pytest.mark.parametrize("length", [20, 40])
@pytest.mark.parametrize(
    "offset,expected_target",
    [
        ((0.5, 0.275), (None, 0)),
        ((0.5, -0.275), (None, 0)),
        ((0.5, 0.36), (None, None)),
        ((-0.25, 0), (0, None)),
        ((0.25, 0.15), (0, None)),
        ((-0.36, 0), (None, None)),
        ((3, 3), (None, None)),
    ],
)
def test_ring_scene_point_matches_native_insert(
    desktop_canvas, length, offset, expected_target
):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    documents = canvas.services.canvas_document_session_service
    source = documents.snapshot_state()
    source["settings"]["bond_length_px"] = length
    documents.apply_state(source)
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(100, 100), QPointF(100 + length, 100), "single", 1
    )
    source = documents.snapshot_state()
    x, y = (100 + value * length for value in offset)
    controller = canvas.services.insert_controller
    assert controller._template_structure_target_ids(QPointF(x, y)) == expected_target
    direct = controller._direct_structure_hit(QPointF(x, y))
    direct_id = direct.id if direct is not None else None
    actual = edit_document(
        {
            "document": build_document_payload(source, 9),
            "edit": {"kind": "ring", "x": x, "y": y, "atom_id": direct_id},
        }
    )
    controller.begin_ring_template_insert(6, "benzene")
    controller.commit_template_insert(QPointF(x, y))
    expected = documents.snapshot_state()
    assert actual["document"]["state"]["model"] == expected["model"]
    assert actual["document"]["state"]["ring_fills"] == expected["ring_fills"]


def test_browser_history_keeps_documents_and_renders_each_edit_once(monkeypatch):
    from chemvas.bootstrap import web_adapter

    session = BrowserSession()
    source = session.info["document"]
    calls = []
    draw = web_adapter.drawing_geometry
    monkeypatch.setattr(
        web_adapter,
        "drawing_geometry",
        lambda state: (calls.append(state), draw(state))[1],
    )
    changed = session.dispatch(
        {"revision": 0, "action": "edit", "edit": {"kind": "ring", "x": 100, "y": 100}}
    )
    assert len(calls) == 1
    command = session.state.history[-1]
    assert command.before is source
    assert command.after is changed["document"]
    assert {"drawing", "sheet", "unsupported"}.isdisjoint(command.before)
    assert {"drawing", "sheet", "unsupported"}.isdisjoint(command.after)
    restored = session.dispatch({"revision": 1, "action": "undo"})
    assert len(calls) == 2
    assert restored["document"] == source
    redone = session.dispatch({"revision": 2, "action": "redo"})
    assert len(calls) == 3
    assert redone["drawing"] == changed["drawing"]


@pytest.mark.parametrize("action", ["undo", "redo"])
def test_failed_history_render_keeps_document_and_stacks(monkeypatch, action):
    from chemvas.bootstrap import web_adapter

    session = BrowserSession()
    session.dispatch(
        {"revision": 0, "action": "edit", "edit": {"kind": "ring", "x": 100, "y": 100}}
    )
    if action == "redo":
        session.dispatch({"revision": 1, "action": "undo"})
    before = session.dispatch({"action": "read"})
    undo, redo = list(session.state.history), list(session.state.redo_stack)
    draw = web_adapter.drawing_geometry

    def fail(state):
        raise ValueError("injected drawing failure")

    monkeypatch.setattr(web_adapter, "drawing_geometry", fail)
    with pytest.raises(ValueError, match="injected"):
        session.dispatch({"revision": session.revision, "action": action})
    assert session.dispatch({"action": "read"}) == before
    assert session.state.history == undo
    assert session.state.redo_stack == redo
    monkeypatch.setattr(web_adapter, "drawing_geometry", draw)
    session.dispatch({"revision": session.revision, "action": action})
    assert session.revision == before["revision"] + 1


def test_atom_prompt_does_not_render_discarded_geometry(monkeypatch):
    from chemvas.bootstrap import web_adapter

    payload = new_document()

    def fail(state):
        raise AssertionError("Input planning must not draw the scene")

    monkeypatch.setattr(web_adapter, "drawing_geometry", fail)
    assert (
        atom_input_plan(
            {"document": payload, "edit": {"x": 100, "y": 100}, "symbol": "O"}
        )["text"]
        == "O"
    )


def test_http_read_recovers_a_stale_revision_and_document_name(server):
    status, body, _ = request(
        server,
        "/api/session",
        method="POST",
        body=json.dumps(
            {
                "revision": 0,
                "action": "load",
                "document": new_document(),
                "name": "Recovered.chemvas",
            }
        ),
    )
    assert status == 200
    session_id = json.loads(body)["session"]
    status, _lost_body, _ = request(
        server,
        "/api/session",
        method="POST",
        body=json.dumps(
            {
                "session": session_id,
                "revision": 1,
                "action": "edit",
                "edit": {"kind": "ring", "x": 100, "y": 100},
            }
        ),
    )
    assert status == 200
    status, body, _ = request(
        server,
        "/api/session",
        method="POST",
        body=json.dumps({"session": session_id, "revision": 1, "action": "read"}),
    )
    assert status == 200
    recovered = json.loads(body)
    assert recovered["revision"] == 2
    assert recovered["name"] == "Recovered.chemvas"
    assert len(recovered["document"]["state"]["model"]["atoms"]) == 6
    assert recovered["can_undo"] and recovered["dirty"]
    status, body, _ = request(
        server,
        "/api/session",
        method="POST",
        body=json.dumps(
            {"session": session_id, "revision": recovered["revision"], "action": "undo"}
        ),
    )
    assert status == 200
    assert not json.loads(body)["document"]["state"]["model"]["atoms"]


def test_busy_document_does_not_block_another_session(server, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    ids = []
    for _ in range(2):
        status, body, _ = request(
            server,
            "/api/session",
            method="POST",
            body=json.dumps({"revision": 0, "action": "read"}),
        )
        assert status == 200
        ids.append(json.loads(body)["session"])
    entered, release = threading.Event(), threading.Event()
    first = server.sessions[ids[0]]
    dispatch = first.dispatch

    def slow_dispatch(payload):
        entered.set()
        assert release.wait(5)
        return dispatch(payload)

    monkeypatch.setattr(first, "dispatch", slow_dispatch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        slow = pool.submit(
            request,
            server,
            "/api/session",
            method="POST",
            body=json.dumps({"session": ids[0], "revision": 0, "action": "read"}),
        )
        try:
            assert entered.wait(2)
            independent = pool.submit(
                request,
                server,
                "/api/session",
                method="POST",
                body=json.dumps({"session": ids[1], "action": "read"}),
            )
            assert independent.result(timeout=2)[0] == 200
        finally:
            release.set()
        assert slow.result(timeout=2)[0] == 200


def test_closed_session_cannot_accept_edits(server):
    status, body, _ = request(
        server,
        "/api/session",
        method="POST",
        body=json.dumps({"revision": 0, "action": "read"}),
    )
    assert status == 200
    session_id = json.loads(body)["session"]
    session = server.sessions[session_id]
    assert (
        request(
            server,
            "/api/session",
            method="POST",
            body=json.dumps({"session": session_id, "action": "close"}),
        )[0]
        == 200
    )
    assert session.closed
    assert session_id not in server.sessions
    assert (
        request(
            server,
            "/api/session",
            method="POST",
            body=json.dumps(
                {
                    "session": session_id,
                    "revision": 0,
                    "action": "edit",
                    "edit": {"kind": "ring", "x": 100, "y": 100},
                }
            ),
        )[0]
        == 400
    )
    assert not session.info["document"]["state"]["model"]["atoms"]


@pytest.mark.parametrize("length", [20, 40])
@pytest.mark.parametrize("text", ["NH2", "NH", "CF3", "Ph3P", "N", "Cl", "tBu"])
@pytest.mark.parametrize("direction", ["left", "right", "vertical", "chain"])
@pytest.mark.parametrize("explicit", [False, True])
def test_browser_label_runs_match_native_typography(
    desktop_canvas, length, text, direction, explicit
):
    from PyQt6.QtGui import QFont, QFontMetricsF, QTextDocument

    from chemvas.bootstrap.web_adapter import (
        browser_label_layouts,
        place_browser_labels,
    )
    from chemvas.features.rendering import RenderMetrics

    state = new_document()["state"]
    adapter = BrowserStructureAdapter(state)
    adapter.model.add_atom(text, 100, 100)
    adapter.model.atoms[0].explicit_label = explicit
    for x, y in {
        "left": [(-1, 0)],
        "right": [(1, 0)],
        "vertical": [(0, -1)],
        "chain": [(-1, 0), (1, 0)],
    }[direction]:
        atom_id = adapter.model.add_atom("C", 100 + x * length, 100 + y * length)
        adapter.model.add_bond(0, atom_id)
    adapter.publish_model()
    state["settings"]["bond_length_px"] = length
    canvas = desktop_canvas
    canvas.services.canvas_document_session_service.apply_state(state)
    item = canvas.runtime_state.atom_graphics_state.atom_items[0]
    metrics = RenderMetrics()
    metrics.set_bond_length(length)
    spec = browser_label_layouts(canvas.model, metrics)
    measured = {}
    for query in spec["queries"]:
        font = QFont(item.font())
        font.setPointSizeF(query["size"])
        fm = QFontMetricsF(font)
        document = QTextDocument()
        document.setDefaultFont(font)
        document.setPlainText(query["text"])
        measured[query["key"]] = {
            "width": fm.horizontalAdvance(query["text"]),
            "ascent": fm.ascent(),
            "descent": fm.descent(),
            "cap_height": fm.capHeight(),
            "line_height": document.size().height() - 2 * document.documentMargin(),
        }
    relative_runs = place_browser_labels(
        {
            "size": spec["size"],
            "labels": [spec["labels"]["0"]],
            "measurements": measured,
        }
    )[0]
    runs = [{**run, "x": run["x"] + 100, "y": run["y"] + 100} for run in relative_runs]
    margin = item.document().documentMargin()
    if item._layout is not None:
        expected = [
            {
                "text": run.text,
                "size": run.point_size,
                "x": item.pos().x() + margin + run.x,
                "y": item.pos().y() + margin + run.baseline,
            }
            for run in item._layout.runs
        ]
    else:
        expected = [
            {
                "text": item.toPlainText(),
                "size": item.font().pointSizeF(),
                "x": item.pos().x() + margin,
                "y": item.pos().y() + margin + QFontMetricsF(item.font()).ascent(),
            }
        ]
    assert len(runs) == len(expected)
    for actual, native in zip(runs, expected, strict=True):
        assert actual["text"] == native["text"]
        assert actual["size"] == pytest.approx(native["size"])
        assert actual["x"] == pytest.approx(native["x"])
        assert actual["y"] == pytest.approx(native["y"])
    assert canvas.model.atoms[0].element == text


def test_label_layout_uses_measured_runs_without_mutating_document(monkeypatch):
    from chemvas.bootstrap.web_adapter import (
        browser_label_layouts,
        place_browser_labels,
    )
    from chemvas.domain.document import deserialize_model_state
    from chemvas.features.rendering import RenderMetrics

    document = edit_document(
        {
            "document": new_document(),
            "edit": {"kind": "atom", "x": 100, "y": 100, "text": "NH2"},
        }
    )["document"]
    before = deepcopy(document)
    model = deserialize_model_state(document["state"]["model"])
    spec = browser_label_layouts(model, RenderMetrics())
    measurements = {
        query["key"]: {
            "width": len(query["text"]) * query["size"] / 2,
            "ascent": 12,
            "descent": 4,
            "cap_height": 11,
            "line_height": 18,
        }
        for query in spec["queries"]
    }

    def no_document_validation(*args, **kwargs):
        raise AssertionError("Label presentation must not validate a document")

    monkeypatch.setattr(
        "chemvas.bootstrap.web_adapter.document_info", no_document_validation
    )
    payload = {
        "size": spec["size"],
        "labels": list(spec["labels"].values()),
        "measurements": measurements,
    }
    placed = place_browser_labels(payload)
    assert [run["text"] for run in placed[0]] == ["NH", "2"]
    assert document == before
    for invalid in [True, -1, "12", None]:
        measurements[spec["queries"][0]["key"]]["width"] = invalid
        with pytest.raises(ValueError):
            place_browser_labels(payload)
    with pytest.raises(ValueError):
        place_browser_labels({**payload, "measurements": {}})


def test_http_stale_edit_is_a_conflict_not_a_validation_error(server):
    status, body, _ = request(
        server,
        "/api/session",
        method="POST",
        body=json.dumps({"revision": 0, "action": "read"}),
    )
    assert status == 200
    session_id = json.loads(body)["session"]
    status, body, _ = request(
        server,
        "/api/session",
        method="POST",
        body=json.dumps({"session": session_id, "revision": 1, "action": "undo"}),
    )
    assert status == 409
    assert "stale state" in json.loads(body)["error"]
    assert server.sessions[session_id].revision == 0


def test_browser_navigation_uses_native_wheel_magnification(desktop_canvas):
    from PyQt6.QtCore import QPoint, Qt

    from chemvas.ui.canvas.canvas_view import CanvasView
    from chemvas.ui.canvas.input_view_access import set_zoom_for
    from tests.test_canvas_view_wheel_and_scroll import _FakeWheelEvent

    cases = [
        (zoom, delta)
        for zoom in (0.2, 1.0, 5.0)
        for delta in (-6000, -60, -0.5, 0, 0.5, 60, 6000)
    ]
    script = """
import {wheelView} from './app/chemvas/web/scene.mjs';
let raw = ''; for await (const chunk of process.stdin) raw += chunk;
const {policy, cases} = JSON.parse(raw);
console.log(JSON.stringify(cases.map(([zoom, delta]) => {
  const view = wheelView({x: 0, y: 0, width: 800 / zoom, height: 600 / zoom},
    {width: 800, height: 600}, {deltaX: 0, deltaY: delta, deltaMode: 0, ctrlKey: true, position: {x: 100, y: 100}}, policy, 18);
  return 800 / view.width;
})));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        input=json.dumps({"policy": ui_spec()["navigation"], "cases": cases}),
        text=True,
        capture_output=True,
        check=True,
    )
    for (zoom, delta), browser_zoom in zip(
        cases, json.loads(result.stdout), strict=True
    ):
        set_zoom_for(desktop_canvas, zoom)
        event = _FakeWheelEvent(
            QPoint(0, 0),
            QPoint(0, int(-delta * 2)),
            Qt.KeyboardModifier.ControlModifier,
        )
        CanvasView.wheelEvent(desktop_canvas, event)
        assert browser_zoom == pytest.approx(
            desktop_canvas.runtime_state.input_view_state.zoom
        )


@pytest.mark.parametrize("size", [1, 5, 10, 12, 24, 48])
def test_browser_font_pixels_match_pinned_native_font(size, desktop_canvas):
    from PyQt6.QtGui import QFont, QRawFont

    from chemvas.bootstrap.web_adapter import browser_font_pixels

    font = QFont("Arial")
    for point_size in (size, size * 0.72):
        font.setPointSizeF(max(1.0, point_size))
        raw_font = QRawFont.fromFont(font)
        assert raw_font.isValid(), (font.family(), point_size)
        assert browser_font_pixels(point_size) == raw_font.pixelSize()


@pytest.mark.parametrize(
    "invalid",
    [
        {"document": {}, "measurements": {}},
        {"size": True, "labels": [], "measurements": {}},
        {"size": 0, "labels": [], "measurements": {}},
        {"size": 12, "labels": "NH2", "measurements": {}},
        {"size": 12, "labels": [["NH2"]], "measurements": {}},
        {"size": 12, "labels": [["N", None, False, True]], "measurements": {}},
        {"size": 12, "labels": [["N", None, 0, None]], "measurements": {}},
    ],
)
def test_label_presentations_reject_invalid_shapes(invalid):
    from chemvas.bootstrap.web_adapter import place_browser_labels

    with pytest.raises(ValueError):
        place_browser_labels(invalid)


@pytest.mark.parametrize(
    "key", ["1", "2", "3", "b", "B", "w", "h", "H", "d", "D", "c", "l", "r"]
)
@pytest.mark.parametrize(
    ("style", "order"),
    [("single", 1), ("double", 2), ("bold_in", 2), ("double_either", 2)],
)
@pytest.mark.parametrize("dy", [0, 6])
def test_browser_bond_shortcut_matches_native_hover(
    desktop_canvas, key, style, order, dy
):
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QKeyEvent

    from tests.runtime_services import shortcut_service_for

    source = draw_bond(new_document(), start=(100, 100), end=(120, 100))["document"][
        "state"
    ]
    source["model"]["bonds"][0].update(style=style, order=order)
    canvas = desktop_canvas
    session = canvas.services.canvas_document_session_service
    session.apply_state(source)
    service = shortcut_service_for(
        canvas,
        scene_transform_controller=canvas.services.scene_transform_controller,
        tool_mode_controller=canvas.services.tool_mode_controller,
    )
    errors = []
    service._notify_error = errors.append
    hit = canvas.services.selection.preferred_structure_hit_at_scene_pos(
        QPointF(110, 100 + dy)
    )
    assert hit is not None and hit.kind == "bond"
    service.handle_bond_hotkey(
        QKeyEvent(
            QEvent.Type.KeyPress,
            ord(key.upper()),
            Qt.KeyboardModifier.ShiftModifier
            if key.isupper()
            else Qt.KeyboardModifier.NoModifier,
            key,
        ),
        hit.id,
    )
    candidate = deepcopy(source)
    adapter = BrowserStructureAdapter(candidate)
    if errors:
        with pytest.raises(ValueError, match="unknown double-bond stereo"):
            adapter.apply_hover_shortcut(110, 100 + dy, key)
        assert candidate == source
    else:
        adapter.apply_hover_shortcut(110, 100 + dy, key)
        assert candidate["model"] == session.snapshot_state()["model"]


def test_browser_shortcut_has_one_history_entry_and_no_hit_is_noop():
    session = BrowserSession()
    source = draw_bond(new_document(), start=(100, 100), end=(120, 100))["document"]
    session.dispatch({"revision": 0, "action": "load", "document": source})
    for revision, point in [(1, (200, 100)), (2, (200, 200))]:
        unchanged = session.dispatch(
            {
                "revision": revision,
                "action": "edit",
                "edit": {
                    "kind": "hover_shortcut",
                    "x": point[0],
                    "y": point[1],
                    "key": "2",
                },
            }
        )
        assert unchanged["document"] == source
        assert not unchanged["can_undo"]
    result = session.dispatch(
        {
            "revision": 3,
            "action": "edit",
            "edit": {"kind": "hover_shortcut", "x": 110, "y": 104, "key": "2"},
        }
    )
    assert result["document"]["state"]["model"]["bonds"][0]["order"] == 2
    assert len(session.state.history) == 1
    assert session.dispatch({"revision": 4, "action": "undo"})["document"] == source
    assert (
        session.dispatch({"revision": 5, "action": "redo"})["document"]
        == result["document"]
    )
    with pytest.raises(ValueError, match="Unsupported hover shortcut"):
        edit_document(
            {
                "document": source,
                "edit": {
                    "kind": "hover_shortcut",
                    "x": 110,
                    "y": 100,
                    "key": "injected",
                },
            }
        )


@pytest.mark.parametrize("shape", ["bond", "benzene"])
@pytest.mark.parametrize(
    "target,key",
    [
        ("atom", key)
        for key in "0123456789azvufFpPAhbBir sSmnwNclCxo qdeEZMLOQHYkK".replace(" ", "")
    ]
    + [("bond", key) for key in "4567890a"],
)
def test_browser_hover_growth_and_labels_match_native(
    desktop_canvas, shape, target, key
):
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QKeyEvent

    from tests.runtime_services import shortcut_service_for

    payload = draw_bond(new_document(), start=(100, 100), end=(120, 100))["document"]
    if shape == "benzene":
        payload = edit_document(
            {"document": payload, "edit": {"kind": "ring", "x": 110, "y": 100}}
        )["document"]
    before = deepcopy(payload)
    source = payload["state"]
    canvas = desktop_canvas
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(source)
    shortcuts = shortcut_service_for(
        canvas,
        scene_transform_controller=canvas.services.scene_transform_controller,
        tool_mode_controller=canvas.services.tool_mode_controller,
    )
    x, y = (100, 100) if target == "atom" else (110, 100)
    hit = canvas.services.selection.preferred_structure_hit_at_scene_pos(QPointF(x, y))
    assert hit is not None and hit.kind == target
    event = QKeyEvent(
        QEvent.Type.KeyPress,
        ord(key.upper()),
        Qt.KeyboardModifier.ShiftModifier
        if key.isupper()
        else Qt.KeyboardModifier.NoModifier,
        key,
    )
    assert getattr(shortcuts, f"handle_{target}_hotkey")(event, hit.id)
    actual = edit_document(
        {
            "document": payload,
            "edit": {"kind": "hover_shortcut", "x": x, "y": y, "key": key},
        }
    )
    expected = documents.snapshot_state()
    assert actual["document"]["state"]["model"] == expected["model"]
    assert actual["document"]["state"]["ring_fills"] == expected["ring_fills"]
    assert actual["shortcut_tool"] is None
    assert payload == before


@pytest.mark.parametrize("target", ["atom", "bond", "empty"])
def test_hover_a_uses_native_growth_before_tool_fallback_and_history(target):
    session = BrowserSession()
    source = draw_bond(new_document(), start=(100, 100), end=(120, 100))["document"]
    session.dispatch({"revision": 0, "action": "load", "document": source})
    x, y = {"atom": (100, 100), "bond": (110, 100), "empty": (200, 200)}[target]
    result = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {"kind": "hover_shortcut", "x": x, "y": y, "key": "a"},
        }
    )
    if target == "empty":
        assert result["shortcut_tool"] == "text"
        assert result["document"] == source
        assert not result["dirty"] and not result["can_undo"]
    else:
        assert result["shortcut_tool"] is None
        assert len(result["document"]["state"]["model"]["atoms"]) == (
            7 if target == "atom" else 6
        )
        assert len(session.state.history) == 1
        assert session.dispatch({"revision": 2, "action": "undo"})["document"] == source
        assert (
            session.dispatch({"revision": 3, "action": "redo"})["document"]
            == result["document"]
        )
    assert "shortcut_tool" not in session.info
    assert session.dispatch({"action": "read"})["shortcut_tool"] is None


def test_hover_growth_failure_keeps_candidate_and_history_unpublished(monkeypatch):
    from chemvas.ui.molecule.structure_build_committer import StructureBuildCommitter

    session = BrowserSession()
    source = draw_bond(new_document(), start=(100, 100), end=(120, 100))["document"]
    session.dispatch({"revision": 0, "action": "load", "document": source})
    original = StructureBuildCommitter.add_bond

    def fail_after_bond(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError("interrupted growth")

    monkeypatch.setattr(StructureBuildCommitter, "add_bond", fail_after_bond)
    with pytest.raises(RuntimeError, match="interrupted growth"):
        session.dispatch(
            {
                "revision": 1,
                "action": "edit",
                "edit": {"kind": "hover_shortcut", "x": 100, "y": 100, "key": "2"},
            }
        )
    assert session.info["document"] == source
    assert session.revision == 1
    assert not session.state.history


def test_hover_growth_declined_after_mutation_discards_whole_candidate(monkeypatch):
    from chemvas.ui.molecule.structure_growth_build_service import (
        StructureGrowthBuildService,
    )

    def decline(self, atom_id, n):
        def action():
            self.actions.add_atom("O", 170, 100)
            return False

        self.actions.run_recorded_additions_action(action)

    monkeypatch.setattr(
        StructureGrowthBuildService, "sprout_regular_ring_from_atom", decline
    )
    session = BrowserSession()
    source = draw_bond(new_document(), start=(100, 100), end=(120, 100))["document"]
    session.dispatch({"revision": 0, "action": "load", "document": source})
    result = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {"kind": "hover_shortcut", "x": 100, "y": 100, "key": "6"},
        }
    )
    assert result["document"] == source
    assert not result["dirty"] and not result["can_undo"]
    assert result["shortcut_tool"] is None


@pytest.mark.parametrize("key", list("4567890a"))
def test_repeated_hover_fusion_matches_native_occupied_sides(desktop_canvas, key):
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent

    from tests.runtime_services import shortcut_service_for

    payload = draw_bond(new_document(), start=(100, 100), end=(120, 100))["document"]
    canvas = desktop_canvas
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(payload["state"])
    shortcuts = shortcut_service_for(
        canvas,
        scene_transform_controller=canvas.services.scene_transform_controller,
        tool_mode_controller=canvas.services.tool_mode_controller,
    )
    for _ in range(4):
        assert shortcuts.handle_bond_hotkey(
            QKeyEvent(
                QEvent.Type.KeyPress,
                ord(key.upper()),
                Qt.KeyboardModifier.NoModifier,
                key,
            ),
            0,
        )
        result = edit_document(
            {
                "document": payload,
                "edit": {"kind": "hover_shortcut", "x": 110, "y": 100, "key": key},
            }
        )
        payload = result["document"]
        expected = documents.snapshot_state()
        assert payload["state"]["model"] == expected["model"]
        assert payload["state"]["ring_fills"] == expected["ring_fills"]


@pytest.mark.parametrize(
    "element,explicit", [("C", False), ("C", True), ("N", True), ("Me", True)]
)
@pytest.mark.parametrize(
    "text,accept",
    [(" NH2 ", True), ("  ", True), ("C", True), ("OMe", True), ("ignored", False)],
)
def test_browser_enter_prompt_matches_native(
    desktop_canvas, monkeypatch, element, explicit, text, accept
):
    from PyQt6.QtWidgets import QInputDialog

    payload = draw_bond(new_document(), start=(100, 100), end=(120, 100))["document"]
    payload["state"]["model"]["atoms"][0].update(
        element=element, explicit_label=explicit
    )
    canvas = desktop_canvas
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(payload["state"])
    initial = []

    def dialog(*args, **kwargs):
        initial.append(kwargs["text"])
        return text, accept

    monkeypatch.setattr(QInputDialog, "getText", dialog)
    canvas.services.atom_label_service.prompt_atom_label(0)
    plan = atom_input_plan(
        {
            "document": payload,
            "symbol": "O",
            "edit": {"kind": "atom_prompt", "x": 100, "y": 100},
        }
    )
    assert plan["needs_prompt"] and plan["atom_id"] == 0
    assert plan["initial"] == initial[0]
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": payload})
    if accept:
        result = session.dispatch(
            {
                "revision": 1,
                "action": "edit",
                "edit": {
                    "kind": "atom_prompt",
                    "atom_id": plan["atom_id"],
                    "x": 100,
                    "y": 100,
                    "text": text,
                },
            }
        )
        assert (
            result["document"]["state"]["model"] == documents.snapshot_state()["model"]
        )
        assert len(session.state.history) == int(result["document"] != payload)
        if result["can_undo"]:
            assert (
                session.dispatch({"revision": 2, "action": "undo"})["document"]
                == payload
            )
            assert (
                session.dispatch({"revision": 3, "action": "redo"})["document"]
                == result["document"]
            )
    else:
        assert session.info["document"] == payload
        assert documents.snapshot_state()["model"] == payload["state"]["model"]
        assert not session.state.history


@pytest.mark.parametrize("position", [(110, 100), (200, 200)])
def test_enter_prompt_does_not_target_bonds_or_empty_space(position):
    payload = draw_bond(new_document(), start=(100, 100), end=(120, 100))["document"]
    plan = atom_input_plan(
        {
            "document": payload,
            "symbol": "C",
            "edit": {"kind": "atom_prompt", "x": position[0], "y": position[1]},
        }
    )
    assert not plan["needs_prompt"] and plan["text"] is None
    assert plan["atom_id"] is None


@pytest.mark.parametrize("shape", ["bond", "lone", "ring"])
@pytest.mark.parametrize(
    "element,explicit", [("C", False), ("C", True), ("N", True), ("Cl", True)]
)
@pytest.mark.parametrize("target", ["atom", "bond", "empty"])
def test_browser_hover_delete_matches_native_input(
    desktop_canvas, monkeypatch, shape, element, explicit, target
):
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QKeyEvent

    from chemvas.ui.canvas import canvas_input_controller

    source = new_document()
    source["state"]["settings"]["bond_length_px"] = 40
    payload = draw_bond(source, start=(100, 100), end=(140, 100))["document"]
    if shape == "ring":
        payload = edit_document(
            {"document": payload, "edit": {"kind": "ring", "x": 120, "y": 100}}
        )["document"]
    elif shape == "lone":
        payload["state"]["model"]["atoms"].pop(1)
        payload["state"]["model"]["bonds"] = []
    payload["state"]["model"]["atoms"][0].update(
        element=element, explicit_label=explicit
    )
    canvas = desktop_canvas
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(payload["state"])
    x, y = {"atom": (100, 100), "bond": (120, 100), "empty": (250, 250)}[target]

    def hover():
        hit = canvas.services.selection.preferred_structure_hit_at_scene_pos(
            QPointF(x, y)
        )
        canvas.runtime_state.hover_preview_state.atom_id = (
            hit.id if hit and hit.kind == "atom" else None
        )
        canvas.runtime_state.hover_preview_state.bond_id = (
            hit.id if hit and hit.kind == "bond" else None
        )

    monkeypatch.setattr(canvas.services.hover, "refresh", hover)
    monkeypatch.setattr(
        canvas_input_controller,
        "scene_pos_from_global_pos_for",
        lambda *_: QPointF(x, y),
    )
    canvas.services.input_controller.key_press_event(
        QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier
        )
    )
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": payload})
    result = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {"kind": "delete_hover", "x": x, "y": y},
        }
    )
    expected = documents.snapshot_state()
    assert result["document"]["state"]["model"] == expected["model"]
    assert result["document"]["state"]["ring_fills"] == expected["ring_fills"]
    assert len(session.state.history) == int(result["document"] != payload)
    if result["can_undo"]:
        assert (
            session.dispatch({"revision": 2, "action": "undo"})["document"] == payload
        )
        assert (
            session.dispatch({"revision": 3, "action": "redo"})["document"]
            == result["document"]
        )


@pytest.mark.parametrize("key_name", ["Key_Delete", "Key_Backspace"])
def test_native_selection_delete_precedes_hover_label_clear(
    desktop_canvas, monkeypatch, key_name
):
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QKeyEvent

    from chemvas.ui.canvas import canvas_input_controller

    payload = draw_bond(new_document(), start=(100, 100), end=(120, 100))["document"]
    payload["state"]["model"]["atoms"][0].update(element="N", explicit_label=True)
    canvas = desktop_canvas
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(payload["state"])
    canvas.runtime_state.atom_graphics_state.atom_items[0].setSelected(True)

    def hover():
        canvas.runtime_state.hover_preview_state.atom_id = 0
        canvas.runtime_state.hover_preview_state.bond_id = None

    monkeypatch.setattr(canvas.services.hover, "refresh", hover)
    monkeypatch.setattr(
        canvas_input_controller,
        "scene_pos_from_global_pos_for",
        lambda *_: QPointF(100, 100),
    )
    canvas.services.input_controller.key_press_event(
        QKeyEvent(
            QEvent.Type.KeyPress,
            getattr(Qt.Key, key_name),
            Qt.KeyboardModifier.NoModifier,
        )
    )
    result = edit_document(
        {
            "document": payload,
            "edit": {
                "kind": "delete_selection",
                "selection": [{"target": "atom", "id": 0}],
            },
        }
    )
    assert result["document"]["state"]["model"] == documents.snapshot_state()["model"]
    assert not result["document"]["state"]["model"]["atoms"]


@pytest.mark.parametrize(
    "position", [(float("nan"), 100), (100, float("inf")), (True, 100), ("100", 100)]
)
def test_prompt_scene_position_rejects_invalid_coordinates(position):
    with pytest.raises(ValueError, match="finite"):
        atom_input_plan(
            {
                "document": new_document(),
                "symbol": "",
                "edit": {"kind": "atom_prompt", "x": position[0], "y": position[1]},
            }
        )


def test_prompt_edit_missing_atom_does_not_consume_history():
    session = BrowserSession()
    before = deepcopy(session.info)
    with pytest.raises(ValueError, match="no longer exists"):
        session.dispatch(
            {
                "revision": 0,
                "action": "edit",
                "edit": {
                    "kind": "atom_prompt",
                    "atom_id": 42,
                    "x": 100,
                    "y": 100,
                    "text": "N",
                },
            }
        )
    assert session.info == before and session.revision == 0
    assert not session.state.history


@pytest.mark.parametrize(
    "size,orientation,custom",
    [
        ("A4", "landscape", None),
        ("A4", "portrait", None),
        ("A3", "landscape", None),
        ("Letter", "portrait", None),
        ("Custom", "landscape", (300, 180)),
        ("Custom", "portrait", (180, 300)),
    ],
)
def test_browser_sheet_matches_native_rectangle(
    desktop_canvas, size, orientation, custom
):
    from PyQt6.QtCore import QPointF

    from chemvas.ui.canvas.sheet_setup_access import (
        scene_pos_in_sheet_for,
        sheet_rect_for,
    )

    payload = new_document()
    settings = payload["state"]["settings"]
    settings.update(sheet_size=size, sheet_orientation=orientation)
    if custom:
        settings["sheet_custom_size_mm"] = list(custom)
    canvas = desktop_canvas
    canvas.services.canvas_document_session_service.apply_state(payload["state"])
    rect = sheet_rect_for(canvas)
    info = document_info(payload)
    assert info["sheet"] == [rect.width(), rect.height()]
    adapter = BrowserStructureAdapter(extract_document_state(info["document"]))
    for x, y in [
        (0, 0),
        (-100, -100),
        (-200, -200),
        (rect.left(), rect.top()),
        (rect.right(), rect.bottom()),
        (rect.left() - 0.001, 0),
        (rect.right() + 0.001, 0),
        (0, rect.top() - 0.001),
        (0, rect.bottom() + 0.001),
    ]:
        if scene_pos_in_sheet_for(canvas, QPointF(x, y)):
            adapter.require_sheet_position(x, y)
        else:
            with pytest.raises(ValueError, match="inside the sheet"):
                adapter.require_sheet_position(x, y)


@pytest.mark.parametrize(
    "kind",
    [
        "bond_start",
        "bond_end",
        "ring",
        "atom",
        "hover_shortcut",
        "delete_hover",
        "atom_prompt",
    ],
)
def test_offsheet_browser_edits_leave_document_revision_and_history_unchanged(kind):
    payload = draw_bond(new_document(), start=(100, 100), end=(120, 100))["document"]
    for atom in payload["state"]["model"]["atoms"].values():
        atom["x"] += 1000
    edits = {
        "bond_start": {
            "kind": "bond",
            "start": [1100, 100],
            "end": [100, 100],
            "style": "single",
        },
        "bond_end": {
            "kind": "bond",
            "start": [100, 100],
            "end": [1100, 100],
            "style": "single",
        },
        "ring": {"kind": "ring", "x": 1100, "y": 100},
        "atom": {"kind": "atom", "x": 1100, "y": 100, "text": "N", "atom_id": 0},
        "hover_shortcut": {"kind": "hover_shortcut", "x": 1100, "y": 100, "key": "n"},
        "delete_hover": {"kind": "delete_hover", "x": 1100, "y": 100},
        "atom_prompt": {
            "kind": "atom_prompt",
            "x": 1100,
            "y": 100,
            "atom_id": 0,
            "text": "N",
        },
    }
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": payload})
    before = deepcopy(session.info)
    with pytest.raises(ValueError, match="inside the sheet"):
        session.dispatch({"revision": 1, "action": "edit", "edit": edits[kind]})
    assert session.info == before and session.revision == 1
    assert not session.state.history
    if kind in {"atom", "atom_prompt"}:
        plan_edit = {"kind": kind, "x": 1100, "y": 100}
        with pytest.raises(ValueError, match="inside the sheet"):
            atom_input_plan({"document": payload, "edit": plan_edit, "symbol": "N"})


def test_offsheet_empty_hover_and_selection_recovery_remain_available():
    session = BrowserSession()
    payload = draw_bond(new_document())["document"]
    session.dispatch({"revision": 0, "action": "load", "document": payload})
    moved = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {
                "kind": "move",
                "selection": [{"target": "bond", "id": 0}],
                "dx": 1000,
                "dy": 0,
            },
        }
    )
    assert moved["document"]["state"]["model"]["atoms"][0]["x"] == 1030
    for kind in ("delete_hover", "hover_shortcut", "atom_prompt"):
        change = {"kind": kind, "x": 2000, "y": 1000}
        if kind == "atom_prompt":
            assert not atom_input_plan(
                {"document": moved["document"], "edit": change, "symbol": ""}
            )["needs_prompt"]
        else:
            if kind == "hover_shortcut":
                change["key"] = "x"
            result = edit_document({"document": moved["document"], "edit": change})
            assert result["document"] == moved["document"]
            if kind == "hover_shortcut":
                assert result["shortcut_tool"] == "bond"
    deleted = session.dispatch(
        {
            "revision": 2,
            "action": "edit",
            "edit": {
                "kind": "delete_selection",
                "selection": [{"target": "bond", "id": 0}],
            },
        }
    )
    assert not deleted["document"]["state"]["model"]["atoms"]
    assert (
        session.dispatch({"revision": 3, "action": "undo"})["document"]
        == moved["document"]
    )
    assert session.dispatch({"revision": 4, "action": "undo"})["document"] == payload


@pytest.mark.parametrize(
    "kind,key_name,text,x",
    [
        ("hover_shortcut", "Key_N", "n", 1100),
        ("hover_shortcut", "Key_2", "2", 1120),
        ("delete_hover", "Key_Delete", "", 1100),
        ("atom_prompt", "Key_Return", "", 1100),
    ],
)
def test_offsheet_hover_refusal_matches_native_input(
    desktop_canvas, monkeypatch, kind, key_name, text, x
):
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QKeyEvent

    from chemvas.ui.canvas import canvas_input_controller

    payload = new_document()
    payload["state"]["settings"]["bond_length_px"] = 40
    payload = draw_bond(payload, start=(100, 100), end=(140, 100))["document"]
    for atom in payload["state"]["model"]["atoms"].values():
        atom["x"] += 1000
    canvas = desktop_canvas
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(payload["state"])
    before = documents.snapshot_state()
    notices = []
    monkeypatch.setattr(
        canvas_input_controller,
        "notify_error_for",
        lambda _, message: notices.append(message),
    )
    monkeypatch.setattr(
        canvas_input_controller,
        "scene_pos_from_global_pos_for",
        lambda *_: QPointF(x, 100),
    )
    monkeypatch.setattr(canvas.services.hover, "refresh", lambda: None)
    event = QKeyEvent(
        QEvent.Type.KeyPress,
        getattr(Qt.Key, key_name),
        Qt.KeyboardModifier.NoModifier,
        text,
    )
    canvas.services.input_controller.key_press_event(event)
    assert len(notices) == 1 and "inside the sheet" in notices[0]
    assert documents.snapshot_state() == before
    change = {"kind": kind, "x": x, "y": 100}
    if kind == "hover_shortcut":
        change["key"] = text
    with pytest.raises(ValueError) as error:
        if kind == "atom_prompt":
            atom_input_plan({"document": payload, "edit": change, "symbol": ""})
        else:
            edit_document({"document": payload, "edit": change})
    assert str(error.value) == notices[0]


@pytest.mark.parametrize("label", ["O", "Cl", "NH2", "CO2Me"])
@pytest.mark.parametrize("length,angle", [(20, 0), (40, 45), (40, 90)])
@pytest.mark.parametrize(
    "style", ["single", "double", "triple", "wedge", "hash", "bold_in"]
)
def test_measured_label_clipping_matches_native_planner(
    desktop_canvas, label, length, angle, style
):
    import math

    from PyQt6.QtGui import QTransform
    from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsPolygonItem

    from chemvas.bootstrap.web_adapter import drawing_geometry

    payload = new_document()
    payload["state"]["settings"]["bond_length_px"] = length
    payload = draw_bond(
        payload, start=(100, 100), end=(100 + length, 100), style=style
    )["document"]
    model = payload["state"]["model"]
    model["atoms"][1].update(
        x=100 + length * math.cos(math.radians(angle)),
        y=100 + length * math.sin(math.radians(angle)),
        element=label,
        explicit_label=True,
    )
    canvas = desktop_canvas
    canvas.services.canvas_document_session_service.apply_state(payload["state"])
    item = canvas.runtime_state.atom_graphics_state.atom_items[1]
    path = item.mapToScene(item.glyph_path())
    points = [
        (p.x() / 64, p.y() / 64)
        for polygon in path.toSubpathPolygons(QTransform.fromScale(64, 64))
        for p in polygon
    ]
    drawing = drawing_geometry(extract_document_state(payload), {1: points})
    native = canvas.runtime_state.bond_graphics_state.bond_items[0]
    actual = drawing["bonds"]["0"]
    assert len(actual) == len(native)
    for primitive, qt_item in zip(actual, native, strict=True):
        if isinstance(qt_item, QGraphicsLineItem):
            line = qt_item.line()
            assert primitive["line"] == pytest.approx(
                (line.x1(), line.y1(), line.x2(), line.y2()), abs=0.03
            )
        elif isinstance(qt_item, QGraphicsPolygonItem):
            polygon = qt_item.polygon()
            assert len(primitive["polygon"]) == polygon.size()
            for point, expected in zip(primitive["polygon"], polygon, strict=True):
                assert point == pytest.approx((expected.x(), expected.y()), abs=0.03)
        else:
            pytest.fail(f"Unexpected native primitive: {type(qt_item)}")


def font_measurements_for(payload):
    spec = document_info(payload)["drawing"]["label_measurements"]
    return {
        "family": spec["family"],
        "metrics": {
            q["key"]: {
                "width": 8,
                "ascent": 12,
                "descent": 4,
                "cap_height": 11,
                "line_height": 18,
            }
            for q in spec["queries"]
        },
        "ink": {
            f"{q['pixels']}:{q['text']}": [[-4, -6], [4, -6], [4, 6], [-4, 6]]
            for q in spec["queries"]
        },
    }


@pytest.fixture
def measured_label_request():
    payload = draw_bond(new_document(), start=(100, 100), end=(120, 100))["document"]
    payload["state"]["model"]["atoms"][1].update(element="O", explicit_label=True)
    return {"document": payload, "font": font_measurements_for(payload)}


def test_measured_geometry_is_read_only_and_uses_ink_size(
    server, measured_label_request
):
    source = measured_label_request
    before = deepcopy(source)
    status, body, _ = request(
        server,
        "/api/session",
        method="POST",
        body=json.dumps(
            {"revision": 0, "action": "load", "document": source["document"]}
        ),
    )
    assert status == 200
    loaded = json.loads(body)
    assert loaded["drawing"]["needs_measurements"]
    status, body, _ = request(
        server,
        "/api/session",
        method="POST",
        body=json.dumps(
            {
                "session": loaded["session"],
                "revision": loaded["revision"],
                "action": "measure",
                "font": source["font"],
            }
        ),
    )
    assert status == 200
    measured = json.loads(body)
    narrow = measured["drawing"]["bonds"]["0"][0]["line"]
    source["font"]["ink"]["16:O"] = [
        [x * 2, y] for x, y in source["font"]["ink"]["16:O"]
    ]
    wide = document_info(
        source["document"], font=BrowserFontMeasurements(source["font"])
    )["drawing"]["bonds"]["0"][0]["line"]
    assert wide[2] == pytest.approx(narrow[2] - 4)
    assert wide[2] < narrow[2] < 116
    assert measured["document"] == json.loads(json.dumps(before["document"]))
    assert measured["revision"] == loaded["revision"]
    assert not measured["dirty"] and not measured["can_undo"]


@pytest.mark.parametrize(
    "invalid",
    [
        "missing_metrics",
        "missing_ink",
        "nan",
        "boolean",
        "too_many",
        "bad_metric",
        "extra_field",
        "wrong_font",
        "too_many_glyphs",
        "long_key",
    ],
)
def test_measured_geometry_rejects_bad_measurements(
    server, measured_label_request, invalid
):
    source = measured_label_request
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source["document"]})
    server.sessions["font-test"] = session
    font = source["font"]
    if invalid == "missing_metrics":
        font["metrics"] = {}
    elif invalid == "missing_ink":
        font["ink"] = {}
    elif invalid == "nan":
        font["ink"]["16:O"][0][0] = float("nan")
    elif invalid == "boolean":
        font["ink"]["16:O"][0][0] = True
    elif invalid == "too_many":
        font["ink"]["16:O"] = [[0, 0]] * 4097
    elif invalid == "bad_metric":
        font["metrics"]["12:O"]["ascent"] = 0
    elif invalid == "wrong_font":
        font["family"] = "other"
    elif invalid == "too_many_glyphs":
        font["ink"] = {str(i): [] for i in range(8193)}
    elif invalid == "long_key":
        font["ink"]["x" * 301] = []
    else:
        font["unexpected"] = 1
    before, original_font = deepcopy(session.info), session.font
    assert (
        request(
            server,
            "/api/session",
            method="POST",
            body=json.dumps(
                {
                    "session": "font-test",
                    "revision": 1,
                    "action": "measure",
                    "font": font,
                }
            ),
        )[0]
        == 400
    )
    assert session.info == before and session.font is original_font
    assert session.revision == 1 and not session.state.history


def test_overlapping_label_ink_suppresses_bond(measured_label_request):
    source = measured_label_request
    source["font"]["ink"]["16:O"] = [[-30, -8], [30, -8], [30, 8], [-30, 8]]
    drawing = document_info(
        source["document"], font=BrowserFontMeasurements(source["font"])
    )["drawing"]
    for primitive in drawing["bonds"]["0"]:
        if "line" in primitive:
            x1, y1, x2, y2 = primitive["line"]
            assert (x1, y1) == (x2, y2)


@pytest.mark.parametrize("length", [20, 40])
@pytest.mark.parametrize(
    "case",
    [
        "competing_atom",
        "near_atom",
        "near_bond",
        "fallback_bond",
        "fallback_atom",
        "empty",
        "label_gap",
    ],
)
def test_atom_tool_target_matches_native_hover_and_press(
    desktop_canvas, monkeypatch, length, case
):
    from types import SimpleNamespace

    from PyQt6.QtCore import QPointF, Qt

    canvas = desktop_canvas
    documents = canvas.services.canvas_document_session_service
    source = new_document()["state"]
    source["settings"]["bond_length_px"] = length
    documents.apply_state(source)
    mutation = canvas.services.canvas_atom_mutation_service
    a = mutation.add_atom("C", 100, 100)
    b = mutation.add_atom("C", 100 + length, 100)
    canvas.services.canvas_bond_mutation_service.add_bond(a, b, 1)
    extra = canvas.services.atom_label_service.add_labelled_atom(
        "CO2Me" if case == "label_gap" else "N", 100 + length / 2, 100 + length * 0.6
    )
    offsets = {
        "competing_atom": (0.5, 0.49),
        "near_atom": (-0.25, 0),
        "near_bond": (0.5, -0.275),
        "fallback_bond": (0.5, -0.5),
        "fallback_atom": (0.5, 1.35),
        "empty": (3, 3),
    }
    direct_atom_id = None
    if case == "label_gap":
        item = canvas.runtime_state.atom_graphics_state.atom_items[extra]
        bounds = item.mapToScene(item.glyph_path()).boundingRect()
        # Empty ink near a box corner is still part of AtomLabelItem.shape.
        pos = QPointF(bounds.right() - 0.1, bounds.top() + 0.1)
        assert item.contains(item.mapFromScene(pos))
        direct_atom_id = extra
    else:
        dx, dy = offsets[case]
        pos = QPointF(100 + length * dx, 100 + length * dy)
    before = build_document_payload(documents.snapshot_state(), 9)
    change = {
        "kind": "atom",
        "x": pos.x(),
        "y": pos.y(),
        "text": "F",
        "atom_id": direct_atom_id,
    }
    changed = edit_document({"document": before, "edit": change})
    canvas.services.hover.update_hover_highlight(pos)
    if case == "competing_atom":
        assert canvas.runtime_state.hover_preview_state.atom_id == extra
    tool = canvas.services.tool_controller.tools["text"]
    monkeypatch.setattr(tool.context, "current_atom_symbol", lambda: "F")
    monkeypatch.setattr(
        tool.context.hit_testing_service, "_scene_pos_mapper", lambda event: pos
    )
    assert tool.on_mouse_press(
        SimpleNamespace(button=lambda: Qt.MouseButton.LeftButton)
    )
    assert changed["document"]["state"]["model"] == documents.snapshot_state()["model"]
    plan = atom_input_plan({"document": before, "edit": change, "symbol": ""})
    if case in {"competing_atom", "fallback_atom", "label_gap"}:
        assert plan["initial"] == ("CO2Me" if case == "label_gap" else "N")
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": before})
    session.dispatch({"revision": 1, "action": "edit", "edit": change})
    assert session.dispatch({"revision": 2, "action": "undo"})["document"] == before
    assert (
        session.dispatch({"revision": 3, "action": "redo"})["document"]
        == changed["document"]
    )


def test_measured_hit_rectangle_covers_all_runs_without_bond_clearance(
    measured_label_request,
):
    source = measured_label_request
    source["document"]["state"]["model"]["atoms"][1]["element"] = "NH2"
    font = font_measurements_for(source["document"])
    drawing = document_info(source["document"], font=BrowserFontMeasurements(font))[
        "drawing"
    ]
    runs = drawing["atom_layouts"]["1"]
    assert [run["text"] for run in runs] == ["NH", "2"]
    left, top, width, height = drawing["atom_hit_rects"]["1"]
    assert left == pytest.approx(min(run["x"] for run in runs) - 4)
    assert top == pytest.approx(min(run["y"] for run in runs) - 6)
    assert left + width == pytest.approx(max(run["x"] for run in runs) + 4)
    assert top + height == pytest.approx(max(run["y"] for run in runs) + 6)
    font["ink"] = {key: [] for key in font["ink"]}
    assert not document_info(source["document"], font=BrowserFontMeasurements(font))[
        "drawing"
    ]["atom_hit_rects"]


def test_known_font_preview_edit_and_history_render_once(
    monkeypatch, measured_label_request
):
    from chemvas.bootstrap import web_adapter

    source = measured_label_request
    session = BrowserSession()
    calls = []
    draw = web_adapter.drawing_geometry
    monkeypatch.setattr(
        web_adapter,
        "drawing_geometry",
        lambda *args: (calls.append(args), draw(*args))[1],
    )
    loaded = session.dispatch(
        {"revision": 0, "action": "load", "document": source["document"]}
    )
    assert loaded["drawing"]["needs_measurements"] and not calls
    measured = session.dispatch(
        {"revision": 1, "action": "measure", "font": source["font"]}
    )
    assert len(calls) == 1 and measured["revision"] == 1
    assert not session.state.history
    cached_font = session.font
    before = deepcopy(session.info)
    move = {
        "kind": "move",
        "selection": [{"target": "bond", "id": 0}],
        "dx": 20,
        "dy": 10,
    }
    preview = session.dispatch({"revision": 1, "action": "preview", "edit": move})
    assert len(calls) == 2
    assert preview["revision"] == 1 and session.info == before
    assert not preview["can_undo"] and not preview["dirty"]
    changed = session.dispatch({"revision": 1, "action": "edit", "edit": move})
    assert len(calls) == 3
    assert preview["drawing"] == changed["drawing"]
    assert preview["document"] == changed["document"]
    assert len(session.state.history) == 1
    assert {"drawing", "font", "metrics", "ink"}.isdisjoint(
        session.state.history[0].before
    )
    undone = session.dispatch({"revision": 2, "action": "undo"})
    assert len(calls) == 4 and undone["document"] == source["document"]
    redone = session.dispatch({"revision": 3, "action": "redo"})
    assert len(calls) == 5 and redone["drawing"] == changed["drawing"]
    session.dispatch({"action": "read"})
    assert len(calls) == 5 and session.font is cached_font
    for old, new in zip(
        measured["drawing"]["atom_layouts"]["1"],
        changed["drawing"]["atom_layouts"]["1"],
        strict=True,
    ):
        assert (new["x"], new["y"]) == pytest.approx((old["x"] + 20, old["y"] + 10))


def test_preview_font_registration_does_not_publish_candidate(measured_label_request):
    source = measured_label_request
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source["document"]})
    session.dispatch({"revision": 1, "action": "measure", "font": source["font"]})
    before = deepcopy(session.info)
    change = {"kind": "atom", "x": 120, "y": 100, "text": "Cl"}
    preview = session.dispatch({"revision": 1, "action": "preview", "edit": change})
    assert preview["drawing"]["needs_measurements"]
    font = font_measurements_for(preview["document"])
    painted = session.dispatch(
        {"revision": 1, "action": "measure", "font": font, "edit": change}
    )
    assert "atom_layouts" in painted["drawing"] and not painted["can_undo"]
    assert session.info == before and session.revision == 1
    assert "16:O" not in session.font.ink  # Replacement bounds retained font data.
    font["metrics"].clear()
    font["ink"].clear()
    committed = session.dispatch({"revision": 1, "action": "edit", "edit": change})
    assert committed["drawing"] == painted["drawing"]
    undone = session.dispatch({"revision": 2, "action": "undo"})
    assert undone["drawing"]["needs_measurements"]
    assert undone["document"] == source["document"]
    session.dispatch({"revision": 3, "action": "measure", "font": source["font"]})
    assert session.state.redo_stack and not session.state.history


@pytest.mark.parametrize("preview", [False, True])
def test_failed_font_render_preserves_session_and_font(
    monkeypatch, measured_label_request, preview
):
    from chemvas.bootstrap import web_adapter

    session = BrowserSession()
    session.dispatch(
        {
            "revision": 0,
            "action": "load",
            "document": measured_label_request["document"],
        }
    )
    before, font = deepcopy(session.info), session.font

    def fail(*args):
        raise ValueError("injected rendering failure")

    monkeypatch.setattr(web_adapter, "drawing_geometry", fail)
    change = {
        "kind": "move",
        "selection": [{"target": "bond", "id": 0}],
        "dx": 1,
        "dy": 2,
    }
    with pytest.raises(ValueError, match="injected"):
        session.dispatch(
            {
                "revision": 1,
                "action": "measure",
                "font": measured_label_request["font"],
                **({"edit": change} if preview else {}),
            }
        )
    assert session.info == before and session.font is font
    assert session.revision == 1 and not session.state.history


def test_http_font_and_preview_requests_are_revision_bound_and_session_local(
    server, measured_label_request
):
    loaded = []
    for _ in range(2):
        status, body, _ = request(
            server,
            "/api/session",
            method="POST",
            body=json.dumps(
                {
                    "revision": 0,
                    "action": "load",
                    "document": measured_label_request["document"],
                }
            ),
        )
        assert status == 200
        loaded.append(json.loads(body))
    a, b = loaded
    for action in ["measure", "preview"]:
        payload = {
            "session": a["session"],
            "revision": 0,
            "action": action,
            **(
                {"font": measured_label_request["font"]}
                if action == "measure"
                else {"edit": {}}
            ),
        }
        assert (
            request(server, "/api/session", method="POST", body=json.dumps(payload))[0]
            == 409
        )
    measure = {
        "session": a["session"],
        "revision": 1,
        "action": "measure",
        "font": measured_label_request["font"],
    }
    assert (
        request(server, "/api/session", method="POST", body=json.dumps(measure))[0]
        == 200
    )
    assert server.sessions[b["session"]].info["drawing"]["needs_measurements"]
    assert not server.sessions[b["session"]].font.ink
    for action in ["measure", "preview"]:
        payload = {
            **measure,
            "action": action,
            "document": measured_label_request["document"],
        }
        assert (
            request(server, "/api/session", method="POST", body=json.dumps(payload))[0]
            == 400
        )
    for path in ["/api/drawing", "/api/labels", "/api/preview"]:
        assert request(server, path, method="POST", body="{}")[0] == 404


def test_browser_font_rejects_placed_coordinate_overflow_even_with_empty_ink(
    measured_label_request,
):
    source = measured_label_request
    source["document"]["state"]["model"]["atoms"][1]["element"] = "NH2"
    font = font_measurements_for(source["document"])
    for metric in font["metrics"].values():
        metric["width"] = 1.7e308
    font["ink"] = {key: [] for key in font["ink"]}
    with pytest.raises(ValueError, match="overflowed"):
        document_info(source["document"], font=BrowserFontMeasurements(font))


@pytest.mark.parametrize("length", [20, 40])
@pytest.mark.parametrize(
    "label,explicit,compact",
    [
        ("C", False, True),
        ("C", True, True),
        ("N", True, True),
        ("O", True, True),
        ("Cl", True, True),
        ("Br", True, True),
        ("Ph", True, True),
        ("NH2", True, False),
        ("OMe", True, False),
        ("CO2Me", True, False),
        ("t-Bu", True, False),
    ],
)
def test_browser_anchor_circle_matches_actual_native_label_item(
    desktop_canvas, length, label, explicit, compact
):
    payload = new_document()
    payload["state"]["settings"]["bond_length_px"] = length
    payload = draw_bond(payload, start=(100, 100), end=(100 + length, 100))["document"]
    payload["state"]["model"]["atoms"][0].update(element=label, explicit_label=explicit)
    canvas = desktop_canvas
    canvas.services.canvas_document_session_service.apply_state(payload["state"])
    radius = document_info(payload)["drawing"]["atom_hit_radii"]["0"]
    assert radius == (pytest.approx(length * 0.32) if compact else None)
    if explicit or label != "C":
        native = canvas.runtime_state.atom_graphics_state.atom_items[0]
        assert radius == native._hit_radius
    else:
        native = canvas.runtime_state.atom_graphics_state.atom_dots[0]
        assert native.shape().boundingRect().width() == pytest.approx(radius * 2)


@pytest.mark.parametrize("length", [20, 40])
@pytest.mark.parametrize("label", ["NH2", "CO2Me"])
@pytest.mark.parametrize(
    "key,kind",
    [
        ("n", "hover_shortcut"),
        ("3", "hover_shortcut"),
        ("a", "hover_shortcut"),
        ("Delete", "delete_hover"),
        ("Return", "atom_prompt"),
    ],
)
def test_extended_label_keyboard_target_matches_native_input(
    desktop_canvas, monkeypatch, length, label, key, kind
):
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QInputDialog

    from chemvas.ui.canvas import canvas_input_controller

    payload = new_document()
    payload["state"]["settings"]["bond_length_px"] = length
    payload = draw_bond(payload, start=(100, 100), end=(100 + length, 100))["document"]
    payload["state"]["model"]["atoms"][0].update(element=label, explicit_label=True)
    canvas = desktop_canvas
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(payload["state"])
    item = canvas.runtime_state.atom_graphics_state.atom_items[0]
    box = item.mapToScene(item.glyph_path()).boundingRect()
    pos = max(
        (
            QPointF(x, y)
            for x in [box.left() + 0.1, box.right() - 0.1]
            for y in [box.top() + 0.1, box.bottom() - 0.1]
        ),
        key=lambda p: (p.x() - 100) ** 2 + (p.y() - 100) ** 2,
    )
    assert item.contains(item.mapFromScene(pos))
    assert canvas.services.selection.preferred_structure_hit_at_scene_pos(pos).id == 0
    # This must exercise a glyph beyond the distance pick, not an atom-center test.
    assert (
        BrowserStructureAdapter(payload["state"]).find_atom_near(
            pos.x(), pos.y(), length * 0.32
        )
        is None
    )
    monkeypatch.setattr(
        canvas.services.hover,
        "refresh",
        lambda: canvas.services.hover.update_hover_highlight(pos),
    )
    monkeypatch.setattr(
        canvas_input_controller, "scene_pos_from_global_pos_for", lambda *_: pos
    )
    initial = []

    def dialog(*args, **kwargs):
        initial.append(kwargs["text"])
        return "F", True

    monkeypatch.setattr(QInputDialog, "getText", dialog)
    event_key = getattr(Qt.Key, f"Key_{key if len(key) > 1 else key.upper()}")
    canvas.services.input_controller.key_press_event(
        QKeyEvent(
            QEvent.Type.KeyPress,
            event_key,
            Qt.KeyboardModifier.NoModifier,
            key if len(key) == 1 else "",
        )
    )
    change = {"kind": kind, "x": pos.x(), "y": pos.y(), "atom_id": 0}
    if kind == "atom_prompt":
        plan = atom_input_plan({"document": payload, "edit": change, "symbol": "O"})
        assert plan["needs_prompt"] and plan["initial"] == initial[0] == label
        change["text"] = "F"
    elif kind == "hover_shortcut":
        change["key"] = key
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": payload})
    result = session.dispatch({"revision": 1, "action": "edit", "edit": change})
    expected = documents.snapshot_state()
    assert result["document"]["state"]["model"] == expected["model"]
    assert result["document"]["state"]["ring_fills"] == expected["ring_fills"]
    assert result["document"] != payload
    assert len(session.state.history) == 1
    assert session.dispatch({"revision": 2, "action": "undo"})["document"] == payload
    assert (
        session.dispatch({"revision": 3, "action": "redo"})["document"]
        == result["document"]
    )


@pytest.mark.parametrize("kind", ["hover_shortcut", "delete_hover", "atom_prompt"])
@pytest.mark.parametrize("atom_id", [True, -1, 999, 0.5, "0", {}])
def test_invalid_direct_keyboard_hit_keeps_document_and_history(kind, atom_id):
    session = BrowserSession()
    session.dispatch(
        {"revision": 0, "action": "edit", "edit": {"kind": "ring", "x": 100, "y": 100}}
    )
    before = deepcopy(session.info)
    change = {"kind": kind, "x": 100, "y": 100, "atom_id": atom_id}
    if kind == "hover_shortcut":
        change["key"] = "n"
    with pytest.raises(ValueError, match="Unknown atom hit target"):
        if kind == "atom_prompt":
            atom_input_plan(
                {"document": session.info["document"], "edit": change, "symbol": ""}
            )
        else:
            session.dispatch({"revision": 1, "action": "edit", "edit": change})
    assert session.info == before and session.revision == 1
    assert len(session.state.history) == 1


@pytest.mark.parametrize("kind", sorted(VALID_ARROW_KINDS))
@pytest.mark.parametrize("length", [20, 40])
@pytest.mark.parametrize("delta", [(0, 0), (60, 0), (0, -60), (-36, 48)])
def test_browser_arrow_paths_and_pens_match_native(desktop_canvas, kind, length, delta):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QPainterPath

    source = new_document()
    source["state"]["settings"].update(
        bond_length_px=length, arrow_line_width=2.5, arrow_head_scale=0.3
    )
    for mirrored in [False, True] if kind.startswith("equilibrium") else [False]:
        for control in [None, [19, -25]] if kind.startswith("curved_") else [None]:
            arrow = {
                "kind": kind,
                "start": [7, -11],
                "end": [7 + delta[0], -11 + delta[1]],
                "control": control,
                "double": kind == "curved_double",
                "color": "#123456",
            }
            if kind.startswith("equilibrium"):
                arrow["mirrored"] = mirrored
            source["state"]["arrows"] = [arrow]
            before = deepcopy(source)
            info = document_info(source)
            assert info["unsupported"] == []
            geometry = info["drawing"]["arrows"][0]
            desktop_canvas.services.canvas_document_session_service.apply_state(
                extract_document_state(source)
            )
            item = desktop_canvas.runtime_state.arrow_items()[0]
            path = QPainterPath()
            for command, coordinates in geometry["path"]:
                if command == "M":
                    path.moveTo(*coordinates)
                elif command == "L":
                    path.lineTo(*coordinates)
                else:
                    assert command == "Q"
                    path.quadTo(*coordinates)
            assert path == item.path()
            pen = item.pen()
            assert geometry["width"] == pen.widthF()
            assert geometry["color"] == pen.color().name()
            assert geometry["dashed"] == (pen.style() == Qt.PenStyle.DashLine)
            if geometry["dashed"]:
                assert pen.dashPattern() == [4.0, 2.0]
            assert geometry["cap"] == (
                "butt" if pen.capStyle() == Qt.PenCapStyle.FlatCap else "round"
            )
            assert geometry["join"] == (
                "miter" if pen.joinStyle() == Qt.PenJoinStyle.MiterJoin else "round"
            )
            assert source == before
            if delta == (0, 0) and kind in {
                "line",
                "line_bold",
                "line_dashed",
                "line_wavy",
            }:
                assert geometry["path"] == []


def test_arrow_path_budget_stops_before_building_remaining_arrows(monkeypatch):
    import chemvas.bootstrap.web_adapter as web

    source = new_document()
    source["state"]["arrows"] = [
        {"kind": "line_wavy", "start": [0, y], "end": [100000, y]} for y in range(100)
    ]
    build = web.arrow_path_commands
    calls = []

    def counted(*args, **kwargs):
        calls.append(args)
        return build(*args, **kwargs)

    monkeypatch.setattr(web, "arrow_path_commands", counted)
    session = BrowserSession()
    before = session.dispatch({"action": "read"})
    with pytest.raises(ValueError, match="browser path point limit"):
        session.dispatch({"revision": 0, "action": "load", "document": source})
    assert len(calls) == 31
    assert session.dispatch({"action": "read"}) == before
    source["state"]["arrows"] = source["state"]["arrows"][:30]
    result = document_info(source)
    assert len(result["drawing"]["arrows"]) == 30


@pytest.mark.parametrize("kind", sorted(VALID_ARROW_KINDS))
def test_browser_arrow_movement_matches_native_and_keeps_history(desktop_canvas, kind):
    from chemvas.domain.document import arrow_to_state

    source = draw_bond(new_document())["document"]
    arrow = {"kind": kind, "start": [0, 0], "end": [70, 30], "color": "#123456"}
    if kind.startswith("curved_"):
        arrow.update(control=[20, -40], double=kind == "curved_double")
    if kind.startswith("equilibrium"):
        arrow["mirrored"] = True
    source["state"]["arrows"] = [arrow]
    original = deepcopy(source)
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    item = desktop_canvas.runtime_state.arrow_items()[0]
    desktop_canvas.services.move_controller.move_item(
        item, 13, -9, update_selection=False
    )
    expected = arrow_to_state(desktop_canvas.render_context.arrows.record(item))
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    change = {
        "kind": "move",
        "selection": [{"target": "arrow", "id": 0}] * 2,
        "dx": 13,
        "dy": -9,
    }
    preview = session.dispatch({"revision": 1, "action": "preview", "edit": change})
    assert session.info["document"] == source and not session.state.history
    moved = session.dispatch({"revision": 1, "action": "edit", "edit": change})
    assert moved["document"] == preview["document"]
    assert extract_document_state(moved["document"])["arrows"] == [expected]
    assert moved["document"]["state"]["model"] == source["state"]["model"]
    assert len(session.state.history) == 1
    assert session.dispatch({"revision": 2, "action": "undo"})["document"] == source
    no_op = session.dispatch(
        {"revision": 3, "action": "edit", "edit": {**change, "dx": 0, "dy": 0}}
    )
    assert no_op["can_redo"] and not session.state.history
    assert (
        session.dispatch({"revision": 4, "action": "redo"})["document"]
        == moved["document"]
    )
    assert source == original


def test_browser_mixed_arrow_graph_delete_and_undo():
    source = draw_bond(new_document())["document"]
    source["state"]["arrows"] = [
        {"kind": kind, "start": [0, 0], "end": [50, 30]}
        for kind in ("arrow", "line_wavy", "inhibit")
    ]
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    selection = [{"target": "arrow", "id": i} for i in (0, 2, 0)] + [
        {"target": "bond", "id": 0}
    ]
    deleted = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {"kind": "delete_selection", "selection": selection},
        }
    )
    state = extract_document_state(deleted["document"])
    assert not state["model"]["atoms"] and not any(state["model"]["bonds"])
    assert [arrow["kind"] for arrow in state["arrows"]] == ["line_wavy"]
    assert len(session.state.history) == 1
    assert session.dispatch({"revision": 2, "action": "undo"})["document"] == source
    assert (
        session.dispatch({"revision": 3, "action": "redo"})["document"]
        == deleted["document"]
    )


@pytest.mark.parametrize("arrow_id", [True, -1, 1, 0.5, "0", None])
@pytest.mark.parametrize("kind", ["move", "delete_selection"])
def test_invalid_arrow_selection_preserves_session(arrow_id, kind):
    source = draw_bond(new_document())["document"]
    source["state"]["arrows"] = [{"kind": "arrow", "start": [0, 0], "end": [50, 30]}]
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    before = session.dispatch({"action": "read"})
    change = {
        "kind": kind,
        "selection": [{"target": "bond", "id": 0}, {"target": "arrow", "id": arrow_id}],
    }
    if kind == "move":
        change.update(dx=5, dy=10)
    with pytest.raises(ValueError):
        session.dispatch({"revision": 1, "action": "edit", "edit": change})
    assert session.dispatch({"action": "read"}) == before
    assert not session.state.history


def test_arrow_move_failure_keeps_mixed_candidate_private(monkeypatch):
    from chemvas.ui.canvas.canvas_move_controller import CanvasMoveController

    source = draw_bond(new_document())["document"]
    source["state"]["arrows"] = [{"kind": "arrow", "start": [0, 0], "end": [50, 30]}]
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    before = session.dispatch({"action": "read"})
    move = CanvasMoveController.move_item

    def fail(self, *args, **kwargs):
        move(self, *args, **kwargs)
        raise ValueError("arrow presentation failed")

    monkeypatch.setattr(CanvasMoveController, "move_item", fail)
    with pytest.raises(ValueError, match="arrow presentation failed"):
        session.dispatch(
            {
                "revision": 1,
                "action": "edit",
                "edit": {
                    "kind": "move",
                    "selection": [
                        {"target": "bond", "id": 0},
                        {"target": "arrow", "id": 0},
                    ],
                    "dx": 5,
                    "dy": 10,
                },
            }
        )
    assert session.dispatch({"action": "read"}) == before
    assert not session.state.history


def test_arrow_labels_stay_read_only_and_are_preserved():
    source = new_document()
    source["state"]["arrows"] = [
        {"kind": "arrow", "start": [0, 0], "end": [50, 30], "labels": {"above": "heat"}}
    ]
    before = deepcopy(source)
    info = document_info(source)
    assert info["unsupported"] == ["arrow labels"]
    with pytest.raises(ValueError, match="read-only"):
        edit_document(
            {
                "document": source,
                "edit": {
                    "kind": "delete_selection",
                    "selection": [{"target": "arrow", "id": 0}],
                },
            }
        )
    assert source == before


def test_arrow_selection_limit_includes_arrows_beyond_graph_limit():
    source = new_document()
    source["state"]["arrows"] = [{"kind": "arrow", "start": [0, 0], "end": [50, 30]}]
    adapter = BrowserStructureAdapter(extract_document_state(source))
    selection = [{"target": "arrow", "id": 0}] * 5001
    assert len(adapter.selection_buckets(selection).arrow_items) == 1
    with pytest.raises(ValueError, match="bounded list"):
        adapter.selection_buckets(selection + selection[:1])


@pytest.mark.parametrize("style", [value for _, value in ARROW_MENU_SPECS])
@pytest.mark.parametrize("shift", [False, True])
@pytest.mark.parametrize("scale", [0.1, 0.5, 1.0, 4.0])
def test_browser_arrow_gesture_matches_native(desktop_canvas, style, shift, scale):
    from types import SimpleNamespace

    from PyQt6.QtCore import QPointF, Qt

    from chemvas.domain.document import arrow_to_state
    from chemvas.ui.tools.preview_tools import ArrowTool

    source = new_document()
    source["state"]["arrows"] = [
        {"kind": "line", "start": [0, 0], "end": [40, 0]},
        {"kind": "line", "start": [100, 30], "end": [180, 30]},
    ]
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    from chemvas.ui.canvas.input_view_access import update_view_transform_for

    desktop_canvas.runtime_state.input_view_state.zoom = scale
    update_view_transform_for(desktop_canvas)
    assert desktop_canvas.viewportTransform().m11() == scale
    context = SimpleNamespace(scene_pos_from_event=lambda event: event.scene)
    tool = ArrowTool(desktop_canvas, mode=style, context=context)
    modifiers = (
        Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    )

    def event(x, y):
        return SimpleNamespace(
            scene=QPointF(x, y),
            position=lambda: QPointF(x * scale, y * scale),
            button=lambda: Qt.MouseButton.LeftButton,
            modifiers=lambda: modifiers,
        )

    tool.on_mouse_press(event(3, 2))
    tool.on_mouse_release(event(102, 32))
    expected = arrow_to_state(
        desktop_canvas.render_context.arrows.record(
            desktop_canvas.runtime_state.arrow_items()[-1]
        )
    )
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    change = {
        "kind": "arrow",
        "start": [3, 2],
        "end": [102, 32],
        "style": style,
        "shift": shift,
        "dragged": True,
        "scale": scale,
    }
    preview = session.dispatch({"revision": 1, "action": "preview", "edit": change})
    assert not session.state.history and session.info["document"] == source
    result = session.dispatch({"revision": 1, "action": "edit", "edit": change})
    assert result["document"] == preview["document"]
    assert extract_document_state(result["document"])["arrows"][-1] == expected
    assert len(session.state.history) == 1
    assert session.dispatch({"revision": 2, "action": "undo"})["document"] == source
    assert (
        session.dispatch({"revision": 3, "action": "redo"})["document"]
        == result["document"]
    )


@pytest.mark.parametrize(
    "change",
    [
        {"dragged": False},
        {"end": [0, 0]},
    ],
)
def test_browser_arrow_click_and_collapsed_drag_keep_history(change):
    source = new_document()
    edit = {
        "kind": "arrow",
        "start": [0, 0],
        "end": [50, 30],
        "style": "reaction",
        "shift": False,
        "dragged": True,
        "scale": 1,
        **change,
    }
    session = BrowserSession()
    before = session.dispatch({"action": "read"})
    after = session.dispatch({"revision": 0, "action": "edit", "edit": edit})
    assert after["document"] == before["document"] == source
    assert not session.state.history


@pytest.mark.parametrize(
    "change",
    [
        {"scale": 0},
        {"scale": True},
        {"scale": float("nan")},
        {"scale": 99},
        {"scale": -1},
        {"scale": float("inf")},
        {"scale": 1e-320},
        {"scale": Decimal("1e-999")},
        {"shift": 1},
        {"dragged": "yes"},
        {"start": [True, 0]},
        {"end": [1]},
        {"style": "line"},
        {"style": "arc_90_right"},
        {"end": [1e30, 0]},
    ],
)
def test_invalid_arrow_gesture_preserves_document(change):
    session = BrowserSession()
    before = session.dispatch({"action": "read"})
    edit = {
        "kind": "arrow",
        "start": [0, 0],
        "end": [50, 30],
        "style": "reaction",
        "shift": False,
        "dragged": True,
        "scale": 1,
        **change,
    }
    with pytest.raises(ValueError):
        session.dispatch({"revision": 0, "action": "edit", "edit": edit})
    assert session.dispatch({"action": "read"}) == before


def test_arrow_gesture_accepts_strict_json_fractional_coordinates():
    from chemvas.domain.json_io import strict_json_loads

    change = strict_json_loads(
        '{"kind":"arrow","start":[0.25,0.5],"end":[50.75,30.5],"style":"curved_double","shift":false,"dragged":true,"scale":1.2}'
    )
    result = edit_document({"document": new_document(), "edit": change})
    arrow = result["document"]["state"]["arrows"][0]
    assert arrow["start"] == (0.25, 0.5)
    assert arrow["end"] == (50.75, 30.5)
    assert arrow["control"] and arrow["double"]


@pytest.mark.parametrize("preferred", [False, True])
@pytest.mark.parametrize("style", ["single", "double", "wedge", "dotted"])
@pytest.mark.parametrize(
    "point",
    [
        (30, 40),
        (33, 44),
        (35, 45),
        (40, 40),
        (40, 45),
        (40, 49),
        (40, 50.55),
        (40, 50.57),
        (49, 43),
        (55, 40),
        (30, 48),
        (25, 35),
    ],
)
def test_browser_pick_matches_native_graphics_and_structure_policy(
    desktop_canvas, preferred, style, point
):
    from PyQt6.QtCore import QPointF

    from chemvas.ui.canvas.canvas_hit_testing_service import (
        scene_items_at_pos_for_canvas,
    )

    source = draw_bond(new_document(), style=style)["document"]
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    pos = QPointF(*point)
    hits = []
    for item in scene_items_at_pos_for_canvas(desktop_canvas, pos):
        if item.data(0) in {"atom", "bond"}:
            hits.append({"target": item.data(0), "id": item.data(1)})
    raw = desktop_canvas.services.hit_testing_service.item_at_scene_pos(pos)
    item = (
        desktop_canvas.services.selection.preferred_structure_item_at_scene_pos(pos)
        if preferred
        else raw
    )
    expected = None if item is None else {"target": item.data(0), "id": item.data(1)}
    adapter = BrowserStructureAdapter(extract_document_state(source))
    assert adapter.pick_target(*point, hits, preferred=preferred, scale=1) == expected


@pytest.mark.parametrize("preferred", [False, True])
def test_browser_pick_prioritizes_atom_over_covering_arrow(desktop_canvas, preferred):
    from PyQt6.QtCore import QPointF

    source = draw_bond(new_document())["document"]
    source["state"]["arrows"] = [{"kind": "arrow", "start": [0, 40], "end": [80, 40]}]
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    native = desktop_canvas.services.hit_testing_service.item_at_scene_pos(
        QPointF(30, 40)
    )
    assert native.data(0) == "atom"
    adapter = BrowserStructureAdapter(extract_document_state(source))
    assert adapter.pick_target(
        30,
        40,
        [
            {"target": "arrow", "id": 0},
            {"target": "atom", "id": 0},
            {"target": "bond", "id": 0},
        ],
        preferred=preferred,
        scale=1,
    ) == {"target": "atom", "id": 0}


def test_session_pick_is_read_only_revision_bound_and_does_not_render(monkeypatch):
    from chemvas.bootstrap import web_adapter

    session = BrowserSession()
    session.dispatch(
        {
            "revision": 0,
            "action": "load",
            "document": draw_bond(new_document())["document"],
        }
    )
    before = deepcopy(session.info)
    monkeypatch.setattr(
        web_adapter,
        "drawing_geometry",
        lambda *args, **kwargs: pytest.fail("pick must not render"),
    )
    request = {
        "revision": 1,
        "action": "pick",
        "scale": 1,
        "x": 40,
        "y": 49,
        "hits": [],
        "preferred": True,
    }
    assert session.dispatch(request) == {
        "target": {"target": "bond", "id": 0},
        "revision": 1,
    }
    assert (
        session.info == before and session.revision == 1 and not session.state.history
    )
    with pytest.raises(web_adapter.StaleRevisionError):
        session.dispatch({**request, "revision": 0})
    assert session.info == before


def test_eraser_uses_native_near_bond_pick_and_one_undo():
    session = BrowserSession()
    source = draw_bond(new_document())["document"]
    session.dispatch({"revision": 0, "action": "load", "document": source})
    result = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {"kind": "erase", "scale": 1, "x": 40, "y": 49, "hits": []},
        }
    )
    assert not result["document"]["state"]["model"]["atoms"]
    assert len(session.state.history) == 1
    assert session.dispatch({"revision": 2, "action": "undo"})["document"] == source


@pytest.mark.parametrize(
    "fields",
    [
        {"x": float("nan")},
        {"y": True},
        {"hits": [{"target": "atom", "id": 999}]},
        {"hits": [{"target": "bond", "id": True}]},
        {"hits": None},
        {"preferred": 1},
        {"unexpected": True},
    ],
)
def test_invalid_session_pick_preserves_state(fields):
    session = BrowserSession()
    before = deepcopy(session.info)
    with pytest.raises(ValueError):
        session.dispatch(
            {
                "revision": 0,
                "action": "pick",
                "scale": 1,
                "x": 0,
                "y": 0,
                "hits": [],
                "preferred": True,
                **fields,
            }
        )
    assert (
        session.info == before and session.revision == 0 and not session.state.history
    )


@pytest.mark.parametrize("kind", sorted(VALID_ARROW_KINDS))
@pytest.mark.parametrize("scale", [0.25, 1, 4])
def test_browser_arrow_near_matches_native_paths(desktop_canvas, kind, scale):
    from PyQt6.QtCore import QPointF

    from chemvas.ui.canvas.canvas_hit_testing_service import (
        scene_items_at_pos_for_canvas,
    )

    source = new_document()
    source["state"]["arrows"] = [{"kind": kind, "start": [0, 0], "end": [100, 40]}]
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    from chemvas.ui.canvas.input_view_access import update_view_transform_for

    desktop_canvas.runtime_state.input_view_state.zoom = scale
    update_view_transform_for(desktop_canvas)
    assert desktop_canvas.viewportTransform().m11() == scale
    item = desktop_canvas.runtime_state.arrow_items()[0]
    path = item.path()
    adapter = BrowserStructureAdapter(extract_document_state(source))
    for fraction in (0.2, 0.5, 0.8):
        anchor = path.pointAtPercent(fraction)
        for offset in (-10, -6.5, -5.5, -3, 0, 3, 5.5, 6.5, 10):
            point = anchor + QPointF(0, offset / scale)
            direct = scene_items_at_pos_for_canvas(desktop_canvas, point)
            hits = [{"target": "arrow", "id": 0}] if item in direct else []
            expected = desktop_canvas.services.hit_testing_service.item_at_scene_pos(
                point
            )
            actual = adapter.pick_target(
                point.x(), point.y(), hits, preferred=False, scale=scale
            )
            assert actual == (
                None if expected is None else {"target": "arrow", "id": 0}
            ), (kind, scale, fraction, offset)


@pytest.mark.parametrize("scale", [0.25, 1, 4])
@pytest.mark.parametrize("preferred", [False, True])
@pytest.mark.parametrize("pixels", [3, 5.99, 6, 6.01])
def test_arrow_near_strict_screen_radius_and_eraser_undo(scale, preferred, pixels):
    source = new_document()
    source["state"]["arrows"] = [{"kind": "arrow", "start": [-100, 0], "end": [100, 0]}]
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    request = {
        "revision": 1,
        "action": "pick",
        "x": 0,
        "y": pixels / scale,
        "hits": [],
        "scale": scale,
        "preferred": preferred,
    }
    expected = {"target": "arrow", "id": 0} if pixels < 6 else None
    assert session.dispatch(request)["target"] == expected
    result = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {
                "kind": "erase",
                "x": 0,
                "y": pixels / scale,
                "hits": [],
                "scale": scale,
            },
        }
    )
    if expected is None:
        assert result["document"] == source and not session.state.history
    else:
        assert not result["document"]["state"]["arrows"]
        assert session.dispatch({"revision": 2, "action": "undo"})["document"] == source


def test_arrow_near_uses_distance_then_reverse_scene_order_and_structure_priority():
    source = new_document()
    source["state"]["arrows"] = [
        {"kind": "arrow", "start": [-100, 0], "end": [100, 0]},
        {"kind": "arrow", "start": [-100, 8], "end": [100, 8]},
    ]
    adapter = BrowserStructureAdapter(extract_document_state(source))
    assert adapter.pick_target(0, 3, [], preferred=True, scale=1) == {
        "target": "arrow",
        "id": 0,
    }
    assert adapter.pick_target(0, 4, [], preferred=True, scale=1) == {
        "target": "arrow",
        "id": 1,
    }
    source = draw_bond(source, start=(0, 0), end=(20, 0))["document"]
    adapter = BrowserStructureAdapter(extract_document_state(source))
    assert adapter.pick_target(10, 4, [], preferred=False, scale=1) == {
        "target": "bond",
        "id": 0,
    }


@pytest.mark.parametrize(
    "scale",
    [None, True, 0, -1, float("nan"), float("inf"), 99, 1e-320, Decimal("1e-999")],
)
def test_invalid_pick_scale_does_not_mutate_session(scale):
    session = BrowserSession()
    before = deepcopy(session.info)
    with pytest.raises(ValueError, match="drawing scale"):
        session.dispatch(
            {
                "revision": 0,
                "action": "pick",
                "x": 0,
                "y": 0,
                "hits": [],
                "preferred": False,
                "scale": scale,
            }
        )
    with pytest.raises(ValueError, match="drawing scale"):
        session.dispatch(
            {
                "revision": 0,
                "action": "edit",
                "edit": {"kind": "erase", "x": 0, "y": 0, "hits": [], "scale": scale},
            }
        )
    assert session.info == before and not session.state.history


@pytest.mark.parametrize(
    "start,control,end",
    [
        ((0, 0), (50, 30), (100, 0)),
        ((0, 0), (0, 0), (0, 0)),
        ((0, 0), (0, 100), (0, 0)),
        ((0, 0), (0.1, 0.2), (0.3, 0.2)),
        ((-90, 35), (400, -200), (10, 70)),
    ],
)
@pytest.mark.parametrize("scale", [0.1, 0.25, 1, 4])
def test_browser_quadratic_pick_segments_match_native_flattening(
    start, control, end, scale
):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QPainterPath, QTransform

    from chemvas.bootstrap.web_adapter import arrow_pick_segments

    path = QPainterPath(QPointF(*start))
    path.quadTo(QPointF(*control), QPointF(*end))
    native = QTransform().scale(scale, scale).map(path).toSubpathPolygons()
    expected = [
        (a.x(), a.y(), b.x(), b.y()) for polygon in native for a, b in pairwise(polygon)
    ]
    actual = [
        (a.x(), a.y(), b.x(), b.y())
        for a, b in arrow_pick_segments([("M", start), ("Q", (*control, *end))], scale)
        if a != b
    ]
    assert len(actual) == len(expected)
    for a, b in zip(actual, expected, strict=True):
        assert a == pytest.approx(b, abs=1e-10)


def test_arrow_pick_point_limit_preserves_eraser_document(monkeypatch):
    from chemvas.bootstrap import web_adapter

    session = BrowserSession()
    source = new_document()
    source["state"]["arrows"] = [{"kind": "arrow", "start": [-100, 0], "end": [100, 0]}]
    session.dispatch({"revision": 0, "action": "load", "document": source})
    before = deepcopy(session.info)

    def oversized(*args):
        point = web_adapter.BrowserPoint(0, 0)
        yield from ((point, point) for _ in range(500_001))

    monkeypatch.setattr(web_adapter, "arrow_pick_segments", oversized)
    with pytest.raises(ValueError, match="point limit"):
        session.dispatch(
            {
                "revision": 1,
                "action": "edit",
                "edit": {"kind": "erase", "x": 0, "y": 0, "hits": [], "scale": 1},
            }
        )
    assert session.info == before and not session.state.history


@pytest.mark.parametrize("style", ["line", "line_dashed", "line_wavy", "line_bold"])
@pytest.mark.parametrize("shift", [False, True])
@pytest.mark.parametrize("scale", [0.25, 1, 4])
@pytest.mark.parametrize(
    "gesture",
    [
        "drag",
        "click",
        "jitter",
        "loopback",
        "endpoint",
        "occupied_arrow",
        "occupied_atom",
        "ring",
    ],
)
def test_browser_line_gesture_matches_native(
    desktop_canvas, style, shift, scale, gesture
):
    from types import SimpleNamespace

    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtWidgets import QApplication

    from chemvas.domain.document import arrow_from_state, arrow_to_state
    from chemvas.ui.canvas.canvas_hit_testing_service import (
        scene_items_at_pos_for_canvas,
    )
    from chemvas.ui.canvas.input_view_access import update_view_transform_for
    from chemvas.ui.tools.line_tool import LineTool

    source = new_document()
    start, end = (10, 20), (100, 57)
    if gesture in {"click", "jitter", "loopback"}:
        end = (
            start
            if gesture != "jitter"
            else (start[0] + 1 / scale, start[1] + 1 / scale)
        )
    elif gesture in {"endpoint", "occupied_arrow"}:
        source["state"]["arrows"] = [{"kind": "arrow", "start": [0, 0], "end": [40, 0]}]
        start, end = (42, 1), ((42, 1) if gesture == "occupied_arrow" else (120, 33))
    elif gesture == "occupied_atom":
        source = draw_bond(source)["document"]
        start = end = (30, 40)
    elif gesture == "ring":
        source = edit_document(
            {"document": source, "edit": {"kind": "ring", "x": 100, "y": 100}}
        )["document"]
        start = end = (100, 100)
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    desktop_canvas.runtime_state.input_view_state.zoom = scale
    update_view_transform_for(desktop_canvas)
    assert desktop_canvas.viewportTransform().m11() == scale
    desktop_canvas.runtime_state.tool_settings_state.active_line_kind = style
    hit_test = desktop_canvas.services.hit_testing_service.item_at_scene_pos
    context = SimpleNamespace(
        scene_pos_from_event=lambda event: event.scene, item_at_scene_pos=hit_test
    )
    tool = LineTool(desktop_canvas, context=context)
    modifiers = (
        Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    )

    def event(point):
        return SimpleNamespace(
            scene=QPointF(*point),
            position=lambda: QPointF(point[0] * scale, point[1] * scale),
            button=lambda: Qt.MouseButton.LeftButton,
            modifiers=lambda: modifiers,
        )

    hits = [
        {"target": item.data(0), "id": item.data(1)}
        for item in scene_items_at_pos_for_canvas(desktop_canvas, QPointF(*start))
        if item.data(0) in {"atom", "bond"}
    ]
    tool.on_mouse_press(event(start))
    if gesture == "loopback":
        tool.on_mouse_move(event((start[0] + 30 / scale, start[1])))
    tool.on_mouse_move(event(end))
    tool.on_mouse_release(event(end))
    expected = [
        arrow_to_state(desktop_canvas.render_context.arrows.record(item))
        for item in desktop_canvas.runtime_state.arrow_items()
    ]
    dragged = (
        gesture == "loopback"
        or (abs(start[0] - end[0]) + abs(start[1] - end[1])) * scale
        >= QApplication.startDragDistance()
    )
    edit = {
        "kind": "line",
        "start": list(start),
        "end": list(end),
        "style": style,
        "shift": shift,
        "dragged": dragged,
        "scale": scale,
        "hits": hits,
    }
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    preview = session.dispatch({"revision": 1, "action": "preview", "edit": edit})
    assert session.info["document"] == source and not session.state.history
    if not dragged or gesture == "loopback":
        assert preview["document"] == source
    result = session.dispatch({"revision": 1, "action": "edit", "edit": edit})
    assert [
        arrow_to_state(arrow_from_state(record))
        for record in extract_document_state(result["document"])["arrows"]
    ] == expected
    if result["document"] != source:
        if dragged and gesture != "loopback":
            assert result["document"] == preview["document"]
        assert len(session.state.history) == 1
        assert session.dispatch({"revision": 2, "action": "undo"})["document"] == source
        assert (
            session.dispatch({"revision": 3, "action": "redo"})["document"]
            == result["document"]
        )
    else:
        assert not session.state.history


def test_line_click_preview_font_registration_does_not_insert_a_level():
    session = BrowserSession()
    before = deepcopy(session.info)
    edit = {
        "kind": "line",
        "start": [0, 0],
        "end": [0, 0],
        "style": "line",
        "shift": False,
        "dragged": False,
        "scale": 1,
        "hits": [],
    }
    font = font_measurements_for(new_document())
    result = session.dispatch(
        {"revision": 0, "action": "measure", "font": font, "edit": edit}
    )
    assert result["document"] == before["document"]
    assert session.revision == 0 and not session.state.history
    inserted = session.dispatch({"revision": 0, "action": "edit", "edit": edit})
    assert inserted["document"]["state"]["arrows"][0]["end"] == (40, 0)


@pytest.mark.parametrize(
    "change",
    [
        {"style": "reaction"},
        {"hits": None},
        {"hits": [{"target": "atom", "id": 999}]},
        {"scale": 0},
        {"dragged": 1},
    ],
)
def test_invalid_line_gesture_preserves_document(change):
    session = BrowserSession()
    before = deepcopy(session.info)
    edit = {
        "kind": "line",
        "start": [0, 0],
        "end": [50, 20],
        "style": "line",
        "shift": False,
        "dragged": True,
        "scale": 1,
        "hits": [],
        **change,
    }
    with pytest.raises(ValueError):
        session.dispatch({"revision": 0, "action": "edit", "edit": edit})
    assert session.info == before and not session.state.history
