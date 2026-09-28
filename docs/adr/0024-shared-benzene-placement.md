# ADR 0024: Shared benzene placement for preview and insertion

- Status: Accepted
- Date: 2026-09-28

## Context

Benzene previews used generic polygon coordinates and fixed alternating double
bonds. Insertion used a different starting vertex and resolved bond orders against
the existing graph. A preview could therefore disagree with the committed drawing
or appear at a location where insertion was refused.

## Decision

The benzene builder owns a read-only placement plan containing coordinates,
merge candidates and resolved bond orders. Both desktop preview and insertion
use this planner. Atom matching shares the committer's tolerance; planning predicts
new IDs without allocating atoms or touching history. Existing shared edges retain
their original bond order.

The preview renderer consumes the resolved orders rather than assigning double
bonds by vertex parity. Generic templates keep their existing geometry resolver.
Document formats and insertion's transaction owner remain unchanged.

## Verification

`tests/test_benzene_template_transaction.py` compares rendered preview segments
with committed positions and bond orders for free, atom-attached and bond-fused
placements, checks rejected placements, and verifies Undo and failure rollback.
`tests/test_template_insert_logic.py` checks that preview and commit select the
same benzene path. The standard verification entry point is `make check`.
