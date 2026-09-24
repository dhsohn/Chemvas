# ADR 0007: Document-owned annotation collections

- Status: Accepted
- Date: 2026-09-23
- Extends: [ADR 0006](0006-document-owned-shapes.md)
- Extended by: [ADR 0008](0008-shared-annotation-rendering-and-records.md), which migrates images and orbitals and consolidates annotation rendering.


The subsequent [ADR 0011](0011-document-identities-for-groups-and-history.md)
completes the group/history ID migration identified as remaining work here.

## Problem

Arrows and TS brackets already had Qt-free values, but their graphics lists still
determined document membership and order. Disposing a view could silently delete
its record. Repeating the shape pilot as a separate owner for each annotation
kind would duplicate the same lifecycle and ordering rules.

## Decision

One Qt-free `AnnotationCollection[Record]` owns ordered active IDs and canonical
records. Shape, Arrow and TSBracket collections use this same implementation.
It replaces `ShapeDocument`, `CanvasArrowState` and `CanvasTSBracketState`;
there are no compatibility aliases or parallel ordered graphics lists.

The shared scene state holds these typed collections. Its graphics registries
are ID-to-view dictionaries. Saving reads canonical records in document order,
without querying graphics items. Group indices and layout diagnostics preserve
slots for missing projections. Finalization may release inactive records retained
by existing history, but cannot delete an active document record.

Explicit add/delete, Undo/Redo, GUI and headless loading all update the same
membership. The existing attach, scene runtime and document savepoints restore
records, ordering and projection dictionaries; failed reattachment preserves the
previous order and container identity. No new transaction or rendering engine is
introduced. IDs and storage changes do not alter the file schema.

## Remaining boundaries

Notes, marks, rings, orbitals and images still own values through their graphics
workflows. Rich-text editing and atom-bound mark updates need explicit document
mutations before those values can be owned by the document. Groups still retain
graphics members, and history still retains graphics items. Their transition to
IDs and data must migrate creation, editing, deletion and recovery together.

This change establishes shared record membership for all three existing typed
annotation records. It does not claim completion of the remaining annotation or
history migrations.

## Verification

The shape ownership regression suite now covers all three kinds: detached,
destroyed and released projections; save/reopen and group indices; dictionary
reordering; repeated delete/Undo/Redo; failure rollback; empty-scene redo; and
reset after projection loss. Native canvas workflows cover drawing, editing,
selection, deletion and history. Differential mixed-annotation documents compare
serialized bytes before and after this change, alongside the full local gate.
