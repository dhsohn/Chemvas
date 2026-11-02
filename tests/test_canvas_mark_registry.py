from __future__ import annotations

from chemvas.ui.canvas.canvas_mark_registry import CanvasMarkRegistry


def test_discard_removes_item_and_empty_entry() -> None:
    first = object()
    second = object()
    registry = CanvasMarkRegistry({7: [first, second]})

    registry.discard(7, first)
    assert registry.by_atom == {7: [second]}

    registry.discard(7, second)
    assert registry.by_atom == {}


def test_discard_ignores_missing_item_and_missing_atom() -> None:
    only = object()
    registry = CanvasMarkRegistry({3: [only]})

    registry.discard(3, object())
    assert registry.by_atom == {3: [only]}

    registry.discard(99, only)
    assert registry.by_atom == {3: [only]}


def test_replace_for_atom_dedupes_and_drops_empty() -> None:
    first = object()
    second = object()
    registry = CanvasMarkRegistry({1: [object()]})

    registry.replace_for_atom(1, [first, second, first])
    assert registry.by_atom == {1: [first, second]}

    registry.replace_for_atom(1, [])
    assert registry.by_atom == {}


def test_reorder_for_atom_restores_saved_indices() -> None:
    a = object()
    b = object()
    c = object()
    registry = CanvasMarkRegistry({5: [a, b, c]})

    registry.reorder_for_atom(5, [(0, c), (2, a)])
    assert registry.by_atom[5] == [c, b, a]


def test_reorder_for_atom_requires_existing_entry() -> None:
    registry = CanvasMarkRegistry()
    try:
        registry.reorder_for_atom(1, [(0, object())])
    except RuntimeError as exc:
        assert "owner registry" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for a missing atom entry")
