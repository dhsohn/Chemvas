# ADR 0057: Bounded spatial layout checks

- Status: Accepted
- Date: 2026-10-13

## Problem

The layout CLI estimated work from all possible object pairs before building a
scene. A large sparse figure could exceed the 10,000-work-unit limit even when
few painted objects were near each other. The shared diagnostics also checked
attached arrow labels against strokes but omitted standalone note ink, so a
line crossing a numeric note could escape `text-arrow-overlap`.

## Decision

Keep layout diagnostics in the shared `ui.export.layout_qa_service` owner and
use a bounded spatial broad phase from `layout_spatial`. A balanced bounds tree
finds possible intersections; exact painted-path intersections retain glyph
holes, dash gaps and existing molecular adjacency exclusions. Include standalone
notes against arrow and line strokes. Warning codes, report version and stable
ordering remain unchanged; report coverage states the newly checked pair family.

Replace the CLI's all-pairs estimate with text-shaping preflight and actual work
budgets. The existing file-size and graphics-record limits remain. Bound spatial
traversal, semantic candidate pairs, individual and total path elements, summed
intersection element counts and products, and dashed-stroke expansion. Validate
geometry before allocating an oversized stroke. A limit failure produces an
error, never a partial successful report. Sheet-only checks skip collision work
but still respect the limits required to construct geometry.

This permits complete checks of sparse figures without splitting a figure into
independent panels, which would miss collisions across the split. Dense and
complex documents can still be rejected; removing resource protection is not
part of this change.

## Verification and limits

`test_layout_spatial.py` covers sparse rows, columns and grids, dense inputs,
non-finite bounds and bounded traversal. `test_layout_qa_service.py` covers
standalone note intersections with line styles, glyph holes, dash gaps, hidden
items, decorations, unchanged molecular exclusions and path/intersection limits.
`test_document_layout_check_cli.py` and `test_journal_layout_checks.py` cover
whole-document sparse checks, retained size/text guards, fail-closed stdout and
sheet-only behavior. Existing shared layout tests protect deterministic warnings.

The checker retains its declared supported object-pair families; it is not an
exhaustive visual-quality or chemistry validator. Native text metrics depend on
the platform font engine, so rendering and real canvas checks remain separate
from offscreen regression tests.
