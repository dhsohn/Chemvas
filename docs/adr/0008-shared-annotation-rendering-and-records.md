# ADR 0008: Shared annotation rendering and records

- Status: Accepted
- Date: 2026-09-23
- Extends: [ADR 0007](0007-document-owned-annotation-collections.md)


The subsequent [ADR 0011](0011-document-identities-for-groups-and-history.md)
completes the group/history ID migration identified as remaining work here.

## Problem

Image values and orbital geometry were still read from Qt items when saving.
Losing those projections could remove content from the saved document. GUI and
headless creation also assembled the same annotation dependencies separately,
while per-kind restoration wrappers and scattered rendering modules made the
owner of a change difficult to follow.

## Decision

Add immutable Qt-free `Image` and `Orbital` records to the existing typed
`AnnotationCollection`. Image records retain the original encoded bytes and
display properties; orbital records retain kind, center, scale and rotation.
Membership, order, save and group indexing use the document collections. Graphics
registries are ID-to-view dictionaries. Insert/paste image budgets use all active
records, including those without a live projection.

`ImageItem` and `OrbitalItem` read their bound records and expose explicit state
application methods. Moves, handles, property changes and history replay update
the records before rendering. Decoded image pixels and orbital lobe paths stay
in Qt; handle metadata is derived and does not own document geometry. Existing
transaction savepoints capture both records and projections for exact rollback.

Consolidate Qt annotation rendering under `ui.annotations`: item implementations,
materialization, graphics, arrows, record binding, state codecs and note styling.
Both GUI and headless callers pass a `SceneRenderContext` to the same creation
function. The editor supplies note focus behavior and manages attachment and
history. Remove seven pairs of per-kind restoration wrappers, the separate
serialization re-export facade and two forwarding state-access modules. Leave no
old module aliases. No new service, port or transaction layer is introduced.

## Consequences and remaining work

The counts below describe this migration on 2026-09-23. [ADR 0009](0009-document-owned-ring-fills.md)
subsequently migrates ring fills, bringing the current count to six of eight.

Five of eight annotation families now have document-owned values and order.
Notes, marks and ring fills remain on their existing graphics workflows. Group
members and Undo commands still retain graphics references; converting them to
IDs and data requires a separate complete lifecycle migration. Missing projections
preserve document data but are not automatically recreated during live editing.
The remaining editor service/access structure is not resolved by this package.

The document version (8), schema (1), raster bytes, drawing policies and chemistry
algorithms remain unchanged. Internal import paths change, and callers must use
record application APIs rather than editing image/orbital Qt transforms directly.

## Verification

Ownership regressions cover all five kinds through projection loss, save/reopen,
group indices, ordering, delete/Undo/Redo, failed attachment/history mutation and
reset. Additional cases exercise tampered projection geometry and image budgets
after projection loss. Native canvas interaction and baseline/current document
and raster comparisons accompany the full local gate; execution evidence is
recorded in the task ledger.
