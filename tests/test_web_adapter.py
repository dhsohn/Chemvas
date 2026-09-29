from __future__ import annotations

import http.client
import json
import re
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
    arrow_frame_bounds,
    atom_input_plan,
    browser_font_pixels,
    browser_note_html,
    browser_notes,
    document_info,
    edit_document,
    new_document,
    ui_css,
    ui_spec,
    validate_font_metrics,
)
from chemvas.domain.document import (
    VALID_ARROW_KINDS,
    VALID_BOND_STYLES,
    build_document_payload,
    extract_document_state,
)
from chemvas.features.annotations import BRACKET_SYMBOLS, sanitize_note_html
from chemvas.features.rendering import RenderMetrics
from chemvas.features.selection.hit import ARROW_PICK_SCREEN_PX
from chemvas.ui.selection.selection_style_access import SELECTION_OBJECT_PADDING_RATIO
from chemvas.ui.window.main_window_config import ARROW_MENU_SPECS, COLOR_TOOL_MESSAGES

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
                "font = BrowserFontMeasurements({'family': spec['family'], 'metrics': {q['key']: {'width': 8, 'ascent': 12, 'descent': 4, 'cap_height': 11, 'bounding_width': 8, 'line_height': 18} for q in spec['queries']}, 'ink': {str(q['pixels'])+':'+q['text']: [[-4,-6],[4,-6],[4,6],[-4,6]] for q in spec['queries']}}); "
                "assert 'atom_layouts' in document_info(labelled['document'], font=font)['drawing']; "
                "from chemvas.domain.document import VALID_ARROW_KINDS; "
                "arrows = new_document(); arrows['state']['arrows'] = [{'kind': k, 'start': [0,0], 'end': [60,30]} for k in VALID_ARROW_KINDS]; "
                "assert len(document_info(arrows)['drawing']['arrows']) == len(VALID_ARROW_KINDS); "
                "from chemvas.bootstrap.web_adapter import BrowserStructureAdapter; from chemvas.domain.document import extract_document_state; BrowserStructureAdapter(extract_document_state(arrows)).pick_target(20, 12, [], preferred=False, scale=1); "
                "moved = edit_document({'document': arrows, 'edit': {'kind': 'move', 'selection': [{'target': 'arrow', 'id': i} for i in range(len(VALID_ARROW_KINDS))], 'dx': 5, 'dy': -10}}); "
                "edit_document({'document': moved['document'], 'edit': {'kind': 'delete_selection', 'selection': [{'target': 'arrow', 'id': 0}]}}); "
                "edit_document({'document': new_document(), 'edit': {'kind': 'arrow', 'start': [0,0], 'end': [60,30], 'style': 'curved_double', 'dragged': True, 'shift': False, 'scale': 1}}); "
                "edit_document({'document': new_document(), 'edit': {'kind': 'line', 'start': [0,0], 'end': [60,30], 'style': 'line_wavy', 'dragged': True, 'shift': True, 'scale': 1, 'hits': []}}); "
                "edit_document({'document': arrows, 'edit': {'kind': 'arrow_style', 'preset': 'Bold'}}); "
                "picked = BrowserSession(); picked.dispatch({'revision': 0, 'action': 'pick', 'scale': 1, 'x': 0, 'y': 0, 'hits': [], 'preferred': True}); "
                "edit_document({'document': ring['document'], 'edit': {'kind': 'erase', 'scale': 1, 'x': 100, 'y': 100, 'hits': []}}); "
                "edit_document({'document': arrows, 'edit': {'kind': 'arrow_handle', 'id': 0, 'handle': 'end', 'position': [90,60], 'previous': None, 'scale': 1}}); "
                "labelled_arrows = edit_document({'document': arrows, 'edit': {'kind': 'arrow_labels', 'id': 0, 'labels': {'above': 'H_2O'}}}); assert labelled_arrows['drawing']['needs_measurements']; "
                "shape = edit_document({'document': new_document(), 'edit': {'kind': 'shape', 'start': [0,0], 'end': [60,30], 'style': 'rect', 'stroke': 'solid'}}); "
                "shape = edit_document({'document': shape['document'], 'edit': {'kind': 'move', 'selection': [{'target': 'shape', 'id': 0}], 'dx': 5, 'dy': -10}}); "
                "edit_document({'document': shape['document'], 'edit': {'kind': 'delete_selection', 'selection': [{'target': 'shape', 'id': 0}]}}); "
                "edit_document({'document': shape['document'], 'edit': {'kind': 'color', 'color': '#123456', 'selection': [{'target': 'shape', 'id': 0}]}}); "
                "edit_document({'document': ring['document'], 'edit': {'kind': 'ring_fill', 'color': '#123456', 'selection': [{'target': 'ring', 'id': 0}]}}); "
                "edit_document({'document': ring['document'], 'edit': {'kind': 'rotate', 'value': 37, 'selection': [{'target': 'ring', 'id': 0}]}}); "
                "edit_document({'document': ring['document'], 'edit': {'kind': 'rotate', 'start': [0,-100], 'end': [100,0], 'shift': True, 'selection': [{'target': 'ring', 'id': 0}]}}); "
                "edit_document({'document': ring['document'], 'edit': {'kind': 'flip', 'horizontal': True, 'selection': [{'target': 'ring', 'id': 0}]}}); "
                "BrowserStructureAdapter(extract_document_state(ring['document'])).selection_frame([{'target': 'ring', 'id': 0}], ring['drawing']); "
                "edit_document({'document': ring['document'], 'edit': {'kind': 'align', 'mode': 'left', 'selection': [{'target': 'ring', 'id': 0}]}}); "
                "edit_document({'document': ring['document'], 'edit': {'kind': 'sheet_setup', 'size': 'Custom', 'orientation': 'portrait', 'custom_size_mm': [123.45,234.56]}}); "
                "edit_document({'document': new_document(), 'edit': {'kind': 'arrow', 'grid': 'hex', 'start': [13,17], 'end': [81,49], 'style': 'reaction', 'dragged': True, 'shift': False, 'scale': 1}}); "
                "marked = new_document(); marked['state']['marks'] = [{'kind':'plus','text':None,'atom_id':None,'dx':None,'dy':None,'x':10,'y':20}]; "
                "spec = document_info(marked)['drawing']['label_measurements']; "
                "font = BrowserFontMeasurements({'family':spec['family'], 'metrics':{q['key']:{'width':8,'ascent':12,'descent':4,'cap_height':11,'bounding_width':8,'line_height':18} for q in spec['queries']}, 'ink':{str(q['pixels'])+':'+q['text']:[] for q in spec['queries']}}); "
                "assert len(document_info(marked, font=font)['drawing']['marks']) == 1; "
                "adapter = BrowserStructureAdapter(extract_document_state(marked)); adapter.move_selection([{'target':'mark','id':0}], 3, 4); adapter.delete_selection([{'target':'mark','id':0}]); assert not adapter.document_state['marks']; adapter.insert_mark(80,70,'plus',scale=1,hits=[],drawing=font.drawing(adapter.document_state),font=font); assert adapter.document_state['marks'][0]['atom_id'] is None; adapter.move_selection([{'target':'mark','id':0}],3,4); assert adapter.document_state['marks'][0]['x'] == 83; "
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
        {"text": "Item", "html": "<ul><li>Item</li></ul>", "x": 10, "y": 20}
    ]
    original = deepcopy(payload)
    info = document_info(payload)
    assert "note lists or formatting without a browser renderer" in info["unsupported"]
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


@pytest.mark.parametrize("style", ["double_outer", "double_either"])
@pytest.mark.parametrize("ring", [False, True])
def test_outward_and_either_doubles_match_native_lines(desktop_canvas, style, ring):
    from PyQt6.QtWidgets import QGraphicsLineItem

    payload = new_document()
    if ring:
        payload = edit_document(
            {"document": payload, "edit": {"kind": "ring", "x": 100, "y": 100}}
        )["document"]
    else:
        payload = draw_bond(payload)["document"]
    for bond in payload["state"]["model"]["bonds"]:
        bond.update(style=style, order=2)
    browser = document_info(payload)
    assert not browser["unsupported"]
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(payload)
    )
    for (
        bond_id,
        items,
    ) in desktop_canvas.runtime_state.bond_graphics_state.bond_items.items():
        lines = [item.line() for item in items if isinstance(item, QGraphicsLineItem)]
        primitives = browser["drawing"]["bonds"][str(bond_id)]
        assert [primitive["line"] for primitive in primitives] == [
            pytest.approx((line.x1(), line.y1(), line.x2(), line.y2()), abs=1e-9)
            for line in lines
        ]


@pytest.mark.parametrize(
    "style", ["double", "double_center", "double_outer", "bold_in", "bold_out"]
)
@pytest.mark.parametrize("position", ["double", "double_center", "double_outer"])
def test_double_bond_position_menu_matches_native(desktop_canvas, style, position):
    from chemvas.features.rendering import (
        double_position_for_style,
        style_for_double_position,
    )

    source = draw_bond(new_document(), start=(0, 0), end=(20, 0))["document"]
    source["state"]["model"]["bonds"][0].update(style=style, order=2)
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    menu = session.dispatch(
        {
            "revision": 1,
            "action": "bond_menu",
            "x": 10,
            "y": 0,
            "hits": [{"target": "bond", "id": 0}],
            "scale": 1,
        }
    )["menu"]
    assert menu == {
        "bond": 0,
        "entries": [
            {
                "label": label,
                "position": value,
                "checked": value == double_position_for_style(style, 2),
            }
            for label, value in (
                ("Inward", "double"),
                ("Centered", "double_center"),
                ("Outward", "double_outer"),
            )
        ],
    }
    result = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {"kind": "double_position", "id": 0, "position": position},
        }
    )
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    desktop_canvas.services.scene_transform_controller.apply_bond_style(
        0, style_for_double_position(style, 2, position), 2
    )
    expected = desktop_canvas.services.canvas_document_session_service.snapshot_state()
    assert result["document"]["state"]["model"]["bonds"] == expected["model"]["bonds"]


def test_double_bond_menu_uses_the_native_nearby_bond_and_skips_other_styles():
    source = draw_bond(new_document(), start=(0, 0), end=(20, 0))["document"]
    source["state"]["model"]["bonds"][0].update(style="double", order=2)
    adapter = BrowserStructureAdapter(extract_document_state(source))
    # The wider of 0.35 bond lengths and the structure pick radius (10.56 here).
    assert adapter.double_bond_menu(10, 10.4, [], 1)["bond"] == 0
    assert adapter.double_bond_menu(10, 10.8, [], 1) is None
    source["state"]["model"]["bonds"][0].update(style="triple", order=3)
    adapter = BrowserStructureAdapter(extract_document_state(source))
    assert adapter.double_bond_menu(10, 0, [{"target": "bond", "id": 0}], 1) is None
    with pytest.raises(ValueError, match="inward, centered or outward"):
        adapter.apply_double_position(0, "double")


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
            "bounding_width": fm.boundingRect(query["text"]).width(),
            "ascent": fm.ascent(),
            "descent": fm.descent(),
            "cap_height": fm.capHeight(),
            "line_height": document.size().height() - 2 * document.documentMargin(),
        }
    relative_runs = place_browser_labels(spec["size"], [spec["labels"]["0"]], measured)[
        0
    ]["runs"]
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
            "bounding_width": 8,
            "line_height": 18,
        }
        for query in spec["queries"]
    }

    def no_document_validation(*args, **kwargs):
        raise AssertionError("Label presentation must not validate a document")

    monkeypatch.setattr(
        "chemvas.bootstrap.web_adapter.document_info", no_document_validation
    )
    placed = place_browser_labels(
        spec["size"], list(spec["labels"].values()), measurements
    )
    assert [run["text"] for run in placed[0]["runs"]] == ["NH", "2"]
    assert document == before
    first = measurements[spec["queries"][0]["key"]]
    for field in ("width", "bounding_width"):
        original = first[field]
        for invalid in [True, -1, "12", None, float("nan"), float("inf")]:
            first[field] = invalid
            with pytest.raises(ValueError):
                validate_font_metrics(measurements)
        first[field] = original


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
                "bounding_width": 8,
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
    from PyQt6.QtGui import QColor, QPainterPath, QPainterPathStroker

    from chemvas.ui.canvas.pick_radius_access import atom_pick_radius_for
    from chemvas.ui.selection.selection_outline_items import selection_outline_pen
    from chemvas.ui.selection.selection_outline_paths import (
        selection_path_for_object_item,
    )

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
            # Freeze the original native width formula, independently of the
            # shared helper now used by both presentations.
            radius = atom_pick_radius_for(desktop_canvas)
            expected_width = max(pen.widthF() + length * 0.12 * 1.5, radius * 0.7)
            assert geometry["selection_width"] == expected_width
            stroke = QPainterPathStroker()
            stroke.setWidth(expected_width)
            stroke.setCapStyle(Qt.PenCapStyle.RoundCap)
            stroke.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            assert selection_path_for_object_item(
                item, kind=kind, pad=length * 0.12, atom_pick_radius=radius
            ) == stroke.createStroke(item.path())
            style = info["drawing"]["selection_style"]
            assert style["screen_width"] == selection_outline_pen(QColor()).widthF()
            assert (
                style["color"]
                == desktop_canvas.runtime_state.selection_state.color.name()
            )
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


def test_arrow_labels_request_measurements_and_preserve_source():
    source = new_document()
    source["state"]["arrows"] = [
        {"kind": "arrow", "start": [0, 0], "end": [50, 30], "labels": {"above": "heat"}}
    ]
    before = deepcopy(source)
    info = document_info(source)
    assert info["unsupported"] == []
    assert info["drawing"]["needs_measurements"]
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
@pytest.mark.parametrize("grid", ["none", "square", "hex"])
def test_browser_arrow_gesture_matches_native(
    desktop_canvas, style, shift, scale, grid
):
    from types import SimpleNamespace

    from PyQt6.QtCore import QPointF, Qt

    from chemvas.domain.document import arrow_to_state
    from chemvas.ui.tools.preview_tools import ArrowTool

    settings = desktop_canvas.runtime_state.tool_settings_state
    settings.grid_snap_enabled = grid != "none"
    settings.grid_style = "hex" if grid == "hex" else "square"
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
        "grid": grid,
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
@pytest.mark.parametrize("grid", ["none", "square", "hex"])
def test_browser_line_gesture_matches_native(
    desktop_canvas, style, shift, scale, gesture, grid
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

    settings = desktop_canvas.runtime_state.tool_settings_state
    settings.grid_snap_enabled = grid != "none"
    settings.grid_style = "hex" if grid == "hex" else "square"
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
        "grid": grid,
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
    if not dragged or (gesture == "loopback" and not (grid == "hex" and shift)):
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


@pytest.mark.parametrize("kind", sorted(VALID_ARROW_KINDS))
@pytest.mark.parametrize(
    "change",
    [
        {"preset": "Default"},
        {"preset": "Bold"},
        {"preset": "Fine"},
        {"setting": "arrow_line_width", "value": 5},
        {"setting": "arrow_line_width", "value": 22},
        {"setting": "arrow_line_width", "value": 60},
        {"setting": "arrow_head_scale", "value": 10},
        {"setting": "arrow_head_scale", "value": 40},
        {"setting": "arrow_head_scale", "value": 80},
    ],
)
def test_browser_arrow_style_matches_native_controller(desktop_canvas, kind, change):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QPainterPath

    from chemvas.ui.window.main_window_config import ARROW_SLIDER_RANGES
    from chemvas.ui.window.main_window_toolbar_logic import arrow_preset_from_label

    source = new_document()
    source["state"]["settings"].update(arrow_line_width=1.3, arrow_head_scale=0.35)
    source["state"]["arrows"] = [
        {
            "kind": kind,
            "start": [0, 0],
            "end": [100, 40],
            "control": [30, -25] if kind.startswith("curved_") else None,
            "double": kind == "curved_double",
            "color": "#123456",
        }
    ]
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    controller = desktop_canvas.services.tool_mode_controller
    if "preset" in change:
        controller.set_arrow_style(*arrow_preset_from_label(change["preset"]))
    else:
        getattr(controller, f"set_{change['setting']}")(
            change["value"] / ARROW_SLIDER_RANGES[change["setting"]][2]
        )
    item = desktop_canvas.runtime_state.arrow_items()[0]
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    result = session.dispatch(
        {"revision": 1, "action": "edit", "edit": {"kind": "arrow_style", **change}}
    )
    assert result["document"]["state"]["arrows"] == source["state"]["arrows"]
    assert (
        result["document"]["state"]["settings"]["arrow_line_width"]
        == controller.get_arrow_line_width()
    )
    assert (
        result["document"]["state"]["settings"]["arrow_head_scale"]
        == controller.get_arrow_head_scale()
    )
    geometry = result["drawing"]["arrows"][0]
    path = QPainterPath()
    for command, coordinates in geometry["path"]:
        if command == "M":
            path.moveTo(*coordinates)
        elif command == "L":
            path.lineTo(*coordinates)
        else:
            path.quadTo(*coordinates)
    assert path == item.path()
    assert geometry["width"] == item.pen().widthF()
    assert geometry["color"] == item.pen().color().name()
    assert geometry["dashed"] == (item.pen().style() == Qt.PenStyle.DashLine)
    assert len(session.state.history) == 1
    assert session.dispatch({"revision": 2, "action": "undo"})["document"] == source
    assert (
        session.dispatch({"revision": 3, "action": "redo"})["document"]
        == result["document"]
    )


def test_arrow_style_noop_preserves_redo():
    session = BrowserSession()
    session.dispatch(
        {
            "revision": 0,
            "action": "edit",
            "edit": {"kind": "arrow_style", "preset": "Bold"},
        }
    )
    session.dispatch({"revision": 1, "action": "undo"})
    before = deepcopy(session.info)
    session.dispatch(
        {
            "revision": 2,
            "action": "edit",
            "edit": {"kind": "arrow_style", "preset": "Default"},
        }
    )
    assert session.info == before and len(session.state.redo_stack) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"preset": "ACS"},
        {"preset": None},
        {"setting": "bond_length_px", "value": 20},
        {"setting": "arrow_line_width", "value": True},
        {"setting": "arrow_line_width", "value": 4},
        {"setting": "arrow_line_width", "value": 61},
        {"setting": "arrow_head_scale", "value": 9},
        {"setting": "arrow_head_scale", "value": 81},
        {"setting": "arrow_line_width", "value": 12.5},
        {"preset": "Bold", "extra": 1},
    ],
)
def test_invalid_arrow_style_preserves_document(change):
    session = BrowserSession()
    before = deepcopy(session.info)
    with pytest.raises(ValueError):
        session.dispatch(
            {"revision": 0, "action": "edit", "edit": {"kind": "arrow_style", **change}}
        )
    assert session.info == before and not session.state.history


@pytest.mark.parametrize("kind", sorted(VALID_ARROW_KINDS))
@pytest.mark.parametrize("handle", ["start", "end"])
@pytest.mark.parametrize("scale", [0.25, 1.0, 4.0])
@pytest.mark.parametrize("path", ["move", "collapse", "return", "snap", "miss"])
@pytest.mark.parametrize("grid", ["none", "square", "hex"])
def test_arrow_handle_matches_native_frames(
    desktop_canvas, kind, handle, scale, path, grid
):
    from PyQt6.QtCore import QPointF

    from chemvas.domain.document import arrow_from_state, arrow_to_state
    from chemvas.ui.canvas.input_view_access import update_view_transform_for

    settings = desktop_canvas.runtime_state.tool_settings_state
    settings.grid_snap_enabled = grid != "none"
    settings.grid_style = "hex" if grid == "hex" else "square"
    source = new_document()
    arrow = {"kind": kind, "start": [10, 20], "end": [100, 50], "color": "#123456"}
    if kind.startswith("curved_"):
        arrow.update(control=[40, -20], double=kind == "curved_double")
    if kind.startswith("equilibrium"):
        arrow["mirrored"] = True
    source["state"]["arrows"] = [
        arrow,
        {"kind": "arrow", "start": [160, 100], "end": [210, 100]},
    ]
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    desktop_canvas.runtime_state.input_view_state.zoom = scale
    update_view_transform_for(desktop_canvas)
    assert desktop_canvas.transform().m11() == scale
    item = desktop_canvas.runtime_state.arrow_items()[0]
    arrows = desktop_canvas.render_context.arrows
    pressed = arrows.record(item)
    anchor = pressed.end if handle == "start" else pressed.start
    original_end = pressed.start if handle == "start" else pressed.end
    frames = [[70.0, -60.0]]
    if path == "collapse":
        frames += [list(anchor), [anchor[0] + 0.1, anchor[1] + 0.1]]
    elif path == "return":
        frames += [list(original_end)]
    elif path in {"snap", "miss"}:
        frames += [[160 + (11 if path == "snap" else 13) / scale, 100]]
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    previous = None
    for position in frames:
        desktop_canvas.services.handle_mutation_service.update_arrow_endpoint(
            item, QPointF(*position), handle, pressed=pressed
        )
        change = {
            "kind": "arrow_handle",
            "grid": grid,
            "id": 0,
            "handle": handle,
            "position": position,
            "previous": previous,
            "scale": scale,
        }
        preview = session.dispatch({"revision": 1, "action": "preview", "edit": change})
        got = arrow_to_state(
            arrow_from_state(preview["document"]["state"]["arrows"][0])
        )
        assert got == arrow_to_state(arrows.record(item))
        assert session.info["document"] == source and not session.state.history
        previous = list(
            next(
                h["point"]
                for h in preview["drawing"]["arrows"][0]["handles"]
                if h["handle"] == handle
            )
        )
    result = session.dispatch({"revision": 1, "action": "edit", "edit": change})
    assert result["document"] == preview["document"]
    assert result["document"]["state"]["arrows"][1] == source["state"]["arrows"][1]
    if arrow_to_state(arrows.record(item)) == arrow_to_state(pressed):
        assert not session.state.history
    else:
        assert len(session.state.history) == 1
        assert session.dispatch({"revision": 2, "action": "undo"})["document"] == source
        assert (
            session.dispatch({"revision": 3, "action": "redo"})["document"]
            == result["document"]
        )


@pytest.mark.parametrize("kind", ["curved_single", "curved_double"])
@pytest.mark.parametrize(
    "position", [[50, 0], [50, -200], [50, 200], [400, -35], [40, 100]]
)
def test_curve_control_handle_matches_native(desktop_canvas, kind, position):
    from PyQt6.QtCore import QPointF

    from chemvas.domain.document import arrow_to_state

    source = new_document()
    source["state"]["arrows"] = [
        {
            "kind": kind,
            "start": [10, 20],
            "end": [100, 50],
            "control": [40, -20],
            "double": kind == "curved_double",
        }
    ]
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    item = desktop_canvas.runtime_state.arrow_items()[0]
    desktop_canvas.services.handle_mutation_service.update_curved_control(
        item, QPointF(*position)
    )
    desktop_canvas.services.handle_overlay_service.show_curved_handles(item)
    result = edit_document(
        {
            "document": source,
            "edit": {
                "kind": "arrow_handle",
                "id": 0,
                "handle": "control",
                "position": position,
                "previous": None,
                "scale": 1,
            },
        }
    )
    assert extract_document_state(result["document"])["arrows"][0] == arrow_to_state(
        desktop_canvas.render_context.arrows.record(item)
    )
    assert [h["point"] for h in result["drawing"]["arrows"][0]["handles"]] == [
        (h.pos().x(), h.pos().y())
        for h in desktop_canvas.runtime_state.handle_state.active_handles
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"id": -1},
        {"id": True},
        {"id": 2},
        {"handle": "control"},
        {"handle": []},
        {"position": [0]},
        {"position": [True, 0]},
        {"position": [float("inf"), 0]},
        {"previous": {}},
        {"previous": [0, float("nan")]},
        {"scale": 0},
        {"extra": 1},
    ],
)
def test_invalid_arrow_handle_preserves_document(change):
    source = new_document()
    source["state"]["arrows"] = [{"kind": "arrow", "start": [0, 0], "end": [100, 50]}]
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    before = deepcopy(session.info)
    edit = {
        "kind": "arrow_handle",
        "id": 0,
        "handle": "end",
        "position": [100, 70],
        "previous": None,
        "scale": 1,
        **change,
    }
    with pytest.raises(ValueError):
        session.dispatch({"revision": 1, "action": "edit", "edit": edit})
    assert session.info == before and not session.state.history


@pytest.mark.parametrize("kind", sorted(VALID_ARROW_KINDS))
@pytest.mark.parametrize("end", [(100, 0), (0, 100), (-100, 0), (80, 60)])
@pytest.mark.parametrize(
    "text", ["k_1", "K_{2}CO_{3}\nΔG^{‡}", "heat & <cold>", "a  b\r\nc"]
)
def test_browser_arrow_label_positions_use_native_boxes(
    qt_application, kind, end, text
):
    from types import SimpleNamespace

    from PyQt6.QtWidgets import QGraphicsScene

    from chemvas.adapters.qt.renderer import Renderer
    from chemvas.ui.annotations.arrows import ArrowRenderer
    from tests.scene_render_context import attach_scene_render_context

    source = new_document()
    source["state"]["arrows"] = [
        {
            "kind": kind,
            "start": [0, 0],
            "end": list(end),
            "labels": {"above": text, "below": text},
            "control": [30, -40] if kind.startswith("curved_") else None,
        }
    ]
    settings = source["state"]["settings"]
    scene = QGraphicsScene()
    renderer = Renderer()
    context = attach_scene_render_context(
        SimpleNamespace(renderer=renderer, scene=lambda: scene)
    )
    style = context.state.text_style_state
    for key in (
        "text_font_family",
        "text_font_size",
        "text_font_weight",
        "text_italic",
        "text_color",
    ):
        setattr(style, key, settings[key])
    native = ArrowRenderer(context).create_from_state(source["state"]["arrows"][0])
    boxes = {child.data(1): child for child in native.childItems()}
    info = document_info(source)
    spec = info["drawing"]["label_measurements"]
    font = BrowserFontMeasurements(
        {
            "family": spec["family"],
            "metrics": {},
            "ink": {},
            "label_boxes": {
                label["key"]: [
                    boxes[label["side"]].boundingRect().width(),
                    boxes[label["side"]].boundingRect().height(),
                ]
                for label in spec["arrow_labels"]
            },
        }
    )
    drawing = document_info(source, font=font)["drawing"]
    for label in drawing["arrow_labels"]:
        child = boxes[label["side"]]
        assert (label["x"], label["y"]) == pytest.approx(
            (child.pos().x(), child.pos().y())
        )
        assert "<cold>" not in label["html"]


def test_arrow_label_edit_preserves_untouched_bytes_and_single_history():
    source = new_document()
    source["state"]["arrows"] = [{"kind": "arrow", "start": [0, 0], "end": [100, 0]}]
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    labels = {"above": "K_{2}CO_{3}\r\nheat", "below": "😀" * 200}
    change = {"kind": "arrow_labels", "id": 0, "labels": labels}
    changed = session.dispatch({"revision": 1, "action": "edit", "edit": change})
    assert changed["document"]["state"]["arrows"][0]["labels"] == labels
    assert changed["drawing"]["needs_measurements"]
    assert len(session.state.history) == 1
    session.dispatch({"revision": session.revision, "action": "edit", "edit": change})
    assert len(session.state.history) == 1
    preview = session.dispatch(
        {
            "revision": session.revision,
            "action": "label_preview",
            "labels": {"above": "<img src=x onerror=evil>", "below": "K_2"},
        }
    )
    assert preview["html"] == {
        "above": "&lt;img src=x onerror=evil&gt;",
        "below": "K<sub>2</sub>",
    }
    assert len(session.state.history) == 1
    session.dispatch({"revision": session.revision, "action": "undo"})
    assert session.info["document"] == source
    session.dispatch({"revision": session.revision, "action": "redo"})
    assert session.info["document"] == changed["document"]
    session.dispatch(
        {
            "revision": session.revision,
            "action": "edit",
            "edit": {
                "kind": "arrow_labels",
                "id": 0,
                "labels": {"above": " \n", "below": ""},
            },
        }
    )
    assert "labels" not in session.info["document"]["state"]["arrows"][0]


@pytest.mark.parametrize(
    "labels", [{"above": "x" * 201}, {"sideways": "x"}, {"above": 42}, []]
)
def test_invalid_arrow_labels_leave_history_untouched(labels):
    source = new_document()
    source["state"]["arrows"] = [{"kind": "arrow", "start": [0, 0], "end": [100, 0]}]
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    before = session.dispatch({"action": "read"})
    with pytest.raises(ValueError, match="Arrow labels"):
        session.dispatch(
            {
                "revision": 1,
                "action": "edit",
                "edit": {"kind": "arrow_labels", "id": 0, "labels": labels},
            }
        )
    assert session.dispatch({"action": "read"}) == before


@pytest.mark.parametrize(
    "box", [[float("nan"), 2], [0, 2], [1e9, 2], [True, 2], [2], "bad"]
)
def test_invalid_arrow_label_boxes_are_rejected(box):
    with pytest.raises(ValueError, match="bounded rich text boxes"):
        BrowserFontMeasurements(
            {
                "family": "Arial",
                "metrics": {},
                "ink": {},
                "label_boxes": {"a" * 64: box},
            }
        )


def test_arrow_label_measurement_accepts_wire_decimals_without_replaying_edit():
    source = new_document()
    source["state"]["arrows"] = [{"kind": "arrow", "start": [0, 0], "end": [100, 0]}]
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    changed = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {"kind": "arrow_labels", "id": 0, "labels": {"above": "H_2O"}},
        }
    )
    spec = changed["drawing"]["label_measurements"]
    font = {
        "family": spec["family"],
        "metrics": {},
        "ink": {},
        "label_boxes": {
            label["key"]: [Decimal("40.125"), Decimal("27.0")]
            for label in spec["arrow_labels"]
        },
    }
    measured = session.dispatch(
        {"revision": session.revision, "action": "measure", "font": font}
    )
    assert measured["revision"] == changed["revision"]
    assert measured["document"] == changed["document"]
    assert measured["drawing"]["arrow_labels"][0]["width"] == 40.125
    assert len(session.state.history) == 1
    before, accepted = session.info, session.font
    with pytest.raises(ValueError, match="do not match"):
        session.dispatch(
            {
                "revision": session.revision,
                "action": "measure",
                "font": {
                    "family": spec["family"],
                    "metrics": {},
                    "ink": {},
                    "label_boxes": {},
                },
            }
        )
    assert session.info is before and session.font is accepted


@pytest.mark.parametrize("kind", ["circle", "ellipse", "rounded_rect", "rect"])
@pytest.mark.parametrize("stroke", ["solid", "dashed", "dotted", "none"])
@pytest.mark.parametrize("end", [[0, 0], [3.9, 3.9], [4, 0], [90, 60], [-70, -40]])
def test_browser_shapes_match_native_creation_and_preview(
    desktop_canvas, kind, stroke, end
):
    from PyQt6.QtCore import QPointF

    from chemvas.ui.scene.scene_decoration_access import add_shape_from_points_for

    source = new_document()
    documents = desktop_canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    item = add_shape_from_points_for(
        desktop_canvas,
        QPointF(0, 0),
        QPointF(*end),
        shape_kind=kind,
        stroke_style=stroke,
    )
    expected = documents.snapshot_state()["shapes"]
    session = BrowserSession()
    change = {
        "kind": "shape",
        "start": [0, 0],
        "end": end,
        "style": kind,
        "stroke": stroke,
    }
    preview = session.dispatch({"revision": 0, "action": "preview", "edit": change})
    assert session.info["document"] == source and not session.state.history
    result = session.dispatch({"revision": 0, "action": "edit", "edit": change})
    assert result["document"] == preview["document"]
    assert extract_document_state(result["document"])["shapes"] == expected
    geometry = result["drawing"]["shapes"][0]
    rect = item.path().boundingRect()
    if not item.path().isEmpty():
        assert (
            geometry["x"],
            geometry["y"],
            geometry["width"],
            geometry["height"],
        ) == pytest.approx((rect.x(), rect.y(), rect.width(), rect.height()))
    assert geometry["line_width"] == item.pen().widthF()
    assert len(session.state.history) == 1
    assert session.dispatch({"revision": 1, "action": "undo"})["document"] == source
    assert (
        session.dispatch({"revision": 2, "action": "redo"})["document"]
        == result["document"]
    )


@pytest.mark.parametrize("kind", ["circle", "ellipse", "rounded_rect", "rect"])
@pytest.mark.parametrize("stroke", ["solid", "dashed", "dotted", "none"])
def test_browser_shape_move_and_delete_keep_native_records(
    desktop_canvas, kind, stroke
):
    source = new_document()
    source["state"]["shapes"] = [
        {
            "kind": "shape",
            "left": -50,
            "top": -30,
            "right": 80,
            "bottom": 60,
            "shape_kind": kind,
            "stroke_style": stroke,
            "fill": "#ffcc33",
            "fill_alpha": 1.0,
        }
    ]
    documents = desktop_canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    item = desktop_canvas.runtime_state.shape_items()[0]
    desktop_canvas.services.move_controller.move_item(
        item, 13, -9, update_selection=False
    )
    expected = documents.snapshot_state()["shapes"]
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    moved = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {
                "kind": "move",
                "selection": [{"target": "shape", "id": 0}] * 2,
                "dx": 13,
                "dy": -9,
            },
        }
    )
    assert extract_document_state(moved["document"])["shapes"] == expected
    deleted = session.dispatch(
        {
            "revision": 2,
            "action": "edit",
            "edit": {
                "kind": "delete_selection",
                "selection": [{"target": "shape", "id": 0}],
            },
        }
    )
    assert not deleted["document"]["state"]["shapes"]
    assert (
        session.dispatch({"revision": 3, "action": "undo"})["document"]
        == moved["document"]
    )
    assert session.dispatch({"revision": 4, "action": "undo"})["document"] == source


@pytest.mark.parametrize(
    "patch",
    [
        {"style": "triangle"},
        {"stroke": []},
        {"start": [True, 0]},
        {"end": [float("inf"), 0]},
        {"extra": 1},
    ],
)
def test_invalid_shape_creation_keeps_session_unchanged(patch):
    session = BrowserSession()
    before = session.dispatch({"action": "read"})
    with pytest.raises(ValueError):
        session.dispatch(
            {
                "revision": 0,
                "action": "edit",
                "edit": {
                    "kind": "shape",
                    "start": [0, 0],
                    "end": [80, 50],
                    "style": "rect",
                    "stroke": "solid",
                    **patch,
                },
            }
        )
    assert session.dispatch({"action": "read"}) == before


@pytest.mark.parametrize("depth", [-12, -10, -0.01, 0, 2, 3, 4, 10])
@pytest.mark.parametrize("preferred", [False, True])
@pytest.mark.parametrize(
    "point",
    [(0, 0), (0, 5.9), (0, 6.1), (50, 50), (30, 40), (40, 44), (-99, -99), (130, 130)],
)
def test_shape_background_preserves_native_structure_and_arrow_pick(
    desktop_canvas, preferred, point, depth
):
    from PyQt6.QtCore import QPointF

    from chemvas.ui.canvas.canvas_hit_testing_service import (
        scene_items_at_pos_for_canvas,
    )

    source = draw_bond(new_document())["document"]
    source["state"]["arrows"] = [{"kind": "arrow", "start": [-40, 0], "end": [40, 0]}]
    source["state"]["shapes"] = [
        {
            "kind": "shape",
            "left": -100,
            "top": -100,
            "right": 100,
            "bottom": 100,
            "shape_kind": "rect",
            "stroke_style": "none",
            "z": depth,
        }
    ]
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    hits = []
    for item in scene_items_at_pos_for_canvas(desktop_canvas, QPointF(*point)):
        kind = item.data(0)
        if kind in {"atom", "bond"}:
            hits.append({"target": kind, "id": item.data(1)})
        elif kind in {"arrow", "shape"}:
            hits.append({"target": kind, "id": 0})
    native = (
        desktop_canvas.services.selection.preferred_structure_item_at_scene_pos(
            QPointF(*point)
        )
        if preferred
        else desktop_canvas.services.hit_testing_service.item_at_scene_pos(
            QPointF(*point)
        )
    )
    expected = (
        None
        if native is None
        else {
            "target": native.data(0),
            "id": native.data(1) if native.data(0) in {"atom", "bond"} else 0,
        }
    )
    assert (
        BrowserStructureAdapter(extract_document_state(source)).pick_target(
            *point, hits, preferred=preferred, scale=1
        )
        == expected
    )


def test_custom_shape_stacking_is_editable():
    source = new_document()
    source["state"]["shapes"] = [
        {
            "kind": "shape",
            "left": 0,
            "top": 0,
            "right": 50,
            "bottom": 50,
            "shape_kind": "rect",
            "stroke_style": "solid",
            "z": 5,
        }
    ]
    assert document_info(source)["unsupported"] == []
    result = edit_document(
        {
            "document": source,
            "edit": {
                "kind": "delete_selection",
                "selection": [{"target": "shape", "id": 0}],
            },
        }
    )
    assert result["document"]["state"]["shapes"] == []


@pytest.mark.parametrize("kind", ["circle", "ellipse", "rounded_rect", "rect"])
@pytest.mark.parametrize(
    "anchor",
    [
        "shape_nw",
        "shape_n",
        "shape_ne",
        "shape_e",
        "shape_se",
        "shape_s",
        "shape_sw",
        "shape_w",
    ],
)
@pytest.mark.parametrize("position", [[-100, -100], [20, 30], [200, 200]])
def test_browser_shape_resize_matches_native_mutation(
    desktop_canvas, kind, anchor, position
):
    from PyQt6.QtCore import QPointF

    from chemvas.ui.tools.handle_mutation_service import HandleMutationService

    source = new_document()
    source["state"]["shapes"] = [
        {
            "kind": "shape",
            "left": 0,
            "top": 0,
            "right": 80,
            "bottom": 50,
            "shape_kind": kind,
            "stroke_style": "dashed",
            "fill": "#abcdef",
            "fill_alpha": 0.4,
        }
    ]
    documents = desktop_canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    item = desktop_canvas.runtime_state.shape_items()[0]
    HandleMutationService(desktop_canvas).update_shape_resize(
        item, anchor, QPointF(*position)
    )
    expected = documents.snapshot_state()["shapes"]
    session = BrowserSession()
    loaded = session.dispatch({"revision": 0, "action": "load", "document": source})
    change = {"kind": "shape_handle", "id": 0, "handle": anchor, "position": position}
    preview = session.dispatch({"revision": 1, "action": "preview", "edit": change})
    assert session.dispatch({"action": "read"}) == loaded
    result = session.dispatch({"revision": 1, "action": "edit", "edit": change})
    assert result["document"] == preview["document"]
    assert result["document"]["state"]["shapes"] == expected
    assert (
        session.dispatch({"revision": 2, "action": "undo"})["document"]
        == loaded["document"]
    )
    assert (
        session.dispatch({"revision": 3, "action": "redo"})["document"]
        == result["document"]
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"id": True},
        {"id": 50},
        {"handle": []},
        {"handle": "shape_bad"},
        {"position": [True, 0]},
        {"position": [float("inf"), 0]},
        {"extra": 0},
    ],
)
def test_shape_resize_rejects_invalid_edits_without_publication(patch):
    session = BrowserSession()
    before = session.dispatch(
        {
            "revision": 0,
            "action": "edit",
            "edit": {
                "kind": "shape",
                "start": [0, 0],
                "end": [80, 50],
                "style": "rect",
                "stroke": "solid",
            },
        }
    )
    with pytest.raises(ValueError):
        session.dispatch(
            {
                "revision": 1,
                "action": "edit",
                "edit": {
                    "kind": "shape_handle",
                    "id": 0,
                    "handle": "shape_se",
                    "position": [100, 80],
                    **patch,
                },
            }
        )
    assert session.dispatch({"action": "read"}) == before


@pytest.mark.parametrize(
    "depths", [[-10, -10, -10], [-12, -11.5, 4.5], [0, 3, 5], [5, 4, 4]]
)
@pytest.mark.parametrize("selected", [[0], [1, 2], [0, 1, 2], []])
@pytest.mark.parametrize("front", [True, False])
def test_browser_stacking_matches_native_history(
    desktop_canvas, depths, selected, front
):
    from chemvas.ui.scene.stacking_actions import stack_selection

    source = new_document()
    source["state"]["shapes"] = [
        dict(
            kind="shape",
            left=i * 50,
            top=0,
            right=i * 50 + 40,
            bottom=40,
            shape_kind="rect",
            stroke_style="solid",
            z=z,
        )
        for i, z in enumerate(depths)
    ]
    documents = desktop_canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    for i, item in enumerate(desktop_canvas.runtime_state.shape_items()):
        item.setSelected(i in selected)
    changed = stack_selection(desktop_canvas, front=front)
    expected = documents.snapshot_state()["shapes"]
    session = BrowserSession()
    before = session.dispatch({"revision": 0, "action": "load", "document": source})
    result = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {
                "kind": "stack",
                "selection": [{"target": "shape", "id": i} for i in selected],
                "front": front,
            },
        }
    )
    assert result["document"]["state"]["shapes"] == expected
    assert len(session.state.history) == int(changed)
    if changed:
        assert (
            session.dispatch({"revision": result["revision"], "action": "undo"})[
                "document"
            ]
            == before["document"]
        )
        assert (
            session.dispatch({"action": "redo", "revision": session.revision})[
                "document"
            ]
            == result["document"]
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"front": 1},
        {"front": "true"},
        {"selection": [{"target": "shape", "id": 99}]},
        {"extra": 0},
    ],
)
def test_stacking_rejects_invalid_input_without_publication(patch):
    session = BrowserSession()
    before = session.dispatch({"action": "read"})
    with pytest.raises(ValueError):
        session.dispatch(
            {
                "revision": 0,
                "action": "edit",
                "edit": {"kind": "stack", "selection": [], "front": True, **patch},
            }
        )
    assert session.dispatch({"action": "read"}) == before


@pytest.mark.parametrize(
    "color",
    [entry["color"] for entry in ui_spec()["color_palette"]] + ["#123456", "#FE0102"],
)
@pytest.mark.parametrize(
    "target", ["atom", "bond", "arrow", "shape", "orbital", "mixed"]
)
def test_browser_color_matches_native_mutation(desktop_canvas, color, target):
    from PyQt6.QtGui import QColor

    from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for

    source = draw_bond(new_document())["document"]
    source["state"]["arrows"] = [
        {"kind": "arrow", "start": [-100, 0], "end": [-40, 0], "labels": {"above": "A"}}
    ]
    source["state"]["shapes"] = [
        {
            "kind": "shape",
            "left": 100,
            "top": 100,
            "right": 180,
            "bottom": 150,
            "shape_kind": "rect",
            "stroke_style": "solid",
            "fill": "#abcdef",
            "fill_alpha": 0.4,
            "z": 4,
        }
    ]
    source["state"]["orbitals"] = [
        {"kind": "p", "center": [70, 20], "scale": 1, "rotation": 45}
    ]
    documents = desktop_canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    items = {
        "atom": visible_atom_item_for(desktop_canvas, 0),
        "bond": desktop_canvas.runtime_state.bond_graphics_state.bond_items[0][0],
        "arrow": desktop_canvas.runtime_state.arrow_items()[0],
        "shape": desktop_canvas.runtime_state.shape_items()[0],
        "orbital": desktop_canvas.runtime_state.orbital_items()[0],
    }
    kinds = list(items) if target == "mixed" else [target]
    desktop_canvas.services.canvas_color_mutation_service.apply_color_to_items(
        [items[kind] for kind in kinds], QColor(color)
    )
    expected = documents.snapshot_state()
    session = BrowserSession()
    loaded = session.dispatch({"revision": 0, "action": "load", "document": source})
    change = {
        "kind": "color",
        "color": color,
        "selection": [{"target": kind, "id": 0} for kind in kinds] * 2,
    }
    preview = session.dispatch({"revision": 1, "action": "preview", "edit": change})
    assert session.dispatch({"action": "read"}) == loaded
    result = session.dispatch({"revision": 1, "action": "edit", "edit": change})
    assert result["document"] == preview["document"]
    from chemvas.domain.document import arrow_from_state

    for key in ("model", "shapes"):
        assert result["document"]["state"][key] == expected[key]
    assert [
        arrow_from_state(item) for item in result["document"]["state"]["arrows"]
    ] == [arrow_from_state(item) for item in expected["arrows"]]
    assert result["document"]["state"]["orbitals"] == source["state"]["orbitals"]
    assert json.loads(json.dumps(expected["orbitals"])) == source["state"]["orbitals"]
    if result["document"] != loaded["document"]:
        assert len(session.state.history) == 1
        assert (
            session.dispatch({"revision": result["revision"], "action": "undo"})[
                "document"
            ]
            == loaded["document"]
        )
        assert (
            session.dispatch({"revision": session.revision, "action": "redo"})[
                "document"
            ]
            == result["document"]
        )
    else:
        assert not session.state.history


@pytest.mark.parametrize(
    "patch",
    [
        {"color": None},
        {"color": "red"},
        {"color": "#12345g"},
        {"color": "#12345600"},
        {"selection": [{"target": "shape", "id": 99}]},
        {"extra": 0},
    ],
)
def test_color_rejects_invalid_input_without_publication(patch):
    session = BrowserSession()
    before = session.dispatch({"action": "read"})
    with pytest.raises(ValueError):
        session.dispatch(
            {
                "revision": 0,
                "action": "edit",
                "edit": {"kind": "color", "color": "#123456", "selection": [], **patch},
            }
        )
    assert session.dispatch({"action": "read"}) == before


@pytest.mark.parametrize(
    "edit",
    [
        {"kind": "hover_shortcut", "key": "+"},
        {"kind": "hover_shortcut", "key": "o"},
        {"kind": "delete_hover"},
    ],
)
def test_hover_edits_skip_structure_under_a_mark(edit):
    source = draw_bond(new_document())["document"]
    atom = source["state"]["model"]["atoms"][0]
    source["state"]["marks"] = [
        {
            "kind": "plus",
            "text": None,
            "atom_id": None,
            "dx": None,
            "dy": None,
            "x": atom["x"] + 2,
            "y": atom["y"],
            "color": "#000000",
        }
    ]
    point = {"x": atom["x"] + 2, "y": atom["y"], "scale": 1}
    hits = [{"target": "mark", "id": 0}, {"target": "atom", "id": 0}]
    # The desktop hover finds no structure beneath the glyph.
    blocked = edit_document(
        {"document": source, "edit": {**edit, **point, "hits": hits}}
    )["document"]
    assert blocked["state"]["model"] == source["state"]["model"]
    if edit.get("key") == "+":
        return  # Placing a charge also needs measured fonts.
    changed = edit_document(
        {"document": source, "edit": {**edit, **point, "hits": hits[1:]}}
    )["document"]
    assert changed["state"]["model"] != source["state"]["model"]


def test_hidden_carbon_notice_ignores_uncolored_orbitals():
    source = draw_bond(new_document())["document"]
    source["state"]["orbitals"] = [
        {"kind": "s", "center": [200, 100], "scale": 1, "rotation": 0}
    ]
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    result = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {
                "kind": "color",
                "color": "#D84A3A",
                "selection": [
                    {"target": "atom", "id": 0},
                    {"target": "atom", "id": 1},
                    {"target": "orbital", "id": 0},
                ],
            },
        }
    )
    # The desktop filters colorable kinds first, so only hidden carbons remain.
    assert result["edit_notice"] == ui_spec()["color_messages"]["hidden"]
    assert "color" not in result["document"]["state"]["orbitals"][0]


@pytest.mark.parametrize(
    "hits,point", [([{"target": "atom", "id": 0}], [30, 40]), ([], [1000, 1000])]
)
def test_color_paint_uses_clicked_target_before_selection(hits, point):
    source = draw_bond(new_document())["document"]
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    result = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {
                "kind": "color",
                "color": "#D84A3A",
                "selection": [{"target": "bond", "id": 0}],
                "x": point[0],
                "y": point[1],
                "hits": hits,
                "scale": 1,
            },
        }
    )
    model = result["document"]["state"]["model"]
    assert model["atoms"][0]["color"] == ("#d84a3a" if hits else "#000000")
    assert model["bonds"][0]["color"] == ("#000000" if hits else "#d84a3a")
    assert result["edit_notice"] == (
        ui_spec()["color_messages"]["hidden"] if hits else None
    )
    assert session.dispatch({"action": "read"})["edit_notice"] is None


@pytest.mark.parametrize("fused", [False, True])
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("mode", ["atoms", "bonds", "partial", "empty", "ring"])
@pytest.mark.parametrize("color", ["#d84a3a", "#2f6ed3", "#ffffff"])
def test_ring_fill_matches_native_and_history(
    desktop_canvas, fused, existing, mode, color
):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QColor

    from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for
    from chemvas.ui.window.main_window_config import RING_FILL_GUIDANCE

    canvas = desktop_canvas
    builder = canvas.services.structure_build_service
    builder.add_benzene_ring(QPointF(100, 100))
    if fused:
        builder.add_benzene_ring(QPointF(100, 100), attach_bond_id=0)
    documents = canvas.services.canvas_document_session_service
    source = new_document()
    source["state"] = documents.snapshot_state()
    if not existing:
        source["state"]["ring_fills"] = []
    documents.apply_state(extract_document_state(source))
    atoms = [{"target": "atom", "id": i} for i in canvas.model.atoms]
    bonds = [{"target": "bond", "id": i} for i, b in enumerate(canvas.model.bonds) if b]
    rings = [
        {"target": "ring", "id": i}
        for i in range(len(canvas.runtime_state.ring_items()))
    ]
    selection = {
        "atoms": atoms,
        "bonds": bonds,
        "partial": atoms[:3] + bonds[3:6],
        "empty": [],
        "ring": rings,
    }[mode]
    items = []
    for hit in selection:
        if hit["target"] == "atom":
            items.append(visible_atom_item_for(canvas, hit["id"]))
        elif hit["target"] == "bond":
            items.append(
                canvas.runtime_state.bond_graphics_state.bond_items[hit["id"]][0]
            )
        else:
            items.append(canvas.runtime_state.ring_items()[hit["id"]])
    canvas.services.canvas_color_mutation_service.apply_ring_fill_color_to_items(
        items, QColor(color)
    )
    expected = documents.snapshot_state()
    session = BrowserSession()
    loaded = session.dispatch({"revision": 0, "action": "load", "document": source})
    change = {"kind": "ring_fill", "selection": selection * 2, "color": color}
    preview = session.dispatch({"revision": 1, "action": "preview", "edit": change})
    assert session.dispatch({"action": "read"}) == loaded
    result = session.dispatch({"revision": 1, "action": "edit", "edit": change})
    assert result["document"] == preview["document"]
    for key in ("model", "ring_fills"):
        assert result["document"]["state"][key] == expected[key]
    changed = result["document"] != loaded["document"]
    assert len(session.state.history) == int(changed)
    assert result["edit_notice"] == (None if changed else RING_FILL_GUIDANCE)
    if changed:
        assert (
            session.dispatch({"revision": 2, "action": "undo"})["document"]
            == loaded["document"]
        )
        assert (
            session.dispatch({"revision": 3, "action": "redo"})["document"]
            == result["document"]
        )
        session.dispatch({"revision": 4, "action": "edit", "edit": change})
        assert len(session.state.history) == 1


@pytest.mark.parametrize("preferred", [False, True])
@pytest.mark.parametrize("filled", [False, True])
@pytest.mark.parametrize("cover", [None, "arrow", "shape"])
@pytest.mark.parametrize(
    "point",
    [
        (100, 100),
        (100, 105),
        (100, 113),
        (110, 100),
        (117, 100),
        (100, 119),
        (140, 140),
    ],
)
def test_ring_pick_matches_native(desktop_canvas, preferred, filled, cover, point):
    from PyQt6.QtCore import QPointF

    from chemvas.ui.canvas.canvas_hit_testing_service import (
        scene_items_at_pos_for_canvas,
    )

    source = edit_document(
        {"document": new_document(), "edit": {"kind": "ring", "x": 100, "y": 100}}
    )["document"]
    if filled:
        source["state"]["ring_fills"][0].update(color="#f5d2ce", alpha=1)
    if cover == "arrow":
        source["state"]["arrows"] = [
            {"kind": "arrow", "start": [90, 100], "end": [110, 100]}
        ]
    if cover == "shape":
        source["state"]["shapes"] = [
            {
                "kind": "shape",
                "left": 90,
                "right": 110,
                "top": 90,
                "bottom": 110,
                "shape_kind": "rect",
                "stroke_style": "solid",
                "z": 4,
            }
        ]
    canvas = desktop_canvas
    canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )

    def target(item):
        if item is None:
            return None
        kind = item.data(0)
        if kind in {"atom", "bond"}:
            return {"target": kind, "id": item.data(1)}
        if kind in {"ring", "arrow", "shape"}:
            return {"target": kind, "id": 0}
        return None

    pos = QPointF(*point)
    hits = [
        hit
        for item in scene_items_at_pos_for_canvas(canvas, pos)
        if (hit := target(item))
    ]
    native = (
        canvas.services.selection.preferred_structure_item_at_scene_pos(pos)
        if preferred
        else canvas.services.hit_testing_service.item_at_scene_pos(pos)
    )
    adapter = BrowserStructureAdapter(extract_document_state(source))
    assert adapter.pick_target(
        *(Decimal(str(v)) for v in point), hits, preferred=preferred, scale=1
    ) == target(native)
    if point == (100, 100):
        assert target(native) == {"target": "ring", "id": 0}
        assert adapter.pick_target(*point, [], preferred=preferred, scale=1) == target(
            native
        )


@pytest.mark.parametrize("kind", ["color", "move", "delete_selection", "erase"])
def test_ring_actions_preserve_native_structure_and_history(desktop_canvas, kind):
    from PyQt6.QtGui import QColor

    canvas = desktop_canvas
    source = edit_document(
        {"document": new_document(), "edit": {"kind": "ring", "x": 100, "y": 100}}
    )["document"]
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    ring = canvas.runtime_state.ring_items()[0]
    change = {"kind": kind, "selection": [{"target": "ring", "id": 0}]}
    if kind == "color":
        canvas.services.canvas_color_mutation_service.apply_color_to_items(
            [ring], QColor("#d84a3a")
        )
        change.update(color="#d84a3a", x=100, y=100, hits=[], scale=1)
    elif kind == "move":
        canvas.services.move_controller.move_atoms(set(ring.data(2)), 13, -9)
        change.update(dx=13, dy=-9)
    else:
        canvas.scene().removeItem(ring)
        # Native ring deletion removes only the fill; the graph is unchanged.
        if kind == "erase":
            change = {"kind": kind, "x": 100, "y": 100, "hits": [], "scale": 1}
    expected = documents.snapshot_state()
    session = BrowserSession()
    loaded = session.dispatch({"revision": 0, "action": "load", "document": source})
    result = session.dispatch({"revision": 1, "action": "edit", "edit": change})
    assert result["document"]["state"]["model"] == expected["model"]
    if kind in {"delete_selection", "erase"}:
        assert result["document"]["state"]["ring_fills"] == []
    else:
        assert result["document"]["state"]["ring_fills"] == expected["ring_fills"]
    assert len(session.state.history) == 1
    assert (
        session.dispatch({"revision": 2, "action": "undo"})["document"]
        == loaded["document"]
    )
    assert (
        session.dispatch({"revision": 3, "action": "redo"})["document"]
        == result["document"]
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"color": None},
        {"color": "red"},
        {"color": "#123456ff"},
        {"selection": [{"target": "ring", "id": 99}]},
        {"extra": 0},
    ],
)
def test_ring_fill_rejects_invalid_input_without_publication(patch):
    session = BrowserSession()
    before = session.dispatch({"action": "read"})
    with pytest.raises(ValueError):
        session.dispatch(
            {
                "revision": 0,
                "action": "edit",
                "edit": {
                    "kind": "ring_fill",
                    "color": "#123456",
                    "selection": [],
                    **patch,
                },
            }
        )
    assert session.dispatch({"action": "read"}) == before


def _selection_parts_path(parts):
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QPainterPath, QPolygonF

    from chemvas.ui.selection.selection_outline_paths import selection_line_stroke_path

    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    for part in parts:
        if part.get("empty"):
            continue
        shape = part.get("shape", part)
        if "line" in shape:
            x1, y1, x2, y2 = shape["line"]
            path.addPath(
                selection_line_stroke_path(
                    QPointF(x1, y1), QPointF(x2, y2), shape["width"]
                )
            )
        elif "rect" in shape:
            rect = QRectF(*shape["rect"])
            corner = min(rect.width(), rect.height()) / 2
            path.addRoundedRect(rect, corner, corner)
        elif "polygon" in shape:
            path.addPolygon(QPolygonF([QPointF(*p) for p in shape["polygon"]]))
        else:
            for point in shape["dots"]:
                path.addEllipse(QPointF(*point), shape["radius"], shape["radius"])
    return path


@pytest.mark.parametrize("style", sorted(VALID_BOND_STYLES))
@pytest.mark.parametrize("length", [20, 40])
@pytest.mark.parametrize("ring", [False, True])
def test_browser_selection_bond_parts_match_native_paths(
    desktop_canvas, style, length, ring
):
    from PyQt6.QtCore import Qt

    source = new_document()
    source["state"]["settings"]["bond_length_px"] = length
    source = edit_document(
        {
            "document": source,
            "edit": {"kind": "ring", "x": 0, "y": 0}
            if ring
            else {"kind": "bond", "start": [0, 0], "end": [30, 14], "style": "single"},
        }
    )["document"]
    for bond in source["state"]["model"]["bonds"]:
        if bond:
            bond.update(
                style=style,
                order=3 if style == "triple" else 2 if "double" in style else 1,
            )
    info = document_info(source)
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    for key, parts in info["drawing"]["selection_bonds"].items():
        native = (
            desktop_canvas.services.selection.outline_service.selection_path_for_bond(
                int(key)
            )
        )
        native.setFillRule(Qt.FillRule.WindingFill)
        assert _selection_parts_path(parts) == native


@pytest.mark.parametrize(
    "selection",
    [
        [],
        [{"target": "atom", "id": 0}],
        [{"target": "bond", "id": 0}],
        [{"target": "ring", "id": 0}],
        [{"target": "atom", "id": 0}, {"target": "atom", "id": 2}],
        [{"target": "atom", "id": 0}, {"target": "atom", "id": 1}],
    ],
)
def test_selection_query_matches_native_components_without_document_changes(
    desktop_canvas, selection
):
    from chemvas.ui.selection.selection_outline_paths import simplified_outline_path

    session = BrowserSession()
    info = session.dispatch(
        {"revision": 0, "action": "edit", "edit": {"kind": "ring", "x": 0, "y": 0}}
    )
    before = deepcopy(session.info)
    result = session.dispatch(
        {"revision": 1, "action": "selection", "selection": selection}
    )
    assert (
        result["revision"] == 1
        and session.info == before
        and len(session.state.history) == 1
    )
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(info["document"])
    )
    for item in selection:
        kind, key = item["target"], item["id"]
        if kind == "atom":
            native_item = desktop_canvas.runtime_state.atom_graphics_state.atom_dots[
                key
            ]
        elif kind == "bond":
            native_item = desktop_canvas.runtime_state.bond_graphics_state.bond_items[
                key
            ][0]
        else:
            native_item = desktop_canvas.runtime_state.ring_items()[key]
        native_item.setSelected(True)
    desktop_canvas.services.selection.outline_service.update_selection_outline()
    native = [
        item.path()
        for item in desktop_canvas.runtime_state.selection_state.outlines
        if (item.data(2) or {}).get("kind") == "component"
    ]
    actual = [
        simplified_outline_path(_selection_parts_path(parts))
        for parts in result["components"]
    ]
    assert len(actual) == len(native)
    assert all(any(path == other for other in native) for path in actual)


@pytest.mark.parametrize(
    "patch",
    [
        {"revision": 0},
        {"selection": [{"target": "atom", "id": 99}]},
        {"selection": None},
        {"edit": {}},
        {"unexpected": True},
    ],
)
def test_selection_query_rejects_stale_or_invalid_requests_without_mutation(patch):
    session = BrowserSession()
    session.dispatch(
        {"revision": 0, "action": "edit", "edit": {"kind": "ring", "x": 0, "y": 0}}
    )
    before = deepcopy(session.info)
    with pytest.raises(ValueError):
        session.dispatch(
            {"revision": 1, "action": "selection", "selection": [], **patch}
        )
    assert (
        session.info == before
        and session.revision == 1
        and len(session.state.history) == 1
    )


def test_move_preview_returns_selection_components_from_the_same_candidate():
    session = BrowserSession()
    session.dispatch(
        {"revision": 0, "action": "edit", "edit": {"kind": "ring", "x": 0, "y": 0}}
    )
    selected = [{"target": "ring", "id": 0}]
    before = deepcopy(session.info)
    original = session.dispatch(
        {"revision": 1, "action": "selection", "selection": selected}
    )["components"]
    result = session.dispatch(
        {
            "revision": 1,
            "action": "preview",
            "edit": {"kind": "move", "selection": selected, "dx": 12, "dy": -8},
            "selection": selected,
        }
    )
    moved = result["selection_components"]
    assert len(moved) == len(original)
    for initial, after in zip(original[0], moved[0], strict=True):
        assert after["line"] == pytest.approx(
            [v + (12 if i % 2 == 0 else -8) for i, v in enumerate(initial["line"])]
        )
    assert (
        session.info == before
        and session.revision == 1
        and len(session.state.history) == 1
    )


@pytest.mark.parametrize("kind", ["circle", "ellipse", "rounded_rect", "rect"])
@pytest.mark.parametrize("stroke", ["solid", "dashed", "dotted", "none"])
@pytest.mark.parametrize("end", [[90, 60], [4, 0], [0, 40], [12, 8]])
def test_browser_shape_selection_encloses_native_outline(
    desktop_canvas, kind, stroke, end
):
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QPainterPath, QPainterPathStroker

    from chemvas.ui.scene.scene_decoration_access import add_shape_from_points_for

    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(new_document())
    )
    item = add_shape_from_points_for(
        desktop_canvas,
        QPointF(10, 15),
        QPointF(10 + end[0], 15 + end[1]),
        shape_kind=kind,
        stroke_style=stroke,
    )
    native = desktop_canvas.services.selection.outline_service.selection_path_for_object_item(
        item
    )
    result = edit_document(
        {
            "document": new_document(),
            "edit": {
                "kind": "shape",
                "start": [10, 15],
                "end": [10 + end[0], 15 + end[1]],
                "style": kind,
                "stroke": stroke,
            },
        }
    )
    part = result["drawing"]["shapes"][0]["selection"]
    shape = part["outline"]
    rect = QRectF(shape["x"], shape["y"], shape["width"], shape["height"])
    path = QPainterPath()
    if shape["kind"] == "ellipse":
        path.addEllipse(rect)
    elif shape["radius"]:
        path.addRoundedRect(rect, shape["radius"], shape["radius"])
    else:
        path.addRect(rect)
    if part["width"]:
        stroker = QPainterPathStroker()
        stroker.setWidth(part["width"])
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        path.addPath(stroker.createStroke(path))
    path.setFillRule(Qt.FillRule.WindingFill)
    assert path.boundingRect().getRect() == pytest.approx(
        native.boundingRect().getRect(), abs=0.05
    )
    # Qt applies two strokers then simplifies; SVG applies the combined stroke.
    # Compare the occupied region away from their curve-flattening fringe.
    fringe = QPainterPathStroker()
    fringe.setWidth(0.5)
    boundary = fringe.createStroke(native)
    bounds = native.boundingRect().adjusted(-1, -1, 1, 1)
    for xi in range(35):
        for yi in range(25):
            point = QPointF(
                bounds.left() + bounds.width() * xi / 34,
                bounds.top() + bounds.height() * yi / 24,
            )
            if not boundary.contains(point):
                assert path.contains(point) == native.contains(point), (
                    kind,
                    stroke,
                    end,
                    point,
                )


@pytest.mark.parametrize("length", [10, 20, 40])
@pytest.mark.parametrize(
    "text", ["CO2Me", "NHBoc", "O", "Cl", "NH2", "tBu", "Ph3P", "CH3CH2OH"]
)
@pytest.mark.parametrize("direction", ["left", "right", "vertical", "chain"])
def test_label_selection_uses_native_layout_bounds(
    desktop_canvas, length, text, direction
):
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QFont, QFontMetricsF, QTextDocument

    from chemvas.ui.selection.selection_style_access import (
        selection_indicator_rect_for_atom_for,
    )

    source = new_document()
    state = source["state"]
    adapter = BrowserStructureAdapter(state)
    adapter.model.add_atom(text, 120, 100)
    adapter.model.atoms[0].explicit_label = True
    for x, y in {
        "left": [(-1, 0)],
        "right": [(1, 0)],
        "vertical": [(0, -1)],
        "chain": [(-1, 0), (1, 0)],
    }[direction]:
        other = adapter.model.add_atom("C", 120 + x * length, 100 + y * length)
        adapter.model.add_bond(0, other)
    adapter.publish_model()
    state["settings"]["bond_length_px"] = length
    desktop_canvas.services.canvas_document_session_service.apply_state(state)
    item = desktop_canvas.runtime_state.atom_graphics_state.atom_items[0]
    spec = document_info(source)["drawing"]["label_measurements"]
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
            "bounding_width": fm.boundingRect(query["text"]).width(),
            "ascent": fm.ascent(),
            "descent": fm.descent(),
            "cap_height": fm.capHeight(),
            "line_height": document.size().height() - 2 * document.documentMargin(),
        }
    font_data = {
        "family": spec["family"],
        "metrics": measured,
        "ink": {f"{q['pixels']}:{q['text']}": [] for q in spec["queries"]},
    }
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    result = session.dispatch({"revision": 1, "action": "measure", "font": font_data})
    assert result["drawing"]["atom_selection_rects"]["0"] == pytest.approx(
        item.sceneBoundingRect().getRect(), abs=1e-8
    )
    before = deepcopy(session.info)
    outline = session.dispatch(
        {
            "revision": 1,
            "action": "selection",
            "selection": [{"target": "atom", "id": 0}],
        }
    )
    assert outline["components"][0][0]["rect"] == pytest.approx(
        selection_indicator_rect_for_atom_for(desktop_canvas, 0).getRect(), abs=1e-8
    )
    assert session.info == before and not session.state.history
    atom_ids = set(adapter.model.atoms)
    frame = session.dispatch(
        {
            "revision": 1,
            "action": "selection",
            "selection": [{"target": "atom", "id": i} for i in atom_ids],
        }
    )["frame"]
    bounds = QRectF()
    for rect in frame["rects"]:
        bounds = bounds.united(QRectF(*rect))
    pad = frame["padding"]
    native_frame = (
        desktop_canvas.services.selection.outline_service.selection_frame_rect(
            atom_ids, []
        )
    )
    assert bounds.adjusted(-pad, -pad, pad, pad).getRect() == pytest.approx(
        native_frame.getRect(), abs=1e-8
    )
    # Selection bounds are layout-owned even when the ink samples change.
    font_data["ink"] = {k: [[0, 0], [1, 0], [1, 1], [0, 1]] for k in font_data["ink"]}
    remeasured = session.dispatch(
        {"revision": 1, "action": "measure", "font": font_data}
    )
    assert (
        remeasured["drawing"]["atom_selection_rects"]
        == result["drawing"]["atom_selection_rects"]
    )
    assert (
        remeasured["drawing"]["atom_hit_rects"] != result["drawing"]["atom_hit_rects"]
    )


@pytest.mark.parametrize("width", [25.59, 25.6, 25.61])
def test_long_label_selection_threshold_uses_layout_margin(width):
    source = edit_document(
        {
            "document": new_document(),
            "edit": {"kind": "atom", "x": 120, "y": 100, "text": "NHBoc"},
        }
    )["document"]
    font = font_measurements_for(source)
    for metric in font["metrics"].values():
        metric["width"] = width
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    result = session.dispatch({"revision": 1, "action": "measure", "font": font})
    bounds = result["drawing"]["atom_selection_rects"]["0"]
    assert bounds[2] == pytest.approx(width + 12.8)
    outline = session.dispatch(
        {
            "revision": 1,
            "action": "selection",
            "selection": [{"target": "atom", "id": 0}],
        }
    )
    rect = outline["components"][0][0]["rect"]
    assert (rect[2] > 12.8 + 1e-8) == (bounds[2] > 38.4)


@pytest.mark.parametrize("angle", [-180, -37, 0, 15, 90, 180, "horizontal", "vertical"])
@pytest.mark.parametrize(
    "target", ["atom", "bond", "ring", "arrow", "shape", "mixed", "empty"]
)
def test_browser_selection_transform_matches_native_command_and_history(
    desktop_canvas, angle, target
):
    from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for

    source = edit_document(
        {"document": new_document(), "edit": {"kind": "ring", "x": -60, "y": 0}}
    )["document"]
    source["state"]["arrows"] = [
        {"kind": kind, "start": [30, -20], "end": [90, 40], "control": [130, -70]}
        for kind in VALID_ARROW_KINDS
    ]
    source["state"]["shapes"] = [
        {
            "kind": "shape",
            "left": 140,
            "top": 50,
            "right": 190,
            "bottom": 80,
            "shape_kind": kind,
            "stroke_style": stroke,
            "fill": "#ffcc33",
            "fill_alpha": 1.0,
        }
        for kind in ("circle", "ellipse", "rounded_rect", "rect")
        for stroke in ("solid", "dashed", "dotted", "none")
    ]
    documents = desktop_canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    # Start from the serialized native state so defaults and item IDs are identical.
    source["state"] = documents.snapshot_state()
    candidates = {
        "atom": [visible_atom_item_for(desktop_canvas, 0)],
        "bond": [desktop_canvas.runtime_state.bond_graphics_state.bond_items[0][0]],
        "ring": desktop_canvas.runtime_state.ring_items(),
        "arrow": desktop_canvas.runtime_state.arrow_items(),
        "shape": desktop_canvas.runtime_state.shape_items(),
    }
    selection = []
    for kind, items in candidates.items():
        if target not in (kind, "mixed"):
            continue
        for key, item in enumerate(items):
            item.setSelected(True)
            selection.append({"target": kind, "id": key})
    if isinstance(angle, str):
        desktop_canvas.services.scene_transform_controller.flip_selected_items(
            angle == "horizontal"
        )
    else:
        desktop_canvas.services.scene_transform_controller.rotate_selected_items(angle)
    expected = documents.snapshot_state()
    session = BrowserSession()
    loaded = session.dispatch({"revision": 0, "action": "load", "document": source})
    change = (
        {
            "kind": "flip",
            "selection": selection * 2,
            "horizontal": angle == "horizontal",
        }
        if isinstance(angle, str)
        else {"kind": "rotate", "selection": selection * 2, "value": angle}
    )
    preview = session.dispatch({"revision": 1, "action": "preview", "edit": change})
    assert session.dispatch({"action": "read"}) == loaded
    result = session.dispatch({"revision": 1, "action": "edit", "edit": change})
    assert result["document"] == preview["document"]
    pending = [
        (result["document"]["state"][key], expected[key])
        for key in ("model", "ring_fills", "arrows", "shapes")
    ]
    while pending:
        actual, native = pending.pop()
        if isinstance(native, dict):
            assert actual.keys() == native.keys()
            pending.extend((actual[key], value) for key, value in native.items())
        elif isinstance(native, (list, tuple)):
            assert len(actual) == len(native)
            pending.extend(zip(actual, native, strict=True))
        elif isinstance(native, float):
            # Qt path bounds and SVG path coordinates differ at machine precision.
            assert actual == pytest.approx(native, abs=1e-10, rel=0)
        else:
            assert actual == native
    changed = result["document"] != loaded["document"]
    assert len(session.state.history) == int(changed)
    if changed:
        assert (
            session.dispatch({"revision": 2, "action": "undo"})["document"]
            == loaded["document"]
        )
        assert (
            session.dispatch({"revision": 3, "action": "redo"})["document"]
            == result["document"]
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"value": -181},
        {"value": 181},
        {"value": True},
        {"value": float("nan")},
        {"value": float("inf")},
        {"value": "15"},
        {"unexpected": 1},
        {"selection": None},
        {"selection": [{"target": "atom", "id": 999}]},
        {"selection": [{"target": "shape", "id": 0}]},
    ],
)
def test_browser_rotation_rejects_invalid_request_without_mutation(patch):
    session = BrowserSession()
    source = draw_bond(new_document())["document"]
    before = session.dispatch({"revision": 0, "action": "load", "document": source})
    with pytest.raises(ValueError):
        session.dispatch(
            {
                "revision": 1,
                "action": "edit",
                "edit": {
                    "kind": "rotate",
                    "selection": [{"target": "bond", "id": 0}],
                    "value": 15,
                    **patch,
                },
            }
        )
    assert session.dispatch({"action": "read"}) == before
    assert not session.state.history


@pytest.mark.parametrize("kind", ["circle", "ellipse", "rounded_rect", "rect"])
@pytest.mark.parametrize("stroke", ["solid", "none"])
@pytest.mark.parametrize("size", [(0, 0), (0, 30), (50, 0), (50, 30)])
def test_rotation_center_matches_native_degenerate_shape_bounds(
    desktop_canvas, kind, stroke, size
):
    from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for

    source = draw_bond(new_document())["document"]
    source["state"]["shapes"] = [
        {
            "kind": "shape",
            "left": 120,
            "top": -70,
            "right": 120 + size[0],
            "bottom": -70 + size[1],
            "shape_kind": kind,
            "stroke_style": stroke,
        }
    ]
    documents = desktop_canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    source["state"] = documents.snapshot_state()
    visible_atom_item_for(desktop_canvas, 0).setSelected(True)
    desktop_canvas.runtime_state.shape_items()[0].setSelected(True)
    desktop_canvas.services.scene_transform_controller.rotate_selected_items(37)
    expected = documents.snapshot_state()
    actual = edit_document(
        {
            "document": source,
            "edit": {
                "kind": "rotate",
                "value": 37,
                "selection": [
                    {"target": "atom", "id": 0},
                    {"target": "shape", "id": 0},
                ],
            },
        }
    )["document"]["state"]
    assert actual["model"]["atoms"][0] == pytest.approx(
        expected["model"]["atoms"][0], abs=1e-10, rel=0
    )
    assert actual["shapes"][0] == pytest.approx(expected["shapes"][0], abs=1e-10, rel=0)


@pytest.mark.parametrize("shift", [False, True])
@pytest.mark.parametrize("end", [[100, 0], [31, 47], [0, 100], [-100, 0], [0, -100]])
def test_browser_drag_rotation_uses_original_press_state(desktop_canvas, shift, end):
    from PyQt6.QtCore import QPointF

    source = edit_document(
        {"document": new_document(), "edit": {"kind": "ring", "x": 0, "y": 0}}
    )["document"]
    documents = desktop_canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    desktop_canvas.services.selection.select_all()
    controller = desktop_canvas.services.scene_transform_controller
    drag = controller.begin_rotation_drag(QPointF(0, -100))
    assert drag is not None
    session = BrowserSession()
    loaded = session.dispatch({"revision": 0, "action": "load", "document": source})
    selection = [{"target": "ring", "id": 0}]
    edit = {
        "kind": "rotate",
        "selection": selection,
        "start": [0, -100],
        "end": end,
        "shift": shift,
    }
    # Neither native nor browser previews accumulate transforms or create history.
    for point in ([60, -20], end):
        controller.update_rotation_drag(
            drag, QPointF(*point), snap_step=15 if shift else None
        )
        result = session.dispatch(
            {
                "revision": 1,
                "action": "preview",
                "edit": {**edit, "end": point},
                "selection": selection,
            }
        )
        assert (
            result["document"]["state"]["model"] == documents.snapshot_state()["model"]
        )
        assert (
            result["document"]["state"]["ring_fills"]
            == documents.snapshot_state()["ring_fills"]
        )
        assert result["selection_frame"] is not None
        assert (
            session.dispatch({"action": "read"}) == loaded and not session.state.history
        )
    result = session.dispatch({"revision": 1, "action": "edit", "edit": edit})
    assert result["document"]["state"]["model"] == documents.snapshot_state()["model"]
    assert len(session.state.history) == (end != [0, -100])
    if session.state.history:
        assert session.dispatch({"revision": 2, "action": "undo"})["document"] == source
        assert (
            session.dispatch({"revision": 3, "action": "redo"})["document"]
            == result["document"]
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"start": [True, 0]},
        {"start": [0]},
        {"start": None},
        {"end": [0, float("nan")]},
        {"end": [float("inf"), 0]},
        {"shift": 1},
        {"shift": None},
        {"value": 15},
    ],
)
def test_browser_drag_rotation_rejects_invalid_inputs(patch):
    session = BrowserSession()
    before = session.dispatch({"action": "read"})
    with pytest.raises(ValueError):
        session.dispatch(
            {
                "revision": 0,
                "action": "edit",
                "edit": {
                    "kind": "rotate",
                    "selection": [],
                    "start": [0, -100],
                    "end": [100, 0],
                    "shift": False,
                    **patch,
                },
            }
        )
    assert session.dispatch({"action": "read"}) == before


@pytest.mark.parametrize(
    "target,kind",
    [("atom", None), ("bond", None), ("ring", None)]
    + [("arrow", kind) for kind in VALID_ARROW_KINDS]
    + [("shape", kind) for kind in ("circle", "ellipse", "rounded_rect", "rect")],
)
@pytest.mark.parametrize("end", [[110, 50], [-60, -20]])
def test_browser_selection_frame_matches_native_bounds(
    desktop_canvas, target, kind, end
):
    from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for

    source = edit_document(
        {"document": new_document(), "edit": {"kind": "ring", "x": 0, "y": 0}}
    )["document"]
    source["state"]["arrows"] = (
        [{"kind": kind, "start": [-60, -20], "end": end, "control": [100, -80]}]
        if target == "arrow"
        else []
    )
    source["state"]["shapes"] = (
        [
            {
                "kind": "shape",
                "left": 40,
                "top": 10,
                "right": 140,
                "bottom": 70,
                "shape_kind": kind,
                "stroke_style": "solid",
            }
        ]
        if target == "shape"
        else []
    )
    documents = desktop_canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    item = {
        "atom": lambda: visible_atom_item_for(desktop_canvas, 0),
        "bond": lambda: desktop_canvas.runtime_state.bond_graphics_state.bond_items[0][
            0
        ],
        "ring": lambda: desktop_canvas.runtime_state.ring_items()[0],
        "arrow": lambda: desktop_canvas.runtime_state.arrow_items()[0],
        "shape": lambda: desktop_canvas.runtime_state.shape_items()[0],
    }[target]()
    item.setSelected(True)
    desktop_canvas.services.selection.outline_service.update_selection_outline()
    native = [
        item.path().boundingRect()
        for item in desktop_canvas.runtime_state.selection_state.outlines
        if (item.data(2) or {}).get("kind") == "frame"
    ]
    session = BrowserSession()
    loaded = session.dispatch({"revision": 0, "action": "load", "document": source})
    frame = session.dispatch(
        {
            "revision": 1,
            "action": "selection",
            "selection": [{"target": target, "id": 0}],
        }
    )["frame"]
    if not native:
        assert frame is None
        return
    result = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            (
                "import {readFileSync} from 'node:fs'; import {selectionFrameMarkup} from './app/chemvas/web/scene.mjs'; "
                "const p=JSON.parse(readFileSync(0,'utf8')); console.log(selectionFrameMarkup(p.frame,p.drawing,p.handles,1).outline);"
            ),
        ],
        cwd=ROOT,
        input=json.dumps(
            {
                "frame": frame,
                "drawing": loaded["drawing"],
                "handles": ui_spec()["handles"],
            }
        ),
        text=True,
        capture_output=True,
        check=True,
    )
    actual = [
        float(re.search(rf'\b{name}="([^"]+)"', result.stdout).group(1))
        for name in ("x", "y", "width", "height")
    ]
    # Control bounds plus half-pen approximate Qt's cubic stroke control bounds.
    tolerance = loaded["drawing"]["arrows"][0]["width"] if target == "arrow" else 1e-3
    assert actual == pytest.approx(native[0].getRect(), abs=tolerance, rel=0)
    assert session.dispatch({"action": "read"}) == loaded and not session.state.history


@pytest.mark.parametrize("kind", ["curved_single", "curved_double"])
@pytest.mark.parametrize("control", [None, [100, -80], [-1000, 1000]])
@pytest.mark.parametrize("width", [0.5, 1.5, 6])
@pytest.mark.parametrize("end", [[110, 50], [0, 0], [-60, -20]])
def test_curved_frame_bounds_follow_native_subdivision(
    desktop_canvas, kind, control, width, end
):
    source = new_document()
    source["state"]["settings"]["arrow_line_width"] = width
    record = {"kind": kind, "start": [-60, -20], "end": end}
    if control is not None:
        record["control"] = control
    source["state"]["arrows"] = [record]
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    item = desktop_canvas.runtime_state.arrow_items()[0]
    geometry = document_info(source)["drawing"]["arrows"][0]
    actual = arrow_frame_bounds(geometry)
    # Qt's stroked cubic control envelope includes small cap/join excursions.
    # A half-pen tolerance also bounds the remaining independent-side subdivision difference.
    assert actual == pytest.approx(
        item.sceneBoundingRect().getRect(), abs=width / 2, rel=0
    )


@pytest.mark.parametrize("horizontal", [True, False])
@pytest.mark.parametrize(
    "kind", ["equilibrium", "equilibrium_forward", "equilibrium_reverse"]
)
def test_browser_flip_rejects_collapsed_equilibrium_atomically(kind, horizontal):
    source = draw_bond(new_document())["document"]
    source["state"]["arrows"] = [{"kind": kind, "start": [70, 20], "end": [70, 20]}]
    session = BrowserSession()
    before = session.dispatch({"revision": 0, "action": "load", "document": source})
    change = {
        "kind": "flip",
        "horizontal": horizontal,
        "selection": [{"target": "bond", "id": 0}, {"target": "arrow", "id": 0}],
    }
    for action in ("preview", "edit"):
        with pytest.raises(ValueError, match="zero-length equilibrium"):
            session.dispatch({"revision": 1, "action": action, "edit": change})
        assert session.dispatch({"action": "read"}) == before
        assert not session.state.history


@pytest.mark.parametrize(
    "patch",
    [
        {"horizontal": 1},
        {"horizontal": "false"},
        {"horizontal": None},
        {"value": 15},
        {"start": [0, 0]},
        {"selection": None},
        {"selection": [{"target": "bond", "id": 999}]},
    ],
)
def test_browser_flip_rejects_invalid_input(patch):
    session = BrowserSession()
    before = session.dispatch(
        {
            "revision": 0,
            "action": "load",
            "document": draw_bond(new_document())["document"],
        }
    )
    change = {
        "kind": "flip",
        "selection": [{"target": "bond", "id": 0}],
        "horizontal": True,
        **patch,
    }
    with pytest.raises(ValueError):
        session.dispatch({"revision": 1, "action": "edit", "edit": change})
    assert session.dispatch({"action": "read"}) == before
    assert not session.state.history


@pytest.mark.parametrize("horizontal", [True, False])
@pytest.mark.parametrize("mirrored", [True, False])
@pytest.mark.parametrize("end", [(90, 40), (-90, 40), (30, -80)])
def test_browser_flip_preserves_native_arrow_labels_and_direction(
    desktop_canvas, horizontal, mirrored, end
):
    from chemvas.domain.document import VALID_EQUILIBRIUM_KINDS

    source = new_document()
    source["state"]["arrows"] = [
        {
            "kind": kind,
            "start": [30, -20],
            "end": list(end),
            "control": [130, -70],
            "labels": {"above": "NHBoc", "below": "H_2O"},
            **({"mirrored": mirrored} if kind in VALID_EQUILIBRIUM_KINDS else {}),
        }
        for kind in VALID_ARROW_KINDS
    ]
    documents = desktop_canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    source["state"] = documents.snapshot_state()
    items = desktop_canvas.runtime_state.arrow_items()
    for item in items:
        item.setSelected(True)
    desktop_canvas.services.scene_transform_controller.flip_selected_items(horizontal)
    expected = documents.snapshot_state()["arrows"]
    result = edit_document(
        {
            "document": source,
            "edit": {
                "kind": "flip",
                "horizontal": horizontal,
                "selection": [{"target": "arrow", "id": i} for i in range(len(items))],
            },
        }
    )
    for actual, native in zip(
        result["document"]["state"]["arrows"], expected, strict=True
    ):
        assert actual.keys() == native.keys()
        for key, value in native.items():
            if key in ("start", "end", "control") and value is not None:
                assert actual[key] == pytest.approx(value, abs=1e-10, rel=0)
            else:
                assert actual[key] == value


@pytest.mark.parametrize(
    "mode",
    ["left", "center", "right", "top", "middle", "bottom", "horizontal", "vertical"],
)
@pytest.mark.parametrize(
    "target", ["atom", "bond", "ring", "annotation", "mixed", "empty"]
)
def test_browser_arrangement_matches_native_whole_objects(desktop_canvas, mode, target):
    from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for

    source = new_document()
    for x, y in ((-100, -80), (20, 30), (200, 110)):
        source = edit_document(
            {"document": source, "edit": {"kind": "ring", "x": x, "y": y}}
        )["document"]
    source["state"]["arrows"] = [
        {"kind": "line", "start": [x, y], "end": [x + 60, y + 30]}
        for x, y in ((-50, -120), (100, 60), (260, 150))
    ]
    source["state"]["shapes"] = [
        {
            "kind": "shape",
            "left": x,
            "top": y,
            "right": x + 50,
            "bottom": y + 20,
            "shape_kind": kind,
            "stroke_style": "solid",
        }
        for (x, y), kind in zip(
            ((30, -130), (140, -90), (270, 30), (330, 180)),
            ("circle", "ellipse", "rect", "rounded_rect"),
            strict=True,
        )
    ]
    documents = desktop_canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    source["state"] = documents.snapshot_state()
    selection = []
    for i in range(3):
        if target in ("atom", "mixed"):
            visible_atom_item_for(desktop_canvas, i * 6).setSelected(True)
            selection.append({"target": "atom", "id": i * 6})
        elif target == "bond":
            desktop_canvas.runtime_state.bond_graphics_state.bond_items[i * 6][
                0
            ].setSelected(True)
            selection.append({"target": "bond", "id": i * 6})
        elif target == "ring":
            desktop_canvas.runtime_state.ring_items()[i].setSelected(True)
            selection.append({"target": "ring", "id": i})
    if target in ("annotation", "mixed"):
        for kind, items in (
            ("arrow", desktop_canvas.runtime_state.arrow_items()),
            ("shape", desktop_canvas.runtime_state.shape_items()),
        ):
            for i, item in enumerate(items):
                item.setSelected(True)
                selection.append({"target": kind, "id": i})
    distribute = mode in ("horizontal", "vertical")
    controller = desktop_canvas.services.scene_transform_controller
    (
        controller.distribute_selected_items
        if distribute
        else controller.align_selected_items
    )(mode)
    expected = documents.snapshot_state()
    session = BrowserSession()
    before = session.dispatch({"revision": 0, "action": "load", "document": source})
    edit = {
        "kind": "distribute" if distribute else "align",
        "mode": mode,
        "selection": selection * 2,
    }
    preview = session.dispatch({"revision": 1, "action": "preview", "edit": edit})
    assert session.dispatch({"action": "read"}) == before
    result = session.dispatch({"revision": 1, "action": "edit", "edit": edit})
    assert result["document"] == preview["document"]
    pending = [
        (result["document"]["state"][key], expected[key])
        for key in ("model", "ring_fills", "arrows", "shapes")
    ]
    while pending:
        actual, native = pending.pop()
        if isinstance(native, dict):
            assert actual.keys() == native.keys()
            pending.extend((actual[key], value) for key, value in native.items())
        elif isinstance(native, (list, tuple)):
            assert len(actual) == len(native)
            pending.extend(zip(actual, native, strict=True))
        elif isinstance(native, float):
            assert actual == pytest.approx(native, abs=1e-8, rel=0)
        else:
            assert actual == native
    changed = result["document"] != before["document"]
    assert len(session.state.history) == int(changed)
    if changed:
        assert (
            session.dispatch({"revision": 2, "action": "undo"})["document"]
            == before["document"]
        )
        assert (
            session.dispatch({"revision": 3, "action": "redo"})["document"]
            == result["document"]
        )


@pytest.mark.parametrize("kind", ["align", "distribute"])
@pytest.mark.parametrize(
    "patch",
    [
        {"mode": "diagonal"},
        {"mode": None},
        {"mode": True},
        {"mode": []},
        {"unexpected": 1},
        {"selection": None},
        {"selection": [{"target": "atom", "id": 999}]},
    ],
)
def test_browser_arrangement_rejects_invalid_request(kind, patch):
    session = BrowserSession()
    before = session.dispatch(
        {
            "revision": 0,
            "action": "load",
            "document": draw_bond(new_document())["document"],
        }
    )
    edit = {
        "kind": kind,
        "mode": "left" if kind == "align" else "horizontal",
        "selection": [{"target": "bond", "id": 0}],
        **patch,
    }
    with pytest.raises(ValueError):
        session.dispatch({"revision": 1, "action": "edit", "edit": edit})
    assert session.dispatch({"action": "read"}) == before
    assert not session.state.history


def test_browser_alignment_requires_actual_label_layout():
    source = edit_document(
        {
            "document": new_document(),
            "edit": {"kind": "atom", "x": 0, "y": 0, "text": "NHBoc"},
        }
    )["document"]
    session = BrowserSession()
    before = session.dispatch({"revision": 0, "action": "load", "document": source})
    with pytest.raises(ValueError, match="completed font measurements"):
        session.dispatch(
            {
                "revision": 1,
                "action": "edit",
                "edit": {
                    "kind": "align",
                    "mode": "left",
                    "selection": [{"target": "atom", "id": 0}],
                },
            }
        )
    assert session.dispatch({"action": "read"}) == before


@pytest.mark.parametrize(
    "mode",
    ["left", "center", "right", "top", "middle", "bottom", "horizontal", "vertical"],
)
@pytest.mark.parametrize("text", ["NHBoc", "O", "CO2Me"])
def test_browser_alignment_uses_native_full_label_bounds(desktop_canvas, mode, text):
    from PyQt6.QtGui import QFont, QFontMetricsF, QTextDocument

    from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for

    source = new_document()
    adapter = BrowserStructureAdapter(source["state"])
    for x, y in ((-100, -80), (30, 20), (240, 130)):
        i = adapter.model.add_atom(text, x, y)
        adapter.model.atoms[i].explicit_label = True
    adapter.publish_model()
    docs = desktop_canvas.services.canvas_document_session_service
    docs.apply_state(extract_document_state(source))
    source["state"] = docs.snapshot_state()
    item = visible_atom_item_for(desktop_canvas, 0)
    spec = document_info(source)["drawing"]["label_measurements"]
    metrics = {}
    for query in spec["queries"]:
        font = QFont(item.font())
        font.setPointSizeF(query["size"])
        fm = QFontMetricsF(font)
        document = QTextDocument()
        document.setDefaultFont(font)
        document.setPlainText(query["text"])
        metrics[query["key"]] = {
            "width": fm.horizontalAdvance(query["text"]),
            "bounding_width": fm.boundingRect(query["text"]).width(),
            "ascent": fm.ascent(),
            "descent": fm.descent(),
            "cap_height": fm.capHeight(),
            "line_height": document.size().height() - 2 * document.documentMargin(),
        }
    for i in range(3):
        visible_atom_item_for(desktop_canvas, i).setSelected(True)
    distribute = mode in ("horizontal", "vertical")
    controller = desktop_canvas.services.scene_transform_controller
    (
        controller.distribute_selected_items
        if distribute
        else controller.align_selected_items
    )(mode)
    expected = docs.snapshot_state()["model"]["atoms"]
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    session.dispatch(
        {
            "revision": 1,
            "action": "measure",
            "font": {
                "family": spec["family"],
                "metrics": metrics,
                "ink": {f"{q['pixels']}:{q['text']}": [] for q in spec["queries"]},
            },
        }
    )
    actual = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {
                "kind": "distribute" if distribute else "align",
                "mode": mode,
                "selection": [{"target": "atom", "id": i} for i in range(3)],
            },
        }
    )["document"]["state"]["model"]["atoms"]
    for i, atom in expected.items():
        assert (actual[i]["x"], actual[i]["y"]) == pytest.approx(
            (atom["x"], atom["y"]), abs=1e-8, rel=0
        )


@pytest.mark.parametrize(
    "size", ["A0", "A1", "A2", "A3", "A4", "A5", "Letter", "Legal", "Tabloid", "Custom"]
)
@pytest.mark.parametrize("orientation", ["landscape", "portrait"])
@pytest.mark.parametrize("custom", [(10, 2000), (123.456, 234.567)])
def test_browser_sheet_setup_matches_native_and_preserves_drawing(
    desktop_canvas, size, orientation, custom
):
    from chemvas.ui.canvas.sheet_setup_logic import sheet_dimensions_px
    from chemvas.ui.canvas.sheet_setup_service import change_sheet_setup_for

    source = draw_bond(new_document(), (200, 150), (220, 150))["document"]
    source["state"]["settings"].update(
        sheet_size="Custom", sheet_custom_size_mm=(300, 200)
    )
    documents = desktop_canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    source["state"] = documents.snapshot_state()
    change_sheet_setup_for(
        desktop_canvas, size, orientation, custom if size == "Custom" else None
    )
    expected = documents.snapshot_state()
    session = BrowserSession()
    before = session.dispatch({"revision": 0, "action": "load", "document": source})
    edit = {
        "kind": "sheet_setup",
        "size": size,
        "orientation": orientation,
        "custom_size_mm": custom if size == "Custom" else None,
    }
    preview = session.dispatch({"revision": 1, "action": "preview", "edit": edit})
    assert session.dispatch({"action": "read"}) == before
    result = session.dispatch({"revision": 1, "action": "edit", "edit": edit})
    assert result["document"] == preview["document"]
    assert result["document"]["state"] == expected
    assert result["document"]["state"]["model"] == before["document"]["state"]["model"]
    assert result["sheet"] == list(
        sheet_dimensions_px(size, orientation, custom if size == "Custom" else None)
    )
    assert len(session.state.history) == 1
    assert (
        session.dispatch({"revision": 2, "action": "undo"})["document"]
        == before["document"]
    )
    assert (
        session.dispatch({"revision": 3, "action": "redo"})["document"]
        == result["document"]
    )
    session.dispatch({"revision": 4, "action": "edit", "edit": edit})
    assert len(session.state.history) == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"size": []},
        {"orientation": []},
        {"size": "A6"},
        {"orientation": "sideways"},
        {"custom_size_mm": None},
        {"custom_size_mm": [10]},
        {"custom_size_mm": [True, 20]},
        {"custom_size_mm": [9.99, 20]},
        {"custom_size_mm": [20, 2000.01]},
        {"custom_size_mm": ["10", 20]},
        {"extra": 1},
    ],
)
def test_browser_sheet_setup_rejects_invalid_without_history(patch):
    session = BrowserSession()
    before = session.dispatch({"action": "read"})
    edit = {
        "kind": "sheet_setup",
        "size": "Custom",
        "orientation": "landscape",
        "custom_size_mm": [100, 200],
        **patch,
    }
    with pytest.raises(ValueError):
        session.dispatch({"revision": 0, "action": "edit", "edit": edit})
    assert session.dispatch({"action": "read"}) == before
    assert not session.state.history


@pytest.mark.parametrize("grid", [None, True, 1, [], {}, "triangular"])
def test_browser_grid_rejects_invalid_mode_without_publication(grid):
    session = BrowserSession()
    before = session.dispatch({"action": "read"})
    with pytest.raises(ValueError, match="grid mode"):
        session.dispatch(
            {
                "revision": 0,
                "action": "edit",
                "edit": {
                    "kind": "arrow",
                    "grid": grid,
                    "start": [13, 17],
                    "end": [81, 49],
                    "style": "reaction",
                    "dragged": True,
                    "shift": False,
                    "scale": 1,
                },
            }
        )
    assert session.dispatch({"action": "read"}) == before
    assert not session.state.history


def test_grid_cannot_silently_change_bond_input():
    with pytest.raises(ValueError, match="only applies"):
        edit_document(
            {
                "document": new_document(),
                "edit": {
                    "kind": "bond",
                    "grid": "square",
                    "start": [13, 17],
                    "end": [81, 49],
                    "style": "single",
                },
            }
        )


@pytest.mark.parametrize(
    "kind,text",
    [
        ("plus", None),
        ("minus", None),
        ("circled_plus", None),
        ("circled_minus", None),
        ("radical", None),
        ("plus", ""),
        ("plus", "2+"),
        ("minus", "δ−"),
        ("plus", "<x>"),
        ("plus", "+\n-"),
        ("plus", "\n+\n"),
        ("plus", "++\r\n-"),
        ("plus", "NH2"),
    ],
)
@pytest.mark.parametrize("length", [10, 20, 40])
@pytest.mark.parametrize("attached", [False, True])
def test_browser_mark_rendering_matches_native(
    desktop_canvas, kind, text, length, attached
):
    from decimal import Decimal

    from PyQt6.QtGui import QFont, QFontMetricsF, QPainterPath, QTextDocument

    source = new_document()
    source["state"]["settings"]["bond_length_px"] = length
    if attached:
        source = draw_bond(source)["document"]
    source["state"]["marks"] = [
        {
            "kind": kind,
            "text": text,
            "atom_id": 0 if attached else None,
            "dx": 11 if attached else None,
            "dy": -7 if attached else None,
            "x": 100,
            "y": 100,
            "color": "#123456",
        }
    ]
    before = deepcopy(source)
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    item = desktop_canvas.runtime_state.mark_items()[0]
    expected_center = (
        desktop_canvas.services.scene_decoration_build_service.mark_center(item)
    )
    spec = document_info(source)["drawing"]["label_measurements"]
    measurements = {"family": spec["family"], "metrics": {}, "ink": {}}
    for query in spec["queries"]:
        font = QFont(spec["family"])
        font.setPointSizeF(query["size"])
        fm = QFontMetricsF(font)
        document = QTextDocument()
        document.setDefaultFont(font)
        document.setDocumentMargin(0)
        document.setPlainText(query["text"])
        measurements["metrics"][query["key"]] = {
            "width": fm.horizontalAdvance(query["text"]),
            "bounding_width": fm.boundingRect(query["text"]).width(),
            "ascent": fm.ascent(),
            "descent": fm.descent(),
            "cap_height": fm.capHeight(),
            "line_height": document.size().height(),
        }
        measurements["ink"][f"{query['pixels']}:{query['text']}"] = []
    measurements = json.loads(json.dumps(measurements), parse_float=Decimal)
    info = document_info(source, font=BrowserFontMeasurements(measurements))
    assert bool(info["unsupported"]) == attached
    assert source == before
    mark = info["drawing"]["marks"][0]
    assert (mark["x"], mark["y"]) == (expected_center.x(), expected_center.y())
    assert mark["color"] == "#123456"
    assert mark["bounds"] == pytest.approx(
        item.sceneBoundingRect().getRect(), abs=1e-10
    )
    if kind == "radical":
        assert mark["radius"] * 2 == item.rect().width()
    elif kind.startswith("circled_"):
        assert mark["radius"] * 2 == item.path().boundingRect().width()
        assert mark["stroke"] == item.pen().widthF()
    else:
        path = QPainterPath()
        for run in mark["runs"]:
            font = QFont(spec["family"])
            font.setPointSizeF(run["size"])
            path.addText(run["x"], run["y"], font, run["text"])
        assert path.boundingRect().getRect() == pytest.approx(
            item.mapToScene(item.glyph_path()).boundingRect().getRect(), abs=1 / 64
        )
    if attached:
        # The imported fixture deliberately has no matching atom annotation.
        with pytest.raises(ValueError, match="read-only"):
            edit_document(
                {"document": source, "edit": {"kind": "bond_length", "value": 30}}
            )
    else:
        changed = edit_document(
            {"document": source, "edit": {"kind": "bond_length", "value": 30}},
            font=BrowserFontMeasurements(measurements),
        )
        assert changed["document"]["state"]["marks"] == source["state"]["marks"]


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "circled_plus", "circled_minus", "radical"]
)
@pytest.mark.parametrize("selection", ["mark", "atom", "both", "mixed"])
@pytest.mark.parametrize("delta", [(10, 7), (-12.5, 3.25), (0, 0)])
def test_browser_mark_move_port_matches_native_drag(
    desktop_canvas, kind, selection, delta
):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(20, 20), QPointF(40, 20), "single", 1
    )
    marks = canvas.services.canvas_mark_scene_service
    bound = marks.add_mark_for_atom(0, QPointF(10, 8), kind=kind)
    free = canvas.services.scene_decoration_service.add_mark(QPointF(90, 60), kind=kind)
    other = marks.add_mark_for_atom(1, QPointF(50, 8), kind=kind)
    snapshot = canvas.services.canvas_document_session_service.snapshot_state
    before = snapshot()
    candidate = deepcopy(before)
    adapter = BrowserStructureAdapter(candidate)
    atom_ids = {0} if selection in {"atom", "both", "mixed"} else set()
    selected = [] if selection == "atom" else [bound]
    request = [{"target": "atom", "id": i} for i in atom_ids]
    if selected:
        request.append({"target": "mark", "id": 0})
    if selection == "mixed":
        selected += [free, other]
        request += [{"target": "mark", "id": 1}, {"target": "mark", "id": 2}]
    tool = canvas.services.tool_controller.tools["select"]
    assert tool._begin_selection_drag(atom_ids, selected, QPointF())
    tool._apply_drag_delta(QPointF(*delta))
    tool._commit_selection_drag()
    adapter.move_selection(request, *delta)
    assert candidate == snapshot()
    assert candidate["model"]["atom_annotations"] == before["model"]["atom_annotations"]
    assert [m["atom_id"] for m in candidate["marks"]] == [0, None, 1]
    if delta != (0, 0):
        canvas.services.history_service.undo()
        assert snapshot() == before


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "circled_plus", "circled_minus", "radical"]
)
@pytest.mark.parametrize(
    "isolated,selection",
    [
        (False, "mark"),
        (False, "bond"),
        (False, "both"),
        (False, "free"),
        (True, "mark"),
        (True, "free"),
    ],
)
def test_browser_mark_delete_port_matches_native(
    desktop_canvas, kind, selection, isolated
):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(20, 20), QPointF(40, 20), "single", 1
    )
    canvas.services.canvas_mark_scene_service.add_mark_for_atom(
        0, QPointF(10, 8), kind=kind
    )
    canvas.services.scene_decoration_service.add_mark(QPointF(90, 60), kind=kind)
    snapshot = canvas.services.canvas_document_session_service.snapshot_state
    if isolated:
        state = snapshot()
        state["model"]["bonds"] = []
        canvas.services.canvas_document_session_service.apply_state(state)
    before = snapshot()
    candidate = deepcopy(before)
    adapter = BrowserStructureAdapter(candidate)
    request = []
    marks = canvas.runtime_state.mark_items()
    if selection in {"mark", "both", "free"}:
        index = 1 if selection == "free" else 0
        marks[index].setSelected(True)
        request.append({"target": "mark", "id": index})
    if selection in {"bond", "both"} and not isolated:
        for item in canvas.runtime_state.bond_graphics_state.bond_items[0]:
            item.setSelected(True)
        request.append({"target": "bond", "id": 0})
    assert request
    assert canvas.services.scene_delete_controller.delete_selected_items()
    adapter.delete_selection(request)
    assert candidate == snapshot()
    canvas.services.history_service.undo()
    assert snapshot() == before


def native_mark_measurements(source, *, glyph_ink=False):
    from PyQt6.QtGui import QFont, QFontMetricsF, QPainterPath, QTextDocument

    spec = document_info(source)["drawing"]["label_measurements"]
    measurements = {"family": spec["family"], "metrics": {}, "ink": {}}
    queries = {
        query["key"]: query for query in [*spec["queries"], *spec["mark_queries"]]
    }
    for query in queries.values():
        font = QFont(spec["family"])
        font.setPointSizeF(query["size"])
        fm = QFontMetricsF(font)
        doc = QTextDocument()
        doc.setDefaultFont(font)
        doc.setDocumentMargin(0)
        doc.setPlainText(query["text"])
        measurements["metrics"][query["key"]] = {
            "width": fm.horizontalAdvance(query["text"]),
            "bounding_width": fm.boundingRect(query["text"]).width(),
            "ascent": fm.ascent(),
            "descent": fm.descent(),
            "cap_height": fm.capHeight(),
            "line_height": doc.size().height(),
        }
        if query["text"] in {"+", "-"} and not glyph_ink:
            rect = fm.boundingRect(query["text"])
            points = [
                [rect.left(), rect.top()],
                [rect.right(), rect.top()],
                [rect.right(), rect.bottom()],
                [rect.left(), rect.bottom()],
            ]
        else:
            path = QPainterPath()
            path.addText(0, 0, font, query["text"])
            points = [
                [point.x(), point.y()]
                for polygon in path.toSubpathPolygons()
                for point in polygon
            ]
        measurements["ink"][f"{query['pixels']}:{query['text']}"] = points
    return BrowserFontMeasurements(measurements)


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "circled_plus", "circled_minus", "radical"]
)
@pytest.mark.parametrize("label", ["C", "N", "Cl", "CO2Me", "NH2"])
@pytest.mark.parametrize(
    "point", [(0, 0), (5, -5), (15, 0), (-12, 0), (30, -5), (90, 50)]
)
@pytest.mark.parametrize("scale", [0.5, 1, 4])
def test_browser_mark_creation_port_matches_native(
    desktop_canvas, kind, label, point, scale
):
    from PyQt6.QtCore import QPointF

    source = draw_bond(new_document(), start=(0, 0), end=(20, 0))["document"]
    if label != "C":
        source = edit_document(
            {
                "document": source,
                "edit": {
                    "kind": "atom_prompt",
                    "atom_id": 0,
                    "x": 0,
                    "y": 0,
                    "text": label,
                },
            }
        )["document"]
    canvas = desktop_canvas
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    source["state"] = documents.snapshot_state()
    font = native_mark_measurements(source)
    drawing = document_info(source, font=font)["drawing"]
    candidate = deepcopy(source["state"])
    adapter = BrowserStructureAdapter(candidate)
    pos = QPointF(*point)
    canvas.runtime_state.input_view_state.zoom = scale
    items = [
        *canvas.runtime_state.atom_graphics_state.atom_items.values(),
        *canvas.runtime_state.atom_graphics_state.atom_dots.values(),
    ]
    hits = [
        {"target": "atom", "id": item.data(1)}
        for item in items
        if item.contains(item.mapFromScene(pos))
    ]
    owner = canvas.services.canvas_mark_scene_service.find_atom_for_mark(pos, kind=kind)
    if owner is None:
        canvas.services.scene_decoration_service.add_mark(pos, kind=kind)
    else:
        canvas.services.canvas_mark_scene_service.add_mark_for_atom(
            owner, pos, kind=kind
        )
    adapter.insert_mark(
        *point, kind, scale=scale, hits=hits, drawing=drawing, font=font
    )
    expected = documents.snapshot_state()
    assert candidate["model"] == expected["model"]
    assert candidate["marks"][0] == pytest.approx(expected["marks"][0], abs=1e-10)


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "circled_plus", "circled_minus", "radical"]
)
@pytest.mark.parametrize("selection", ["mark", "atom", "both", "mixed", "free", "all"])
@pytest.mark.parametrize("operation", ["rotate", "horizontal", "vertical"])
def test_browser_mark_transform_port_matches_native(
    desktop_canvas, kind, selection, operation
):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(20, 20), QPointF(40, 20), "single", 1
    )
    marks = canvas.services.canvas_mark_scene_service
    bound = marks.add_mark_for_atom(0, QPointF(10, 8), kind=kind)
    free = canvas.services.scene_decoration_service.add_mark(QPointF(90, 60), kind=kind)
    other = marks.add_mark_for_atom(1, QPointF(50, 8), kind=kind)
    snapshot = canvas.services.canvas_document_session_service.snapshot_state
    before = snapshot()
    source = build_document_payload(before, 9)
    font = native_mark_measurements(source)
    drawing = document_info(source, font=font)["drawing"]
    candidate = deepcopy(before)
    adapter = BrowserStructureAdapter(candidate)
    atom_ids = (
        {0, 1}
        if selection == "all"
        else {0}
        if selection in {"atom", "both", "mixed"}
        else set()
    )
    selected = [] if selection == "atom" else [free] if selection == "free" else [bound]
    request = [{"target": "atom", "id": i} for i in atom_ids]
    if selected:
        request.append({"target": "mark", "id": 1 if selection == "free" else 0})
    if selection in {"mixed", "all"}:
        selected += [free, other]
        request += [{"target": "mark", "id": 1}, {"target": "mark", "id": 2}]
    for atom_id in atom_ids:
        item = canvas.runtime_state.atom_graphics_state.atom_items.get(atom_id)
        if item is None:
            item = canvas.runtime_state.atom_graphics_state.atom_dots[atom_id]
        item.setSelected(True)
    for item in selected:
        item.setSelected(True)
    edit = (
        {"kind": "rotate", "value": 37, "selection": request}
        if operation == "rotate"
        else {
            "kind": "flip",
            "horizontal": operation == "horizontal",
            "selection": request,
        }
    )
    controller = canvas.services.scene_transform_controller
    if operation == "rotate":
        controller.rotate_selected_items(37)
    else:
        controller.flip_selected_items(operation == "horizontal")
    adapter.transform_selection(edit, drawing)
    expected = snapshot()
    assert candidate["model"]["atom_annotations"] == before["model"]["atom_annotations"]
    for atom_id, atom in candidate["model"]["atoms"].items():
        assert atom == pytest.approx(expected["model"]["atoms"][atom_id], abs=1e-10)
    for actual, wanted in zip(candidate["marks"], expected["marks"], strict=True):
        assert actual == pytest.approx(wanted, abs=1e-10)
    if expected != before:
        canvas.services.history_service.undo()
        assert snapshot() == before


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "circled_plus", "circled_minus", "radical"]
)
@pytest.mark.parametrize("preferred", [False, True])
@pytest.mark.parametrize("offset", [(0, 0), (3, -2), (10, -8), (60, 40)])
@pytest.mark.parametrize("point_offset", [(0, 0), (2, -1), (-3, 2)])
def test_browser_mark_pick_port_matches_native(
    desktop_canvas, kind, preferred, offset, point_offset
):
    from PyQt6.QtCore import QPointF

    from chemvas.ui.canvas.canvas_hit_testing_service import (
        scene_items_at_pos_for_canvas,
    )

    canvas = desktop_canvas
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(20, 20), QPointF(40, 20), "single", 1
    )
    canvas.services.canvas_mark_scene_service.add_mark_for_atom(
        0, QPointF(20 + offset[0], 20 + offset[1]), kind=kind
    )
    mark_items = canvas.runtime_state.mark_items()
    center = canvas.services.scene_decoration_build_service.mark_center(mark_items[0])
    pos = center + QPointF(*point_offset)
    before = canvas.services.canvas_document_session_service.snapshot_state()
    hits = []
    for item in scene_items_at_pos_for_canvas(canvas, pos):
        target = item.data(0)
        if target in {"atom", "bond", "mark"}:
            hits.append(
                {
                    "target": target,
                    "id": mark_items.index(item) if target == "mark" else item.data(1),
                }
            )
    item = (
        canvas.services.selection.preferred_structure_item_at_scene_pos(pos)
        if preferred
        else canvas.services.hit_testing_service.item_at_scene_pos(pos)
    )
    expected = (
        None
        if item is None
        else {
            "target": item.data(0),
            "id": mark_items.index(item) if item.data(0) == "mark" else item.data(1),
        }
    )
    adapter = BrowserStructureAdapter(deepcopy(before))
    assert (
        adapter.pick_target(pos.x(), pos.y(), hits, preferred=preferred, scale=1)
        == expected
    )
    assert canvas.services.canvas_document_session_service.snapshot_state() == before


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "circled_plus", "circled_minus", "radical"]
)
@pytest.mark.parametrize("attached", [False, True])
def test_browser_mark_selection_circle_matches_native(desktop_canvas, kind, attached):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(20, 20), QPointF(40, 20), "single", 1
    )
    mark = (
        canvas.services.canvas_mark_scene_service.add_mark_for_atom(
            0, QPointF(10, 8), kind=kind
        )
        if attached
        else canvas.services.scene_decoration_service.add_mark(
            QPointF(90, 60), kind=kind
        )
    )
    source = build_document_payload(
        canvas.services.canvas_document_session_service.snapshot_state(), 9
    )
    adapter = BrowserStructureAdapter(extract_document_state(source))
    drawing = document_info(source, font=native_mark_measurements(source))["drawing"]
    components = adapter.selection_components([{"target": "mark", "id": 0}], drawing)
    from chemvas.ui.scene.mark_item_access import mark_selection_radius_for
    from chemvas.ui.selection.selection_outline_paths import (
        selection_path_for_object_item,
    )

    path = selection_path_for_object_item(
        mark,
        kind="mark",
        pad=0,
        mark_center=canvas.services.scene_decoration_build_service.mark_center(mark),
        mark_radius=mark_selection_radius_for(canvas),
    )
    assert components == [[{"rect": pytest.approx(path.boundingRect().getRect())}]]
    assert adapter.selection_frame([{"target": "mark", "id": 0}], drawing) is None


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "circled_plus", "circled_minus", "radical"]
)
@pytest.mark.parametrize("selection", ["marks", "owner", "neighbor", "free"])
@pytest.mark.parametrize(
    "mode",
    ["left", "center", "right", "top", "middle", "bottom", "horizontal", "vertical"],
)
def test_browser_mark_arrangement_matches_native(desktop_canvas, kind, selection, mode):
    from PyQt6.QtCore import QPointF

    from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for

    canvas = desktop_canvas
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(20, 20), QPointF(40, 20), "single", 1
    )
    canvas.services.canvas_mark_scene_service.add_mark_for_atom(
        0, QPointF(10, 8), kind=kind
    )
    for x, y in [(90, 60), (-60, -30), (150, -70)]:
        canvas.services.scene_decoration_service.add_mark(QPointF(x, y), kind=kind)
    documents = canvas.services.canvas_document_session_service
    before = documents.snapshot_state()
    source = build_document_payload(before, 9)
    drawing = document_info(source, font=native_mark_measurements(source))["drawing"]
    selection_request = []
    if selection in {"owner", "neighbor"}:
        atom_id = 0 if selection == "owner" else 1
        visible_atom_item_for(canvas, atom_id).setSelected(True)
        selection_request.append({"target": "atom", "id": atom_id})
    for index, item in enumerate(canvas.runtime_state.mark_items()):
        if selection == "free" and index == 0:
            continue
        item.setSelected(True)
        selection_request.append({"target": "mark", "id": index})
    candidate = deepcopy(before)
    adapter = BrowserStructureAdapter(candidate)
    distribute = mode in {"horizontal", "vertical"}
    controller = canvas.services.scene_transform_controller
    (
        controller.distribute_selected_items
        if distribute
        else controller.align_selected_items
    )(mode)
    adapter.arrange_selection(
        selection_request, mode, distribute=distribute, drawing=drawing
    )
    expected = documents.snapshot_state()
    for atom_id, atom in candidate["model"]["atoms"].items():
        assert atom == pytest.approx(expected["model"]["atoms"][atom_id], abs=1e-10)
    for actual, wanted in zip(candidate["marks"], expected["marks"], strict=True):
        assert actual == pytest.approx(wanted, abs=1e-10)
    assert (
        candidate["model"]["atom_annotations"] == expected["model"]["atom_annotations"]
    )
    if expected != before:
        canvas.services.history_service.undo()
        assert documents.snapshot_state() == before


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "circled_plus", "circled_minus", "radical"]
)
@pytest.mark.parametrize("selection", ["mark", "atom", "both", "free"])
def test_browser_mark_color_matches_native(desktop_canvas, kind, selection):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QColor

    from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for

    canvas = desktop_canvas
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(20, 20), QPointF(40, 20), "single", 1
    )
    bound = canvas.services.canvas_mark_scene_service.add_mark_for_atom(
        0, QPointF(10, 8), kind=kind
    )
    free = canvas.services.scene_decoration_service.add_mark(QPointF(90, 60), kind=kind)
    documents = canvas.services.canvas_document_session_service
    before = documents.snapshot_state()
    selected, request = [], []
    if selection in {"mark", "both", "free"}:
        selected.append(free if selection == "free" else bound)
        request.append({"target": "mark", "id": 1 if selection == "free" else 0})
    if selection in {"atom", "both"}:
        selected.append(visible_atom_item_for(canvas, 0))
        request.append({"target": "atom", "id": 0})
    candidate = deepcopy(before)
    canvas.services.canvas_color_mutation_service.apply_color_to_items(
        selected, QColor("#Ab12Cd")
    )
    result = BrowserStructureAdapter(candidate).apply_color(
        {"kind": "color", "selection": request, "color": "#Ab12Cd"}
    )
    assert candidate == documents.snapshot_state()
    if selection != "atom":
        assert result is None
    canvas.services.history_service.undo()
    assert documents.snapshot_state() == before


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "circled_plus", "circled_minus", "radical"]
)
@pytest.mark.parametrize("length", [10, 20, 35.5, 60])
@pytest.mark.parametrize("structure", ["bond", "ring", "empty"])
def test_browser_mark_bond_length_matches_native(
    desktop_canvas, kind, length, structure
):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    source = new_document()
    if structure == "bond":
        source = draw_bond(source)["document"]
    elif structure == "ring":
        source = edit_document(
            {"document": source, "edit": {"kind": "ring", "x": 80, "y": 50}}
        )["document"]
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    if structure != "empty":
        canvas.services.canvas_mark_scene_service.add_mark_for_atom(
            0, QPointF(10, 8), kind=kind
        )
    canvas.services.scene_decoration_service.add_mark(QPointF(120, -60), kind=kind)
    before = documents.snapshot_state()
    candidate = deepcopy(before)
    canvas.services.geometry_controller.set_bond_length(length)
    BrowserStructureAdapter(candidate).set_drawing_settings(
        {"kind": "bond_length", "value": length}
    )
    expected = documents.snapshot_state()
    for atom_id, atom in candidate["model"]["atoms"].items():
        assert atom == pytest.approx(expected["model"]["atoms"][atom_id], abs=1e-10)
    for actual, wanted in zip(candidate["marks"], expected["marks"], strict=True):
        assert actual == pytest.approx(wanted, abs=1e-10)
    for actual, wanted in zip(
        candidate["ring_fills"], expected["ring_fills"], strict=True
    ):
        for point, target in zip(actual["points"], wanted["points"], strict=True):
            assert point == pytest.approx(target, abs=1e-10)
    assert candidate["settings"] == expected["settings"]
    assert candidate["marks"][-1] == before["marks"][-1]
    if expected != before:
        canvas.services.history_service.undo()
        assert documents.snapshot_state() == before


@pytest.mark.parametrize("length", [10, 20, 35.5, 60])
def test_browser_bond_length_rescales_geometry_in_one_history_step(length):
    from decimal import Decimal

    source = json.loads(
        json.dumps(draw_bond(new_document())["document"]), parse_float=Decimal
    )
    session = BrowserSession()
    before = session.dispatch({"action": "load", "revision": 0, "document": source})
    edit = json.loads(
        json.dumps({"kind": "bond_length", "value": length}), parse_float=Decimal
    )
    preview = session.dispatch({"action": "preview", "revision": 1, "edit": edit})
    assert session.dispatch({"action": "read"}) == before
    result = session.dispatch({"action": "edit", "revision": 1, "edit": edit})
    assert result["document"] == preview["document"]
    atoms = list(result["document"]["state"]["model"]["atoms"].values())
    assert float(atoms[1]["x"]) - float(atoms[0]["x"]) == pytest.approx(length)
    assert (float(atoms[1]["x"]) + float(atoms[0]["x"])) / 2 == 40
    if length != 20:
        assert (
            session.dispatch({"action": "undo", "revision": 2})["document"]
            == before["document"]
        )
        assert (
            session.dispatch({"action": "redo", "revision": 3})["document"]
            == result["document"]
        )


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "circled_plus", "circled_minus", "radical"]
)
@pytest.mark.parametrize("origin", ["free", "isolated", "bonded"])
@pytest.mark.parametrize("target_mark", [False, True])
def test_browser_mark_rebind_matches_native(desktop_canvas, kind, origin, target_mark):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QColor

    canvas = desktop_canvas
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(20, 20), QPointF(40, 20), "single", 1
    )
    if origin == "isolated":
        canvas.model.bonds.clear()
    marks = canvas.services.canvas_mark_scene_service
    item = (
        canvas.services.scene_decoration_service.add_mark(QPointF(80, 90), kind=kind)
        if origin == "free"
        else marks.add_mark_for_atom(0, QPointF(10, 8), kind=kind)
    )
    canvas.services.canvas_color_mutation_service.apply_color_to_items(
        [item], QColor("#125678")
    )
    if target_mark:
        marks.add_mark_for_atom(1, QPointF(50, 8), kind="minus")
    documents = canvas.services.canvas_document_session_service
    before = documents.snapshot_state()
    candidate = deepcopy(before)
    adapter = BrowserStructureAdapter(candidate)
    assert marks.rebind_mark(item, 1)
    assert adapter.rebind_mark(0, 1)
    expected = documents.snapshot_state()
    assert candidate == expected
    assert not adapter.rebind_mark(0, 1)
    assert candidate == expected
    canvas.services.history_service.undo()
    assert documents.snapshot_state() == before


@pytest.mark.parametrize("target", [True, False, -1, 999, None, "1", 1.0, [], {}])
def test_browser_mark_rebind_rejects_invalid_owner_without_mutation(
    desktop_canvas, target
):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(20, 20), QPointF(40, 20), "single", 1
    )
    item = canvas.services.canvas_mark_scene_service.add_mark_for_atom(
        0, QPointF(10, 8), kind="plus"
    )
    before = canvas.services.canvas_document_session_service.snapshot_state()
    candidate = deepcopy(before)
    with pytest.raises(ValueError, match="Choose an existing atom"):
        canvas.services.canvas_mark_scene_service.rebind_mark(item, target)
    with pytest.raises(ValueError, match="Choose an existing atom"):
        BrowserStructureAdapter(candidate).rebind_mark(0, target)
    assert candidate == before


@pytest.mark.parametrize(
    "annotation", [{"formal_charge": 2}, {"isotope": 13}, {"radical_electrons": 1}]
)
def test_browser_mark_rebind_rejects_annotation_conflict(desktop_canvas, annotation):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(20, 20), QPointF(40, 20), "single", 1
    )
    item = canvas.services.canvas_mark_scene_service.add_mark_for_atom(
        0, QPointF(10, 8), kind="plus"
    )
    canvas.model.set_atom_annotation(0, annotation)
    before = canvas.services.canvas_document_session_service.snapshot_state()
    candidate = deepcopy(before)
    with pytest.raises(ValueError, match="annotations and marks disagree"):
        canvas.services.canvas_mark_scene_service.rebind_mark(item, 1)
    with pytest.raises(ValueError, match="annotations and marks disagree"):
        BrowserStructureAdapter(candidate).rebind_mark(0, 1)
    assert candidate == before


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "circled_plus", "circled_minus", "radical"]
)
def test_browser_mark_session_creation_move_rebind_and_history(kind):
    from decimal import Decimal

    source = draw_bond(new_document())["document"]
    session = BrowserSession()
    initial = session.dispatch({"action": "load", "revision": 0, "document": source})
    session.font = native_mark_measurements(source)
    create = json.loads(
        json.dumps(
            {
                "kind": "mark",
                "x": 30.0,
                "y": 40.0,
                "mark_kind": kind,
                "scale": 1.0,
                "hits": [{"target": "atom", "id": 0}],
            }
        ),
        parse_float=Decimal,
    )
    preview = session.dispatch({"action": "preview", "revision": 1, "edit": create})
    assert session.dispatch({"action": "read"}) == initial
    created = session.dispatch({"action": "edit", "revision": 1, "edit": create})
    assert created["document"] == preview["document"]
    assert not created["unsupported"]
    assert created["document"]["state"]["marks"][0]["atom_id"] == 0
    before_move = deepcopy(created["document"]["state"]["marks"][0])
    moved = session.dispatch(
        {
            "action": "edit",
            "revision": 2,
            "edit": {
                "kind": "move",
                "selection": [{"target": "mark", "id": 0}],
                "dx": 60,
                "dy": -10,
            },
        }
    )
    before_rebind = deepcopy(moved["document"]["state"]["marks"][0])
    assert before_rebind["atom_id"] == 0
    assert before_rebind["x"] == before_move["x"] + 60
    rebound = session.dispatch(
        {
            "action": "edit",
            "revision": 3,
            "edit": {"kind": "mark_owner", "id": 0, "atom_id": 1},
        }
    )
    after_rebind = rebound["document"]["state"]["marks"][0]
    assert after_rebind["atom_id"] == 1
    assert (after_rebind["x"], after_rebind["y"]) == (
        before_rebind["x"],
        before_rebind["y"],
    )
    assert not rebound["unsupported"]
    for revision, document in [
        (4, moved["document"]),
        (5, created["document"]),
        (6, initial["document"]),
    ]:
        assert (
            session.dispatch({"action": "undo", "revision": revision})["document"]
            == document
        )
    for revision, document in [
        (7, created["document"]),
        (8, moved["document"]),
        (9, rebound["document"]),
    ]:
        assert (
            session.dispatch({"action": "redo", "revision": revision})["document"]
            == document
        )


@pytest.mark.parametrize("label", ["C", "N", "NH2"])
@pytest.mark.parametrize("length", [20, 40])
@pytest.mark.parametrize("bonded", [False, True])
@pytest.mark.parametrize("initial", [None, "circled_plus", "circled_minus", "radical"])
@pytest.mark.parametrize(
    "keys", ["+", "-", "+++", "---", "+-", "-+", "+" * 12, "-" * 12]
)
def test_browser_charge_shortcut_matches_native(
    desktop_canvas, label, length, bonded, initial, keys
):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    canvas.renderer.set_bond_length(length)
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(20, 20), QPointF(20 + length, 20), "single", 1
    )
    if not bonded:
        state = canvas.services.canvas_document_session_service.snapshot_state()
        state["model"]["bonds"] = []
        canvas.services.canvas_document_session_service.apply_state(state)
    if label != "C":
        canvas.services.atom_label_service.add_or_update_atom_label(0, label)
    if initial:
        canvas.services.canvas_mark_scene_service.add_mark_for_atom(
            0, QPointF(20, 20), kind=initial
        )
    documents = canvas.services.canvas_document_session_service
    source = new_document()
    source["state"] = documents.snapshot_state()
    candidate = deepcopy(source["state"])
    for key in keys:
        font = native_mark_measurements({**source, "state": candidate}, glyph_ink=True)
        adapter = BrowserStructureAdapter(candidate)
        adapter.apply_hover_shortcut(20, 20, key, 0, font=font)
        canvas.services.canvas_mark_scene_service.change_charge_for_atom(
            0, 1 if key == "+" else -1
        )
        expected = documents.snapshot_state()
        assert candidate["model"] == expected["model"]
        assert len(candidate["marks"]) == len(expected["marks"])
        for actual, native in zip(candidate["marks"], expected["marks"], strict=True):
            assert actual == pytest.approx(native, rel=0, abs=1e-12)


@pytest.mark.parametrize("keys", ["++-", "--+", "+" * 12])
def test_browser_charge_shortcut_session_preview_and_history(keys):
    source = draw_bond(new_document())["document"]
    session = BrowserSession()
    session.dispatch({"action": "load", "revision": 0, "document": source})
    snapshots = [source]
    revision = 1
    for key in keys:
        session.font = native_mark_measurements(snapshots[-1], glyph_ink=True)
        before = session.dispatch({"action": "read"})
        change = {"kind": "hover_shortcut", "x": 30, "y": 40, "atom_id": 0, "key": key}
        preview = session.dispatch(
            {"action": "preview", "revision": revision, "edit": change}
        )
        assert session.dispatch({"action": "read"}) == before
        edited = session.dispatch(
            {"action": "edit", "revision": revision, "edit": change}
        )
        assert edited["document"] == preview["document"]
        assert not edited["unsupported"]
        snapshots.append(edited["document"])
        revision += 1
    for expected in reversed(snapshots[:-1]):
        assert (
            session.dispatch({"action": "undo", "revision": revision})["document"]
            == expected
        )
        revision += 1
    for expected in snapshots[1:]:
        assert (
            session.dispatch({"action": "redo", "revision": revision})["document"]
            == expected
        )
        revision += 1


@pytest.mark.parametrize("kind", ["plus", "minus", "circled_plus", "circled_minus"])
@pytest.mark.parametrize("origin", [None, 1])
def test_browser_charge_after_reassignment_preserves_native_binding_order(
    desktop_canvas, kind, origin
):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(20, 20), QPointF(40, 20), "single", 1
    )
    marks = canvas.services.canvas_mark_scene_service
    first = (
        canvas.services.scene_decoration_service.add_mark(QPointF(80, 80), kind=kind)
        if origin is None
        else marks.add_mark_for_atom(origin, QPointF(80, 80), kind=kind)
    )
    marks.add_mark_for_atom(0, QPointF(20, 20), kind=kind)
    documents = canvas.services.canvas_document_session_service
    source = new_document()
    source["state"] = documents.snapshot_state()
    session = BrowserSession()
    loaded = session.dispatch({"action": "load", "revision": 0, "document": source})
    rebound = session.dispatch(
        {
            "action": "edit",
            "revision": 1,
            "edit": {"kind": "mark_owner", "id": 0, "atom_id": 0},
        }
    )
    marks.rebind_mark(first, 0)
    assert rebound["document"]["state"] == documents.snapshot_state()
    assert rebound["mark_order"][0] == [1, 0]
    # Real browser measurement completion must not reset the registry order.
    font = native_mark_measurements(rebound["document"], glyph_ink=True)
    measured = session.dispatch(
        {
            "action": "measure",
            "revision": 2,
            "font": {
                "family": rebound["drawing"]["label_measurements"]["family"],
                "metrics": font.metrics,
                "ink": {
                    key: [list(point) for point in points]
                    for key, points in font.ink.items()
                },
            },
        }
    )
    assert measured["mark_order"] == rebound["mark_order"]
    key = "-" if kind in {"plus", "circled_plus"} else "+"
    change = {"kind": "hover_shortcut", "x": 20, "y": 20, "atom_id": 0, "key": key}
    preview = session.dispatch({"action": "preview", "revision": 2, "edit": change})
    assert session.dispatch({"action": "read"})["mark_order"] == rebound["mark_order"]
    changed = session.dispatch({"action": "edit", "revision": 2, "edit": change})
    marks.change_charge_for_atom(0, -1 if key == "-" else 1)
    assert changed["document"]["state"] == documents.snapshot_state()
    assert changed["document"] == preview["document"]
    undone = session.dispatch({"action": "undo", "revision": 3})
    assert undone["mark_order"] == rebound["mark_order"]
    undone = session.dispatch({"action": "undo", "revision": 4})
    assert undone["mark_order"] == loaded["mark_order"]
    redone = session.dispatch({"action": "redo", "revision": 5})
    assert redone["mark_order"] == rebound["mark_order"]
    redone = session.dispatch({"action": "redo", "revision": 6})
    assert redone["document"] == changed["document"]
    assert "mark_order" not in redone["document"]["state"]


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "circled_plus", "circled_minus", "radical"]
)
@pytest.mark.parametrize("label", ["C", "NH2", "CO2Me"])
@pytest.mark.parametrize("offset", [(0, 0), (5, -5), (20, 0), (20.001, 0), (100, -80)])
@pytest.mark.parametrize("bound", [False, True])
def test_browser_mark_owner_feedback_matches_native(
    desktop_canvas, kind, label, offset, bound
):
    from PyQt6.QtCore import QPointF

    from chemvas.ui.scene.mark_ownership import mark_is_distant_for, mark_owner_text_for
    from chemvas.ui.selection.selection_style_access import (
        selection_indicator_rect_for_atom_for,
    )

    canvas = desktop_canvas
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(20, 20), QPointF(40, 20), "single", 1
    )
    if label != "C":
        canvas.services.atom_label_service.add_or_update_atom_label(0, label)
    item = (
        canvas.services.canvas_mark_scene_service.add_mark_for_atom(
            0, QPointF(20, 20), kind=kind
        )
        if bound
        else canvas.services.scene_decoration_service.add_mark(
            QPointF(20, 20), kind=kind
        )
    )
    center = QPointF(20 + offset[0], 20 + offset[1])
    canvas.services.scene_decoration_build_service.set_mark_center(item, center)
    if bound:
        data = dict(item.data(1))
        data.update(dx=offset[0], dy=offset[1])
        item.setData(1, data)
    source = new_document()
    source["state"] = canvas.services.canvas_document_session_service.snapshot_state()
    before = deepcopy(source)
    drawing = document_info(source, font=native_mark_measurements(source))["drawing"]
    feedback = drawing["mark_owners"]["0"]
    assert source == before
    assert feedback["text"] == mark_owner_text_for(canvas, item)
    if bound:
        assert feedback["line"] == [20, 20, center.x(), center.y()]
        rect = selection_indicator_rect_for_atom_for(canvas, 0)
        assert feedback["rect"] == pytest.approx(
            (rect.x(), rect.y(), rect.width(), rect.height()), abs=1 / 64
        )
        assert feedback["color"] == (
            "#b45309" if mark_is_distant_for(canvas, item) else "#0d9488"
        )
    else:
        assert set(feedback) == {"text"}


@pytest.mark.parametrize("delta", [-1, 1])
@pytest.mark.parametrize("deleted", [[0], [1], [0, 2]])
def test_browser_mark_delete_undo_then_charge_matches_native(
    desktop_canvas, delta, deleted
):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(20, 20), QPointF(40, 20), "single", 1
    )
    marks = canvas.services.canvas_mark_scene_service
    for _ in range(3):
        marks.change_charge_for_atom(0, delta)
    source = new_document()
    documents = canvas.services.canvas_document_session_service
    source["state"] = documents.snapshot_state()
    session = BrowserSession()
    session.dispatch({"action": "load", "revision": 0, "document": source})
    session.font = native_mark_measurements(source, glyph_ink=True)
    original = list(canvas.runtime_state.mark_registry.get_for_atom(0))
    canvas.scene().clearSelection()
    for index in deleted:
        original[index].setSelected(True)
    canvas.services.scene_delete_controller.delete_selected_items()
    result = session.dispatch(
        {
            "action": "edit",
            "revision": 1,
            "edit": {
                "kind": "delete_selection",
                "selection": [{"target": "mark", "id": index} for index in deleted],
            },
        }
    )
    assert result["document"]["state"] == documents.snapshot_state()
    revision = 2
    for action in ["undo", "redo", "undo"]:
        getattr(canvas.services.history_service, action)()
        result = session.dispatch({"action": action, "revision": revision})
        revision += 1
        assert result["document"]["state"] == documents.snapshot_state()
        if action == "undo":
            assert canvas.runtime_state.mark_registry.get_for_atom(0) == original
    marks.change_charge_for_atom(0, -delta)
    result = session.dispatch(
        {
            "action": "edit",
            "revision": revision,
            "edit": {
                "kind": "hover_shortcut",
                "x": 20,
                "y": 20,
                "atom_id": 0,
                "key": "+" if delta < 0 else "-",
            },
        }
    )
    assert result["document"]["state"] == documents.snapshot_state()
    for action in ["undo", "redo", "undo"]:
        revision += 1
        getattr(canvas.services.history_service, action)()
        result = session.dispatch({"action": action, "revision": revision})
        assert result["document"]["state"] == documents.snapshot_state()


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "circled_plus", "circled_minus", "radical"]
)
@pytest.mark.parametrize("label", ["C", "NH2", "CO2Me"])
@pytest.mark.parametrize("point", [(0, 0), (5, -5), (15, 0), (-12, 0), (90, 50)])
@pytest.mark.parametrize("scale", [0.5, 2])
def test_browser_mark_hover_matches_native_without_document_mutation(
    desktop_canvas, kind, label, point, scale
):
    from PyQt6.QtCore import QPointF

    from chemvas.ui.tools.hover import HoverController

    source = draw_bond(new_document(), start=(0, 0), end=(20, 0))["document"]
    if label != "C":
        source = edit_document(
            {
                "document": source,
                "edit": {
                    "kind": "atom_prompt",
                    "atom_id": 0,
                    "x": 0,
                    "y": 0,
                    "text": label,
                },
            }
        )["document"]
    canvas = desktop_canvas
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    source["state"] = documents.snapshot_state()
    canvas.runtime_state.input_view_state.zoom = scale
    canvas.runtime_state.tool_settings_state.mark_kind = kind
    pos = QPointF(*point)
    native = HoverController(
        canvas,
        selection_controller=canvas.services.selection,
        hit_testing_service=canvas.services.hit_testing_service,
        insert_controller=canvas.services.insert_controller,
        scene_decoration_build_service=canvas.services.scene_decoration_build_service,
        mark_scene_service=canvas.services.canvas_mark_scene_service,
        active_tool_name_provider=lambda: "mark",
    )
    native.add_mark_hover_preview(pos)
    state = canvas.runtime_state.hover_preview_state
    center = canvas.services.scene_decoration_build_service.mark_center(state.items[-1])
    items = [
        *canvas.runtime_state.atom_graphics_state.atom_items.values(),
        *canvas.runtime_state.atom_graphics_state.atom_dots.values(),
    ]
    hits = [
        {"target": "atom", "id": item.data(1)}
        for item in items
        if item.contains(item.mapFromScene(pos))
    ]
    font = native_mark_measurements(source, glyph_ink=True)
    session = BrowserSession()
    session.dispatch({"action": "load", "revision": 0, "document": source})
    before = deepcopy(session.dispatch({"action": "read"}))
    request = {
        "action": "mark_preview",
        "revision": 1,
        "kind": kind,
        "x": point[0],
        "y": point[1],
        "scale": scale,
        "hits": hits,
        "font": {
            "family": before["drawing"]["label_measurements"]["family"],
            "metrics": font.metrics,
            "ink": {key: [list(p) for p in points] for key, points in font.ink.items()},
        },
    }
    result = session.dispatch(request)
    assert session.dispatch(request) == result
    assert session.dispatch({"action": "read"}) == before
    assert documents.snapshot_state() == source["state"]
    assert result["owner"] == state.atom_id
    assert (result["mark"]["x"], result["mark"]["y"]) == pytest.approx(
        (center.x(), center.y()), rel=0, abs=1e-12
    )
    assert state.items[-1].opacity() == ui_spec()["mark_hover"]["opacity"]
    assert state.items[-1].zValue() == ui_spec()["mark_hover"]["z"]
    if state.atom_id is not None:
        atom = canvas.model.atoms[state.atom_id]
        assert result["atom"] == [atom.x, atom.y, state.items[0].rect().width() / 2]
    else:
        assert result["atom"] is None


@pytest.mark.parametrize(
    "kind",
    ["bond", "N", "NH2", "plus", "minus", "circled_plus", "circled_minus", "radical"],
)
@pytest.mark.parametrize("position", [(-1000, -900), (1000, 900)])
def test_browser_scene_range_matches_native_persistent_content(
    desktop_canvas, kind, position
):
    from PyQt6.QtCore import QPointF

    from chemvas.ui.canvas.sheet_setup_access import apply_sheet_scene_rect_for

    canvas = desktop_canvas
    x, y = position
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(x, y), QPointF(x + 20, y + 12), "single", 1
    )
    if kind in {"N", "NH2"}:
        canvas.services.atom_label_service.add_or_update_atom_label(0, kind)
    elif kind != "bond":
        canvas.services.scene_decoration_service.add_mark(
            QPointF(x + 100, y - 100), kind=kind
        )
    apply_sheet_scene_rect_for(canvas)
    source = new_document()
    source["state"] = canvas.services.canvas_document_session_service.snapshot_state()
    drawing = document_info(
        source, font=native_mark_measurements(source, glyph_ink=True)
    )["drawing"]
    assert drawing["scene_rect"] == pytest.approx(
        canvas.sceneRect().getRect(), abs=1e-9, rel=0
    )


@pytest.mark.parametrize("kind", sorted(VALID_ARROW_KINDS))
@pytest.mark.parametrize("delta", [(60, 0), (-36, 48)])
def test_browser_scene_range_matches_native_arrows(desktop_canvas, kind, delta):
    source = new_document()
    source["state"]["arrows"] = [
        {
            "kind": kind,
            "start": [1000, 900],
            "end": [1000 + delta[0], 900 + delta[1]],
            "control": [1030, 850] if kind.startswith("curved_") else None,
        }
    ]
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    drawing = document_info(source)["drawing"]
    assert drawing["scene_rect"] == pytest.approx(
        desktop_canvas.sceneRect().getRect(),
        abs=drawing["arrows"][0]["width"] / 2,
        rel=0,
    )


@pytest.mark.parametrize("style", sorted(VALID_BOND_STYLES))
def test_browser_scene_range_matches_native_bond_styles(desktop_canvas, style):
    source = draw_bond(new_document())["document"]
    for atom in source["state"]["model"]["atoms"].values():
        atom["x"] += 1000
        atom["y"] += 900
    source["state"]["model"]["bonds"][0]["style"] = style
    if style == "double_either":
        source["state"]["model"]["bonds"][0]["order"] = 2
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    drawing = document_info(source)["drawing"]
    assert drawing["scene_rect"] == pytest.approx(
        desktop_canvas.sceneRect().getRect(), abs=1e-6, rel=0
    )


@pytest.mark.parametrize("zoom", [0.25, 1, 2])
@pytest.mark.parametrize("target", [(-990, -890), (1000, 900), (0, 0), (400, -300)])
def test_browser_candidate_clamp_matches_qt_view(qt_application, zoom, target):
    from PyQt6.QtCore import QPoint, QRectF, Qt
    from PyQt6.QtGui import QTransform
    from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

    scene = QGraphicsScene()
    scene.setSceneRect(-1080, -980, 2180, 1980)
    view = QGraphicsView(scene)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.resize(640, 480)
    view.setTransform(QTransform.fromScale(zoom, zoom))
    view.show()
    qt_application.processEvents()
    view.centerOn(0, 0)
    viewport = view.viewport()
    before = view.mapToScene(QPoint(0, 0))
    rect = QRectF(*target, 12.8, 12.8)
    view.ensureVisible(rect, 80, 80)
    after = view.mapToScene(QPoint(0, 0))
    request = {
        "view": {
            "x": before.x(),
            "y": before.y(),
            "width": viewport.width() / zoom,
            "height": viewport.height() / zoom,
        },
        "viewport": {"width": viewport.width(), "height": viewport.height()},
        "rect": rect.getRect(),
        "scene": scene.sceneRect().getRect(),
    }
    script = r"""
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {clampView} from './app/chemvas/web/scene.mjs';
const input=JSON.parse(readFileSync(0,'utf8'));
const source=readFileSync('app/chemvas/web/app.mjs','utf8');
const start=source.indexOf('    const highlight = () => {');
const end=source.indexOf('\n    };',start)+7;
const context={view:input.view,clampView,field:{value:'0'},render(){},
 $:()=>({replaceChildren(){},append(){}}),
 editor:{info:{drawing:{mark_owner_rects:{'0':input.rect},scene_rect:input.scene,selection_style:{screen_width:1.5}}}},
 canvas:{clientWidth:input.viewport.width,clientHeight:input.viewport.height,setAttribute(){}},
 document:{createElementNS:()=>({setAttribute(){}})}};
context.viewScale=()=>Math.min(context.canvas.clientWidth/context.view.width,context.canvas.clientHeight/context.view.height);
runInNewContext(source.slice(start,end)+'\nhighlight();',context);
process.stdout.write(JSON.stringify(context.view));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=True,
    )
    actual = json.loads(result.stdout)
    # Qt's scrollbars quantize the same geometric boundary to integer pixels.
    assert [actual["x"], actual["y"]] == pytest.approx(
        [after.x(), after.y()], abs=1 / zoom, rel=0
    )
    view.close()


@pytest.mark.parametrize("kind", ["circle", "ellipse", "rect", "rounded_rect"])
@pytest.mark.parametrize(
    "stroke,fill,alpha",
    [
        ("solid", None, None),
        ("none", None, None),
        ("none", "#123456", None),
        ("none", "#123456", 0),
        ("dashed", None, None),
    ],
)
def test_browser_scene_range_matches_native_shapes(
    desktop_canvas, kind, stroke, fill, alpha
):
    source = new_document()
    shape = {
        "kind": "shape",
        "left": 1000,
        "top": 900,
        "right": 1080,
        "bottom": 960,
        "shape_kind": kind,
        "stroke_style": stroke,
    }
    if fill is not None:
        shape["fill"] = fill
    if alpha is not None:
        shape["fill_alpha"] = alpha
    source["state"]["shapes"] = [shape]
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    drawing = document_info(source)["drawing"]
    assert drawing["scene_rect"] == pytest.approx(
        desktop_canvas.sceneRect().getRect(), abs=1e-6, rel=0
    )


def test_browser_scene_range_tracks_commits_without_preview_state():
    source = draw_bond(new_document())["document"]
    session = BrowserSession()
    original = session.dispatch({"action": "load", "revision": 0, "document": source})
    change = {
        "kind": "move",
        "selection": [{"target": "bond", "id": 0}],
        "dx": 1000,
        "dy": 900,
    }
    preview = session.dispatch(
        {"action": "preview", "revision": original["revision"], "edit": change}
    )
    assert preview["drawing"]["scene_rect"] != original["drawing"]["scene_rect"]
    assert session.dispatch({"action": "read"}) == original
    edited = session.dispatch(
        {"action": "edit", "revision": original["revision"], "edit": change}
    )
    assert edited["drawing"]["scene_rect"] == preview["drawing"]["scene_rect"]
    undone = session.dispatch({"action": "undo", "revision": edited["revision"]})
    assert undone["drawing"]["scene_rect"] == original["drawing"]["scene_rect"]
    redone = session.dispatch({"action": "redo", "revision": undone["revision"]})
    assert redone["drawing"]["scene_rect"] == edited["drawing"]["scene_rect"]


@pytest.mark.parametrize(
    "kind", ["s", "p", "sp", "sp2", "sp3", "d", "mo_bonding", "mo_antibonding"]
)
@pytest.mark.parametrize("phase", [False, True])
@pytest.mark.parametrize("length", [20, 40])
@pytest.mark.parametrize("scale,rotation", [(1, 0), (0.5, 45), (2, -90)])
def test_browser_orbital_graphics_match_native(
    desktop_canvas, kind, phase, length, scale, rotation
):
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import QPainterPath, QTransform
    from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsLineItem

    source = new_document()
    source["state"]["settings"].update(
        bond_length_px=length, orbital_phase_enabled=phase
    )
    source["state"]["orbitals"] = [
        {
            "kind": kind,
            "center": [37, -21],
            "scale": scale,
            "rotation": rotation,
        }
    ]
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    native = next(
        item for item in desktop_canvas.scene().items() if item.data(0) == "orbital"
    )
    info = document_info(source)
    assert not info["unsupported"]
    drawing = info["drawing"]["orbitals"][0]
    hit_path = QPainterPath()
    hit_path.addRect(QRectF(*drawing["hit_rect"]))
    assert native.shape() == hit_path
    adapter = BrowserStructureAdapter(extract_document_state(source))
    left, top, width, height = drawing["hit_rect"]
    for local in (
        QPointF(left + 0.01, top + 0.01),
        QPointF(left + width / 2, top + height / 2),
        QPointF(left - 1, top - 1),
    ):
        pos = native.mapToScene(local)
        hits = [{"target": "orbital", "id": 0}] if hit_path.contains(local) else []
        expected_hit = desktop_canvas.services.hit_testing_service.item_at_scene_pos(
            pos
        )
        for preferred in (False, True):
            actual_hit = adapter.pick_target(
                pos.x(), pos.y(), hits, preferred=preferred, scale=1
            )
            assert actual_hit == (
                {"target": "orbital", "id": 0} if expected_hit is native else None
            )
    assert drawing["bounds"] == pytest.approx(
        native.sceneBoundingRect().getRect(), rel=0, abs=1e-12
    )
    frame = BrowserStructureAdapter(extract_document_state(source)).selection_frame(
        [{"target": "orbital", "id": 0}], info["drawing"]
    )
    assert frame is not None
    frame_rect = QRectF(*frame["rects"][0])
    pad = frame["padding"]
    native_frame = (
        desktop_canvas.services.selection.outline_service.selection_frame_rect(
            set(), [native]
        )
    )
    assert frame_rect.adjusted(-pad, -pad, pad, pad).getRect() == pytest.approx(
        native_frame.getRect(), rel=0, abs=1e-12
    )
    ellipses = [
        item for item in native.childItems() if isinstance(item, QGraphicsEllipseItem)
    ]
    assert len(ellipses) == len(drawing["ellipses"])
    matrix = (
        QTransform()
        .translate(*drawing["center"])
        .rotate(drawing["rotation"])
        .scale(drawing["scale"], drawing["scale"])
        .translate(-drawing["center"][0], -drawing["center"][1])
    )
    for item, (*rect, positive) in zip(ellipses, drawing["ellipses"], strict=True):
        assert item.rect().getRect() == tuple(rect)
        assert item.pen().widthF() == drawing["width"]
        assert item.pen().color().name() == drawing["color"]
        assert item.brush().style().name == ("SolidPattern" if phase else "NoBrush")
        if phase:
            assert (
                item.brush().color().name()
                == drawing["positive" if positive else "negative"]
            )
            assert item.brush().color().alphaF() == pytest.approx(
                drawing["alpha"], abs=1 / 65535
            )
        for point in [
            item.rect().topLeft(),
            item.rect().bottomRight(),
            item.rect().center(),
        ]:
            expected = item.mapToScene(point)
            actual = matrix.map(point)
            assert (actual.x(), actual.y()) == pytest.approx(
                (expected.x(), expected.y()), rel=0, abs=1e-12
            )
    lines = [
        item for item in native.childItems() if isinstance(item, QGraphicsLineItem)
    ]
    assert len(lines) == (1 if kind == "mo_antibonding" else 0)
    if lines:
        line = lines[0].line()
        assert drawing["node"] == (line.x1(), line.y1(), line.x2(), line.y2())
    else:
        assert drawing["node"] is None
    desktop_canvas.services.handle_overlay_service.show_orbital_handles(native)
    handles = desktop_canvas.runtime_state.handle_state.active_handles
    assert [(item.pos().x(), item.pos().y()) for item in handles] == [
        tuple(item["point"]) for item in drawing["handles"]
    ]


@pytest.mark.parametrize(
    "kind", ["s", "p", "sp", "sp2", "sp3", "d", "mo_bonding", "mo_antibonding"]
)
@pytest.mark.parametrize("delta", [(10, 7), (-12.5, 3.25), (0, 0)])
@pytest.mark.parametrize("action", ["move", "delete"])
def test_browser_orbital_move_delete_matches_native(
    desktop_canvas, kind, delta, action
):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    source = new_document()
    source["state"]["orbitals"] = [
        {"kind": kind, "center": [37, -21], "scale": 0.5, "rotation": 45},
        {"kind": "p", "center": [100, 70], "scale": 2, "rotation": -90},
    ]
    canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    snapshot = canvas.services.canvas_document_session_service.snapshot_state
    before = snapshot()
    candidate = deepcopy(before)
    adapter = BrowserStructureAdapter(candidate)
    orbital = canvas.runtime_state.orbital_items()[0]
    # Repeated hit entries must still mutate the selected record once.
    selected = [{"target": "orbital", "id": 0}] * 2
    if action == "move":
        tool = canvas.services.tool_controller.tools["select"]
        assert tool._begin_selection_drag(set(), [orbital], QPointF())
        tool._apply_drag_delta(QPointF(*delta))
        tool._commit_selection_drag()
        adapter.move_selection(selected, *delta)
    else:
        orbital.setSelected(True)
        assert canvas.services.scene_delete_controller.delete_selected_items()
        adapter.delete_selection(selected)
    assert candidate == snapshot()
    assert candidate["orbitals"][-1] == before["orbitals"][-1]
    if action == "delete" or delta != (0, 0):
        canvas.services.history_service.undo()
        assert snapshot() == before
        canvas.services.history_service.redo()
        assert snapshot() == candidate


@pytest.mark.parametrize("handle", ["scale", "rotate"])
@pytest.mark.parametrize(
    "position", [(37, -21), (37, -100), (-50, 37), (60, 20), (37.001, -21.001)]
)
@pytest.mark.parametrize("snap,step", [(False, 15), (True, 15), (True, 30)])
@pytest.mark.parametrize("length", [20, 40])
def test_browser_orbital_handles_match_native(
    desktop_canvas, handle, position, snap, step, length
):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    source = new_document()
    source["state"]["settings"]["bond_length_px"] = length
    source["state"]["orbitals"] = [
        {"kind": "sp3", "center": [37, -21], "scale": 2, "rotation": 45}
    ]
    canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    snapshot = canvas.services.canvas_document_session_service.snapshot_state
    candidate = deepcopy(snapshot())
    adapter = BrowserStructureAdapter(candidate)
    for settings in (
        canvas.runtime_state.tool_settings_state,
        adapter.runtime_state.tool_settings_state,
    ):
        settings.orbital_snap_enabled = snap
        settings.orbital_snap_step = step
    item = canvas.runtime_state.orbital_items()[0]
    service = canvas.services.handle_mutation_service
    if handle == "scale":
        service.update_orbital_scale(item, QPointF(*position))
    else:
        service.update_orbital_rotate(item, QPointF(*position))
    adapter.move_orbital_handle(
        {
            "kind": "orbital_handle",
            "id": 0,
            "handle": handle,
            "position": list(position),
        }
    )
    assert candidate == snapshot()


@pytest.mark.parametrize(
    "patch",
    [
        {"id": -1},
        {"id": True},
        {"id": 1},
        {"handle": "missing"},
        {"position": [float("nan"), 0]},
        {"position": [0, float("inf")]},
        {"position": [True, 0]},
        {"position": [0]},
        {"unexpected": 1},
    ],
)
def test_orbital_handle_rejects_invalid_input_without_mutation(patch):
    source = new_document()["state"]
    source["orbitals"] = [{"kind": "p", "center": [37, -21], "scale": 1, "rotation": 0}]
    before = deepcopy(source)
    adapter = BrowserStructureAdapter(source)
    edit = {
        "kind": "orbital_handle",
        "id": 0,
        "handle": "scale",
        "position": [50, 20],
        **patch,
    }
    with pytest.raises(ValueError):
        adapter.move_orbital_handle(edit)
    assert source == before


@pytest.mark.parametrize(
    "kind", ["s", "p", "sp", "sp2", "sp3", "d", "mo_bonding", "mo_antibonding"]
)
@pytest.mark.parametrize("operation", [37, -90, "horizontal", "vertical"])
@pytest.mark.parametrize("multiple", [False, True])
def test_browser_orbital_selection_transform_matches_native(
    desktop_canvas, kind, operation, multiple
):
    canvas = desktop_canvas
    source = new_document()
    source["state"]["orbitals"] = [
        {"kind": kind, "center": [37, -21], "scale": 0.5, "rotation": 45},
        {"kind": "p", "center": [130, 70], "scale": 2, "rotation": -90},
    ]
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    before = documents.snapshot_state()
    candidate = deepcopy(before)
    adapter = BrowserStructureAdapter(candidate)
    selection = [{"target": "orbital", "id": i} for i in range(2 if multiple else 1)]
    for item in canvas.runtime_state.orbital_items()[: len(selection)]:
        item.setSelected(True)
    controller = canvas.services.scene_transform_controller
    if isinstance(operation, str):
        controller.flip_selected_items(operation == "horizontal")
        edit = {
            "kind": "flip",
            "horizontal": operation == "horizontal",
            "selection": selection * 2,
        }
    else:
        controller.rotate_selected_items(operation)
        edit = {"kind": "rotate", "value": operation, "selection": selection * 2}
    adapter.transform_selection(edit)
    expected = documents.snapshot_state()
    for actual, native in zip(candidate["orbitals"], expected["orbitals"], strict=True):
        assert actual.keys() == native.keys()
        assert actual["center"] == pytest.approx(native["center"], rel=0, abs=1e-10)
        assert actual["rotation"] == native["rotation"]
        assert actual["scale"] == native["scale"]
        assert actual["kind"] == native["kind"]
    canvas.services.history_service.undo()
    assert documents.snapshot_state() == before
    canvas.services.history_service.redo()
    assert documents.snapshot_state() == expected


@pytest.mark.parametrize(
    "mode",
    ["left", "center", "right", "top", "middle", "bottom", "horizontal", "vertical"],
)
def test_browser_orbital_arrangement_matches_native(desktop_canvas, mode):
    canvas = desktop_canvas
    source = new_document()
    source["state"]["orbitals"] = [
        {"kind": kind, "center": [x, y], "scale": scale, "rotation": angle}
        for kind, x, y, scale, angle in [
            ("sp", -150, -20, 0.5, 45),
            ("d", 37, 65, 1, 0),
            ("mo_antibonding", 130, -90, 2, -90),
        ]
    ]
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    before = documents.snapshot_state()
    candidate = deepcopy(before)
    adapter = BrowserStructureAdapter(candidate)
    for item in canvas.runtime_state.orbital_items():
        item.setSelected(True)
    distribute = mode in {"horizontal", "vertical"}
    controller = canvas.services.scene_transform_controller
    (
        controller.distribute_selected_items
        if distribute
        else controller.align_selected_items
    )(mode)
    selection = [{"target": "orbital", "id": i} for i in range(3)]
    adapter.arrange_selection(
        selection, mode, distribute=distribute, drawing=document_info(source)["drawing"]
    )
    expected = documents.snapshot_state()
    for actual, native in zip(candidate["orbitals"], expected["orbitals"], strict=True):
        assert actual["center"] == pytest.approx(native["center"], rel=0, abs=1e-10)
        assert actual["kind"] == native["kind"]
        assert actual["rotation"] == native["rotation"]
        assert actual["scale"] == native["scale"]
    canvas.services.history_service.undo()
    assert documents.snapshot_state() == before


@pytest.mark.parametrize(
    "kind", ["s", "p", "sp", "sp2", "sp3", "d", "mo_bonding", "mo_antibonding"]
)
@pytest.mark.parametrize("position", [(37, -21), (-100, 100)])
def test_browser_orbital_insertion_uses_native_defaults(desktop_canvas, kind, position):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    documents = canvas.services.canvas_document_session_service
    before = documents.snapshot_state()
    candidate = deepcopy(before)
    adapter = BrowserStructureAdapter(candidate)
    canvas.runtime_state.tool_settings_state.active_orbital_type = kind
    canvas.services.scene_decoration_service.add_orbital(QPointF(*position))
    adapter.insert_orbital(
        {"kind": "orbital", "x": position[0], "y": position[1], "orbital_kind": kind}
    )
    assert candidate == documents.snapshot_state()
    canvas.services.history_service.undo()
    assert documents.snapshot_state() == before
    canvas.services.history_service.redo()
    assert documents.snapshot_state() == candidate


def test_browser_orbital_options_reuse_native_declarations():
    from chemvas.shell.icon_design import design_icon_svg
    from chemvas.ui.window.main_window_toolbar_logic import ORBITAL_TYPE_BY_LABEL

    spec = ui_spec()
    assert [item["key"] for item in spec["orbital_options"]] == list(
        ORBITAL_TYPE_BY_LABEL.values()
    )
    assert [item["label"] for item in spec["orbital_options"]] == [
        f"Orbital: {label}" for label in ORBITAL_TYPE_BY_LABEL
    ]
    for item in spec["orbital_options"][:6]:
        assert item["icon"] == design_icon_svg("orbital_" + item["key"])
    assert [item["text"] for item in spec["orbital_options"][-2:]] == ["MO+", "MO−"]
    assert [item["icon"] for item in spec["orbital_phases"]] == [
        design_icon_svg("orbital_phase_off"),
        design_icon_svg("orbital_phase_on"),
    ]


@pytest.mark.parametrize(
    "kind", ["s", "p", "sp", "sp2", "sp3", "d", "mo_bonding", "mo_antibonding"]
)
def test_browser_orbital_phase_matches_native_settings_history(desktop_canvas, kind):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QGraphicsEllipseItem

    canvas = desktop_canvas
    canvas.runtime_state.tool_settings_state.active_orbital_type = kind
    native = canvas.services.scene_decoration_service.add_orbital(QPointF(37, -21))
    documents = canvas.services.canvas_document_session_service
    before = documents.snapshot_state()
    candidate = deepcopy(before)
    adapter = BrowserStructureAdapter(candidate)
    canvas.services.tool_mode_controller.set_orbital_phase_enabled(True)
    adapter.set_drawing_settings({"kind": "orbital_phase", "enabled": True})
    assert candidate == documents.snapshot_state()
    assert all(
        item.brush().style().name == "SolidPattern"
        for item in native.childItems()
        if isinstance(item, QGraphicsEllipseItem)
    )
    canvas.services.history_service.undo()
    assert documents.snapshot_state() == before
    canvas.services.history_service.redo()
    assert documents.snapshot_state() == candidate


@pytest.mark.parametrize(
    "kind", ["s", "p", "sp", "sp2", "sp3", "d", "mo_bonding", "mo_antibonding"]
)
@pytest.mark.parametrize("length", [10, 40])
def test_native_orbital_length_refresh_matches_reload_and_browser(
    desktop_canvas, kind, length
):
    from PyQt6.QtCore import QPointF

    from chemvas.bootstrap.web_adapter import drawing_geometry

    canvas = desktop_canvas
    canvas.runtime_state.tool_settings_state.active_orbital_type = kind
    item = canvas.services.scene_decoration_service.add_orbital(QPointF(37, -21))
    item.apply_orbital_state({"center": (70, 50), "scale": 0.5, "rotation": 45})
    canvas.services.handle_overlay_service.show_orbital_handles(item)
    before_bounds = item.sceneBoundingRect().getRect()
    before_state = item.orbital_state()
    record_id = item.record_id
    documents = canvas.services.canvas_document_session_service
    canvas.services.geometry_controller.set_bond_length(length)
    bounds = item.sceneBoundingRect().getRect()
    assert item.record_id == record_id and item.orbital_state() == before_state
    drawing = drawing_geometry(documents.snapshot_state())["orbitals"][0]
    assert bounds == pytest.approx(drawing["bounds"], abs=1e-10, rel=0)
    assert not canvas.runtime_state.handle_state.active_handles
    canvas.services.handle_overlay_service.show_orbital_handles(item)
    assert [
        (h.pos().x(), h.pos().y())
        for h in canvas.runtime_state.handle_state.active_handles
    ] == [h["point"] for h in drawing["handles"]]
    canvas.services.history_service.undo()
    assert item.sceneBoundingRect().getRect() == pytest.approx(
        before_bounds, abs=1e-10, rel=0
    )
    canvas.services.history_service.redo()
    assert item.sceneBoundingRect().getRect() == pytest.approx(bounds, abs=1e-10, rel=0)
    documents.apply_state(documents.snapshot_state())
    assert canvas.runtime_state.orbital_items()[
        0
    ].sceneBoundingRect().getRect() == pytest.approx(bounds, abs=1e-10, rel=0)


@pytest.mark.parametrize(
    "kind", ["s", "p", "sp", "sp2", "sp3", "d", "mo_bonding", "mo_antibonding"]
)
def test_orbital_session_preview_history_and_native_reopen(desktop_canvas, kind):
    session = BrowserSession()
    source = draw_bond(new_document())["document"]
    current = session.dispatch({"action": "load", "revision": 0, "document": source})
    original_model = deepcopy(source["state"]["model"])
    selection = [{"target": "orbital", "id": 0}]
    changes = [
        {"kind": "orbital", "orbital_kind": kind, "x": 60, "y": 70},
        {"kind": "orbital_phase", "enabled": True},
        {"kind": "move", "selection": selection, "dx": 30, "dy": -10},
        {"kind": "orbital_handle", "id": 0, "handle": "scale", "position": [122, 60]},
        {"kind": "orbital_handle", "id": 0, "handle": "rotate", "position": [106, 44]},
        {"kind": "rotate", "selection": selection, "value": 37},
        {"kind": "flip", "selection": selection, "horizontal": True},
        {"kind": "bond_length", "value": 40},
        {"kind": "delete_selection", "selection": selection},
    ]
    documents = [current["document"]]
    for change in changes:
        before = session.dispatch({"action": "read"})
        preview = session.dispatch(
            {"action": "preview", "revision": before["revision"], "edit": change}
        )
        # Dropping a candidate is cancellation: no history or saved-state changes.
        assert session.dispatch({"action": "read"}) == before
        current = session.dispatch(
            {"action": "edit", "revision": before["revision"], "edit": change}
        )
        assert current["document"] == preview["document"]
        assert current["document"] != before["document"], change
        assert current["dirty"] and current["can_undo"]
        assert not current["unsupported"]
        documents.append(current["document"])
    assert not current["document"]["state"]["orbitals"]
    # Undo every accepted edit, then replay through the same existing history owner.
    for document in reversed(documents[:-1]):
        current = session.dispatch({"action": "undo", "revision": current["revision"]})
        assert current["document"] == document
    assert not current["dirty"] and not current["can_undo"]
    for document in documents[1:]:
        current = session.dispatch({"action": "redo", "revision": current["revision"]})
        assert current["document"] == document
    # Restore the orbital and open the JSON copy in both adapters.
    current = session.dispatch({"action": "undo", "revision": current["revision"]})
    saved = json.loads(json.dumps(current["document"]))
    reopened = BrowserSession().dispatch(
        {"action": "load", "revision": 0, "document": saved, "name": "orbitals.chemvas"}
    )
    assert not reopened["dirty"] and not reopened["can_undo"]
    assert not reopened["unsupported"]
    assert reopened["document"] == saved
    native = desktop_canvas.services.canvas_document_session_service
    native.apply_state(extract_document_state(saved))
    assert json.loads(json.dumps(native.snapshot_state())) == saved["state"]
    # Orbital-only changes leave the pre-existing bond intact until its length edit.
    assert documents[-3]["state"]["model"] == original_model


@pytest.mark.parametrize(
    "kind",
    [
        "square_pair",
        "parentheses_pair",
        "braces_pair",
        "square_left",
        "parenthesis_left",
        "brace_left",
        "dagger",
        "double_dagger",
    ],
)
@pytest.mark.parametrize("length", [10, 20, 40])
def test_browser_bracket_drawing_uses_native_paths(desktop_canvas, kind, length):
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QFont, QPainterPath, QPainterPathStroker

    source = new_document()
    source["state"]["settings"]["bond_length_px"] = length
    source["state"]["ts_brackets"] = [
        {
            "kind": "ts_bracket",
            "bracket_kind": kind,
            "left": 37,
            "top": -21,
            "right": 73,
            "bottom": 27,
        }
    ]
    info = document_info(source, font=native_mark_measurements(source, glyph_ink=True))
    assert not info["unsupported"]
    geometry = info["drawing"]["brackets"][0]
    desktop_canvas.renderer.set_bond_length(length)
    original = desktop_canvas.services.scene_decoration_build_service.ts_bracket_path(
        QRectF(37, -21, 36, 48), kind
    )
    materialized = QPainterPath()
    if geometry["symbol"]:
        symbol = geometry["symbol"]
        font = QFont(symbol["family"])
        font.setPixelSize(symbol["pixels"])
        materialized.addText(symbol["x"], symbol["y"], font, symbol["text"])
        if length == 20:
            assert symbol["pixels"] == 27
            assert symbol["x"] == pytest.approx(49.6)
            assert symbol["y"] == pytest.approx(12.72)
    else:
        for command, coordinates in geometry["path"]:
            if command == "M":
                materialized.moveTo(*coordinates)
            elif command == "L":
                materialized.lineTo(*coordinates)
            else:
                materialized.cubicTo(*coordinates)
        stroker = QPainterPathStroker()
        stroker.setWidth(geometry["width"])
        stroker.setCapStyle(Qt.PenCapStyle.FlatCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        materialized = stroker.createStroke(materialized)
        # Selection, alignment and pivots use the filled outline's bounds.
        assert geometry["bounds"] == pytest.approx(
            original.boundingRect().getRect(), abs=1e-3
        )
    assert materialized == original


@pytest.mark.parametrize(
    "kind",
    [
        "square_pair",
        "parentheses_pair",
        "braces_pair",
        "square_left",
        "parenthesis_left",
        "brace_left",
        "dagger",
        "double_dagger",
    ],
)
@pytest.mark.parametrize(
    "start,end",
    [
        ([30, 40], [30, 40]),
        ([100, 70], [10, -30]),
        ([30, 40], [32, 42]),
        ([10, 20], [100, 120]),
    ],
)
def test_bracket_insertion_matches_native_and_preserves_preview(
    desktop_canvas, kind, start, end
):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    rect = canvas.services.scene_decoration_build_service.ts_bracket_rect_from_points(
        QPointF(*start), QPointF(*end)
    )
    canvas.services.scene_decoration_service.add_ts_bracket(rect, bracket_kind=kind)
    expected = canvas.services.canvas_document_session_service.snapshot_state()[
        "ts_brackets"
    ]
    session = BrowserSession()
    before = session.dispatch({"action": "read"})
    edit = {"kind": "ts_bracket", "start": start, "end": end, "style": kind}
    preview = session.dispatch({"action": "preview", "revision": 0, "edit": edit})
    assert session.dispatch({"action": "read"}) == before
    result = session.dispatch({"action": "edit", "revision": 0, "edit": edit})
    assert result["document"] == preview["document"]
    assert result["document"]["state"]["ts_brackets"] == expected
    assert not result["unsupported"]
    assert (
        session.dispatch({"action": "undo", "revision": 1})["document"]
        == before["document"]
    )
    assert (
        session.dispatch({"action": "redo", "revision": 2})["document"]
        == result["document"]
    )


@pytest.mark.parametrize(
    "kind",
    [
        "square_pair",
        "parentheses_pair",
        "braces_pair",
        "square_left",
        "parenthesis_left",
        "brace_left",
        "dagger",
        "double_dagger",
    ],
)
@pytest.mark.parametrize("delta", [(10, 7), (-12.5, 3.25), (0, 0)])
@pytest.mark.parametrize("action", ["move", "delete"])
def test_bracket_move_delete_matches_native_history(
    desktop_canvas, kind, delta, action
):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    source = new_document()
    source["state"]["ts_brackets"] = [
        {
            "kind": "ts_bracket",
            "bracket_kind": kind,
            "left": 37,
            "top": -21,
            "right": 73,
            "bottom": 27,
        },
        {
            "kind": "ts_bracket",
            "bracket_kind": "square_pair",
            "left": 100,
            "top": 70,
            "right": 136,
            "bottom": 118,
        },
    ]
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    before = documents.snapshot_state()
    candidate = deepcopy(before)
    adapter = BrowserStructureAdapter(candidate)
    bracket = canvas.runtime_state.ts_bracket_items()[0]
    selected = [{"target": "ts_bracket", "id": 0}] * 2
    if action == "move":
        tool = canvas.services.tool_controller.tools["select"]
        assert tool._begin_selection_drag(set(), [bracket], QPointF())
        tool._apply_drag_delta(QPointF(*delta))
        tool._commit_selection_drag()
        adapter.move_selection(selected, *delta)
    else:
        bracket.setSelected(True)
        assert canvas.services.scene_delete_controller.delete_selected_items()
        adapter.delete_selection(selected)
    assert candidate == documents.snapshot_state()
    assert candidate["ts_brackets"][-1] == before["ts_brackets"][-1]
    if action == "delete" or delta != (0, 0):
        canvas.services.history_service.undo()
        assert documents.snapshot_state() == before
        canvas.services.history_service.redo()
        assert documents.snapshot_state() == candidate


BRACKET_KINDS = [
    "square_pair",
    "parentheses_pair",
    "braces_pair",
    "square_left",
    "parenthesis_left",
    "brace_left",
    "dagger",
    "double_dagger",
]


def bracket_document(kind, length=20, rect=(1000, 900, 36, 48)):
    source = new_document()
    source["state"]["settings"]["bond_length_px"] = length
    x, y, width, height = rect
    source["state"]["ts_brackets"] = [
        {
            "kind": "ts_bracket",
            "bracket_kind": kind,
            "left": x,
            "top": y,
            "right": x + width,
            "bottom": y + height,
        }
    ]
    return source


@pytest.mark.parametrize("kind", BRACKET_KINDS)
@pytest.mark.parametrize("length", [10, 20, 40])
def test_browser_bracket_bounds_and_scene_range_match_native(
    desktop_canvas, kind, length
):
    from chemvas.ui.canvas.sheet_setup_access import apply_sheet_scene_rect_for

    source = bracket_document(kind, length)
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    apply_sheet_scene_rect_for(desktop_canvas)
    item = desktop_canvas.runtime_state.ts_bracket_items()[0]
    drawing = document_info(
        source, font=native_mark_measurements(source, glyph_ink=True)
    )["drawing"]
    # Glyph ink comes from flattened outline polygons; strokes are sampled.
    tolerance = 2e-2 if kind in {"dagger", "double_dagger"} else 1e-3
    assert drawing["brackets"][0]["bounds"] == pytest.approx(
        item.sceneBoundingRect().getRect(), abs=tolerance
    )
    assert drawing["scene_rect"] == pytest.approx(
        desktop_canvas.sceneRect().getRect(), abs=tolerance
    )


def test_dagger_documents_request_glyph_measurements():
    info = document_info(bracket_document("dagger"))
    spec = info["drawing"]["label_measurements"]
    assert info["drawing"]["needs_measurements"]
    assert [query["text"] for query in spec["queries"]] == ["†"]
    assert spec["queries"][0]["pixels"] == 27
    assert browser_font_pixels(spec["queries"][0]["size"]) == 27


@pytest.mark.parametrize("kind", ["square_pair", "parenthesis_left", "brace_left"])
@pytest.mark.parametrize("scale", [0.5, 1, 3])
def test_browser_bracket_pick_matches_native(desktop_canvas, kind, scale):
    from PyQt6.QtCore import QPointF

    from chemvas.ui.canvas.canvas_hit_testing_service import (
        scene_items_at_pos_for_canvas,
    )
    from chemvas.ui.canvas.input_view_access import update_view_transform_for

    source = bracket_document(kind, rect=(0, 0, 36, 48))
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    desktop_canvas.runtime_state.input_view_state.zoom = scale
    update_view_transform_for(desktop_canvas)
    item = desktop_canvas.runtime_state.ts_bracket_items()[0]
    hit_testing = desktop_canvas.services.hit_testing_service
    view = desktop_canvas.viewportTransform()
    outline = view.map(item.mapToScene(item.path())).toSubpathPolygons()
    adapter = BrowserStructureAdapter(extract_document_state(source))
    checked = 0
    for y in (4.0, 24.0, 44.0):
        for offset in (-10, -6.5, -5.5, -2, 0, 2, 5.5, 6.5, 10):
            point = QPointF(offset / scale, y)
            screen = view.map(point)
            distance = min(
                hit_testing.distance_point_to_segment(screen, poly[i - 1], poly[i])
                for poly in outline
                for i in range(1, len(poly))
            )
            direct = item in scene_items_at_pos_for_canvas(desktop_canvas, point)
            # Qt flattens the filled outline; skip points on the 6 px boundary.
            if not direct and abs(distance - ARROW_PICK_SCREEN_PX) < 0.1:
                continue
            checked += 1
            hits = [{"target": "ts_bracket", "id": 0}] if direct else []
            expected = hit_testing.item_at_scene_pos(point)
            actual = adapter.pick_target(
                point.x(), point.y(), hits, preferred=False, scale=scale
            )
            assert actual == (
                None if expected is None else {"target": "ts_bracket", "id": 0}
            ), (kind, scale, y, offset)
    assert checked >= 20


@pytest.mark.parametrize("kind", ["dagger", "double_dagger"])
def test_browser_dagger_hit_uses_measured_glyph_box(desktop_canvas, kind):
    from PyQt6.QtCore import QPointF

    source = bracket_document(kind, rect=(0, 0, 36, 48))
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    font = native_mark_measurements(source, glyph_ink=True)
    x, y, width, height = document_info(source, font=font)["drawing"]["brackets"][0][
        "bounds"
    ]
    adapter = BrowserStructureAdapter(extract_document_state(source))
    center = QPointF(x + width / 2, y + height * 0.45)
    far = QPointF(x - 40, y + height / 2)
    hit_testing = desktop_canvas.services.hit_testing_service
    assert hit_testing.item_at_scene_pos(center) is not None
    assert adapter.pick_target(
        center.x(),
        center.y(),
        [{"target": "ts_bracket", "id": 0}],
        preferred=False,
        scale=1,
    ) == {"target": "ts_bracket", "id": 0}
    assert hit_testing.item_at_scene_pos(far) is None
    assert adapter.pick_target(far.x(), far.y(), [], preferred=False, scale=1) is None


@pytest.mark.parametrize("kind", ["square_pair", "brace_left", "double_dagger"])
@pytest.mark.parametrize("operation", ["rotate", "horizontal", "vertical"])
def test_browser_bracket_transform_matches_native(desktop_canvas, kind, operation):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(-60, 10), QPointF(-40, 10), "single", 1
    )
    canvas.services.scene_decoration_service.add_ts_bracket(
        canvas.services.scene_decoration_build_service.ts_bracket_rect_from_points(
            QPointF(10, -20), QPointF(40, 30)
        ),
        bracket_kind=kind,
    )
    snapshot = canvas.services.canvas_document_session_service.snapshot_state
    before = snapshot()
    source = build_document_payload(before, 9)
    font = native_mark_measurements(source, glyph_ink=True)
    drawing = document_info(source, font=font)["drawing"]
    candidate = deepcopy(before)
    adapter = BrowserStructureAdapter(candidate)
    for item in canvas.runtime_state.atom_graphics_state.atom_dots.values():
        item.setSelected(True)
    canvas.runtime_state.ts_bracket_items()[0].setSelected(True)
    request = [
        {"target": "atom", "id": 0},
        {"target": "atom", "id": 1},
        {"target": "ts_bracket", "id": 0},
    ]
    controller = canvas.services.scene_transform_controller
    if operation == "rotate":
        controller.rotate_selected_items(37)
        edit = {"kind": "rotate", "value": 37, "selection": request}
    else:
        controller.flip_selected_items(operation == "horizontal")
        edit = {
            "kind": "flip",
            "horizontal": operation == "horizontal",
            "selection": request,
        }
    adapter.transform_selection(edit, drawing)
    expected = snapshot()
    tolerance = 2e-2 if kind in BRACKET_SYMBOLS else 1e-3
    assert candidate["ts_brackets"][0] == pytest.approx(
        expected["ts_brackets"][0], abs=tolerance
    )
    for atom_id, atom in candidate["model"]["atoms"].items():
        assert atom == pytest.approx(expected["model"]["atoms"][atom_id], abs=tolerance)


@pytest.mark.parametrize("kind", ["square_left", "parentheses_pair", "dagger"])
@pytest.mark.parametrize("mode", ["left", "center", "bottom"])
def test_browser_bracket_alignment_matches_native(desktop_canvas, kind, mode):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(-60, 10), QPointF(-40, 30), "single", 1
    )
    canvas.services.scene_decoration_service.add_ts_bracket(
        canvas.services.scene_decoration_build_service.ts_bracket_rect_from_points(
            QPointF(10, -20), QPointF(40, 30)
        ),
        bracket_kind=kind,
    )
    snapshot = canvas.services.canvas_document_session_service.snapshot_state
    before = snapshot()
    source = build_document_payload(before, 9)
    drawing = document_info(
        source, font=native_mark_measurements(source, glyph_ink=True)
    )["drawing"]
    candidate = deepcopy(before)
    for item in canvas.runtime_state.atom_graphics_state.atom_dots.values():
        item.setSelected(True)
    canvas.runtime_state.ts_bracket_items()[0].setSelected(True)
    canvas.services.scene_transform_controller.align_selected_items(mode)
    BrowserStructureAdapter(candidate).transform_selection(
        {
            "kind": "align",
            "mode": mode,
            "selection": [
                {"target": "atom", "id": 0},
                {"target": "ts_bracket", "id": 0},
            ],
        },
        drawing,
    )
    expected = snapshot()
    tolerance = 2e-2 if kind in BRACKET_SYMBOLS else 1e-3
    assert candidate["ts_brackets"][0] == pytest.approx(
        expected["ts_brackets"][0], abs=tolerance
    )
    for atom_id, atom in candidate["model"]["atoms"].items():
        assert atom == pytest.approx(expected["model"]["atoms"][atom_id], abs=tolerance)


def test_bracket_color_notice_and_selection_outline():
    source = bracket_document("square_pair", rect=(0, 0, 36, 48))
    source["state"]["ts_brackets"].append(
        {**bracket_document("dagger")["state"]["ts_brackets"][0]}
    )
    changed = edit_document(
        {
            "document": source,
            "edit": {
                "kind": "color",
                "color": "#ff0000",
                "selection": [{"target": "ts_bracket", "id": 0}],
            },
        }
    )
    assert changed["edit_notice"] == COLOR_TOOL_MESSAGES["ts_bracket"]
    assert changed["document"]["state"]["ts_brackets"] == source["state"]["ts_brackets"]
    font = native_mark_measurements(source, glyph_ink=True)
    drawing = document_info(source, font=font)["drawing"]
    adapter = BrowserStructureAdapter(extract_document_state(source))
    stroke, glyph = adapter.selection_components(
        [{"target": "ts_bracket", "id": 0}, {"target": "ts_bracket", "id": 1}],
        drawing,
    )
    pad = RenderMetrics().style.bond_length_px * SELECTION_OBJECT_PADDING_RATIO
    assert stroke == [
        {
            "path": drawing["brackets"][0]["path"],
            "width": drawing["brackets"][0]["width"] + pad * 2,
        }
    ]
    assert glyph == [
        {
            "text": drawing["brackets"][1]["symbol"],
            "width": pad * 2,
            "bounds": drawing["brackets"][1]["bounds"],
        }
    ]


def test_shift_tool_hotkeys_follow_native_generic_shortcuts():
    from chemvas.ui.canvas.canvas_chemdraw_shortcut_service import (
        CanvasChemdrawShortcutService,
    )

    spec = ui_spec()
    assert spec["shift_tool_hotkeys"] == {
        "T": {"tool": "ts_bracket", "value": "square_pair"},
        "G": {
            "tool": "orbital",
            "value": CanvasChemdrawShortcutService.DEFAULT_ORBITAL_TYPE,
        },
        "E": {"tool": "mark", "value": CanvasChemdrawShortcutService.DEFAULT_MARK_KIND},
    }
    assert (
        spec["default_arrow_style"] == CanvasChemdrawShortcutService.DEFAULT_ARROW_TYPE
    )
    # Shift+E labels a hovered atom; over empty canvas it opens the Mark tool.
    adapter = BrowserStructureAdapter(extract_document_state(new_document()))
    assert adapter.apply_hover_shortcut(0, 0, "E") == "mark"
    assert adapter.apply_hover_shortcut(0, 0, "e") == "arrow"


@pytest.mark.parametrize(
    "kind", [kind for kind in BRACKET_KINDS if kind not in BRACKET_SYMBOLS]
)
@pytest.mark.parametrize("height", [0, 0.25])
def test_flat_brackets_open_with_native_outline_bounds(desktop_canvas, kind, height):
    # Qt drops zero-length sides, clips reversing miters at its limit and joins
    # a subpath that returns to its start.
    source = bracket_document(kind, rect=(0, 0, 36, height))
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    item = desktop_canvas.runtime_state.ts_bracket_items()[0]
    info = document_info(source)
    assert not info["unsupported"]
    # A nearly reversing brace joint approximates Qt's clipped miter tip.
    assert info["drawing"]["brackets"][0]["bounds"] == pytest.approx(
        item.sceneBoundingRect().getRect(), abs=1e-3 if height == 0 else 5e-3
    )


@pytest.mark.parametrize("kind", ["dagger", "double_dagger"])
# The convex ink hull fills the dagger's concavities, so points level with the
# stem but beside a crossbar can be caught a few pixels earlier than in Qt.
@pytest.mark.parametrize("gap", [1, 3, 8])
def test_browser_dagger_near_pick_matches_native(desktop_canvas, kind, gap):
    from PyQt6.QtCore import QPointF

    source = bracket_document(kind, rect=(0, 0, 36, 48))
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    font = native_mark_measurements(source, glyph_ink=True)
    drawing = document_info(source, font=font)["drawing"]
    x, y, _width, height = drawing["brackets"][0]["bounds"]
    point = QPointF(x - gap, y + height / 2)
    expected = desktop_canvas.services.hit_testing_service.item_at_scene_pos(point)
    adapter = BrowserStructureAdapter(
        extract_document_state(source), measured_drawing=drawing
    )
    actual = adapter.pick_target(point.x(), point.y(), [], preferred=False, scale=1)
    assert actual == (None if expected is None else {"target": "ts_bracket", "id": 0})


def test_bracket_transforms_without_measured_font():
    source = bracket_document("square_pair", rect=(0, 0, 36, 48))
    source["state"]["ts_brackets"].append(
        bracket_document("dagger", rect=(60, 0, 36, 48))["state"]["ts_brackets"][0]
    )
    rotated = edit_document(
        {
            "document": source,
            "edit": {
                "kind": "rotate",
                "value": 90,
                "selection": [{"target": "ts_bracket", "id": 0}],
            },
        }
    )
    # An axis-aligned bracket turned about its own centre stays in place.
    assert rotated["document"]["state"]["ts_brackets"][0] == pytest.approx(
        source["state"]["ts_brackets"][0]
    )
    with pytest.raises(ValueError, match="Dagger transforms need completed font"):
        edit_document(
            {
                "document": source,
                "edit": {
                    "kind": "rotate",
                    "value": 90,
                    "selection": [{"target": "ts_bracket", "id": 1}],
                },
            }
        )


# Stored exactly as the desktop's NoteItem publishes them after a restore.
QT_NOTE_PARAGRAPH = (
    '<p style="margin-top:0px; margin-bottom:0px; margin-left:0px; '
    'margin-right:0px; text-indent:0px; line-height:100%; white-space:pre-wrap">'
)


@pytest.mark.parametrize(
    ("note", "expected"),
    [
        (
            {"text": "a\nb<"},
            (
                '<p data-style="margin-top:0px; margin-bottom:0px; white-space:pre-wrap">a</p>'
                '<p data-style="margin-top:0px; margin-bottom:0px; white-space:pre-wrap">b&lt;</p>'
            ),
        ),
        (
            {
                "html": QT_NOTE_PARAGRAPH
                + 'H<span style="vertical-align:sub">2</span>O</p>\n'
                '<p style="-qt-paragraph-type:empty; margin-top:0px"><br /></p>'
            },
            (
                '<p data-style="margin-top:0px; margin-bottom:0px; margin-left:0px; '
                'margin-right:0px; text-indent:0px; white-space:pre-wrap">H<span '
                'data-style="font-size:11px" data-script="sub" data-base-pixels="16">'
                '2</span>O</p><p data-style="margin-top:0px; white-space:pre-wrap"></p>'
            ),
        ),
        (
            # Qt scales a script run from its integer point size: 20pt -> 13pt.
            {
                "html": '<p align="center">x <span style="font-size:20pt">B</span>'
                '<span style="font-size:20pt; vertical-align:super">2</span></p>'
            },
            (
                '<p data-style="white-space:pre-wrap" align="center">x <span '
                'data-style="font-size:27px" data-pt="20">B</span><span '
                'data-style="font-size:17px" data-script="super" '
                'data-base-pixels="27" data-pt="20">2</span></p>'
            ),
        ),
        (
            # Bare inline HTML gets Qt's implicit block without margins.
            {"html": "<b>bold</b> &amp; plain"},
            (
                '<p data-style="margin-top:0px; margin-bottom:0px; white-space:pre-wrap">'
                "<b>bold</b> &amp; plain</p>"
            ),
        ),
    ],
)
def test_browser_note_html_follows_the_native_restore(note, expected):
    assert browser_note_html(note, 12) == expected


@pytest.mark.parametrize(
    "html",
    [
        "<ul><li>item</li></ul>",
        '<p><span style="font-size:1.5em">em</span></p>',
        '<p><span style="vertical-align:sub"><sup>2</sup></span></p>',
    ],
)
def test_unrendered_note_formatting_stays_read_only_with_its_text(html):
    source = new_document()
    source["state"]["notes"] = [{"text": "item", "html": html, "x": 10, "y": 20}]
    info = document_info(source)
    assert info["unsupported"] == [
        "note lists or formatting without a browser renderer"
    ]
    (note,) = browser_notes(extract_document_state(source))
    assert note["html"] == browser_note_html({"text": "item"}, 12)


def native_note_canvas(canvas, notes, **settings):
    """Restore notes on the desktop; return its state and matching browser font."""
    from chemvas.bootstrap.web_adapter import ACS1996Style

    state = extract_document_state(new_document())
    state["notes"] = notes
    state["settings"].update(settings)
    canvas.services.canvas_document_session_service.apply_state(state)
    items = sorted(
        canvas.runtime_state.note_items(), key=lambda item: (item.y(), item.x())
    )
    snapshot = canvas.services.canvas_document_session_service.snapshot_state()
    boxes = {
        spec["key"]: [item.boundingRect().width(), item.boundingRect().height()]
        for spec, item in zip(
            browser_notes(snapshot),
            sorted(
                items,
                key=lambda item: [(n["y"], n["x"]) for n in snapshot["notes"]].index(
                    (item.y(), item.x())
                ),
            ),
            strict=True,
        )
    }
    font = BrowserFontMeasurements(
        {
            "family": ACS1996Style().font_family,
            "metrics": {},
            "ink": {},
            "label_boxes": boxes,
        }
    )
    return snapshot, font


SAMPLE_NOTES = [
    {"text": "Hello\nworld", "html": "", "x": 20.0, "y": -30.0, "rotation": 30.0},
    {
        "text": "H2O",
        "html": QT_NOTE_PARAGRAPH + 'H<span style="vertical-align:sub">2</span>O</p>',
        "x": -40.0,
        "y": 50.0,
    },
]


def test_browser_note_bounds_box_and_scene_range_match_native(desktop_canvas):
    state, font = native_note_canvas(
        desktop_canvas,
        deepcopy(SAMPLE_NOTES),
        note_box_enabled=True,
        note_border_enabled=True,
        note_border_width=3.0,
        note_padding=5.0,
    )
    source = build_document_payload(state, 9)
    info = document_info(source, font=font)
    assert info["unsupported"] == []
    drawing = info["drawing"]
    items = {
        (item.x(), item.y()): item for item in desktop_canvas.runtime_state.note_items()
    }
    for note in drawing["notes"]:
        item = items[(note["x"], note["y"])]
        rect = item.sceneBoundingRect()
        assert note["bounds"] == pytest.approx(
            (rect.x(), rect.y(), rect.width(), rect.height()), abs=1e-9
        )
        box = item.data(20).sceneBoundingRect()
        assert drawing["scene_rect"][0] <= box.left()
        assert drawing["scene_rect"][1] <= box.top()
    assert drawing["note_box"] == {
        "padding": 5.0,
        "fill": "rgba(255,255,255,1.0)",
        "stroke": "#333333",
        "width": 3.0,
    }


@pytest.mark.parametrize("operation", ["rotate", "horizontal", "vertical"])
def test_browser_note_transform_matches_native(desktop_canvas, operation):
    from PyQt6.QtCore import QPointF

    canvas = desktop_canvas
    before, font = native_note_canvas(canvas, deepcopy(SAMPLE_NOTES))
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(-60, 10), QPointF(-40, 10), "single", 1
    )
    before = canvas.services.canvas_document_session_service.snapshot_state()
    drawing = document_info(build_document_payload(before, 9), font=font)["drawing"]
    for item in [
        *canvas.runtime_state.atom_graphics_state.atom_dots.values(),
        *canvas.runtime_state.note_items(),
    ]:
        item.setSelected(True)
    request = [
        {"target": "atom", "id": 0},
        {"target": "atom", "id": 1},
        {"target": "note", "id": 0},
        {"target": "note", "id": 1},
    ]
    controller = canvas.services.scene_transform_controller
    if operation == "rotate":
        controller.rotate_selected_items(-50)
        edit = {"kind": "rotate", "value": -50, "selection": request}
    else:
        controller.flip_selected_items(operation == "horizontal")
        edit = {
            "kind": "flip",
            "horizontal": operation == "horizontal",
            "selection": request,
        }
    candidate = deepcopy(before)
    BrowserStructureAdapter(candidate).transform_selection(edit, drawing)
    expected = canvas.services.canvas_document_session_service.snapshot_state()
    assert candidate["notes"] == [
        pytest.approx(note, abs=1e-9) for note in expected["notes"]
    ]
    for atom_id, atom in candidate["model"]["atoms"].items():
        assert atom == pytest.approx(expected["model"]["atoms"][atom_id], abs=1e-9)


@pytest.mark.parametrize("mode", ["left", "center", "bottom"])
def test_browser_note_alignment_matches_native(desktop_canvas, mode):
    canvas = desktop_canvas
    before, font = native_note_canvas(canvas, deepcopy(SAMPLE_NOTES))
    drawing = document_info(build_document_payload(before, 9), font=font)["drawing"]
    for item in canvas.runtime_state.note_items():
        item.setSelected(True)
    canvas.services.scene_transform_controller.align_selected_items(mode)
    candidate = deepcopy(before)
    BrowserStructureAdapter(candidate).transform_selection(
        {
            "kind": "align",
            "mode": mode,
            "selection": [{"target": "note", "id": 0}, {"target": "note", "id": 1}],
        },
        drawing,
    )
    expected = canvas.services.canvas_document_session_service.snapshot_state()
    assert candidate["notes"] == [
        pytest.approx(note, abs=1e-9) for note in expected["notes"]
    ]


def test_notes_move_delete_and_fail_closed_without_measurements():
    source = new_document()
    source["state"]["notes"] = deepcopy(SAMPLE_NOTES)
    selection = [{"target": "note", "id": 0}]
    moved = edit_document(
        {
            "document": source,
            "edit": {"kind": "move", "selection": selection, "dx": 5, "dy": -2},
        }
    )["document"]["state"]["notes"]
    assert (moved[0]["x"], moved[0]["y"]) == (25.0, -32.0)
    assert moved[1] == SAMPLE_NOTES[1]
    deleted = edit_document(
        {
            "document": source,
            "edit": {"kind": "delete_selection", "selection": selection},
        }
    )["document"]["state"]["notes"]
    assert deleted == [SAMPLE_NOTES[1]]
    with pytest.raises(ValueError, match="Note transforms need completed font"):
        edit_document(
            {
                "document": source,
                "edit": {"kind": "rotate", "value": 15, "selection": selection},
            }
        )


@pytest.mark.parametrize(
    ("hits", "expected"),
    [
        ([{"target": "note", "id": 0}], "note"),
        # Implicit carbons are transparent; a visible label covers the note.
        ([{"target": "atom", "id": 0}, {"target": "note", "id": 0}], "note"),
        ([{"target": "atom", "id": 1}, {"target": "note", "id": 0}], "atom"),
        ([{"target": "bond", "id": 0}, {"target": "note", "id": 0}], "bond"),
    ],
)
def test_note_pick_follows_the_native_foreground_rule(hits, expected):
    source = draw_bond(new_document(), start=(0, 0), end=(20, 0))["document"]
    state = source["state"]
    state["model"]["atoms"][1].update(element="O", explicit_label=True)
    state["notes"] = [{"text": "note", "html": "", "x": -5.0, "y": -5.0}]
    adapter = BrowserStructureAdapter(extract_document_state(source))
    target = adapter.pick_target(10, 0, hits, preferred=True, scale=1)
    assert target["target"] == expected


# What the browser note editor sends: Qt point sizes and script alignment.
EDITOR_NOTE_HTML = (
    '<p style="margin-top:0px; margin-bottom:0px; white-space:pre-wrap">'
    'x <span style="font-size:20pt">B</span>'
    '<span style="font-size:20pt; vertical-align:super">2</span><br>'
    '<span style="font-weight:700; color:rgb(192, 0, 0)">bold&nbsp;red</span></p>'
    '<p style="margin-top:0px; margin-bottom:0px; white-space:pre-wrap">'
    '<span style="font-style:italic">next</span></p>'
)


def test_note_editor_commits_like_the_native_focus_out():
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": new_document()})
    created = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {
                "kind": "note_text",
                "id": None,
                "x": 10,
                "y": -20,
                "html": EDITOR_NOTE_HTML,
            },
        }
    )["document"]["state"]["notes"]
    assert created == [
        {
            "text": "x B2\nbold red\nnext",
            "x": 10.0,
            "y": -20.0,
            "html": sanitize_note_html(EDITOR_NOTE_HTML),
        }
    ]
    updated = session.dispatch(
        {
            "revision": 2,
            "action": "edit",
            "edit": {"kind": "note_text", "id": 0, "html": "<p>changed</p>"},
        }
    )["document"]["state"]["notes"]
    assert updated[0]["text"] == "changed"
    assert (updated[0]["x"], updated[0]["y"]) == (10.0, -20.0)
    # Emptying a note removes it in the same single history step.
    emptied = session.dispatch(
        {
            "revision": 3,
            "action": "edit",
            "edit": {"kind": "note_text", "id": 0, "html": "<p> <br></p>"},
        }
    )["document"]["state"]["notes"]
    assert emptied == []
    assert (
        session.dispatch({"revision": 4, "action": "undo"})["document"]["state"][
            "notes"
        ]
        == updated
    )
    for edit, message in [
        ({"id": None, "x": 0, "y": 0, "html": "<p> </p>"}, "empty note"),
        ({"id": None, "html": "<p>a</p>"}, "needs its position"),
        ({"id": 7, "html": "<p>a</p>"}, "no longer exists"),
        ({"id": 0, "html": "<ul><li>a</li></ul>"}, "no browser renderer"),
        ({"id": None, "x": 1e6, "y": 0, "html": "<p>a</p>"}, "sheet"),
    ]:
        with pytest.raises(ValueError, match=message):
            session.dispatch(
                {
                    "revision": 5,
                    "action": "edit",
                    "edit": {"kind": "note_text", **edit},
                }
            )


def test_note_editor_text_restores_identically_on_the_desktop(desktop_canvas):
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": new_document()})
    document = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {
                "kind": "note_text",
                "id": None,
                "x": 0,
                "y": 0,
                "html": EDITOR_NOTE_HTML,
            },
        }
    )["document"]
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(document)
    )
    (item,) = desktop_canvas.runtime_state.note_items()
    assert item.toPlainText() == document["state"]["notes"][0]["text"]
    box = item.boundingRect()
    saved = desktop_canvas.services.canvas_document_session_service.snapshot_state()
    # Qt's own saved form of the edited note lays out identically.
    desktop_canvas.services.canvas_document_session_service.apply_state(saved)
    (restored,) = desktop_canvas.runtime_state.note_items()
    assert restored.boundingRect() == box
    assert saved["notes"][0]["text"] == document["state"]["notes"][0]["text"]


def test_text_format_page_and_whole_note_formatting():
    from chemvas.ui.window.main_window_config import (
        TEXT_FORMAT_ACTION_GROUPS,
        TEXT_FORMAT_TARGET_MESSAGE,
        TEXT_SIZE_ACTION_SPECS,
    )

    spec = ui_spec()
    assert spec["context_pages"]["note"] == "text"
    assert spec["context_pages"]["text"] == "atom"
    assert [size["delta"] for size in spec["text_format"]["sizes"]] == [
        delta for _, _, delta in TEXT_SIZE_ACTION_SPECS
    ]
    assert [
        [action["key"] for action in group] for group in spec["text_format"]["groups"]
    ] == [[key for key, _, _ in group] for group in TEXT_FORMAT_ACTION_GROUPS]
    assert spec["text_format"]["target_message"] == TEXT_FORMAT_TARGET_MESSAGE
    source = new_document()
    source["state"]["notes"] = deepcopy(SAMPLE_NOTES)
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    markup = session.dispatch(
        {"revision": 1, "action": "note_markup", "html": EDITOR_NOTE_HTML}
    )["html"]
    assert markup == browser_note_html({"html": EDITOR_NOTE_HTML}, 12)
    italic = '<p style="margin-top:0px"><span style="font-style:italic">H2O</span></p>'
    result = session.dispatch(
        {
            "revision": 1,
            "action": "edit",
            "edit": {"kind": "note_format", "notes": [{"id": 1, "html": italic}]},
        }
    )["document"]["state"]["notes"]
    assert result[1]["html"] == sanitize_note_html(italic)
    assert result[1]["text"] == "H2O"
    assert result[0] == SAMPLE_NOTES[0]
    with pytest.raises(ValueError, match="cannot change a note's text"):
        session.dispatch(
            {
                "revision": 2,
                "action": "edit",
                "edit": {
                    "kind": "note_format",
                    "notes": [{"id": 1, "html": "<p>other</p>"}],
                },
            }
        )


def test_note_color_matches_the_native_color_tool(desktop_canvas):
    from PyQt6.QtGui import QColor

    notes = deepcopy(SAMPLE_NOTES)
    notes[1]["html"] = (
        '<p style="margin-top:0px; margin-bottom:0px">x <span style="color:#c00000; '
        'font-weight:700">B</span><br>y</p><p style="-qt-paragraph-type:empty"><br></p>'
    )
    state, _ = native_note_canvas(desktop_canvas, notes)
    source = draw_bond(build_document_payload(state, 9))["document"]
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    items = sorted(desktop_canvas.runtime_state.note_items(), key=lambda item: item.y())
    desktop_canvas.services.canvas_color_mutation_service.apply_color_to_items(
        [*items, *desktop_canvas.runtime_state.atom_graphics_state.atom_dots.values()],
        QColor("#00aa00"),
    )
    expected = desktop_canvas.services.canvas_document_session_service.snapshot_state()
    browser = edit_document(
        {
            "document": source,
            "edit": {
                "kind": "color",
                "color": "#00aa00",
                "selection": [
                    {"target": "note", "id": 0},
                    {"target": "note", "id": 1},
                    {"target": "atom", "id": 0},
                    {"target": "atom", "id": 1},
                ],
            },
        }
    )["document"]["state"]

    def runs(state):
        # Restore each saved note on the desktop and read its character formats.
        desktop_canvas.services.canvas_document_session_service.apply_state(state)
        result = []
        for item in sorted(
            desktop_canvas.runtime_state.note_items(), key=lambda item: item.y()
        ):
            block = item.document().begin()
            while block.isValid():
                fragment = block.begin()
                while not fragment.atEnd():
                    part = fragment.fragment()
                    fmt = part.charFormat()
                    result.append(
                        (part.text(), fmt.foreground().color().name(), fmt.fontWeight())
                    )
                    fragment += 1
                result.append(("block", block.charFormat().foreground().color().name()))
                block = block.next()
        return result

    assert runs(browser) == runs(expected)
    assert [note["text"] for note in browser["notes"]] == [
        note["text"] for note in expected["notes"]
    ]
    assert browser["model"]["atoms"] == expected["model"]["atoms"]


def test_session_limit_drops_only_windows_idle_for_thirty_minutes(server):
    from chemvas.bootstrap.web_adapter import (
        MAX_BROWSER_SESSIONS,
        SESSION_IDLE_SECONDS,
    )

    def open_window():
        return request(
            server,
            "/api/session",
            method="POST",
            body=json.dumps({"revision": 0, "action": "read"}),
        )

    ids = [json.loads(open_window()[1])["session"] for _ in range(MAX_BROWSER_SESSIONS)]
    status, body, _ = open_window()
    assert status == 400
    assert "Close a browser window" in json.loads(body)["error"]
    # Just short of the limit keeps the window; a later request refreshes it.
    stale, fresh = server.sessions[ids[0]], server.sessions[ids[1]]
    stale.last_used -= SESSION_IDLE_SECONDS
    fresh.last_used -= SESSION_IDLE_SECONDS - 5
    status, _, _ = request(
        server,
        "/api/session",
        method="POST",
        body=json.dumps({"session": ids[1], "revision": 0, "action": "read"}),
    )
    assert status == 200
    status, body, _ = open_window()
    assert status == 200
    assert ids[0] not in server.sessions and stale.closed
    assert ids[1] in server.sessions
    assert len(server.sessions) == MAX_BROWSER_SESSIONS
    status, body, _ = request(
        server,
        "/api/session",
        method="POST",
        body=json.dumps({"session": ids[0], "revision": 0, "action": "read"}),
    )
    assert status == 400
    assert "session has ended" in json.loads(body)["error"]
    status, body, _ = open_window()
    assert status == 400
