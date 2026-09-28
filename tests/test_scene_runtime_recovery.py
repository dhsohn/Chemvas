"""Scene recovery reports failed Qt mutations and remains retryable."""

from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

from chemvas.ui.transactions.scene_runtime import capture_scene_runtime
from chemvas.ui.transactions.scene_runtime_restore import restore_scene_runtime


@pytest.mark.parametrize("operation", ["addItem", "removeItem"])
@pytest.mark.parametrize("failure", ["raise", "false", "no-op"])
def test_scene_membership_failure_is_reported_while_other_state_restores(
    qt_application, monkeypatch, operation, failure
):
    scene = QGraphicsScene()
    retained = scene.addRect(0, 0, 10, 10)
    peer = scene.addRect(20, 0, 10, 10)
    peer.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    peer.setSelected(True)
    peer.setZValue(3)
    expected = list(scene.items())
    snapshot = capture_scene_runtime(SimpleNamespace(scene=lambda: scene))
    if operation == "addItem":
        scene.removeItem(retained)
        target = retained
    else:
        target = scene.addRect(50, 0, 10, 10)
    peer.setSelected(False)
    peer.setZValue(9)
    attempted = []
    original_error = RuntimeError("edit failed")

    def fail(item):
        attempted.append(item)
        if failure == "raise":
            raise RuntimeError("Qt mutation unavailable")
        return False if failure == "false" else None

    with monkeypatch.context() as patch:
        patch.setattr(scene, operation, fail)
        errors = restore_scene_runtime(
            snapshot, original_error=original_error, collect_errors=True
        )

    assert target in attempted
    assert errors
    assert any("scene restore" in str(error) for error in errors)
    assert (target.scene() is scene) == (operation == "removeItem")
    assert peer.isSelected() and peer.zValue() == 3
    assert not scene.signalsBlocked()
    assert restore_scene_runtime(snapshot, collect_errors=True) == []
    assert list(scene.items()) == expected


@pytest.mark.parametrize("behind_parent", [False, True])
def test_restoring_stacking_flags_preserves_unrelated_interaction_flags(
    qt_application, behind_parent
):
    scene = QGraphicsScene()
    parent = scene.addRect(0, 0, 20, 20)
    child = scene.addRect(1, 1, 2, 2)
    child.setParentItem(parent)
    stacking = QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent
    movable = QGraphicsItem.GraphicsItemFlag.ItemIsMovable
    child.setFlag(stacking, behind_parent)
    expected = list(scene.items())
    snapshot = capture_scene_runtime(SimpleNamespace(scene=lambda: scene))
    child.setFlag(stacking, not behind_parent)
    child.setFlag(movable, True)

    errors = restore_scene_runtime(snapshot, collect_errors=True)

    assert errors == []
    assert child.parentItem() is parent
    assert bool(child.flags() & stacking) == behind_parent
    assert child.flags() & movable
    assert list(scene.items()) == expected
