from types import SimpleNamespace

from ui.canvas_state_lookup import canvas_state_object


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
    canvas = SimpleNamespace(_insert_state="legacy", runtime_state=SimpleNamespace(insert_state="runtime"))

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
