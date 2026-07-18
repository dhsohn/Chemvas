import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from chemvas.core.tool_overlay_logic import (  # noqa: E402
    activate_tool_no_drag,
    clear_temporary_tool_overlay,
)


class _Scene:
    def __init__(self) -> None:
        self.removed_items = []

    def removeItem(self, item) -> None:
        self.removed_items.append(item)


class _Canvas:
    DragMode = SimpleNamespace(NoDrag="none")

    def __init__(self) -> None:
        self.drag_mode = None
        self.scene_obj = _Scene()
        self.clear_handles_calls = 0

    def setDragMode(self, mode) -> None:
        self.drag_mode = mode

    def scene(self):
        return self.scene_obj

    def clear_handles(self) -> None:
        self.clear_handles_calls += 1


class _PreviewItem:
    def __init__(self, scene_obj) -> None:
        self._scene = scene_obj

    def scene(self):
        return self._scene


class _BrokenPreviewItem:
    def scene(self):
        raise RuntimeError("wrapped C/C++ object has been deleted")


class ToolOverlayLogicTest(unittest.TestCase):
    def test_activate_tool_no_drag_sets_canvas_drag_mode(self) -> None:
        canvas = _Canvas()

        activate_tool_no_drag(canvas)

        self.assertEqual(canvas.drag_mode, canvas.DragMode.NoDrag)

    def test_clear_temporary_tool_overlay_removes_preview_item_from_current_scene(
        self,
    ) -> None:
        canvas = _Canvas()
        preview_item = _PreviewItem(canvas.scene())

        result = clear_temporary_tool_overlay(canvas, preview_item=preview_item)

        self.assertIsNone(result)
        self.assertEqual(canvas.scene_obj.removed_items, [preview_item])

    def test_clear_temporary_tool_overlay_clears_handles_through_explicit_callback(
        self,
    ) -> None:
        canvas = _Canvas()

        result = clear_temporary_tool_overlay(
            canvas,
            clear_handles=True,
            clear_handles_callback=canvas.clear_handles,
        )

        self.assertIsNone(result)
        self.assertEqual(canvas.clear_handles_calls, 1)

    def test_clear_temporary_tool_overlay_does_not_call_canvas_handle_alias(
        self,
    ) -> None:
        canvas = _Canvas()

        result = clear_temporary_tool_overlay(canvas, clear_handles=True)

        self.assertIsNone(result)
        self.assertEqual(canvas.clear_handles_calls, 0)

    def test_clear_temporary_tool_overlay_ignores_preview_item_from_other_scene(
        self,
    ) -> None:
        canvas = _Canvas()
        preview_item = _PreviewItem(_Scene())

        result = clear_temporary_tool_overlay(canvas, preview_item=preview_item)

        self.assertIsNone(result)
        self.assertEqual(canvas.scene_obj.removed_items, [])

    def test_clear_temporary_tool_overlay_ignores_runtime_error_from_preview_item(
        self,
    ) -> None:
        canvas = _Canvas()

        result = clear_temporary_tool_overlay(canvas, preview_item=_BrokenPreviewItem())

        self.assertIsNone(result)
        self.assertEqual(canvas.scene_obj.removed_items, [])


if __name__ == "__main__":
    unittest.main()
