from types import SimpleNamespace

import pytest
from chemvas.ui.canvas_state_lookup import canvas_state_object, ensure_canvas_state


def test_canvas_state_object_prefers_runtime_state_over_public_canvas_attr() -> None:
    canvas = SimpleNamespace(
        graph_state="public",
        _graph_state="legacy",
        runtime_state=SimpleNamespace(graph_state="runtime"),
    )

    assert canvas_state_object(canvas, "graph_state") == "runtime"
    assert canvas_state_object(canvas, "_graph_state") == "runtime"


def test_canvas_state_object_uses_public_canvas_attr_without_runtime_state() -> None:
    canvas = SimpleNamespace(graph_state="public", _graph_state="legacy")

    assert canvas_state_object(canvas, "graph_state") == "public"
    assert canvas_state_object(canvas, "_graph_state") == "public"


def test_canvas_state_object_uses_runtime_state_and_ignores_private_attr() -> None:
    canvas = SimpleNamespace(
        _insert_state="legacy", runtime_state=SimpleNamespace(insert_state="runtime")
    )

    assert canvas_state_object(canvas, "insert_state") == "runtime"


def test_canvas_state_object_ignores_private_attr_without_promoting_it() -> None:
    canvas = SimpleNamespace(_insert_state="legacy")

    assert canvas_state_object(canvas, "insert_state") is None
    assert not hasattr(canvas, "insert_state")


def test_canvas_state_object_uses_runtime_state_public_name() -> None:
    canvas = SimpleNamespace(runtime_state=SimpleNamespace(rotation_state="runtime"))

    assert canvas_state_object(canvas, "rotation_state") == "runtime"
    assert canvas_state_object(canvas, "_rotation_state") == "runtime"


def test_canvas_state_object_returns_none_when_missing() -> None:
    assert canvas_state_object(SimpleNamespace(), "missing_state") is None


class _StrictContainer(SimpleNamespace):
    STRICT_STATE_CONTAINER = True


def test_ensure_canvas_state_returns_runtime_state_field() -> None:
    canvas = SimpleNamespace(runtime_state=SimpleNamespace(group_state="runtime"))

    assert ensure_canvas_state(canvas, "group_state", lambda: "fresh") == "runtime"


def test_ensure_canvas_state_lazily_attaches_on_bare_canvas() -> None:
    canvas = SimpleNamespace()

    state = ensure_canvas_state(canvas, "group_state", list)

    assert state == []
    assert canvas.group_state is state
    assert ensure_canvas_state(canvas, "group_state", list) is state


def test_ensure_canvas_state_rejects_missing_field_on_strict_container() -> None:
    # A strict container missing the field means the accessor and the runtime
    # container are out of sync; attaching a shadow state would split the
    # state in two, so this must fail loudly.
    canvas = SimpleNamespace(runtime_state=_StrictContainer())

    with pytest.raises(AttributeError, match="out of sync"):
        ensure_canvas_state(canvas, "group_state", list)
    assert not hasattr(canvas, "group_state")


def test_ensure_canvas_state_direct_attr_skips_strict_check() -> None:
    canvas = SimpleNamespace(runtime_state=_StrictContainer())

    state = ensure_canvas_state(
        canvas, "renderer", lambda: "fresh", runtime_field=False
    )

    assert state == "fresh"
    assert canvas.renderer == "fresh"


def test_ensure_canvas_state_prefers_runtime_entry_even_for_direct_attr() -> None:
    canvas = SimpleNamespace(
        renderer="public", runtime_state=SimpleNamespace(renderer="runtime")
    )

    assert (
        ensure_canvas_state(canvas, "renderer", lambda: "fresh", runtime_field=False)
        == "runtime"
    )
