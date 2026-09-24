# ADR 0014: One spelling for canvas and window state

- Status: Accepted
- Date: 2026-09-24
- Extends: [ADR 0012](0012-flat-editor-runtime-and-ui-packages.md), [ADR 0013](0013-editor-followups-splits-ports-core-scope.md)

## Problem

ADR 0012 removed the modules that consisted only of forwarders, but 229
single-statement forwarders survived inside modules that also hold real
logic: `atom_items_for(canvas)` for `canvas.runtime_state.atom_graphics_state.atom_items`,
`services_for_window(window)` for `window.services`,
`remove_marks_for_atom_for(canvas, atom_id)` for
`canvas.services.canvas_mark_scene_service.remove_marks_for_atom(atom_id)`,
and so on. Each of them was a second spelling for state or a runtime that
already has one owner, and each one was a seam that tests patched instead of
the owner.

The window-level operations in `main_window_ports` were also a candidate for
becoming `MainWindow` methods. `MainWindow` lives in `shell`, which the
dependency rules keep free of `ui`, and every one of those operations resolves
editor objects, so they cannot move there without inverting that edge.

## Decision

1. A single-statement forwarder that only reads or writes a field, or calls
   one method, of a canvas- or window-owned object is inlined at every call
   site and deleted. The mechanical rule: the replacement uses only the call's
   own arguments, attribute access, literals and builtins; a forwarder whose
   body needs a helper, a Qt constructor or a module constant stays.
   Forwarders that callers pass around as callables (the scene item
   operations in `scene_item_access`) stay as functions.
2. Tests exercise owners, not seams: a test that used to patch
   `preview_for_window` on a service module now gives the fake window a
   `preview_3d` attribute, and a test that patched `snapshot_canvas_state_for`
   now patches `snapshot_state` on the canvas's document session service.
3. The `*_for_window` operations stay as functions in
   `chemvas.ui.window.main_window_ports`. What remains there is the set with
   logic: active-canvas resolution, text-editor-aware undo/redo/clipboard,
   zoom, sheet setup and the selection transforms.

## Verification and limits

Every pass ran ruff, mypy and `make check`. The inlining tool rewrites a call
only in files that import the name from its defining or re-exporting module,
after an earlier attempt that matched by name alone rewrote calls to
same-named functions in other modules and was discarded. Remaining
`_access`/`_state` modules hold multi-statement policy or dataclasses; their
names are historical and are not changed here. One structural pin that
recognized scene detachment only through the removed `canvas_scene_for`
resolver could no longer see the canonical `canvas.scene()` spelling and is
removed rather than kept hollow; the group rollback pin now recognizes the
`group_state` attribute as well as the old helper names.
