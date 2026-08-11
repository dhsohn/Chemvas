# ADR 0003: Footprint-scoped savepoint for selection move gestures

- Status: Accepted
- Date: 2026-08-11

## Context

ADR 0002 fixed one whole-document savepoint per top-level exact operation.
For drag gestures that savepoint is captured lazily on the first effective
move frame, which puts an O(document) reflection pass — one
`ObjectStateSnapshot` per atom and bond, one `SceneItemExactSnapshot` per
scene item, plus per-item topology/selection/visibility snapshots and the
full bond/atom primitive graphics captures — exactly on the frame where the
user starts pulling. Profiling on a 210-atom / 560-item document measured
10–30 ms per gesture (with 45–70 ms GC outliers), growing linearly with
document size; on realistic research schemes this is a visible hitch at the
start of every drag, regardless of how small the dragged selection is.

A selection move is special among exact operations: its mutation footprint
is closed and enumerable at capture time. The single move path
(`CanvasMoveController.move_atoms` / `move_item` with
`update_selection=False`, plus outline shifting and handle following)
touches only:

- the selected atoms' coordinates and 3D coordinates,
- the runtime state objects (already captured as single-object snapshots),
- the positions/geometry/data of a known item set: atom labels/dots,
  atom-attached marks, incident bond items, affected ring polygons, the
  independently moved selection items (with children), active handles, and
  the selection outlines. A failed commit can additionally rebuild outlines,
  creating items that did not exist at capture time.

## Decision

`DocumentSavepoint.capture` accepts an optional `MoveGestureScope`
(`atom_ids`, `bond_ids`, `scene_items`). With a scope:

- per-atom/per-bond `ObjectStateSnapshot`s and per-item
  `SceneItemExactSnapshot`s are restricted to the scope,
- `capture_scene_runtime` restricts its per-item detail snapshots
  (topology, selection, visibility, bond primitives) to the scope, while
  the **ordered scene-item identity list stays whole-document**, so
  membership restore still removes items created after capture (the rebuilt
  outlines) and identity verification stays exact,
- `capture_atom_primitive_graphics` is restricted to the scope's atoms,
- model/runtime-state/group/history single-object snapshots are unchanged.

`SelectionDragMixin._apply_drag_delta` passes the footprint; the scope is
built at first-mutation time from the same collections the move path reads.
Gestures whose footprint is not closed keep the whole-document capture:
handle drags (arbitrary geometry rewrite) and MoveTool's direct item drags
(whose atom/bond branches redraw bonds, deleting and recreating items).

The fail-closed semantics of ADR 0002 are unchanged: the savepoint is still
captured before the first mutation, restored once, and verified once. What
changes is the proven statement — restore is exact for everything the
gesture can touch, and everything else is untouched by construction of the
single move path. Anyone extending the move path with a new mutation target
must add it to the footprint builder
(`SelectionDragMixin._selection_move_scope`); the characterization suite's
drag round-trips are the behavioral guard.

## Consequences

- Drag-start capture cost scales with the selection, not the document
  (measured: 210-atom document, single-bond drag capture ~20 ms → sub-ms).
- `MoveGestureScope` is owned by the savepoint owner module
  (`chemvas.ui.transactions.document`), keeping ADR 0002's one-owner rule.
- The whole-document capture path is byte-for-byte unchanged when no scope
  is passed.
