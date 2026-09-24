# ADR 0006: Document-owned shapes

- Status: Extended by [ADR 0007](0007-document-owned-annotation-collections.md)
- Date: 2026-09-23
- Builds on: [ADR 0005](0005-responsibility-based-editor-boundaries.md)


The subsequent [ADR 0011](0011-document-identities-for-groups-and-history.md)
completes the group/history ID migration identified as remaining work here.

## Problem

Shape values were already Qt-free records, but the editor decided which shapes
existed and their saved order by iterating attached graphics items. Removing a
projection could therefore silently remove document data. Record finalizers also
treated the graphics item's lifetime as the lifetime of every shape.

## Decision

`ShapeDocument` owns canonical records and ordered active IDs. It has no Qt
dependency. The existing shared drawing state holds this owner, and
`CanvasSceneItemsState.shape_items` becomes an ID-to-view lookup, with no authority
over document membership or order. There is no second ordered graphics list.

Saving enumerates active document records. Group indices and layout diagnostics
follow the same order, retaining missing-projection slots. Explicit add/delete,
document materialization, and Undo/Redo update membership and projections through
their existing workflows. History restores order through the document owner rather
than mutating a derived item list.

The existing document, scene, and attach savepoints restore both owners on failure.
No independent transaction engine is introduced. Records for detached items remain
available to existing history commands; item finalization only releases those
inactive records. It can never delete an active document shape.

## Scope and consequences

- `.chemvas` retains its existing shape array, group indices, and schema version.
- GUI and headless materialization use the same document owner and rendering path.
- The pilot covers shapes. Other annotations and group membership still have
  graphics-based runtime ownership and can be migrated in separate coherent slices.
- History still retains graphics items. Replacing that representation with pure
  data commands is outside this change; detached record retention remains bounded
  by the existing history limit.
- Projection loss preserves shape data for saving and reconstruction on reopen.
  Automatic reconstruction of a damaged live scene is outside this change.

Verification covers projection loss, saved order and group references, repeated
delete/Undo/Redo, failed attachment and document replacement, record retention,
native canvas interactions, and GUI/headless output equivalence.
