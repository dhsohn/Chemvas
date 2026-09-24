# ADR 0009: Document-owned ring fills

- Status: Accepted
- Date: 2026-09-24
- Extends: [ADR 0008](0008-shared-annotation-rendering-and-records.md)

## Problem

Ring membership, order and fill appearance were owned by Qt polygons. Saving or
copying could lose a fill when its polygon disappeared. A Qt data-role witness
was needed to retain opacity more precisely than the paint brush. Coordinates
already belonged to molecular atoms, so moving them into another record would
create redundant geometry ownership.

## Decision

Store immutable `RingFill` records in the existing `AnnotationCollection`.
Each record owns ordered atom IDs, color and exact alpha; coordinates always come
from the current molecular graph. Keep polygon items in an ID-to-view dictionary.
The shared GUI/headless materializer creates `RingFillItem` projections. Explicit
fill edits update the record before painting, and the selection topology role is
derived from the record. Remove the old brush-alpha witness module.

Save and clipboard serialization read document records, retaining the existing
policy of excluding fills whose atoms no longer form a bonded cycle. Bond-side
geometry also reads ring topology from records. Editing/deleting a ring with a
missing view rebuilds that projection using the existing record ID; its old
wrapper relinquishes record cleanup so it cannot destroy later Undo data.

The existing history and transaction machinery owns membership/order changes,
rollback and redo retention. Reattachment redraws the polygon from restored
atoms. No new history stack, schema version, service hierarchy or compatibility
alias is introduced. Schema 1 and document version 8 stay unchanged.

## Consequences and verification

Six of eight annotation families now own their values and order independently
of Qt. [ADR 0010](0010-document-owned-notes-and-marks.md) subsequently migrates
notes and marks; groups and history still retain item
references. Ring projection recovery does not claim to solve those other
lifecycles.

Tests cover save/reopen and copy after projection loss; precise alpha and Qt
tampering; cycle deletion, repeated Undo/Redo and failed publication; record order
and reset. Native canvas workflows, baseline/current document and raster
comparisons, protected-code checks and the full local gate accompany this change.
