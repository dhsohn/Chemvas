# ADR 0011: Document identities for groups and history

- Status: Accepted
- Date: 2026-09-24
- Extends: [ADR 0010](0010-document-owned-notes-and-marks.md)

## Problem

Annotation values belonged to document collections, but groups and history still
retained their Qt projections. Deleted items survived as long as their commands;
releasing or replacing a view could invalidate group membership or replay.
Style commands also retained canvas or item callbacks. Two history access modules
forwarded calls to existing owners without adding behavior.

## Decision

`SceneGroup` is a Qt-free document value containing atom IDs and annotation IDs.
Saving and copying resolve members through document collections and their order,
so a missing projection cannot shift or remove another member's saved reference.
Runtime IDs remain process-local and are not added to the saved file format.

Add, delete, update, ring geometry, group and mark-binding commands retain IDs and
value payloads. Text and sheet-style commands use explicit operation targets
instead of closures. Copied Qt value types such as fonts and colors are allowed;
commands must not retain QObjects, graphics items, canvases or bound callbacks.

`CanvasHistoryOperations` resolves identities at the Qt boundary. A weak cache
reuses an existing projection without owning it. `annotations.projections` can
recreate collected records and projections from history values, preserving IDs.
Existing document records remain authoritative. Active annotations are reattached
when replay needs their view. Native editing state stays in Qt while it is live.

Delete history captures document order, depth, selection and sibling ordering as
values. Sibling references include annotations, atom labels/dots and bond parts,
preserving interleaved content at the same depth. Replay updates collection
membership through the existing lifecycle service and restores stacking after
attachment. Selection is captured before removal so repeated paste/Undo/Redo
retains the original subsequent delete behavior.

Each record ID has one projection cleanup lease. Replacing a projection detaches
the old finalizer; an old wrapper retained by an exception cannot later erase its
replacement's detached record. Exact document savepoints include the weak cache,
so a failed replay does not leave a projection pointing at rolled-back data.
Short-lived savepoints still retain native objects for exact transaction rollback;
that responsibility is separate from long-lived history payloads.

Remove `history_canvas_access` and `history_recording_access`, with their consumers
calling `DocumentSavepoint`, the operations adapter or recording service directly.
Remove the unused recording selector and the redundant history hit-testing
selector. Keep the adapter that translates document identities into Qt operations.
No compatibility shim, new history stack or document schema is introduced.

## Verification and limits

Regression coverage releases deleted projections before replay, destroys active
views before geometry/style replay, checks groups with missing views, exercises
failed recreation followed by retry, and checks retained history for live Qt
references. Grouped paste selection and stacking among molecular graphics are
checked after collection. Saved documents and raster exports are compared against
the preceding implementation through the same editing sequence.

This migration does not make all editor state Qt-free. Gestures, selection,
rendering and exact rollback snapshots operate on native objects. Replay can
recreate an annotation; arbitrary damage to a running scene is not a general
automatic recovery interface. Other editor forwarding modules remain outside
this change.
