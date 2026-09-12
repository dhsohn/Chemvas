from __future__ import annotations

import json
from copy import deepcopy
from decimal import Decimal

import pytest

from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION, CHEMVAS_FILE_TYPE
from chemvas.features.session import DocDescriptor
from chemvas.ui import session_snapshot_store
from chemvas.ui.session_snapshot_store import SessionSnapshotStore
from tests.test_core_document_io import _canvas_state


def _drawing():
    state = _canvas_state()
    state["arrows"] = [
        {
            "kind": "arrow",
            "start": [0.0, 0.0],
            "end": [60.0, 0.0],
            "control": None,
            "double": False,
        }
    ]
    state["notes"] = [{"text": "Caption\nsecond line", "x": 5.0, "y": 25.0}]
    return state


BOUNDARY_SETTINGS = [
    ("arrow_head_scale", 0.1),
    ("arrow_head_scale", 0.8),
    ("arrow_head_scale", 0.11),
    ("text_line_spacing", 0.8),
    ("text_line_spacing", 0.81),
]


@pytest.mark.parametrize("field,value", BOUNDARY_SETTINGS)
def test_control_value_write_read_preserves_whole_drawing(tmp_path, field, value):
    state = _drawing()
    state["settings"][field] = value
    before = deepcopy(state)
    path = tmp_path / "settings.chemvas"

    written = write_document(path, state, CANVAS_FILE_VERSION)
    source_bytes = path.read_bytes()
    loaded = read_document(path)

    assert loaded.state == written.state == before
    assert loaded.source_sha256 == written.source_sha256
    assert type(loaded.state["settings"][field]) is float
    assert state == before
    assert path.read_bytes() == source_bytes


def _crashed_store(tmp_path, monkeypatch, state):
    root = tmp_path / "sessions"
    store = SessionSnapshotStore(
        root, session_id="crashed", pid=4242, process_identity="synthetic-owner"
    )
    store.begin()
    store.save_documents([DocDescriptor(state, None, "Unsaved drawing", True)])
    manifest = json.loads((store.session_dir / "session.json").read_text())
    assert manifest["clean_exit"] is False
    snapshot = store.session_dir / manifest["docs"][0]["snapshot"]
    monkeypatch.setattr(session_snapshot_store, "_pid_alive", lambda _pid: False)
    reader = SessionSnapshotStore(
        root, session_id="reader", pid=4343, process_identity="synthetic-reader"
    )
    return store, reader, snapshot


@pytest.mark.parametrize("field,value", BOUNDARY_SETTINGS)
def test_crash_snapshot_at_control_boundary_is_recovered(
    tmp_path, monkeypatch, field, value
):
    state = _drawing()
    state["settings"][field] = value
    before = deepcopy(state)
    store, reader, snapshot = _crashed_store(tmp_path, monkeypatch, state)
    source_bytes = snapshot.read_bytes()

    result = reader.consume_previous_sessions()

    assert result.warnings == []
    assert result.recovered_unsaved == 1
    assert len(result.docs) == 1
    assert result.docs[0].state == before
    assert result.docs[0].dirty is True
    assert result.docs[0].file_path is None
    assert result.docs[0].display_name == "Unsaved drawing"
    assert read_document(snapshot).state == before
    # Consumption only proposes pruning; it must retain the sole crash copy.
    assert store.session_dir.exists()
    assert snapshot.read_bytes() == source_bytes
    assert state == before


@pytest.mark.parametrize(
    "field,token,accepted",
    [
        ("arrow_head_scale", "0.09999999999999999", False),
        ("arrow_head_scale", "0.10000000000000002", True),
        ("arrow_head_scale", "0.7999999999999999", True),
        ("arrow_head_scale", "0.8000000000000002", False),
        ("text_line_spacing", "0.7999999999999999", False),
        ("text_line_spacing", "0.8000000000000002", True),
        # These would round onto the boundary if validation converted early.
        ("arrow_head_scale", "0.099999999999999999999999999999", False),
        ("arrow_head_scale", "0.800000000000000000000000000001", False),
    ],
)
def test_exact_decimal_file_boundary_is_checked_before_normalization(
    tmp_path, field, token, accepted
):
    state = _drawing()
    state["settings"][field] = "numeric-token"
    payload = {
        "type": CHEMVAS_FILE_TYPE,
        "version": CANVAS_FILE_VERSION,
        "state": state,
    }
    raw = json.dumps(payload).replace('"numeric-token"', token)
    assert json.loads(raw, parse_float=Decimal)["state"]["settings"][field] == Decimal(
        token
    )
    path = tmp_path / "decimal.chemvas"
    path.write_text(raw, encoding="utf-8")
    before = path.read_bytes()

    if accepted:
        loaded = read_document(path)
        expected = _drawing()
        expected["settings"][field] = float(token)
        assert loaded.state == expected
    else:
        with pytest.raises(ValueError, match=field):
            read_document(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("field", ["arrow_head_scale", "text_line_spacing"])
@pytest.mark.parametrize("invalid", [True, False, float("nan"), float("inf")])
def test_invalid_live_setting_cannot_overwrite_a_saved_document(
    tmp_path, field, invalid
):
    path = tmp_path / "kept.chemvas"
    valid = _drawing()
    write_document(path, valid, CANVAS_FILE_VERSION)
    source_bytes = path.read_bytes()
    bad = deepcopy(valid)
    bad["settings"][field] = invalid
    original_settings = dict(bad["settings"])

    with pytest.raises(ValueError, match="Failed to save"):
        write_document(path, bad, CANVAS_FILE_VERSION)

    assert path.read_bytes() == source_bytes
    assert read_document(path).state == valid
    assert bad["settings"] == original_settings
    assert bad["settings"][field] is invalid
    assert bad["arrows"] == valid["arrows"]
    assert bad["notes"] == valid["notes"]


@pytest.mark.parametrize("field", ["arrow_head_scale", "text_line_spacing"])
@pytest.mark.parametrize("token", ["true", "NaN", "Infinity"])
def test_invalid_snapshot_is_reported_and_retained_not_normalized(
    tmp_path, monkeypatch, field, token
):
    state = _drawing()
    _store, reader, snapshot = _crashed_store(tmp_path, monkeypatch, state)
    payload = json.loads(snapshot.read_text())
    payload["state"]["settings"][field] = "numeric-token"
    raw = json.dumps(payload).replace('"numeric-token"', token)
    snapshot.write_text(raw, encoding="utf-8")
    before = snapshot.read_bytes()

    with pytest.raises(ValueError):
        read_document(snapshot)
    result = reader.consume_previous_sessions()

    assert result.docs == []
    assert result.recovered_unsaved == 0
    assert result.prune_ids == []
    assert result.warnings
    assert "Unsaved drawing" in result.warnings[0]
    assert snapshot.read_bytes() == before
