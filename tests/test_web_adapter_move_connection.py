"""Moving a selection joins a moved arrow end to another arrow's end, as on the desktop.

The desktop's selection drag (SelectionDragMixin._apply_drag_delta_with_connect)
shifts the moved items so that the closest moved arrow end within the endpoint
snap reach lands exactly on another arrow's end; the reach is measured on
screen. The browser's move edit applies the same rule through the session.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from chemvas.bootstrap.web_adapter import edit_document, new_document
from chemvas.features.rendering import ENDPOINT_SNAP_SCREEN_PX


def two_arrows():
    document = deepcopy(new_document())
    document["state"]["arrows"] = [
        {
            "kind": "arrow",
            "start": [0.0, 0.0],
            "end": [60.0, 0.0],
            "control": None,
            "double": False,
        },
        {
            "kind": "arrow",
            "start": [100.0, 40.0],
            "end": [160.0, 40.0],
            "control": None,
            "double": False,
        },
    ]
    return document


@pytest.mark.parametrize(
    ("scale", "joined"),
    [(1.0, True), (4.0, False)],
)
def test_moved_arrow_end_joins_another_arrow_end_within_the_screen_reach(scale, joined):
    # A third of the reach at 100 %, beyond it at 400 %.
    gap = ENDPOINT_SNAP_SCREEN_PX / 3
    dx, dy = 100.0 - 60.0 - gap, 40.0
    moved = edit_document(
        {
            "document": two_arrows(),
            "edit": {
                "kind": "move",
                "selection": [{"target": "arrow", "id": 0}],
                "dx": dx,
                "dy": dy,
                "scale": scale,
            },
        }
    )["document"]["state"]["arrows"]
    shift = gap if joined else 0.0
    assert moved[0]["start"] == pytest.approx([dx + shift, dy])
    assert moved[0]["end"] == pytest.approx([60.0 + dx + shift, dy])
    if joined:
        assert moved[0]["end"] == pytest.approx(moved[1]["start"])
    # The other arrow never moves.
    assert moved[1]["start"] == [100.0, 40.0]
    assert moved[1]["end"] == [160.0, 40.0]


import json
import math
from decimal import Decimal

from chemvas.bootstrap.web_adapter import BrowserSession
from chemvas.domain.json_io import strict_json_loads


def wire_move(scale: str) -> object:
    """The move edit as the server reads it: JSON numbers arrive as Decimal."""
    text = json.dumps(
        {
            "kind": "move",
            "selection": [{"target": "arrow", "id": 0}],
            "dx": 36.0,
            "dy": 40.0,
            "scale": "SCALE",
        }
    )
    return strict_json_loads(text.replace('"SCALE"', scale).encode())


def loaded_session() -> BrowserSession:
    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": two_arrows()})
    return session


def session_state(session: BrowserSession) -> tuple:
    return (
        session.revision,
        deepcopy(session.info["document"]),
        session.history.can_undo(),
        session.history.can_redo(),
    )


# Each is refused like every other drawing scale: not a positive number up to
# the zoom maximum whose on-screen reach is finite in scene units.
UNUSABLE_WIRE_SCALES = [
    "0",
    "0.0",
    "-1",
    "true",
    "false",
    "null",
    '"1"',
    "1e-310",
    "1e-400",
    "1e309",
    "6",
]


@pytest.mark.parametrize("scale", UNUSABLE_WIRE_SCALES)
def test_a_move_with_an_unusable_wire_scale_is_refused_and_changes_nothing(scale):
    session = loaded_session()
    before = session_state(session)
    with pytest.raises(ValueError):
        session.dispatch(
            {"revision": session.revision, "action": "edit", "edit": wire_move(scale)}
        )
    assert session_state(session) == before


@pytest.mark.parametrize(
    "scale", [True, math.nan, math.inf, -math.inf, 1e-310, 0, -2.5, Decimal("1e-400")]
)
def test_a_move_with_an_unusable_scale_value_is_refused(scale):
    document = two_arrows()
    edit = {
        "kind": "move",
        "selection": [{"target": "arrow", "id": 0}],
        "dx": 36.0,
        "dy": 40.0,
        "scale": scale,
    }
    with pytest.raises(ValueError):
        edit_document({"document": document, "edit": edit})
    assert document == two_arrows()


# A fitted page can show the sheet far below 100 %; the maximum zoom is 500 %.
@pytest.mark.parametrize(("scale", "joined"), [("0.1", True), ("5", False)])
def test_fit_page_and_maximum_zoom_scales_still_move(scale, joined):
    session = loaded_session()
    revision = session.revision
    session.dispatch({"revision": revision, "action": "edit", "edit": wire_move(scale)})
    arrows = session.info["document"]["state"]["arrows"]
    shift = ENDPOINT_SNAP_SCREEN_PX / 3 if joined else 0.0
    assert arrows[0]["end"] == pytest.approx([96.0 + shift, 40.0])
    assert arrows[1]["start"] == [100.0, 40.0]
    assert (session.revision, session.history.can_undo()) == (revision + 1, True)


def test_a_move_without_a_scale_only_translates():
    # A keyboard nudge carries no scale, so it never connects.
    moved = edit_document(
        {
            "document": two_arrows(),
            "edit": {
                "kind": "move",
                "selection": [{"target": "arrow", "id": 0}],
                "dx": 36.0,
                "dy": 40.0,
            },
        }
    )["document"]["state"]["arrows"]
    assert moved[0]["start"] == (36.0, 40.0)
    assert moved[0]["end"] == (96.0, 40.0)
    assert moved[1]["start"] == [100.0, 40.0]
